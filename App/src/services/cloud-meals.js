import { request } from './request.js'
import { sessionRevision } from './session.js'
import { scopedStorage } from './storage.js'
import { newHealthRequestId } from './health-request-id.js'
const root='/api/health/v1',copy=v=>JSON.parse(JSON.stringify(v))
const uncertain=e=>e.code==='NETWORK_ERROR'||Number(e.code)>=500
export const mealLabels={breakfast:'早餐',lunch:'午餐',dinner:'晚餐',snack:'加餐'}
export function mealDay(time){const n=Date.parse(time);return Number.isFinite(n)?new Date(n+8*3600000).toISOString().slice(0,10):''}
export function feedbackUrl(memberId,record){return `/pages/chat/index?taskType=diet_analysis&memberId=${encodeURIComponent(memberId)}&recordId=${encodeURIComponent(record.id)}&version=${record.source_version}`}
export async function readDietRecord(memberId,id,send=request){
  // The deployed list contract already returns authorized, complete snapshots.
  let offset=0
  for(let page=0;page<100;page++){
    const {data}=await send({path:`${root}/members/${memberId}/diet-logs/page?limit=50&offset=${offset}`})
    if(!Array.isArray(data.records))throw new Error('饮食记录返回不完整')
    const found=data.records.find(r=>r.id===id)
    if(found)return {...found,member_id:memberId}
    if(data.next_offset==null)throw Object.assign(new Error('记录不存在或已不可读取'),{code:404})
    if(data.next_offset<=offset)throw new Error('记录分页未推进，请重新读取')
    offset=data.next_offset
  }
  throw new Error('记录较多，请从日期列表重新选择')
}
export function portionNote(item){return (item.uncertainties||[]).find(s=>s.startsWith('本人粗略份量：'))?.slice(7)||'不确定'}
export function personalMeal(dishes,person,{mealType,eatenAt,captureScope,oil='不确定'},newId=newHealthRequestId){
  if(!mealLabels[mealType]||!Number.isFinite(Date.parse(eatenAt)))throw new Error('请选择有效的餐次和日期')
  const items=dishes.filter(d=>person.dishes.includes(d.name)).map(d=>({item_id:newId(),name:d.name,
    ...(d.recipe_version_id?{recipe_version_id:d.recipe_version_id}:{}),...(d.food_id?{food_id:d.food_id}:{}),
    // A person's combined weight cannot be silently assigned to each dish.
    grams:person.dishes.length===1&&Number(person.grams)>0?Number(person.grams):null,
    share_ratio:person.dishes.length===1&&Number(person.grams)>0?1:null,portion_source:person.dishes.length===1&&Number(person.grams)>0?'manual':'unknown',
    uncertainties:[`本人粗略份量：${person.portion||'不确定'}`,`记录方式：${captureScope}`,`烹饪用油：${oil}`,
      ...(person.dishes.length>1&&Number(person.grams)>0?[`本人所选菜品合计重量：${Number(person.grams)}g；各菜重量未知`]:[])]}))
  if(!items.length)throw new Error('请确认本人实际吃过的菜；未吃的成员不创建摄入记录')
  return {meal_type:mealType,eaten_at:eatenAt,items,photos:[]}
}

