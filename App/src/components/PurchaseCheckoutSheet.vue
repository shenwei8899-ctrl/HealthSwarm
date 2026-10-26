<script setup>
import { computed, ref, watch } from 'vue'
import FoodImageSlot from './FoodImageSlot.vue'
const props = defineProps({
  open: Boolean, title: { type: String, default: '确认采购订单' },
  address: Object, slots: { type: Array, default: () => [] }, slotId: [String, Number],
  quote: Object, products: { type: Array, default: () => [] }, busy: Boolean,
  error: String, pending: Boolean, accessRequired: Boolean,
})
defineEmits(['close', 'address', 'slot', 'confirm', 'recover', 'quote'])
const choosingSlot = ref(false)
watch(() => props.open, () => { choosingSlot.value = false })
const slot = computed(() => props.slots.find(s => String(s.id) === String(props.slotId)))
const slotName = item => item ? item.name || [item.start_time, item.end_time].filter(Boolean).join('—') : '选择送达时间'
const money = cents => (Number(cents || 0) / 100).toFixed(2)
const lines = computed(() => (props.quote?.items || []).map(line => {
  const product = props.products.find(item => String(item.id ?? item.skuId) === String(line.sku_id))
  return { ...line, name: line.snapshot?.product_name || product?.name || '商品',
    image: line.snapshot?.image_url || product?.imageUrl || '', spec: product?.packLabel || line.snapshot?.sku_name || '' }
}))
</script>
<template>
  <view v-if="open" class="checkout-mask" @click.self="!busy && $emit('close')">
    <view class="checkout-panel" role="dialog" aria-modal="true" :aria-label="title">
      <view class="checkout-heading"><text>{{title}}</text><button :disabled="busy" aria-label="关闭订单确认" @click="$emit('close')">×</button></view>
      <scroll-view class="checkout-body" scroll-y>
        <slot v-if="accessRequired" name="access" />
        <template v-else>
          <button class="delivery-row address-row" :disabled="busy" @click="$emit('address')">
            <view class="location-icon" aria-hidden="true"><view /></view>
            <view class="delivery-copy"><text class="address-person">{{address ? (address.name || address.receiver) + ' · ' + (address.phone || address.mobile) : '选择收货地址'}}</text><text v-if="address" class="supporting">{{address.region}} {{address.detail}}</text></view><text class="chevron">›</text>
          </button>
          <button class="delivery-row" :disabled="busy || !slots.length" @click="choosingSlot=!choosingSlot"><text class="delivery-label">送达时间</text><text class="slot-value">{{slotName(slot)}}</text><text class="chevron">›</text></button>
          <view v-if="choosingSlot" class="slot-options"><button v-for="item in slots" :key="item.id" :disabled="busy" :class="{chosen:String(item.id)===String(slotId)}" @click="$emit('slot',item.id);choosingSlot=false">{{slotName(item)}}<text v-if="String(item.id)===String(slotId)">✓</text></button></view>
          <text v-if="error" class="checkout-error" role="alert">{{error}}</text>
          <view v-if="quote" class="quote">
            <view v-for="line in lines" :key="line.sku_id" class="checkout-item"><FoodImageSlot :src="line.image" :label="line.name" class="item-image"/><view class="item-copy"><text class="item-name">{{line.name}}</text><text v-if="line.spec" class="supporting">{{line.spec}}</text></view><view class="item-numbers"><text>¥{{money(line.line_amount_cent)}}</text><text class="supporting">×{{line.quantity}}</text></view></view>
            <view class="costs"><view><text>商品金额</text><text>¥{{money(quote.goods_amount_cent)}}</text></view><view><text>配送费</text><text>¥{{money(quote.shipping_fee_cent)}}</text></view><view v-if="Number(quote.discount_amount_cent)>0"><text>优惠</text><text>−¥{{money(quote.discount_amount_cent)}}</text></view></view>
          </view>
        </template>
      </scroll-view>
      <view v-if="!accessRequired" class="checkout-footer">
        <view v-if="quote" class="payable"><text>应付金额</text><text class="amount">¥{{money(quote.payable_amount_cent)}}</text></view>
        <button v-if="pending" class="checkout-submit" :disabled="busy" @click="$emit('recover')">确认原订单结果</button>
        <button v-else-if="!address" class="checkout-submit" :disabled="busy" @click="$emit('address')">添加收货地址</button>
        <button v-else-if="quote" class="checkout-submit" :disabled="busy" @click="$emit('confirm')">{{busy?'正在核对…':'确认下单'}} <text>¥{{money(quote.payable_amount_cent)}}</text></button>
        <button v-else class="checkout-submit" :disabled="busy" @click="$emit('quote')">{{busy?'正在核对…':'核对商品与价格'}}</button>
        <text class="payment-note">下单后进入订单详情支付</text>
      </view>
    </view>
  </view>
