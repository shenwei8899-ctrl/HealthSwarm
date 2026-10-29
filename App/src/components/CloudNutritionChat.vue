<script setup>
import { computed, reactive, ref, nextTick, onMounted, onUnmounted } from 'vue'
import { onShow, onHide } from '@dcloudio/uni-app'
import NutritionistLayout from './NutritionistLayout.vue'
import ChatConversationDrawer from './ChatConversationDrawer.vue'
import ChatWelcome from './ChatWelcome.vue'
import { chatPresentation } from '../services/chat-presentation.js'
import AppIcon from './AppIcon.vue'
import DinerPicker from './DinerPicker.vue'
import HealthChatBusinessCard from './HealthChatBusinessCard.vue'
import DailyArrangementCard from './DailyArrangementCard.vue'
import DailyMealPlanCard from './DailyMealPlanCard.vue'
import {readDailyMealPlan,mealQuestionAction} from '../services/daily-meal-plan.js'
import {referenceSelection as chooseReference,isReferencePlan} from '../services/reference-meal-plan.js'
import ConversationFoodPackages from './ConversationFoodPackages.vue'
import VoiceInput from './VoiceInput.vue'
import AiAnswer from './AiAnswer.vue'
import ChatReplyActions from './ChatReplyActions.vue'
import { readCurrentPreparation } from '../services/onboarding-preparation.js'
import { loadCloudProfile } from '../services/cloud-profile.js'
import { rememberChatEntry } from '../services/app-entry.js'
import { createDailyArrangementClient, dailyArrangementState } from '../services/daily-arrangement-client.js'
import { request } from '../services/request.js'
import { commerce } from '../services/commerce.js'
import { storageContext, scopedStorage } from '../services/storage.js'
import { getSession } from '../services/session.js'
import { createHealthTaskFlow, HEALTH_TEXT_TASKS, newHealthRequestId } from '../services/health-task-flow.js'
import { persistChatImage, previewChatImage } from '../services/chat-images.js'
import { readChatSnapshot, chatImageContent, chatTimestamp, chatBusinessDate } from '../services/cloud-chat.js'
import { localDate } from '../utils/meal-state.js'
import { selectChatPrompts } from '../services/chat-prompts.js'
import { parseChatMealIntent, isMealPlanningCancelled } from '../utils/chat-meal-intent.js'
import { loadChatMealPlan } from '../services/chat-meal-plan.js'

const props=defineProps({route:{type:Object,default:()=>({})}})
const state=reactive(dailyArrangementState()),profile=ref(null),cardVisible=ref(false),selectedMeal=ref(null)
const profileLoading=ref(false),entryReady=ref(false)
const returning=ref(false),returnError=ref(''),returnVerified=ref(true)
const entryError=ref(''),entryStatus=ref('正在读取咨询资料…')
const needsProfileLink=computed(()=>profile.value&&!props.route.memberId&&!profile.value.members.some(m=>m.relation==='本人'&&m.healthMemberId))
const question=ref(''),chatError=ref(''),messages=ref([]),task=ref({}),consentChecked=ref(false)
const voiceMode=ref(false),voiceBusy=ref(false),voiceRef=ref(null),communityOpen=ref(false),scrollTarget=ref(''),inlineTodayOpen=ref(false)
const draftImage=ref(null),draftSaving=ref(false),draftError=ref('')
const keyboardFocused=ref(false)
const familyState=reactive(dailyArrangementState()),familyPanel=ref(false),familySelection=ref(null),familyIntent=ref('')
const mealPlanReady=ref(false),mealPlanAudience=ref('default')
const liveAnswer=computed(()=>!!task.value.streamText&&!task.value.result)
const progressText=computed(()=>profileLoading.value?'正在读取你的资料':familyState.busy?(familyState.phase==='generating'?'正在生成三餐，并核对成员、营养与食材':'正在核对已保存的餐单'):task.value.streamStatus||(['queued','pending'].includes(task.value.status)?'问题已收到，正在等待营养师处理':'正在读取资料并整理回复'))
let scrollTimer=null
const prompts=ref([]),promptDate=ref('')
function refreshPrompts(){
  const previousIds=prompts.value.length?prompts.value.map(p=>p.id):scopedStorage.getStorageSync('homepage-prompt-ids')||[]
  prompts.value=selectChatPrompts({previousIds})
  promptDate.value=localDate()
  scopedStorage.setStorageSync('homepage-prompt-ids',prompts.value.map(p=>p.id))
}
function shufflePrompts(){
  if(chatBusy.value||voiceBusy.value)return
  refreshPrompts()
}
const newConversationWelcome=ref(false),preparedThreadId=ref(''),latestReference=ref(null)
const dailyPlans=ref({}),todayPlan=computed(()=>dailyPlans.value[localDate()]||null)
const activePlanStatus=status=>['queued','dispatched','pending','running','cancel_requested'].includes(status)
const planRunning=computed(()=>activePlanStatus(todayPlan.value?.pending?.status)||task.value.taskType==='reference_meal_preview'&&referenceSelection?.plan_date===localDate()&&activePlanStatus(task.value.status))
const historyOpen=ref(false),conversationId=ref(''),conversationThreadId=ref(''),conversationBusinessDate=ref(''),switchingConversation=ref(false)
const conversationReadOnly=computed(()=>!!task.value.readOnly||!!conversationBusinessDate.value&&conversationBusinessDate.value<localDate())
const conversationDrafts=new Map()
const historyMemberId=computed(()=>profile.value?.members.find(m=>m.id===profile.value.selfMemberId)?.healthMemberId||'')
const mealReplyActions=computed(()=>{
  const last=messages.value.at(-1),user=messages.value.filter(m=>m.role==='user').at(-1)
  return !props.route.taskType&&last?.role==='assistant'&&!last.error&&!last.business&&!!user?.text&&!!parseChatMealIntent(user.text,localDate())
})
const mealsLoading=ref(false),mealReadError=ref('')
const planPurchaseBusy=ref(false)
let referenceSelection=null,mealReadGeneration=0,planReads={},planTimers={},planPolls={},refreshedTerminal=''
const failedTask=computed(()=>!props.route.taskType&&['failed','rejected','interrupted'].includes(task.value.status))
const failedQuestion=computed(()=>failedTask.value?messages.value.find(m=>m.role==='user'&&m.requestId===task.value.requestId):null)
const visibleMessages=computed(()=>messages.value.filter(m=>!failedTask.value||m.requestId!==task.value.requestId))
const presentation=computed(()=>chatPresentation({route:props.route,hasMessages:visibleMessages.value.length>0,
  hasSavedArrangement:state.phase==='ready',newConversation:newConversationWelcome.value,
  preparedThreadId:preparedThreadId.value,currentThreadId:task.value.entry?.thread_id,
  loading:false}))