/** Freeze every member's draft and confirmation before transport; never repeat an unknown draft creation. */
export function createCloudMealSaver({send=request,storage=scopedStorage,revision=sessionRevision,newId=newHealthRequestId,key='meal-capture-pending'}={}){
  let busy=false,generation=0
  const read=()=>storage.getStorageSync(key)||null
  function hide(){generation++}
  async function save(meals,acceptIncomplete){
    if(busy)return null
    const rev=revision(),mine=generation,valid=()=>rev===revision()&&mine===generation
    const current=()=>{if(!valid())throw Object.assign(new Error('页面或账号已变化，请重新读取保存结果'),{code:'SESSION_CHANGED'})}
    let group=read()
    if(group?.editable){group={...group,editable:false,rows:[...group.rows.filter(r=>r.phase==='saved'),...meals.filter(m=>!group.rows.some(r=>r.phase==='saved'&&r.memberId===m.memberId)).map(m=>({...copy(m),phase:m.draftId?'patching':'new',clientId:newId(),acceptIncomplete:acceptIncomplete===true}))]};storage.setStorageSync(key,group)}
    if(!group){if(!meals.length)throw new Error('请选择实际吃过的成员');group={groupId:newId(),rows:meals.map(m=>({...copy(m),phase:m.draftId?'patching':'new',clientId:newId(),acceptIncomplete:acceptIncomplete===true}))};storage.setStorageSync(key,group)}
    const checkpoint=()=>{current();storage.setStorageSync(key,copy(group))}
    busy=true
    try{
      for(const row of group.rows){
        current();if(row.phase==='saved')continue
        if(row.phase==='rejected')throw new Error('请先重新核对未保存成员，再提交修正后的内容')
        try{
        if(row.phase==='patching'){
          const {data:draft}=await send({path:`${root}/meal-drafts/${row.draftId}`});current()
          if(draft.member_id!==row.memberId||draft.review_status!=='pending_confirmation')throw Object.assign(new Error('照片候选已变化，请重新核对原餐次'),{code:409})
          const stable=value=>JSON.stringify({...value,photos:value.photos||[],items:value.items.map(item=>({candidates:[],cooking_method:'未知',visible_ingredients:[],locations:[],uncertainties:[],food_id:null,recipe_version_id:null,grams:null,portion_reference_id:null,portion_count:null,share_ratio:null,portion_source:'unknown',adjustments:[],excluded:false,...item}))},(key,item)=>['grams','share_ratio','portion_count'].includes(key)&&item!==null?Number(item):item&&typeof item==='object'&&!Array.isArray(item)?Object.fromEntries(Object.entries(item).sort(([a],[b])=>a.localeCompare(b))):item)
          if(stable(draft.payload)===stable(row.meal)){row.version=draft.version;row.phase='draft';checkpoint()}
          else{
            if(draft.version!==row.draftVersion)throw Object.assign(new Error('照片候选已被修改，请重新读取后核对份量'),{code:409})
            const {data}=await send({path:`${root}/meal-drafts/${row.draftId}`,method:'PATCH',headers:{'If-Match':`"${row.draftVersion}"`},data:{version:row.draftVersion,reason:'核对照片中本人实际吃过的菜和粗略份量',meal:row.meal}});current()
            if(data.member_id!==row.memberId||!Number.isInteger(data.version))throw new Error('照片候选保存回执待确认')
            row.version=data.version;row.phase='draft';checkpoint()
          }
        }
        if(row.phase==='creating'){
          let offset=0,found=null
          for(let page=0;page<100;page++){
            const {data}=await send({path:`${root}/members/${row.memberId}/vision/page?kind=meal&jobs_limit=1&drafts_limit=50&drafts_offset=${offset}`});current()
            found=data.drafts?.find(d=>d.kind==='meal'&&d.payload?.items?.length===row.meal.items.length&&d.payload.items.every(i=>row.meal.items.some(item=>item.item_id===i.item_id)))
            if(found||data.drafts_next_offset==null)break
            if(data.drafts_next_offset<=offset)throw new Error('草稿分页异常，请重新读取')
            offset=data.drafts_next_offset
          }
          if(!found)throw new Error('上次创建草稿的结果尚未确认，已保留原餐次。请稍后重新读取，暂勿重新记同一餐。')
          row.draftId=found.id;row.version=found.version;row.phase='draft';checkpoint()
        }
        if(row.phase==='new'){
          row.phase='creating';checkpoint()
          let data
          try{({data}=await send({path:root+'/manual-drafts',method:'POST',data:{member_id:row.memberId,kind:'meal',meal:row.meal}}))}
          catch(e){current();if(!uncertain(e)){row.phase='new';checkpoint()}throw e}
          current();if(!data?.id||data.member_id!==row.memberId)throw new Error('草稿回执待核对，请重新读取')
          row.draftId=data.id;row.version=data.version;row.phase='draft';checkpoint()
        }
        if(row.phase==='draft'){
          const {data}=await send({path:`${root}/meal-drafts/${row.draftId}/calculate`,method:'POST',data:{version:row.version}});current()
          if(data.draft_version!==row.version||!data.calculation_id)throw new Error('本次计算与草稿版本不一致')
          row.confirm={version:row.version,client_request_id:row.clientId,calculation_id:data.calculation_id,accept_incomplete:row.acceptIncomplete};row.phase='confirming';checkpoint()
        }
        if(row.phase==='confirming'){
          const {data}=await send({path:`${root}/meal-drafts/${row.draftId}/confirm`,method:'POST',headers:{'Idempotency-Key':row.clientId},data:row.confirm});current()
          if(data.review_status!=='confirmed'||data.target_ids?.length!==1)throw new Error('保存回执尚未确认，请重试原请求')
          row.recordId=data.target_ids[0];row.phase='reading';checkpoint()
        }
        if(row.phase==='reading'){
          row.record=await readDietRecord(row.memberId,row.recordId,send);current();row.phase='saved';checkpoint()
        }
        }catch(e){current();if([400,409,413,422].includes(Number(e.code))&&['new','creating','patching','draft','confirming'].includes(row.phase)){row.phase='rejected';row.rejection=e.message;checkpoint()}throw e}
      }
      return copy(group)
    }finally{busy=false}
  }
  function releaseRejected(){const group=read();if(busy||!group?.rows.some(r=>r.phase==='rejected')||!group.rows.every(r=>['saved','rejected','new','patching'].includes(r.phase)))return null;group.editable=true;storage.setStorageSync(key,copy(group));return copy(group)}
  return {read,save,hide,releaseRejected,finish(){const group=read();if(group?.rows.every(r=>r.phase==='saved'))storage.setStorageSync(key,null)}}
}
