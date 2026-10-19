<script setup>
import { computed, reactive, ref, nextTick, onMounted, onUnmounted } from 'vue'
import { onShow, onHide } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
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
const voiceMode=ref(false),voiceBusy=ref(false),voiceRef=ref(null),communityOpen=ref(false)
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
    } catch (error) { if (!disposed && mine === epoch) { state.phase = 'error'; state.error = error.message; state.busy = false } }
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
function archives() { uni.navigateTo({url:'/pages/family-shared/index'}) }
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
      if(!self)throw new Error('当前账号尚无可咨询的本人健康档案，请先在账号页核对。')
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
function history(){if(task.value.memberId)uni.navigateTo({url:'/pages/chat/agent?memberId='+task.value.memberId+'&taskType=consultation'});else uni.navigateTo({url:'/pages/account/index'})}
</script>

<template>
  <view class="screen cloud-chat">
    <AppNavBar><view class="nav-row"><button class="icon-button" aria-label="咨询记录" @click="history"><AppIcon name="record" :size="36"/></button><view class="assistant-heading"><text>家庭营养师</text><text>一起安排每一天</text></view><button class="icon-button" aria-label="账号与家庭" @click="uni.navigateTo({url:'/pages/account/index'})"><AppIcon name="user" :size="36"/></button></view></AppNavBar>
    <scroll-view scroll-y class="cloud-conversation">
      <view v-if="state.busy && !state.arrangement" class="analysis-progress" aria-live="polite"><view class="progress-dot"></view><view><text>正在为家人安排今日饮食</text><text>分析档案、搭配三餐，并核对食材。</text></view></view>
      <view v-if="state.error" class="dialogue-status" role="alert"><text>{{state.error}}</text><button :disabled="state.busy" @click="load(true)">重试并读取今日安排</button><button @click="archives">核对对应成员档案</button></view>
      <view v-if="state.phase==='ready'" class="analysis-message"><text class="analysis-label">家庭营养师</text><text class="analysis-copy">{{state.arrangement.analysis.text}}</text></view>
      <DailyArrangementCard v-if="cardVisible && state.phase==='ready'" :arrangement="state.arrangement" :disabled="state.busy" @open="openMeal" @members="selectedMeal=$event" @shop="shop"/>
      <view v-for="message in messages" :key="message.id" class="chat-message" :class="message.role"><text>{{message.text}}</text></view>
      <text v-if="chatBusy" class="reply-progress">营养师正在分析…</text><text v-if="chatError" class="chat-error" role="alert">{{chatError}}</text>
      <view v-if="task.error||task.notice" class="dialogue-status"><text>{{task.error||task.notice}}</text><button v-if="task.requestId" @click="flow.refresh()">重新读取本次回复</button><button v-if="task.canRetry" @click="flow.submit('',true)">重试原问题</button></view>
      <view v-if="task.consentOption" class="dialogue-status"><text>本次营养咨询处理方：{{task.consentOption.processor}}；政策版本：{{task.consentOption.policyVersion}}。</text><checkbox-group @change="consentChecked=$event.detail.value.includes('yes')"><label><checkbox value="yes" :checked="consentChecked" color="#333333"/>同意本次咨询的数据处理</label></checkbox-group><button :disabled="!consentChecked||chatBusy" @click="consent">同意并继续咨询</button></view>
      <view class="conversation-space"></view>
    </scroll-view>
    <view class="cloud-composer"><scroll-view scroll-x class="cloud-shortcuts"><view class="shortcut-row"><button @click="archives">家庭健康档案</button><button @click="camera">拍照记录饮食</button><button @click="load()">今日饮食安排</button><button @click="uni.navigateTo({url:'/pages/records/index'})">饮食记录</button><button @click="shop">选购食材</button><button @click="communityOpen=true">加入社群</button></view></scroll-view><view class="input-row"><button class="input-icon" aria-label="拍照或选择照片" :disabled="voiceBusy" @click="camera"><AppIcon name="camera" :size="34"/></button><VoiceInput v-if="voiceMode" ref="voiceRef" :disabled="chatBusy" @send="sendVoice" @busy="voiceBusy=$event"/><input v-else v-model="question" :disabled="chatBusy" placeholder="告诉营养师你的饮食想法…" confirm-type="send" @confirm="sendQuestion"/><button v-if="voiceMode" :disabled="voiceBusy" @click="voiceMode=false">键盘</button><button v-else-if="!question.trim()" class="input-icon" aria-label="切换语音输入" @click="voiceMode=true"><AppIcon name="mic" :size="34"/></button><button v-else :disabled="chatBusy" @click="sendQuestion">发送</button></view><text class="composer-note">建议基于已保存档案与配方计算，实际食量可继续调整。</text></view>
    <DinerPicker :open="Boolean(selectedMeal)" :members="profile?.members||[]" :selected="selectedMeal?.members.map(member=>member.id)||[]" :meal="({breakfast:'早餐',lunch:'午餐',dinner:'晚餐'})[selectedMeal?.type]" @close="selectedMeal=null" @confirm="members"/>
    <view v-if="communityOpen" class="sheet-mask" @click.self="communityOpen=false"><view class="sheet"><text class="section-title">加入社群</text><text class="composer-note">暂无可用社群二维码，请稍后再试。</text><button class="secondary-button" @click="communityOpen=false">关闭</button></view></view>
  </view>
