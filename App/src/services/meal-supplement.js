import { request } from './request.js'
import { scopedStorage } from './storage.js'
import { sessionRevision } from './session.js'
import { newHealthRequestId } from './health-request-id.js'
import { readDietRecord } from './cloud-meals.js'

const copy = value => JSON.parse(JSON.stringify(value))
export const mealDishKey = dish => dish.item_id || dish.name
const sameName = (a,b) => String(a).trim().replace(/\s/g,'') === String(b).trim().replace(/\s/g,'')

/** 候选单独存放，重复项必须明确选择，尚未加入的内容不改变本餐。 */
export function supplementCandidates(existing, incoming) {
  return incoming.map((dish,index) => ({ dish:copy(dish),
    duplicate:[...existing,...incoming.slice(0,index)].some(old=>sameName(old.name,dish.name)),
    choice:[...existing,...incoming.slice(0,index)].some(old=>sameName(old.name,dish.name))?'':'add',
    amount:String((dish.source_basis==='per_serving'?dish.servings:dish.grams)??'') }))
}

export function appendMealCandidates(existing, candidates, newId=newHealthRequestId) {
  const additions=[]
  for(const row of candidates){
    if(row.duplicate&&!['same','extra','skip'].includes(row.choice))throw new Error('请确认重复食物是否又吃了一份')
    if(['same','skip'].includes(row.choice))continue
    const dish=copy(row.dish), amount=String(row.amount??'').trim()
    if(amount&&(!Number.isFinite(Number(amount))||Number(amount)<=0||Number(amount)>(dish.source_basis==='per_serving'?1000:10000)))throw new Error('请填写有效的本人食用份量，或留空待补充')
    const field=dish.source_basis==='per_serving'?'servings':'grams'
    if(!amount){dish[field]=null;dish.portion_confirmed=false;dish.portion_source='unknown'}
    else {if(Number(amount)!==Number(dish[field]))dish.portion_source='manual';dish[field]=Number(amount);dish.portion_confirmed=true}
    dish.item_id ||= newId()
    if([...existing,...additions].some(old=>old.item_id===dish.item_id))throw new Error('这次识别结果已经加入，请重新拍摄新增的食物')
    additions.push(dish)
  }
  if(existing.length+additions.length>30)throw new Error('一餐最多记录30项食物，请先核对已有内容')
  return [...existing,...additions]
}

/** 各照片的估计继续引用原候选；不伪造或改动主餐原图坐标。 */
export function preserveMealEvidence(meal, original) {
  const result=copy(meal), byId=new Map(original.items.map(item=>[item.item_id,item]))
  result.photos=copy(original.photos||[])
  const selected=new Map(result.items.map(item=>[item.item_id,item]))
  result.items=[...original.items.map(item=>selected.has(item.item_id)?{
    ...copy(item),...selected.get(item.item_id),locations:copy(item.locations||[]),excluded:false,
  }:{...copy(item),excluded:true}),...result.items.filter(item=>!byId.has(item.item_id)).map(item=>({...item,locations:[],excluded:false}))]
  return result
}

/** 补充已经保存的餐：固定原 ID、版本和幂等键；超时后重试原请求。 */
export function createMealSupplementSaver({send=request,storage=scopedStorage,revision=sessionRevision,newId=newHealthRequestId}={}) {
  const key='meal-supplement-pending'
  let busy=false,generation=0
  const read=()=>storage.getStorageSync(key)||null
  return {read,hide(){generation++},async save(row,meal,acceptIncomplete){
    if(busy)return null
    const epoch=generation,rev=revision(),current=()=>epoch===generation&&rev===revision()
    let pending=read()
    if(pending&&(pending.memberId!==row.memberId||pending.recordId!==row.record.id))throw new Error('请先确认上一条本餐修改的保存结果')
    if(!pending){
      const id=newId(),version=row.record.source_version
      if(!Number.isInteger(version))throw new Error('记录版本缺失，请重新读取本餐')
      pending={memberId:row.memberId,recordId:row.record.id,request:{path:`/api/health/v1/diet-logs/${row.record.id}`,method:'PATCH',
        headers:{'Idempotency-Key':id,'If-Match':`"${version}"`},
        data:{expected_version:version,client_request_id:id,meal:copy(meal),reason:'补充本餐并核对本人实际食用份量',accept_incomplete:!!acceptIncomplete}}}
      storage.setStorageSync(key,pending)
    }
    busy=true
    try{
      await send(copy(pending.request))
      if(!current())return null
      const record=await readDietRecord(row.memberId,row.record.id,send)
      if(!current())return null
      if(record.id!==row.record.id||record.source_version<=pending.request.data.expected_version)throw new Error('本餐修改结果尚未确认，请恢复原保存请求')
      storage.setStorageSync(key,null)
      return {...row,recordId:record.id,record,phase:'saved'}
    }catch(error){
      if(current()&&[400,403,404,409,410,422].includes(Number(error.code)))storage.setStorageSync(key,null)
      throw error
    }finally{busy=false}
  }}
}
