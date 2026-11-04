<script setup>
import { computed, ref } from 'vue'
import FoodImageSlot from './FoodImageSlot.vue'
const props = defineProps({ products: Array, picked: Array, address: Object, slots: Array, slotId: [String,Number], quote: Object,
  busy: Boolean, pricing: Boolean, ready: Boolean, pending: Boolean, error: String, accessRequired: Boolean, canSubmit: Boolean })
defineEmits(['address','slot','toggle','quantity','confirm','recover','retry','scroll'])
const timesOpen = ref(false)
const slot = computed(() => props.slots?.find(item => String(item.id) === String(props.slotId)))
const slotName = item => item?.name || [item?.date || item?.delivery_date, [item?.start_time,item?.end_time].filter(Boolean).join('—')].filter(Boolean).join(' ') || '选择送达时间'
const money = value => Number.isFinite(value) ? '¥'+(value/100).toFixed(2) : '—'
const total = computed(() => !props.ready ? '—' : props.picked?.length ? money(props.quote?.payable_amount_cent) : '¥0.00')
</script>
<template>
  <view class="mp-order">
    <scroll-view class="mp-order-scroll" scroll-y :show-scrollbar="false" @scroll="$emit('scroll',$event.detail.scrollTop)">
      <slot v-if="accessRequired" name="access"/>
      <template v-else>
        <view class="mp-delivery mp-surface">
          <button class="mp-address" :disabled="busy||!ready" @click="$emit('address')"><view><text class="mp-row-title">{{address?(address.name||address.receiver)+' · '+(address.phone||address.mobile):'添加配送地址'}}</text><text v-if="address" class="mp-support">{{address.region}} {{address.detail}}</text></view><text class="mp-chevron">›</text></button>
          <button class="mp-delivery-time" :disabled="busy||!slots?.length" @click="timesOpen=!timesOpen"><text>配送时间</text><text class="mp-time-value">{{slot?slotName(slot):ready?(address?'暂无可用时段':'添加地址后选择'):'正在读取…'}}</text><text class="mp-chevron">›</text></button>
          <view v-if="timesOpen&&slots?.length" class="mp-times"><button v-for="item in slots" :key="item.id" :class="{chosen:String(item.id)===String(slotId)}" :disabled="busy" @click="$emit('slot',item.id);timesOpen=false"><text>{{slotName(item)}}</text><text v-if="String(item.id)===String(slotId)">✓</text></button></view>
        </view>
        <view v-if="busy&&!ready" class="mp-loading" role="status">正在准备本餐商品与价格…</view>
        <view v-if="error" class="mp-error" role="alert"><text>{{error}}</text><button :disabled="busy" @click="$emit('retry')">重新核对</button></view>
        <template v-if="ready">
          <view class="mp-section-heading"><text>本餐食材</text><text>家中已有可取消</text></view>
          <view class="mp-products mp-surface">
            <view v-for="item in products" :key="item.id" class="mp-product">
              <button class="mp-select" :aria-pressed="picked.includes(item.id)" :aria-label="(picked.includes(item.id)?'取消选择':'选择')+item.name" :disabled="busy||pending" @click="$emit('toggle',item.id)"><view :class="{'is-selected':picked.includes(item.id)}">{{picked.includes(item.id)?'✓':''}}</view></button>
              <FoodImageSlot :src="item.imageUrl" :label="item.name" :width="52" :height="58" :radius="14" fallback-icon/>
              <view class="mp-product-copy"><text class="mp-product-name">{{item.name}}</text><text class="mp-support">{{item.packLabel}} · {{money(item.priceCents)}}/包</text><view class="mp-quantity"><button :aria-label="'减少'+item.name+'数量'" :disabled="busy||pending||item.quantity<=1" @click="$emit('quantity',item,-1)">−</button><text>{{item.quantity}}</text><button :aria-label="'增加'+item.name+'数量'" :disabled="busy||pending||item.quantity>=item.availableQuantity" @click="$emit('quantity',item,1)">＋</button></view></view>
              <text class="mp-product-price">{{money(item.priceCents*item.quantity)}}</text>
            </view>
          </view>
          <view class="mp-costs mp-surface"><view><text>商品金额</text><text>{{money(quote?.goods_amount_cent)}}</text></view><view><text>运费</text><text>{{money(quote?.shipping_fee_cent)}}</text></view><view v-if="quote?.discount_amount_cent>0"><text>优惠</text><text>−{{money(quote.discount_amount_cent)}}</text></view><view class="mp-payable"><text>应付总额</text><text>{{money(quote?.payable_amount_cent)}}</text></view></view>
        </template>
      </template>
      <view class="mp-scroll-space"/>
    </scroll-view>
    <view v-if="!accessRequired" class="mp-order-footer"><view class="mp-total"><text>合计</text><text>{{(busy||pricing)&&ready?'核算中…':total}}</text></view><button :disabled="busy||(!pending&&!canSubmit)" @click="pending?$emit('recover'):$emit('confirm')">{{pending?'确认原订单':busy?'正在核对…':'确认下单'}}</button></view>
  </view>
