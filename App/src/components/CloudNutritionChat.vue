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
import ReferenceMealPlanCard from './ReferenceMealPlanCard.vue'
import {referenceSelection as chooseReference,isReferencePlan} from '../services/reference-meal-plan.js'
import ConversationFoodPackages from './ConversationFoodPackages.vue'
import VoiceInput from './VoiceInput.vue'
import AiAnswer from './AiAnswer.vue'
import { readCurrentPreparation } from '../services/onboarding-preparation.js'
import { loadCloudProfile } from '../services/cloud-profile.js'
import { createDailyArrangementClient, dailyArrangementState } from '../services/daily-arrangement-client.js'
import { request } from '../services/request.js'
import { storageContext, scopedStorage } from '../services/storage.js'
import { getSession } from '../services/session.js'
import { createHealthTaskFlow, HEALTH_TEXT_TASKS, newHealthRequestId } from '../services/health-task-flow.js'
import { persistChatImage, previewChatImage } from '../services/chat-images.js'
import { readChatSnapshot, chatImageContent } from '../services/cloud-chat.js'
import { localDate } from '../utils/meal-state.js'
import { parseChatMealIntent } from '../utils/chat-meal-intent.js'
import { loadChatMealPlan } from '../services/chat-meal-plan.js'

const props=defineProps({route:{type:Object,default:()=>({})}})
const state=reactive(dailyArrangementState()),profile=ref(null),cardVisible=ref(false),selectedMeal=ref(null)
const profileLoading=ref(false),entryReady=ref(false)
const entryError=ref(''),entryStatus=ref('正在读取咨询资料…')
const needsProfileLink=computed(()=>profile.value&&!props.route.memberId&&!profile.value.members.some(m=>m.relation==='本人'&&m.healthMemberId))
const question=ref(''),chatError=ref(''),messages=ref([]),task=ref({}),consentChecked=ref(false)
const voiceMode=ref(false),voiceBusy=ref(false),voiceRef=ref(null),communityOpen=ref(false),scrollTarget=ref(''),inlineTodayOpen=ref(false)
const draftImage=ref(null),draftSaving=ref(false),draftError=ref('')
const familyState=reactive(dailyArrangementState()),familyPanel=ref(false),familySelection=ref(null),familyIntent=ref('')
const mealPlanReady=ref(false),mealPlanAudience=ref('default')
const liveAnswer=computed(()=>!!task.value.streamText&&!task.value.result)
const progressText=computed(()=>profileLoading.value?'正在读取你的资料':familyState.busy?(familyState.phase==='generating'?'正在生成三餐，并核对成员、营养与食材':'正在核对已保存的餐单'):task.value.streamStatus||(['queued','pending'].includes(task.value.status)?'问题已收到，正在等待营养师处理':'正在读取资料并整理回复'))
let scrollTimer=null
const prompts=['今晚全家吃什么？','给我安排明天早餐','看看我的饮食记录','糖尿病家庭怎么吃？']
const newConversationWelcome=ref(false),preparedThreadId=ref(''),latestReference=ref(null)
const historyOpen=ref(false),conversationId=ref(''),conversationThreadId=ref(''),conversationBusinessDate=ref(''),switchingConversation=ref(false)
const conversationReadOnly=computed(()=>!!task.value.readOnly||!!conversationBusinessDate.value&&conversationBusinessDate.value<localDate())
const conversationDrafts=new Map()
const historyMemberId=computed(()=>profile.value?.members.find(m=>m.id===profile.value.selfMemberId)?.healthMemberId||'')
const mealReplyActions=computed(()=>{
  const last=messages.value.at(-1),user=messages.value.filter(m=>m.role==='user').at(-1)
  return !props.route.taskType&&last?.role==='assistant'&&!last.error&&!last.business&&!!user?.text&&!!parseChatMealIntent(user.text,localDate())
})
const mealsLoading=ref(false),mealReadError=ref('')
let referenceSelection=null,mealReadGeneration=0
const presentation=computed(()=>chatPresentation({route:props.route,hasMessages:messages.value.length>0,
  hasSavedArrangement:state.phase==='ready',newConversation:newConversationWelcome.value,
  preparedThreadId:preparedThreadId.value,currentThreadId:task.value.entry?.thread_id,
  // The public conversation shell is ready before its private data. Validation
  // still gates every submit through entryReady and chatBusy.
  loading:false}))
