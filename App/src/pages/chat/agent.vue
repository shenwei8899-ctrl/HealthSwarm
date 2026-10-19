<script setup>
import { computed, ref } from 'vue'
import { onLoad, onShow, onHide, onUnload } from '@dcloudio/uni-app'
import { scopedStorage } from '../../services/storage.js'
import AppNavBar from '../../components/AppNavBar.vue'
import { createHealthTaskFlow } from '../../services/health-task-flow.js'

const route = ref({ memberId: '', taskType: '' })
const view = ref({}), question = ref(''), consentChecked = ref(false)
const flow = createHealthTaskFlow({ onChange: next => { view.value = next } })
const canAsk = computed(() => view.value.available && !!view.value.entry?.thread_id && !view.value.busy &&
  !view.value.loading && !view.value.submitUnknown)
const canCancel = computed(() => view.value.requestId && !view.value.submitUnknown &&
  !['completed', 'failed', 'cancelled', 'interrupted', 'rejected'].includes(view.value.status))
const statusText = computed(() => ({ queued: '排队中', dispatched: '已派发', pending: '等待运行', running: '正在处理',
  cancel_requested: '正在取消', completed: '已完成', failed: '处理失败', cancelled: '已取消',
  interrupted: '运行中断', rejected: '请求被拒绝' })[view.value.status] || view.value.status)

onLoad(options => { route.value = { memberId: options.memberId || '', taskType: options.taskType || '', selection: options.indicatorChoice === '1' ? scopedStorage.getStorageSync('indicator-choice:' + options.memberId + ':' + options.taskType) : null } })
onShow(() => { void flow.open(route.value.memberId, route.value.taskType, route.value.selection) })
onHide(() => { flow.hide(); question.value = ''; consentChecked.value = false })
onUnload(() => { flow.hide(); question.value = ''; consentChecked.value = false })
function back() { uni.navigateBack() }
function create() { void flow.createEntry() }
function send() {
  if (!canAsk.value || !question.value.trim()) return
  const text = question.value.trim()
  void flow.submit(text).then(accepted => { if (accepted && question.value.trim() === text) question.value = '' })
}
function refresh() { void flow.refresh() }
function retry() { void flow.submit('', true) }
function consent() { if (consentChecked.value) { consentChecked.value = false; void flow.acceptConsent(true) } }
</script>

<template>
  <view class="screen task-screen">
    <AppNavBar><view class="nav-row"><button class="text-button" @click="back">返回</button><text class="nav-title">{{ view.title || '健康助手' }}</text><text></text></view></AppNavBar>
    <view class="card task-card">
      <text class="section-title">{{ view.title || '健康任务' }}</text>
      <text class="helper">本页只显示服务端当前核验的结果。新问题须由你明确提交；任务入口、运行和专业批准是不同状态。</text>
      <text v-if="view.loading" class="helper">正在核对成员与服务状态…</text>
      <text v-if="view.error" class="error-note">{{ view.error }}</text>
      <text v-if="view.notice" class="helper">{{ view.notice }}</text>
      <view v-if="view.consentOption" class="consent-box">
        <text class="helper">用途：{{ route.taskType==='diet_analysis'?'这餐饮食反馈':'营养咨询与指标记录回顾' }}。处理方：{{ view.consentOption.processor }}。政策版本：{{ view.consentOption.policyVersion }}。</text>
        <checkbox-group @change="event => consentChecked = event.detail.value.includes('yes')"><label><checkbox value="yes" :checked="consentChecked" />我已核对，并同意本次用途的数据处理</label></checkbox-group>
        <button class="secondary-button" :disabled="!consentChecked || view.busy" @click="consent">确认同意并重新核对状态</button>
      </view>
      <button v-if="view.available && !view.entry?.thread_id" class="primary-button" :disabled="view.busy || view.loading" @click="create">
        {{ view.entry?.pending ? '用原请求键确认线程' : '开始这项咨询' }}
      </button>
      <template v-if="view.entry?.thread_id">
        <view v-if="view.requests?.length>1" class="request-list"><button v-for="(item,index) in view.requests" :key="item.request_id" :disabled="view.busy||view.submitUnknown" :class="{selected:item.request_id===view.requestId}" @click="flow.selectRequest(item.request_id)">问题 {{index+1}} · {{({queued:'排队中',running:'处理中',completed:'已完成',cancelled:'已取消',rejected:'已拒绝'})[item.status]||item.status}}</button></view>
        <text v-if="view.requestId" class="helper">当前请求：{{ statusText || '待核对' }}</text>
        <text v-if="view.result?.type === 'answer'" class="answer">{{ view.result.text }}</text>
        <view v-if="view.result?.citations?.length" class="citation"><text>本次引用：</text><text v-for="(title,index) in view.result.citations" :key="index">{{ title }}</text></view>
        <view v-if="view.result?.type === 'needs_input'" class="answer"><text>请补充：</text><text v-for="(item,index) in view.result.questions" :key="index">{{ item }}</text></view>
        <text v-if="view.result?.type === 'error'" class="error-note">任务未完成（{{ view.result.code }}）。如需继续，请明确提交新问题。</text>
        <button v-if="view.requestId" class="secondary-button" :disabled="view.busy || view.loading" @click="refresh">重新读取同一任务</button>
        <button v-if="view.canRetry" class="secondary-button" :disabled="view.busy" @click="retry">用同一请求键重试提交</button>
        <button v-if="canCancel" class="secondary-button" :disabled="view.busy||view.loading" @click="flow.cancelRequest()">取消当前问题</button>
        <template v-if="canAsk">
          <textarea v-model="question" class="question-input" maxlength="4000" placeholder="输入本次想咨询的问题" />
          <button class="primary-button" :disabled="!question.trim()" @click="send">{{canCancel?'追加问题，按顺序处理':'提交问题'}}</button>
        </template>
      </template>
    </view>
  </view>
</template>

<style scoped>
.task-screen{padding-bottom:48rpx}.task-card{padding:28rpx;margin:24rpx 0}.section-title{display:block;font-size:34rpx;font-weight:600}.task-card button{margin-top:18rpx}.helper{display:block;font-size:25rpx;color:#63636b;line-height:1.7;margin:18rpx 0}.error-note{display:block;color:#a13a30;line-height:1.6;margin:18rpx 0}.answer{display:block;white-space:pre-line;font-size:29rpx;line-height:1.75;margin:24rpx 0}.answer text,.citation text{display:block}.citation{font-size:24rpx;color:#63636b;margin:18rpx 0}.consent-box{padding:18rpx;background:#f1f6f2;border-radius:16rpx;font-size:25rpx}.question-input{width:100%;min-height:190rpx;padding:20rpx;border:1px solid #ddd;border-radius:16rpx;box-sizing:border-box;margin-top:24rpx}.text-button{background:transparent;color:#246b50;font-size:26rpx}
</style>
<style scoped>.request-list{display:flex;gap:12rpx;flex-wrap:wrap}.request-list button{font-size:24rpx;padding:12rpx 18rpx;background:#eef2ed}.request-list .selected{background:#246b50;color:#fff}</style>
