import { request } from './request.js'
import { storageContext } from './storage.js'
import { getSession } from './session.js'
import { newHealthRequestId } from './health-task-flow.js'
import { dishKey } from '../utils/meal-presentation.js'
import { localDate } from '../utils/meal-state.js'
import { watch } from 'vue'
import { readDailyMealPlan } from './daily-meal-plan.js'

// Visibility is an input: returning to the same plan version must reload candidates.
export function watchDishSwap({ client, plan, enabled }) {
  const stop = watch([plan, enabled], ([value, active]) => {
    if (active && value) void client.load(value)
    else client.pause()
  }, { immediate:true })
  return () => { stop(); client.clear() }
}

export const dishSwapState = () => ({ loading:false, busy:false, open:false, error:'', entries:[], version:null, date:'', target:null, selected:'' })

/** 保留原候选和来源；占位译名不参与判重。 */
function distinctSwapCandidates(candidates) {
  const result=[],seen=new Set()
  for(const candidate of candidates){
    const dish=candidate.dish,keys=['candidate:'+candidate.candidate_id]
    const file=dish?.source?.file_id||dish?.file_id
    const name=String(dish?.name||'').normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]+/gu,'')
    if(file)keys.push('file:'+file)
    if(name)keys.push('name:'+name)
    if(keys.some(key=>seen.has(key)))continue
    result.push(candidate);keys.forEach(key=>seen.add(key))
    if(result.length===3)break
  }
  return result
}

export function createDishSwap({ state, send=request, context=storageContext, family=()=>getSession().householdId,
  day=localDate, newId=newHealthRequestId, onPlan=()=>{}, readPlan=(familyId,date)=>readDailyMealPlan(familyId,date,send,{fresh:true}), schedule=setTimeout, cancel=clearTimeout }) {
  let generation=0, plan=null, owner='', requestId='', attempted='', retryTimer=null, snapshot=null
  function pause() {
    if(retryTimer!==null){cancel(retryTimer);retryTimer=null}
    generation++;plan=null;owner='';requestId='';attempted='';Object.assign(state,dishSwapState())
  }
  function clear() { pause(); snapshot=null }
  function scopeKey(value) { return JSON.stringify([context(),family(),day(),value?.date,value?.version]) }
  async function load(value, retryAttempt=0, refresh=false) {
    pause()
    if(value?.date!==day()||value.status!=='ready'){snapshot=null;return}
    const key=scopeKey(value)
    if(snapshot?.key!==key)snapshot=null
    plan=value;owner=context()
    if(snapshot)Object.assign(state,{entries:snapshot.entries,version:value.version,date:value.date})
    const ticket=generation, familyId=family(), scope=owner
    const current=()=>ticket===generation&&scope===context()&&value.date===day()&&familyId===family()
    state.loading=true
    try {
      if(refresh){
        const latest=await readPlan(familyId,value.date)
        if(!current())return
        if(latest.date!==value.date||latest.status!=='ready'||!Number.isInteger(latest.version)||latest.version<value.version)throw Error('餐单尚未核对完成')
        if(latest.version>value.version)await onPlan(latest)
        if(current())await load(latest,retryAttempt+1)
        return
      }
      const {data}=await send({path:'/api/family/'+encodeURIComponent(familyId)+'/daily-meal-plans/'+value.date+'/dish-swap-candidates?version='+value.version})
      if(!current())return
      if(data.date!==value.date||data.version!==value.version||!Array.isArray(data.meals))throw Object.assign(Error('候选版本不一致，请刷新餐单。'),{code:409})
      state.entries=data.meals.flatMap(m=>(m.dishes||[]).map(d=>({mealType:m.meal_type,dishKey:d.dish_key,candidates:distinctSwapCandidates(d.candidates||[])})))
      state.version=data.version;state.date=data.date
      snapshot={key,entries:state.entries}
    } catch(error) {
      // Candidate reads are background work; recover quietly while this page and plan remain current.
      if(!current())return
      if([401,403,404,410].includes(Number(error.code))){clear();return}
      if(Number(error.code)===409){
        snapshot=null;state.entries=[];state.version=null;state.date=''
        // Fetch the current plan before asking for candidates again.
        if(!refresh&&retryAttempt===0)return await load(value,retryAttempt,true)
        refresh=true
      }
      if(current()){
        const delays=[2000,5000,10000,30000,60000]
        retryTimer=schedule(()=>{
          retryTimer=null
          if(current())void load(value,retryAttempt+1,refresh)
        },delays[Math.min(retryAttempt,delays.length-1)])
        retryTimer?.unref?.()
      }
    }
    finally { if(current())state.loading=false }
  }
  function candidates(item,dish,value=plan) {
    if(owner!==context()||!plan||snapshot?.key!==scopeKey(plan)||plan.date!==day()||value?.version!==plan.version||value.date!==plan.date)return []
    return state.entries.find(e=>e.mealType===item.meal_type&&e.dishKey===dishKey(dish))?.candidates||[]
  }
  function open(item,dish,value) {
    if(state.busy||state.loading||!candidates(item,dish,value).length)return
    state.target={item,dish,plan:value,candidates:candidates(item,dish,value)}
    state.open=true;state.error='';state.selected='';requestId='';attempted=''
  }
  function close() { if(!state.busy){state.open=false;state.target=null} }
  async function choose(candidate) {
    const target=state.target
    if(state.busy||!target||!target.candidates.some(c=>c.candidate_id===candidate.candidate_id)||owner!==context()||plan.date!==day())return
    if(attempted&&attempted!==candidate.candidate_id)return
    attempted=candidate.candidate_id;requestId ||= newId()
    const ticket=generation,scope=owner,familyId=family()
    const current=()=>ticket===generation&&scope===context()&&familyId===family()&&plan?.date===day()
    state.busy=true;state.error='';state.selected=candidate.candidate_id
    try {
      const {data}=await send({path:'/api/family/'+encodeURIComponent(familyId)+'/daily-meal-plans/'+plan.date+'/dish-swaps',method:'POST',
        data:{version:plan.version,meal_type:target.item.meal_type,dish_key:dishKey(target.dish),candidate_id:candidate.candidate_id,client_request_id:requestId}})
      if(!current())return
      if(data.date!==plan.date||data.status!=='ready'||!Number.isInteger(data.version)||data.version<=plan.version)throw Error('换菜结果尚未确认，请刷新餐单。')
      state.open=false;state.target=null
      await onPlan(data)
      if(current())await load(data)
    } catch(error) {
      if(!current())return
      state.error=error.code===409?'餐单或候选已更新，请关闭后刷新餐单。':(error.message||'结果尚未确认，请重试同一道候选。')
      // An unknown response keeps the same request key and candidate for a safe retry.
    } finally { if(current())state.busy=false }
  }
  return {load,pause,clear,candidates,open,close,choose}
}
