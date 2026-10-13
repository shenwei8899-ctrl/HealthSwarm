import { scopedStorage } from '../services/storage.js'
import { getProfile } from './profile.js'
import { createPlan, subtotal } from './demo.js'
import { getOrders } from './orders.js'
import { DAILY_MEALS } from './meal-flow.js'
import { applyMealCustomization, getMealSwap } from './meal-customization.js'
import { ingredientConflicts, unresolvedHealth } from './health.js'
import { isMockMode } from '../services/config.js'
import { mealPlanKey, readMealResult, writeMealResult, unavailableMeal, MEAL_RULE_VERSION } from './meal-plan-store.js'

export function localDate(date = new Date()) { const shanghai=new Date(date.getTime()+8*60*60*1000);return `${shanghai.getUTCFullYear()}-${String(shanghai.getUTCMonth()+1).padStart(2,'0')}-${String(shanghai.getUTCDate()).padStart(2,'0')}` }
const read = () => scopedStorage.getStorageSync('meal-session-v3') || {}
const write = value => scopedStorage.setStorageSync('meal-session-v3',JSON.parse(JSON.stringify(value)))
const profileSignature = profile => JSON.stringify({rules:MEAL_RULE_VERSION,members:profile.members,defaultDiners:profile.defaultDiners,usageMode:profile.usageMode,goals:profile.goals,tastes:profile.tastes})
export function mealProfile(profile, meal, date=localDate()) {
  const saved=read()[date]?.[meal]?.members
  const defaults=profile.usageMode==='个人使用' ? [profile.members.find(m=>m.relation==='本人')?.id || profile.members[0]?.id] : profile.defaultDiners
  const ids=(saved || defaults || []).filter(id=>profile.members.some(m=>m.id===id))
  return {...profile, mealScoped:true,defaultDiners:ids.length?ids:[profile.members[0]?.id]}
}
export function activePlanOrder(date=localDate()) {
  return getOrders().find(o=>o.sourcePlanId && ['paid','partial','delivered'].includes(o.status) && !o.planPaused && o.deliveryBatches?.some(b=>b.date===date)) || null
}
export function todayPlan(profile=getProfile(),meal='晚餐',date=localDate()) {
  const scoped=mealProfile(profile,meal,date), paid=activePlanOrder(date)
  const batch=paid?.deliveryBatches.find(b=>b.date===date)
  const snapshot=paid?.cookingGuides?.find(b=>b.index===batch.index)?.guides.find(g=>g.meal===meal)
  const state=read()[date]?.[meal]
  const savedSwap=getMealSwap(meal), key=mealPlanKey(scoped,meal,date,savedSwap)
  let plan=readMealResult(date,meal,key)
  if (!plan) {
    plan=isMockMode?createPlan(scoped,meal,date):unavailableMeal(scoped.members.filter(member=>scoped.defaultDiners.includes(member.id)),meal,date)
    if (isMockMode) {
      const swap=applyMealCustomization(plan,savedSwap)
      if (!ingredientConflicts(plan.members,swap.dishes.map(d=>d.name+' '+d.detail).concat(swap.products.map(p=>p.name))).length) plan=swap
      writeMealResult(date,meal,key,plan)
    }
  }
  if (snapshot) {
    // Purchased recipes are immutable. Only today's eating advice follows current members.
    const known=snapshot.dishGuides.flatMap(d=>d.ingredients).concat(snapshot.dishes)
    const issues=[...ingredientConflicts(plan.members,known),...unresolvedHealth(plan.members),...plan.blocked]
    const unique=[...new Set(issues)]
    return {...plan,dishes:snapshot.dishGuides.map(d=>({name:d.name,recipeId:d.recipeId,recipeVersion:d.recipeVersion,steps:d.steps,notes:d.notes,detail:d.ingredients.join(' · '),icon:d.icon||'菜',color:'#e4f0d3',nutrition:d.nutrition ?? null})),products:paid.items,
      memberNotes:plan.memberNotes.map(note=>({...note,dishes:(note.dishes||[]).filter(portion=>snapshot.dishGuides.some(dish=>dish.recipeId===portion.recipeId&&dish.recipeVersion===portion.recipeVersion))})),
      blocked:unique, issues:unique.map(message=>({type:/请补充/.test(message)?'needs_info':'conflict',message})), safeSuggestions:unique.length&&!plan.blocked.length?plan.dishes.map(d=>d.name):[], safetyText:unique.length?'已购菜谱的当前吃法需要复核':'已避开已知冲突', paid:true, orderId:paid.id,batchIndex:batch.index,source:'执行中的 AI 专属计划',snapshot,nutrition:null}
  }
  if (state?.proposal && state.profileKey===profileSignature(profile)) {
    plan={...plan,...state.proposal,members:plan.members,memberNotes:plan.memberNotes}
    const issues=ingredientConflicts(plan.members,plan.dishes.map(d=>d.name+' '+d.detail).concat(plan.products.map(p=>p.name)))
    if (!issues.length && state.proposalKey===key) return {...plan,source:'已保存的明日提议'}
    plan=readMealResult(date,meal,key) || (isMockMode?createPlan(scoped,meal,date):unavailableMeal(plan.members,meal,date))
  }
  return {...plan,source:'家庭档案建议'}
}
export function saveTomorrowProposal(profile,meal) {
  const date=new Date(); date.setDate(date.getDate()+1); const key=localDate(date), store=read()
  store[key] ||= {}; store[key][meal] ||= {}
  const scoped=mealProfile(profile,meal,key)
  const proposalKey=mealPlanKey(scoped,meal,key,getMealSwap(meal))
  store[key][meal].proposal=readMealResult(key,meal,proposalKey) || (isMockMode?createPlan(scoped,meal,key):null)
  store[key][meal].proposalKey=proposalKey
  store[key][meal].profileKey=profileSignature(profile)
  write(store)
}
export function setMealMembers(profile,meal,ids,date=localDate()) {
  if (!ids.length) return false
  const store=read();store[date] ||= {};store[date][meal] ||= {};store[date][meal].members=ids
  delete store[date][meal].proposal
  write(store);return true
}
export function selectedFor(meal,products,date=localDate()) {
  const unchecked=read()[date]?.[meal]?.unchecked || []
  return products.filter(p=>!unchecked.includes(p.id)).map(p=>p.id)
}
export function saveSelection(meal,products,selected,date=localDate()) {
  const store=read();store[date] ||= {};store[date][meal] ||= {}
  store[date][meal].unchecked=products.filter(p=>!selected.includes(p.id)).map(p=>p.id);write(store)
}
export function mergeDailyProducts(plans, selectedMap) {
  const map=new Map()
  for(const plan of plans) for(const p of plan.products) {
    if(selectedMap && !selectedMap[plan.meal]?.includes(p.id)) continue
    const key=`${p.id}:${p.pack}:${p.unit}`
    if(map.has(key)) map.get(key).need+=p.need
    else map.set(key,{...p,need:p.need})
  }
  return [...map.values()].map(p=>({...p,quantity:Math.ceil(p.need/p.pack)}))
}
export function dailyProcurement(profile,meals=DAILY_MEALS.map(m=>m.name)) {
  const plans=meals.map(m=>todayPlan(profile,m))
  const selectedProducts=mergeDailyProducts(plans,Object.fromEntries(plans.map(p=>[p.meal,selectedFor(p.meal,p.products)])))
  const products=mergeDailyProducts(plans).map(p=>selectedProducts.find(s=>s.id===p.id)||p)
  return {plans,products,selectedProducts,selectedIds:selectedProducts.map(p=>p.id),blocked:plans.flatMap(p=>p.blocked)}
}
export function changeResult(before,after,selected) {
  if(after.paid) return '本餐就餐者已更新；已支付订单的商品、价格与配送不变，仅更新分餐建议与安全提示。'
  const previous=selected || before.products.map(p=>p.id)
  const unchecked=before.products.filter(p=>!previous.includes(p.id)).map(p=>p.id)
  const next=after.products.filter(p=>!unchecked.includes(p.id)).map(p=>p.id)
  const a=subtotal(before.products,previous),b=subtotal(after.products,next)
  const changed=JSON.stringify(before.products.map(p=>[p.id,p.quantity]))!==JSON.stringify(after.products.map(p=>[p.id,p.quantity]))
  return `已按 ${after.count} 位就餐成员更新本餐建议。`+(changed?`食材清单已更新，预计金额 ¥${(a/100).toFixed(2)} → ¥${(b/100).toFixed(2)}。`:'采购数量无需调整。')
}
