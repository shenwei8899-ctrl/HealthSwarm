<script setup>
import { computed, ref, watch, onUnmounted } from 'vue'
import FoodImageSlot from './FoodImageSlot.vue'
const props = defineProps({
  open: Boolean, embedded: Boolean, title: { type: String, default: '确认采购订单' },
  address: Object, slots: { type: Array, default: () => [] }, slotId: [String, Number],
  quote: Object, products: { type: Array, default: () => [] }, busy: Boolean,
  error: String, pending: Boolean, accessRequired: Boolean,
  addressBusy: {type:Boolean,default:undefined}, slotsBusy: {type:Boolean,default:undefined},
})
defineEmits(['close', 'address', 'slot', 'confirm', 'recover', 'quote'])
const choosingSlot = ref(false)
const panelHeight = ref(80), dragging = ref(false)
const dragArea = ref(null)
let gesture = null, moved = false
// #ifdef H5
let mouseArea = null
watch(dragArea, value => {
  mouseArea?.removeEventListener('mousedown', startDrag)
  mouseArea = value?.$el || value
  mouseArea?.addEventListener('mousedown', startDrag)
}, { flush: 'post' })
// #endif
const clampHeight = value => Math.max(42, Math.min(92, value))
function stopDrag() {
  gesture = null
  dragging.value = false
  // #ifdef H5
  document.removeEventListener('mousemove', moveDrag)
  document.removeEventListener('mouseup', stopDrag)
  // #endif
}
watch(() => props.open, () => {
  choosingSlot.value = false
  stopDrag()
  panelHeight.value = 80
})
function startDrag(event) {
  // #ifdef H5
  if (event.target?.closest?.('[aria-label="关闭订单确认"]')) return
  // #endif
  if (props.embedded || (event.touches && event.touches.length !== 1) || (event.button != null && event.button !== 0)) return
  const point = event.touches?.[0] || event
  const y = point.clientY ?? point.pageY
  if (!Number.isFinite(y)) return
  const viewport = uni.getWindowInfo().windowHeight
  if (!(viewport > 0)) return
  moved = false
  gesture = { y, height: panelHeight.value, viewport, id: point.identifier }
  dragging.value = true
  // #ifdef H5
  if (!event.touches) {
    event.preventDefault()
    document.addEventListener('mousemove', moveDrag)
    document.addEventListener('mouseup', stopDrag)
  }
  // #endif
}
function moveDrag(event) {
  if (!gesture) return
  if (event.touches && event.touches.length !== 1) { stopDrag(); return }
  const point = event.touches?.[0] || event
  if (gesture.id != null && point.identifier !== gesture.id) return
  const delta = gesture.y - (point.clientY ?? point.pageY)
  if (!Number.isFinite(delta) || (!moved && Math.abs(delta) < 4)) return
  moved = true
  panelHeight.value = clampHeight(gesture.height + delta / gesture.viewport * 100)
}
function toggleHeight() {
  if (!moved) panelHeight.value = panelHeight.value < 86 ? 92 : 42
}
onUnmounted(() => {
  stopDrag()
  // #ifdef H5
  mouseArea?.removeEventListener('mousedown', startDrag)
  // #endif
})
const slot = computed(() => props.slots.find(s => String(s.id) === String(props.slotId)))
const slotName = item => item ? item.name || [item.start_time, item.end_time].filter(Boolean).join('—') : '选择送达时间'
const money = cents => (Number(cents || 0) / 100).toFixed(2)
const lines = computed(() => (props.quote?.items || props.products.map(p=>({sku_id:p.id,quantity:p.quantity,line_amount_cent:Number.isFinite(p.priceCents)?p.priceCents*p.quantity:null}))).map(line => {
  const product = props.products.find(item => String(item.id ?? item.skuId) === String(line.sku_id))
  return { ...line, name: line.snapshot?.product_name || product?.name || '商品',
    image: line.snapshot?.image_url || product?.imageUrl || '', spec: product?.packLabel || line.snapshot?.sku_name || '' }
}))
</script>
<template>
  <view v-if="open" class="checkout-mask" :class="{'is-embedded':embedded}" @click.self="!busy && $emit('close')">
    <view class="checkout-panel" :class="{'is-dragging':dragging}" :style="embedded ? {} : {height:panelHeight+'vh'}" role="dialog" aria-modal="true" :aria-label="title">
      <view v-if="!embedded" ref="dragArea" class="checkout-drag-area" @touchstart.stop="startDrag" @touchmove.stop.prevent="moveDrag" @touchend.stop="stopDrag" @touchcancel.stop="stopDrag">
        <button class="checkout-grip" aria-label="调整订单面板高度" :aria-expanded="panelHeight>=86" @click="toggleHeight"><view /></button>
        <view class="checkout-heading"><text>{{title}}</text><button :disabled="busy" aria-label="关闭订单确认" @touchstart.stop @mousedown.stop @click="$emit('close')">×</button></view>
      </view>
      <scroll-view class="checkout-body" scroll-y :show-scrollbar="false">
        <slot v-if="accessRequired" name="access" />
        <template v-else>
          <button class="delivery-row address-row" :disabled="addressBusy??busy" @click="$emit('address')">
            <view class="location-icon" aria-hidden="true"><view /></view>
            <view class="delivery-copy"><text class="address-person">{{address ? (address.name || address.receiver) + ' · ' + (address.phone || address.mobile) : '选择收货地址'}}</text><text v-if="address" class="supporting">{{address.region}} {{address.detail}}</text></view><text class="chevron">›</text>
          </button>
          <button class="delivery-row" :disabled="(slotsBusy??busy) || !slots.length" @click="choosingSlot=!choosingSlot"><text class="delivery-label">送达时间</text><text class="slot-value">{{slotName(slot)}}</text><text class="chevron">›</text></button>
          <view v-if="choosingSlot" class="slot-options"><button v-for="item in slots" :key="item.id" :disabled="slotsBusy??busy" :class="{chosen:String(item.id)===String(slotId)}" @click="$emit('slot',item.id);choosingSlot=false">{{slotName(item)}}<text v-if="String(item.id)===String(slotId)">✓</text></button></view>
          <text v-if="error" class="checkout-error" role="alert">{{error}}</text>
          <view class="quote"><text class="review-caption">已选食材 · {{lines.length}} 项</text>
            <view v-for="line in lines" :key="line.sku_id" class="checkout-item"><view class="item-image"><FoodImageSlot :src="line.image" :label="line.name" :width="56" :height="56" :radius="14"/></view><view class="item-copy"><text class="item-name">{{line.name}}</text><text v-if="line.spec" class="supporting">{{line.spec}}</text></view><view class="item-numbers"><text>{{Number.isFinite(line.line_amount_cent)?'¥'+money(line.line_amount_cent):'待核价'}}</text><text class="supporting">×{{line.quantity}}</text></view></view>
            <view v-if="quote" class="costs"><view><text>商品金额</text><text>¥{{money(quote.goods_amount_cent)}}</text></view><view><text>配送费</text><text>¥{{money(quote.shipping_fee_cent)}}</text></view><view v-if="Number(quote.discount_amount_cent)>0"><text>优惠</text><text>−¥{{money(quote.discount_amount_cent)}}</text></view></view><text v-else class="repricing-note">{{busy?'正在更新商品金额与配送费…':'商品已保留，请核对价格与配送费'}}</text>
          </view>
        </template>
      </scroll-view>
      <view v-if="!accessRequired" class="checkout-footer">
        <view v-if="quote" class="payable"><text>应付金额</text><text class="amount">¥{{money(quote.payable_amount_cent)}}</text></view>
        <button v-if="pending" class="checkout-submit" :disabled="busy" @click="$emit('recover')">确认原订单结果</button>
        <button v-else-if="!address" class="checkout-submit" :disabled="addressBusy??busy" @click="$emit('address')">添加收货地址</button>
        <button v-else-if="quote" class="checkout-submit" :disabled="busy" @click="$emit('confirm')">{{busy?'正在核对…':'确认下单'}} <text>¥{{money(quote.payable_amount_cent)}}</text></button>
        <button v-else class="checkout-submit" :disabled="busy" @click="$emit('quote')">{{busy?'正在核对…':'核对商品与价格'}}</button>
      </view>
    </view>
  </view>
