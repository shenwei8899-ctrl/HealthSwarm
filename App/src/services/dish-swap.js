import { request } from './request.js'
import { storageContext } from './storage.js'
import { getSession } from './session.js'
import { newHealthRequestId } from './health-task-flow.js'
import { dishKey } from '../utils/meal-presentation.js'
import { localDate } from '../utils/meal-state.js'
import { watch } from 'vue'

// Visibility is an input: returning to the same plan version must reload candidates.
export function watchDishSwap({ client, plan, enabled }) {
  return watch([plan, enabled], ([value, active]) => {
    if (active && value) void client.load(value)
    else client.clear()
  }, { immediate:true })
}

export const dishSwapState = () => ({ loading:false, busy:false, open:false, error:'', entries:[], version:null, date:'', target:null, selected:'' })

export function createDishSwap({ state, send=request, context=storageContext, family=()=>getSession().householdId,
  day=localDate, newId=newHealthRequestId, onPlan=()=>{} }) {
  let generation=0, plan=null, owner='', requestId='', attempted=''
  function clear() { generation++;plan=null;owner='';requestId='';attempted='';Object.assign(state,dishSwapState()) }
  async function load(value) {
    clear()
    if(value?.date!==day()||value.status!=='ready')return
    plan=value;owner=context()
    const ticket=generation, familyId=family()
    const current=()=>ticket===generation&&owner===context()&&value.date===day()&&familyId===family()
    state.loading=true
    try {
      const {data}=await send({path:'/api/family/'+encodeURIComponent(familyId)+'/daily-meal-plans/'+value.date+'/dish-swap-candidates?version='+value.version})
      if(!current())return
      if(data.date!==value.date||data.version!==value.version||!Array.isArray(data.meals))throw Error('候选版本不一致，请刷新餐单。')
      state.entries=data.meals.flatMap(m=>(m.dishes||[]).map(d=>({mealType:m.meal_type,dishKey:d.dish_key,candidates:(d.candidates||[]).slice(0,3)})))
      state.version=data.version;state.date=data.date
    } catch(error) { if(current())state.error=error.message||'换菜候选暂时无法读取，请刷新。' }
    finally { if(current())state.loading=false }
  }
  function candidates(item,dish,value=plan) {
    if(owner!==context()||!plan||plan.date!==day()||value?.version!==plan.version||value.date!==plan.date)return []
    return state.entries.find(e=>e.mealType===item.meal_type&&e.dishKey===dishKey(dish))?.candidates||[]
  }
  function open(item,dish,value) {
    if(state.busy||!candidates(item,dish,value).length)return
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
  return {load,clear,candidates,open,close,choose}
}
