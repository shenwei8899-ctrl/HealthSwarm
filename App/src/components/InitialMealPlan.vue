<script setup>
import { reactive, ref, watch, onUnmounted } from 'vue'
import { createInitialPlanClient, initialPlanState } from '../services/health-initial-plan-client.js'
import { scopedStorage } from '../services/storage.js'
const props = defineProps({ memberId: String })
const emit = defineEmits(['saved'])
const state = reactive(initialPlanState()), followup = ref('')
const today = () => new Date(Date.now() + 8 * 3600000).toISOString().slice(0,10)
const date = ref(scopedStorage.getStorageSync('initial-plan-date') || today())
const client = createInitialPlanClient({ state, onSaved: plan => emit('saved', plan) })
const names = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐' }
watch(() => props.memberId, id => { if(id) client.open(id, date.value); else client.hide() }, { immediate: true })
function chooseDate(event) { date.value = event.detail.value; scopedStorage.setStorageSync('initial-plan-date', date.value); client.open(props.memberId, date.value) }
function inspect() { uni.navigateTo({ url: '/pages/health/plans?memberId=' + encodeURIComponent(props.memberId) + '&planId=' + encodeURIComponent(state.saved.plan_id) }) }
onUnmounted(() => client.hide())
</script>

<template>
  <view class="initial-plan card">
    <text class="section-title">制定单日三餐计划</text>
    <picker mode="date" :value="date" :disabled="state.loading || state.saving || state.task.busy || !!state.pending" @change="chooseDate"><view class="date-choice">安排日期：{{date}} · 点击选择</view></picker>
    <text>根据所选成员已确认的营养档案和已批准规则生成，核对三餐后再保存。</text>
    <text v-if="state.loading">正在核对档案与配餐来源…</text>
    <text v-if="state.notice">{{state.notice}}</text>
    <text v-if="state.error || state.task.error" class="inline-error">{{state.error || state.task.error}}</text>
    <button v-if="state.error && !state.pending" class="secondary-button" @click="client.open(memberId,date)">重新读取</button>
    <view v-if="state.task.consentOption" class="consent">
      <text>生成时会将本任务需要的已授权资料发送给 {{state.task.consentOption.processor}}，用于配餐。请确认是否同意。</text>
      <button class="secondary-button" :disabled="state.task.busy" @click="client.flow.acceptConsent(true)">同意用于本次配餐</button>
    </view>
    <text v-else-if="state.task.notice">{{state.task.notice}}</text>
    <button v-if="state.task.available && !state.pending && !state.task.submitUnknown" class="secondary-button" :disabled="state.loading || state.saving || state.task.busy || ['pending','queued','running'].includes(state.task.status)" @click="client.generate()">{{state.task.busy ? '正在提交…' : client.preview() ? '重新生成三餐' : '生成这一天的三餐'}}</button>
    <text v-if="state.task.status">生成状态：{{state.task.status}}</text>
    <button v-if="state.task.requestId" class="secondary-button" :disabled="state.saving || state.task.busy" @click="client.flow.refresh()">读取当前任务</button>
    <button v-if="state.task.canRetry" class="secondary-button" :disabled="state.task.busy" @click="client.flow.submit('',true)">用原请求重试生成</button>
    <view v-if="state.task.result?.type==='needs_input'">
      <text v-for="question in state.task.result.questions" :key="question">{{question}}</text>
      <textarea v-model="followup" maxlength="4000" placeholder="补充本次安排要求" />
      <button class="secondary-button" :disabled="!followup.trim() || state.task.busy" @click="client.generate(followup)">补充后继续</button>
    </view>
    <text v-if="state.task.result?.type==='error'" class="inline-error">本次生成未完成，请重新读取或重试。</text>
    <view v-if="client.preview()" class="preview">
      <view v-for="meal in client.preview().plan_snapshot.meals" :key="meal.meal_type" class="meal">
        <text class="section-title">{{names[meal.meal_type]}}</text>
        <text v-for="dish in meal.dishes" :key="dish.dish_index">{{dish.name}} · 计划份量 {{dish.planned_grams ?? '未知'}} g</text>
        <text>计划能量 {{meal.nutrition?.totals?.energy_kcal ?? '未知'}} kcal</text>
      </view>
      <text>此预览尚未正式采用。保存后仍须按专业审核流程确认，不自动替换今日安排、记餐或购买。</text>
      <button v-if="!state.saved" class="secondary-button" :disabled="state.saving || state.task.busy" @click="client.confirmSave()">{{state.saving ? '正在保存…' : state.pending ? '用原请求核对保存结果' : '确认三餐并保存草稿'}}</button>
    </view>
    <text v-else-if="state.task.result?.type==='business'">当前资料或菜谱无法生成合格的三餐，请补充资料或联系营养师核对。</text>
    <button v-if="state.pending && !client.preview()" class="secondary-button" :disabled="state.saving" @click="client.confirmSave()">用原请求核对上次保存结果</button>
    <view v-if="state.saved"><text>三餐草稿已保存，可在下方计划列表重新读取。</text><button class="secondary-button" @click="inspect">查看已保存计划</button></view>
  </view>
</template>

<style scoped>
.initial-plan,.preview,.meal,.consent{display:flex;flex-direction:column;gap:20rpx}.initial-plan{padding:30rpx;margin-top:24rpx;font-size:26rpx;line-height:1.7}.date-choice,.meal{padding:20rpx;background:#f0f4f1;border-radius:16rpx}.initial-plan textarea{box-sizing:border-box;width:100%;padding:20rpx;border:1px solid #cbd8cf;border-radius:12rpx}
</style>
