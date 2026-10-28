<script setup>
import FoodImageSlot from './FoodImageSlot.vue'
import PurchaseCheckoutSheet from './PurchaseCheckoutSheet.vue'
import { ref, onMounted, onUnmounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import { request } from '../services/request.js'
import { commerce } from '../services/commerce.js'
import { openAddressPicker } from '../services/address-navigation.js'
import { resolveCheckoutAddress } from '../services/address-model.js'
import { storageContext } from '../services/storage.js'
const props=defineProps({route:Object})
const offer=ref(null),publication=ref(null),address=ref(null),slots=ref([]),slotId=ref(0)
const busy=ref(false),error=ref(''),checkoutOpen=ref(false),quote=ref(null),orderSn=ref(''),pending=ref(false)
const money=value=>(Number(value||0)/100).toFixed(2)
let alive=true,owner=storageContext(),preferredAddressId=''
function current(scope){return alive&&scope===storageContext()}
function reset(){preferredAddressId='';offer.value=null;publication.value=null;address.value=null;slots.value=[];slotId.value=0;quote.value=null;orderSn.value='';pending.value=false;checkoutOpen.value=false}
async function load(){
  if(owner!==storageContext()){owner=storageContext();reset();busy.value=false}
  if(busy.value)return
  const scope=storageContext();busy.value=true;error.value='';quote.value=null
  try{
    const {data}=await request({path:'/api/health/v1/conversation-purchases/'+encodeURIComponent(props.route.conversation)})
    if(!current(scope))return
    offer.value=data.offers.find(item=>item.offer_token===props.route.offer)||null
    if(!offer.value)throw new Error('这份食材包不属于当前对话，请重新询问。')
    pending.value=!!commerce.pendingOrder()
    if(checkoutOpen.value)await delivery(scope)
  }catch(e){if(current(scope)){offer.value=null;error.value=e.message}}
  finally{if(current(scope))busy.value=false}
}
async function delivery(scope){
  const addresses=await commerce.addresses();if(!current(scope))return
  const selected=resolveCheckoutAddress(addresses,preferredAddressId||address.value?.id)
  address.value=selected;quote.value=null
  if(!selected){slots.value=[];error.value='请选择配送地址，再核对价格。';return}
  const result=await commerce.slots(selected.id);if(!current(scope))return
  slots.value=result.supported===false?[]:(result.items||[]).filter(item=>item.available)
  if(!slots.value.some(item=>String(item.id)===String(slotId.value)))slotId.value=slots.value[0]?.id||0
  if(result.supported===false||!slots.value.length)error.value=result.message||'当前地址暂不能配送。'
}
async function checkout(){
  if(busy.value||!offer.value?.available||orderSn.value)return
  const scope=storageContext();busy.value=true;error.value='';quote.value=null;checkoutOpen.value=true
  try{
    await commerce.connect();if(!current(scope))return
    pending.value=!!commerce.pendingOrder();if(pending.value)return
    if(!publication.value){
      const {data}=await request({path:'/api/health/v1/conversation-purchases/'+encodeURIComponent(props.route.conversation),method:'POST',data:{offer_token:props.route.offer},timeout:30000})
      if(!current(scope))return
      if(!data.package?.package_sn||!['available','confirmed'].includes(data.package.status))throw new Error('食材包库存尚未确认，请重试读取。')
      publication.value=data.package
    }
    await commerce.confirmRecommendation(publication.value.package_sn,publication.value.package_version)
    if(!current(scope))return
    await delivery(scope);if(!current(scope)||!address.value||!slots.value.length||error.value)return
    const result=await commerce.quoteRecommendation(publication.value.package_sn,publication.value.package_version,address.value.id,slotId.value)
    if(current(scope))quote.value=result
  }catch(e){if(current(scope))error.value=e.message}
  finally{if(current(scope))busy.value=false}
}
async function submit(recover=false){
  if(busy.value)return
  const scope=storageContext();busy.value=true;error.value=''
  try{
    if(!recover&&(!quote.value?.checkout_token||!Number.isFinite(Date.parse(quote.value.expires_at))||Date.parse(quote.value.expires_at)<=Date.now())){quote.value=null;throw new Error('报价已失效，请重新核对。')}
    const result=recover?await commerce.retryOrder():await commerce.createOrder(quote.value.checkout_token)
    if(!current(scope))return
    orderSn.value=result.order_sn;quote.value=null;pending.value=false
    uni.navigateTo({url:'/pages/orders/detail?id='+encodeURIComponent(result.order_sn)})
  }catch(e){if(current(scope)){pending.value=!!commerce.pendingOrder();error.value=e.message}}
  finally{if(current(scope))busy.value=false}
}
function chooseAddress(){ if(busy.value)return; quote.value=null;openAddressPicker({selectedId:address.value?.id,onSelected:id=>{preferredAddressId=id;quote.value=null}}) }
onMounted(load);onShow(load);onUnmounted(()=>alive=false)

</script>
<template>
 <view class="screen package-purchase"><AppNavBar><view class="nav-row"><button class="icon-button" aria-label="返回" @click="uni.navigateBack()">‹</button><text class="nav-title">食材包</text><view class="nav-spacer"/></view></AppNavBar>
  <text v-if="busy" class="safe-note">正在核对食材包…</text><view v-if="error" class="card status" role="alert"><text>{{error}}</text><button :disabled="busy" @click="load">重新读取</button></view>
  <view v-if="offer" class="package-content"><FoodImageSlot :src="offer.image_url" :label="offer.name" class="package-hero"/><view class="package-heading"><text class="display-title">{{offer.name}}</text><text class="package-meta">{{offer.spec}} · 1 包</text><text class="package-price"><text>¥</text>{{money(offer.price_cent)}}</text><text v-if="offer.note" class="package-meta">{{offer.note}}</text></view><view class="ingredients"><text class="section-title">包含食材</text><text>{{offer.ingredients?.join(' · ')}}</text></view><view class="package-bottom"><text>商品参考价 <text>¥{{money(offer.price_cent)}}</text></text><button :disabled="busy||!offer.available||!!orderSn" @click="checkout">去结算 <text>→</text></button></view></view>
  <PurchaseCheckoutSheet :open="checkoutOpen" :address="address" :slots="slots" :slot-id="slotId" :quote="quote" :busy="busy" :error="error" :pending="pending" @close="checkoutOpen=false" @address="chooseAddress" @slot="slotId=$event;quote=null" @confirm="submit()" @recover="submit(true)" @quote="checkout"/>
 </view>
</template>
<style scoped>
.package-purchase{background:#fafbfc;padding-bottom:calc(env(safe-area-inset-bottom) + 170rpx)}.nav-spacer{width:80rpx}.package-hero{width:100%;height:400rpx;border-radius:30rpx;margin:22rpx 0 32rpx}.package-heading{padding:0 8rpx 28rpx}.package-heading .display-title{font-size:42rpx;font-weight:500;line-height:1.4}.package-meta{display:block;margin-top:14rpx;font-size:27rpx;line-height:1.6;color:#65728c}.package-price{display:block;font-size:54rpx;font-weight:600;margin-top:26rpx;font-variant-numeric:tabular-nums}.package-price>text{font-size:30rpx;font-weight:400;margin-right:4rpx}.ingredients{padding:24rpx 8rpx;border-top:1rpx solid #e8edf3}.ingredients>text{display:block}.ingredients>text+text{font-size:28rpx;color:#7c899e;margin-top:16rpx;line-height:1.6}.package-bottom{position:fixed;z-index:10;bottom:0;left:0;right:0;display:flex;align-items:center;justify-content:space-between;gap:20rpx;padding:18rpx 32rpx calc(env(safe-area-inset-bottom) + 18rpx);border-top:1rpx solid #eceff4;background:#fff;box-sizing:border-box}.package-bottom>text{font-size:24rpx;color:#65728c}.package-bottom>text>text{display:block;color:#20242b;font-size:38rpx;font-weight:600}.package-bottom>button{display:flex;align-items:center;justify-content:center;gap:20rpx;min-height:92rpx;background:#25262a;color:#fff;border-radius:999rpx;padding:18rpx 38rpx;font-size:29rpx}.status{padding:24rpx;font-size:27rpx;line-height:1.6}.status button{min-height:44px;color:#0674ed}button[disabled]{opacity:.45}
/* #ifdef H5 */
.package-bottom{max-width:480px;margin:0 auto}
/* #endif */
</style>
