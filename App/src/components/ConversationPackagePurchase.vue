<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import { request } from '../services/request.js'
import { commerce } from '../services/commerce.js'
import { storageContext } from '../services/storage.js'
const props=defineProps({route:Object})
const offer=ref(null),publication=ref(null),address=ref(null),slots=ref([]),slotId=ref(0)
const busy=ref(false),error=ref(''),checkoutOpen=ref(false),quote=ref(null),orderSn=ref(''),pending=ref(false)
const money=value=>(Number(value||0)/100).toFixed(2)
let alive=true,owner=storageContext()
function current(scope){return alive&&scope===storageContext()}
function reset(){offer.value=null;publication.value=null;address.value=null;slots.value=[];slotId.value=0;quote.value=null;orderSn.value='';pending.value=false;checkoutOpen.value=false}
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
  const selected=addresses.find(item=>item.isDefault)||null
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
onMounted(load);onShow(load);onUnmounted(()=>alive=false)
</script>
<template><view class="screen package-purchase"><AppNavBar><view class="nav-row"><button @click="uni.navigateBack()">‹</button><text class="nav-title">食材包选购</text><view/></view></AppNavBar><text v-if="busy" class="safe-note">正在核对食材包…</text><view v-if="error" class="card status" role="alert"><text>{{error}}</text><button :disabled="busy" @click="load">重新读取</button></view><view v-if="offer" class="card details"><image v-if="offer.image_url" :src="offer.image_url" mode="aspectFill"/><text class="display-title">{{offer.name}}</text><text>{{offer.spec}} · 1 包</text><text>配料：{{offer.ingredients?.join('、')}}</text><text>{{offer.note}}</text><text>商品参考价 ¥{{money(offer.price_cent)}}</text><button class="primary-button" :disabled="busy||!offer.available||!!orderSn" @click="checkout">去结算</button></view><view v-if="checkoutOpen" class="card details"><text class="section-title">核对本次购买</text><button :disabled="busy" @click="uni.navigateTo({url:'/pages/address/index'})">{{address?address.name+' · '+address.phone+' '+address.detail:'选择配送地址'}}</button><button v-for="slot in slots" :key="slot.id" :disabled="busy" @click="slotId=slot.id;quote=null">{{String(slotId)===String(slot.id)?'✓ ':''}}{{slot.name||slot.start_time+'—'+slot.end_time}}</button><text v-if="quote">商品 ¥{{money(quote.goods_amount_cent)}} · 配送 ¥{{money(quote.shipping_fee_cent)}} · 优惠 ¥{{money(quote.discount_amount_cent)}} · 应付 ¥{{money(quote.payable_amount_cent)}}</text><button v-if="pending" class="primary-button" :disabled="busy" @click="submit(true)">确认原订单结果</button><button v-else-if="quote" class="primary-button" :disabled="busy" @click="submit()">确认下单 ¥{{money(quote.payable_amount_cent)}}</button><button v-else class="primary-button" :disabled="busy||!offer?.available" @click="checkout">核对商品、配送和价格</button><text>下单后进入订单详情支付，以服务端结果为准。</text></view></view></template>
<style scoped>.details,.status{margin:28rpx 0;padding:28rpx;display:flex;flex-direction:column;gap:24rpx;font-size:27rpx;line-height:1.7}.details image{width:100%;height:350rpx;border-radius:24rpx}.details .display-title{font-size:42rpx}</style>
