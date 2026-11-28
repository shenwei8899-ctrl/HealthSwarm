import { request } from './request.js'
import { storageContext } from './storage.js'
import { getSession } from './session.js'
import { newHealthRequestId } from './health-task-flow.js'
import { dishKey } from '../utils/meal-presentation.js'
import { localDate } from '../utils/meal-state.js'
import { watch } from 'vue'
import { readDailyMealPlan } from './daily-meal-plan.js'

// Visibility is an input: returning to the same plan version must reload candidates.
export function watchDishSwap({ client, plan, enabled, mealTypes }) {
  const stop = watch([plan, enabled, () => mealTypes?.()], ([value, active, types]) => {
    if (active && value) void (mealTypes?client.prepare(value,types):client.load(value))
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

export function createDishSwap({ state, send=request, context=storageContext, family=()=>getSession()?.householdId,
  day=localDate, newId=newHealthRequestId, onPlan=()=>{}, readPlan=(familyId,date)=>readDailyMealPlan(familyId,date,send,{fresh:true}), schedule=setTimeout, cancel=clearTimeout }) {
  let generation=0, plan=null, owner='', requestId='', attempted='', snapshot=null, boundKey=''
  const pending=new Map(), timers=new Map(), statuses=new Map()
  const scopeKey=value=>JSON.stringify([context(),family(),day(),value?.date,value?.version])
  const targetKey=target=>JSON.stringify([target?.mealType||'',target?.dishKey||''])
  function pause() {
    for(const timer of timers.values())cancel(timer)
    timers.clear();pending.clear();statuses.clear()
    generation++;plan=null;owner='';boundKey='';requestId='';attempted=''
    Object.assign(state,dishSwapState())
  }
  function clear(){pause();snapshot=null}
  function bind(value){
    if(value?.date!==day()||value.status!=='ready'){clear();return false}
    const key=scopeKey(value)
    if(boundKey!==key){
      pause();boundKey=key;plan=value;owner=context()
      if(snapshot?.key!==key)snapshot=null
      Object.assign(state,{entries:snapshot?.entries||[],version:value.version,date:value.date})
    }else plan=value
    return true
  }
  function refreshTarget(){
    const target=state.target
    if(!target||state.busy||attempted)return
    const entry=state.entries.find(e=>e.mealType===target.item.meal_type&&e.dishKey===dishKey(target.dish))
    const status=statuses.get(targetKey({mealType:target.item.meal_type,dishKey:dishKey(target.dish)}))||statuses.get(targetKey({mealType:target.item.meal_type}))||statuses.get(targetKey(null))
    target.candidates=entry?.candidates||[]
    target.status=status?.status==='error'?'error':status?.status==='ready'?(target.candidates.length?'ready':'empty'):'loading'
    target.error=status?.error||''
  }
  async function load(value,retryAttempt=0,refresh=false,target=null){
    if(!bind(value))return
    const key=targetKey(target)
    if(pending.has(key))return pending.get(key)
    if(timers.has(key)){cancel(timers.get(key));timers.delete(key)}
    const ticket=generation,scope=owner,familyId=family()
    const current=()=>ticket===generation&&scope===context()&&value.date===day()&&familyId===family()
    statuses.set(key,{status:'loading'});state.loading=true;refreshTarget()
    const flight=Promise.resolve().then(async()=>{try{
      if(refresh){
        const latest=await readPlan(familyId,value.date)
        if(!current())return
        if(latest.date!==value.date||latest.status!=='ready'||!Number.isInteger(latest.version)||latest.version<value.version)throw Error('餐单尚未核对完成')
        if(latest.version>value.version){await onPlan(latest);if(current()){pending.delete(key);return await load(latest,retryAttempt+1,false,target)}}
        else{pending.delete(key);return await load(latest,retryAttempt+1,false,target)}
        return
      }
      const query='?version='+value.version+(target?.mealType?'&meal_type='+encodeURIComponent(target.mealType):'')+(target?.dishKey?'&dish_key='+encodeURIComponent(target.dishKey):'')
      const {data}=await send({path:'/api/family/'+encodeURIComponent(familyId)+'/daily-meal-plans/'+value.date+'/dish-swap-candidates'+query})
      if(!current())return
      if(data.date!==value.date||data.version!==value.version||!Array.isArray(data.meals))throw Object.assign(Error('候选版本不一致，请刷新餐单。'),{code:409})
      const entries=data.meals.flatMap(m=>(m.dishes||[]).map(d=>({mealType:m.meal_type,dishKey:d.dish_key,candidates:distinctSwapCandidates(d.candidates||[])})))
      if(target?.dishKey&&!entries.some(e=>e.mealType===target.mealType&&e.dishKey===target.dishKey))throw Object.assign(Error('原菜已更新，请刷新餐单。'),{code:409})
      state.entries=[...state.entries.filter(e=>target?.dishKey?e.mealType!==target.mealType||e.dishKey!==target.dishKey:target?.mealType?e.mealType!==target.mealType:false),...entries]
      state.version=data.version;state.date=data.date;statuses.set(key,{status:'ready'})
      snapshot={key:boundKey,entries:state.entries};refreshTarget()
    }catch(error){
      if(!current())return
      if([401,403,404,410].includes(Number(error.code))){clear();return}
      if(Number(error.code)===409){
        snapshot=null;state.entries=[];state.version=null;state.date=''
        if(!refresh&&retryAttempt===0){pending.delete(key);return await load(value,retryAttempt,true,target)}
        refresh=true
      }
      statuses.set(key,{status:'error',error:error.message||'候选暂未读取成功，请重试。'});refreshTarget()
      const delays=[2000,5000,10000,30000,60000]
      timers.set(key,schedule(()=>{timers.delete(key);if(current())void load(value,retryAttempt+1,refresh,target)},delays[Math.min(retryAttempt,delays.length-1)]))
      timers.get(key)?.unref?.()
    }finally{
      if(current()&&pending.get(key)===flight){pending.delete(key);state.loading=pending.size>0}
    }})
    pending.set(key,flight)
    return flight
  }
  async function prepare(value,mealTypes){
    if(!bind(value))return
    const types=[...new Set(mealTypes??value.meals?.map(m=>m.meal_type)??[])]
    const ticket=generation
    for(const mealType of types){
      if(ticket!==generation||owner!==context())return
      const key=targetKey({mealType})
      if(statuses.get(key)?.status==='ready')continue
      await load(value,0,false,{mealType})
    }
  }
  function candidates(item,dish,value=plan){
    if(owner!==context()||!plan||snapshot?.key!==scopeKey(plan)||plan.date!==day()||value?.version!==plan.version||value.date!==plan.date)return []
    return state.entries.find(e=>e.mealType===item.meal_type&&e.dishKey===dishKey(dish))?.candidates||[]
  }
  function open(item,dish,value){
    if(state.busy||!bind(value))return
    state.target={item,dish,plan:value,candidates:[],status:'loading',error:''}
    state.open=true;state.error='';state.selected='';requestId='';attempted='';refreshTarget()
    if(state.target.status==='loading'){
      if(!pending.has(targetKey(null)))void load(value,0,false,{mealType:item.meal_type,dishKey:dishKey(dish)})
    }
  }
  function retry(){const target=state.target;if(target&&!state.busy)void load(target.plan,0,false,{mealType:target.item.meal_type,dishKey:dishKey(target.dish)})}
  function close(){if(!state.busy){state.open=false;state.target=null}}
  async function choose(candidate) {
    const target=state.target
    if(state.busy||!target||target.status!=='ready'||!target.candidates.some(c=>c.candidate_id===candidate.candidate_id)||owner!==context()||plan.date!==day())return
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
      if(current())await prepare(data,[target.item.meal_type])
    } catch(error) {
      if(!current())return
      state.error=error.code===409?'餐单或候选已更新，请关闭后刷新餐单。':(error.message||'结果尚未确认，请重试同一道候选。')
      // An unknown response keeps the same request key and candidate for a safe retry.
    } finally { if(current())state.busy=false }
  }
  return {load,prepare,pause,clear,candidates,open,close,choose,retry}
}
