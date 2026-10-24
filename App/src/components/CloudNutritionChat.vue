<script setup>
import { computed, reactive, ref, nextTick, onMounted, onUnmounted } from 'vue'
import { onShow, onHide } from '@dcloudio/uni-app'
import NutritionistLayout from './NutritionistLayout.vue'
import AppIcon from './AppIcon.vue'
import DinerPicker from './DinerPicker.vue'
import HealthChatBusinessCard from './HealthChatBusinessCard.vue'
import DailyArrangementCard from './DailyArrangementCard.vue'
import ConversationFoodPackages from './ConversationFoodPackages.vue'
import VoiceInput from './VoiceInput.vue'
import { loadCloudProfile } from '../services/cloud-profile.js'
import { createDailyArrangementClient, dailyArrangementState } from '../services/daily-arrangement-client.js'
import { request } from '../services/request.js'
import { storageContext, scopedStorage } from '../services/storage.js'
import { getSession } from '../services/session.js'
import { createHealthTaskFlow, HEALTH_TEXT_TASKS, newHealthRequestId } from '../services/health-task-flow.js'
import { persistChatImage, previewChatImage } from '../services/chat-images.js'
import { readChatSnapshot, chatImageContent } from '../services/cloud-chat.js'
import { localDate } from '../utils/meal-state.js'