const failureText={budget_price_unavailable:'营养咨询服务的计费配置尚未就绪，请联系管理员。原问题已保留。',budget_exceeded:'本月健康 AI 可用额度不足或待核账，请稍后再试。原问题已保留。',execution_cancelled:'本次处理已取消。',execution_interrupted:'本次处理已中断，可稍后重新发送。'}
const chatBusy=computed(()=>switchingConversation.value||!entryReady.value||profileLoading.value||sending.value||familyState.busy||task.value.busy||task.value.loading||task.value.submitUnknown||['queued','dispatched','pending','running','cancel_requested'].includes(task.value.status))
const sending=ref(false),hasDraftContent=computed(()=>!!question.value.trim()||!!draftImage.value)
const canCancel=computed(()=>task.value.requestId&&!task.value.submitUnknown&&['queued','dispatched','pending','running'].includes(task.value.status))
let disposed=false,visible=true,loading=null,epoch=0,pageScope=storageContext(),flowScope=pageScope,draftVersion=0,openingCamera=false,pendingUser=null,submittedDraft=null,desiredType='consultation',restoring=false,startNewHandled=false
const flow=createHealthTaskFlow({daily:true,onChange:next=>{
  if(disposed||flowScope!==storageContext())return
  task.value=next
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
  if(next.result&&next.requestId){
    const id=next.requestId+'-answer',index=messages.value.findIndex(m=>m.requestId===next.requestId&&m.role==='assistant')
    const result=next.result
    if(result.type==='business'&&isReferencePlan(result.data))latestReference.value=result.data
    const message={id,requestId:next.requestId,role:'assistant',createdAt:new Date().toISOString(),citations:result.citations||[],
      text:result.type==='answer'?result.text:result.type==='needs_input'?result.questions.join('\n'):result.type==='error'?(failureText[result.code]||'本次处理失败，原问题已保留，可稍后重新发送。'):'餐单结果已返回，请核对后决定是否使用。',
      memberId:next.memberId,purchaseOffers:result.purchaseOffers,purchaseRequestId:result.purchaseOffers?.length?next.requestId:'',error:result.type==='error',errorCode:result.code,retryable:result.retryable===true,business:result.type==='business'?result:null}
    if(index<0)messages.value.push(message);else messages.value[index]={...messages.value[index],...message}
    if(!restoring)void scrollLatest()
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
function clearPrivate(){historyOpen.value=false;conversationId.value='';conversationThreadId.value='';conversationBusinessDate.value='';conversationDrafts.clear();mealsLoading.value=false;mealReadError.value='';latestReference.value=null;referenceSelection=null;newConversationWelcome.value=false;preparedThreadId.value='';epoch++;loading=null;profileLoading.value=false;flow.hide();client.reset();familyClient.reset();familyPanel.value=false;familySelection.value=null;messages.value=[];question.value='';chatError.value='';profile.value=null;task.value={};selectedMeal.value=null;removeDraft();pendingUser=null;submittedDraft=null;voiceRef.value?.cancel();voiceBusy.value=false;voiceMode.value=false;cardVisible.value=false}
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
  saveConversation(task.value.memberId)
  const title=messages.value.find(m=>m.role==='user'&&(m.text||m.image))
  if(title&&conversationThreadId.value)scopedStorage.setStorageSync(`conversation-summary:${task.value.memberId}:${conversationThreadId.value}`,{title:(title.text||'[图片]').replace(/\s+/g,' ').trim().slice(0,36),updatedAt:new Date().toISOString()})
}
function saveConversation(memberId){
  if(!conversationId.value||props.route.taskType)return
  const value={id:conversationId.value,threadId:conversationThreadId.value,memberId,businessDate:conversationBusinessDate.value,scope:storageContext()}
  scopedStorage.setStorageSync('homepage-conversation',value)
  if(value.threadId)scopedStorage.setStorageSync('conversation-index:'+value.threadId,value)
}
function visibleConversationMessage(message,explicit){
  if(!message.createdAt)return true
  if(explicit&&!conversationBusinessDate.value||props.route.taskType)return true
  const timestamp=Date.parse(message.createdAt)
  return Number.isFinite(timestamp)&&new Date(timestamp+8*3600000).toISOString().slice(0,10)===(conversationBusinessDate.value||localDate())
}
async function restoreChat(type=desiredType){
  if(!profile.value)return
  const scope=storageContext(),ticket=epoch
  if(type==='reference_meal_preview'&&!referenceSelection)referenceSelection=chooseReference(profile.value,'今天三餐',{today:localDate(),tomorrow:localDate(new Date(Date.now()+86400000)),memberId:props.route.memberId})
  const anchor=type==='reference_meal_preview'?profile.value.members.find(m=>referenceSelection.participant_ids.includes(m.id)&&m.healthMemberId):null
  const id=anchor?.healthMemberId||props.route.memberId||profile.value.members.find(m=>m.id===profile.value.selfMemberId)?.healthMemberId
  const capability=profile.value.healthConfiguration?.[['meal_preview','reference_meal_preview'].includes(type)?'meal_plan':type]
  if(capability?.available===false){flow.hide();task.value={};chatError.value='营养服务暂未就绪：'+(capability.reason||'请先完成服务配置')+'。配置完成后重新读取即可。';return}
  if(!id){flow.hide();task.value={};chatError.value='请打开当前成员的家庭档案，核对已保存资料并明确同意营养咨询。';return}
  const selection=type==='reference_meal_preview'?referenceSelection:type==='diet_analysis'?{record_id:props.route.recordId,source_version:Number(props.route.version)}:props.route.indicatorChoice==='1'?scopedStorage.getStorageSync(`indicator-choice:${id}:${type}`):null
  flowScope=scope;restoring=true
  try{
    const options=!props.route.taskType&&conversationId.value?{conversationId:conversationId.value,...(type==='consultation'&&conversationThreadId.value?{threadId:conversationThreadId.value}:{})}:undefined
    await flow.open(id,type,selection,options)
    if(disposed||ticket!==epoch||scope!==storageContext())return
    if(task.value.entry?.thread_id){
      rememberThread({migrateLegacy:!options})
      const currentThread=task.value.entry.thread_id
      const pointers=props.route.taskType?[{thread_id:currentThread}]:conversationId.value?(scopedStorage.getStorageSync('conversation-threads:'+conversationId.value)||[]).filter(p=>!p.memberId||p.memberId===id):(scopedStorage.getStorageSync(`homepage-chat-threads:${id}:${localDate()}`)||[])
      if(!pointers.some(p=>p.thread_id===currentThread))pointers.push({thread_id:currentThread,memberId:id})
      const results=await Promise.allSettled(pointers.map(async p=>({...(await readChatSnapshot(p.thread_id)),threadId:p.thread_id})))
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
      const saved=snapshots.flatMap(p=>p.messages.filter(m=>visibleConversationMessage(m,!!options?.conversationId)).map(m=>({...m,memberId:id,threadId:p.threadId}))).sort((a,b)=>(Date.parse(a.createdAt)||0)-(Date.parse(b.createdAt)||0))
      const live=messages.value.filter(m=>m.requestId===task.value.requestId&&(m.status==='unknown'||m.role==='assistant'&&task.value.result))
      messages.value=[...saved,...live.filter(m=>!saved.some(row=>m.requestId&&row.requestId===m.requestId&&row.role===m.role))]
      rememberThread()
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
    if(resume?.type==='reference_meal_preview'&&resume.selection?.family_id===next.householdId)referenceSelection=resume.selection
    desiredType=Object.hasOwn(HEALTH_TEXT_TASKS,props.route.taskType)?props.route.taskType:resume?.memberId===selfId&&resume?.conversationId===conversationId.value&&resume?.date===localDate()?resume.type:'consultation'
    latestReference.value=null;preparedThreadId.value=''
    entryStatus.value='正在恢复对话…'
    await restoreChat()
    if(disposed||!visible||mine!==epoch)return
    if(scope!==storageContext())return await recoverSession()
    cardVisible.value=state.phase==='ready';entryReady.value=true
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
async function loadOptionalMeals(familyId,mine,scope){
  const ticket=++mealReadGeneration,date=localDate(),familyPath='/api/family/'+encodeURIComponent(familyId)
  const current=()=>!disposed&&visible&&mine===epoch&&ticket===mealReadGeneration
  mealsLoading.value=true;mealReadError.value='';latestReference.value=null;cardVisible.value=false;client.reset()
  const results=await Promise.allSettled([
    readCurrentPreparation(),
    request({path:familyPath+'/reference-meal-plans/'+date+'/current'}),
    request({path:familyPath+'/daily-arrangements/'+date}),
  ])
  if(!current())return
  mealsLoading.value=false
  if(scope!==storageContext()||results.some(r=>r.status==='rejected'&&[401,403].includes(Number(r.reason?.code)))){
    clearPrivate();entryReady.value=false;entryError.value='身份或成员授权已变化，请重新读取当前档案。'
    if(!getSession()?.token)uni.reLaunch({url:'/pages/index/index'})
    return
  }
  const prepared=results[0].status==='fulfilled'?results[0].value:null
  preparedThreadId.value=prepared?.thread_id||''
  const reference=results[1].status==='fulfilled'?results[1].value.data:null
  if(isReferencePlan(reference))latestReference.value=reference
  const arrangement=results[2].status==='fulfilled'?results[2].value.data:null
  if(arrangement?.status==='ready'){
    try{if(arrangement.date!==date)throw new Error('餐单日期不符');client.adopt(arrangement);cardVisible.value=true}
    catch{mealReadError.value='已保存餐单的内容尚未读完整，请重新读取。'}
  }
  if(results.some(r=>r.status==='rejected'))mealReadError.value='暂时无法读取已有餐单，请重新读取。'
}
onMounted(load);onShow(()=>{if(!disposed)void load()})
onHide(()=>{historyOpen.value=false;if(scrollTimer!==null)clearTimeout(scrollTimer);scrollTimer=null;mealPlanReady.value=false;entryReady.value=false;visible=false;epoch++;loading=null;profileLoading.value=false;mealsLoading.value=false;voiceRef.value?.cancel();flow.hide();client.reset();familyClient.reset();cardVisible.value=false;familyPanel.value=false;familySelection.value=null})
onUnmounted(()=>{if(scrollTimer!==null)clearTimeout(scrollTimer);disposed=true;epoch++;draftVersion++;client.dispose();familyClient.dispose();flow.hide()})
function openMeal(meal){uni.navigateTo({url:'/pages/shop/index?meal='+meal.type+'&date='+state.date+'&arrangement='+encodeURIComponent(state.arrangement.id)+'&version='+state.arrangement.version})}
function shop(arrangement){if(arrangement)uni.navigateTo({url:'/pages/shop/index?daily=1&date='+arrangement.date+'&arrangement='+encodeURIComponent(arrangement.id)+'&version='+arrangement.version})}
function archives(){uni.navigateTo({url:'/pages/profile/index'})}
function memberArchive(){const member=props.route.memberId?profile.value?.members.find(m=>m.healthMemberId===props.route.memberId):profile.value?.members.find(m=>m.id===profile.value.selfMemberId);if(!member){chatError.value='当前成员档案不可访问，请返回家庭档案核查。';return}uni.navigateTo({url:'/pages/profile/member?id='+encodeURIComponent(member.id)})}
async function members(ids){const type=selectedMeal.value.type;selectedMeal.value=null;await client.changeMembers(type,ids);cardVisible.value=state.phase==='ready';if(familyPanel.value&&familyState.date===state.date)await familyClient.load(state.date)}
async function sendQuestion(explicitType){
  if(conversationReadOnly.value){chatError.value='这段每日对话已归档，请新建对话继续。';return}
  if(!entryReady.value){chatError.value=entryError.value||'对话资料尚未读到，请重新读取。';return}
  if(!hasDraftContent.value||chatBusy.value||draftSaving.value||draftError.value)return
  if(!profile.value){chatError.value=entryError.value||'咨询资料尚未读到，请重新读取咨询资料后再发送。';return}
  const scope=storageContext(),text=question.value.trim(),image=draftImage.value&&{...draftImage.value}
  sending.value=true;chatError.value=''
  let stage='select-task'
  try{
    const mealIntent=!props.route.taskType&&!image?parseChatMealIntent(text,localDate()):null
    // A revision stays in the selected plan's thread, preserving its date and
    // participants. A fresh arrangement still creates its own explicit choice.
    const referenceAdjustment=!props.route.taskType&&!image&&task.value.taskType==='reference_meal_preview'&&!!referenceSelection&&
      !/(?:换(?:个|一个)?话题|换个问题|(?:取消|停止|不用|不需要|不想|不要)(?:再|继续)?(?:配餐|安排|生成|制定))/.test(text)&&
      !/(?:^|[，。！？；、\s])(?:请)?(?:为我|给我|帮我|给全家|为全家|帮全家)?(?:安排|生成|制定|配一)/.test(text)&&
      (task.value.result?.type==='needs_input'||/换(?:菜|成|掉|一|个)|替换|改(?:成|为|一下)|调整|重新(?:生成|安排|做)|再(?:生成|安排|做)|去掉|不放|不吃|不含|不要|加(?:一|点|些)|少(?:一|点|些)|多(?:一|点|些)/.test(text))
    if((explicitType==='reference_meal_preview'||referenceAdjustment)&&mealIntent?.unsupportedDate)throw new Error('请明确选择今天或明天的一日餐单，原问题已保留。')
    // Conversation stays conversational. Structured, saved plans are an explicit
    // follow-up action; asking for ideas must not demand a supplied recipe first.
    const type=explicitType==='reference_meal_preview'||referenceAdjustment?'reference_meal_preview':Object.hasOwn(HEALTH_TEXT_TASKS,props.route.taskType)?props.route.taskType:'consultation'
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
    let referenceFollowUp=false
    if(type==='reference_meal_preview'){
      stage='select-reference'
      const selection=chooseReference(profile.value,text,{today:localDate(),tomorrow:localDate(new Date(Date.now()+86400000)),memberId:props.route.memberId,...(referenceAdjustment?{previous:referenceSelection}:{})})
      referenceFollowUp=referenceAdjustment&&JSON.stringify(selection)===JSON.stringify(referenceSelection)
      referenceSelection=selection
    }
    stage='open-task'
    if(type==='reference_meal_preview'&&!referenceFollowUp||!task.value.memberId||task.value.taskType!==type)await restoreChat(type)
    if(disposed||!visible||scope!==storageContext())return
    if(task.value.canRetry){chatError.value='上次问题的提交结果尚未确认，请先点击“重试原问题”或重新读取。';return}
    if(!task.value.available){chatError.value=task.value.error||task.value.notice||chatError.value||'请先在该成员的家庭档案中完成资料和咨询同意。';return}
    if(!task.value.entry?.thread_id){stage='create-conversation';await flow.createEntry();rememberThread();if(task.value.entry?.thread_id)await restoreChat(type)}
    rememberThread()
    if(disposed||!visible||scope!==storageContext())return
    if(!task.value.entry?.thread_id){chatError.value=task.value.error||task.value.notice||'咨询尚未建立，请重新读取后再发送。';return}
    stage='read-image'
    const images=image?[await chatImageContent(image)]:[]
    if(disposed||!visible||scope!==storageContext())return
    stage='queue-message'
    const user=reactive({id:newHealthRequestId(),role:'user',text,createdAt:new Date().toISOString(),status:'sending',...(image?{image}: {})})
    pendingUser=user;submittedDraft={text,path:image?.localPath||'',requestId:''};messages.value.push(user)
    rememberThread()
    stage='save-draft'
    scopedStorage.setStorageSync('homepage-chat-task',{memberId:task.value.memberId,type,date:localDate(),conversationId:conversationId.value,...(type==='reference_meal_preview'?{selection:referenceSelection}:{})});desiredType=type
    stage='scroll-message'
    await scrollLatest()
    stage='submit-task'
    const accepted=await flow.submit(text,false,images)
    if(disposed||!visible||scope!==storageContext())return
    user.status=accepted?'sent':task.value.canRetry?'unknown':'failed'
    if(accepted&&!['failed','rejected'].includes(task.value.status)){if(question.value.trim()===text)question.value='';if(draftImage.value?.localPath===(image?.localPath||''))removeDraft()}
    else chatError.value=task.value.error||'回复尚未完成，原问题和图片已保留。'
  }catch(e){if(!disposed&&scope===storageContext()){
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
  finally{pendingUser=null;sending.value=false;if(!disposed&&visible&&scope===storageContext()&&chatError.value)uni.showToast({title:chatError.value,icon:'none',duration:3500})}
}
async function retryQuestion(){chatError.value='';await flow.submit('',true);await scrollLatest()}
async function restartChat(){
  if(chatBusy.value||draftSaving.value)return
  const scope=storageContext(),text=question.value,image=draftImage.value,error=draftError.value
  await newConversation()
  if(disposed||!visible||scope!==storageContext())return
  question.value=text;draftImage.value=image;draftError.value=error
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
async function newConversation(){
  if(chatBusy.value||voiceBusy.value||draftSaving.value)return
  if(props.route.taskType){uni.reLaunch({url:'/pages/chat/index?newConversation=1'});return}
  stashConversationDraft();resetConversationView()
  conversationId.value=newHealthRequestId();conversationThreadId.value='';conversationBusinessDate.value='';newConversationWelcome.value=true
  const id=profile.value?.members.find(m=>m.id===profile.value.selfMemberId)?.healthMemberId
  if(id)saveConversation(id)
  historyOpen.value=false;switchingConversation.value=true
  try{await restoreChat('consultation')}finally{switchingConversation.value=false}
}
async function selectConversation(row){
  if(chatBusy.value||voiceBusy.value||draftSaving.value||row.unavailable)return
  const id=profile.value?.members.find(m=>m.id===profile.value.selfMemberId)?.healthMemberId
  if(!id||row.member_id!==id||row.agent_slug!=='health-consultation')return
  if(props.route.taskType){scopedStorage.setStorageSync('homepage-conversation',{id:row.thread_id,threadId:row.thread_id,memberId:id,businessDate:row.business_date||''});uni.reLaunch({url:'/pages/chat/index'});return}
  stashConversationDraft();resetConversationView()
  const scope=storageContext(),mine=epoch
  const saved=scopedStorage.getStorageSync('conversation-index:'+row.thread_id)
  conversationId.value=saved?.memberId===id?saved.id:row.thread_id
  conversationThreadId.value=row.thread_id;conversationBusinessDate.value=row.business_date||'';newConversationWelcome.value=false
  saveConversation(id);historyOpen.value=false;switchingConversation.value=true
  scopedStorage.setStorageSync('homepage-chat-task',{memberId:id,type:'consultation',date:localDate(),conversationId:conversationId.value})
  try{
    await restoreChat('consultation')
    if(scope!==storageContext()||mine!==epoch||task.value.invalidated)return
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
function askPrompt(text){if(text==='看看我的饮食记录'){uni.navigateTo({url:'/pages/records/index'});return}desiredType='consultation';question.value=text;void sendQuestion()}
function generateReference(){question.value='请帮我安排今天的三餐';void sendQuestion('reference_meal_preview')}

</script>
<template>
<NutritionistLayout :voice-busy="voiceBusy" :scroll-target="scrollTarget" :history-open="historyOpen" @history="history" @profile="uni.navigateTo({url:'/pages/my/index'})" @shortcut="shortcut">
 <template #default>
  <view v-if="presentation.initialResults" class="analysis-message"><AiAnswer :text="state.arrangement.analysis.text"/></view>
  <DailyArrangementCard v-if="cardVisible && presentation.initialResults" :arrangement="state.arrangement" :disabled="state.busy" @open="openMeal" @members="selectedMeal=$event" @shop="shop"/>
  <ChatWelcome v-if="presentation.welcome" :prompts="prompts" :disabled="chatBusy" @ask="askPrompt" @today="shortcut('today')"/>
  <view v-for="message in messages" :id="'message-'+message.id" :key="message.id" class="message-row" :class="message.role">
   <view class="message-content"><view class="bubble"><image v-if="message.image" class="chat-message-image" :src="message.image.localPath" mode="widthFix" @click="previewChatImage(message.image)"/><AiAnswer v-if="message.role==='assistant'&&message.text" :text="message.text" :citations="message.citations||[]"/><text v-else-if="message.text" selectable>{{message.text}}</text>
    <text v-if="message.status==='unknown'" class="chat-error">提交结果待确认，请勿重复发送。</text>
    <text v-if="message.status==='failed'||message.status==='rejected'" class="chat-error">服务器已收到本条问题，但处理未完成。</text><text v-if="message.status==='cancelled'" class="chat-error">已取消本次问题。</text>
   </view><HealthChatBusinessCard v-if="message.business" :result="message.business" :member-id="message.memberId||task.memberId"/><ConversationFoodPackages v-if="message.purchaseRequestId" :offers="message.purchaseOffers" :request-id="message.purchaseRequestId"/></view>
  </view>
  <view v-if="mealReplyActions&&!chatBusy&&!conversationReadOnly" class="reply-actions" aria-label="继续安排饮食">
   <button @click="question='请换几道菜，继续沿用已确认的饮食限制。'">换几道菜</button>
   <button @click="generateReference">整理成今日餐单</button>
  </view>
  <view v-if="liveAnswer" id="stream-answer" class="message-row assistant live-answer"><view class="message-content"><view class="bubble"><AiAnswer :text="task.streamText" streaming/></view></view></view>
  <view v-if="familyPanel" class="dialogue-status"><text>家庭餐单 · {{familyState.date}}</text><text>按这餐实际参加的成员核对家庭安排，每位成员的资料和权限由服务端检查。</text><text v-if="familyState.busy">正在读取家庭安排…</text><text v-if="familyState.error" class="chat-error">{{familyState.error}}</text><button v-if="familyState.error" :disabled="familyState.busy" @click="familyPlan('',true)">重新读取家庭餐单</button><DailyArrangementCard v-if="familyState.phase==='ready'" :arrangement="familyState.arrangement" family :disabled="familyState.busy" @open="openFamilyMeal" @members="familySelection={type:$event.type,ids:$event.members.map(m=>m.id),question:''}" @shop="shop"/><button @click="familyPanel=false">收起家庭餐单</button></view>
  <view v-if="entryReady&&!profileLoading&&chatBusy" id="reply-progress" class="reply-progress" role="status" aria-live="polite"><view class="progress-dot"/><text>{{progressText}}</text><button v-if="canCancel" class="stop-generation" @click="flow.cancelRequest()">停止</button></view><text v-if="entryError||chatError" class="chat-error" role="alert">{{entryError||chatError}}</text>
  <button v-if="!profile&&!profileLoading" class="secondary-button" @click="load()">重新读取咨询资料</button>
  <view v-if="task.error||task.notice||task.canRetry||canCancel" class="dialogue-status"><text>{{task.error||task.notice}}</text><button v-if="task.requestId&&task.result?.type!=='error'" @click="flow.refresh()">重新读取本次回复</button><button v-if="task.canRetry" @click="retryQuestion">重试原问题</button><button v-if="canCancel" @click="flow.cancelRequest()">取消当前问题</button></view>
  <button v-if="(task.invalidated||task.status==='failed')&&!route.taskType" class="secondary-button" :disabled="chatBusy||draftSaving" @click="restartChat">开始新咨询</button>
  <button v-if="entryReady&&profile&&(!task.available||needsProfileLink)" class="secondary-button" @click="memberArchive">查看该成员档案</button><view v-if="task.consentOption" class="dialogue-status"><text>本次咨询处理方：{{task.consentOption.processor}}；政策版本：{{task.consentOption.policyVersion}}。</text><checkbox-group @change="consentChecked=$event.detail.value.includes('yes')"><label><checkbox value="yes" :checked="consentChecked"/>同意本次咨询的数据处理</label></checkbox-group><button :disabled="!consentChecked||chatBusy" @click="consent">同意并继续咨询</button></view>
 </template>
 <template #composer>
  <view v-if="conversationReadOnly" class="archived-conversation"><text>这段每日对话已归档，记录仍可查看。</text><button :disabled="chatBusy" @click="newConversation">新对话继续聊</button></view>
  <template v-else>
  <view v-if="draftImage" class="image-draft"><view class="draft-thumbnail"><image :src="draftImage.localPath||draftImage.path" mode="aspectFill" @click="previewChatImage(draftImage)"/><button aria-label="移除待发送图片" @click="removeDraft">×</button></view><view><text>{{draftSaving?'正在准备图片…':draftError||'可直接发送图片，也可以补充文字'}}</text><button v-if="draftError" @click="prepareDraft()">重新准备图片</button></view></view>
  <view class="composer"><button class="input-icon" aria-label="打开相机或选择照片" :disabled="chatBusy||voiceBusy||draftSaving" @click="camera"><AppIcon name="camera" :size="38"/></button><VoiceInput v-if="voiceMode" ref="voiceRef" :disabled="chatBusy||draftSaving" @send="sendVoice" @busy="voiceBusy=$event"/><input v-else v-model="question" :disabled="chatBusy" placeholder="问问家庭营养师…" confirm-type="send" @confirm="sendQuestion"/>
   <button v-if="voiceMode" class="input-icon" aria-label="切换文字输入" :disabled="voiceBusy" @click="voiceMode=false"><view class="keyboard-icon"><view/><view/><view/></view></button>
   <button v-else-if="hasDraftContent" class="send-button" aria-label="发送" :disabled="chatBusy||draftSaving||!!draftError" @click="sendQuestion"><AppIcon name="arrow" :size="30"/></button><button v-else class="input-icon" aria-label="切换语音输入" @click="voiceMode=true"><AppIcon name="mic" :size="36"/></button>
  </view>
  </template>
 </template>
 <template #overlays>
  <ChatConversationDrawer :open="historyOpen" :member-id="historyMemberId" :active-thread-id="conversationThreadId" :busy="chatBusy||voiceBusy||draftSaving" :display-name="profile?.members.find(m=>m.id===profile.selfMemberId)?.name||'我的'" @close="historyOpen=false" @new="newConversation" @select="selectConversation" @profile="historyOpen=false;uni.navigateTo({url:'/pages/my/index'})"/>
  <view v-if="inlineTodayOpen" class="meal-sheet-mask" @click.self="inlineTodayOpen=false">
   <view class="meal-sheet" role="dialog" aria-label="今日餐单">
    <view class="inline-today-head"><text>今日餐单</text><button aria-label="关闭今日餐单" @click="inlineTodayOpen=false">×</button></view>
    <scroll-view class="meal-sheet-content" scroll-y>
     <ReferenceMealPlanCard v-if="latestReference?.plan_date===localDate()" :plan="latestReference"/>
     <DailyArrangementCard v-else-if="state.phase==='ready'" :arrangement="state.arrangement" :disabled="state.busy" @open="openMeal" @members="selectedMeal=$event" @shop="shop"/>
     <text v-else-if="mealsLoading||state.busy" class="composer-note">正在读取已保存的餐单…</text>
     <view v-else-if="!mealReadError&&!state.error" class="reference-empty"><text class="composer-note">今天还没有保存餐单。可以先聊聊想吃什么，再整理成餐单。</text><button class="secondary-button" :disabled="chatBusy||conversationReadOnly" @click="inlineTodayOpen=false;generateReference()">生成今日餐单</button></view>
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
.reply-actions{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 24px}.reply-actions button{margin:0;padding:8px 14px;min-height:40px;border:1px solid #e4e8e3;border-radius:20px;background:#f7f9f6;color:#3b5544;font-size:13px;line-height:1.6}.reply-actions button:after{border:0}.archived-conversation{display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:12px;color:#777;line-height:1.7}.archived-conversation button{flex-shrink:0;padding:8px 12px;min-height:44px;border-radius:8px;background:#111;color:#fff;font-size:13px}.archived-conversation button:after{border:0}.meal-sheet-mask{position:fixed;inset:0;z-index:70;display:flex;align-items:flex-end;background:rgba(0,0,0,.35)}.meal-sheet{display:flex;flex-direction:column;box-sizing:border-box;width:100%;max-height:80vh;padding:12px 20px calc(env(safe-area-inset-bottom) + 20px);border-radius:24px 24px 0 0;background:#fff}.meal-sheet-content{flex:1;min-height:0;max-height:65vh}.meal-sheet .inline-today-head{flex-shrink:0;padding-bottom:8px;font-size:18px;color:#222}.meal-sheet .inline-today-head button{font-size:28px;justify-content:center;min-width:44px}.reference-empty{padding:20px 0}
.message-row{display:flex;width:100%;gap:0;margin:28px 0;color:#202020}.message-content{width:100%;min-width:0;max-width:100%}.message-row.user{justify-content:flex-end;padding-left:42px;box-sizing:border-box}.user .message-content{width:auto;max-width:100%;flex:0 1 auto}.bubble{font-size:16px;line-height:1.8;white-space:pre-line;overflow-wrap:anywhere;word-break:break-word;padding:0;border:0;background:transparent;color:#242424;max-width:100%;border-radius:0}.user .bubble{display:block;width:auto;box-sizing:border-box;padding:12px 16px;border-radius:10px 2px 10px 10px;background:#111;color:#fff;font-size:16px;line-height:1.6}.analysis-message{margin:24px 0 22px;padding:0}.analysis-copy{display:block;font-size:16px;line-height:1.85;color:#282828;white-space:pre-line;overflow-wrap:anywhere}.citation{display:block;font-size:12px;line-height:1.75;color:#777;margin-top:10px}.user .citation{color:#d0d0d0}
.dialogue-status{padding:14px 0;margin:18px 0;border-bottom:1px solid #ededed;background:transparent;font-size:14px;line-height:1.8;color:#666}.dialogue-status>text{display:block}.dialogue-status button,.secondary-button{display:inline-flex;align-items:center;justify-content:center;min-height:44px;font-size:14px;color:#333;background:transparent;border:1px solid #ddd;border-radius:8px;margin:10px 10px 0 0;padding:7px 12px;line-height:1.5}.dialogue-status button:after,.secondary-button:after{border:0}.reply-progress{display:flex;align-items:center;gap:9px;min-height:28px;margin:22px 0;font-size:14px;line-height:1.6;color:#888}.thinking-dots{display:flex;align-items:center;gap:3px}.thinking-dots>view{width:3px;height:3px;border-radius:50%;background:#999;animation:reply-pulse 1.3s infinite ease-in-out}.thinking-dots>view:nth-child(2){animation-delay:.16s}.thinking-dots>view:nth-child(3){animation-delay:.32s}.chat-error{display:block;margin-top:12px;font-size:13px;line-height:1.7;color:#8d4c40}
.composer{display:flex;align-items:center;gap:8px;padding:0;background:#fff;border:0;border-radius:0;min-height:50px}.composer input{flex:1;min-width:0;height:48px;box-sizing:border-box;padding:0 13px;border:1px solid #e0e0e0;border-radius:8px;background:#fff;color:#222;font-size:16px;line-height:1.5}.input-icon,.send-button{display:flex;flex-shrink:0;align-items:center;justify-content:center;min-width:44px;width:44px;min-height:48px;height:48px;border:0;border-radius:0;background:transparent;color:#80848a;padding:0}.input-icon:after,.send-button:after{border:0}.composer>.input-icon:first-child{margin-left:-8px;width:44px;min-width:44px}.send-button{color:#fff;background:#111;border-radius:8px;min-height:44px;height:44px}.composer :deep(.voice-input){flex:1;width:auto;min-width:0;height:48px;border:1px solid #e0e0e0;box-sizing:border-box;border-radius:8px;background:#fff}.composer :deep(.hold-to-talk){height:46px;font-size:16px}.keyboard-icon{width:20px;height:15px;border:1.5px solid currentColor;border-radius:3px;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:3px}.keyboard-icon>view{width:13px;border-top:1px dotted currentColor}.keyboard-icon>view:last-child{width:9px;border-top-style:solid}
.chat-message-image{display:block;width:210px;max-width:100%;height:auto;border-radius:8px;margin-bottom:8px}.image-draft{display:flex;align-items:center;gap:12px;padding:8px 0 14px;font-size:13px;line-height:1.6;color:#777}.draft-thumbnail{position:relative;flex-shrink:0}.draft-thumbnail image{width:56px;height:56px;border-radius:8px}.draft-thumbnail button{position:absolute;top:-7px;right:-7px;width:24px;height:24px;display:flex;align-items:center;justify-content:center;border-radius:50%;background:#fff;color:#444}.image-draft>view+view{flex:1}.image-draft button{font-size:13px;min-height:24px}.inline-today{padding:0;margin:22px 0;max-height:none;overflow:visible}.inline-today-head{display:flex;align-items:center;justify-content:space-between;color:#777;font-size:13px}.inline-today-head button{display:flex;align-items:center;min-height:44px;background:transparent;color:#444;font-size:13px}.inline-today :deep(.daily-arrangement-card){margin-top:0}.composer-note{display:block;font-size:12px;color:#888;line-height:1.7;margin-top:8px}.inline-error{font-size:13px;color:#8d4c40}.section-title{font-size:18px}.sheet-mask .sheet{background:#fff;color:#222}.sheet-mask .composer-note{text-align:left}
@keyframes reply-pulse{0%,70%,100%{opacity:.3}35%{opacity:1}}@media(prefers-reduced-motion:reduce){.thinking-dots>view{animation:none}}@media(max-width:350px){.bubble,.analysis-copy{font-size:15px}.message-row{margin:24px 0}.message-row.user{padding-left:30px}.user .bubble{padding:11px 14px;font-size:15px}.composer input{font-size:15px;padding-left:11px}.input-icon,.send-button{min-width:44px;width:44px}}

.progress-dot{width:7px;height:7px;flex-shrink:0;border-radius:50%;background:#558367;animation:progress-breathe 1.4s ease-in-out infinite}.stop-generation{flex-shrink:0;padding:5px 12px;min-height:36px;border:1px solid #dce7dd;border-radius:18px;background:#fff;color:#48614d;font-size:12px}.live-answer{padding-bottom:5px}@keyframes progress-breathe{0%,100%{opacity:.4}50%{opacity:1}}@media(prefers-reduced-motion:reduce){.progress-dot{animation:none}}
</style>