</template>
<style scoped>
.checkout-mask{position:fixed;inset:0;z-index:100;background:var(--ui-overlay);display:flex;align-items:flex-end}
.checkout-panel{width:100%;max-height:92vh;display:flex;flex-direction:column;background:#fff;border-radius:40rpx 40rpx 0 0;overflow:hidden;color:#232936;box-sizing:border-box;transition:height .2s ease}
.checkout-panel.is-dragging{transition:none}.checkout-drag-area{flex-shrink:0;touch-action:none;user-select:none;cursor:ns-resize}.checkout-grip{display:flex;align-items:center;justify-content:center;width:100%;height:24px;min-height:24px;margin:0;padding:0;background:transparent;cursor:ns-resize}.checkout-grip>view{width:32px;height:4px;border-radius:4px;background:#b9bfce}.checkout-grip:after{border:0}@media(prefers-reduced-motion:reduce){.checkout-panel{transition:none}}
.checkout-heading{display:flex;justify-content:space-between;align-items:center;gap:16rpx;padding:18rpx 32rpx 6rpx;flex-shrink:0;font-size:36rpx;font-weight:500}
.checkout-heading button{display:flex;align-items:center;justify-content:center;width:44px;height:44px;font-size:36rpx;color:#6d7688;flex-shrink:0}
.checkout-body{flex:1;height:0;min-height:0}.delivery-row{display:flex;align-items:center;gap:18rpx;width:calc(100% - 64rpx);margin:16rpx 32rpx 0;padding:20rpx;border:1rpx solid #e9edf3;border-radius:24rpx;text-align:left;min-height:88rpx;font-size:27rpx;box-sizing:border-box}
.address-row{padding:24rpx 20rpx}.delivery-copy{flex:1;min-width:0}.delivery-copy text{display:block}.address-person{font-size:29rpx;font-weight:500;overflow-wrap:anywhere}.supporting{color:var(--ui-muted);font-size:24rpx;line-height:1.6}.address-row .supporting{margin-top:6rpx}.delivery-label{flex-shrink:0}.slot-value{flex:1;text-align:right;min-width:0;line-height:1.6}.chevron{color:#8390a6;font-size:34rpx;flex-shrink:0}
.location-icon{width:30rpx;height:38rpx;border:3rpx solid #414b60;border-radius:50% 50% 50% 0;transform:rotate(-45deg);margin:0 8rpx 6rpx 4rpx;flex-shrink:0}.location-icon view{width:10rpx;height:10rpx;border:2rpx solid #414b60;border-radius:50%;margin:9rpx auto}
.slot-options{margin:12rpx 32rpx;padding:8rpx 20rpx;border-radius:20rpx;background:var(--ui-soft)}.slot-options button{width:100%;display:flex;justify-content:space-between;align-items:center;min-height:44px;font-size:26rpx;color:#626e80}.slot-options .chosen{color:var(--ui-accent)}
.checkout-error{display:block;margin:18rpx 32rpx;color:#b83532;font-size:26rpx;line-height:1.6}.quote{padding:4rpx 32rpx 0}.checkout-item{display:flex;align-items:center;gap:20rpx;padding:22rpx 0;border-bottom:1rpx solid #f0f2f6}.item-image{width:116rpx;height:116rpx;border-radius:18rpx}.item-copy{flex:1;min-width:0}.item-copy text{display:block}.item-name{font-size:28rpx;font-weight:500;line-height:1.5;overflow-wrap:anywhere}.item-copy .supporting{margin-top:8rpx}.item-numbers{display:flex;flex-direction:column;align-items:flex-end;gap:8rpx;font-size:27rpx;flex-shrink:0;font-variant-numeric:tabular-nums}.costs{padding:18rpx 0 8rpx;color:var(--ui-muted);font-size:26rpx}.costs>view{display:flex;justify-content:space-between;gap:24rpx;padding:5rpx 0}
.checkout-footer{padding:16rpx 32rpx calc(env(safe-area-inset-bottom) + 20rpx);flex-shrink:0}.payable{display:flex;justify-content:space-between;align-items:baseline;margin:0 0 20rpx;font-size:30rpx}.amount{font-size:44rpx;font-weight:500;font-variant-numeric:tabular-nums}.checkout-submit{width:100%;min-height:92rpx;padding:18rpx 20rpx;border-radius:999rpx;background:var(--ui-accent);color:#fff;display:flex;align-items:center;justify-content:center;gap:16rpx;font-size:30rpx;line-height:1.5}.payment-note{display:block;text-align:center;margin-top:12rpx;font-size:24rpx;color:var(--ui-muted)}button[disabled]{opacity:.45}
/* #ifdef H5 */
.checkout-panel{max-width:480px;margin:0 auto}
/* #endif */
</style>

<style scoped>
.address-row[disabled]{opacity:1}
</style>

<style scoped>
.checkout-mask.is-embedded{position:relative;inset:auto;z-index:auto;background:transparent;display:flex;flex:1;min-height:0;width:100%;overflow:hidden}.is-embedded .checkout-panel{height:100%;max-height:none;border-radius:0;flex:1;min-height:0}.is-embedded .checkout-body{height:0;max-height:none;flex:1;min-height:0}.is-embedded .checkout-footer{background:#fff;border-top:1px solid #eee}
</style>

<style scoped>
.checkout-panel,.is-embedded .checkout-panel{background:var(--ui-canvas-gradient)}.delivery-row{background:var(--ui-bubble);border:1px solid white;box-shadow:inset 0 1px 1px white,0 3px 16px rgba(59,43,79,.025);border-radius:22px}.review-caption{display:block;font-size:13px;color:var(--ui-muted);margin:22px 0 3px}.quote{margin:0 16px;padding:0 16px 12px;border-radius:24px;background:rgba(255,255,255,.8);border:1px solid #fff}.checkout-item{border-color:#f0ebf5}.item-image{width:56px;height:56px;border-radius:16px}.item-name{font-size:15px}.checkout-submit{background:var(--ui-accent);box-shadow:none;font-weight:500}.is-embedded .checkout-footer{background:rgba(255,255,255,.94);border-top:1px solid #fff}.repricing-note{display:block;font-size:12px;line-height:1.7;color:var(--ui-muted);padding:14px 0}.amount{font-weight:600}.payment-note{font-size:11px}.slot-options{border:1px solid #fff;border-radius:20px;background:#f3eef9}
</style>

<style scoped>
.delivery-row{width:calc(100% - 32px);margin:12px 16px 0;padding:14px;gap:12px;min-height:52px;font-size:14px;line-height:1.6}.address-row{padding:14px}.address-person{font-size:14px;line-height:1.6}.supporting{font-size:12px;line-height:1.6}.address-row .supporting{margin-top:4px}.slot-value{font-size:14px;overflow-wrap:anywhere}.quote{margin:14px 16px 0;padding:0 14px 12px}.review-caption{margin:16px 0 0;font-size:13px;line-height:1.6}.checkout-item{align-items:flex-start;gap:12px;padding:16px 0;min-height:88px}.item-image{display:block;flex:0 0 56px;min-width:56px;width:56px;height:56px;overflow:hidden;border-radius:14px}.item-copy{flex:1;min-width:0;width:0}.item-name{font-size:14px;line-height:1.6;word-break:break-all;overflow-wrap:anywhere}.item-copy .supporting{margin-top:5px;overflow-wrap:anywhere}.item-numbers{flex:0 0 auto;min-width:52px;gap:5px;font-size:14px;line-height:1.6;text-align:right}.item-numbers .supporting{font-size:12px}.checkout-footer{padding:14px 16px calc(env(safe-area-inset-bottom) + 16px)}.checkout-submit{min-height:44px;font-size:14px;line-height:1.6}.payment-note{margin-top:8px;line-height:1.6}
</style>
