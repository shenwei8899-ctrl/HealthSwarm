<script setup>
import FoodImageSlot from './FoodImageSlot.vue'
import MealPurchaseSheet from './MealPurchaseSheet.vue'
import MealPurchasePanel from './MealPurchasePanel.vue'
import { ref, computed, onMounted, onUnmounted } from 'vue'
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
const phase=ref('prepare'),quotedProducts=ref([])
const sourceUnavailable=ref(false)
const retryLabel=computed(()=>phase.value==='delivery'?'重新获取配送信息':phase.value==='quote'?'重新核价':'重新准备商品')
const products=computed(()=>quotedProducts.value.length?quotedProducts.value:publication.value?.items?.length?publication.value.items.map(item=>({
  id:String(item.sku_id),name:item.product_snapshot?.product_name||offer.value?.name,
  imageUrl:item.product_snapshot?.image_url||offer.value?.image_url,packLabel:item.product_snapshot?.sku_name||offer.value?.spec,
  quantity:Number(item.quantity),priceCents:packagePrice(item.unit_price_cent)===null?null:Number(item.unit_price_cent),
})):offer.value?[{
  id:String(offer.value.sku_id||props.route.offer),name:offer.value.name,imageUrl:offer.value.image_url,
  packLabel:offer.value.spec,quantity:1,priceCents:phase.value==='quote'?NaN:packagePrice(offer.value.price_cent)===null?null:Number(offer.value.price_cent),
}]:[])
const picked=computed(()=>products.value.map(item=>item.id))
const canSubmit=computed(()=>!!(offer.value?.available&&address.value&&slots.value.some(item=>String(item.id)===String(slotId.value))
  &&quote.value?.checkout_token&&Number.isFinite(Date.parse(quote.value.expires_at))&&Date.parse(quote.value.expires_at)>Date.now()
  &&['goods_amount_cent','shipping_fee_cent','payable_amount_cent'].every(key=>Number.isSafeInteger(quote.value[key])&&quote.value[key]>=0)
  &&!busy.value&&!error.value&&!pending.value&&!orderSn.value))