</template>
<style scoped>
.checkout-mask{position:fixed;inset:0;z-index:100;background:rgba(24,29,36,.28);display:flex;align-items:flex-end}
.checkout-panel{width:100%;max-height:90vh;display:flex;flex-direction:column;background:#fff;border-radius:40rpx 40rpx 0 0;overflow:hidden;color:#232936;box-sizing:border-box}
.checkout-heading{display:flex;justify-content:space-between;align-items:center;gap:16rpx;padding:18rpx 32rpx 6rpx;flex-shrink:0;font-size:36rpx;font-weight:500}
.checkout-heading button{display:flex;align-items:center;justify-content:center;width:44px;height:44px;font-size:36rpx;color:#6d7688;flex-shrink:0}
.checkout-body{max-height:60vh;height:auto;min-height:0}.delivery-row{display:flex;align-items:center;gap:18rpx;width:calc(100% - 64rpx);margin:16rpx 32rpx 0;padding:20rpx;border:1rpx solid #e9edf3;border-radius:24rpx;text-align:left;min-height:88rpx;font-size:27rpx;box-sizing:border-box}
.address-row{padding:24rpx 20rpx}.delivery-copy{flex:1;min-width:0}.delivery-copy text{display:block}.address-person{font-size:29rpx;font-weight:500;overflow-wrap:anywhere}.supporting{color:#65728c;font-size:24rpx;line-height:1.6}.address-row .supporting{margin-top:6rpx}.delivery-label{flex-shrink:0}.slot-value{flex:1;text-align:right;min-width:0;line-height:1.6}.chevron{color:#8390a6;font-size:34rpx;flex-shrink:0}
.location-icon{width:30rpx;height:38rpx;border:3rpx solid #414b60;border-radius:50% 50% 50% 0;transform:rotate(-45deg);margin:0 8rpx 6rpx 4rpx;flex-shrink:0}.location-icon view{width:10rpx;height:10rpx;border:2rpx solid #414b60;border-radius:50%;margin:9rpx auto}
.slot-options{margin:12rpx 32rpx;padding:8rpx 20rpx;border-radius:20rpx;background:#f6f8fb}.slot-options button{width:100%;display:flex;justify-content:space-between;align-items:center;min-height:44px;font-size:26rpx;color:#626e80}.slot-options .chosen{color:#0674ed}
.checkout-error{display:block;margin:18rpx 32rpx;color:#b83532;font-size:26rpx;line-height:1.6}.quote{padding:4rpx 32rpx 0}.checkout-item{display:flex;align-items:center;gap:20rpx;padding:22rpx 0;border-bottom:1rpx solid #f0f2f6}.item-image{width:116rpx;height:116rpx;border-radius:18rpx}.item-copy{flex:1;min-width:0}.item-copy text{display:block}.item-name{font-size:28rpx;font-weight:500;line-height:1.5;overflow-wrap:anywhere}.item-copy .supporting{margin-top:8rpx}.item-numbers{display:flex;flex-direction:column;align-items:flex-end;gap:8rpx;font-size:27rpx;flex-shrink:0;font-variant-numeric:tabular-nums}.costs{padding:18rpx 0 8rpx;color:#65728c;font-size:26rpx}.costs>view{display:flex;justify-content:space-between;gap:24rpx;padding:5rpx 0}
.checkout-footer{padding:16rpx 32rpx calc(env(safe-area-inset-bottom) + 20rpx);flex-shrink:0}.payable{display:flex;justify-content:space-between;align-items:baseline;margin:0 0 20rpx;font-size:30rpx}.amount{font-size:44rpx;font-weight:600;font-variant-numeric:tabular-nums}.checkout-submit{width:100%;min-height:92rpx;padding:18rpx 20rpx;border-radius:999rpx;background:#25262a;color:#fff;display:flex;align-items:center;justify-content:center;gap:16rpx;font-size:30rpx;line-height:1.5}.payment-note{display:block;text-align:center;margin-top:12rpx;font-size:24rpx;color:#65728c}button[disabled]{opacity:.45}
/* #ifdef H5 */
.checkout-panel{max-width:480px;margin:0 auto}
/* #endif */
</style>
