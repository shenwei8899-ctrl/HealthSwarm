<script setup>
import { computed, ref } from 'vue'
import { onLoad, onShow, onHide, onUnload } from '@dcloudio/uni-app'
import { client } from '../../services/runtime.js'
import { createConsultationController } from '../../ui/consultation-controller.js'
import { CONSULTATION_SCOPES, runStatusLabel } from '../../ui/consultation-projection.js'

const state = ref({ messages: [], consultations: [] })
let routeMemberId = ''
const controller = createConsultationController({ client, onChange: value => { state.value = value },
  onUnauthorized: () => uni.reLaunch({ url: '/pages/login/index' }) })
const scopeLabels = { ai_use: '云 AI 处理', report_view: '报告读取', diet_edit: '饮食记录' }
const missingScopes = computed(() => CONSULTATION_SCOPES.filter(scope => !state.value.member?.scopes.includes(scope)))
const eligible = computed(() => state.value.link && state.value.policy?.available && !missingScopes.value.length && !state.value.blocked)
const waiting = computed(() => state.value.polling || state.value.pollTimedOut || state.value.submitUnknown)
const canCreate = computed(() => eligible.value && state.value.consentChoice && !state.value.busy
  && !state.value.historyLoading && !waiting.value && !state.value.createUnknown)
const canSubmit = computed(() => eligible.value && state.value.thread && state.value.consentAccepted
  && state.value.query?.trim() && !state.value.busy && !state.value.historyLoading && !waiting.value && state.value.run?.status !== 'interrupted')
const hasAnswers = computed(() => state.value.messages.some(row => row.role === 'assistant'))
function consentChanged(event) { controller.setConsentChoice(event.detail.value.includes('consultation')) }
function goBack() { uni.navigateBack({ fail: () => uni.reLaunch({ url: '/pages/members/index' }) }) }
function logout() { controller.hide(); client.logout(); uni.reLaunch({ url: '/pages/login/index' }) }
onLoad(options => { routeMemberId = typeof options.member_id === 'string' ? options.member_id : '' })
onShow(() => controller.show(routeMemberId))
onHide(() => controller.hide())
onUnload(() => controller.dispose())
</script>

