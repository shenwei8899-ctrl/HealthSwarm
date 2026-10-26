<script setup>
import { ref, watch } from 'vue'
import { commerce } from '../services/commerce.js'
import { useCommercePage } from '../services/commerce-page.js'
import { priceText, batchNames } from '../services/plan-presentation.js'
import PlanDeliveryPicker from './PlanDeliveryPicker.vue'
const props = defineProps({ order: Object })
const emit = defineEmits(['changed'])
const mode = ref(''), selection = ref(null), preview = ref(null), message = ref('')
const { busy, error, run } = useCommercePage(() => { mode.value = ''; preview.value = null; selection.value = null; message.value = '' })
watch(() => props.order.plan?.row_version, () => { preview.value = null; mode.value = '' })
function pause() {
  uni.showModal({title:'暂停未来配送', content:'只暂停未截单、未备货的批次。已安排备货的批次继续配送。', confirmText:'确认暂停', success:({confirm}) => {
    if (confirm) run(async active => { await commerce.pausePlan(props.order.id, Number(props.order.plan.row_version)); if (active()) { message.value='可变更批次已暂停'; emit('changed') } })
  }})
}
function change(value) { selection.value = value; preview.value = null }
function prepare(type) {
  return run(async active => {
    preview.value = null
    const result = type === 'resume'
      ? await commerce.previewResumePlan(props.order.id, {...selection.value, version:Number(props.order.plan.row_version)})
      : await commerce.previewCancelPlan(props.order.id, Number(props.order.plan.row_version))
    if (active()) { mode.value = type; preview.value = result }
  })
}
function confirm() {
  return run(async active => {
    if (!preview.value) return
    const result = await commerce.confirmPlanChange(props.order.id, preview.value.change_request_sn)
    if (active()) {
      message.value = result.refund_sn ? '剩余批次已停止配送，退款正在处理' : result.status === 'active' ? '新配送安排已确认' : '剩余批次已取消'
      preview.value = null; mode.value = ''; emit('changed')
    }
  })
}
</script>
<template>
  <view class="exclusive-screen plan-order-controls">
    <view class="plan-surface">
      <text class="plan-section-title">配送计划</text>
      <text class="plan-caption">{{order.plan?.status==='paused'?'已暂停未来配送':order.plan?.status==='completed'?'计划已完成':order.plan?.status==='cancelled'?'计划已取消':'按批次查看进度'}}</text>
      <view v-for="batch in order.batches" :key="batch.id" class="plan-row"><view><text>第 {{batch.batch_no}} 批 · {{batch.delivery_date}}</text><text class="plan-tiny">{{batch.meal_date}} 食用</text></view><text class="plan-caption">{{batchNames[batch.status] || '处理中'}}</text></view>
      <view v-if="['paid','partially_refunded'].includes(order.paymentStatus) && Number(order.plan?.user_cancellable)===1" class="plan-actions">
        <button v-if="order.plan.status==='active'" class="plan-secondary" :disabled="busy" @click="pause">暂停未来配送</button>
        <button v-if="order.plan.status==='paused'" class="plan-primary" :disabled="busy" @click="mode='resume'; preview=null">重新预约配送</button>
        <button v-if="['active','paused'].includes(order.plan.status)" class="plan-text-link" :disabled="busy" @click="prepare('cancel_remaining')">取消剩余批次 <text>›</text></button>
      </view>
    </view>
    <PlanDeliveryPicker v-if="mode==='resume'" :sn="order.id" resume :disabled="busy" @change="change"/>
    <button v-if="mode==='resume' && !preview" class="plan-primary" :disabled="busy || !selection" @click="prepare('resume')">预览新的配送安排</button>
    <view v-if="preview" class="plan-surface">
      <text class="plan-section-title">{{preview.type==='resume'?'确认恢复配送':'确认取消剩余批次'}}</text>
      <view v-for="batch in preview.batches" :key="batch.id" class="plan-row"><text>第 {{batch.batch_no}} 批</text><view v-if="batch.schedule"><text>{{batch.schedule.delivery_date}} 送达</text><text class="plan-tiny">{{batch.schedule.meal_date}} 食用</text></view><text v-else>{{priceText(batch.refund_amount_cent)}}</text></view>
      <view v-if="preview.type==='cancel_remaining'"><view class="plan-row"><text>预计退回</text><text>{{priceText(preview.refund_amount_cent)}}</text></view><text class="plan-caption">包含这些批次分摊的食材、服务及配送费用，扣除原优惠与已退金额。其他批次继续履行。</text></view>
      <button class="plan-primary" :disabled="busy" @click="confirm">{{preview.type==='resume'?'确认恢复配送':'确认取消并申请退款'}}</button>
      <button class="plan-text-link" :disabled="busy" @click="preview=null; mode=''">暂不变更</button>
    </view>
    <text v-if="error" class="plan-notice">{{error}}</text><text v-if="message" class="plan-notice">{{message}}</text>
  </view>
</template>
<style scoped>
@import '../styles/exclusive-plan.css';
.plan-order-controls{min-height:0;padding-bottom:0;background:transparent}.plan-actions{display:flex;flex-direction:column;gap:16rpx;margin-top:24rpx}.plan-row>view>text{display:block}.plan-surface>.plan-primary{margin-top:24rpx}
</style>