const failureText={budget_price_unavailable:'营养咨询服务的计费配置尚未就绪，请联系管理员。原问题已保留。',budget_exceeded:'本月健康 AI 可用额度不足或待核账，请稍后再试。原问题已保留。',execution_cancelled:'本次处理已取消。',execution_interrupted:'本次处理已中断，可稍后重新发送。'}
const chatBusy=computed(()=>switchingConversation.value||!entryReady.value||!returnVerified.value||profileLoading.value||sending.value||familyState.busy||task.value.busy||task.value.loading||task.value.submitUnknown||['queued','dispatched','pending','running','cancel_requested'].includes(task.value.status))
const inputBusy=computed(()=>!entryReady.value||sending.value||familyState.busy||task.value.busy||(!returning.value&&task.value.loading)||['queued','dispatched','pending','running','cancel_requested'].includes(task.value.status))
const sending=ref(false),hasDraftContent=computed(()=>!!question.value.trim()||!!draftImage.value)
const retryBusy=computed(()=>sending.value||switchingConversation.value||!entryReady.value||task.value.busy||task.value.loading||task.value.refreshing)
const canCancel=computed(()=>task.value.requestId&&!task.value.submitUnknown&&['queued','dispatched','pending','running'].includes(task.value.status))
let disposed=false,visible=true,loading=null,epoch=0,pageScope=storageContext(),flowScope=pageScope,draftVersion=0,sendGeneration=0,openingCamera=false,pendingUser=null,submittedDraft=null,desiredType='consultation',restoring=false,suspended=false,loadedDate='',startNewHandled=false
const flow=createHealthTaskFlow({daily:true,onChange:next=>{
  if(disposed||flowScope!==storageContext())return
  task.value=next
  if(!restoring&&profile.value&&next.taskType==='reference_meal_preview'&&next.requestId&&referenceSelection?.plan_date&&['completed','failed','cancelled','interrupted','rejected'].includes(next.status)){
    const key=next.requestId+':'+next.status
    if(key!==refreshedTerminal){
      refreshedTerminal=key;const mine=epoch,scope=storageContext()
      void loadDailyPlan(profile.value.householdId,referenceSelection.plan_date,mine,scope).catch(e=>{if(!disposed&&visible&&mine===epoch&&scope===storageContext())mealReadError.value=e.message})
    }
  }
  rememberSpecialTask(next)
  if(next.streamText||next.streamStatus)queueScroll()
  if(next.invalidated){messages.value=[];question.value='';removeDraft();submittedDraft=null;pendingUser=null;return}
  if(pendingUser&&next.requestId){pendingUser.requestId=next.requestId;pendingUser.status=next.status||'sending'}
  if(submittedDraft&&!submittedDraft.requestId&&pendingUser&&next.requestId)submittedDraft.requestId=next.requestId
  if(next.submitUnknown&&next.requestId&&!messages.value.some(m=>m.role==='user'&&m.requestId===next.requestId)){
    messages.value.push({id:'pending-'+next.requestId,role:'user',requestId:next.requestId,text:next.pendingText||'',status:'unknown',...(next.pendingImages?.[0]?{image:{localPath:next.pendingImages[0]}}:{})})
  }
  const outgoing=messages.value.find(m=>m.role==='user'&&m.requestId===next.requestId)
  if(outgoing){
    outgoing.status=next.submitUnknown?'unknown':['cancelled','failed','rejected'].includes(next.status)?next.status:'sent'
    if(!next.submitUnknown&&next.status!=='提交中'&&!['failed','rejected'].includes(next.status)&&submittedDraft?.requestId===next.requestId){
      if(question.value.trim()===submittedDraft.text)question.value=''
      if(draftImage.value?.localPath===submittedDraft.path)removeDraft()
      submittedDraft=null
    }
  }
  if(next.result&&next.requestId&&!(next.result.type==='error'&&!props.route.taskType)){
    const id=next.requestId+'-answer',index=messages.value.findIndex(m=>m.requestId===next.requestId&&m.role==='assistant')
    const result=next.result
    if(result.type==='business'&&isReferencePlan(result.data)){
      latestReference.value=result.data
    }
    const message={id,serverMessageId:next.finalMessageId,requestId:next.requestId,role:'assistant',createdAt:new Date().toISOString(),citations:result.citations||[],
      text:result.type==='answer'?result.text:result.type==='needs_input'?result.questions.join('\n'):result.type==='error'?(failureText[result.code]||'这次处理未能完成，请重新读取或编辑问题后再试。'):isReferencePlan(result.data)?'饮食计划已更新。':'餐单结果已返回，请核对后决定是否使用。',
      memberId:next.memberId,purchaseOffers:result.purchaseOffers,purchaseRequestId:result.purchaseOffers?.length?next.requestId:'',error:result.type==='error',errorCode:result.code,retryable:result.retryable===true,business:result.type==='business'?result:null,planDate:isReferencePlan(result.data)?result.data.plan_date:''}
    if(index<0)messages.value.push(message);else messages.value[index]={...messages.value[index],...message}
    if(!restoring&&!returning.value&&visible)void scrollLatest()
  }
}})
const client=createDailyArrangementClient({state,send:request,context:()=>({scope:storageContext(),familyId:getSession()?.householdId}),storage:scopedStorage,newId:newHealthRequestId,beforeStart:requirePlanningReady})
const familyClient=createDailyArrangementClient({state:familyState,send:request,context:()=>({scope:storageContext(),familyId:getSession()?.householdId}),storage:scopedStorage,newId:newHealthRequestId,beforeStart:requirePlanningReady})
function requirePlanningReady(){
  const capability=profile.value?.healthConfiguration?.meal_plan
  if(capability?.available===false)throw Object.assign(new Error('营养服务暂未就绪：'+(capability.reason||'请先完成服务配置')+'。配置完成后重新读取即可。'),{businessCode:'daily_dependencies_not_ready',retryable:false})
  const diners=profile.value?.defaultDiners
  if(diners?.some(id=>profile.value.members.some(member=>member.id===id && !member.healthMemberId && member.claimed===true && member.relation!=='本人')))throw Object.assign(new Error('有已认领的家人尚未完成健康资料关联，请让该成员登录后确认自己的资料和分析授权，或在家庭档案中调整默认就餐成员。'),{businessCode:'daily_member_consent_required',retryable:false})
  if(diners?.length && diners.some(id=>!profile.value.members.find(member=>member.id===id)?.healthMemberId))throw Object.assign(new Error('请在家庭档案中选择尚未确认的就餐成员，核对资料并明确同意对应分析。'),{businessCode:'daily_member_sources_unavailable',retryable:false})
}
async function familyPlan(text,retry=false){
  text=retry?familyIntent.value:String(text||'');if(!retry)familyIntent.value=text
  const scope=storageContext(),mine=epoch
  const intent=parseChatMealIntent(text,localDate())
  if(!intent)return
  familyPanel.value=true;mealPlanReady.value=false;mealPlanAudience.value=intent.audience
  const isCurrent=()=>!disposed&&visible&&mine===epoch&&scope===storageContext()
  const arrangement=await loadChatMealPlan(intent,{client:familyClient,state:familyState,profile:profile.value,isCurrent,retry})
  if(!isCurrent())return
  mealPlanReady.value=!!arrangement
  if(!arrangement){chatError.value=familyState.error||'餐单仍在处理中，请继续读取本次安排。';return}
  if(question.value.trim()===text)question.value=''
  if(state.date===intent.date){await client.load(intent.date);if(!isCurrent())return;cardVisible.value=state.phase==='ready'}
  await nextTick();scrollTarget.value='chat-meal-plan'
}
async function familyMembers(ids){
  const choice=familySelection.value;familySelection.value=null;if(!choice)return
  const scope=storageContext(),mine=epoch;await familyClient.changeMembers(choice.type,ids)
  if(disposed||!visible||mine!==epoch||scope!==storageContext())return
  if(!familyState.error&&familyState.date===state.date){await client.load(state.date);if(disposed||!visible||mine!==epoch||scope!==storageContext())return}
  if(!familyState.error&&question.value.trim()===choice.question)question.value=''
}
function openFamilyMeal(meal){uni.navigateTo({url:'/pages/shop/index?meal='+meal.type+'&date='+familyState.date+'&arrangement='+encodeURIComponent(familyState.arrangement.id)+'&version='+familyState.arrangement.version})}
async function scrollLatest(){await nextTick();scrollTarget.value='';await nextTick();if(messages.value.length)scrollTarget.value='message-'+messages.value.at(-1).id}
function queueScroll(){if(scrollTimer!==null)return;scrollTimer=setTimeout(async()=>{scrollTimer=null;if(disposed||!visible)return;await nextTick();scrollTarget.value='';await nextTick();scrollTarget.value=liveAnswer.value?'stream-answer':'reply-progress'},180)}
function stopPlanTimers(){Object.values(planTimers).forEach(timer=>clearTimeout(timer));planTimers={};planPolls={}}
function clearPrivate(){historyOpen.value=false;conversationId.value='';conversationThreadId.value='';conversationBusinessDate.value='';conversationDrafts.clear();entryReady.value=false;returnVerified.value=false;returning.value=false;returnError.value='';prompts.value=[];promptDate.value='';mealsLoading.value=false;mealReadError.value='';latestReference.value=null;dailyPlans.value={};stopPlanTimers();referenceSelection=null;refreshedTerminal='';newConversationWelcome.value=false;preparedThreadId.value='';epoch++;sendGeneration++;sending.value=false;loading=null;profileLoading.value=false;flow.hide();client.reset();familyClient.reset();familyPanel.value=false;familySelection.value=null;messages.value=[];question.value='';chatError.value='';profile.value=null;task.value={};selectedMeal.value=null;removeDraft();pendingUser=null;submittedDraft=null;voiceRef.value?.cancel();voiceBusy.value=false;voiceMode.value=false;cardVisible.value=false}
function rememberThread({migrateLegacy=false}={}){
  if(flowScope!==storageContext()||props.route.taskType||!task.value.entry?.thread_id||!task.value.memberId)return
  const key=`homepage-chat-threads:${task.value.memberId}:${localDate()}`,old=scopedStorage.getStorageSync(key)||[]
  const row={thread_id:task.value.entry.thread_id,task_type:task.value.taskType}
  scopedStorage.setStorageSync(key,[...old.filter(t=>t.thread_id!==row.thread_id),row].slice(-20))
  if(task.value.taskType==='consultation'){
    if(!conversationId.value)conversationId.value=row.thread_id
    conversationThreadId.value=row.thread_id
    conversationBusinessDate.value=task.value.entry.business_date||''
  }
  if(!conversationId.value)return
  const groupKey='conversation-threads:'+conversationId.value
  const grouped=scopedStorage.getStorageSync(groupKey)||[]
  const initial=grouped.length?grouped:migrateLegacy?old.filter(t=>t.task_type!=='consultation'||t.thread_id===row.thread_id):[]
  scopedStorage.setStorageSync(groupKey,[...initial.filter(t=>t.thread_id!==row.thread_id),{...row,memberId:task.value.memberId}].slice(-50))
  saveConversation()
  const title=messages.value.find(m=>m.role==='user'&&(m.text||m.image))
  if(title&&conversationThreadId.value)scopedStorage.setStorageSync(`conversation-summary:${historyMemberId.value}:${conversationThreadId.value}`,{title:(title.text||'[图片]').replace(/\s+/g,' ').trim().slice(0,36),updatedAt:new Date().toISOString()})
}
function saveConversation(){
  const memberId=profile.value?.members.find(m=>m.id===profile.value.selfMemberId)?.healthMemberId
  if(!memberId)return
  if(!conversationId.value||props.route.taskType)return
  const value={id:conversationId.value,threadId:conversationThreadId.value,memberId,businessDate:conversationBusinessDate.value,scope:storageContext()}
  scopedStorage.setStorageSync('homepage-conversation',value)
  if(value.threadId)scopedStorage.setStorageSync('conversation-index:'+value.threadId,value)
}
function rememberSpecialTask(next){
  if(props.route.taskType||!conversationId.value||next.taskType!=='reference_meal_preview')return
  const key='conversation-task:'+conversationId.value
  if(next.invalidated||['cancelled','rejected'].includes(next.status)||next.status==='completed'&&next.result&&next.result.type!=='needs_input'){
    scopedStorage.setStorageSync(key,null);return
  }
  if(!referenceSelection||!next.entry?.thread_id||!next.requestId)return
  scopedStorage.setStorageSync(key,{conversationId:conversationId.value,type:next.taskType,memberId:next.memberId,
    selection:referenceSelection,threadId:next.entry.thread_id,requestId:next.requestId,scope:storageContext()})
}
async function restoreSpecialTask(legacy){
  if(props.route.taskType||!conversationId.value||conversationReadOnly.value||task.value.invalidated||task.value.submitUnknown||
    ['queued','dispatched','pending','running','cancel_requested'].includes(task.value.status))return
  const scope=storageContext(),mine=epoch,id=conversationId.value,key='conversation-task:'+id
  const saved=scopedStorage.getStorageSync(key)||legacy
  if(saved?.type!=='reference_meal_preview'||saved.conversationId!==id||saved.scope&&saved.scope!==scope||
    saved.selection?.family_id!==profile.value?.householdId)return
  const pointers=(scopedStorage.getStorageSync('conversation-threads:'+id)||[]).filter(row=>row.task_type===saved.type&&
    (!row.memberId||row.memberId===(saved.taskMemberId||saved.memberId))&&(!saved.threadId||row.thread_id===saved.threadId))
  if(!pointers.length)return
  try{
    const selection=chooseReference(profile.value,'',{today:localDate(),tomorrow:localDate(new Date(Date.now()+86400000)),previous:saved.selection})
    if(saved.selection.daily_base_version!==undefined)selection.daily_base_version=saved.selection.daily_base_version
    if(JSON.stringify(selection)!==JSON.stringify(saved.selection))return
    referenceSelection=selection
  }catch{return}
  await restoreChat(saved.type)
  if(disposed||!visible||scope!==storageContext()||mine!==epoch||id!==conversationId.value||task.value.invalidated)return
  if(task.value.memberId===(saved.taskMemberId||saved.memberId)&&pointers.some(row=>row.thread_id===task.value.entry?.thread_id)&&
    (!saved.requestId||task.value.requestId===saved.requestId)&&
    (task.value.result?.type==='needs_input'||task.value.submitUnknown||['queued','dispatched','pending','running','cancel_requested'].includes(task.value.status))){
    desiredType=saved.type;return
  }
  scopedStorage.setStorageSync(key,null);referenceSelection=null
  await restoreChat('consultation')
}
function visibleConversationMessage(message,explicit){
  if(!message.createdAt)return true
  if(explicit&&!conversationBusinessDate.value||props.route.taskType)return true
  return chatBusinessDate(message.createdAt)===(conversationBusinessDate.value||localDate())
}
async function restoreChat(type=desiredType,{fresh=false,pending=null}={}){
  if(!profile.value)return
  const scope=storageContext(),ticket=epoch
  if(type==='reference_meal_preview'&&!referenceSelection)referenceSelection=chooseReference(profile.value,'今天三餐',{today:localDate(),tomorrow:localDate(new Date(Date.now()+86400000)),memberId:props.route.memberId})
  const anchor=type==='reference_meal_preview'?profile.value.members.find(m=>referenceSelection.participant_ids.includes(m.id)&&m.healthMemberId):null
  const id=pending?.member_id||anchor?.healthMemberId||props.route.memberId||profile.value.members.find(m=>m.id===profile.value.selfMemberId)?.healthMemberId
  const capability=profile.value.healthConfiguration?.[['meal_preview','reference_meal_preview'].includes(type)?'meal_plan':type]
  if(capability?.available===false){flow.hide();task.value={};chatError.value='营养服务暂未就绪：'+(capability.reason||'请先完成服务配置')+'。配置完成后重新读取即可。';return}
  if(!id){flow.hide();task.value={};chatError.value='请打开当前成员的家庭档案，核对已保存资料并明确同意营养咨询。';return}
  const selection=type==='reference_meal_preview'?referenceSelection:type==='diet_analysis'?{record_id:props.route.recordId,source_version:Number(props.route.version)}:props.route.indicatorChoice==='1'?scopedStorage.getStorageSync(`indicator-choice:${id}:${type}`):null
  flowScope=scope;restoring=true
  try{
    const options=!props.route.taskType&&conversationId.value?{conversationId:conversationId.value,...(type==='consultation'&&conversationThreadId.value?{threadId:conversationThreadId.value}:{})}:undefined
    await flow.open(id,type,selection,{...options,fresh})
    if(pending&&!await flow.restoreReferenceRequest(pending.thread_id,pending.request_id))throw new Error('当前问题无法恢复，请重新读取。')
    if(disposed||ticket!==epoch||scope!==storageContext())return
    if(task.value.entry?.thread_id){
      rememberThread({migrateLegacy:!options})
      const currentThread=task.value.entry.thread_id
      const pointers=props.route.taskType?[{thread_id:currentThread}]:conversationId.value?(scopedStorage.getStorageSync('conversation-threads:'+conversationId.value)||[]):(scopedStorage.getStorageSync(`homepage-chat-threads:${id}:${localDate()}`)||[])
      if(!pointers.some(p=>p.thread_id===currentThread))pointers.push({thread_id:currentThread,memberId:id})
      const results=await Promise.allSettled(pointers.map(async p=>({...(await readChatSnapshot(p.thread_id)),threadId:p.thread_id,memberId:p.memberId||id})))
      if(disposed||ticket!==epoch||scope!==storageContext()||task.value.invalidated)return
      const invalid=[]
      results.forEach((r,i)=>{if(r.status==='rejected'){if(![403,404,409,410].includes(Number(r.reason?.code)))throw r.reason;invalid.push(pointers[i].thread_id)}})
      if(invalid.length&&!props.route.taskType){
        scopedStorage.setStorageSync(conversationId.value?'conversation-threads:'+conversationId.value:`homepage-chat-threads:${id}:${localDate()}`,pointers.filter(p=>!invalid.includes(p.thread_id)))
        const legacyKey=`homepage-chat-threads:${id}:${localDate()}`
        scopedStorage.setStorageSync(legacyKey,(scopedStorage.getStorageSync(legacyKey)||[]).filter(p=>!invalid.includes(p.thread_id)))
        chatError.value='部分旧对话的授权或资料来源已变化，已停止展示；其他有效对话仍可读取。'
      }
      if(results.some((r,i)=>pointers[i].thread_id===currentThread&&r.status==='rejected'&&[409,410].includes(Number(r.reason?.code))))flow.invalidateThread()
      if(task.value.invalidated)return
      const snapshots=results.filter(r=>r.status==='fulfilled').map(r=>r.value)
      const saved=snapshots.flatMap(p=>p.messages.filter(m=>visibleConversationMessage(m,!!options?.conversationId)).map(m=>({...m,memberId:p.memberId||id,threadId:p.threadId}))).sort((a,b)=>(Date.parse(a.createdAt)||0)-(Date.parse(b.createdAt)||0))
      const live=messages.value.filter(m=>m.requestId===task.value.requestId&&(m.status==='unknown'||m.role==='assistant'&&task.value.result))
      messages.value=[...saved,...live.filter(m=>!saved.some(row=>m.requestId&&row.requestId===m.requestId&&row.role===m.role))]
      rememberThread()
      for(const date of new Set(saved.map(message=>message.planDate).filter(Boolean))){
        if(date!==localDate())void loadDailyPlan(profile.value.householdId,date,ticket,scope).catch(e=>{if(!disposed&&visible&&ticket===epoch&&scope===storageContext())mealReadError.value=e.message})
      }
      const active=snapshots.find(s=>s.threadId===currentThread)?.runs.find(r=>['queued','dispatched','pending','running','cancel_requested'].includes(r.status))
      if(active?.request_id&&!task.value.submitUnknown&&(!task.value.requestId||task.value.status==='queued'&&active.request_id!==task.value.requestId))await flow.restoreRequest(active.request_id,{preferActive:true})
      await scrollLatest()
    }else if(!task.value.requestId)messages.value=[]
  }catch(e){if(!disposed&&ticket===epoch&&scope===storageContext()){chatError.value=e.message;if([401,403,404,409,410].includes(Number(e.code))){messages.value=[];question.value='';removeDraft();submittedDraft=null}}}
  finally{restoring=false}
}
function load(){
  if(disposed)return
  visible=true
  return loadEntry(0)
}
async function loadEntry(recoveries){
  entryReady.value=false
  if(pageScope!==storageContext()){clearPrivate();pageScope=storageContext();flowScope=pageScope}
  if(loading)return loading
  const mine=++epoch,scope=storageContext(),account=getSession()
  entryError.value='';entryStatus.value='正在读取咨询资料…'
  profileLoading.value=true
  async function recoverSession(){
    // Discard every result from the previous scope before a bounded reread.
    clearPrivate();pageScope=storageContext();flowScope=pageScope
    const current=getSession()
    if(!current?.token||current.accountId!==account?.accountId||current.token!==account?.token||account?.householdId&&current.householdId!==account.householdId){
      entryError.value='登录账号或当前家庭已变化，请重新进入咨询。'
      uni.reLaunch({url:'/pages/index/index'})
      return
    }
    if(recoveries>=1){entryError.value='登录状态仍在更新，请稍后重新读取咨询资料。';return}
    return loadEntry(recoveries+1)
  }
  loading=(async()=>{try{
    const next=await loadCloudProfile({openConsultation:true})
    if(disposed||!visible||mine!==epoch)return
    if(scope!==storageContext())return await recoverSession()
    profile.value=next
    chatError.value=''
    if(props.route.question&&!question.value)question.value=String(props.route.question).slice(0,4000)
    if(props.route.indicatorChoice==='1'&&!question.value)question.value='请回顾我选择的实测记录，说明还需要补充哪些测量信息。'
    if(!next.completeProfile&&!next.onboarded){uni.redirectTo({url:'/pages/onboarding/index'});return}
    const resume=scopedStorage.getStorageSync('homepage-chat-task')
    const selfId=next.members.find(m=>m.id===next.selfMemberId)?.healthMemberId
    const current=scopedStorage.getStorageSync('homepage-conversation')
    if(!props.route.taskType&&current&&current.memberId===selfId&&(!current.scope||current.scope===scope)){conversationId.value=current.id||'';conversationThreadId.value=current.threadId||'';conversationBusinessDate.value=current.businessDate||''}
    if(!props.route.taskType&&props.route.newConversation==='1'&&!startNewHandled){startNewHandled=true;conversationId.value=newHealthRequestId();conversationThreadId.value='';conversationBusinessDate.value='';newConversationWelcome.value=true;saveConversation(selfId)}
    desiredType=Object.hasOwn(HEALTH_TEXT_TASKS,props.route.taskType)?props.route.taskType:'consultation'
    latestReference.value=null;preparedThreadId.value=''
    entryStatus.value='正在恢复对话…'
    const legacyReference=!conversationId.value&&resume?.memberId===selfId&&resume?.date===localDate()&&resume.type==='reference_meal_preview'&&resume.selection?.family_id===next.householdId
    if(legacyReference){referenceSelection=resume.selection;desiredType=resume.type}
    newConversationWelcome.value=!!conversationId.value&&!conversationThreadId.value
    await restoreChat(desiredType,{fresh:newConversationWelcome.value&&resume?.fresh===true})
    if(!disposed&&visible&&mine===epoch&&scope===storageContext()&&!props.route.taskType)await restoreSpecialTask(resume)
    if(disposed||!visible||mine!==epoch)return
    if(scope!==storageContext())return await recoverSession()
    cardVisible.value=state.phase==='ready';entryReady.value=true;returnVerified.value=true;loadedDate=localDate()
    rememberChatEntry(next)
    if(!prompts.value.length||promptDate.value!==localDate())refreshPrompts()
    void loadOptionalMeals(next.householdId,mine,scope)
  }catch(e){
    if(disposed||!visible||mine!==epoch)return
    if(scope!==storageContext())return await recoverSession()
    if([401,403].includes(Number(e.code))||!getSession()?.token){
      clearPrivate()
      entryError.value=e.message||'登录或咨询授权已变化，请重新读取。'
      if(!getSession()?.token)uni.reLaunch({url:'/pages/index/index'})
      return
    }
    entryError.value=e.message||'咨询资料暂时无法读取，请重试。'
  }
  finally{if(mine===epoch){loading=null;profileLoading.value=false}}})()
  return loading
}
async function loadDailyPlan(familyId,date,mine,scope){
  const ticket=(planReads[date]||0)+1;planReads[date]=ticket
  let plan
  try{plan=await readDailyMealPlan(familyId,date)}catch(error){
    if(!disposed&&visible&&mine===epoch&&scope===storageContext()&&planReads[date]===ticket&&[404,409,410].includes(Number(error.code))){
      const plans={...dailyPlans.value};delete plans[date];dailyPlans.value=plans
      if(planTimers[date])clearTimeout(planTimers[date])
      delete planTimers[date];delete planPolls[date]
      if(state.date===date){cardVisible.value=false;client.reset();selectedMeal.value=null}
      if(familyState.date===date){familyClient.reset();familyPanel.value=false;familySelection.value=null}
      if(latestReference.value?.plan_date===date)latestReference.value=null
    }
    if(!disposed&&visible&&mine===epoch&&scope===storageContext()&&planReads[date]===ticket&&[401,403].includes(Number(error.code))){
      clearPrivate();entryReady.value=false;entryError.value='身份或成员授权已变化，请重新读取当前档案。'
      if(!getSession()?.token)uni.reLaunch({url:'/pages/index/index'})
    }
    throw error
  }
  if(disposed||!visible||mine!==epoch||scope!==storageContext()||planReads[date]!==ticket)return null
  dailyPlans.value={...dailyPlans.value,[date]:plan}
  if(!activePlanStatus(plan.pending?.status)&&task.value.requestId&&task.value.taskType==='reference_meal_preview'&&referenceSelection?.plan_date===date&&activePlanStatus(task.value.status))void flow.refresh()
  if(planTimers[date])clearTimeout(planTimers[date])
  delete planTimers[date]
  if(activePlanStatus(plan.pending?.status)&&(planPolls[date]||0)<45){
    planTimers[date]=setTimeout(()=>{delete planTimers[date];planPolls[date]=(planPolls[date]||0)+1;void loadDailyPlan(familyId,date,mine,scope).catch(error=>{if(!disposed&&visible&&mine===epoch&&scope===storageContext())mealReadError.value=error.message})},2000)
  }else if(!activePlanStatus(plan.pending?.status))delete planPolls[date]
  return plan
}
async function reloadToday(){
  await loadOptionalMeals(profile.value.householdId,epoch,storageContext())
  if(task.value.requestId&&task.value.taskType==='reference_meal_preview'&&referenceSelection?.plan_date===localDate()&&activePlanStatus(task.value.status))await flow.refresh()
}
async function loadOptionalMeals(familyId,mine,scope,{preserve=false}={}){
  const ticket=++mealReadGeneration,date=localDate()
  planPolls[date]=0
  const current=()=>!disposed&&visible&&mine===epoch&&ticket===mealReadGeneration
  mealsLoading.value=true;mealReadError.value='';if(!preserve){cardVisible.value=false;client.reset()}
  const results=await Promise.allSettled([readCurrentPreparation(),loadDailyPlan(familyId,date,mine,scope)])
  if(!current())return
  mealsLoading.value=false
  if(scope!==storageContext()||results.some(r=>r.status==='rejected'&&[401,403].includes(Number(r.reason?.code)))){
    clearPrivate();entryReady.value=false;entryError.value='身份或成员授权已变化，请重新读取当前档案。'
    if(!getSession()?.token)uni.reLaunch({url:'/pages/index/index'})
    return
  }
  const prepared=results[0].status==='fulfilled'?results[0].value:null
  preparedThreadId.value=prepared?.thread_id||''
  const plan=results[1].status==='fulfilled'?results[1].value:null
  const arrangement=plan?.formal_arrangement
  if(arrangement?.status==='ready'){
    try{if(arrangement.date!==date)throw new Error('餐单日期不符');client.adopt(arrangement);cardVisible.value=true}
    catch{mealReadError.value='已保存餐单的内容尚未读完整，请重新读取。'}
  }
  if(results[1].status==='rejected')mealReadError.value='暂时无法读取已有餐单，请重新读取。'
  else if(preserve&&plan?.status!=='ready'){cardVisible.value=false;client.reset()}
}
async function refreshReturn(){
  if(disposed||!visible||!entryReady.value||returning.value)return
  const mine=++epoch,scope=storageContext();returning.value=true;returnVerified.value=false;returnError.value='';restoring=true
  const current=()=>{
    if(!disposed&&visible&&mine===epoch&&scope!==storageContext()&&pageScope===scope){
      clearPrivate();pageScope=storageContext();flowScope=pageScope
      uni.reLaunch({url:'/pages/index/index'})
      return false
    }
    return !disposed&&visible&&mine===epoch&&scope===storageContext()
  }
  try{
    const next=await loadCloudProfile({openConsultation:true})
    if(!current())return
    if(!next.completeProfile&&!next.onboarded){clearPrivate();uni.redirectTo({url:'/pages/onboarding/index'});return}
    profile.value=next
    const ok=await flow.resume()
    if(!current())return
    if(task.value.invalidated){clearPrivate();entryError.value='身份或成员授权已变化，请重新读取当前档案。';return}
    if(!ok)throw new Error(task.value.error||task.value.notice||'咨询状态暂未确认，请重新读取。')
    if(task.value.entry?.thread_id){
      const id=task.value.memberId,currentThread=task.value.entry.thread_id
      const key=conversationId.value?'conversation-threads:'+conversationId.value:`homepage-chat-threads:${id}:${localDate()}`
      const stored=props.route.taskType?[]:(scopedStorage.getStorageSync(key)||[])
      const pointers=[...stored.filter(pointer=>pointer.thread_id!==currentThread),{thread_id:currentThread}]
      const snapshots=await Promise.allSettled(pointers.map(async p=>({...(await readChatSnapshot(p.thread_id)),threadId:p.thread_id,memberId:p.memberId||id})))
      if(!current())return
      const invalid=[]
      snapshots.forEach((result,index)=>{
        if(result.status!=='rejected')return
        if(![403,404,409,410].includes(Number(result.reason?.code)))throw result.reason
        invalid.push(pointers[index].thread_id)
      })
      if(invalid.includes(currentThread)){
        flow.invalidateThread();clearPrivate();entryError.value='当前对话的授权或资料来源已变化，请重新读取。';return
      }
      if(invalid.length){
        messages.value=messages.value.filter(message=>!invalid.includes(message.threadId))
        if(!props.route.taskType)scopedStorage.setStorageSync(key,pointers.filter(pointer=>!invalid.includes(pointer.thread_id)))
        chatError.value='部分旧对话的授权或资料来源已变化，已停止展示。'
      }
      const saved=snapshots.filter(result=>result.status==='fulfilled').flatMap(result=>result.value.messages
        .filter(message=>visibleConversationMessage(message,!!conversationId.value))
        .map(message=>({...message,memberId:result.value.memberId||id,threadId:result.value.threadId})))
      for(const message of saved){
        if(!messages.value.some(old=>old.id===message.id||old.requestId&&old.requestId===message.requestId&&old.role===message.role))messages.value.push(message)
      }
    }
    returnVerified.value=true
    rememberChatEntry(next)
    void loadOptionalMeals(next.householdId,mine,scope,{preserve:true})
  }catch(error){
    if(!current())return
    if([401,403].includes(Number(error.code))||!getSession()?.token){clearPrivate();entryError.value='身份或成员授权已变化，请重新读取当前档案。';if(!getSession()?.token)uni.reLaunch({url:'/pages/index/index'});return}
    returnError.value=error.message||'暂时无法更新咨询状态，请重新读取。'
  }finally{if(mine===epoch){returning.value=false;restoring=false}}
}
onMounted(load);onShow(()=>{
  if(disposed)return
  visible=true
  if(!suspended){if(!entryReady.value)void load();return}
  suspended=false
  if(pageScope!==storageContext()){clearPrivate();pageScope=storageContext();flowScope=pageScope;void load();return}
  if(loadedDate&&loadedDate!==localDate()){
    const text=question.value,image=draftImage.value,error=draftError.value
    clearPrivate();question.value=text;draftImage.value=image;draftError.value=error;void load();return
  }
  if(entryReady.value)void refreshReturn();else void load()
})
onHide(()=>{historyOpen.value=false;if(scrollTimer!==null)clearTimeout(scrollTimer);scrollTimer=null;visible=false;suspended=true;epoch++;sendGeneration++;loading=null;profileLoading.value=false;returning.value=false;restoring=false;returnVerified.value=false;mealsLoading.value=false;stopPlanTimers();voiceRef.value?.cancel();flow.pause();pendingUser=null;sending.value=false;client.pause();familyClient.pause();familyPanel.value=false;familySelection.value=null})
onUnmounted(()=>{if(scrollTimer!==null)clearTimeout(scrollTimer);disposed=true;epoch++;draftVersion++;stopPlanTimers();client.dispose();familyClient.dispose();flow.hide()})
function openMeal(meal){uni.navigateTo({url:'/pages/shop/index?meal='+meal.type+'&date='+state.date+'&arrangement='+encodeURIComponent(state.arrangement.id)+'&version='+state.arrangement.version})}
function openDailyMeal(item,date){uni.navigateTo({url:'/pages/shop/index?meal='+item.meal_type+'&date='+date+'&arrangement='+encodeURIComponent(item.source.id)+'&version='+item.source.version+'&daily_plan_version='+dailyPlans.value[date].version})}
async function selectDailyMembers(item,date){
  await client.load(date)
  if(state.arrangement?.id!==item.source.id||state.arrangement?.version!==item.source.version){mealReadError.value='餐单已更新，请重新读取。';return}
  const meal=state.arrangement.meals.find(meal=>meal.type===item.meal_type)
  selectedMeal.value=meal?{...meal,dailyPlanVersion:dailyPlans.value[date].version}:null
}
async function purchaseDaily(option,plan){
  if(planPurchaseBusy.value)return
  if(option.kind==='formal'){uni.navigateTo({url:'/pages/shop/index?daily=1&date='+plan.date+'&arrangement='+encodeURIComponent(option.id)+'&version='+option.version+'&daily_plan_version='+plan.version});return}
  const scope=storageContext(),version=plan.version;planPurchaseBusy.value=true;mealReadError.value=''
  try{
    await commerce.connect()
    const {data}=await request({path:'/api/family/'+encodeURIComponent(profile.value.householdId)+'/daily-meal-plans/'+plan.date+'/purchase',method:'POST',data:{preview_id:option.id,version,meal_types:option.meal_types}})
    if(scope!==storageContext())return
    const current=await loadDailyPlan(profile.value.householdId,plan.date,epoch,scope)
    if(!current||current.version!==version||!current.purchase_options?.some(item=>item.kind==='reference'&&item.id===option.id))throw new Error('饮食计划已更新，请重新核对采购。')
    if(data.preview_id!==option.id||!data.package?.package_sn)throw new Error('采购来源未确认，请重试。')
    const menu=await commerce.mealPackage(data.package.package_sn,data.package.package_version)
    if(scope!==storageContext())return
    if(!menu.available||menu.scope!=='daily_reference')throw new Error('采购商品已变化，请重新核对。')
    await commerce.addMeal(menu);if(scope===storageContext())uni.navigateTo({url:'/pages/shop/index?commerce=1&cart=1'})
  }catch(e){if(scope===storageContext())mealReadError.value=e.message||'采购建议暂不可用。'}
  finally{planPurchaseBusy.value=false}
}
function shop(arrangement){if(arrangement)uni.navigateTo({url:'/pages/shop/index?daily=1&date='+arrangement.date+'&arrangement='+encodeURIComponent(arrangement.id)+'&version='+arrangement.version})}
function archives(){uni.navigateTo({url:'/pages/profile/index'})}
function memberArchive(){const member=props.route.memberId?profile.value?.members.find(m=>m.healthMemberId===props.route.memberId):profile.value?.members.find(m=>m.id===profile.value.selfMemberId);if(!member){chatError.value='当前成员档案不可访问，请返回家庭档案核查。';return}uni.navigateTo({url:'/pages/profile/member?id='+encodeURIComponent(member.id)})}
async function members(ids){const type=selectedMeal.value.type,dailyPlanVersion=selectedMeal.value.dailyPlanVersion;selectedMeal.value=null;await client.changeMembers(type,ids,{dailyPlanVersion});cardVisible.value=state.phase==='ready';if(profile.value)await loadDailyPlan(profile.value.householdId,state.date,epoch,storageContext());if(familyPanel.value&&familyState.date===state.date)await familyClient.load(state.date)}
async function sendQuestion(promptAction=''){
  if(conversationReadOnly.value){chatError.value='这段每日对话已归档，请新建对话继续。';return}
  if(!entryReady.value){chatError.value=entryError.value||'对话资料尚未读到，请重新读取。';return}
  if(!returnVerified.value){returnError.value=returnError.value||'正在核对咨询状态，请稍后发送。';return}
  if(!hasDraftContent.value||chatBusy.value||draftSaving.value||draftError.value)return
  if(!profile.value){chatError.value=entryError.value||'咨询资料尚未读到，请重新读取咨询资料后再发送。';return}
  const scope=storageContext(),mine=epoch,sendTicket=++sendGeneration,text=question.value.trim(),image=draftImage.value&&{...draftImage.value}
  sending.value=true;chatError.value=''
  let stage='select-task'
  try{
    const mealIntent=!props.route.taskType&&!image?parseChatMealIntent(text,localDate()):null
    // A revision stays in the selected plan's thread, preserving its date and
    // participants. A fresh arrangement still creates its own explicit choice.
    const referenceAdjustment=!props.route.taskType&&!image&&task.value.taskType==='reference_meal_preview'&&!!referenceSelection&&
      !(promptAction==='consultation'&&!mealIntent)&&
      !isMealPlanningCancelled(text)&&
      !/(?:什么是|介绍|解释|科普|原则|注意事项|怎么理解|如何理解|有什么区别|有何区别)/.test(text)&&
      !(!mealIntent&&/(?:怎么|怎样|如何|为什么).*(?:选|做|搭配|准备|保存|作用|摄入)|(?:有什么|有何)(?:好处|作用)/.test(text))&&
      !/(?:换(?:个|一个)?话题|换个问题|^(?:取消|停止|不用了|不需要了)(?:[，。！？\s]|$)|(?:取消|停止|不用|不需要|不想|不要)(?:再|继续)?(?:配餐|安排|生成|制定))/.test(text)&&
      (task.value.result?.type==='needs_input'||!/(?:^|[，。！？；、\s])(?:请)?(?:为我|给我|帮我|给全家|为全家|帮全家)?(?:安排|生成|制定|配一)/.test(text)&&
      /换(?:菜|成|掉|一|个)|替换|改(?:成|为|一下|早餐|午餐|晚餐|早饭|午饭|晚饭)|调整|重新(?:生成|安排|做)|再(?:生成|安排|做)|去掉|不放|不吃|不含|不要|加(?:一|点|些)|少(?:一|点|些)|多(?:一|点|些)/.test(text))
    if(mealIntent?.unsupportedDate)throw new Error('请明确选择今天或明天的一日餐单，原问题已保留。')
    const baseAction=mealQuestionAction(text)
    let action=image?'consultation':referenceAdjustment?'change':mealIntent||promptAction==='reference_meal_preview'?(baseAction==='change'?'change':'generate'):baseAction
    if(!props.route.taskType&&action==='view'){
      const date=/明天|明日/.test(text)?localDate(new Date(Date.now()+86400000)):localDate()
      const plan=await loadDailyPlan(profile.value.householdId,date,epoch,scope)
      if(!plan)return
      messages.value.push({id:newHealthRequestId(),role:'user',text},{id:newHealthRequestId(),role:'assistant',text:plan.status==='ready'?'这是当前饮食计划。':'这一天还没有饮食计划。',planDate:date})
      question.value='';await scrollLatest();return
    }
    let continuing=!props.route.taskType&&!image&&task.value.taskType==='reference_meal_preview'&&task.value.result?.type==='needs_input'&&referenceAdjustment
    let referenceFollowUp=false
    const type=Object.hasOwn(HEALTH_TEXT_TASKS,props.route.taskType)?props.route.taskType
      :!image&&(mealIntent||continuing||referenceAdjustment||promptAction==='reference_meal_preview')?'reference_meal_preview':'consultation'
    if(!props.route.taskType&&type==='consultation'&&conversationId.value)scopedStorage.setStorageSync('conversation-task:'+conversationId.value,null)
    // A plan-first conversation still needs a real consultation anchor so it
    // remains discoverable in the server-backed conversation drawer.
    if(type!=='consultation'&&!props.route.taskType&&!conversationThreadId.value){
      if(!conversationId.value)conversationId.value=newHealthRequestId()
      stage='create-conversation-anchor';await restoreChat('consultation')
      if(disposed||!visible||scope!==storageContext())return
      if(!task.value.available)throw new Error(task.value.error||task.value.notice||chatError.value||'请先核对营养咨询资料与授权。')
      if(!task.value.entry?.thread_id)await flow.createEntry()
      if(disposed||!visible||scope!==storageContext())return
      rememberThread()
      if(!conversationThreadId.value)throw new Error(task.value.error||'对话尚未建立，原问题已保留，请重试。')
    }
    if(type==='reference_meal_preview'){
      const previousVersion=referenceSelection?.daily_base_version
      const candidate=chooseReference(profile.value,text,{today:localDate(),tomorrow:localDate(new Date(Date.now()+86400000)),memberId:props.route.memberId,...(referenceAdjustment?{previous:referenceSelection}:{})})
      const changedChoice=continuing&&(candidate.plan_date!==referenceSelection.plan_date||JSON.stringify(candidate.participant_ids)!==JSON.stringify(referenceSelection.participant_ids)||/(?:安排|生成|制定|配一|只(?:要|需|用|做|安排)?(?:今天|明天|今晚)?(?:的)?(?:早餐|午餐|晚餐|早饭|午饭|晚饭)|先(?:做|安排|配)?(?:早餐|午餐|晚餐|早饭|午饭|晚饭)|^(?:早餐|午餐|晚餐|早饭|午饭|晚饭)[。！!\s]*$)/.test(text)&&JSON.stringify(candidate.meal_types)!==JSON.stringify(referenceSelection.meal_types))
      if(changedChoice){continuing=false;action='generate'}
      const selection=continuing?referenceSelection:candidate
      referenceFollowUp=referenceAdjustment&&['family_id','plan_date','participant_ids','meal_types'].every(key=>JSON.stringify(selection[key])===JSON.stringify(referenceSelection[key]))
      if(!continuing)referenceSelection=selection
      if(action==='change'&&!referenceFollowUp&&referenceSelection.meal_types.length===3&&!/三餐|全天|一天/.test(text))throw new Error('请说明要调整早餐、午餐还是晚餐。')
      const plan=await loadDailyPlan(profile.value.householdId,referenceSelection.plan_date,epoch,scope)
      if(!plan)throw new Error('计划状态已变化，请重新读取。')
      if(continuing&&referenceSelection.daily_base_version!==plan.version)throw new Error('饮食计划已有更新，请重新核对后继续。')
      if(referenceFollowUp&&previousVersion!==plan.version)referenceFollowUp=false
      if(activePlanStatus(plan.pending?.status)){inlineTodayOpen.value=plan.date===localDate();throw new Error('该日饮食计划正在生成，请等待已有任务完成。')}
      const covered=type=>plan.meals.some(item=>item.meal_type===type&&JSON.stringify((item.members||[]).map(m=>m.id).sort())===JSON.stringify(referenceSelection.participant_ids))
      if(action==='generate'&&plan.status==='ready'&&referenceSelection.meal_types.every(covered)){
        messages.value.push({id:newHealthRequestId(),role:'user',text},{id:newHealthRequestId(),role:'assistant',text:'这是当前饮食计划。',planDate:plan.date})
        question.value='';await scrollLatest();return
      }
      if(action==='generate'&&plan.status==='ready')referenceSelection.meal_types=referenceSelection.meal_types.filter(type=>!covered(type))
      if(action==='change'&&!continuing&&plan.status!=='ready')throw new Error('这一天还没有饮食计划，请先生成餐单。')
      const explicitMembers=/全家|一家|家人|我们|家庭(?:三餐|配餐|餐单|菜单|用餐|饮食计划)|为我|给我|帮我|本人|自己|一个人|一人|只(?:有|给)?我/.test(text)||profile.value.members.some(member=>[member.name,member.relation].some(label=>typeof label==='string'&&label.length>1&&['给','为','帮'].some(prefix=>['','我','我的'].some(owner=>text.includes(prefix+owner+label)))))
      if(action==='change'&&!continuing&&!referenceAdjustment&&!explicitMembers){
        const existing=plan.meals.find(item=>item.meal_type===referenceSelection.meal_types[0])
        if(existing?.members?.length)referenceSelection.participant_ids=[...new Set(existing.members.map(member=>member.id))].sort()
      }
      referenceSelection.daily_base_version=plan.version
    }
    if(type==='reference_meal_preview'&&!referenceFollowUp||!task.value.memberId||task.value.taskType!==type)await restoreChat(type,{fresh:newConversationWelcome.value&&(task.value.taskType!==type||!task.value.entry?.thread_id)})
    if(disposed||!visible||mine!==epoch||scope!==storageContext())return
    if(task.value.canRetry){chatError.value='上次问题的提交结果尚未确认，请先点击“重试原问题”或重新读取。';return}
    if(!task.value.available){chatError.value=task.value.error||task.value.notice||chatError.value||'请先在该成员的家庭档案中完成资料和咨询同意。';return}
    if(!task.value.entry?.thread_id){await flow.createEntry();rememberThread();if(task.value.entry?.thread_id)await restoreChat(type)}
    rememberThread()
    if(disposed||!visible||mine!==epoch||scope!==storageContext())return
    if(!task.value.entry?.thread_id){chatError.value=task.value.error||task.value.notice||'咨询尚未建立，请重新读取后再发送。';return}
    stage='read-image'
    const images=image?[await chatImageContent(image)]:[]
    if(disposed||!visible||mine!==epoch||scope!==storageContext())return
    stage='queue-message'
    const user=reactive({id:newHealthRequestId(),role:'user',text,createdAt:new Date().toISOString(),status:'sending',...(image?{image}: {})})
    pendingUser=user;submittedDraft={text,path:image?.localPath||'',requestId:''};messages.value.push(user)
    rememberThread()
    stage='save-draft'
    scopedStorage.setStorageSync('homepage-chat-task',{memberId:historyMemberId.value||task.value.memberId,taskMemberId:task.value.memberId,type,date:localDate(),newConversation:newConversationWelcome.value,conversationId:conversationId.value,...(type==='reference_meal_preview'?{selection:referenceSelection}:{})});desiredType=type
    stage='scroll-message'
    await scrollLatest()
    if(disposed||!visible||mine!==epoch||scope!==storageContext()||sendTicket!==sendGeneration)return
    stage='submit-task'
    const accepted=await flow.submit(text,false,images)
    if(disposed||!visible||mine!==epoch||scope!==storageContext())return
    if(!accepted&&type==='reference_meal_preview'&&task.value.error?.includes('该日饮食计划正在生成')){
      messages.value=messages.value.filter(message=>message!==user)
      await loadDailyPlan(profile.value.householdId,referenceSelection.plan_date,epoch,scope)
      inlineTodayOpen.value=referenceSelection.plan_date===localDate()
      chatError.value=task.value.error;return
    }
    user.status=accepted?'sent':task.value.canRetry?'unknown':'failed'
    if(accepted&&!['failed','rejected'].includes(task.value.status)){if(question.value.trim()===text)question.value='';if(draftImage.value?.localPath===(image?.localPath||''))removeDraft()}
    else chatError.value=task.value.error||'回复尚未完成，原问题和图片已保留。'
  }catch(e){if(!disposed&&visible&&mine===epoch&&scope===storageContext()){
    chatError.value=e.message
    if(e?.name==='TypeError'){
      // Caught client errors otherwise lose their frames on the device. Keep
      // this local and omit message payloads, URL queries and private paths.
      const stack=String(e.stack||'').split('\n').filter(line=>/^\s*at\s/.test(line)).map(line=>{
        const frame=line.match(/(?:^|[\\/])([A-Za-z0-9_-]+\.(?:js|vue))(?:\?[^\r\n]*)?:(\d+):(\d+)\)?$/)
        return frame?`at ${frame[1]}:${frame[2]}:${frame[3]}`:''
      }).filter(Boolean).slice(0,6).join('\n')
      console.error('[health-chat-send]',{stage,name:'TypeError',message:e.message==='Cannot convert undefined or null to object'?e.message:'TypeError',stack})
    }
  }}
  finally{if(sendTicket===sendGeneration){pendingUser=null;sending.value=false;if(!disposed&&visible&&mine===epoch&&scope===storageContext()&&chatError.value)uni.showToast({title:chatError.value,icon:'none',duration:3500})}}
}
async function resumePlanQuestion(){
  const pending=todayPlan.value?.pending
  if(chatBusy.value||pending?.status!=='needs_input'||pending.selection?.family_id!==profile.value?.householdId||pending.selection?.plan_date!==localDate())return
  const scope=storageContext(),mine=epoch
  try{
    referenceSelection=pending.selection;desiredType='reference_meal_preview';chatError.value=''
    await restoreChat(desiredType,{pending})
    if(disposed||!visible||mine!==epoch||scope!==storageContext())return
    scopedStorage.setStorageSync('homepage-chat-task',{memberId:historyMemberId.value||pending.member_id,taskMemberId:pending.member_id,type:desiredType,date:localDate(),conversationId:conversationId.value,selection:referenceSelection})
    rememberThread();await scrollLatest()
  }catch(e){if(!disposed&&visible&&mine===epoch&&scope===storageContext())chatError.value=e.message}
}
async function retryQuestion(){chatError.value='';await flow.submit('',true);await scrollLatest()}
async function restartChat(){
  if(chatBusy.value||draftSaving.value)return
  const scope=storageContext(),text=question.value,image=draftImage.value,error=draftError.value
  await newConversation()
  if(disposed||!visible||scope!==storageContext())return
  question.value=text;draftImage.value=image;draftError.value=error
}
async function editFailedQuestion(){
  const original=failedQuestion.value
  if(!original||chatBusy.value||draftSaving.value)return
  const scope=storageContext(),ticket=epoch,text=original.text||'',image=original.image&&{...original.image}
  await restartChat()
  if(disposed||!visible||scope!==storageContext()||ticket!==epoch)return
  question.value=text;draftImage.value=image||null;draftError.value=''
}
async function consent(){if(!consentChecked.value)return;consentChecked.value=false;await flow.acceptConsent(true);await sendQuestion(task.value.taskType==='reference_meal_preview'?'reference_meal_preview':undefined)}
function sendVoice(text){question.value=text;voiceBusy.value=false;void sendQuestion()}
function removeDraft(){draftVersion++;draftImage.value=null;draftSaving.value=false;draftError.value=''}
async function prepareDraft(image=draftImage.value){
  if(!image)return
  const version=++draftVersion,scope=storageContext();draftImage.value=image;draftSaving.value=true;draftError.value=''
  try{const saved=await persistChatImage({path:image.path||image.localPath,source:image.source});if(!disposed&&version===draftVersion&&scope===storageContext()){draftImage.value=saved;scopedStorage.setStorageSync('last-chat-image',saved)}}
  catch(e){if(!disposed&&version===draftVersion&&scope===storageContext())draftError.value=e.message}
  finally{if(version===draftVersion)draftSaving.value=false}
}
function camera(){
  if(openingCamera||chatBusy.value||voiceBusy.value||draftSaving.value)return
  const scope=storageContext();openingCamera=true;uni.hideKeyboard?.()
  uni.navigateTo({url:'/pages/chat/camera',events:{photoSelected:image=>{if(!disposed&&scope===storageContext())void prepareDraft(image)}},fail(){chatError.value='相机打开失败，请重试'},complete(){openingCamera=false}})
}
function history(){uni.hideKeyboard?.();historyOpen.value=true}
function stashConversationDraft(){if(conversationId.value)conversationDrafts.set(conversationId.value,{text:question.value,image:draftImage.value,error:draftError.value})}
function resetConversationView(){flow.hide();messages.value=[];question.value='';removeDraft();submittedDraft=null;pendingUser=null;referenceSelection=null;latestReference.value=null;familyPanel.value=false;inlineTodayOpen.value=false;chatError.value='';desiredType='consultation';scrollTarget.value=''}
async function generateReference(){
  if(chatBusy.value||conversationReadOnly.value)return
  question.value='请帮我安排今天的三餐'
  await sendQuestion('reference_meal_preview')
}
async function newConversation(){
  if(chatBusy.value||voiceBusy.value||draftSaving.value)return
  if(props.route.taskType){uni.reLaunch({url:'/pages/chat/index?newConversation=1'});return}
  stashConversationDraft();resetConversationView();refreshPrompts()
  conversationId.value=newHealthRequestId();conversationThreadId.value='';conversationBusinessDate.value='';newConversationWelcome.value=true
  const id=profile.value?.members.find(m=>m.id===profile.value.selfMemberId)?.healthMemberId
  if(id){saveConversation();scopedStorage.setStorageSync('homepage-chat-task',{memberId:id,type:'consultation',date:localDate(),conversationId:conversationId.value,newConversation:true})}
  historyOpen.value=false;switchingConversation.value=true
  try{await restoreChat('consultation')}finally{switchingConversation.value=false}
}
async function selectConversation(row){
  if(chatBusy.value||voiceBusy.value||draftSaving.value||row.unavailable)return
  const id=profile.value?.members.find(m=>m.id===profile.value.selfMemberId)?.healthMemberId
  if(!id||row.member_id!==id||row.agent_slug!=='health-consultation')return
  if(props.route.taskType){scopedStorage.setStorageSync('homepage-conversation',{id:row.thread_id,threadId:row.thread_id,memberId:id,businessDate:row.business_date||''});uni.reLaunch({url:'/pages/chat/index'});return}
  stashConversationDraft();resetConversationView();refreshPrompts()
  const scope=storageContext(),mine=epoch
  const saved=scopedStorage.getStorageSync('conversation-index:'+row.thread_id)
  const resume=scopedStorage.getStorageSync('homepage-chat-task')
  conversationId.value=saved?.memberId===id?saved.id:row.thread_id
  conversationThreadId.value=row.thread_id;conversationBusinessDate.value=row.business_date||'';newConversationWelcome.value=false
  saveConversation(id);historyOpen.value=false;switchingConversation.value=true
  try{
    await restoreChat('consultation')
    if(scope!==storageContext()||mine!==epoch||task.value.invalidated)return
    await restoreSpecialTask(resume)
    if(scope!==storageContext()||mine!==epoch||task.value.invalidated)return
    scopedStorage.setStorageSync('homepage-chat-task',{memberId:historyMemberId.value||task.value.memberId,taskMemberId:task.value.memberId,type:task.value.taskType,date:localDate(),conversationId:conversationId.value,...(task.value.taskType==='reference_meal_preview'?{selection:referenceSelection}:{})})
    const draft=conversationDrafts.get(conversationId.value)
    if(draft&&!conversationReadOnly.value){question.value=draft.text;draftImage.value=draft.image;draftError.value=draft.error}
  }finally{switchingConversation.value=false}
}
async function shortcut(key){
  if(key==='family')archives()
  else if(key==='camera')uni.navigateTo({url:'/pages/scan/index'})
  else if(key==='community')communityOpen.value=true
  else if(key==='plans')uni.navigateTo({url:'/pages/exclusive-plans/index'})
  else{inlineTodayOpen.value=!inlineTodayOpen.value;if(inlineTodayOpen.value&&!mealsLoading.value&&!state.busy&&profile.value)await loadOptionalMeals(profile.value.householdId,epoch,storageContext())}
}
async function askPrompt(prompt){
  if(chatBusy.value||voiceBusy.value||draftSaving.value)return
  const {text,action}=typeof prompt==='string'?{text:prompt}:prompt||{}
  if(!text)return
  if(action==='open_records'||!action&&text==='看看我的饮食记录'){uni.navigateTo({url:'/pages/records/index'});return}
  question.value=text
  await sendQuestion(action||'')
}
function quoteReply(text){if(chatBusy.value||conversationReadOnly.value)return;question.value=`关于你刚才提到的“${text.slice(0,600)}”，`}
function messageTime(message,index){
  const now=Date.parse(chatTimestamp(message.createdAt)),previous=Date.parse(chatTimestamp(visibleMessages.value[index-1]?.createdAt))
  if(!Number.isFinite(now)||index>0&&Number.isFinite(previous)&&now-previous<5*60000)return ''
  const date=new Date(now),time=String(date.getHours()).padStart(2,'0')+':'+String(date.getMinutes()).padStart(2,'0')
  return localDate(date)===localDate()?time:`${date.getMonth()+1}月${date.getDate()}日 ${time}`
}