const props=defineProps({route:{type:Object,default:()=>({})}})
const state=reactive(dailyArrangementState()),profile=ref(null),cardVisible=ref(false),selectedMeal=ref(null)
const profileLoading=ref(false)
const needsProfileLink=computed(()=>profile.value&&!props.route.memberId&&!profile.value.members.some(m=>m.relation==='本人'&&m.healthMemberId))
const question=ref(''),chatError=ref(''),messages=ref([]),task=ref({}),consentChecked=ref(false)
const voiceMode=ref(false),voiceBusy=ref(false),voiceRef=ref(null),communityOpen=ref(false),scrollTarget=ref(''),inlineTodayOpen=ref(false)
const draftImage=ref(null),draftSaving=ref(false),draftError=ref('')
const familyState=reactive(dailyArrangementState()),familyPanel=ref(false),familySelection=ref(null),familyIntent=ref('')
const prompts=['今晚全家吃什么？','给我安排明天早餐','看看我的饮食记录','糖尿病家庭怎么吃？']
const chatBusy=computed(()=>profileLoading.value||sending.value||familyState.busy||task.value.busy||task.value.loading||['queued','dispatched','pending','running','cancel_requested'].includes(task.value.status))
const sending=ref(false),hasDraftContent=computed(()=>!!question.value.trim()||!!draftImage.value)
const canCancel=computed(()=>task.value.requestId&&!task.value.submitUnknown&&['queued','dispatched','pending','running'].includes(task.value.status))
let disposed=false,visible=true,loading=null,epoch=0,pageScope=storageContext(),flowScope=pageScope,draftVersion=0,openingCamera=false,pendingUser=null,submittedDraft=null,desiredType='consultation',restoring=false
const flow=createHealthTaskFlow({daily:true,onChange:next=>{
  if(disposed||flowScope!==storageContext())return
  task.value=next
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
    const message={id,requestId:next.requestId,role:'assistant',createdAt:new Date().toISOString(),citations:result.citations||[],
      text:result.type==='answer'?result.text:result.type==='needs_input'?result.questions.join('\n'):result.type==='error'?'这次回复未完成，请保留原问题，重新读取处理结果。':'餐单结果已返回，请核对后决定是否使用。',
      memberId:next.memberId,purchaseOffers:result.purchaseOffers,purchaseRequestId:result.purchaseOffers?.length?next.requestId:'',error:result.type==='error',business:result.type==='business'?result:null}
    if(index<0)messages.value.push(message);else messages.value[index]={...messages.value[index],...message}
    if(!restoring)void scrollLatest()
  }
}})
const client=createDailyArrangementClient({state,send:request,context:()=>({scope:storageContext(),familyId:getSession()?.householdId}),storage:scopedStorage,newId:newHealthRequestId})
const familyClient=createDailyArrangementClient({state:familyState,send:request,context:()=>({scope:storageContext(),familyId:getSession()?.householdId}),storage:scopedStorage,newId:newHealthRequestId})
async function familyPlan(text,retry=false){
  text=retry?familyIntent.value:String(text||'');if(!retry)familyIntent.value=text
  const scope=storageContext(),mine=epoch
  const date=/明天|明日/.test(text)?localDate(new Date(Date.now()+86400000)):localDate()
  const type=/早餐|早上/.test(text)?'breakfast':/午餐|中午/.test(text)?'lunch':'dinner'
  familyPanel.value=true;await familyClient.load(date,retry)
  if(disposed||!visible||mine!==epoch||scope!==storageContext())return
  if(familyState.phase==='ready')familySelection.value={type,ids:profile.value.members.map(m=>m.id),question:text}
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
function clearPrivate(){epoch++;loading=null;profileLoading.value=false;flow.hide();client.reset();familyClient.reset();familyPanel.value=false;familySelection.value=null;messages.value=[];question.value='';chatError.value='';profile.value=null;task.value={};selectedMeal.value=null;removeDraft();pendingUser=null;submittedDraft=null;voiceRef.value?.cancel();voiceBusy.value=false;voiceMode.value=false;cardVisible.value=false}
function rememberThread(){
  if(flowScope!==storageContext()||props.route.taskType||!task.value.entry?.thread_id||!task.value.memberId)return
  const key=`homepage-chat-threads:${task.value.memberId}:${localDate()}`,old=scopedStorage.getStorageSync(key)||[]
  const row={thread_id:task.value.entry.thread_id,task_type:task.value.taskType}
  scopedStorage.setStorageSync(key,[...old.filter(t=>t.thread_id!==row.thread_id),row].slice(-20))
}
async function restoreChat(type=desiredType){
  if(!profile.value)return
  const scope=storageContext(),ticket=epoch
  const id=props.route.memberId||profile.value.members.find(m=>m.relation==='本人')?.healthMemberId
  if(!id){chatError.value='请在“我的 → 资料管理 → 我的健康资料”核对本人资料，完成后即可咨询。';return}
  const selection=type==='diet_analysis'?{record_id:props.route.recordId,source_version:Number(props.route.version)}:props.route.indicatorChoice==='1'?scopedStorage.getStorageSync(`indicator-choice:${id}:${type}`):null
  flowScope=scope;restoring=true
  try{
    await flow.open(id,type,selection)
    if(disposed||ticket!==epoch||scope!==storageContext())return
    if(task.value.entry?.thread_id){
      rememberThread()
      const currentThread=task.value.entry.thread_id
      const pointers=props.route.taskType?[{thread_id:currentThread}]:(scopedStorage.getStorageSync(`homepage-chat-threads:${id}:${localDate()}`)||[{thread_id:currentThread}])
      const results=await Promise.allSettled(pointers.map(async p=>({...(await readChatSnapshot(p.thread_id)),threadId:p.thread_id})))
      if(disposed||ticket!==epoch||scope!==storageContext())return
      const invalid=[]
      results.forEach((r,i)=>{if(r.status==='rejected'){if(![403,404,409,410].includes(Number(r.reason?.code)))throw r.reason;invalid.push(pointers[i].thread_id)}})
      if(invalid.length&&!props.route.taskType){
        scopedStorage.setStorageSync(`homepage-chat-threads:${id}:${localDate()}`,pointers.filter(p=>!invalid.includes(p.thread_id)))
        chatError.value='部分旧对话的授权或资料来源已变化，已停止展示；其他有效对话仍可读取。'
      }
      if(results.some((r,i)=>pointers[i].thread_id===currentThread&&r.status==='rejected'&&[409,410].includes(Number(r.reason?.code))))flow.invalidateThread()
      const snapshots=results.filter(r=>r.status==='fulfilled').map(r=>r.value)
      const saved=snapshots.flatMap(p=>p.messages.filter(m=>props.route.taskType||!m.createdAt||new Date(Date.parse(m.createdAt)+8*3600000).toISOString().slice(0,10)===localDate()).map(m=>({...m,memberId:id,threadId:p.threadId}))).sort((a,b)=>(Date.parse(a.createdAt)||0)-(Date.parse(b.createdAt)||0))
      const live=messages.value.filter(m=>m.requestId===task.value.requestId&&(m.status==='unknown'||m.role==='assistant'&&task.value.result))
      messages.value=[...saved,...live.filter(m=>!saved.some(row=>m.requestId&&row.requestId===m.requestId&&row.role===m.role))]
      const active=snapshots.find(s=>s.threadId===currentThread)?.runs.find(r=>['queued','dispatched','pending','running','cancel_requested'].includes(r.status))
      if(active?.request_id&&!task.value.requestId)await flow.restoreRequest(active.request_id)
      await scrollLatest()
    }else if(!task.value.requestId)messages.value=[]
  }catch(e){if(!disposed&&ticket===epoch&&scope===storageContext()){chatError.value=e.message;if([401,403,404,409,410].includes(Number(e.code))){messages.value=[];question.value='';removeDraft();submittedDraft=null}}}
  finally{restoring=false}
}
async function load(retry=false){
  visible=true
  if(pageScope!==storageContext()){clearPrivate();pageScope=storageContext();flowScope=pageScope}
  if(loading)return loading
  const mine=++epoch,scope=storageContext()
  profileLoading.value=true
  loading=(async()=>{try{
    const next=await loadCloudProfile()
    if(disposed||mine!==epoch||scope!==storageContext())return
    profile.value=next
    profileLoading.value=false
    chatError.value=''
    if(props.route.question&&!question.value)question.value=String(props.route.question).slice(0,4000)
    if(props.route.indicatorChoice==='1'&&!question.value)question.value='请回顾我选择的实测记录，说明还需要补充哪些测量信息。'
    if(!next.onboarded){uni.redirectTo({url:'/pages/onboarding/index'});return}
    const resume=scopedStorage.getStorageSync('homepage-chat-task')
    desiredType=Object.hasOwn(HEALTH_TEXT_TASKS,props.route.taskType)?props.route.taskType:resume?.memberId===next.members.find(m=>m.relation==='本人')?.healthMemberId&&resume?.date===localDate()?resume.type:'consultation'
    await Promise.all([client.load(localDate(),retry===true),restoreChat()])
    if(disposed||mine!==epoch)return
    if(scope!==storageContext()){clearPrivate();uni.reLaunch({url:'/pages/index/index'});return}
    cardVisible.value=state.phase==='ready'
  }catch(e){if(!disposed&&mine===epoch){if([401,403].includes(Number(e.code))||!getSession()?.token){clearPrivate();if(!getSession()?.token){uni.reLaunch({url:'/pages/index/index'});return}}state.error=e.message;state.phase='error';state.busy=false}}
  finally{if(mine===epoch){loading=null;profileLoading.value=false}}})()
  return loading
}
onMounted(load);onShow(()=>{if(!disposed)void load()})
onHide(()=>{visible=false;epoch++;loading=null;profileLoading.value=false;voiceRef.value?.cancel();flow.hide();client.reset();familyClient.reset();cardVisible.value=false;familyPanel.value=false;familySelection.value=null})
onUnmounted(()=>{disposed=true;epoch++;draftVersion++;client.dispose();familyClient.dispose();flow.hide()})
function openMeal(meal){uni.navigateTo({url:'/pages/shop/index?meal='+meal.type+'&date='+state.date+'&arrangement='+encodeURIComponent(state.arrangement.id)+'&version='+state.arrangement.version})}
function shop(arrangement){if(arrangement)uni.navigateTo({url:'/pages/shop/index?daily=1&date='+arrangement.date+'&arrangement='+encodeURIComponent(arrangement.id)+'&version='+arrangement.version})}
function archives(){uni.navigateTo({url:'/pages/profile/index'})}
function consultationProfile(){uni.navigateTo({url:'/pages/settings/health-profile'})}
async function members(ids){const type=selectedMeal.value.type;selectedMeal.value=null;await client.changeMembers(type,ids);cardVisible.value=state.phase==='ready';if(familyPanel.value&&familyState.date===state.date)await familyClient.load(state.date)}
async function sendQuestion(){
  if(!hasDraftContent.value||chatBusy.value||draftSaving.value||draftError.value)return
  if(!profile.value){chatError.value=state.error||'咨询资料尚未读到，请重新读取咨询资料后再发送。';return}
  const scope=storageContext(),text=question.value.trim(),image=draftImage.value&&{...draftImage.value}
  sending.value=true;chatError.value=''
  try{
    if(!props.route.taskType&&!image&&/全家|一家|家人|家庭/.test(text)&&/安排.*(餐|吃)|吃什么|明天早餐|今晚.*吃|规划|推荐.*餐/.test(text)){if(!/^(今晚|今天|明天)(全家|一家人)(早餐吃什么|午餐吃什么|晚餐吃什么|吃什么)[？?！!。]*$/.test(text)){chatError.value='这条家庭安排还包含未能直接承接的要求，原问题已保留。请先从家庭餐单核对日期、参加成员及档案中的饮食限制。';return}await familyPlan(text);return}
    const type=Object.hasOwn(HEALTH_TEXT_TASKS,props.route.taskType)?props.route.taskType:image?'consultation':/安排.*(餐|吃)|吃什么|明天早餐|今晚.*吃/.test(text)?'meal_preview':'consultation'
    if(!task.value.memberId||task.value.taskType!==type)await restoreChat(type)
    if(disposed||!visible||scope!==storageContext())return
    if(task.value.canRetry){chatError.value='上次问题的提交结果尚未确认，请先点击“重试原问题”或重新读取。';return}
    if(!task.value.available){chatError.value=task.value.error||task.value.notice||chatError.value||'咨询暂未就绪，请重新读取咨询资料后再发送。';return}
    if(!task.value.entry?.thread_id){await flow.createEntry();rememberThread();if(task.value.entry?.thread_id)await restoreChat(type)}
    rememberThread()
    if(disposed||!visible||scope!==storageContext()||!task.value.entry?.thread_id)return
    const images=image?[await chatImageContent(image)]:[]
    if(disposed||!visible||scope!==storageContext())return
    const user=reactive({id:newHealthRequestId(),role:'user',text,createdAt:new Date().toISOString(),status:'sending',...(image?{image}: {})})
    pendingUser=user;submittedDraft={text,path:image?.localPath||'',requestId:''};messages.value.push(user)
    scopedStorage.setStorageSync('homepage-chat-task',{memberId:task.value.memberId,type,date:localDate()});desiredType=type
    await scrollLatest()
    const accepted=await flow.submit(text,false,images)
    if(disposed||!visible||scope!==storageContext())return
    user.status=accepted?'sent':task.value.canRetry?'unknown':'failed'
    if(accepted&&!['failed','rejected'].includes(task.value.status)){if(question.value.trim()===text)question.value='';if(draftImage.value?.localPath===(image?.localPath||''))removeDraft()}
    else chatError.value=task.value.error||'回复尚未完成，原问题和图片已保留。'
  }catch(e){if(!disposed&&scope===storageContext())chatError.value=e.message}
  finally{pendingUser=null;sending.value=false}
}
async function retryQuestion(){chatError.value='';await flow.submit('',true);await scrollLatest()}
async function restartChat(){
  if(chatBusy.value||draftSaving.value)return
  const scope=storageContext()
  if(task.value.status==='failed'){
    const text=question.value,image=draftImage.value,error=draftError.value
    flow.invalidateThread()
    question.value=text;draftImage.value=image;draftError.value=error
  }
  chatError.value='';await restoreChat()
  if(disposed||!visible||scope!==storageContext())return
  if(task.value.available&&!task.value.entry?.thread_id){await flow.createEntry();rememberThread()}
}
async function consent(){if(!consentChecked.value)return;consentChecked.value=false;await flow.acceptConsent(true);await sendQuestion()}
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
function history(){uni.navigateTo({url:'/pages/chat/history'})}
async function shortcut(key){
  if(key==='family')archives()
  else if(key==='camera')uni.navigateTo({url:'/pages/scan/index'})
  else if(key==='community')communityOpen.value=true
  else if(key==='plans')uni.navigateTo({url:'/pages/exclusive-plans/index'})
  else{inlineTodayOpen.value=!inlineTodayOpen.value;if(inlineTodayOpen.value&&!state.arrangement)await client.load(localDate())}
}
function askPrompt(text){if(text==='看看我的饮食记录'){uni.navigateTo({url:'/pages/records/index'});return}desiredType=/安排|吃什么/.test(text)?'meal_preview':'consultation';question.value=text;void sendQuestion()}

</script>
<template>
<NutritionistLayout :voice-busy="voiceBusy" :scroll-target="scrollTarget" @history="history" @profile="uni.navigateTo({url:'/pages/my/index'})" @shortcut="shortcut">
 <template #default>
  <view v-if="state.busy&&!state.arrangement" class="dialogue-status"><text>正在读取今日安排…</text></view>
  <view v-if="state.error" class="dialogue-status" role="alert"><text>今日安排暂未就绪</text><text>{{state.error}}</text><button :disabled="state.busy" @click="load(true)">重试并读取今日安排</button><button @click="archives">核对家庭档案</button></view>
  <view v-if="state.phase==='ready'" class="analysis-message"><text class="analysis-label">家庭营养师</text><text class="analysis-copy">{{state.arrangement.analysis.text}}</text></view>
  <DailyArrangementCard v-if="cardVisible && state.phase==='ready'" :arrangement="state.arrangement" :disabled="state.busy" @open="openMeal" @members="selectedMeal=$event" @shop="shop"/>
  <view v-if="!messages.length" class="welcome-message"><view class="welcome-symbol"><AppIcon name="chat" :size="54"/></view><text class="welcome-title">今天，想怎么吃？</text><text>告诉我你想吃什么，我们一起安排适合家人的三餐。</text></view>
  <view v-for="message in messages" :id="'message-'+message.id" :key="message.id" class="message-row" :class="message.role">
   <view v-if="message.role==='assistant'" class="ai-avatar"><AppIcon name="chat" :size="28"/></view>
   <view class="bubble"><image v-if="message.image" class="chat-message-image" :src="message.image.localPath" mode="widthFix" @click="previewChatImage(message.image)"/><text v-if="message.text">{{message.text}}</text>
    <text v-for="citation in message.citations||[]" :key="citation" class="citation">参考：{{citation}}</text>
    <text v-if="message.status==='unknown'" class="chat-error">提交结果待确认，请勿重复发送。</text>
    <text v-if="message.status==='failed'||message.status==='rejected'" class="chat-error">这条问题未完成，可核对后重新发送。</text><text v-if="message.status==='cancelled'" class="chat-error">已取消本次问题。</text>
    <button v-if="message.error" @click="flow.refresh()">重新读取回复</button><ConversationFoodPackages v-if="message.purchaseRequestId" :offers="message.purchaseOffers" :request-id="message.purchaseRequestId"/><HealthChatBusinessCard v-if="message.business" :result="message.business" :member-id="message.memberId||task.memberId"/>
   </view>
  </view>
  <view v-if="familyPanel" class="dialogue-status"><text>家庭餐单 · {{familyState.date}}</text><text>按这餐实际参加的成员核对家庭安排，每位成员的资料和权限由服务端检查。</text><text v-if="familyState.busy">正在读取家庭安排…</text><text v-if="familyState.error" class="chat-error">{{familyState.error}}</text><button v-if="familyState.error" :disabled="familyState.busy" @click="familyPlan('',true)">重新读取家庭餐单</button><DailyArrangementCard v-if="familyState.phase==='ready'" :arrangement="familyState.arrangement" family :disabled="familyState.busy" @open="openFamilyMeal" @members="familySelection={type:$event.type,ids:$event.members.map(m=>m.id),question:''}" @shop="shop"/><button @click="familyPanel=false">收起家庭餐单</button></view>
  <text v-if="chatBusy" class="reply-progress">{{profileLoading?'正在读取咨询资料…':'营养师正在分析…'}}</text><text v-if="chatError" class="chat-error" role="alert">{{chatError}}</text>
  <button v-if="!profile&&!profileLoading" class="secondary-button" @click="load()">重新读取咨询资料</button>
  <button v-if="needsProfileLink" class="secondary-button" @click="consultationProfile">核对并关联本人咨询资料</button>
  <view v-if="task.error||task.notice||task.canRetry||canCancel" class="dialogue-status"><text>{{task.error||task.notice}}</text><button v-if="task.requestId" @click="flow.refresh()">重新读取本次回复</button><button v-if="task.canRetry" @click="retryQuestion">重试原问题</button><button v-if="canCancel" @click="flow.cancelRequest()">取消当前问题</button></view>
  <button v-if="(task.invalidated||task.status==='failed')&&!route.taskType" class="secondary-button" :disabled="chatBusy||draftSaving" @click="restartChat">开始新咨询</button>
  <view v-if="task.consentOption" class="dialogue-status"><text>本次咨询处理方：{{task.consentOption.processor}}；政策版本：{{task.consentOption.policyVersion}}。</text><checkbox-group @change="consentChecked=$event.detail.value.includes('yes')"><label><checkbox value="yes" :checked="consentChecked"/>同意本次咨询的数据处理</label></checkbox-group><button :disabled="!consentChecked||chatBusy" @click="consent">同意并继续咨询</button></view>
  <view class="quick-prompts"><text>问问AI</text><button v-for="prompt in prompts" :key="prompt" :disabled="chatBusy" @click="askPrompt(prompt)">{{prompt}}</button></view>
 </template>
 <template #composer>
  <view v-if="inlineTodayOpen" class="inline-today card"><text class="section-title">今日饮食计划</text><button v-for="meal in state.arrangement?.meals||[]" :key="meal.type" @click="openMeal(meal)"><text>{{({breakfast:'早餐',lunch:'午餐',dinner:'晚餐'})[meal.type]}}</text><text>{{meal.dishes.map(d=>d.name).join('、')}} ›</text></button><text v-if="!state.arrangement" class="composer-note">{{state.error||'今日安排仍在读取，请稍后重试。'}}</text></view>
  <view v-if="draftImage" class="image-draft"><view class="draft-thumbnail"><image :src="draftImage.localPath||draftImage.path" mode="aspectFill" @click="previewChatImage(draftImage)"/><button aria-label="移除待发送图片" @click="removeDraft">×</button></view><view><text>{{draftSaving?'正在准备图片…':draftError||'可直接发送图片，也可以补充文字'}}</text><button v-if="draftError" @click="prepareDraft()">重新准备图片</button></view></view>
  <view class="composer"><button class="input-icon" aria-label="打开相机或选择照片" :disabled="chatBusy||voiceBusy||draftSaving" @click="camera"><AppIcon name="camera" :size="38"/></button><VoiceInput v-if="voiceMode" ref="voiceRef" :disabled="chatBusy||draftSaving" @send="sendVoice" @busy="voiceBusy=$event"/><input v-else v-model="question" :disabled="chatBusy" placeholder="问问家庭营养师…" confirm-type="send" @confirm="sendQuestion"/>
   <button v-if="voiceMode" class="input-icon" aria-label="切换文字输入" :disabled="voiceBusy" @click="voiceMode=false"><view class="keyboard-icon"><view/><view/><view/></view></button>
   <button v-else-if="hasDraftContent" class="send-button" aria-label="发送" :disabled="chatBusy||draftSaving||!!draftError" @click="sendQuestion"><AppIcon name="arrow" :size="30"/></button><button v-else class="input-icon" aria-label="切换语音输入" @click="voiceMode=true"><AppIcon name="mic" :size="36"/></button>
  </view><text class="composer-note">膳食建议仅供参考 · 资料与安排以服务端保存为准</text>
 </template>
 <template #overlays>
  <DinerPicker :open="!!familySelection" :members="profile?.members||[]" :selected="familySelection?.ids||[]" :meal="({breakfast:'早餐',lunch:'午餐',dinner:'晚餐'})[familySelection?.type]" @close="familySelection=null" @confirm="familyMembers"/>
  <DinerPicker :open="!!selectedMeal" :members="profile?.members||[]" :selected="selectedMeal?.members.map(m=>m.id)||[]" :meal="({breakfast:'早餐',lunch:'午餐',dinner:'晚餐'})[selectedMeal?.type]" @close="selectedMeal=null" @confirm="members"/>
  <view v-if="communityOpen" class="sheet-mask" @click.self="communityOpen=false"><view class="sheet"><text class="section-title">加入社群</text><text class="composer-note">暂无可用社群二维码，请稍后再试。</text><button class="secondary-button" @click="communityOpen=false">关闭</button></view></view>
 </template>
</NutritionistLayout>
</template>
<style scoped>
.dialogue-status{padding:28rpx;background:#f5f5f7;border-radius:24rpx;margin:24rpx 0;color:#555;font-size:27rpx;line-height:1.7}.dialogue-status>text{display:block}.dialogue-status button{margin-top:18rpx;min-height:72rpx;text-decoration:underline;color:#222}.analysis-message{padding:30rpx 4rpx 24rpx}.analysis-label{display:block;font-size:23rpx;color:#888;margin-bottom:16rpx}.analysis-copy{display:block;white-space:pre-line;font-size:29rpx;line-height:1.8;color:#28282c}.welcome-message{display:flex;flex-direction:column;align-items:center;text-align:center;padding:56rpx 16rpx 36rpx;gap:20rpx}.welcome-symbol{height:96rpx;width:96rpx;border-radius:30rpx;background:#eaf2ed;color:seagreen;display:flex;align-items:center;justify-content:center}.welcome-title{font-size:40rpx;font-weight:600}.welcome-message>text:last-child{font-size:27rpx;color:#63636b;line-height:1.7;white-space:pre-line}.message-row{display:flex;gap:14rpx;margin:24rpx 0}.message-row.user{justify-content:flex-end;padding-left:60rpx}.ai-avatar{width:52rpx;height:52rpx;display:flex;align-items:center;justify-content:center;border-radius:18rpx;background:#eaf2ed;color:seagreen;flex-shrink:0}.bubble{max-width:570rpx;padding:24rpx;border-radius:4rpx 24rpx 24rpx;background:#f5f5f7;font-size:28rpx;line-height:1.75;white-space:pre-line}.user .bubble{border-radius:24rpx 4rpx 24rpx 24rpx;background:#eaf2ed}.reply-progress,.chat-error{display:block;margin-top:20rpx;color:#777;font-size:25rpx}.composer{display:flex;align-items:center;gap:12rpx;padding:12rpx;border:1rpx solid #dedee3;border-radius:24rpx;background:#fafafa}.composer input{flex:1;min-width:0;height:68rpx;font-size:29rpx}.input-icon,.send-button{width:68rpx;height:68rpx;display:flex;align-items:center;justify-content:center;color:#63636b;flex-shrink:0}.send-button{border-radius:50%;background:#1d1d1f;color:#fff}.composer-note{display:block;font-size:20rpx;color:#999;text-align:center;margin-top:12rpx}.composer :deep(.voice-input){flex:1}.quick-prompts{display:flex;flex-direction:column;gap:14rpx;padding:16rpx 0 32rpx}.quick-prompts>text{font-size:28rpx;font-weight:600}.quick-prompts button{min-height:80rpx;padding:16rpx 0;text-align:left;font-size:26rpx}
</style>

<style scoped>
.chat-message-image{display:block;width:360rpx;max-width:100%;border-radius:16rpx;margin-bottom:12rpx}.citation{display:block;margin-top:14rpx;font-size:23rpx;color:#63636b}.image-draft{display:flex;gap:20rpx;align-items:center;padding:12rpx 0 20rpx;font-size:24rpx;color:#63636b}.draft-thumbnail{position:relative;flex-shrink:0}.draft-thumbnail image{width:110rpx;height:110rpx;border-radius:16rpx}.draft-thumbnail button{position:absolute;top:-12rpx;right:-12rpx;width:40rpx;height:40rpx;border-radius:50%;background:#fff}.image-draft>view+view{flex:1}.inline-today{max-height:320rpx;overflow:auto;padding:24rpx;margin-bottom:18rpx}.inline-today>button{display:flex;justify-content:space-between;gap:16rpx;width:100%;padding:20rpx 0;text-align:left;font-size:25rpx}.keyboard-icon{width:42rpx;height:32rpx;border:3rpx solid currentColor;border-radius:7rpx;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:4rpx}.keyboard-icon>view{width:26rpx;border-top:3rpx dotted currentColor}.keyboard-icon>view:last-child{width:18rpx;border-top-style:solid}
</style>
