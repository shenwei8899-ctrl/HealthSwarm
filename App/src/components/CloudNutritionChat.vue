<script setup>
import { computed, reactive, ref, nextTick, onMounted, onUnmounted } from 'vue'
import { onShow, onHide } from '@dcloudio/uni-app'
import NutritionistLayout from './NutritionistLayout.vue'
import AppIcon from './AppIcon.vue'
import DinerPicker from './DinerPicker.vue'
import DailyArrangementCard from './DailyArrangementCard.vue'
import VoiceInput from './VoiceInput.vue'
import { loadCloudProfile } from '../services/cloud-profile.js'
import { createDailyArrangementClient, dailyArrangementState } from '../services/daily-arrangement-client.js'
import { request } from '../services/request.js'
import { storageContext, scopedStorage } from '../services/storage.js'
import { getSession } from '../services/session.js'
import { commerce } from '../services/commerce.js'
import { createHealthTaskFlow, newHealthRequestId } from '../services/health-task-flow.js'
import { localDate } from '../utils/meal-state.js'

const state = reactive(dailyArrangementState()), profile = ref(null), cardVisible = ref(false), selectedMeal = ref(null)
const question = ref(''), chatError = ref(''), messages = ref([]), task = ref({}), consentChecked=ref(false)
const voiceMode=ref(false),voiceBusy=ref(false),voiceRef=ref(null),communityOpen=ref(false),scrollTarget=ref('')
const prompts=['今晚全家吃什么？','给我安排明天早餐','看看我的饮食记录','糖尿病家庭怎么吃？']
const chatBusy=computed(()=>task.value.busy||task.value.loading||['queued','dispatched','pending','running'].includes(task.value.status))
let disposed = false, loading = null, epoch = 0, pageScope=storageContext(), flowScope=pageScope
const delivered=new Set()
const flow=createHealthTaskFlow({onChange:next=>{
  if(disposed||flowScope!==storageContext())return
  task.value=next
  if(next.result && !delivered.has(next.requestId)) {
    delivered.add(next.requestId)
    if(next.result.type==='answer')messages.value.push({id:next.requestId,role:'assistant',text:next.result.text})
    else if(next.result.type==='needs_input')messages.value.push({id:next.requestId,role:'assistant',text:next.result.questions.join('\n')})
  }
}})
const client = createDailyArrangementClient({ state, send: request, context: () => ({ scope: storageContext(), familyId: getSession()?.householdId }), storage: scopedStorage, newId: newHealthRequestId, beforeStart: () => commerce.connect() })
async function load(retry=false) {
  if(pageScope!==storageContext()) {
    epoch++;loading=null;client.reset();flow.hide();pageScope=storageContext();flowScope=pageScope
    messages.value=[];delivered.clear();question.value='';chatError.value='';profile.value=null;task.value={};selectedMeal.value=null
    voiceRef.value?.cancel();voiceMode.value=false;voiceBusy.value=false;cardVisible.value=false
  }
  if (loading) return loading
  const mine = ++epoch
  cardVisible.value = !!state.arrangement
  loading = (async () => {
    try {
      profile.value = await loadCloudProfile()
      if (disposed || mine !== epoch) return
      pageScope=storageContext();flowScope=pageScope
      if (!profile.value.onboarded) { uni.redirectTo({url:'/pages/onboarding/index'}); return }
      await client.load(localDate(),retry===true)
      if (disposed || mine !== epoch) return
      await nextTick()
      cardVisible.value = state.phase === 'ready'
    } catch (error) { if (!disposed && mine === epoch) {
      if ([401,403].includes(Number(error.code)) || !getSession()?.token) {
        profile.value=null;messages.value=[];state.arrangement=null;cardVisible.value=false;flow.hide();client.reset()
        if (!getSession()?.token || Number(error.code)===401) { uni.reLaunch({url:'/pages/index/index'}); return }
      }
      state.phase = 'error'; state.error = error.message; state.busy = false
    } }
    finally { if (mine === epoch) loading = null }
  })()
  return loading
}
onMounted(load)
onShow(() => { if (!disposed) void load() })
onHide(()=>{voiceRef.value?.cancel();flow.hide()})
onUnmounted(() => { disposed = true; epoch++; client.dispose();flow.hide() })
function openMeal(meal) { uni.navigateTo({url:'/pages/shop/index?meal='+meal.type+'&date='+state.date+'&arrangement='+encodeURIComponent(state.arrangement.id)+'&version='+state.arrangement.version}) }
function shop() { uni.navigateTo({url:'/pages/shop/index?commerce=1'}) }
function archives() { uni.navigateTo({url:'/pages/profile/index'}) }
async function members(ids) {
  const type = selectedMeal.value.type
  selectedMeal.value = null
  await client.changeMembers(type, ids)
  await nextTick(); cardVisible.value = state.phase === 'ready'
}
async function sendQuestion() {
  if (!question.value.trim() || chatBusy.value) return
  const scope=storageContext(),text=question.value.trim()
  chatError.value=''
  try {
    if(!task.value.memberId) {
      const {data}=await request({path:'/api/health/v1/members'})
      if(disposed||scope!==storageContext())return
      const healthId=profile.value?.members.find(member=>member.relation==='本人')?.healthMemberId
      const self=data.find(member=>member.id===healthId)
      if(!self)throw new Error('当前账号尚无可咨询的本人健康档案，请在“我的 → 本人健康档案与咨询授权”中核对。')
      flowScope=scope;await flow.open(self.id,'consultation')
    }
    if(disposed||scope!==storageContext())return
    if(task.value.canRetry){await flow.submit('',true);return}
    if(!task.value.available)return
    if(!task.value.entry?.thread_id)await flow.createEntry()
    if(disposed||scope!==storageContext()||!task.value.entry?.thread_id)return
    if(await flow.submit(text)){messages.value.push({id:task.value.requestId+'-user',role:'user',text});question.value=''}
  } catch(error) { if (!disposed && scope===storageContext()) chatError.value=error.message }
}
async function consent(){if(!consentChecked.value)return;consentChecked.value=false;await flow.acceptConsent(true);await sendQuestion()}
function sendVoice(text){question.value=text;voiceBusy.value=false;void sendQuestion()}
function camera(){uni.navigateTo({url:'/pages/health/vision?kind=meal'})}
function history(){const id=task.value.memberId||profile.value?.members.find(m=>m.relation==='本人')?.healthMemberId;if(id)uni.navigateTo({url:'/pages/chat/agent?memberId='+encodeURIComponent(id)+'&taskType=consultation'});else{uni.showToast({title:'请先核对本人健康档案',icon:'none'});uni.navigateTo({url:'/pages/my/index'})}}
async function shortcut(key){if(key==='family')archives();else if(key==='camera')camera();else if(key==='community')communityOpen.value=true;else if(key==='plans')uni.showModal({title:'AI专属计划',content:'21天专属计划的正式服务尚未接入，开通后可在这里使用。',showCancel:false});else{scrollTarget.value='';await nextTick();scrollTarget.value='today-arrangement';void load()}}
function askPrompt(text){question.value=text;void sendQuestion()}
</script>

