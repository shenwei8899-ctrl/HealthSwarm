import { callApiAdapter } from './index.js'
import { isMockMode } from './config.js'
import { storageContext } from './storage.js'
import { getMealMembers, subtotal } from '../utils/demo.js'
import { getProfile } from '../utils/profile.js'
import { adaptExclusivePlan, exclusivePlanKey, saveExclusivePlan, defaultPlanStartDate } from '../utils/exclusive-plans.js'
import { memberAge, shanghaiDate } from '../utils/member-age.js'
import { mealContext, planningMembers } from '../utils/meal-context.js'
import { normalizeMealResult } from '../utils/meal-result.js'
import { mergeDailyProducts } from '../utils/meal-state.js'
import { MEAL_RULE_VERSION } from '../utils/meal-plan-store.js'

const pending=new Map()
const latest=new Map()
export async function ensureExclusivePlan(template,profile=getProfile(),{startDate=defaultPlanStartDate(),force=false,mode=isMockMode?'mock':'api'}={}) {
  const cached=adaptExclusivePlan(template,profile,startDate)
  if(mode==='mock'||(!force&&cached.sourceType==='api'))return cached
  const scope=storageContext(),key=exclusivePlanKey(template,profile,startDate),taskKey=scope+key
  if(pending.has(taskKey))return pending.get(taskKey)
  const slot=scope+':'+template.id,liveKey=exclusivePlanKey(template,getProfile(),startDate)
  latest.set(slot,taskKey)
  const task=(async()=>{
    const input={clientRequestId:'exclusive-'+Date.now()+'-'+Math.random().toString(36).slice(2),ruleVersion:MEAL_RULE_VERSION,templateId:template.id,startDate,count:21,
      members:planningMembers(getMealMembers(profile),profile.viewerAccount),context:mealContext(shanghaiDate()),goals:profile.goals||[],tastes:profile.tastes||[]}
    const result=await callApiAdapter('generateExclusivePlan',input)
    if(!result?.generationId||!Array.isArray(result.days)||result.days.length!==21)throw new Error('专属计划结果不完整，请重试')
    const variants=result.days.map((day,index)=>{
      const date=new Date(startDate+'T00:00:00Z');date.setUTCDate(date.getUTCDate()+index);const target=date.toISOString().slice(0,10)
      if(day.date!==target||!Array.isArray(day.plans)||day.plans.length!==3||new Set(day.plans.map(p=>p.meal)).size!==3)throw new Error('专属计划餐次或日期不完整')
      return ['早餐','午餐','晚餐'].map(meal=>normalizeMealResult(day.plans.find(plan=>plan.meal===meal),{...input,date:target,meal,members:input.members.map(member=>({...member,age:memberAge(member,target).years,ageMonths:memberAge(member,target).months}))}))
    })
    if(scope!==storageContext()||latest.get(slot)!==taskKey||liveKey!==exclusivePlanKey(template,getProfile(),startDate)||key!==exclusivePlanKey(template,profile,startDate))throw new Error('计划依据已变化，请重新分析')
    const costs=variants.map(plans=>{const products=mergeDailyProducts(plans);return subtotal(products,products.map(product=>product.id))})
    const first=mergeDailyProducts(variants[0])
    const plan={...template,sourceType:'api',fixturePlans:variants,generation:result.generationId,
      days:variants.map((plans,index)=>({day:'第 '+(index+1)+' 天',meals:plans.map(p=>({type:p.meal,name:p.dishes.map(d=>d.name).join('与'),minutes:p.minutes||0,image:template.image}))})),
      products:first.map(product=>({name:product.name,count:product.quantity+' 包 · '+product.pack+product.unit,cents:product.priceCents*product.quantity,image:template.image})),
      estimateCents:costs[0],totalEstimateCents:costs.reduce((sum,cost)=>sum+cost,0),blocked:[...new Set(variants.flatMap(plans=>plans.flatMap(p=>p.blocked)))]}
    saveExclusivePlan(template,profile,startDate,plan);return plan
  })()
  pending.set(taskKey,task)
  try{return await task}finally{pending.delete(taskKey)}
}