const money=value=>packagePrice(value)??'待核对'
let alive=true,owner=storageContext(),preferredAddressId=''
function current(scope){return alive&&scope===storageContext()}
function reset(){preferredAddressId='';offer.value=null;publication.value=null;address.value=null;slots.value=[];slotId.value=0;quote.value=null;quotedProducts.value=[];orderSn.value='';pending.value=false;checkoutOpen.value=false;sourceUnavailable.value=false}
function returnToChat(){if(!busy.value)uni.navigateBack({fail:()=>uni.reLaunch({url:'/pages/index/index'})})}
async function load(){
  if(owner!==storageContext()){owner=storageContext();reset();busy.value=false}
  if(busy.value)return
  const scope=storageContext();busy.value=true;error.value='';quote.value=null;sourceUnavailable.value=false
  try{
    const {data}=await request({path:'/api/health/v1/conversation-purchases/'+encodeURIComponent(props.route.conversation)})
    if(!current(scope))return
    if(data?.request_id&&data.request_id!==props.route.conversation)throw Object.assign(new Error('食材包来源无法核对，请返回对话重新咨询。'),{code:'OFFER_UNAVAILABLE'})
    if(!Array.isArray(data?.offers))throw new Error('食材包读取失败，请重试。')
    offer.value=data.offers.find(item=>item.offer_token===props.route.offer)||null
    if(!offer.value)throw Object.assign(new Error('这份推荐已失效，商品或健康档案可能已变化，请返回对话重新咨询。'),{code:'OFFER_UNAVAILABLE'})
    pending.value=!!commerce.pendingOrder()
  }catch(e){if(current(scope)){
    if([401,403,404,409,410,'SESSION_CHANGED','OFFER_UNAVAILABLE'].includes(e.code)){reset();sourceUnavailable.value=true}
    error.value=e.message
  }}
  finally{if(current(scope))busy.value=false}
  if(current(scope)&&checkoutOpen.value&&offer.value&&!error.value)await checkout()
}
async function delivery(scope){
  phase.value='delivery';slots.value=[]
  const addresses=await commerce.addresses();if(!current(scope))return
  const selected=resolveCheckoutAddress(addresses,preferredAddressId||address.value?.id)
  address.value=selected;quote.value=null
  if(!selected){slotId.value=0;return}
  const result=await commerce.slots(selected.id);if(!current(scope))return
  slots.value=result.supported===false?[]:(result.items||[]).filter(item=>item.available)
  if(!slots.value.some(item=>String(item.id)===String(slotId.value)))slotId.value=slots.value[0]?.id||0
  if(result.supported===false)error.value=result.message||'当前地址暂不支持配送，请更换地址。'
  else if(!slots.value.length)error.value='当前地址暂无可用配送时段，请更换地址或稍后重试。'
}
async function checkout(){
  if(busy.value||!offer.value?.available||orderSn.value)return
  const scope=storageContext();busy.value=true;error.value='';quote.value=null;checkoutOpen.value=true;phase.value='prepare'
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
    phase.value='quote'
    const result=await commerce.quoteRecommendation(publication.value.package_sn,publication.value.package_version,address.value.id,slotId.value)
    if(!current(scope))return
    if(!result?.checkout_token||!Number.isFinite(Date.parse(result.expires_at))||Date.parse(result.expires_at)<=Date.now()
      ||!['goods_amount_cent','shipping_fee_cent','payable_amount_cent'].every(key=>Number.isSafeInteger(result[key])&&result[key]>=0)
      ||!Array.isArray(result.items)||!result.items.length)throw new Error('报价信息不完整，请重新核价。')
    quotedProducts.value=result.items.map(item=>({id:String(item.sku_id),name:item.snapshot?.product_name||offer.value.name,
      imageUrl:item.snapshot?.image_url||offer.value.image_url,packLabel:item.snapshot?.sku_name||offer.value.spec,
      quantity:item.quantity,priceCents:Number.isSafeInteger(item.line_amount_cent)&&item.quantity>0?item.line_amount_cent/item.quantity:null}))
    quote.value=result
  }catch(e){if(current(scope)){
    error.value=e.code==='INVALID_RESPONSE'?(phase.value==='delivery'?'配送信息读取失败，请重试或更换地址。':phase.value==='quote'?'商品价格与配送费读取失败，请重新核价。':'商品准备失败，请重新读取。'):e.message
    if([401,403,404,409,410,'SESSION_CHANGED'].includes(e.code)){reset();sourceUnavailable.value=true}
  }}
  finally{if(current(scope))busy.value=false}
}
async function submit(recover=false){
  if(busy.value||orderSn.value)return
  if(!recover&&!canSubmit.value){quote.value=null;phase.value='quote';error.value='报价已失效或尚未就绪，请重新核价。';return}
  const scope=storageContext();busy.value=true;error.value=''
  try{
    if(!recover&&(!quote.value?.checkout_token||!Number.isFinite(Date.parse(quote.value.expires_at))||Date.parse(quote.value.expires_at)<=Date.now())){quote.value=null;throw new Error('报价已失效，请重新核对。')}
    const result=recover?await commerce.retryOrder():await commerce.createOrder(quote.value.checkout_token)
    if(!current(scope))return
    orderSn.value=result.order_sn;quote.value=null;pending.value=false;checkoutOpen.value=false
    uni.navigateTo({url:'/pages/orders/detail?id='+encodeURIComponent(result.order_sn)})
  }catch(e){if(current(scope)){pending.value=!!commerce.pendingOrder();error.value=e.message}}
  finally{if(current(scope))busy.value=false}
}
async function selectSlot(id){if(busy.value||String(slotId.value)===String(id))return;slotId.value=id;quote.value=null;await checkout()}
function chooseAddress(){ if(busy.value)return; quote.value=null;openAddressPicker({selectedId:address.value?.id,onSelected:id=>{preferredAddressId=id;quote.value=null}}) }
function closeCheckout(){if(!busy.value){checkoutOpen.value=false;quote.value=null}}
onMounted(load);onShow(load);onUnmounted(()=>alive=false)