</script>
<template>
<NutritionistLayout :voice-busy="voiceBusy" :scroll-target="scrollTarget" :history-open="historyOpen" :show-shortcuts="presentation.welcome&&!keyboardFocused" @history="history" @profile="uni.navigateTo({url:'/pages/my/index'})" @shortcut="shortcut">
 <template #default>
  <view v-if="presentation.initialResults" class="analysis-message"><AiAnswer :text="state.arrangement.analysis.text" compact/></view>
  <DailyArrangementCard v-if="cardVisible && presentation.initialResults" :arrangement="state.arrangement" :disabled="state.busy" @open="openMeal" @members="selectedMeal=$event" @shop="shop"/>
   <view v-if="failedTask" class="recovery-card" role="status">
    <text class="recovery-label">上次的请求</text>
    <text class="recovery-title">{{task.taskType==='reference_meal_preview'?'餐单还没有生成':'这次咨询还没有完成'}}</text>
    <text class="recovery-copy">{{failedQuestion?'可以编辑原问题后重新发送，也可以开始新的营养咨询。':'原问题暂未读到，可以重新读取对话，或开始新的营养咨询。'}}</text>
    <text v-if="failedQuestion?.text" class="recovery-question" selectable>{{failedQuestion.text}}</text>
    <image v-if="failedQuestion?.image" class="recovery-image" :src="failedQuestion.image.localPath" mode="aspectFill" @click="previewChatImage(failedQuestion.image)"/>
    <view class="recovery-actions"><button v-if="failedQuestion" class="recovery-primary" :disabled="chatBusy||draftSaving" @click="editFailedQuestion">编辑原问题</button><button v-else :disabled="chatBusy" @click="load">重新读取对话</button><button :disabled="chatBusy||draftSaving" @click="restartChat">开始新咨询</button></view>
   </view>
   <ChatWelcome v-if="presentation.welcome" :compact="failedTask" :prompts="prompts" :disabled="chatBusy" @ask="askPrompt" @shuffle="shufflePrompts" @today="shortcut('today')"/>
  <view v-for="(message,messageIndex) in visibleMessages" :id="'message-'+message.id" :key="message.id" class="message-turn">
   <view v-if="messageTime(message,messageIndex)" class="message-time"><text>{{messageTime(message,messageIndex)}}</text></view>
   <view class="message-row" :class="message.role"><view class="message-content"><view class="bubble"><view v-if="message.role==='assistant'" class="reply-card-head"><AppIcon name="assistant" :size="46" :state="message.business&&isReferencePlan(message.business.data)?'success':'idle'"/><text>家庭营养师</text></view><view class="bubble-body"><image v-if="message.image" class="chat-message-image" :src="message.image.localPath" mode="widthFix" @click="previewChatImage(message.image)"/><AiAnswer v-if="message.role==='assistant'&&message.text" :text="message.text" :citations="message.citations||[]" compact/><text v-else-if="message.text" selectable>{{message.text}}</text>
    <text v-if="message.status==='unknown'" class="chat-error">提交结果待确认，请勿重复发送。</text>
    <text v-if="message.status==='failed'||message.status==='rejected'" class="chat-error">服务器已收到本条问题，但处理未完成。</text><text v-if="message.status==='cancelled'" class="chat-error">已取消本次问题。</text>
   </view></view><DailyMealPlanCard v-if="message.planDate&&dailyPlans[message.planDate]?.status==='ready'" :plan="dailyPlans[message.planDate]" :busy="planPurchaseBusy" @open="openDailyMeal($event,message.planDate)" @members="selectDailyMembers($event,message.planDate)" @shop="purchaseDaily($event,dailyPlans[message.planDate])"/><HealthChatBusinessCard v-else-if="message.business&&!message.planDate" :result="message.business" :member-id="message.memberId||task.memberId"/><ConversationFoodPackages v-if="message.purchaseRequestId" :offers="message.purchaseOffers" :request-id="message.purchaseRequestId"/><ChatReplyActions v-if="message.role==='assistant'&&message.text&&!message.error" :text="message.text" :message-id="message.serverMessageId||message.id" :can-quote="!chatBusy&&!conversationReadOnly" @quote="quoteReply"/></view></view>
  </view>
  <view v-if="mealReplyActions&&!chatBusy&&!conversationReadOnly" class="reply-actions" aria-label="继续安排饮食">
   <button @click="question='请换几道菜，继续沿用已确认的饮食限制。'"><text>换几道菜</text><AppIcon name="arrow" :size="23"/></button>
   <button @click="generateReference"><text>整理成今日餐单</text><AppIcon name="arrow" :size="23"/></button>
  </view>
  <view v-if="liveAnswer||entryReady&&!profileLoading&&chatBusy" id="stream-answer" class="message-row assistant live-answer"><view class="message-content"><view class="bubble"><view class="reply-card-head"><AppIcon name="assistant" :size="46" :state="task.taskType==='reference_meal_preview'?'planning':'thinking'"/><text>家庭营养师</text></view><view class="bubble-body"><AiAnswer v-if="liveAnswer" :text="task.streamText" streaming compact/><view id="reply-progress" class="reply-progress" role="status" aria-live="polite"><view class="progress-dot"/><text>{{progressText}}</text></view></view></view></view></view>
  <view v-if="familyPanel" class="dialogue-status"><text>家庭餐单 · {{familyState.date}}</text><text>按这餐实际参加的成员核对家庭安排，每位成员的资料和权限由服务端检查。</text><text v-if="familyState.busy">正在读取家庭安排…</text><text v-if="familyState.error" class="chat-error">{{familyState.error}}</text><button v-if="familyState.error" :disabled="familyState.busy" @click="familyPlan('',true)">重新读取家庭餐单</button><DailyArrangementCard v-if="familyState.phase==='ready'" :arrangement="familyState.arrangement" family :disabled="familyState.busy" @open="openFamilyMeal" @members="familySelection={type:$event.type,ids:$event.members.map(m=>m.id),question:''}" @shop="shop"/><button @click="familyPanel=false">收起家庭餐单</button></view>
  <text v-if="entryError||chatError" class="chat-error" role="alert">{{entryError||chatError}}</text>
  <view v-if="returnError" class="dialogue-status"><text>{{returnError}}</text><button :disabled="returning" @click="refreshReturn">重新核对咨询状态</button></view>
  <button v-if="!profile&&!profileLoading" class="secondary-button" @click="load()">重新读取咨询资料</button>
  <view v-if="task.error||task.canRetry||task.submitUnknown||task.streamPhase==='paused'||task.notice&&!chatBusy" class="dialogue-status recovery-status"><text>{{task.error||task.notice}}</text><button v-if="task.requestId&&task.result?.type!=='error'" :disabled="task.refreshing" @click="flow.refresh()">{{task.refreshing?'正在读取…':'重新读取本次回复'}}</button><button v-if="task.canRetry" :disabled="retryBusy" @click="retryQuestion">重试原问题</button></view>
  <button v-if="(task.invalidated||task.status==='failed')&&!route.taskType" class="secondary-button" :disabled="chatBusy||draftSaving" @click="restartChat">开始新咨询</button>
  <button v-if="entryReady&&profile&&(!task.available||needsProfileLink)" class="secondary-button" @click="memberArchive">查看该成员档案</button><view v-if="task.consentOption" class="dialogue-status"><text>本次{{task.taskType==='reference_meal_preview'?'配餐':'咨询'}}处理方：{{task.consentOption.processor}}；政策版本：{{task.consentOption.policyVersion}}。</text><checkbox-group @change="consentChecked=$event.detail.value.includes('yes')"><label><checkbox value="yes" :checked="consentChecked"/>同意本次{{task.taskType==='reference_meal_preview'?'配餐':'咨询'}}的数据处理</label></checkbox-group><button :disabled="!consentChecked||chatBusy" @click="consent">同意并继续{{task.taskType==='reference_meal_preview'?'配餐':'咨询'}}</button></view>
 </template>
 <template #composer>
  <view v-if="conversationReadOnly" class="archived-conversation"><text>这段每日对话已归档，记录仍可查看。</text><button :disabled="chatBusy" @click="newConversation">新对话继续聊</button></view>
  <template v-else>
  <view v-if="draftImage" class="image-draft"><view class="draft-thumbnail"><image :src="draftImage.localPath||draftImage.path" mode="aspectFill" @click="previewChatImage(draftImage)"/><button aria-label="移除待发送图片" @click="removeDraft">×</button></view><view><text>{{draftSaving?'正在准备图片…':draftError||'可直接发送图片，也可以补充文字'}}</text><button v-if="draftError" @click="prepareDraft()">重新准备图片</button></view></view>
  <view class="composer"><button class="input-icon camera-input" aria-label="打开相机或选择照片" :disabled="chatBusy||voiceBusy||draftSaving" @click="camera"><AppIcon name="camera" :size="34"/></button><VoiceInput v-if="voiceMode" ref="voiceRef" :disabled="chatBusy||draftSaving" @send="sendVoice" @busy="voiceBusy=$event"/><input v-else v-model="question" :disabled="inputBusy" placeholder="有问题尽管问我" confirm-type="send" @focus="keyboardFocused=true" @blur="keyboardFocused=false" @confirm="sendQuestion"/>
   <button v-if="canCancel" class="send-button stop-button" aria-label="停止生成" :disabled="task.busy||task.streamPhase==='cancelling'" @click="flow.cancelRequest()"><view class="stop-square"/></button>
   <button v-else-if="voiceMode" class="input-icon" aria-label="切换文字输入" :disabled="voiceBusy" @click="voiceMode=false"><view class="keyboard-icon"><view/><view/><view/></view></button>
   <button v-else-if="hasDraftContent" class="send-button" aria-label="发送" :disabled="chatBusy||draftSaving||!!draftError" @click="sendQuestion"><AppIcon name="arrow" :size="28"/></button><button v-else class="input-icon" aria-label="切换语音输入" :disabled="chatBusy" @click="voiceMode=true"><AppIcon name="mic" :size="34"/></button>
  </view>
  </template>
  <text class="ai-content-note">内容由 AI 生成，请结合自身情况核对</text>
 </template>
 <template #overlays>
  <ChatConversationDrawer :open="historyOpen" :member-id="historyMemberId" :active-thread-id="conversationThreadId" :busy="chatBusy||voiceBusy||draftSaving" :display-name="profile?.members.find(m=>m.id===profile.selfMemberId)?.name||'我的'" @close="historyOpen=false" @new="newConversation" @select="selectConversation" @profile="historyOpen=false;uni.navigateTo({url:'/pages/my/index'})"/>
  <view v-if="inlineTodayOpen" class="meal-sheet-mask" @click.self="inlineTodayOpen=false">
   <view class="meal-sheet" role="dialog" aria-label="今日餐单">
    <view class="inline-today-head"><text>今日餐单</text><button aria-label="关闭今日餐单" @click="inlineTodayOpen=false">×</button></view>
    <scroll-view class="meal-sheet-content" scroll-y>
   <text v-if="planRunning" class="composer-note">{{(planPolls[localDate()]||0)>=45?'等待已暂停，可重新读取同一计划。':'正在生成今日饮食计划，已有计划会保留到更新完成。'}}</text>
   <view v-if="todayPlan?.pending?.status==='needs_input'" class="dialogue-status"><text>生成饮食计划还需要补充：</text><text v-for="question in todayPlan.pending.questions" :key="question">{{question}}</text><button :disabled="chatBusy" @click="resumePlanQuestion">继续回答</button></view>
   <text v-else-if="todayPlan?.status==='ready'&&['failed','rejected','interrupted'].includes(todayPlan?.pending?.status)" class="composer-note">上次调整未完成，当前仍显示已保存的计划。</text>
   <DailyMealPlanCard v-if="todayPlan?.status==='ready'" :plan="todayPlan" :busy="planPurchaseBusy||state.busy||planRunning" @open="openDailyMeal($event,todayPlan.date)" @members="selectDailyMembers($event,todayPlan.date)" @shop="purchaseDaily($event,todayPlan)"/>
   <text v-else-if="planRunning" class="composer-note">请稍候，也可以重新读取同一任务。</text>
   <text v-else-if="mealsLoading||state.busy" class="composer-note">正在读取已保存的餐单…</text>
   <view v-else-if="todayPlan?.pending?.status!=='needs_input'&&!mealReadError&&!state.error" class="reference-empty"><text class="composer-note">{{['failed','rejected','interrupted'].includes(todayPlan?.pending?.status)?'上次饮食计划未能完成，可以重新生成。':'今天还没有饮食计划。'}}</text><button class="secondary-button" :disabled="chatBusy" @click="generateReference">生成今日饮食计划</button></view>
   <button v-if="planRunning" class="secondary-button" :disabled="mealsLoading" @click="reloadToday">重新读取计划</button>
   <view v-if="mealReadError||state.error"><text class="chat-error" role="alert">{{mealReadError||state.error}}</text><button class="secondary-button" :disabled="mealsLoading||state.busy" @click="loadOptionalMeals(profile.householdId,epoch,storageContext())">重新读取餐单</button></view>
    </scroll-view>
   </view>
  </view>
  <DinerPicker :open="!!familySelection" :members="profile?.members||[]" :selected="familySelection?.ids||[]" :meal="({breakfast:'早餐',lunch:'午餐',dinner:'晚餐'})[familySelection?.type]" @close="familySelection=null" @confirm="familyMembers"/>
  <DinerPicker :open="!!selectedMeal" :members="profile?.members||[]" :selected="selectedMeal?.members.map(m=>m.id)||[]" :meal="({breakfast:'早餐',lunch:'午餐',dinner:'晚餐'})[selectedMeal?.type]" @close="selectedMeal=null" @confirm="members"/>
  <view v-if="communityOpen" class="sheet-mask" @click.self="communityOpen=false"><view class="sheet"><text class="section-title">加入社群</text><text class="composer-note">暂无可用社群二维码，请稍后再试。</text><button class="secondary-button" @click="communityOpen=false">关闭</button></view></view>
 </template>