</template>
<style>
/* #ifdef MP-WEIXIN */
:host{display:flex;flex-direction:column;flex:1;height:100%;min-height:0}
/* #endif */
</style>
<style scoped>
.mp-order{display:flex;flex:1;flex-direction:column;height:100%;min-height:0;color:var(--ui-text)}.mp-order-scroll{height:0;flex:1;min-height:0;padding:0 18px;box-sizing:border-box}.mp-surface{border:1px solid var(--ui-bubble-line);border-radius:22px;background:var(--ui-bubble);box-shadow:var(--ui-bubble-shadow)}
.mp-delivery{padding:0 14px}.mp-address,.mp-delivery-time{display:flex;align-items:center;gap:10px;width:100%;min-height:56px;margin:0;padding:13px 0;background:transparent;text-align:left;font-size:14px}.mp-address>view{flex:1;min-width:0}.mp-row-title{display:block;font-size:15px;line-height:1.6;font-weight:600;overflow-wrap:anywhere}.mp-support{display:block;color:var(--ui-muted);font-size:12px;line-height:1.7;margin-top:3px}.mp-chevron{flex-shrink:0;color:var(--ui-muted);font-size:22px}.mp-delivery-time{border-top:1px solid var(--ui-line)}.mp-delivery-time>text:first-child{font-weight:600}.mp-time-value{flex:1;min-width:0;text-align:right;color:var(--ui-muted);font-size:12px;line-height:1.7}.mp-times{padding:0 0 10px}.mp-times>button{display:flex;align-items:center;justify-content:space-between;gap:8px;width:100%;min-height:44px;text-align:left;font-size:13px;color:var(--ui-muted)}.mp-times .chosen{color:var(--ui-accent)}
.mp-section-heading{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:21px 3px 10px;font-size:16px;font-weight:600}.mp-section-heading>text:last-child{font-size:12px;font-weight:400;color:var(--ui-muted)}.mp-products{padding:0 12px}.mp-product{display:flex;align-items:center;gap:9px;padding:16px 0}.mp-product+.mp-product{border-top:1px solid var(--ui-line)}.mp-select{display:flex;align-items:center;justify-content:center;flex-shrink:0;width:28px;min-height:44px;padding:0;margin:0}.mp-select>view{display:flex;align-items:center;justify-content:center;width:19px;height:19px;border:1px solid #bbc0cb;border-radius:7px;font-size:12px}.mp-select .is-selected{background:var(--ui-accent);border-color:var(--ui-accent);color:#fff}.mp-product-copy{flex:1;min-width:0}.mp-product-name{display:block;font-size:15px;line-height:1.5;font-weight:600;overflow-wrap:anywhere}.mp-product-price{align-self:flex-start;flex-shrink:0;margin-top:3px;font-size:14px;font-weight:600;font-variant-numeric:tabular-nums}.mp-quantity{display:flex;align-items:center;gap:10px;margin-top:5px;font-size:13px}.mp-quantity>button{display:flex;align-items:center;justify-content:center;width:32px;min-height:36px;margin:0;padding:0;border-radius:50%;background:var(--ui-accent-soft);font-size:17px}
.mp-costs{padding:12px 16px;margin-top:14px;font-size:13px;color:var(--ui-muted)}.mp-costs>view{display:flex;justify-content:space-between;gap:16px;padding:5px 0;font-variant-numeric:tabular-nums}.mp-costs .mp-payable{padding-top:10px;margin-top:5px;border-top:1px solid var(--ui-line);color:var(--ui-text);font-weight:600}.mp-scroll-space{height:18px}.mp-loading{padding:28px 12px;color:var(--ui-muted);font-size:13px;text-align:center}.mp-error{margin:14px 3px;color:#a63c35;font-size:13px;line-height:1.7}.mp-error>text{display:block}.mp-error>button{min-height:44px;text-align:left;font-size:13px;color:var(--ui-accent)}
.mp-order-footer{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-shrink:0;padding:13px 20px calc(env(safe-area-inset-bottom) + 13px);border-top:1px solid var(--ui-bubble-line);background:rgba(255,255,255,.94)}.mp-total{display:flex;flex-direction:column;gap:1px;min-width:0}.mp-total>text:first-child{font-size:12px;color:var(--ui-muted)}.mp-total>text:last-child{font-size:22px;line-height:1.4;font-weight:600;font-variant-numeric:tabular-nums}.mp-order-footer>button{display:flex;align-items:center;justify-content:center;min-width:132px;min-height:48px;margin:0;padding:10px 21px;border-radius:99px;background:var(--ui-accent);color:#fff;font-size:15px;font-weight:600}.mp-order button:after{border:0}.mp-order button[disabled]{opacity:.45}@media(max-width:350px){.mp-order-scroll{padding:0 12px}.mp-products{padding:0 8px}.mp-product{gap:6px}.mp-product-price{font-size:13px}.mp-order-footer{padding-left:16px;padding-right:16px}}
</style>
