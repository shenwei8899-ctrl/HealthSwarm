<script setup>
import FoodImageSlot from './FoodImageSlot.vue'
import MealPurchaseSheet from './MealPurchaseSheet.vue'
import MealPurchasePanel from './MealPurchasePanel.vue'
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import { request } from '../services/request.js'
import { commerce } from '../services/commerce.js'
import { openAddressPicker } from '../services/address-navigation.js'
import { resolveCheckoutAddress } from '../services/address-model.js'
import { storageContext } from '../services/storage.js'
import { packagePrice, packageSpec } from '../utils/package-presentation.js'
const props=defineProps({route:Object})
const offer=ref(null),publication=ref(null),address=ref(null),slots=ref([]),slotId=ref(0)
const busy=ref(false),error=ref(''),checkoutOpen=ref(false),quote=ref(null),orderSn=ref(''),pending=ref(false)
const money=value=>packagePrice(value)??'待核对'
const quoteAmountsValid=computed(()=>['goods_amount_cent','shipping_fee_cent','payable_amount_cent'].every(key=>Number.isSafeInteger(quote.value?.[key])&&quote.value[key]>=0))
const products=computed(()=>offer.value?[{id:offer.value.sku_id,name:offer.value.name,imageUrl:offer.value.image_url,packLabel:packageSpec(offer.value.spec),priceCents:quoteAmountsValid.value?quote.value.goods_amount_cent:NaN,quantity:1}]:[])
const canSubmit=computed(()=>Boolean(offer.value?.available&&address.value&&slots.value.some(item=>String(item.id)===String(slotId.value))&&quote.value?.checkout_token&&quoteAmountsValid.value&&Number.isFinite(Date.parse(quote.value.expires_at))&&Date.parse(quote.value.expires_at)>Date.now()&&!busy.value&&!error.value&&!pending.value&&!orderSn.value))
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
    if(!offer.value.available){error.value='商品已变化或暂不可购买，请重新询问。';return}
    pending.value=!!commerce.pendingOrder()
    if(checkoutOpen.value&&!pending.value&&publication.value)await reprice(scope)
  }catch(e){if(current(scope)){if(!checkoutOpen.value)offer.value=null;error.value=e.message}}
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
async function reprice(scope){
  await delivery(scope);if(!current(scope)||!address.value||!slots.value.length||error.value)return
  const result=await commerce.quoteRecommendation(publication.value.package_sn,publication.value.package_version,address.value.id,slotId.value)
  if(current(scope))quote.value=result
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
    await reprice(scope)
  }catch(e){if(current(scope))error.value=e.message}
  finally{if(current(scope))busy.value=false}
}
async function submit(recover=false){
  if(busy.value||orderSn.value)return
  const scope=storageContext();busy.value=true;error.value=''
  try{
    if(!recover&&(!quote.value?.checkout_token||!quoteAmountsValid.value||!Number.isFinite(Date.parse(quote.value.expires_at))||Date.parse(quote.value.expires_at)<=Date.now())){quote.value=null;throw new Error('报价已失效，请重新核对。')}
    const result=recover?await commerce.retryOrder():await commerce.createOrder(quote.value.checkout_token)
    if(!current(scope))return
    orderSn.value=result.order_sn;quote.value=null;pending.value=false;checkoutOpen.value=false
    uni.navigateTo({url:'/pages/orders/detail?id='+encodeURIComponent(result.order_sn)})
  }catch(e){if(current(scope)){pending.value=!!commerce.pendingOrder();error.value=e.message}}
  finally{if(current(scope))busy.value=false}
}
function chooseAddress(){ if(busy.value)return; quote.value=null;openAddressPicker({selectedId:address.value?.id,onSelected:id=>{preferredAddressId=id;quote.value=null}}) }
function selectSlot(id){if(busy.value)return;slotId.value=id;quote.value=null;void checkout()}
onMounted(load);onShow(load);onUnmounted(()=>alive=false)