<template>
  <view class="screen access-screen consultation-screen">
    <AppNavBar><view class="nav-row"><button class="text-button" @click="goBack">返回</button><text class="nav-title">本人营养咨询</text><view /></view></AppNavBar>
    <view v-if="state.account" class="account-bar card access-card"><view><text>{{ state.account.username }}</text><text class="account-id">当前账号：{{ state.account.uid }}</text></view><button class="text-button" @click="logout">退出账号</button></view>
    <view class="page-heading"><text class="display-title">和营养师聊聊</text><text class="subtitle">使用当前本人关联及服务端授权，读取真实咨询结果。资料不足时由服务说明需要补充的内容。</text></view>
    <text v-if="state.loading" class="status-loading">正在重新核对当前账号、本人关联与咨询政策…</text>
    <view v-if="state.error" class="error-box" role="alert"><text>{{ state.error }}</text></view>
    <view v-if="state.notice" class="notice"><text>{{ state.notice }}</text></view>
    <view v-if="state.blocked" class="card access-card"><text class="body-copy">当前页面已停止继续咨询。返回成员页核对真实身份、授权与关联后再进入。</text><button class="secondary-button" @click="goBack">返回本人成员接入</button></view>
    <template v-if="!state.loading && state.link && !state.blocked">
      <view class="card access-card">
        <text class="section-title">当前本人身份</text><text class="body-copy">{{ state.member.display_name }} · 本人</text>
        <view class="result-row"><text class="result-label">健康成员 ID</text><text>{{ state.member.id }}</text></view>
        <view class="result-row"><text class="result-label">已关联的家庭成员 ID</text><text>{{ state.link.source_member_id }}</text></view>
        <text v-if="state.profile" class="body-copy">基础档案：{{ state.profile.description }}</text>
        <text class="safe-note">基础档案状态不代表完整专业档案或营养安全规则已完成。</text>
      </view>
      <view v-if="state.policy" class="card access-card">
        <text class="section-title">授权与本次用途同意</text>
        <view class="result-row"><text class="result-label">当前成员授权</text><text v-for="scope in CONSULTATION_SCOPES" :key="scope">{{ scopeLabels[scope] }}：{{ state.member.scopes.includes(scope) ? '已授权' : '未授权' }}</text></view>
        <text v-if="missingScopes.length" class="notice">缺少咨询所需成员授权，请在已有后台明确授权后重新进入。页面不会自动授予权限。</text>
        <view class="result-row"><text class="result-label">当前模型与处理政策</text><text>模型：{{ state.policy.model || '尚未配置' }}</text><text>处理方：{{ state.policy.processor || '尚未配置' }}</text><text>政策版本：{{ state.policy.policy_version || '尚未审批' }}</text></view>
        <text v-if="!state.policy.available" class="notice">咨询当前不可用：{{ state.policy.reason || '请联系管理员核对当前模型处理政策' }}</text>
        <text class="body-copy">咨询用途将由上述处理方处理当前问题及完成任务必要的已授权资料。本页只记录你本次明确选择，没有读取或推断既有同意。</text>
        <checkbox-group @change="consentChanged"><label class="identity-confirm"><checkbox value="consultation" :checked="state.consentChoice" :disabled="!eligible || state.busy || waiting" color="#246b50" /><text>我已核对上述处理方与政策，同意本次营养咨询用途处理。</text></label></checkbox-group>
        <text v-if="state.consentAccepted" class="success-note">本次明确同意已保存。</text>
        <button class="secondary-button" :disabled="state.busy || waiting || state.createUnknown" @click="controller.refreshPolicy">重新读取当前政策</button>
        <button class="text-button" :disabled="state.busy || !state.policy.processor || !state.policy.policy_version" @click="controller.withdrawConsent">撤回咨询用途同意</button>
        <text class="safe-note">撤回会阻止新问题与后续模型处理；历史读取仍按服务端当前授权判断。</text>
      </view>
      <view class="card access-card">
        <text class="section-title">开始或恢复真实咨询</text>
        <button v-if="!state.needsNew" class="primary-button" :disabled="!canCreate" @click="controller.createThread('daily')">明确同意并进入今日咨询</button>
        <button class="secondary-button" :disabled="!canCreate" @click="controller.createThread('new')">明确同意并新建独立咨询</button>
        <view v-if="state.createUnknown" class="notice"><text>创建请求的结果尚未确认。重试沿用同一创建请求键。</text><button class="secondary-button" :disabled="state.busy || (!state.consentAccepted && !state.consentChoice)" @click="controller.createThread(state.createMode, true)">重试原创建请求</button></view>
        <text class="field-label">当前本人成员的咨询记录</text><text class="body-copy">每次读取20条真实绑定记录；点击后重新核对历史与最终回答的读取权限。</text>
        <button class="text-button" :disabled="state.listLoading || state.busy" @click="controller.loadConsultations(false)">重新读取咨询记录</button>
        <text v-if="state.listLoading" class="status-loading">正在读取咨询记录…</text>
        <text v-if="!state.consultations.length && !state.listLoading" class="body-copy">当前没有可恢复的真实咨询记录。</text>
        <view class="choice-list"><button v-for="thread in state.consultations" :key="thread.thread_id" class="choice-button" :class="{ selected: state.thread?.thread_id === thread.thread_id }" :disabled="state.busy || state.historyLoading || waiting || state.createUnknown" @click="controller.openThread(thread.thread_id)"><view class="choice-indicator" /><view class="choice-copy"><text>{{ thread.business_date ? thread.business_date + ' · 日咨询' : '独立咨询' }}</text><text class="choice-detail">{{ thread.created_at || '服务端咨询记录' }}</text><text class="choice-detail">线程：{{ thread.thread_id }}</text></view></button></view>
        <button v-if="state.hasMore" class="secondary-button" :disabled="state.listLoading" @click="controller.loadConsultations(true)">读取更多咨询记录</button>
      </view>
      <view v-if="state.thread" class="card access-card">
        <text class="section-title">{{ state.thread.business_date ? state.thread.business_date + ' 的咨询' : '独立咨询' }}</text>
        <text class="body-copy">展示当前线程最近20次完成的顶层咨询。待处理、失败、工具与内部审计内容不会作为回答展示。</text>
        <text v-if="state.historyLoading" class="status-loading">正在核对历史回答…</text>
        <text v-if="!state.historyLoading && !state.messages.length" class="body-copy">尚无可展示的完成回答。</text>
        <view v-for="row in state.messages" :key="row.id" class="conversation-message" :class="row.role"><text class="message-label">{{ row.role === 'user' ? '你的问题' : '营养咨询回答' }}</text><text class="message-text" selectable>{{ row.text }}</text></view>
        <view v-if="hasAnswers" class="notice"><text>引用来源：当前公开结果接口未提供可展示的结构化引用。此页没有提取正文链接或内部工具记录作为来源。</text></view>
        <view v-if="state.request" class="result-row"><text class="result-label">真实请求与运行</text><text>Request：{{ state.request.request_id }}</text><text v-if="state.run">Run：{{ state.run.run_id }}</text><text>{{ runStatusLabel(state.run?.status || state.request.status) }}</text></view>
        <text v-if="state.polling" class="status-loading">正在有界读取同一请求，离开页面会停止本地等待…</text>
        <button v-if="state.pollTimedOut" class="secondary-button" :disabled="state.busy" @click="controller.continuePolling">继续读取原请求</button>
        <view v-if="state.submitUnknown" class="notice"><text>提交结果尚未确认，原问题仅保留在本页内存。重试会使用相同正文、线程及请求键。</text><button class="secondary-button" :disabled="state.busy || !state.consentAccepted" @click="controller.submit(true)">重试原问题</button></view>
        <button v-if="!state.consentAccepted" class="secondary-button" :disabled="!eligible || !state.consentChoice || state.busy || state.historyLoading" @click="controller.acceptForThread">保存本次明确同意，继续此咨询</button>
        <text class="field-label">营养问题</text><textarea class="question-input" :value="state.query" :disabled="!state.consentAccepted || state.busy || waiting || state.historyLoading || state.run?.status === 'interrupted'" maxlength="4000" placeholder="填写你本次想咨询的营养问题" aria-label="营养问题" @input="controller.setQuery($event.detail.value)" />
        <button class="primary-button" :disabled="!canSubmit" @click="controller.submit(false)">{{ state.busy ? '正在提交…' : '提交营养问题' }}</button>
      </view>
      <text class="safe-note">咨询正文只保留在当前页面内存。隐藏、退出、401 或账号切换会清理旧内容。真实历史由服务端保存并在每次读取时校验授权。当前未接入自动恢复中断、完整专业档案与营养安全规则验收。</text>
    </template>
  </view>
</template>

<style scoped>
.question-input{box-sizing:border-box;width:100%;height:230rpx;margin-top:16rpx;padding:22rpx;border:2rpx solid #dedee3;border-radius:18rpx;background:#fafafb;font-size:28rpx;line-height:1.6}.conversation-message{padding:24rpx;margin:22rpx 0;border-radius:20rpx;background:#f2f3f5}.conversation-message.assistant{background:#edf4ef}.message-label{display:block;color:#526456;font-size:24rpx;margin-bottom:12rpx}.message-text{display:block;white-space:pre-wrap;font-size:28rpx;line-height:1.75;overflow-wrap:anywhere}.consultation-screen .nav-row>.text-button{width:110rpx;margin:0}.consultation-screen .safe-note{display:block}
</style>