<template>
  <NutritionistLayout :voice-busy="voiceBusy" :scroll-target="scrollTarget" @history="history" @profile="uni.navigateTo({url:'/pages/my/index'})" @shortcut="shortcut">
    <template #default>
      <view id="today-arrangement">
        <view v-if="state.busy && !state.arrangement" class="dialogue-status" aria-live="polite"><text>正在为家人安排今日饮食</text><text>分析档案、搭配三餐，并核对食材。</text></view>
        <view v-if="state.error" class="dialogue-status" role="alert"><text>今日安排暂未就绪</text><text>{{state.error}}</text><button :disabled="state.busy" @click="load(true)">重试并读取今日安排</button><button @click="archives">核对家庭档案</button></view>
        <view v-if="state.phase==='ready'" class="analysis-message"><text class="analysis-label">家庭营养师</text><text class="analysis-copy">{{state.arrangement.analysis.text}}</text></view>
        <DailyArrangementCard v-if="cardVisible && state.phase==='ready'" :arrangement="state.arrangement" :disabled="state.busy" @open="openMeal" @members="selectedMeal=$event" @shop="shop"/>
      </view>
      <view v-if="!messages.length" class="welcome-message"><view class="welcome-symbol"><AppIcon name="chat" :size="54"/></view><text class="welcome-title">今天，想怎么吃？</text><text>告诉我你想吃什么，