</NutritionistLayout>
</template>
<style scoped>
.recovery-card{margin:24px 0 8px;padding:18px;border:1px solid #e5e5e5;border-radius:12px;background:#fafafa}.recovery-label{display:block;font-size:11px;line-height:1.6;color:#888}.recovery-title{display:block;margin-top:5px;font-size:18px;font-weight:500;line-height:1.5;color:#222}.recovery-copy{display:block;margin-top:8px;font-size:13px;line-height:1.7;color:#777}.recovery-question{display:block;margin-top:14px;padding-left:12px;border-left:2px solid #d7d7d7;font-size:14px;line-height:1.7;color:#444;white-space:pre-line;overflow-wrap:anywhere;max-height:120px;overflow:auto}.recovery-image{display:block;width:64px;height:64px;margin-top:12px;border-radius:6px}.recovery-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}.recovery-actions button{display:flex;align-items:center;justify-content:center;min-height:44px;margin:0;padding:0 14px;border:1px solid #ddd;border-radius:8px;background:#fff;font-size:13px;line-height:1.5;color:#444}.recovery-actions button:after{border:0}.recovery-actions .recovery-primary{background:#222;border-color:#222;color:#fff}.recovery-actions button[disabled]{opacity:.45}
.message-turn{margin:18px 0}.message-row{display:flex;width:100%;margin:18px 0;color:#242637}.message-turn>.message-row{margin:0}.message-content{width:100%;min-width:0;max-width:100%}.message-row.user{justify-content:flex-end;padding-left:38px;box-sizing:border-box}.user .message-content{width:auto;max-width:100%;flex:0 1 auto}.bubble{position:relative;box-sizing:border-box;max-width:100%;border:0;border-radius:14px;background:#fff;color:#242637;font-size:16px;line-height:1.62;overflow-wrap:anywhere;word-break:break-word}.bubble-body{padding:14px}.assistant .bubble:after{content:'';position:absolute;left:-6px;bottom:0;width:15px;height:12px;background:#fff;clip-path:polygon(100% 0,100% 100%,0 100%)}.reply-card-head{display:flex;align-items:center;gap:6px;min-height:30px;box-sizing:border-box;padding:5px 12px;border-bottom:1px solid #eeeafa;font-size:11px;line-height:1.4;color:#9290a2}.user .bubble{display:block;width:auto;border-radius:13px 13px 0 13px;background:#5937fa;color:#fff;box-shadow:0 2px 3px rgba(77,48,208,.1);white-space:pre-line}.user .bubble-body{padding:11px 13px}.user .bubble:after{content:'';position:absolute;right:-6px;bottom:0;width:12px;height:11px;background:#5937fa;clip-path:polygon(0 0,100% 100%,0 100%)}.message-time{display:flex;justify-content:center;margin:16px 0 14px}.message-time text{padding:2px 7px;background:rgba(116,119,138,.53);border-radius:12px;font-size:11px;line-height:1.5;color:#fff}.analysis-message{margin:18px 0;padding:14px;background:#fff;border-radius:14px}.reply-actions{display:flex;flex-direction:column;align-items:flex-start;gap:9px;margin:0 0 20px}.reply-actions button{display:flex;align-items:center;justify-content:space-between;gap:16px;max-width:100%;min-height:40px;margin:0;padding:9px 13px;border:0;border-radius:10px;background:rgba(255,255,255,.88);color:#3c394d;font-size:14px;line-height:1.5;text-align:left}.reply-actions button:after{border:0}.reply-actions button :deep(.app-icon){color:#7e7693}
.dialogue-status{padding:12px 14px;margin:16px 0;background:rgba(255,255,255,.8);border-radius:12px;font-size:13px;line-height:1.65;color:#777186}.dialogue-status>text{display:block}.dialogue-status button,.secondary-button{display:inline-flex;align-items:center;justify-content:center;min-height:42px;margin:9px 8px 0 0;padding:7px 12px;border:1px solid #e5dff6;border-radius:9px;background:#fff;font-size:13px;line-height:1.5;color:#625581}.dialogue-status button:after,.secondary-button:after{border:0}.reply-progress{display:flex;align-items:center;gap:8px;min-height:26px;font-size:13px;line-height:1.6;color:#9c92b4}.live-answer .ai-answer+.reply-progress{margin-top:12px}.progress-dot{width:6px;height:6px;flex-shrink:0;border-radius:50%;background:#9677ed;animation:progress-breathe 1.4s ease-in-out infinite}.chat-error{display:block;margin-top:10px;font-size:12px;line-height:1.6;color:#9c5664}.user .chat-error{color:#f7d5e5}.live-answer{padding-bottom:3px}
.composer{display:flex;align-items:center;gap:4px;padding:5px 6px;min-height:48px;box-sizing:border-box;border:1px solid rgba(255,255,255,.95);border-radius:14px;background:#f9f9fe;box-shadow:0 4px 16px rgba(100,78,181,.035)}.composer input{flex:1;min-width:0;height:40px;box-sizing:border-box;padding:0 8px;border:0;border-radius:0;background:transparent;color:#302c43;font-size:16px;line-height:1.5}.input-icon,.send-button{display:flex;flex-shrink:0;align-items:center;justify-content:center;min-width:40px;width:40px;min-height:40px;height:40px;margin:0;padding:0;border:0;border-radius:50%;background:transparent;color:#50525f}.input-icon:after,.send-button:after{border:0}.camera-input{position:relative}.camera-input:before{content:'';position:absolute;right:0;top:10px;bottom:10px;width:1px;background:#e9e6f0}.send-button{color:#fff;background:#5937fa}.send-button[disabled]{opacity:.4}.stop-square{width:12px;height:12px;border-radius:3px;background:#fff}.composer :deep(.voice-input){flex:1;width:auto;min-width:0;height:40px;box-sizing:border-box;border:0;border-radius:8px;background:transparent}.composer :deep(.hold-to-talk){height:40px;font-size:15px}.keyboard-icon{width:20px;height:15px;border:1.5px solid currentColor;border-radius:3px;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:3px}.keyboard-icon>view{width:13px;border-top:1px dotted currentColor}.keyboard-icon>view:last-child{width:9px;border-top-style:solid}.ai-content-note{display:block;padding-top:9px;text-align:center;font-size:10px;line-height:1.4;color:#9690a9}.archived-conversation{display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:12px;color:#81778f;line-height:1.6}.archived-conversation button{flex-shrink:0;padding:7px 10px;min-height:40px;border-radius:9px;background:#5937fa;color:#fff;font-size:12px}.archived-conversation button:after{border:0}
.chat-message-image{display:block;width:210px;max-width:100%;height:auto;border-radius:9px;margin-bottom:8px}.image-draft{display:flex;align-items:center;gap:12px;padding:8px 0 14px;font-size:12px;line-height:1.6;color:#81778f}.draft-thumbnail{position:relative;flex-shrink:0}.draft-thumbnail image{width:56px;height:56px;border-radius:8px}.draft-thumbnail button{position:absolute;top:-7px;right:-7px;width:24px;height:24px;display:flex;align-items:center;justify-content:center;border-radius:50%;background:#fff;color:#66587e}.image-draft>view+view{flex:1}.image-draft button{font-size:13px;min-height:24px}.meal-sheet-mask{position:fixed;inset:0;z-index:70;display:flex;align-items:flex-end;background:rgba(31,23,54,.35)}.meal-sheet{display:flex;flex-direction:column;box-sizing:border-box;width:100%;max-height:80vh;padding:12px 20px calc(env(safe-area-inset-bottom) + 20px);border-radius:24px 24px 0 0;background:#fff}.meal-sheet-content{flex:1;min-height:0;max-height:65vh}.inline-today-head{display:flex;align-items:center;justify-content:space-between;padding-bottom:8px;font-size:18px;color:#3e3550}.inline-today-head button{display:flex;align-items:center;justify-content:center;min-height:44px;min-width:44px;background:transparent;color:#6e6285;font-size:28px}.reference-empty{padding:20px 0}.composer-note{display:block;font-size:12px;color:#8c829b;line-height:1.7;margin-top:8px}.section-title{font-size:18px}.sheet-mask .sheet{background:#fff;color:#3e3550}.sheet-mask .composer-note{text-align:left}
@keyframes progress-breathe{0%,100%{opacity:.4}50%{opacity:1}}@media(prefers-reduced-motion:reduce){.progress-dot{animation:none}}@media(max-width:350px){.bubble{font-size:15px}.message-row.user{padding-left:26px}.user .bubble-body{padding:10px 12px}.composer input{font-size:15px;padding-left:6px}.input-icon,.send-button{min-width:38px;width:38px}}
</style>
