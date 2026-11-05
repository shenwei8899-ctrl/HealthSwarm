<script setup>
// WeChat must share this component's scoped styles with the NutritionistLayout slots.
defineOptions({options:{styleIsolation:'shared'}})
import { computed, reactive, ref, nextTick, watch, onMounted, onUnmounted } from 'vue'
import { onShow, onHide } from '@dcloudio/uni-app'
import NutritionistLayout from './NutritionistLayout.vue'
import ChatConversationDrawer from './ChatConversationDrawer.vue'
import MealDetailSheet from './MealDetailSheet.vue'
import ChatMealRecordCard from './ChatMealRecordCard.vue'
import {mealTarget,openMealPage} from '../services/meal-workspace.js'
import {canPurchaseAllMeals} from '../utils/meal-presentation.js'
import ChatWelcome from './ChatWelcome.vue'
import { chatPresentation } from '../services/chat-presentation.js'
import { createChatEntryTransition } from '../services/chat-entry-transition.js'
import { createChatKeyboardLayout } from '../services/chat-keyboard-layout.js'
import AppIcon from './AppIcon.vue'
import DinerPicker from './DinerPicker.vue'
import HealthChatBusinessCard from './HealthChatBusinessCard.vue'
import DailyArrangementCard from './DailyArrangementCard.vue'
import DailyMealPlanCard from './DailyMealPlanCard.vue'
import TodayMealPlanSheet from './TodayMealPlanSheet.vue'
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

const detailRef=ref(null),detailOpen=ref(false)
const reading=ref({following:true}),latestAvailable=ref(false)
let scrollRevision=0,textVersion=0
const props=defineProps({route:{type:Object,default:()=>({})}})
const state=reactive(dailyArrangementState()),profile=ref(null),cardVisible=ref(false),selectedMeal=ref(null)
const profileLoading=ref(false),entryReady=ref(false)
const returning=ref(false),returnError=ref(''),returnVerified=ref(true)
const entryError=ref('')
const composerPlaceholder=computed(()=>profileLoading.value||returning.value?'正在连接营养师…':'有问题尽管问我')
const onboardingPending=ref(false)
const needsProfileLink=computed(()=>!!profile.value&&!props.route.memberId&&!profile.value.members.find(m=>m.id===profile.value.selfMemberId)?.healthMemberId)
const question=ref(''),chatError=ref(''),messages=ref([]),task=ref({}),consentChecked=ref(false)
// 跨流式区和最终消息保留已出现餐次；历史读取默认不播放入场动画。
const mealAppearances=reactive({})
function rememberMealAppearance({requestId,key}){
  if(!requestId)return
  const seen=mealAppearances[requestId]||(mealAppearances[requestId]=[])
  if(!seen.includes(key))seen.push(key)
}
const localSend=ref(null),sendPhase=ref('')
const voiceMode=ref(false),voiceBusy=ref(false),voiceRef=ref(null),communityOpen=ref(false),scrollTarget=ref(''),inlineTodayOpen=ref(false)
const draftImage=ref(null),draftSaving=ref(false),draftError=ref('')
const keyboardFocused=ref(false)
const familyState=reactive(dailyArrangementState()),familyPanel=ref(false),familySelection=ref(null),familyIntent=ref('')
const mealPlanReady=ref(false),mealPlanAudience=ref('default')
const liveAnswer=computed(()=>!!task.value.streamText&&!task.value.result)
const progressText=computed(()=>sendPhase.value||(familyState.busy?'正在生成三餐':task.value.streamStatus||(['queued','pending'].includes(task.value.status)?'问题已收到，正在等待营养师处理':'正在准备回复')))
let scrollTimer=null,returnRetryTimer=null,returnRetryAttempt=0,entryRetryTimer=null,entryRetryAttempt=0,loginRedirecting=false,entryRecovery=null
function clearEntryRetry(reset=true){
 if(entryRetryTimer!==null)clearTimeout(entryRetryTimer)
 entryRetryTimer=null;if(reset)entryRetryAttempt=0
}
function requireLogin(){
 if(disposed||!visible||loginRedirecting)return
 loginRedirecting=true;clearPrivate();entryError.value=''
 uni.reLaunch({url:'/pages/index/index'})
}
function retryEntryInBackground(){
 if(disposed||!visible||loginRedirecting||entryRetryTimer!==null||entryRetryAttempt>=3)return
 const scope=storageContext(),mine=epoch,delay=1500*2**entryRetryAttempt++
 entryRetryTimer=setTimeout(()=>{
  entryRetryTimer=null
  if(!disposed&&visible&&mine===epoch&&scope===storageContext())void loadEntry(0,{skipOptional:true})
 },delay)
}
function reconnectEntry(event){
 if(!event.isConnected||disposed||!visible||loginRedirecting)return
 if(!entryReady.value)void load()
 else if(!returnVerified.value){returnRetryAttempt=0;void refreshReturn()}
}
function recoverEntry({resetConversation=false}={}){
 if(entryRecovery)return entryRecovery
 const draft={text:question.value,image:draftImage.value,error:draftError.value}
 const conversation={id:conversationId.value,thread:conversationThreadId.value,date:conversationBusinessDate.value}
 clearPrivate();pageScope=storageContext();flowScope=pageScope;historyDenied=false
 question.value=draft.text;draftImage.value=draft.image;draftError.value=draft.error
 if(resetConversation){
  // Do not resume the persisted pointer to the thread that just lost access.
  // Reserve a fresh local conversation; no server task or question is submitted.
  conversationId.value=newHealthRequestId()
 }else{conversationId.value=conversation.id;conversationThreadId.value=conversation.thread;conversationBusinessDate.value=conversation.date}
 const flight=loadEntry(0,{skipOptional:true})
 entryRecovery=flight
 return flight.finally(()=>{if(entryRecovery===flight)entryRecovery=null})
}
function clearReturnRetry(reset=true){
 if(returnRetryTimer!==null)clearTimeout(returnRetryTimer)
 returnRetryTimer=null;if(reset)returnRetryAttempt=0
}
function retryReturnInBackground(mine,scope){
 if(disposed||!visible||mine!==epoch||scope!==storageContext()||returnRetryAttempt>=3)return
 clearReturnRetry(false)
 const delay=Math.min(30000,1500*2**Math.min(returnRetryAttempt++,5))
 returnRetryTimer=setTimeout(()=>{
  returnRetryTimer=null
  if(!disposed&&visible&&mine===epoch&&scope===storageContext()&&!returnVerified.value)void refreshReturn()
 },delay)
}
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
const activePlanStatus=status=>['queued','dispatched','pending','running','recovering','cancel_requested'].includes(status)
const planRunning=computed(()=>activePlanStatus(todayPlan.value?.pending?.status)||task.value.taskType==='reference_meal_preview'&&referenceSelection?.plan_date===localDate()&&activePlanStatus(task.value.status))
const historyOpen=ref(false),conversationId=ref(''),conversationThreadId=ref(''),conversationBusinessDate=ref(''),switchingConversation=ref(false)
const historyLoading=ref(false),historyError=ref(''),historyNotice=ref(''),continuationChecking=ref(false),continuationError=ref('')
let selectionGeneration=0,historyDenied=false
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
function messageDeliveryStatus(next,accepted=true){
  if(next.status==='提交中'&&next.busy)return 'sending'
  if(next.readUnavailable)return 'unavailable'
  if(next.submitUnknown)return 'unknown'
  if(['failed','rejected','interrupted','cancelled'].includes(next.status))return next.status
  return accepted?'sent':'failed'
}
function hasMessageIssue(message){return message.role==='user'&&['failed','rejected','interrupted','unavailable'].includes(message.status)}
const visibleMessages=computed(()=>messages.value
  .filter(m=>m.role==='user'||!m.error&&(!failedTask.value||m.requestId!==task.value.requestId))
  .map(m=>m.role==='user'&&m.requestId&&m.requestId===task.value.requestId&&(task.value.status||task.value.submitUnknown)
    ?{...m,status:messageDeliveryStatus(task.value)}:m))
const taskMessageIssue=computed(()=>(task.value.readUnavailable||task.value.submitUnknown||['failed','rejected','interrupted','提交中'].includes(task.value.status))&&visibleMessages.value.some(m=>(hasMessageIssue(m)||m.role==='user'&&m.status==='unknown')&&(!task.value.requestId||m.requestId===task.value.requestId)))
const presentation=computed(()=>chatPresentation({route:props.route,hasMessages:visibleMessages.value.length>0,
  hasSavedArrangement:state.phase==='ready',newConversation:newConversationWelcome.value,
  preparedThreadId:preparedThreadId.value,currentThreadId:task.value.entry?.thread_id,
  loading:false}))
