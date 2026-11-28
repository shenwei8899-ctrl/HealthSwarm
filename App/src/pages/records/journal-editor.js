import {createJournalDraft,journalDraftMeal,journalMealLabels} from '../../services/diet-journal-presentation.js'
import {sortMealRecords} from '../../services/meal-record-entry.js'
import {storageContext} from '../../services/storage.js'

export function journalEditorState(){return {open:false,memberId:'',day:'',mealType:'breakfast',records:[],record:null,draft:null}}
export function createJournalEditor({state,page,client,context=storageContext,onDenied=()=>{}}){
 const drafts=new Map();let generation=0,scope=''
 const slot=()=>`${state.memberId}:${state.day}:${state.mealType}`
 const key=id=>slot()+':'+(id||'new')
 const locked=()=>page.busy||page.saving||!!page.pending
 function clear(){generation++;drafts.clear();Object.assign(state,journalEditorState());client.hide()}
 function remember(){if(state.record&&state.draft)drafts.set(key(state.record.id),{record:state.record,draft:state.draft})}
 async function select({memberId=state.memberId,day=state.day,mealType=state.mealType,id}={}){
  if(locked())return
  remember();const mine=++generation
  Object.assign(state,{memberId,day,mealType,record:null,draft:null,records:[]})
  await client.load(memberId,day)
  if(scope!==context()){clear();onDenied('登录状态已变化，请重新读取。');return}
  if(mine!==generation||!state.open)return
  if(page.error||page.memberId!==memberId){if(page.denied){const error=page.error;clear();onDenied(error)}return}
  state.records=sortMealRecords(page.records).filter(r=>r.snapshot.meal.meal_type===mealType)
  const creation=client.resumeCreation(memberId,day,mealType)
  if(creation)page.pending=null
  await record(creation?'new':id||state.records[0]?.id,mine)
 }
 async function record(id,mine=++generation){
  if(locked())return
  remember()
  state.record=null;state.draft=null
  const summary=state.records.find(r=>r.id===id)
  let value
  if(summary){value=await client.detail(summary)}
  else {
   const pending=client.resumeCreation(state.memberId,state.day,state.mealType)
   value={id:'',member_id:state.memberId,source_version:0,snapshot:{meal:pending?.data?.meal||{meal_type:state.mealType,eaten_at:state.day+'T12:00:00+08:00',photos:[],items:[]}}}
  }
  if(scope!==context()){clear();onDenied('登录状态已变化，请重新读取。');return}
  if(page.denied&&page.error){const error=page.error;clear();onDenied(error);return}
  if(mine!==generation||!state.open||!value)return
  const cached=drafts.get(key(value.id))
  state.record=cached?.record||value
  state.draft=cached?.draft||createJournalDraft(value)
  if(value.id)page.detail=state.record
 }
 async function open({memberId,day,mealType='breakfast',id}={}){
  if(page.saving)return
  clear();scope=context();state.open=true
  await select({memberId,day,mealType:journalMealLabels[mealType]?mealType:'breakfast',id})
 }
 async function save(){
  if(page.busy||page.saving||!state.record||!state.draft)return null
  if(scope!==context()){clear();onDenied('登录状态已变化，请重新读取。');return null}
  try{
   const meal=page.pending?.path?.endsWith('/withdraw')?undefined:page.pending?.data?.meal||journalDraftMeal(state.record,state.draft)
   const id=state.record.id
   const result=id?await client.mutate('correct',meal):await client.create(state.memberId,meal)
   if(scope!==context()){clear();onDenied('登录状态已变化，请重新读取。');return null}
   if(!result){if(page.denied&&page.error){const error=page.error;clear();onDenied(error)}return null}
   drafts.delete(key(id));state.record=null;state.draft=null
   await select({id:result.id||id});return result
  }catch(error){page.error=error.message;return null}
 }
 async function withdraw(){
  if(locked()||!state.record?.id)return null
  if(scope!==context()){clear();onDenied('登录状态已变化，请重新读取。');return null}
  const id=state.record.id,result=await client.mutate('withdraw')
  if(scope!==context()){clear();onDenied('登录状态已变化，请重新读取。');return null}
  if(!result&&page.denied&&page.error){const error=page.error;clear();onDenied(error);return null}
  if(result){drafts.delete(key(id));state.record=null;state.draft=null;await select()}
  return result
 }
 async function reload(){if(locked())return;drafts.delete(key(state.record?.id));const id=state.record?.id;state.record=null;state.draft=null;await select({id})}
 return {open,select,record,save,withdraw,reload,clear}
}
