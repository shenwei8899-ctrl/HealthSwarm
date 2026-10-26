<script setup>
import { ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import AppNavBar from '../../components/AppNavBar.vue'
import PlanDeliveryPicker from '../../components/PlanDeliveryPicker.vue'
import { commerce } from '../../services/commerce.js'
import { useCommercePage } from '../../services/commerce-page.js'
import { priceText, validPlanRoute } from '../../services/plan-presentation.js'
const route = ref(null), selection = ref(null), quote = ref(null), pending = ref(false)
const { busy, error, run } = useCommercePage(() => { quote.value = null; selection.value = null; pending.value = false })
onLoad(options => { try { route.value = validPlanRoute(options) } catch (e) { error.value = e.message } })
onShow(() => { quote.value = null; pending.value = !!commerce.pendingOrder() })
function change(value) { selection.value = value; quote.value = null }
function preview() {
  if (!selection.value || !route.value) return
  return run(async active => {
    quote.value = null
    if (commerce.pendingOrder()) { pending.value = true; return }
    const s = selection.value
    const result = await commerce.quotePlan(route.value.sn, route.value.version, s.address_id, s.first_delivery_date, s.delivery_slot_id)
    if (active()) quote.value = result
  })
}
function submit(recover = false) {
  return run(async active => {
    if (!recover && (!quote.value || Date.parse(quote.value.expires_at) <= Date.now())) { quote.value = null; throw new Error('报价已过期，请重新核对金额') }
    try {
      const result = recover ? await commerce.retryOrder() : await commerce.createOrder(quote.value.checkout_token)
      if (active()) { quote.value = null; uni.redirectTo({url:'/pages/orders/detail?id='+encodeURIComponent(result.order_sn)}) }
    } finally { if (active()) pending.value = !!commerce.pendingOrder() }
  })
}
const back = () => uni.navigateBack()
</script>
<template>
  <view class="screen exclusive-screen schedule-screen">
    <AppNavBar><view class="nav-row"><button class="icon-button" aria-label="返回" @click="back">‹</button><text class="nav-title">配送安排</text></view></AppNavBar>
    <view class="plan-heading"><view class="plan-title"><text class="plan-title-line">为接下来的三餐，</text><text class="plan-title-line">做好准备。</text></view><text class="plan-caption">每日一批 · 提前一天送达</text></view>
    <view v-if="pending" class="plan-surface"><text class="plan-section-title">上次下单结果待确认</text><button class="plan-primary" :disabled="busy" @click="submit(true)">查询原订单</button></view>
    <PlanDeliveryPicker v-if="route && !pending" :sn="route.sn" :version="route.version" :disabled="busy" @change="change"/>
    <view v-if="error" class="plan-notice">{{error}}</view>
    <template v-if="quote && !pending">
      <view class="plan-surface"><text class="plan-section-title">这一次的费用</text><view class="plan-row"><text>21 批食材</text><text>{{priceText(quote.goods_amount_cent)}}</text></view><view class="plan-row"><text>计划服务费</text><text>{{priceText(quote.service_fee_cent)}}</text></view><view class="plan-row"><text>21 批配送费</text><text>{{priceText(quote.shipping_fee_cent)}}</text></view><view v-if="quote.discount_amount_cent" class="plan-row"><text>优惠</text><text>−{{priceText(quote.discount_amount_cent)}}</text></view><view class="plan-row total-row"><text>一次支付</text><text>{{priceText(quote.payable_amount_cent)}}</text></view></view>
      <view class="plan-surface"><text class="plan-section-title">21 次配送</text><view v-for="batch in quote.delivery_batches" :key="batch.batch_no" class="batch-row"><text class="batch-number">{{batch.batch_no}}</text><view><text>{{batch.delivery_date}} 送达</text><text class="plan-tiny">{{batch.meal_date}} 食用</text></view><text class="plan-tiny">{{priceText(batch.allocated_pay_amount_cent)}}</text></view></view>
      <text class="plan-notice">未截单、未备货的批次可暂停或取消。取消按购买时分摊金额退回，已执行批次的优惠不追回。</text>
    </template>
    <view v-if="route && !pending" class="plan-fixed"><button v-if="!quote" class="plan-primary" :disabled="busy || !selection" @click="preview">{{busy?'正在核对…':'核对配送与金额'}}</button><button v-else class="plan-primary" :disabled="busy" @click="submit(false)">确认下单 · {{priceText(quote.payable_amount_cent)}}</button></view>
  </view>
</template>
<style scoped>
@import '../../styles/exclusive-plan.css';
.schedule-screen{padding-bottom:calc(170rpx + env(safe-area-inset-bottom))}.batch-row{display:flex;gap:24rpx;align-items:center;padding:22rpx 0;border-bottom:1rpx solid #eff1f5;font-size:28rpx}.batch-row:last-child{border:0}.batch-row>view{flex:1}.batch-row>view>text{display:block}.batch-number{width:48rpx;height:48rpx;line-height:48rpx;text-align:center;background:#edf5ff;border-radius:50%;color:#267ddf;font-size:25rpx}.total-row{font-weight:500}.total-row>text:last-child{font-size:36rpx}
</style>