</script>
<template>
 <view class="screen package-purchase"><AppNavBar><view class="nav-row"><button class="icon-button" aria-label="返回" @click="uni.navigateBack()">‹</button><text class="nav-title">商品详情</text><view class="nav-spacer"/></view></AppNavBar>
  <text v-if="busy&&!offer" class="package-status">正在核对商品…</text><view v-if="error&&!checkoutOpen" class="package-status" role="alert"><text>{{error}}</text><button :disabled="busy" @click="load">重新读取</button></view>
  <view v-if="offer" class="package-content"><FoodImageSlot :src="offer.image_url" :label="offer.name" :width="'100%'" :height="210" :radius="22" fallback-icon class="package-hero"/><view class="package-heading"><text class="package-kicker">本次咨询的商品候选</text><text class="display-title">{{offer.name}}</text><text class="package-meta">{{packageSpec(offer.spec)}} · 1 包</text><text class="package-intro">这款{{offer.name}}可供查看和选购。购买前请核对配料及个人饮食限制。</text></view><view class="ingredients"><text class="section-title">商品信息</text><view class="info-row"><text>规格</text><text>{{packageSpec(offer.spec)||'待核对'}}</text></view><view class="info-row"><text>包含食材</text><text>{{offer.ingredients?.length?offer.ingredients.join(' · '):'商城尚未提供完整配料信息'}}</text></view><text class="package-caution">商品资料不代表个人适用性；实际价格和库存以结算时核对结果为准。</text></view><view class="package-bottom"><view><text>参考价</text><text>{{packagePrice(offer.price_cent)===null?'待核对':'¥'+money(offer.price_cent)}}</text></view><button :disabled="busy||!offer.available||!!orderSn" @click="checkout">购买 <text>→</text></button></view></view>
  <MealPurchaseSheet :open="checkoutOpen" :busy="busy" page title="购买商品" @close="checkoutOpen=false"><MealPurchasePanel fixed title="所选商品" :products="products" :picked="products.map(item=>item.id)" :address="address" :slots="slots" :slot-id="slotId" :quote="quote" :busy="busy" :ready="!!publication" :pending="pending" :error="error" :can-submit="canSubmit" @address="chooseAddress" @slot="selectSlot" @confirm="submit()" @recover="submit(true)" @retry="checkout"/></MealPurchaseSheet>
 </view>
</template>
<style scoped>
.package-purchase{--meal-surface:var(--ui-canvas-gradient);position:relative;min-height:100vh;background:var(--ui-canvas-gradient);padding-bottom:calc(env(safe-area-inset-bottom) + 145px);color:var(--ui-text)}.nav-spacer{width:80rpx}.package-content{padding:0 18px}.package-hero{display:block;margin:14px 0 22px;border:1px solid #fff;box-shadow:var(--ui-bubble-shadow)}.package-heading{padding:0 4px 20px}.package-kicker{display:block;font-size:12px;color:var(--ui-accent);margin-bottom:8px}.package-heading .display-title{display:block;font-size:24px;font-weight:600;line-height:1.4}.package-meta{display:block;margin-top:7px;font-size:13px;color:var(--ui-muted)}.package-intro{display:block;margin-top:17px;font-size:14px;line-height:1.7}.ingredients{padding:18px;border:1px solid var(--ui-bubble-line);border-radius:22px;background:var(--ui-bubble);box-shadow:var(--ui-bubble-shadow)}.ingredients .section-title{display:block;margin-bottom:12px;font-size:16px;font-weight:600}.info-row{display:flex;justify-content:space-between;gap:15px;padding:10px 0;border-top:1px solid var(--ui-line);font-size:13px;line-height:1.7}.info-row>text:first-child{color:var(--ui-muted);flex-shrink:0}.info-row>text:last-child{text-align:right;overflow-wrap:anywhere}.package-caution{display:block;margin-top:12px;font-size:12px;color:var(--ui-muted);line-height:1.6}.package-bottom{position:fixed;z-index:10;bottom:0;left:0;right:0;display:flex;align-items:center;justify-content:space-between;gap:20px;padding:14px 20px calc(env(safe-area-inset-bottom) + 14px);border-top:1px solid var(--ui-bubble-line);background:rgba(255,255,255,.94);box-sizing:border-box}.package-bottom>view>text{display:block}.package-bottom>view>text:first-child{font-size:12px;color:var(--ui-muted)}.package-bottom>view>text:last-child{font-size:22px;font-weight:600}.package-bottom>button{display:flex;align-items:center;justify-content:center;gap:9px;min-width:132px;min-height:48px;background:var(--ui-accent);color:#fff;border-radius:99px;padding:10px 20px;font-size:15px;font-weight:600}.package-status{display:block;margin:20px 18px;font-size:14px;line-height:1.7}.package-status button{min-height:44px;color:var(--ui-accent)}button[disabled]{opacity:.45}
/* #ifdef H5 */
.package-bottom{max-width:480px;margin:0 auto}
/* #endif */
</style>