</script>
<template>
 <view class="screen package-purchase"><AppNavBar title="商品详情"><template #left><button class="icon-button" aria-label="返回" @click="uni.navigateBack()">‹</button></template></AppNavBar>
  <text v-if="busy&&!offer" class="package-status">正在核对商品…</text><view v-if="error&&!checkoutOpen" class="package-status" role="alert"><text>{{error}}</text><button v-if="sourceUnavailable" :disabled="busy" @click="returnToChat">返回对话重新咨询</button><button v-else :disabled="busy" @click="load">重新读取</button></view>
  <view v-if="offer" class="package-content"><FoodImageSlot :src="offer.image_url" :label="offer.name" :width="'100%'" :height="210" :radius="22" fallback-icon class="package-hero"/><view class="package-heading"><text class="package-kicker">本次咨询的商品候选</text><text class="display-title">{{offer.name}}</text><text class="package-meta">{{packageSpec(offer.spec)}} · 1 包</text><text class="package-intro">这款{{offer.name}}可供查看和选购。购买前请核对配料及个人饮食限制。</text></view><view class="ingredients"><text class="section-title">商品信息</text><view class="info-row"><text>规格</text><text>{{packageSpec(offer.spec)||'待核对'}}</text></view><view class="info-row"><text>包含食材</text><text>{{offer.ingredients?.length?offer.ingredients.join(' · '):'商城尚未提供完整配料信息'}}</text></view><text class="package-caution">商品资料不代表个人适用性；实际价格和库存以结算时核对结果为准。</text></view><view class="package-bottom"><view><text>参考价</text><text>{{packagePrice(offer.price_cent)===null?'待核对':'¥'+money(offer.price_cent)}}</text></view><button :disabled="busy||!offer.available||!!orderSn" @click="checkout">购买 <text>→</text></button></view></view>
  <MealPurchaseSheet :open="checkoutOpen" :busy="busy" page title="购买商品" @close="closeCheckout"><MealPurchasePanel fixed title="所选商品" :products="products" :picked="products.map(item=>item.id)" :address="address" :slots="slots" :slot-id="slotId" :quote="quote" :busy="busy" :ready="!!offer" :pending="pending" :error="error" :retry-label="retryLabel" :can-submit="canSubmit" @address="chooseAddress" @slot="selectSlot" @confirm="submit()" @recover="submit(true)" @retry="load"/></MealPurchaseSheet>
 </view>
</template>
<style scoped>
.package-purchase{--meal-surface:var(--ui-canvas-gradient);position:relative;min-height:100vh;background:var(--ui-canvas-gradient);padding-bottom:calc(env(safe-area-inset-bottom) + 145px);color:var(--ui-text)}.nav-spacer{width:80rpx}.package-content{padding:0 18px}.package-hero{display:block;margin:14px 0 22px;border:1px solid #fff;box-shadow:var(--ui-bubble-shadow)}.package-heading{padding:0 4px 20px}.package-kicker{display:block;font-size:12px;color:var(--ui-accent);margin-bottom:8px}.package-heading .display-title{display:block;font-size:24px;font-weight:600;line-height:1.4}.package-meta{display:block;margin-top:7px;font-size:13px;color:var(--ui-muted)}.package-intro{display:block;margin-top:17px;font-size:14px;line-height:1.7}.ingredients{padding:18px;border:1px solid var(--ui-bubble-line);border-radius:22px;background:var(--ui-bubble);box-shadow:var(--ui-bubble-shadow)}.ingredients .section-title{display:block;margin-bottom:12px;font-size:16px;font-weight:600}.info-row{display:flex;justify-content:space-between;gap:15px;padding:10px 0;border-top:1px solid var(--ui-line);font-size:13px;line-height:1.7}.info-row>text:first-child{color:var(--ui-muted);flex-shrink:0}.info-row>text:last-child{text-align:right;overflow-wrap:anywhere}.package-caution{display:block;margin-top:12px;font-size:12px;color:var(--ui-muted);line-height:1.6}.package-bottom{position:fixed;z-index:10;bottom:0;left:0;right:0;display:flex;align-items:center;justify-content:space-between;gap:20px;padding:14px 20px calc(env(safe-area-inset-bottom) + 14px);border-top:1px solid var(--ui-bubble-line);background:rgba(255,255,255,.94);box-sizing:border-box}.package-bottom>view>text{display:block}.package-bottom>view>text:first-child{font-size:12px;color:var(--ui-muted)}.package-bottom>view>text:last-child{font-size:22px;font-weight:600}.package-bottom>button{display:flex;align-items:center;justify-content:center;gap:9px;min-width:132px;min-height:48px;background:var(--ui-accent);color:#fff;border-radius:99px;padding:10px 20px;font-size:15px;font-weight:600}.package-status{display:block;margin:20px 18px;font-size:14px;line-height:1.7}.package-status button{min-height:44px;color:var(--ui-accent)}button[disabled]{opacity:.45}
/* #ifdef H5 */
.package-bottom{max-width:480px;margin:0 auto}
/* #endif */
</style>