const failureText={answer_unavailable:'本次答复读取失败，原问题已保留，可以编辑后重试。',planner_output_invalid:'本次餐单结果无法核对，原问题已保留，可以编辑后重试。',planner_receipt_invalid:'本次餐单回执无法核对，原问题已保留，可以编辑后重试。',request_rejected:'本次消息未被接受，原问题已保留，可以编辑后重试。',budget_price_unavailable:'营养咨询服务的计费配置尚未就绪，请联系管理员。原问题已保留。',budget_exceeded:'本月健康 AI 可用额度不足或待核账，请稍后再试。原问题已保留。',answer_finalization_required:'答复准备未能完成，请编辑原问题后再试。',answer_stream_empty:'本次未生成有效答复，请编辑原问题后再试。',answer_stream_tool_call:'答复生成未能完成，请编辑原问题后再试。',catalog_tool_required:'商品查询未完成，请稍后再试。',catalog_selection_required:'商品选择未完成，请稍后再试。',execution_cancelled:'本次处理已取消。',execution_interrupted:'本次处理已中断，可稍后重新发送。'}
const pendingEntrySend=ref(null)
const chatBusy=computed(()=>historyLoading.value||switchingConversation.value||continuationChecking.value||!!continuationError.value||!!historyError.value||!entryReady.value||!returnVerified.value||profileLoading.value||!!pendingEntrySend.value||sending.value||familyState.busy||task.value.busy||task.value.loading||task.value.submitUnknown||['queued','dispatched','pending','running','recovering','cancel_requested'].includes(task.value.status))
const inputBusy=computed(()=>historyLoading.value||switchingConversation.value||continuationChecking.value||!!continuationError.value||!!historyError.value||conversationReadOnly.value||!!task.value.invalidated||!!pendingEntrySend.value)
const sendBlocked=computed(()=>inputBusy.value||sending.value||draftSaving.value||!!draftError.value||familyState.busy||task.value.busy||task.value.submitUnknown||['queued','dispatched','pending','running','recovering','cancel_requested'].includes(task.value.status)||(entryReady.value&&task.value.loading))
const conversationChangeBusy=computed(()=>sending.value||task.value.busy||task.value.submitUnknown||['queued','dispatched','pending','running','recovering','cancel_requested'].includes(task.value.status))
const sending=ref(false),hasDraftContent=computed(()=>!!question.value.trim()||!!draftImage.value)
// 页面恢复和历史读取只约束操作，不作为营养师正在回复的依据。
const replyPending=computed(()=>!!pendingEntrySend.value||sending.value||familyState.busy||!!task.value.requestId&&!task.value.submitUnknown&&activePlanStatus(task.value.status))
const retryBusy=computed(()=>sending.value||switchingConversation.value||!entryReady.value||task.value.busy||task.value.loading||task.value.refreshing)
const canCancel=computed(()=>task.value.requestId&&!task.value.submitUnknown&&['queued','dispatched','pending','running','recovering','cancel_requested'].includes(task.value.status))
const preparingSend=computed(()=>sending.value&&!!localSend.value&&!localSend.value.submitting)
// 未确认标记也保护正在发送的请求；只有发送结束后才显示待核对状态。
const submitting=computed(()=>task.value.submitUnknown&&task.value.status==='提交中'&&task.value.busy)
const readingSuspended=computed(()=>detailOpen.value||historyOpen.value||inlineTodayOpen.value||communityOpen.value)
const primaryMode=computed(()=>pendingEntrySend.value||submitting.value?'submitting':task.value.submitUnknown||task.value.readUnavailable?'check':task.value.cancelPhase==='unknown'?'check':['requesting','confirming'].includes(task.value.cancelPhase)||task.value.status==='cancel_requested'?'stopping':preparingSend.value||canCancel.value?'stop':voiceMode.value?'keyboard':hasDraftContent.value?'send':'voice')
const canCheckTask=computed(()=>!disposed&&visible&&flowScope===storageContext()&&returnVerified.value&&!task.value.invalidated&&!!task.value.requestId&&(task.value.submitUnknown||task.value.readUnavailable||task.value.cancelPhase==='unknown')&&!retryBusy.value)
async function checkTaskStatus(){if(canCheckTask.value)await flow.refresh()}
const recoveryNotice=computed(()=>{
  if(task.value.cancelPhase==='error')return task.value.cancelError||'停止未成功，可以重试。'
  if(chatBusy.value||liveAnswer.value||taskMessageIssue.value||failedTask.value)return ''
  return task.value.error||task.value.notice||''
})
watch(question,()=>{textVersion++},{flush:'sync'})
function markDraftInput(){textVersion++}
function captureDraft(){return {scope:storageContext(),conversation:conversationId.value,text:question.value,textVersion,imageVersion:draftVersion,path:draftImage.value?.localPath||draftImage.value?.path||''}}
function settleDraft(snapshot){
 if(!snapshot||snapshot.scope!==storageContext()||snapshot.conversation!==conversationId.value||snapshot.requestId&&snapshot.requestId!==task.value.requestId)return
 if(snapshot.textVersion===textVersion&&question.value===snapshot.text){question.value='';uni.hideKeyboard?.()}
 if(snapshot.path&&snapshot.imageVersion===draftVersion&&(draftImage.value?.localPath||draftImage.value?.path)===snapshot.path)removeDraft()
}
function failLocalSend(operation=localSend.value){
 if(operation?.message?.status==='cancelled')return
 // A failed local preparation may restore only the untouched composer it cleared.
 if(!operation||disposed||operation.scope!==storageContext()||operation.epoch!==epoch||operation.generation!==sendGeneration||task.value.invalidated||!messages.value.includes(operation.message)||operation.message.requestId&&task.value.submitUnknown)return
 operation.message.status='failed'
 if(question.value===''&&textVersion===operation.clearedVersion)question.value=operation.message.text
}
function stopQuestion(){
 if(!preparingSend.value)return flow.cancelRequest()
 const operation=localSend.value
 if(!operation||disposed||!visible||operation.scope!==storageContext()||operation.epoch!==epoch||operation.generation!==sendGeneration)return
 // No AI request exists yet. Invalidate both preparation and its late reads;
 // an empty conversation may finish creating, but this question cannot submit.
 operation.message.status='cancelled'
 epoch++;sendGeneration++;localSend.value=null;sendPhase.value='';pendingUser=null;submittedDraft=null
 sending.value=false;restoring=false;chatError.value='';flow.pause()
}
function rememberReading(value){if(!readingSuspended.value){reading.value=value;if(value.following)latestAvailable.value=false;else{scrollRevision++;scrollTarget.value=''}}}
watch(readingSuspended,locked=>{scrollRevision++;if(locked)reading.value={...reading.value,following:false}},{flush:'sync'})
function canRetryMessage(message){
 return !disposed&&visible&&flowScope===storageContext()&&returnVerified.value&&message.role==='user'&&message.status==='unknown'&&!!message.requestId&&message.requestId===task.value.requestId&&task.value.submitUnknown&&task.value.canRetry&&!retryBusy.value
}
function messageStatus(message){
 const copy={cancelled:'本次已停止，未生成完整回复。',failed:'本次处理失败，可编辑原问题后重试。',rejected:'本次请求未被接受，请核对资料后重试。',interrupted:'本次处理已中断，可编辑原问题后重试。',unknown:'提交结果待确认，请先核对原任务，避免重复发送。'}
 const retryable=canRetryMessage(message),scope=storageContext(),ticket=epoch,conversation=conversationId.value
 const reason=typeof failureText[message.errorCode]==='string'?failureText[message.errorCode]:''
 const checkable=message.status==='unavailable'&&message.requestId===task.value.requestId&&canCheckTask.value
 const editable=message.status!=='unavailable'&&hasMessageIssue(message)&&(!!message.text||!!message.image)&&!voiceBusy.value&&!chatBusy.value&&!conversationReadOnly.value&&!hasDraftContent.value&&!draftSaving.value
 uni.showModal({title:'消息状态',content:checkable?'暂时无法读取本次回复，系统仍在自动恢复。可以立即重新读取，无需重复发送。':retryable?'提交结果尚未确认，正在自动核对。也可以使用原请求重试提交。':reason||copy[message.status]||'这条消息尚未完成。',
  showCancel:checkable||retryable||editable,confirmText:checkable?'重新读取':retryable?'重试原问题':editable?'编辑问题':'知道了',...(retryable?{cancelText:'继续等待'}:editable?{cancelText:'取消'}:{}),
  success:result=>{
   if(!result.confirm||disposed||!visible||scope!==storageContext()||ticket!==epoch||conversation!==conversationId.value)return
   if(checkable&&message.requestId===task.value.requestId&&canCheckTask.value)void checkTaskStatus()
   else if(retryable&&canRetryMessage(message))void retryQuestion()
   else if(editable&&!voiceBusy.value&&!chatBusy.value&&!conversationReadOnly.value&&!hasDraftContent.value&&!draftSaving.value){
    question.value=message.text||'';draftVersion++;draftImage.value=message.image?{...message.image}:null;draftError.value='';voiceMode.value=false
   }
  }})
}
let disposed=false,visible=true,loading=null,epoch=0,pageScope=storageContext(),flowScope=pageScope,draftVersion=0,sendGeneration=0,openingCamera=false,pendingUser=null,submittedDraft=null,desiredType='consultation',restoring=false,suspended=false,loadedDate='',startNewHandled=false
// UI lifecycle is independent from request epochs and session restoration.
const entryView=ref({phase:'home',engaged:false,generation:0})
const textFocusRequested=ref(false),inputFocused=ref(false),composerIntent=ref(false),cameraPending=ref(false)
const keyboardView=ref({height:0,offsetTop:0,keyboardOpen:false,homeHeight:0})
watch(()=>keyboardView.value.height,()=>{if(reading.value.following)queueScroll()})
let intentTimer,blurTimer,intentGeneration=0
const entryBlocked=computed(()=>!!(historyLoading.value||historyError.value||historyNotice.value||continuationChecking.value||continuationError.value||detailOpen.value||historyOpen.value||props.route.taskType||presentation.value.initialResults||failedTask.value||onboardingPending.value||entryError.value||chatError.value||familyPanel.value||inlineTodayOpen.value||communityOpen.value||task.value.error||task.value.notice||task.value.canRetry||task.value.invalidated||task.value.consentOption||task.value.result?.type==='needs_input'||needsProfileLink.value))
const entryContext=computed(()=>({
  eligible:entryReady.value&&presentation.value.welcome&&!entryBlocked.value,
  hasMessages:messages.value.length>0,hasDraft:hasDraftContent.value||!!draftError.value,
  blocked:entryBlocked.value,busy:chatBusy.value||voiceBusy.value||draftSaving.value||cameraPending.value,
  focused:inputFocused.value||textFocusRequested.value,keyboardOpen:keyboardView.value.keyboardOpen,
  voiceMode:voiceMode.value,intent:composerIntent.value,
}))
const entryMotion=createChatEntryTransition({read:()=>entryContext.value,onChange:value=>{entryView.value=value}})
let keyboardPlatform='native',keyboardBrowser
// #ifdef H5
keyboardPlatform='h5';keyboardBrowser=typeof window==='undefined'?undefined:window
// #endif
const keyboardLayout=createChatKeyboardLayout({platform:keyboardPlatform,api:uni,browser:keyboardBrowser,onChange:value=>{keyboardView.value=value}})
const viewportStyle=computed(()=>keyboardView.value.height>0?{height:keyboardView.value.height+'px',...(keyboardPlatform==='h5'?{position:'fixed',top:keyboardView.value.offsetTop+'px',left:'0',right:'0'}:{})}:{})
const welcomeMounted=computed(()=>entryView.value.phase==='leaving'||entryView.value.phase==='home'&&entryContext.value.eligible)
const welcomeDensity=computed(()=>keyboardView.value.homeHeight>0?(keyboardView.value.homeHeight<=660?'small':keyboardView.value.homeHeight<=720?'medium':'large'):'')
watch(entryContext,()=>entryMotion.reconcile())
watch(()=>entryView.value.phase,phase=>keyboardLayout.freeze(phase!=='home'))
function handleInputFocus(event){
  clearTimeout(blurTimer);entryMotion.enter();inputFocused.value=true;keyboardLayout.focus(true)
  // Focus can carry the first keyboard height before the global height callback.
  const height=Number(event?.detail?.height ?? event?.height)
  if(Number.isFinite(height)&&height>0)keyboardLayout.keyboard({height})
}
function handleInputBlur(){
  textFocusRequested.value=false;keyboardLayout.focus(false);clearTimeout(blurTimer)
  // Blur may precede a send/camera click. Let that intent settle first.
  blurTimer=setTimeout(()=>{inputFocused.value=false;entryMotion.reconcile()},120)
}
function handleKeyboardHeightChange(event){keyboardLayout.keyboard(event)}
function holdComposerIntent(){
  if(chatBusy.value||voiceBusy.value||draftSaving.value)return
  clearTimeout(intentTimer);composerIntent.value=true
  const ticket=++intentGeneration
  intentTimer=setTimeout(()=>{if(ticket===intentGeneration)composerIntent.value=false},800)
}
function releaseComposerIntent(){clearTimeout(intentTimer);intentGeneration++;composerIntent.value=false}
function settleComposerPress(){
  clearTimeout(intentTimer)
  const ticket=++intentGeneration
  intentTimer=setTimeout(()=>{if(ticket===intentGeneration)composerIntent.value=false},120)
}
function resumeEntryUI(){cameraPending.value=false;keyboardLayout.start();entryMotion.resume()}
function pauseEntryUI(){clearTimeout(blurTimer);releaseComposerIntent();entryMotion.pause();inputFocused.value=false;textFocusRequested.value=false;keyboardLayout.stop()}
function resetEntryUI(){clearTimeout(blurTimer);releaseComposerIntent();inputFocused.value=false;textFocusRequested.value=false;cameraPending.value=false;entryMotion.reset()}
const flow=createHealthTaskFlow({daily:true,onChange:next=>{
  if(!disposed&&visible&&next.invalidated&&Number(next.failureStatus)===401&&(!getSession()?.token||flowScope===storageContext())){requireLogin();return}
  if(disposed||flowScope!==storageContext()||historyDenied)return
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
  if(next.invalidated){
    if(continuationChecking.value&&next.taskType==='reference_meal_preview'&&next.invalidatedThreadId){
      messages.value=messages.value.filter(m=>m.threadId!==next.invalidatedThreadId)
      continuationError.value='关联餐单的授权或来源已变化，请重新核对。'
    }else{
      historyDenied=true;messages.value=[];submittedDraft=null;pendingUser=null
      if(!restoring&&!returning.value){
        const mine=epoch,scope=storageContext()
        void Promise.resolve().then(()=>{if(!disposed&&visible&&mine===epoch&&scope===storageContext())return recoverEntry({resetConversation:true})})
      }
    }
    return
  }
  if(pendingUser&&next.requestId){pendingUser.requestId=next.requestId;pendingUser.localOnly=false;pendingUser.status=next.status||'sending';sendPhase.value=''}
  if(submittedDraft&&!submittedDraft.requestId&&pendingUser&&next.requestId)submittedDraft.requestId=next.requestId
  if(next.submitUnknown&&next.requestId&&!messages.value.some(m=>m.role==='user'&&m.requestId===next.requestId)){
    messages.value.push({threadId:next.entry?.thread_id||conversationThreadId.value,id:'pending-'+next.requestId,role:'user',requestId:next.requestId,text:next.pendingText||'',status:'unknown',...(next.pendingImages?.[0]?{image:{localPath:next.pendingImages[0]}}:{})})
  }
  const outgoing=messages.value.find(m=>m.role==='user'&&m.requestId===next.requestId)
  if(outgoing){
    outgoing.status=messageDeliveryStatus(next)
    outgoing.threadId=next.entry?.thread_id||outgoing.threadId
    if(next.result?.type==='error')outgoing.errorCode=next.result.code
    if(!next.submitUnknown&&next.status!=='提交中'&&!['failed','rejected','interrupted'].includes(next.status)&&submittedDraft?.requestId===next.requestId){
      settleDraft(submittedDraft)
      submittedDraft=null
    }
  }
  if(next.result&&next.requestId&&!(next.result.type==='error'&&!props.route.taskType)){
    const id=next.requestId+'-answer',index=messages.value.findIndex(m=>m.requestId===next.requestId&&m.role==='assistant')
    const result=next.result
    if(result.type==='business'&&isReferencePlan(result.data)){
      latestReference.value=result.data
    }
    const message={threadId:next.entry?.thread_id||conversationThreadId.value,id:messages.value[index]?.id||id,serverMessageId:next.finalMessageId,requestId:next.requestId,role:'assistant',createdAt:messages.value[index]?.createdAt||new Date().toISOString(),citations:result.citations||[],
      text:result.type==='answer'?result.text:result.type==='needs_input'?result.questions.join('\n'):result.type==='error'?(failureText[result.code]||'这次处理未能完成，请重新读取或编辑问题后再试。'):isReferencePlan(result.data)?'餐单已更新。':'餐单结果已返回，请核对后决定是否使用。',
      memberId:next.memberId,recordedMeals:continuationChecking.value&&!result.recordedMeals?.length?(messages.value[index]?.recordedMeals||[]):result.recordedMeals||messages.value[index]?.recordedMeals||[],mealEnter:messages.value[index]?.mealEnter??(index<0&&!restoring&&!returning.value&&visible),purchaseEnter:index<0&&!restoring&&!returning.value,purchaseOffers:result.purchaseOffers,purchaseRequestId:result.purchaseOffers?.length?next.requestId:'',error:result.type==='error',errorCode:result.code,retryable:result.retryable===true,business:result.type==='business'?result:null,planDate:isReferencePlan(result.data)?result.data.plan_date:'',planMeals:isReferencePlan(result.data)?(result.data.meals||[]).map(meal=>meal.meal_type):undefined}
    if(index<0)messages.value.push(message);else messages.value[index]={...messages.value[index],...message}
    if(!restoring&&!returning.value&&visible)void scrollLatest()
  }
  if(next.requestId&&Array.isArray(next.recordedMeals)&&(!continuationChecking.value||next.recordedMeals.length)){
    const turns=messages.value.filter(row=>row.requestId===next.requestId)
    for(const row of turns)row.recordedMeals=[]
    const target=turns.find(row=>row.role==='assistant')||turns.find(row=>row.role==='user')
    if(target)target.recordedMeals=next.recordedMeals
  }
}})
const client=createDailyArrangementClient({state,send:request,context:()=>({scope:storageContext(),familyId:getSession()?.householdId}),storage:scopedStorage,newId:newHealthRequestId,beforeStart:requirePlanningReady})
const familyClient=createDailyArrangementClient({state:familyState,send:request,context:()=>({scope:storageContext(),familyId:getSession()?.householdId}),storage:scopedStorage,newId:newHealthRequestId,beforeStart:requirePlanningReady})
function updateMealReceipt(record){
  for(const message of messages.value){
    if(message.recordedMeals?.some(row=>row.id===record.id))message.recordedMeals=message.recordedMeals.map(row=>row.id===record.id?record:row)
  }
}
function requirePlanningReady(){
  const capability=profile.value?.healthConfiguration?.meal_plan
  if(capability?.available===false)throw Object.assign(new Error('营养服务暂未就绪：'+(capability.reason||'请先完成服务配置')+'。配置完成后重新读取即可。'),{businessCode:'daily_dependencies_not_ready',retryable:false})
  const diners=profile.value?.defaultDiners
  if(diners?.some(id=>profile.value.members.some(member=>member.id===id && !member.healthMemberId && member.claimed===true && member.relation!=='本人')))throw Object.assign(new Error('有已认领的家人尚未完成健康资料关联，请让该成员登录后确认自己的资料和分析授权，或在家庭档案中调整默认就餐成员。'),{businessCode:'daily_member_consent_required',retryable:false})
  if(diners?.length && diners.some(id=>!profile.value.members.find(member=>member.id===id)?.healthMemberId))throw Object.assign(new Error('请在家庭档案中选择尚未确认的就餐成员，核对资料并明确同意对应分析。'),{businessCode:'daily_member_sources_unavailable',retryable:false})
}
async function familyPlan(text,retry=false){
  text=retry?familyIntent.value:String(text||'');if(!retry)familyIntent.value=text
  const scope=storageContext(),mine=epoch,snapshot=captureDraft()
  const intent=parseChatMealIntent(text,localDate())
  if(!intent)return
  familyPanel.value=true;mealPlanReady.value=false;mealPlanAudience.value=intent.audience
  const isCurrent=()=>!disposed&&visible&&mine===epoch&&scope===storageContext()
  const arrangement=await loadChatMealPlan(intent,{client:familyClient,state:familyState,profile:profile.value,isCurrent,retry})
  if(!isCurrent())return
  mealPlanReady.value=!!arrangement
  if(!arrangement){chatError.value=familyState.error||'餐单仍在处理中，请继续读取本次安排。';return}
  if(snapshot.text.trim()===text)settleDraft(snapshot)
  if(state.date===intent.date){await client.load(intent.date);if(!isCurrent())return;cardVisible.value=state.phase==='ready'}
  await scrollLatest()
}
async function familyMembers(ids){
  const choice=familySelection.value;familySelection.value=null;if(!choice)return
  const scope=storageContext(),mine=epoch,snapshot=captureDraft();await familyClient.changeMembers(choice.type,ids)
  if(disposed||!visible||mine!==epoch||scope!==storageContext())return
  if(!familyState.error&&familyState.date===state.date){await client.load(state.date);if(disposed||!visible||mine!==epoch||scope!==storageContext())return}
  if(!familyState.error&&snapshot.text.trim()===choice.question)settleDraft(snapshot)
}
function openFamilyMeal(meal){openFormalDetail(meal,familyState.arrangement,familyState.date)}
/** 自动跟随只作用于当前对话；每次渲染等待后重新检查阅读状态。 */
async function scrollLatest({force=false}={}){
 const mine=++scrollRevision,scope=storageContext(),conversation=conversationId.value
 const valid=()=>!disposed&&visible&&mine===scrollRevision&&scope===storageContext()&&conversation===conversationId.value&&!readingSuspended.value&&(force||reading.value.following)
 if(!valid()){if(!disposed&&visible)latestAvailable.value=true;return}
 if(force){reading.value={...reading.value,following:true};latestAvailable.value=false}
 await nextTick();if(!valid())return
 scrollTarget.value=''
 await nextTick();if(!valid())return
 scrollTarget.value='chat-bottom-anchor';latestAvailable.value=false
}
function queueScroll(){
 if(disposed||!visible||!messages.value.length&&!liveAnswer.value)return
 if(readingSuspended.value||!reading.value.following){latestAvailable.value=true;return}
 if(scrollTimer!==null)return
 scrollTimer=setTimeout(()=>{scrollTimer=null;void scrollLatest()},180)
}