我们一起安排适合家人的三餐。</text></view>
      <view v-for="message in messages" :id="'message-'+message.id" :key="message.id" class="message-row" :class="message.role"><view v-if="message.role==='assistant'" class="ai-avatar"><AppIcon name="chat" :size="28"/></view><view class="bubble"><text>{{message.text}}</text></view></view>
      <text v-if="chatBusy" class="reply-progress">营养师正在分析…</text><text v-if="chatError" class="chat-error" role="alert">{{chatError}}</text>
      <view v-if="task.error||task.notice" class="dialogue-status"><text>{{task.error||task.notice}}</text><button v-if="task.requestId" @click="flow.refresh()">重新读取本次回复</button><button v-if="task.canRetry" @click="flow.submit('',true)">重试原问题</button></view>
      <view v-if="task.consentOption" class="dialogue-status"><text>本次营养咨询处理方：{{task.consentOption.processor}}；政策版本：{{task.consentOption.policyVersion}}。</text><checkbox-group @change="consentChecked=$event.detail.value.includes('yes')"><label><checkbox value="yes" :checked="consentChecked" color="#333333"/>同意本次咨询的数据处理</label></checkbox-group><button :disabled="!consentChecked||chatBusy" @click="consent">同意并继续咨询</button></view>
      <view class="quick-prompts"><text>问问AI</text><button v-for="prompt in prompts" :key="prompt" :disabled="chatBusy" @click="askPrompt(prompt)">{{prompt}}</button></view>
    </template>
    <template #composer>
      <view class="composer"><button class="input-icon" aria-label="打开相机或选择照片" :disabled="voiceBusy" @click="camera"><AppIcon name="camera" :size="38"/></button><VoiceInput v-if="voiceMode" ref="voiceRef" :disabled="chatBusy" @send="sendVoice" @busy="voiceBusy=$event"/><input v-else v-model="question" :disabled="chatBusy" placeholder="问问家庭营养师…" confirm-type="send" @confirm="sendQuestion"/><button v-if="voiceMode" class="input-icon" :disabled="voiceBusy" @click="voiceMode=false">键盘</button><button v-else-if="!question.trim()" class="input-icon" aria-label="切换语音输入" @click="voiceMode=true"><AppIcon name="mic" :size="36"/></button><button v-else class="send-button" :disabled="chatBusy" aria-label="发送" @click="sendQuestion"><AppIcon name="arrow" :size="30"/></button></view><text class="composer-note">膳食建议仅供参考 · 资料与安排以服务端保存为准</text>
    </template>
    <template #overlays>
      <DinerPicker :open="Boolean(selectedMeal)" :members="profile?.members||[]" :selected="selectedMeal?.members.map(member=>member.id)||[]" :meal="({breakfast:'早餐',lunch:'午餐',dinner:'晚餐'})[selectedMeal?.type]" @close="selectedMeal=null" @confirm="members"/>
      <view v-if="communityOpen" class="sheet-mask" @click.self="communityOpen=false"><view class="sheet"><text class="section-title">加入社群</text><text class="composer-note">暂无可用社群二维码，请稍后再试。</text><button class="secondary-button" @click="communityOpen=false">关闭</button></view></view>
    </template>
  </NutritionistLayout>
</template>
<style scoped>
.dialogue-status{padding:28rpx;background:#f5f5f7;border-radius:24rpx;margin:24rpx 0;color:#555;font-size:27rpx;line-height:1.7}.dialogue-status>text{display:block}.dialogue-status button{margin-top:18rpx;min-height:72rpx;text-decoration:underline;color:#222}.analysis-message{padding:30rpx 4rpx 24rpx}.analysis-label{display:block;font-size:23rpx;color:#888;margin-bottom:16rpx}.analysis-copy{display:block;white-space:pre-line;font-size:29rpx;line-height:1.8;color:#28282c}.welcome-message{display:flex;flex-direction:column;align-items:center;text-align:center;padding:56rpx 16rpx 36rpx;gap:20rpx}.welcome-symbol{height:96rpx;width:96rpx;border-radius:30rpx;background:#eaf2ed;color:seagreen;display:flex;align-items:center;justify-content:center}.welcome-title{font-size:40rpx;font-weight:600}.welcome-message>text:last-child{font-size:27rpx;color:#63636b;line-height:1.7;white-space:pre-line}.message-row{display:flex;gap:14rpx;margin:24rpx 0}.message-row.user{justify-content:flex-end;padding-left:60rpx}.ai-avatar{width:52rpx;height:52rpx;display:flex;align-items:center;justify-content:center;border-radius:18rpx;background:#eaf2ed;color:seagreen;flex-shrink:0}.bubble{max-width:570rpx;padding:24rpx;border-radius:4rpx 24rpx 24rpx;background:#f5f5f7;font-size:28rpx;line-height:1.75;white-space:pre-line}.user .bubble{border-radius:24rpx 4rpx 24rpx 24rpx;background:#eaf2ed}.reply-progress,.chat-error{display:block;margin-top:20rpx;color:#777;font-size:25rpx}.composer{display:flex;align-items:center;gap:12rpx;padding:12rpx;border:1rpx solid #dedee3;border-radius:24rpx;background:#fafafa}.composer input{flex:1;min-width:0;height:68rpx;font-size:29rpx}.input-icon,.send-button{width:68rpx;height:68rpx;display:flex;align-items:center;justify-content:center;color:#63636b;flex-shrink:0}.send-button{border-radius:50%;background:#1d1d1f;color:#fff}.composer-note{display:block;font-size:20rpx;color:#999;text-align:center;margin-top:12rpx}.composer :deep(.voice-input){flex:1}.quick-prompts{display:flex;flex-direction:column;gap:14rpx;padding:16rpx 0 32rpx}.quick-prompts>text{font-size:28rpx;font-weight:600}.quick-prompts button{min-height:80rpx;padding:16rpx 0;text-align:left;font-size:26rpx}
</style>