</template>

<style scoped>
.cloud-chat{display:flex;flex-direction:column;height:100vh;height:100dvh;padding-bottom:0;background:#fff}.assistant-heading{text-align:center;display:flex;flex-direction:column;gap:8rpx;font-size:31rpx;font-weight:600}.assistant-heading text+text{font-size:21rpx;font-weight:400;color:#8a8a91}.cloud-conversation{flex:1;min-height:0}.analysis-progress{display:flex;gap:20rpx;padding:45rpx 8rpx;align-items:flex-start}.analysis-progress text{display:block;font-size:28rpx;line-height:1.8}.analysis-progress text+text{font-size:24rpx;color:#85858d}.progress-dot{width:14rpx;height:14rpx;margin-top:18rpx;border-radius:50%;background:#777;animation:breathe 1.5s infinite}.dialogue-status{padding:28rpx;background:#f5f5f7;border-radius:24rpx;margin:24rpx 0;color:#555;font-size:27rpx;line-height:1.7}.dialogue-status button{margin-top:18rpx;min-height:72rpx;text-decoration:underline;color:#222}.analysis-message{padding:30rpx 4rpx 34rpx}.analysis-label{display:block;font-size:23rpx;color:#888;margin-bottom:16rpx}.analysis-copy{display:block;white-space:pre-line;font-size:29rpx;line-height:1.9;color:#28282c}.cloud-composer{padding:18rpx 0 calc(env(safe-area-inset-bottom) + 16rpx);background:#fff}.cloud-shortcuts{display:flex;gap:18rpx;margin-bottom:18rpx}.cloud-shortcuts button{background:#f4f4f6;border:1rpx solid #e7e7eb;padding:14rpx 22rpx;border-radius:99rpx;font-size:23rpx;color:#53535b}.input-row{display:flex;gap:16rpx;padding:16rpx 18rpx;background:#f4f4f6;border-radius:24rpx;align-items:center}.input-row input{flex:1;min-width:0;height:72rpx;font-size:27rpx}.input-row button{padding:18rpx 24rpx;border-radius:18rpx;background:#222;color:#fff;font-size:25rpx}.composer-note{display:block;font-size:20rpx;color:#999;text-align:center;margin-top:15rpx}.conversation-space{height:40rpx}.chat-message{padding:24rpx;margin-top:24rpx;background:#f5f5f7;border-radius:24rpx;font-size:28rpx;line-height:1.8;white-space:pre-line}.chat-message.user{margin-left:60rpx;background:#eaeaec}.reply-progress,.chat-error{display:block;margin-top:20rpx;color:#777;font-size:25rpx}.cloud-chat :deep(.checked){color:#222}.cloud-chat :deep(.helper){color:#777}.cloud-chat :deep(.secondary-button){color:#333}@keyframes breathe{50%{opacity:.3}}@media(prefers-reduced-motion:reduce){.progress-dot{animation:none}}
</style>
<style scoped>
.cloud-shortcuts{white-space:nowrap;display:block}.shortcut-row{display:inline-flex;gap:14rpx}.shortcut-row button{flex-shrink:0}.input-row .input-icon{background:transparent;color:#555;padding:12rpx;display:flex;align-items:center;justify-content:center}.input-row :deep(.voice-input){flex:1}.cloud-chat :deep(.voice-recording-overlay){background:#303036}.cloud-chat :deep(.recording-wash){background:radial-gradient(ellipse at 50% 100%,#73737d,transparent 70%)}.cloud-chat :deep(.secondary-button){color:#333}
</style>