function stopPlanTimers(){Object.values(planTimers).forEach(timer=>clearTimeout(timer));planTimers={};planPolls={}}
function clearPrivate(){clearEntryRetry(false);selectionGeneration++;historyDenied=false;historyLoading.value=false;historyError.value='';historyNotice.value='';continuationChecking.value=false;continuationError.value='';pendingEntrySend.value=null;for(const key of Object.keys(mealAppearances))delete mealAppearances[key];clearReturnRetry();localSend.value=null;sendPhase.value='';scrollRevision++;latestAvailable.value=false;detailRef.value?.clear();resetEntryUI();onboardingPending.value=false;inlineTodayOpen.value=false;historyOpen.value=false;conversationId.value='';conversationThreadId.value='';conversationBusinessDate.value='';conversationDrafts.clear();entryReady.value=false;returnVerified.value=false;returning.value=false;returnError.value='';prompts.value=[];promptDate.value='';mealsLoading.value=false;mealReadError.value='';latestReference.value=null;dailyPlans.value={};stopPlanTimers();referenceSelection=null;refreshedTerminal='';newConversationWelcome.value=false;preparedThreadId.value='';epoch++;sendGeneration++;sending.value=false;loading=null;profileLoading.value=false;flow.hide();client.reset();familyClient.reset();familyPanel.value=false;familySelection.value=null;messages.value=[];question.value='';chatError.value='';profile.value=null;task.value={};selectedMeal.value=null;removeDraft();pendingUser=null;submittedDraft=null;voiceRef.value?.cancel();voiceBusy.value=false;voiceMode.value=false;cardVisible.value=false}
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
async function restoreSpecialTask(legacy,{readHistory=true}={}){
  if(props.route.taskType||!conversationId.value||conversationReadOnly.value||task.value.invalidated||task.value.submitUnknown||
    ['queued','dispatched','pending','running','recovering','cancel_requested'].includes(task.value.status))return
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
  await restoreChat(saved.type,{readHistory})
  if(disposed||!visible||scope!==storageContext()||mine!==epoch||id!==conversationId.value||task.value.invalidated)return
  if(task.value.memberId===(saved.taskMemberId||saved.memberId)&&pointers.some(row=>row.thread_id===task.value.entry?.thread_id)&&
    (!saved.requestId||task.value.requestId===saved.requestId)&&
    (task.value.result?.type==='needs_input'||task.value.submitUnknown||['queued','dispatched','pending','running','recovering','cancel_requested'].includes(task.value.status))){
    desiredType=saved.type;return
  }
  scopedStorage.setStorageSync(key,null);referenceSelection=null
  await restoreChat('consultation',{readHistory})
}
function visibleConversationMessage(message,explicit){
  if(!message.createdAt)return true
  if(explicit&&!conversationBusinessDate.value||props.route.taskType)return true
  return chatBusinessDate(message.createdAt)===(conversationBusinessDate.value||localDate())
}
async function restoreChat(type=desiredType,{fresh=false,pending=null,preserveView=false,readHistory=true,verifyEntry=false}={}){
  if(!profile.value)return
  const scope=storageContext(),ticket=epoch
  if(type==='reference_meal_preview'&&!referenceSelection)referenceSelection=chooseReference(profile.value,'今天三餐',{today:localDate(),tomorrow:localDate(new Date(Date.now()+86400000)),memberId:props.route.memberId})
  const anchor=type==='reference_meal_preview'?profile.value.members.find(m=>referenceSelection.participant_ids.includes(m.id)&&m.healthMemberId):null
  const id=pending?.member_id||anchor?.healthMemberId||props.route.memberId||profile.value.members.find(m=>m.id===profile.value.selfMemberId)?.healthMemberId
  const capability=profile.value.healthConfiguration?.[['meal_preview','reference_meal_preview'].includes(type)?'meal_plan':type]
  if(capability?.available===false){
    flow.hide();task.value={}
    if(verifyEntry)throw Object.assign(new Error('咨询连接暂不可用'),{code:'CONSULTATION_UNAVAILABLE'})
    chatError.value='营养服务暂未就绪：'+(capability.reason||'请先完成服务配置')+'。配置完成后重新读取即可。';return
  }
  if(!id){
    flow.hide();task.value={}
    if(verifyEntry)throw Object.assign(new Error('咨询连接尚未就绪'),{code:'CONSULTATION_MEMBER_PENDING'})
    chatError.value='咨询连接尚未就绪，请稍后再试。';return
  }
  const selection=type==='reference_meal_preview'?referenceSelection:type==='diet_analysis'?{record_id:props.route.recordId,source_version:Number(props.route.version)}:props.route.indicatorChoice==='1'?scopedStorage.getStorageSync(`indicator-choice:${id}:${type}`):null
  flowScope=scope;restoring=true
  try{
    const options=!props.route.taskType&&conversationId.value?{conversationId:conversationId.value,...(type==='consultation'&&conversationThreadId.value?{threadId:conversationThreadId.value}:type==='reference_meal_preview'&&conversationThreadId.value?{rootThreadId:conversationThreadId.value}:{})}:undefined
    await flow.open(id,type,selection,{...options,fresh})
    if(verifyEntry&&!task.value.available&&!task.value.invalidated&&!task.value.consentOption){
      throw Object.assign(new Error('咨询连接暂不可用'),{code:'CONSULTATION_UNAVAILABLE'})
    }
    if(pending&&!await flow.restoreReferenceRequest(pending.thread_id,pending.request_id))throw new Error('当前问题无法恢复，请重新读取。')
    if(disposed||ticket!==epoch||scope!==storageContext())return
    if(task.value.entry?.thread_id){
      rememberThread({migrateLegacy:!options})
      if(!readHistory)return
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
      const live=messages.value.filter(m=>m.localOnly||m.requestId===task.value.requestId&&(m.status==='unknown'||m.role==='assistant'&&task.value.result))
      messages.value=[...saved,...live.filter(m=>!saved.some(row=>row.id===m.id||m.requestId&&row.requestId===m.requestId&&row.role===m.role))]
      rememberThread()
      for(const date of new Set(saved.map(message=>message.planDate).filter(Boolean))){
        if(date!==localDate())void loadDailyPlan(profile.value.householdId,date,ticket,scope).catch(e=>{if(!disposed&&visible&&ticket===epoch&&scope===storageContext())mealReadError.value=e.message})
      }
      const active=snapshots.find(s=>s.threadId===currentThread)?.runs.find(r=>['queued','dispatched','pending','running','cancel_requested'].includes(r.status))
      if(active?.request_id&&!task.value.submitUnknown&&(!task.value.requestId||task.value.status==='queued'&&active.request_id!==task.value.requestId))await flow.restoreRequest(active.request_id,{preferActive:true})
      if(!preserveView)await scrollLatest()
    }else if(readHistory&&!task.value.requestId)messages.value=messages.value.filter(m=>m.localOnly)
  }catch(e){if(!disposed&&ticket===epoch&&scope===storageContext()){if(verifyEntry)throw e;chatError.value=e.message;if(readHistory&&[401,403,404,409,410].includes(Number(e.code))){messages.value=[];question.value='';removeDraft();submittedDraft=null}}}
  finally{if(ticket===epoch&&scope===storageContext())restoring=false}
}
function load(){
  if(disposed)return
  clearEntryRetry();loginRedirecting=false
  selectionGeneration++;historyDenied=false;historyLoading.value=false;historyError.value='';historyNotice.value='';continuationChecking.value=false;continuationError.value='';switchingConversation.value=false
  clearReturnRetry()
  visible=true
  resumeEntryUI()
  return loadEntry(0)
}
async function loadEntry(recoveries,{skipOptional=false}={}){
  if(!getSession()?.token){requireLogin();return}
  const preserveView=!!profile.value&&loadedDate===localDate()&&pageScope===storageContext()
  entryReady.value=false
  if(pageScope!==storageContext()){clearPrivate();pageScope=storageContext();flowScope=pageScope}
  if(loading)return loading
  historyDenied=false
  if(!prompts.value.length||promptDate.value!==localDate())refreshPrompts()
  const mine=++epoch,scope=storageContext(),account=getSession()
  entryError.value=''
  profileLoading.value=true
  async function recoverSession(){
    // Discard every result from the previous scope before a bounded reread.
    const current=getSession()
    const sameIdentity=current?.token&&current.accountId===account?.accountId&&(!account?.householdId||current.householdId===account.householdId)
    const draft=sameIdentity?{text:question.value,image:draftImage.value,error:draftError.value}:null
    clearPrivate();pageScope=storageContext();flowScope=pageScope
    if(draft){question.value=draft.text;draftImage.value=draft.image;draftError.value=draft.error}
    if(!current?.token||current.accountId!==account?.accountId||account?.householdId&&current.householdId!==account.householdId){
      requireLogin()
      return
    }
    if(recoveries>=1){entryError.value='连接暂不可用';retryEntryInBackground();return}
    return loadEntry(recoveries+1,{skipOptional})
  }
  loading=(async()=>{try{
    const next=await loadCloudProfile({openConsultation:true})
    if(disposed||!visible||mine!==epoch)return
    if(scope!==storageContext())return await recoverSession()
    profile.value=next
    onboardingPending.value=!!scopedStorage.getStorageSync('onboarding-preparation-pending')
    chatError.value=''
    if(props.route.question&&!question.value)question.value=String(props.route.question).slice(0,4000)
    if(props.route.indicatorChoice==='1'&&!question.value)question.value='请回顾我选择的实测记录，说明还需要补充哪些测量信息。'
    if(!next.completeProfile&&!next.onboarded){uni.redirectTo({url:'/pages/onboarding/index'});return}
    // A plain entry is the product home. Only an explicitly selected existing
    // conversation may recover the previous pointer or legacy daily task.
    const resumePrevious=props.route.entry==='conversation'||props.route.from==='onboarding'||!!props.route.preparation
    const resume=resumePrevious?scopedStorage.getStorageSync('homepage-chat-task'):null
    const selfId=next.members.find(m=>m.id===next.selfMemberId)?.healthMemberId
    const current=resumePrevious?scopedStorage.getStorageSync('homepage-conversation'):null
    if(!props.route.taskType&&!conversationId.value&&current&&current.memberId===selfId&&(!current.scope||current.scope===scope)){conversationId.value=current.id||'';conversationThreadId.value=current.threadId||'';conversationBusinessDate.value=current.businessDate||''}
    if(!props.route.taskType&&!conversationId.value&&!resumePrevious){
      // Reserve a local identity, without creating a server thread or replacing
      // the saved history selection. This also prevents the daily-thread fallback.
      conversationId.value=newHealthRequestId();newConversationWelcome.value=true
    }
    if(!props.route.taskType&&props.route.newConversation==='1'&&!startNewHandled){startNewHandled=true;conversationId.value=newHealthRequestId();conversationThreadId.value='';conversationBusinessDate.value='';newConversationWelcome.value=true;saveConversation(selfId)}
    desiredType=Object.hasOwn(HEALTH_TEXT_TASKS,props.route.taskType)?props.route.taskType:'consultation'
    latestReference.value=null;preparedThreadId.value=''
    const legacyReference=!conversationId.value&&resume?.memberId===selfId&&resume?.date===localDate()&&resume.type==='reference_meal_preview'&&resume.selection?.family_id===next.householdId
    if(legacyReference){referenceSelection=resume.selection;desiredType=resume.type}
    newConversationWelcome.value=!!conversationId.value&&!conversationThreadId.value
    await restoreChat(desiredType,{fresh:newConversationWelcome.value&&resume?.fresh===true,preserveView,verifyEntry:true})
    if(!disposed&&visible&&mine===epoch&&scope===storageContext()&&!props.route.taskType)await restoreSpecialTask(resume)
    if(disposed||!visible||mine!==epoch)return
    if(scope!==storageContext())return await recoverSession()
    if(task.value.invalidated){entryError.value='连接暂不可用';retryEntryInBackground();return}
    cardVisible.value=state.phase==='ready';entryReady.value=true;returnVerified.value=true;loadedDate=localDate()
    clearEntryRetry()
    rememberChatEntry(next)
    if(!prompts.value.length||promptDate.value!==localDate())refreshPrompts()
    if(!skipOptional)void loadOptionalMeals(next.householdId,mine,scope)
  }catch(e){
    if(disposed||!visible||mine!==epoch)return
    if(Number(e.code)===401||!getSession()?.token){requireLogin();return}
    if(scope!==storageContext())return await recoverSession()
    if(Number(e.code)===403){
      const text=question.value,image=draftImage.value,error=draftError.value
      clearPrivate();question.value=text;draftImage.value=image;draftError.value=error
    }
    entryError.value=e.message||'咨询资料暂时无法读取，请重试。'
    retryEntryInBackground()
  }
  finally{if(mine===epoch){loading=null;profileLoading.value=false}}})()
  return loading
}
function clearMealAccess(date){
  const plans={...dailyPlans.value};delete plans[date];dailyPlans.value=plans
  if(planTimers[date])clearTimeout(planTimers[date])
  delete planTimers[date];delete planPolls[date]
  if(state.date===date){cardVisible.value=false;client.reset();selectedMeal.value=null}
  if(familyState.date===date){familyClient.reset();familyPanel.value=false;familySelection.value=null}
  if(latestReference.value?.plan_date===date)latestReference.value=null
}
async function loadDailyPlan(familyId,date,mine,scope,{verifyAccess=true}={}){
  const ticket=(planReads[date]||0)+1;planReads[date]=ticket
  let plan
  try{plan=await readDailyMealPlan(familyId,date)}catch(error){
    if(!disposed&&visible&&mine===epoch&&planReads[date]===ticket){
      if(Number(error.code)===401||!getSession()?.token){requireLogin();throw error}
      if(scope===storageContext()){
        if([403,404,409,410].includes(Number(error.code)))clearMealAccess(date)
        if(Number(error.code)===403&&verifyAccess){mealsLoading.value=false;void refreshReturn({skipOptional:true})}
      }
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
  const results=await Promise.allSettled([readCurrentPreparation(),loadDailyPlan(familyId,date,mine,scope,{verifyAccess:false})])
  if(!current())return
  mealsLoading.value=false
  if(results.some(r=>r.status==='rejected'&&Number(r.reason?.code)===401)||!getSession()?.token){requireLogin();return}
  if(scope!==storageContext()){
    clearPrivate();pageScope=storageContext();flowScope=pageScope;void load()
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
  // A denied optional resource must not invalidate an otherwise authorized chat.
  // Recheck the core once, without immediately requesting the denied meals again.
  if(results.some(r=>r.status==='rejected'&&Number(r.reason?.code)===403))await refreshReturn({skipOptional:true})
}
async function refreshReturn({skipOptional=false}={}){
  if(disposed||!visible||!entryReady.value||returning.value)return
  clearReturnRetry(false)
  const mine=++epoch,scope=storageContext(),account=getSession();returning.value=true;returnVerified.value=false;returnError.value='';restoring=true
  const current=()=>{
    if(!disposed&&visible&&mine===epoch&&scope!==storageContext()&&pageScope===scope){
      const now=getSession()
      if(now?.token&&now.accountId===account?.accountId&&now.householdId===account?.householdId&&now.token!==account?.token){void recoverEntry();return false}
      requireLogin()
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
    if(task.value.invalidated){return await recoverEntry({resetConversation:true})}
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
        flow.invalidateThread();return await recoverEntry({resetConversation:true})
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
    clearReturnRetry()
    rememberChatEntry(next)
    if(!skipOptional)void loadOptionalMeals(next.householdId,mine,scope,{preserve:true})
  }catch(error){
    if(!current())return
    if(Number(error.code)===401||!getSession()?.token){requireLogin();return}
    if(Number(error.code)===403){return await recoverEntry()}
    returnError.value=error.message||'暂时无法更新咨询状态，请重新读取。'
    retryReturnInBackground(mine,scope)
  }finally{if(mine===epoch){returning.value=false;restoring=false}}
}
onMounted(()=>{keyboardLayout.start();uni.onNetworkStatusChange?.(reconnectEntry);void load()});onShow(()=>{
  if(disposed)return
  visible=true
  if(!suspended){resumeEntryUI();if(!entryReady.value)void load();return}
  suspended=false
  if(pageScope!==storageContext()){clearPrivate();pageScope=storageContext();flowScope=pageScope;void load();return}
  if(loadedDate&&loadedDate!==localDate()){
    const text=question.value,image=draftImage.value,error=draftError.value
    clearPrivate();question.value=text;draftImage.value=image;draftError.value=error;void load();return
  }
  resumeEntryUI()
  if(entryReady.value)void refreshReturn();else void load()
})
onHide(()=>{clearEntryRetry();entryRecovery=null;if(historyLoading.value||continuationChecking.value)entryReady.value=false;selectionGeneration++;historyLoading.value=false;continuationChecking.value=false;switchingConversation.value=false;clearReturnRetry();if(pendingEntrySend.value){messages.value=messages.value.filter(message=>message!==pendingEntrySend.value.message);pendingEntrySend.value=null}if(localSend.value?.message.localOnly)failLocalSend();localSend.value=null;sendPhase.value='';scrollRevision++;pauseEntryUI();historyOpen.value=false;if(scrollTimer!==null)clearTimeout(scrollTimer);scrollTimer=null;visible=false;suspended=true;epoch++;sendGeneration++;loading=null;profileLoading.value=false;returning.value=false;restoring=false;returnVerified.value=false;mealsLoading.value=false;stopPlanTimers();voiceRef.value?.cancel();flow.pause();pendingUser=null;sending.value=false;client.pause();familyClient.pause();familyPanel.value=false;familySelection.value=null})
onUnmounted(()=>{uni.offNetworkStatusChange?.(reconnectEntry);clearEntryRetry();entryRecovery=null;selectionGeneration++;clearReturnRetry();scrollRevision++;pauseEntryUI();entryMotion.dispose();if(scrollTimer!==null)clearTimeout(scrollTimer);disposed=true;epoch++;draftVersion++;stopPlanTimers();client.dispose();familyClient.dispose();flow.hide()})
async function openFormalDetail(meal,arrangement,date,extra={}){
 if(voiceBusy.value||!arrangement||!profile.value)return
 const scope=storageContext(),mine=epoch
 try{const plan=await loadDailyPlan(profile.value.householdId,date,mine,scope);if(!plan||scope!==storageContext()||mine!==epoch)return
 const item=plan.meals.find(item=>item.meal_type===meal.type&&item.source.kind==='formal'&&item.source.id===arrangement.id)
 if(!item)throw new Error('这餐已经更新，请从今日餐单重新打开。')
 if(extra.purchaseMeals?.length>1)return openMealPage({date:plan.date,version:plan.version},{all:true})
 return detailRef.value?.open({...mealTarget(item,plan),...extra})
 }catch(e){if(scope===storageContext())chatError.value=e.message}
}
function openMeal(meal){return openFormalDetail(meal,state.arrangement,state.date)}
function openDailyMeal(item,date){if(voiceBusy.value)return;openMealPage(mealTarget(item,dailyPlans.value[date]))}
function openDailyDish(value,date){if(voiceBusy.value)return;openMealPage(mealTarget(value.item,dailyPlans.value[date]),{dishIndex:value.dishIndex})}
function buyAllMeals(plan){if(voiceBusy.value||planPurchaseBusy.value||!canPurchaseAllMeals(plan))return;openMealPage({date:plan.date,version:plan.version},{all:true})}

async function openReferencePlan(value){
 const source=value.plan||value,meal=source.meals?.[0]
 if(!meal||!profile.value||voiceBusy.value)return
 const scope=storageContext(),mine=epoch
 try{const plan=await loadDailyPlan(profile.value.householdId,source.plan_date,mine,scope);if(!plan||scope!==storageContext()||mine!==epoch)return
 const item=plan.meals.find(item=>item.meal_type===meal.meal_type&&item.source.id===source.preview_id)
 if(!item)throw new Error('这餐已经更新，请从今日餐单重新打开。')
 return detailRef.value?.open({...mealTarget(item,plan),...(value.purchase?{initialView:'purchase'}:{})})
 }catch(e){if(scope===storageContext())chatError.value=e.message}
}
async function reloadDetailPlan(date){const plan=await loadDailyPlan(profile.value.householdId,date,epoch,storageContext());if(state.date===date)await client.load(date);if(familyPanel.value&&familyState.date===date)await familyClient.load(date);return plan}
function selectDailyMembers(item,date){return detailRef.value?.open({kind:'formal',familyId:profile.value.householdId,date,mealType:item.meal_type,sourceId:item.source.id,version:item.source.version,dailyPlanVersion:dailyPlans.value[date].version,seed:{...item.meal,members:item.members||[]},initialView:'members'})}
function purchaseDaily(option,plan){
 const item=plan.meals.find(item=>item.source.id===option.id&&item.source.kind===option.kind)
 if(!item||voiceBusy.value)return
 return detailRef.value?.open({kind:option.kind,familyId:profile.value.householdId,date:plan.date,mealType:item.meal_type,sourceId:option.id,version:item.source.version||option.version,dailyPlanVersion:plan.version,seed:{...item.meal,members:item.members||[]},purchaseOption:option,initialView:'purchase',...(option.kind==='formal'?{purchaseMeals:option.meal_types||plan.meals.filter(i=>i.source.id===option.id).map(i=>i.meal_type),purchaseMembers:[...new Map(plan.meals.flatMap(i=>i.members||[]).map(m=>[m.id,m])).values()]}:{})})
}
function shop(arrangement){if(arrangement?.meals?.length)return openFormalDetail(arrangement.meals[0],arrangement,arrangement.date,{initialView:'purchase',purchaseMeals:arrangement.meals.map(m=>m.type),purchaseMembers:[...new Map(arrangement.meals.flatMap(m=>m.members||[]).map(m=>[m.id,m])).values()]})}
function archives(){uni.navigateTo({url:'/pages/profile/index'})}
async function members(ids){const type=selectedMeal.value.type,dailyPlanVersion=selectedMeal.value.dailyPlanVersion;selectedMeal.value=null;await client.changeMembers(type,ids,{dailyPlanVersion});cardVisible.value=state.phase==='ready';if(profile.value)await loadDailyPlan(profile.value.householdId,state.date,epoch,storageContext());if(familyPanel.value&&familyState.date===state.date)await familyClient.load(state.date)}
async function sendQuestion(promptAction=''){
  if(conversationReadOnly.value){chatError.value='这段每日对话已归档，请新建对话继续。';return}
  if(!hasDraftContent.value||draftSaving.value||draftError.value||pendingEntrySend.value||inputBusy.value)return
  if(!entryReady.value||!returnVerified.value){
    const pending=reactive({scope:storageContext(),text:question.value,image:draftImage.value,message:reactive({id:newHealthRequestId(),role:'user',text:question.value.trim(),createdAt:new Date().toISOString(),status:'sending',localOnly:true,...(draftImage.value?{image:{...draftImage.value}}:{})})})
    pendingEntrySend.value=pending;messages.value.push(pending.message)
    const flight=loading||loadEntry(0,{skipOptional:true});pending.ticket=epoch
    try{
      await flight
      if(pendingEntrySend.value!==pending||disposed||!visible||pending.scope!==storageContext()||pending.ticket!==epoch)return
      if(!entryReady.value||!returnVerified.value){
        const reason=task.value.notice||profile.value?.consultationError||returnError.value||entryError.value
        chatError.value=reason&&reason!=='咨询连接暂不可用'&&reason!=='连接暂不可用'?reason+'；问题已保留。':'咨询服务尚未就绪，问题已保留，请稍后重试。'
        uni.showToast({title:chatError.value,icon:'none',duration:3500})
        return
      }
      if(question.value!==pending.text||draftImage.value!==pending.image)return
      messages.value=messages.value.filter(message=>message!==pending.message)
      pendingEntrySend.value=null
      return await sendQuestion(promptAction)
    }finally{
      if(pendingEntrySend.value===pending){messages.value=messages.value.filter(message=>message!==pending.message);pendingEntrySend.value=null}
    }
  }
  if(!hasDraftContent.value||chatBusy.value||draftSaving.value||draftError.value)return
  if(!profile.value){chatError.value=entryError.value||'咨询资料尚未读到，请重新读取咨询资料后再发送。';return}
  entryMotion.enter();releaseComposerIntent()
  const scope=storageContext(),mine=epoch,sendTicket=++sendGeneration,text=question.value.trim(),image=draftImage.value&&{...draftImage.value},snapshot=captureDraft()
  sending.value=true;chatError.value=''
  let stage='select-task',user=null,localOperation=null
  try{
    const mealIntent=!props.route.taskType&&!image?parseChatMealIntent(text,localDate()):null
    // A revision stays in the selected plan's thread, preserving its date and
    // participants. A fresh arrangement still creates its own explicit choice.
    const referenceAdjustment=!props.route.taskType&&!image&&task.value.taskType==='reference_meal_preview'&&!!referenceSelection&&
      !(promptAction==='consultation'&&!mealIntent)&&
      !isMealPlanningCancelled(text)&&
      !/(?:什么是|介绍|解释|科普|原则|注意事项|怎么理解|如何理解|有什么区别|有何区别)/.test(text)&&
      !(!mealIntent&&/(?:怎么|怎样|如何|为什么).*(?:选|做|换|替换|调整|搭配|准备|保存|作用|摄入)|(?:有什么|有何)(?:好处|作用)/.test(text))&&
      !/(?:换(?:个|一个)?话题|换个问题|^(?:取消|停止|不用了|不需要了)(?:[，。！？\s]|$)|(?:取消|停止|不用|不需要|不想|不要)(?:再|继续)?(?:配餐|安排|生成|制定))/.test(text)&&
      (task.value.result?.type==='needs_input'||!/(?:^|[，。！？；、\s])(?:请)?(?:为我|给我|帮我|给全家|为全家|帮全家)?(?:安排|生成|制定|配一)/.test(text)&&
      /换(?:(?:今天|明天|今日|明日)?的?(?:早餐|午餐|晚餐|早饭|午饭|晚饭)|菜|成|掉|一|个)|替换|改(?:成|为|一下|早餐|午餐|晚餐|早饭|午饭|晚饭)|调整|重新(?:生成|安排|做)|再(?:生成|安排|做)|去掉|不放|不吃|不含|不要|加(?:一|点|些)|少(?:一|点|些)|多(?:一|点|些)/.test(text))
    if(mealIntent?.unsupportedDate)throw new Error('请明确选择今天或明天的一日餐单，原问题已保留。')
    const displayQuestion=text.split(/[，。！？；,;]/).filter(part=>!/不变|保持原样|照旧|不用改|不要改/.test(part)).join('，')
    const requestedMealTypes=[['breakfast',/早餐|早饭|早上|今早|明早/],['lunch',/午餐|午饭|中午/],['dinner',/晚餐|晚饭|晚上|今晚|明晚/]].filter(([,pattern])=>pattern.test(displayQuestion)).map(([type])=>type)
    if(/三餐|全天|一天/.test(displayQuestion)||!requestedMealTypes.length)requestedMealTypes.splice(0,requestedMealTypes.length,'breakfast','lunch','dinner')
    const baseAction=mealQuestionAction(text)
    let action=image?'consultation':referenceAdjustment?'change':mealIntent||promptAction==='reference_meal_preview'?(baseAction==='change'?'change':'generate'):baseAction
    // Every send uses the same local message and releases only the captured text.
    // Keep pendingUser unbound until flow.submit publishes this request's own ID.
    stage='queue-message'
    user=reactive({id:newHealthRequestId(),role:'user',text,createdAt:new Date().toISOString(),status:'sending',localOnly:true,...(image?{image}:{})})
    localOperation=reactive({message:user,scope,epoch:mine,generation:sendTicket,clearedVersion:0,submitting:false})
    localSend.value=localOperation;messages.value.push(user)
    question.value='';localOperation.clearedVersion=textVersion;uni.hideKeyboard?.()
    sendPhase.value='正在准备对话';void scrollLatest({force:true})
    stage='prepare-conversation'
    if(!props.route.taskType&&action==='view'){
      const date=/明天|明日/.test(text)?localDate(new Date(Date.now()+86400000)):localDate()
      const plan=await loadDailyPlan(profile.value.householdId,date,epoch,scope)
      if(disposed||!visible||mine!==epoch||scope!==storageContext()||sendTicket!==sendGeneration||!plan)return
      user.localOnly=false;user.status='sent'
      messages.value.push({id:newHealthRequestId(),role:'assistant',text:plan.status==='ready'?'这是已安排的餐单。':'这一天还没有餐单。',planDate:date,planMeals:requestedMealTypes})
      settleDraft(snapshot);await scrollLatest({force:true});return
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
      if(disposed||!visible||mine!==epoch||scope!==storageContext()||sendTicket!==sendGeneration)return
      if(!task.value.available)throw new Error(task.value.error||task.value.notice||chatError.value||'请先核对营养咨询资料与授权。')
      if(!task.value.entry?.thread_id)await flow.createEntry()
      if(disposed||!visible||mine!==epoch||scope!==storageContext()||sendTicket!==sendGeneration)return
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
      if(disposed||!visible||mine!==epoch||scope!==storageContext()||sendTicket!==sendGeneration)return
      if(!plan)throw new Error('计划状态已变化，请重新读取。')
      if(continuing&&referenceSelection.daily_base_version!==plan.version)throw new Error('饮食计划已有更新，请重新核对后继续。')
      if(referenceFollowUp&&previousVersion!==plan.version)referenceFollowUp=false
      if(activePlanStatus(plan.pending?.status)){inlineTodayOpen.value=plan.date===localDate();throw new Error('该日饮食计划正在生成，请等待已有任务完成。')}
      const covered=type=>plan.meals.some(item=>item.meal_type===type&&JSON.stringify((item.members||[]).map(m=>m.id).sort())===JSON.stringify(referenceSelection.participant_ids))
      if(action==='generate'&&plan.status==='ready'&&referenceSelection.meal_types.every(covered)){
        user.localOnly=false;user.status='sent'
        messages.value.push({id:newHealthRequestId(),role:'assistant',text:'这是已安排的餐单。',planDate:plan.date,planMeals:[...referenceSelection.meal_types]})
        settleDraft(snapshot);await scrollLatest({force:true});return
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
    if(disposed||!visible||mine!==epoch||scope!==storageContext()||sendTicket!==sendGeneration)return
    if(task.value.canRetry)return
    if(!task.value.available){chatError.value=task.value.error||task.value.notice||chatError.value||'请先在该成员的家庭档案中完成资料和咨询同意。';return}
    if(!task.value.entry?.thread_id){
      await flow.createEntry()
      if(disposed||!visible||mine!==epoch||scope!==storageContext()||sendTicket!==sendGeneration)return
      rememberThread();if(task.value.entry?.thread_id)await restoreChat(type)
    }
    if(disposed||!visible||mine!==epoch||scope!==storageContext()||sendTicket!==sendGeneration)return
    rememberThread()
    if(disposed||!visible||mine!==epoch||scope!==storageContext())return
    if(!task.value.entry?.thread_id){chatError.value=task.value.error||task.value.notice||'咨询尚未建立，请重新读取后再发送。';return}
    stage='read-image'
    const images=image?[await chatImageContent(image)]:[]
    if(disposed||!visible||mine!==epoch||scope!==storageContext())return
    stage='queue-message'
    snapshot.conversation=conversationId.value;snapshot.requestId='';submittedDraft=snapshot
    rememberThread()
    stage='save-draft'
    scopedStorage.setStorageSync('homepage-chat-task',{memberId:historyMemberId.value||task.value.memberId,taskMemberId:task.value.memberId,type,date:localDate(),newConversation:newConversationWelcome.value,conversationId:conversationId.value,...(type==='reference_meal_preview'?{selection:referenceSelection}:{})});desiredType=type
    stage='scroll-message'
    await scrollLatest({force:true})
    if(disposed||!visible||mine!==epoch||scope!==storageContext()||sendTicket!==sendGeneration)return
    stage='submit-task'
    pendingUser=user;localOperation.submitting=true;sendPhase.value='正在提交问题'
    const accepted=await flow.submit(text,false,images)
    if(disposed||!visible||mine!==epoch||scope!==storageContext())return
    if(!accepted&&type==='reference_meal_preview'&&task.value.error?.includes('该日饮食计划正在生成')){
      failLocalSend(localOperation)
      messages.value=messages.value.filter(message=>message!==user)
      await loadDailyPlan(profile.value.householdId,referenceSelection.plan_date,epoch,scope)
      inlineTodayOpen.value=referenceSelection.plan_date===localDate()
      chatError.value=task.value.error;return
    }
    user.status=messageDeliveryStatus(task.value,!!accepted)
    if(accepted)user.localOnly=false
    if(accepted&&!['failed','rejected','interrupted'].includes(task.value.status)){settleDraft(snapshot)}
    // 未确认提交由任务状态接管，避免恢复后仍残留一份本地错误。
    else if(!task.value.submitUnknown)chatError.value=task.value.error||'回复尚未完成，原问题和图片已保留。'
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
  finally{if(sendTicket===sendGeneration){
    if(localOperation&&(user.localOnly||['failed','rejected','interrupted','cancelled'].includes(user.status)))failLocalSend(localOperation)
    localSend.value=null;sendPhase.value='';pendingUser=null;sending.value=false
    if(!disposed&&visible&&mine===epoch&&scope===storageContext()&&chatError.value)uni.showToast({title:chatError.value,icon:'none',duration:3500})
  }}
}
async function resumePlanQuestion(pending=todayPlan.value?.pending){
  if(chatBusy.value||pending?.status!=='needs_input'||pending.selection?.family_id!==profile.value?.householdId||pending.selection?.plan_date!==localDate())return
  inlineTodayOpen.value=false
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
  entryMotion.reset();entryMotion.reconcile()
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
function sendVoice(text){
  const draft=question.value.trim()
  question.value=draft?draft+'\n'+text:text
  voiceBusy.value=false
  return sendQuestion()
}
function switchInputMode(){
  if(chatBusy.value||voiceBusy.value||draftSaving.value)return
  entryMotion.enter();releaseComposerIntent()
  voiceMode.value=!voiceMode.value
  textFocusRequested.value=!voiceMode.value
  if(voiceMode.value)uni.hideKeyboard?.()
}
function removeDraft(){draftVersion++;draftImage.value=null;draftSaving.value=false;draftError.value=''}
async function prepareDraft(image=draftImage.value){
  if(!image)return
  entryMotion.enter()
  const version=++draftVersion,scope=storageContext();draftImage.value=image;draftSaving.value=true;draftError.value=''
  try{const saved=await persistChatImage({path:image.path||image.localPath,source:image.source});if(!disposed&&version===draftVersion&&scope===storageContext()){draftImage.value=saved;scopedStorage.setStorageSync('last-chat-image',saved)}}
  catch(e){if(!disposed&&version===draftVersion&&scope===storageContext())draftError.value=e.message}
  finally{if(version===draftVersion)draftSaving.value=false}
}
function camera(){
  if(openingCamera||chatBusy.value||voiceBusy.value||draftSaving.value)return
  entryMotion.enter();releaseComposerIntent();cameraPending.value=true
  const scope=storageContext();openingCamera=true;uni.hideKeyboard?.()
  uni.navigateTo({url:'/pages/chat/camera',events:{photoSelected:image=>{if(!disposed&&scope===storageContext())void prepareDraft(image)}},fail(){cameraPending.value=false;chatError.value='相机打开失败，请重试'},complete(){openingCamera=false}})
}
function history(){uni.hideKeyboard?.();historyOpen.value=true}
function stashConversationDraft(){if(conversationId.value)conversationDrafts.set(conversationId.value,{text:question.value,image:draftImage.value,error:draftError.value})}
function resetConversationView(){selectionGeneration++;historyDenied=false;historyLoading.value=false;historyError.value='';historyNotice.value='';continuationChecking.value=false;continuationError.value='';for(const key of Object.keys(mealAppearances))delete mealAppearances[key];localSend.value=null;sendPhase.value='';scrollRevision++;reading.value={following:true};latestAvailable.value=false;detailRef.value?.clear();resetEntryUI();flow.hide();messages.value=[];question.value='';removeDraft();submittedDraft=null;pendingUser=null;referenceSelection=null;latestReference.value=null;familyPanel.value=false;inlineTodayOpen.value=false;chatError.value='';desiredType='consultation';scrollTarget.value=''}
function generateReference(){if(!voiceBusy.value)inlineTodayOpen.value=true}
function acceptTodayPlan(plan){dailyPlans.value={...dailyPlans.value,[plan.date]:plan}}
async function newConversation(){
  if(conversationChangeBusy.value||switchingConversation.value||!entryReady.value||voiceBusy.value||draftSaving.value)return
  if(props.route.taskType){uni.reLaunch({url:'/pages/chat/index?newConversation=1'});return}
  stashConversationDraft();resetConversationView();refreshPrompts()
  conversationId.value=newHealthRequestId();conversationThreadId.value='';conversationBusinessDate.value='';newConversationWelcome.value=true
  const id=profile.value?.members.find(m=>m.id===profile.value.selfMemberId)?.healthMemberId
  if(id){saveConversation();scopedStorage.setStorageSync('homepage-chat-task',{memberId:id,type:'consultation',date:localDate(),conversationId:conversationId.value,newConversation:true})}
  historyOpen.value=false;switchingConversation.value=true
  try{await restoreChat('consultation')}finally{switchingConversation.value=false}
}
/** 已鉴权的历史逐线程呈现；服务就绪和队列恢复不持有正文的显示权。 */
async function readSelectedHistory(row,memberId,current,snapshots){
  const key='conversation-threads:'+conversationId.value
  const pointers=[{thread_id:row.thread_id,memberId},...(scopedStorage.getStorageSync(key)||[])]
  const reading=new Map(),failures=new Map()
  async function readOne(pointer){
    if(reading.has(pointer.thread_id))return reading.get(pointer.thread_id)
    const operation=(async()=>{
      try{
        const snapshot=await readChatSnapshot(pointer.thread_id)
        if(!current()||historyDenied)return
        snapshots.set(pointer.thread_id,{...snapshot,threadId:pointer.thread_id})
        const saved=snapshot.messages.filter(m=>visibleConversationMessage(m,true)).map(m=>({...m,threadId:pointer.thread_id,memberId:pointer.memberId||memberId}))
        for(const message of saved){
          const index=messages.value.findIndex(old=>old.threadId===message.threadId&&(old.id===message.id||message.requestId&&old.requestId===message.requestId&&old.role===message.role))
          if(index<0)messages.value.push(message)
          else messages.value[index]={...messages.value[index],...message}
        }
        messages.value.sort((a,b)=>(Date.parse(a.createdAt)||0)-(Date.parse(b.createdAt)||0))
        const related=snapshot.relatedThreads||[]
        if(related.length){
          const stored=scopedStorage.getStorageSync(key)||[]
          const unique=new Map([...stored,...related].map(p=>[p.thread_id,p]))
          scopedStorage.setStorageSync(key,[...unique.values()])
        }
        for(const date of new Set(saved.map(m=>m.planDate).filter(Boolean))){
          if(!dailyPlans.value[date])void loadDailyPlan(profile.value.householdId,date,epoch,storageContext()).catch(()=>{})
        }
        await scrollLatest()
        await Promise.all(related.filter(p=>p.thread_id!==pointer.thread_id).map(readOne))
      }catch(error){
        if(!current())return
        const denied=[401,403,404,409,410].includes(Number(error.code))
        if(denied&&pointer.thread_id===row.thread_id){
          flow.invalidateThread();historyDenied=true;messages.value=[];question.value='';removeDraft()
          historyError.value='这段对话已不可访问，请重新核对登录与授权。'
        }else if(denied){
          historyNotice.value='部分历史记录的授权或资料来源已变化，暂不可访问。'
          messages.value=messages.value.filter(m=>m.threadId!==pointer.thread_id)
          scopedStorage.setStorageSync(key,(scopedStorage.getStorageSync(key)||[]).filter(p=>p.thread_id!==pointer.thread_id))
        }else failures.set(pointer.thread_id,error)
      }
    })()
    reading.set(pointer.thread_id,operation)
    return operation
  }
  await Promise.all(pointers.map(readOne))
  if(current()&&!historyDenied&&failures.size)historyError.value='部分历史记录暂未读取成功，请重试。'
}
async function selectConversation(row){
  if(conversationChangeBusy.value||voiceBusy.value||draftSaving.value||row.unavailable)return
  const id=profile.value?.members.find(m=>m.id===profile.value.selfMemberId)?.healthMemberId
  if(!id||row.member_id!==id||row.agent_slug!=='health-consultation')return
  if(props.route.taskType){scopedStorage.setStorageSync('homepage-conversation',{id:row.thread_id,threadId:row.thread_id,memberId:id,businessDate:row.business_date||''});uni.reLaunch({url:'/pages/chat/index?entry=conversation'});return}
  epoch++;stashConversationDraft();resetConversationView();refreshPrompts()
  const scope=storageContext(),mine=epoch,generation=selectionGeneration
  const current=()=>{
    if(scope!==storageContext()&&pageScope===scope){clearPrivate();pageScope=storageContext();flowScope=pageScope;return false}
    return !disposed&&visible&&scope===storageContext()&&mine===epoch&&generation===selectionGeneration
  }
  const saved=scopedStorage.getStorageSync('conversation-index:'+row.thread_id)
  const resume=scopedStorage.getStorageSync('homepage-chat-task'),snapshots=new Map()
  conversationId.value=saved?.memberId===id?saved.id:row.thread_id
  conversationThreadId.value=row.thread_id;conversationBusinessDate.value=row.business_date||'';newConversationWelcome.value=false
  saveConversation();historyOpen.value=false;switchingConversation.value=true;historyLoading.value=true;continuationChecking.value=true
  const history=readSelectedHistory(row,id,current,snapshots).finally(()=>{if(current())historyLoading.value=false})
  const continuation=(async()=>{
    await restoreChat('consultation',{readHistory:false})
    if(!current()||historyDenied)return
    await restoreSpecialTask(resume,{readHistory:false})
    if(!current()||historyDenied)return
    continuationError.value=task.value.error||(!task.value.available?task.value.notice||'续聊状态暂未确认，请重试。':'')
    if(!continuationError.value)scopedStorage.setStorageSync('homepage-chat-task',{memberId:historyMemberId.value||task.value.memberId,taskMemberId:task.value.memberId,type:task.value.taskType,date:localDate(),conversationId:conversationId.value,...(task.value.taskType==='reference_meal_preview'?{selection:referenceSelection}:{})})
  })().catch(error=>{if(current())continuationError.value=error.message||'续聊状态暂未确认，请重试。'}).finally(()=>{if(current())continuationChecking.value=false})
  try{
    await Promise.all([history,continuation])
    if(!current()||historyDenied||task.value.invalidated)return
    const active=snapshots.get(task.value.entry?.thread_id)?.runs.find(r=>['queued','dispatched','pending','running','cancel_requested'].includes(r.status))
    if(active?.request_id&&!task.value.submitUnknown)await flow.restoreRequest(active.request_id,{preferActive:true})
    if(!current()||historyDenied)return
    const draft=conversationDrafts.get(conversationId.value)
    if(draft&&!conversationReadOnly.value){question.value=draft.text;draftImage.value=draft.image;draftError.value=draft.error}
  }finally{if(current())switchingConversation.value=false}
}
async function retryHistory(){
  if(historyLoading.value)return
  if(historyDenied)return retrySelectedConversation()
  const scope=storageContext(),generation=selectionGeneration,mine=epoch
  const current=()=>!disposed&&visible&&scope===storageContext()&&generation===selectionGeneration&&mine===epoch
  historyError.value='';historyLoading.value=true
  try{await readSelectedHistory({thread_id:conversationThreadId.value},historyMemberId.value,current,new Map())}
  finally{if(current())historyLoading.value=false}
}
function retrySelectedConversation(){return selectConversation({thread_id:conversationThreadId.value,member_id:historyMemberId.value,agent_slug:'health-consultation',business_date:conversationBusinessDate.value||null})}
async function shortcut(key){
  if(key==='family')archives()
  else if(key==='camera')uni.navigateTo({url:'/pages/scan/index'})
  else if(key==='community')communityOpen.value=true
  else if(key==='plans')uni.navigateTo({url:'/pages/exclusive-plans/index'})
  else inlineTodayOpen.value=!inlineTodayOpen.value
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
<NutritionistLayout :history-open="historyOpen" :scroll-locked="readingSuspended" :follow-bottom="reading.following" :latest-available="latestAvailable" @reading-change="rememberReading" @latest="scrollLatest({force:true})" entry-transition :welcome-mounted="welcomeMounted" :welcome-leaving="entryView.phase==='leaving'" :transition-ticket="entryView.generation" :keyboard-open="keyboardView.keyboardOpen" :viewport-style="viewportStyle" @welcome-finished="entryMotion.finish" :voice-busy="voiceBusy" :scroll-target="scrollTarget" @history="history" @profile="uni.navigateTo({url:'/pages/my/index'})" @shortcut="shortcut">
 <template #welcome>
  <ChatWelcome :density="welcomeDensity" :prompts="prompts" :disabled="chatBusy||entryView.phase==='leaving'" @ask="askPrompt" @shuffle="shufflePrompts"/>
 </template>
 <template #default>
  <view v-if="historyLoading||historyError" class="entry-status" :role="historyError?'alert':'status'" aria-live="polite"><text>{{historyError||'正在加载历史对话…'}}</text><button v-if="historyError&&!historyLoading" @click="retryHistory">重新读取历史</button></view>
  <text v-if="historyNotice" class="entry-status" role="status">{{historyNotice}}</text>
  <view v-if="continuationChecking||continuationError" class="entry-status" role="status"><text>{{continuationChecking?'正在核对续聊状态，历史记录可先阅读。':continuationError}}</text><button v-if="continuationError&&!continuationChecking" @click="retrySelectedConversation">重新核对</button></view>
  <text v-if="entryView.phase==='composing'&&entryContext.eligible&&!chatBusy" class="entry-greeting">你好，想聊聊今天怎么吃？</text>
  <view v-if="onboardingPending" class="dialogue-status"><text>上次资料保存结果尚未确认，可以继续核对原提交。</text><button @click="uni.navigateTo({url:'/pages/onboarding/preparing'})">核对保存结果</button></view>
  <view v-if="presentation.initialResults" class="analysis-message"><AiAnswer :text="state.arrangement.analysis.text" compact/></view>
  <DailyArrangementCard v-if="cardVisible && presentation.initialResults" :arrangement="state.arrangement" :disabled="state.busy" @open="openMeal" @members="openFormalDetail($event,state.arrangement,state.date,{initialView:'members'})" @shop="shop"/>
   <ChatWelcome v-if="presentation.welcome&&(failedTask||!entryReady)&&(!entryView.engaged||!entryReady)" :compact="failedTask" :prompts="prompts" :disabled="chatBusy" @ask="askPrompt" @shuffle="shufflePrompts"/>
  <view v-for="(message,messageIndex) in visibleMessages" :id="'message-'+message.id" :key="message.id" class="message-turn">
   <view v-if="messageTime(message,messageIndex)" class="message-time"><text>{{messageTime(message,messageIndex)}}</text></view>
   <view class="message-row" :class="message.role"><text v-if="hasMessageIssue(message)||message.role==='user'&&message.status==='unknown'" class="message-issue" :class="{'is-unconfirmed':message.status==='unknown'}" role="button" tabindex="0" :aria-label="message.status==='unknown'?'消息状态待确认':'查看消息失败原因'" @click="messageStatus(message)" @keydown.enter="messageStatus(message)">{{message.status==='unknown'?'?':'!'}}</text><view class="message-content"><view class="bubble"><view v-if="message.role==='assistant'" class="reply-card-head"><AppIcon name="assistant" :size="46" :state="message.business&&isReferencePlan(message.business.data)?'success':'idle'"/><text>家庭营养师</text></view><view class="bubble-body"><image v-if="message.image" class="chat-message-image" :src="message.image.localPath" mode="widthFix" @click="previewChatImage(message.image)"/><AiAnswer v-if="message.role==='assistant'&&message.text" :text="message.text" :citations="message.citations||[]" :message-key="message.requestId" :shown-meals="mealAppearances[message.requestId]||[]" :animate-meals="!!message.mealEnter" @meal-shown="rememberMealAppearance" compact/><text v-else-if="message.text" selectable>{{message.text}}</text>
   </view></view><text v-if="message.role==='user'&&message.status==='cancelled'" class="message-status-note">已停止</text><DailyMealPlanCard :meal-types="message.planMeals" @dish="openDailyDish($event,message.planDate)" @all="buyAllMeals" @detail="openDailyMeal($event,message.planDate)" detail-mode v-if="message.planDate&&dailyPlans[message.planDate]?.status==='ready'" :plan="dailyPlans[message.planDate]" :busy="planPurchaseBusy" @open="openDailyMeal($event,message.planDate)" @members="selectDailyMembers($event,message.planDate)" @shop="purchaseDaily($event,dailyPlans[message.planDate])"/><HealthChatBusinessCard detail-mode @detail="openReferencePlan" v-else-if="message.business&&!message.planDate" :result="message.business" :member-id="message.memberId||task.memberId"/><ConversationFoodPackages v-if="message.purchaseRequestId" :offers="message.purchaseOffers" :request-id="message.purchaseRequestId" :animate="message.purchaseEnter" @ready="queueScroll"/><ChatMealRecordCard v-for="receipt in message.recordedMeals||[]" :key="receipt.id" :receipt="receipt" @changed="updateMealReceipt"/><ChatReplyActions v-if="message.role==='assistant'&&message.text&&!message.error" :text="message.text" :message-id="message.serverMessageId||message.id" :can-quote="!chatBusy&&!conversationReadOnly" @quote="quoteReply"/></view></view>
  </view>
  <view v-if="mealReplyActions&&!chatBusy&&!conversationReadOnly" class="reply-actions" aria-label="继续安排饮食">
   <button @click="question='请换几道菜，继续沿用已确认的饮食限制。'"><text>换几道菜</text><AppIcon name="arrow" :size="23"/></button>
   <button @click="generateReference"><text>整理成今日餐单</text><AppIcon name="arrow" :size="23"/></button>
  </view>
  <view v-if="liveAnswer||entryReady&&!profileLoading&&replyPending" id="stream-answer" class="message-row assistant live-answer" :class="{'is-pending':!liveAnswer}"><view class="message-content"><view class="bubble"><view class="reply-card-head"><AppIcon name="assistant" :size="46" :state="task.taskType==='reference_meal_preview'?'planning':'thinking'"/><text>家庭营养师</text></view><view class="bubble-body"><AiAnswer v-if="liveAnswer" :text="task.streamText" :message-key="task.requestId" :shown-meals="mealAppearances[task.requestId]||[]" :animate-meals="visible&&!restoring&&!returning" @meal-shown="rememberMealAppearance" streaming compact/><view v-if="!liveAnswer" id="reply-progress" class="reply-progress" role="status" aria-live="polite"><view class="progress-dot"/><text class="progress-label">{{progressText}}</text></view></view></view></view></view>
  <view v-if="familyPanel" class="dialogue-status"><text>家庭餐单 · {{familyState.date}}</text><text>按这餐实际参加的成员核对家庭安排，每位成员的资料和权限由服务端检查。</text><text v-if="familyState.busy">正在读取家庭安排…</text><text v-if="familyState.error" class="chat-error">{{familyState.error}}</text><button v-if="familyState.error" :disabled="familyState.busy" @click="familyPlan('',true)">重新读取家庭餐单</button><DailyArrangementCard v-if="familyState.phase==='ready'" :arrangement="familyState.arrangement" family :disabled="familyState.busy" @open="openFamilyMeal" @members="openFormalDetail($event,familyState.arrangement,familyState.date,{initialView:'members'})" @shop="shop"/><button @click="familyPanel=false">收起家庭餐单</button></view>
  <view v-if="task.consentOption" class="dialogue-status"><text>本次{{task.taskType==='reference_meal_preview'?'配餐':'咨询'}}处理方：{{task.consentOption.processor}}；政策版本：{{task.consentOption.policyVersion}}。</text><checkbox-group @change="consentChecked=$event.detail.value.includes('yes')"><label><checkbox value="yes" :checked="consentChecked"/>同意本次{{task.taskType==='reference_meal_preview'?'配餐':'咨询'}}的数据处理</label></checkbox-group><button :disabled="!consentChecked||chatBusy" @click="consent">同意并继续{{task.taskType==='reference_meal_preview'?'配餐':'咨询'}}</button></view>
 </template>
 <template #composer>
  <view v-if="conversationReadOnly" class="archived-conversation"><text>这段每日对话已归档，记录仍可查看。</text><button :disabled="chatBusy" @click="newConversation">新对话继续聊</button></view>
  <template v-else>


  <view v-if="draftImage" class="image-draft"><view class="draft-thumbnail"><image :src="draftImage.localPath||draftImage.path" mode="aspectFill" @click="previewChatImage(draftImage)"/><button aria-label="移除待发送图片" @click="removeDraft">×</button></view><view><text>{{draftSaving?'正在准备图片…':draftError||'可直接发送图片，也可以补充文字'}}</text><button v-if="draftError" @click="prepareDraft()">重新准备图片</button></view></view>
  <view class="composer" :class="{'is-voice-mode':voiceMode}" @touchstart="holdComposerIntent" @touchend="settleComposerPress" @touchcancel="releaseComposerIntent" @mousedown="holdComposerIntent" @mouseup="settleComposerPress">
   <button class="input-icon camera-button" aria-label="打开相机或选择照片" :disabled="chatBusy||voiceBusy||draftSaving" @click="camera"><AppIcon name="camera-solid" :size="46"/></button>
   <view v-if="voiceMode" class="voice-input-slot"><VoiceInput ref="voiceRef" embedded style="width:100%;min-width:0;flex:1" :disabled="chatBusy||draftSaving" @send="sendVoice" @busy="voiceBusy=$event"/></view>
    <input v-else v-model="question" :disabled="inputBusy" @input="markDraftInput" aria-label="输入营养咨询问题" :placeholder="composerPlaceholder" placeholder-style="color:#898b92" confirm-type="send" :focus="textFocusRequested" :adjust-position="false" :cursor-spacing="0" @focus="handleInputFocus" @blur="handleInputBlur" @keyboardheightchange="handleKeyboardHeightChange" @confirm="sendQuestion"/>
   <button v-if="primaryMode==='send'&&!chatBusy" class="input-icon mode-button" aria-label="切换语音输入" :disabled="voiceBusy||draftSaving" @click="switchInputMode"><AppIcon name="voice-waves" :size="46"/></button>
   <view class="composer-primary-slot">
    <button v-if="primaryMode==='submitting'" key="submitting" class="send-button" aria-label="正在发送问题" disabled><view class="primary-spinner"/></button>
    <button v-else-if="primaryMode==='stopping'" key="stopping" class="send-button" aria-label="正在停止生成" disabled><view class="primary-spinner"/></button>
    <button v-else-if="primaryMode==='stop'" key="stop" class="send-button" :class="{'is-thinking':!liveAnswer}" aria-label="停止生成" :disabled="!preparingSend&&task.busy" @click="stopQuestion"><view class="stop-square"/></button>
    <button v-else-if="primaryMode==='check'" key="check" class="send-button" :aria-label="task.cancelPhase==='unknown'?'核对停止结果':'核对发送结果'" :disabled="!canCheckTask" @click="checkTaskStatus"><view v-if="task.refreshing||task.loading||task.busy" class="primary-spinner"/><view v-else class="check-task-icon"/></button>
    <button v-else-if="primaryMode==='send'" key="send" class="send-button" aria-label="发送" :disabled="sendBlocked" @click="sendQuestion"><AppIcon name="arrow" :size="32"/></button>
    <button v-else key="mode" class="input-icon mode-button" :aria-label="voiceMode?'切换文字输入':'切换语音输入'" :disabled="chatBusy||voiceBusy||draftSaving" @click="switchInputMode"><view v-if="voiceMode" class="keyboard-icon"><view/><view/><view/></view><AppIcon v-else name="voice-waves" :size="46"/></button>
   </view>
  </view>

  </template>
  <text class="ai-content-note">内容由 AI 生成，请结合自身情况核对</text>
 </template>
 <template #overlays>
  <MealDetailSheet ref="detailRef" :members="profile?.members||[]" :reload="reloadDetailPlan" @open-change="detailOpen=$event"/>
  <ChatConversationDrawer :open="historyOpen" :member-id="historyMemberId" :active-thread-id="conversationThreadId" :new-busy="switchingConversation" :busy="conversationChangeBusy||voiceBusy||draftSaving" :display-name="profile?.members.find(m=>m.id===profile.selfMemberId)?.name||'我的'" @close="historyOpen=false" @new="newConversation" @select="selectConversation" @profile="historyOpen=false;uni.navigateTo({url:'/pages/my/index'})"/>
  <TodayMealPlanSheet :open="inlineTodayOpen" :profile="profile" :unavailable="!!entryError" :busy="planPurchaseBusy||state.busy" @close="inlineTodayOpen=false" @plan="acceptTodayPlan" @continue="resumePlanQuestion($event)" @detail="openDailyMeal($event,todayPlan.date)" @dish="openDailyDish($event,todayPlan.date)" @all="buyAllMeals"/>
  <DinerPicker :open="!!familySelection" :members="profile?.members||[]" :selected="familySelection?.ids||[]" :meal="({breakfast:'早餐',lunch:'午餐',dinner:'晚餐'})[familySelection?.type]" @close="familySelection=null" @confirm="familyMembers"/>
  <DinerPicker :open="!!selectedMeal" :members="profile?.members||[]" :selected="selectedMeal?.members.map(m=>m.id)||[]" :meal="({breakfast:'早餐',lunch:'午餐',dinner:'晚餐'})[selectedMeal?.type]" @close="selectedMeal=null" @confirm="members"/>
  <view v-if="communityOpen" class="sheet-mask" @click.self="communityOpen=false"><view class="sheet"><text class="section-title">加入社群</text><text class="composer-note">暂无可用社群二维码，请稍后再试。</text><button class="secondary-button" @click="communityOpen=false">关闭</button></view></view>
 </template>
</NutritionistLayout>
</template>
<style scoped>
.entry-greeting{display:block;margin-top:24px;font-size:16px;line-height:1.8;color:#555}
.message-issue{display:flex;align-items:center;justify-content:center;align-self:center;flex:0 0 18px;width:18px;height:18px;margin-right:10px;border-radius:50%;background:#d83a3a;color:#fff;font-size:13px;font-weight:700;line-height:18px}.message-issue.is-unconfirmed{background:#eef0f2;color:#687078}.message-status-note{display:block;margin-top:6px;text-align:right;color:var(--ui-muted);font-size:12px;line-height:1.5}

.entry-status{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:12px 0;color:#858585;font-size:13px;line-height:1.7}.entry-status>text{flex:1 1 100%}.entry-status button{min-height:44px;margin:0;padding:0 12px;border:1px solid #e5e5e5;border-radius:8px;background:var(--ui-surface);color:#555;font-size:13px;display:flex;align-items:center;justify-content:center}.entry-status button:after{border:0}
.message-row{display:flex;width:100%;gap:0;margin:28px 0;color:#202020}.message-content{width:100%;min-width:0;max-width:100%}.message-row.user{justify-content:flex-end;padding-left:40px;box-sizing:border-box}.user .message-content{width:auto;max-width:100%;flex:0 1 auto}.bubble{font-size:16px;line-height:1.8;white-space:pre-line;overflow-wrap:anywhere;word-break:break-word;padding:0;border:0;background:transparent;color:var(--ui-text);max-width:100%;border-radius:0}.user .bubble{display:block;width:auto;box-sizing:border-box;padding:12px 16px;border-radius:20px 20px 6px 20px;background:var(--ui-user);color:var(--ui-user-text);font-size:16px;line-height:1.6;font-weight:500}.analysis-message{margin:24px 0 22px}
.dialogue-status{padding:14px 0;margin:18px 0;border-bottom:1px solid #ededed;background:transparent;font-size:14px;line-height:1.8;color:#666}.dialogue-status>text{display:block}.dialogue-status button,.secondary-button{display:inline-flex;align-items:center;justify-content:center;min-height:44px;font-size:14px;color:#333;background:transparent;border:1px solid #ddd;border-radius:8px;margin:10px 10px 0 0;padding:7px 12px;line-height:1.5}.dialogue-status button:after,.secondary-button:after{border:0}.reply-progress{display:flex;align-items:center;gap:9px;min-height:28px;margin:22px 0;font-size:14px;line-height:1.6;color:#888}.chat-error{display:block;margin-top:12px;font-size:13px;line-height:1.7;color:#8d4c40}
.composer{position:relative;display:flex;align-items:center;gap:4px;width:100%;min-height:58px;box-sizing:border-box;padding:6px;background:linear-gradient(180deg,rgba(255,255,255,.30),rgba(255,255,255,.96));border:1px solid rgba(255,255,255,.88);border-radius:19px;box-shadow:inset 0 1px 0 #fff}
.composer:focus-within{border-color:#fff;box-shadow:inset 0 1px 0 #fff,0 0 0 1px rgba(121,100,200,.10)}
.composer input{flex:1;min-width:0;width:0;height:44px;box-sizing:border-box;padding:0 6px;border:0;border-radius:0;background:transparent;color:var(--ui-text);font-size:16px;line-height:1.5;outline:none}
.input-icon,.send-button{display:flex;flex-shrink:0;align-items:center;justify-content:center;min-width:44px;width:44px;min-height:44px;height:44px;box-sizing:border-box;margin:0;padding:0;border:0;border-radius:50%;background:transparent;color:#303739}
.input-icon{position:relative}.camera-button:before,.mode-button:before{content:"";position:absolute;top:12px;bottom:12px;width:1px;background:linear-gradient(transparent,rgba(91,99,122,.18),transparent);pointer-events:none}.camera-button:before{right:-2px}.mode-button:before{left:-2px}.input-icon:after,.send-button:after{border:0}.input-icon:active{background:#eceef1}.input-icon[disabled],.send-button[disabled]{opacity:.4}
.send-button{color:#fff;background:var(--ui-accent,#303739);border-radius:50%}.send-button:active{background:var(--ui-accent-pressed,#202628)}.send-button[disabled]{background:var(--ui-accent,#303739);color:#fff;opacity:1}
.voice-input-slot{display:flex;align-items:center;flex:1;min-width:0;height:44px}
.keyboard-icon{width:22px;height:17px;border:2px solid currentColor;border-radius:4px;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:3px}.keyboard-icon>view{width:14px;border-top:2px dotted currentColor}.keyboard-icon>view:last-child{width:10px;border-top-style:solid}
.chat-message-image{display:block;width:210px;max-width:100%;height:auto;border-radius:8px;margin-bottom:8px}.image-draft{display:flex;align-items:center;gap:12px;padding:8px 0 14px;font-size:13px;line-height:1.6;color:#777}.draft-thumbnail{position:relative;flex-shrink:0}.draft-thumbnail image{width:56px;height:56px;border-radius:8px}.draft-thumbnail button{position:absolute;top:-7px;right:-7px;width:24px;height:24px;display:flex;align-items:center;justify-content:center;border-radius:50%;background:#fff;color:#444}.image-draft>view+view{flex:1}.image-draft button{font-size:13px;min-height:24px}@media(max-width:350px){.bubble{font-size:15px}.message-row{margin:24px 0}.message-row.user{padding-left:30px}.user .bubble{padding:11px 14px;font-size:15px}.composer input{font-size:15px}}


.message-turn{margin:22px 0}.message-time{display:flex;justify-content:center;margin:18px 0}.message-time text{padding:2px 7px;background:transparent;border-radius:12px;font-size:11px;line-height:1.5;color:var(--ui-muted)}.reply-actions{display:flex;flex-direction:column;align-items:flex-start;gap:9px;margin:0 0 20px}.reply-actions button{display:flex;align-items:center;justify-content:space-between;gap:16px;max-width:100%;min-height:44px;margin:0;padding:10px 14px;border:0;border-radius:16px;background:var(--ui-surface);color:var(--ui-text);font-size:14px;line-height:1.5;text-align:left}.reply-actions button:after{border:0}.reply-actions button :deep(.app-icon){color:#7e7693}.progress-dot{width:6px;height:6px;flex-shrink:0;border-radius:50%;background:var(--ui-accent)}.live-answer{padding-bottom:3px}.ai-content-note{display:block;padding-top:9px;text-align:center;font-size:10px;line-height:1.4;color:var(--ui-muted)}.archived-conversation{display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:12px;color:#81778f;line-height:1.6}.archived-conversation button{flex-shrink:0;padding:7px 10px;min-height:40px;border-radius:9px;background:var(--ui-accent);color:#fff;font-size:12px}.archived-conversation button:after{border:0}
.bubble-body{padding:0}.reply-card-head{display:none}.message-turn>.message-row{margin:0}
.stop-square{width:12px;height:12px;border-radius:3px;background:#fff}
.check-task-icon{position:relative;width:18px;height:18px;border:2px solid currentColor;border-right-color:transparent;border-radius:50%}.check-task-icon:after{content:"";position:absolute;top:-3px;right:-2px;width:6px;height:6px;border-top:2px solid currentColor;border-right:2px solid currentColor;transform:rotate(15deg)}

.composer-note{display:block;font-size:12px;color:var(--ui-muted);line-height:1.7;margin-top:8px}.section-title{font-size:18px}.sheet-mask .sheet{color:var(--ui-text)}.sheet-mask .composer-note{text-align:left}


.composer-primary-slot{display:flex;flex:0 0 44px;width:44px;height:44px}.composer-primary-slot .send-button>text{font-size:12px}.primary-spinner{width:17px;height:17px;border:2px solid rgba(255,255,255,.35);border-top-color:#fff;border-radius:50%;animation:primary-spin 800ms linear infinite}.message-issue[role="button"]{cursor:pointer}@keyframes primary-spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.primary-spinner{animation:none}}

/* A single white surface per answer; semantic blocks use spacing inside it. */
.assistant .bubble,.analysis-message{padding:20px 18px;background:rgba(255,255,255,.9);border-radius:var(--ui-radius);box-shadow:inset 0 0 0 1px rgba(255,255,255,.72)}.message-row.assistant{margin-top:22px}.message-turn>.message-row.assistant{margin:0}.live-answer .bubble{min-height:70px}.reply-actions{margin-left:4px}.ai-content-note{padding-top:10px;font-size:11px;line-height:1.5}.image-draft{padding-left:6px}.sheet-mask .sheet{background:var(--ui-surface);border-radius:28px 28px 0 0}.message-content>.answer-tools{padding-left:4px}
@media(max-width:350px){.assistant .bubble,.analysis-message{padding:18px 15px}}

/* Before the first public text arrives, the progress bubble follows its content. */
.live-answer.is-pending .message-content{width:auto;max-width:90%;flex:0 1 auto}.live-answer.is-pending .bubble{min-height:0;padding:12px 16px;border-radius:18px;white-space:normal}.live-answer.is-pending .reply-progress{margin:0;min-height:22px}.live-answer.is-pending .reply-progress text{min-width:0;overflow-wrap:anywhere}

/* Keep progress motion local to the waiting state and leave the bubble still. */
.live-answer.is-pending .progress-dot{animation:chat-progress-dot 1.4s ease-in-out infinite}
.live-answer.is-pending .progress-label{color:#666;font-weight:500;animation:chat-progress-label 1.4s ease-in-out infinite}
@keyframes chat-progress-dot{0%,100%{opacity:.25}50%{opacity:1}}
@keyframes chat-progress-label{0%,100%{opacity:.60}50%{opacity:1}}
@media(prefers-reduced-motion:reduce){.live-answer.is-pending .progress-dot,.live-answer.is-pending .progress-label{animation:none;opacity:1}}

/* A quiet breath while waiting for the first public text; transforms do not move the input. */
.send-button.is-thinking{animation:stop-button-breathe 1.8s ease-in-out infinite;transform-origin:center}
@keyframes stop-button-breathe{0%,100%{transform:scale(1)}50%{transform:scale(1.05)}}
@media(prefers-reduced-motion:reduce){.send-button.is-thinking{animation:none;transform:none}}
</style>
