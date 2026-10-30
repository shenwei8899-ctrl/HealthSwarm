<script setup>
import FoodImageSlot from './FoodImageSlot.vue'
import PurchaseCheckoutSheet from './PurchaseCheckoutSheet.vue'
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { openAddressPicker } from '../services/address-navigation.js'
import { onShow } from '@dcloudio/uni-app'
import CommerceAccess from './CommerceAccess.vue'
import { commerce } from '../services/commerce.js'
import { useMealCommercePage } from '../services/meal-commerce-page.js'
import { commerceMealView } from '../services/meal-commerce-state.js'
import { request } from '../services/request.js'
import { getSession } from '../services/session.js'
import { scopedStorage, storageContext } from '../services/storage.js'

const props = defineProps({ meal: Object, route: Object, embedded: Boolean, reference: Object, managed: Boolean })
const emit=defineEmits(['checkout','ordered'])
const preview = ref(null), publication = ref(null), selected = ref([]), draftQuantities = ref({})
const writing=ref(false)
const busy = ref(false), error = ref(''), checkoutOpen = ref(false), loginOpen = ref(false)
let alive = true, initialized = false, ownerScope = storageContext()
const page = useMealCommercePage(() => ({
  enabled: Boolean(publication.value), meal: props.route.meal, date: props.route.date,
  packageSn: publication.value?.package_sn, packageVersion: publication.value?.package_version,
  members: props.meal.members || [],
}))
const state = page.state
const purchaseReady = computed(() => Boolean(preview.value?.available || preview.value?.confirmation_pending))
const referenceProducts = computed(() => (props.reference?.items || []).map(item => ({id:String(item.sku_id),name:item.product_name,packLabel:item.sku_name||'规格待核对',quantity:draftQuantities.value[String(item.sku_id)]??item.quantity,imageUrl:item.image_url||'',needLabel:'参考用量未核算',priceCents:null,availableQuantity:null})))
const products = computed(() => props.reference && !state.ready ? (preview.value?referenceProducts.value:[]) : state.ready ? page.plan.value.products : commerceMealView({
  items: (preview.value?.items || []).filter(item => item.sku?.sku_id),
  ingredient_requirements: preview.value?.ingredient_requirements || [],
  available: preview.value?.available,
}).products.map(item=>({...item,quantity:draftQuantities.value[item.id]??item.quantity})))
const picked = computed(() => state.ready ? state.selected : selected.value)
const total = computed(() => products.value.filter(item => picked.value.includes(item.id)).reduce((sum, item) => sum + item.priceCents * item.quantity, 0))
const totalKnown=computed(()=>!(props.reference?.needsMatching&&!state.ready)&&products.value.filter(item=>picked.value.includes(item.id)).every(item=>Number.isFinite(item.priceCents)))
const money = cents => (Number(cents || 0) / 100).toFixed(2)
const active = scope => alive && scope === storageContext()
function failure(e,scope){
  if(!alive||ownerScope!==scope)return
  if(scope!==storageContext()||[401,403,404,409,410].includes(Number(e.code))||e.code==='SESSION_CHANGED'){
    preview.value=null;publication.value=null;selected.value=[];draftQuantities.value={};checkoutOpen.value=false;loginOpen.value=false;initialized=false;page.reset()
  }
  error.value=e.message;busy.value=false
}
const path = () => '/api/family/' + encodeURIComponent(getSession().householdId) + '/daily-arrangements/' + props.route.date + (props.route.meal === 'daily' ? '' : '/meals/' + props.route.meal) + '/purchase'
const version = () => ({ arrangement_id: props.route.arrangement, version: Number(props.route.version), ...(props.route.daily_plan_version!=null?{daily_plan_version:Number(props.route.daily_plan_version)}:{}), ...(props.route.meal === 'daily' ? { meals: props.route.meals } : {}) })
const selectionKey = () => 'meal-purchase-selection:' + props.route.arrangement + ':' + props.route.meal + ':' + (props.route.meals || []).join(',')
function rememberSelection() { scopedStorage.setStorageSync(selectionKey(), { known: products.value.map(item => item.id), selected: [...picked.value], quantities: {...draftQuantities.value}, version: props.route.version, dailyPlanVersion: props.route.daily_plan_version }) }
function receipt(data) {
  if (data.arrangement_id !== props.route.arrangement || data.version !== Number(props.route.version)) throw new Error('本餐已更新，请返回今日安排重新读取。')
  if (!data.purchase || !Array.isArray(data.purchase.items)) throw new Error('本餐采购内容不完整，请重新读取。')
  return data.purchase
}
const returnKey = () => 'meal-checkout-address-return:' + [props.route.arrangement, props.route.version, props.route.date, props.route.meal, (props.route.meals || []).join(',')].join(':')
function chooseAddress() {
  if (busy.value || state.busy) return
  const key = returnKey(), scope = storageContext()
  page.invalidateQuote()
  scopedStorage.setStorageSync(key, { at: Date.now(), scope })
  openAddressPicker({ selectedId: state.address?.id, onSelected: id => { state.preferredAddressId = id; page.invalidateQuote() }, onCancel: () => { if (active(scope)) scopedStorage.setStorageSync(key, null) } })
}
async function resumeCheckout(scope) {
  if (!active(scope)) return
  const key = returnKey(), pending = scopedStorage.getStorageSync(key)
  if (!pending) return
  scopedStorage.setStorageSync(key, null)
  if (!preview.value?.available || error.value || pending.scope !== scope || !Number.isFinite(pending.at) || Date.now() - pending.at > 15 * 60 * 1000 || pending.at > Date.now()) return
  await checkout()
}
async function verifyReference() {
  const ref=props.reference
  if(!ref || ref.dailyPlanVersion==null)return
  const scope=storageContext()
  const {data}=await request({path:'/api/family/'+encodeURIComponent(getSession().householdId)+'/daily-meal-plans/'+props.route.date})
  if(!active(scope))throw new Error('账号或家庭已变化，请重新读取。')
  if(data.date!==props.route.date || data.version!==ref.dailyPlanVersion || !data.purchase_options?.some(o=>o.kind==='reference'&&o.id===ref.previewId&&ref.mealTypes.length>0&&new Set(ref.mealTypes).size===ref.mealTypes.length&&ref.mealTypes.every(t=>o.meal_types.includes(t))))throw new Error('参考餐单已更新，请关闭详情后重新核对。')
}
async function refresh() {
  if (ownerScope !== storageContext()) {
    ownerScope = storageContext(); preview.value = null; publication.value = null; selected.value = []; draftQuantities.value={}
    initialized = false; checkoutOpen.value = false; loginOpen.value = false; busy.value = false; page.reset()
  }
  if (busy.value) return
  const scope = storageContext(); busy.value = true; error.value = ''; page.invalidateQuote()
  try {
    const { data } = props.reference ? (await verifyReference(), {data:null}) : await request({ path: path() + '?arrangement_id=' + encodeURIComponent(props.route.arrangement) + '&version=' + Number(props.route.version) + (props.route.daily_plan_version!=null?'&daily_plan_version='+Number(props.route.daily_plan_version):'') + (props.route.meals || []).map(meal => '&meals=' + meal).join('') })
    if (!active(scope)) return
    preview.value = props.reference ? {available:referenceProducts.value.length>0||props.reference.needsMatching,items:[]} : receipt(data)
    if (!initialized) {
      const saved = scopedStorage.getStorageSync(selectionKey()); if(saved?.version===props.route.version&&saved?.dailyPlanVersion===props.route.daily_plan_version)draftQuantities.value=saved.quantities||{}
      selected.value = products.value.filter(item => !saved?.known?.includes(item.id) || saved.selected.includes(item.id)).map(item => item.id)
      initialized = true
    }
    if (publication.value && commerce.session()?.token) {
      const slotId = state.slotId, addressId = state.address?.id
      await page.load()
      if (active(scope) && addressId === state.address?.id && state.slots.some(slot => slot.id === slotId)) state.slotId = slotId
    }
  } catch (e) { if(active(scope))preview.value=null;failure(e,scope) }
  finally { if (active(scope)) busy.value = false }
  await resumeCheckout(scope)
}
function toggle(id) { if (busy.value || state.busy) return; if (state.ready) page.toggle(id); else selected.value = selected.value.includes(id) ? selected.value.filter(value => value !== id) : [...selected.value, id]; rememberSelection() }
async function checkout() {
  if (busy.value || state.busy) return
  const scope = storageContext(); busy.value = true; writing.value=true; error.value = ''; checkoutOpen.value = true
  try {
    try { await commerce.connect() }
    catch (e) { if (active(scope)) loginOpen.value = true; throw e }
    if (!active(scope)) return
    loginOpen.value = false
    await verifyReference()
    if (publication.value && state.ready) {
      await page.prepare()
      return
    }
    const previous = [...picked.value], previousIds = products.value.map(item => item.id)
    const ref=props.reference
    const { data } = await request(ref ? {path:ref.dailyPlanVersion!=null?'/api/family/'+encodeURIComponent(getSession().householdId)+'/daily-meal-plans/'+props.route.date+'/purchase':'/api/health/v1/reference-meal-plans/'+encodeURIComponent(ref.previewId)+'/purchase',method:'POST',data:ref.dailyPlanVersion!=null?{preview_id:ref.previewId,version:ref.dailyPlanVersion,meal_types:ref.mealTypes}:undefined,timeout:30000} : { path: path(), method: 'POST', data: version(), timeout: 30000 })
    if (!active(scope)) return
    if(props.reference && (data.preview_id!==props.reference.previewId||!data.package?.package_sn))throw new Error('采购来源无法核对，请重试。')
    publication.value = props.reference ? data.package : receipt(data)
    await page.load()
    if (!active(scope) || !state.ready || state.error) return
    if(props.reference && state.menu?.scope!=='daily_reference')throw new Error('参考采购来源已变化，请重新核对。')
    await verifyReference()
    state.selected = page.plan.value.products.filter(item => previous.includes(item.id) || !previousIds.includes(item.id)).map(item => item.id)
    const quantityChanges=page.plan.value.products.filter(item=>draftQuantities.value[item.id]!=null)
    if(quantityChanges.some(item=>draftQuantities.value[item.id]>item.availableQuantity))throw new Error('库存已有变化，请返回食材列表重新确认包装数量。')
    for(const item of quantityChanges)page.quantity(item.id,draftQuantities.value[item.id])
    rememberSelection()
    await page.prepare()
  } catch (e) { failure(e,scope) }
  finally { writing.value=false; if (active(scope)) busy.value = false }
}
async function submit() {
  if(writing.value)return
  writing.value=true
  try{await verifyReference();await page.submit();if(alive&&state.orderSn){if(props.managed)emit('ordered',state.orderSn);else uni.navigateTo({url:'/pages/orders/detail?id='+encodeURIComponent(state.orderSn)})}}
  catch(e){error.value=e.message;page.invalidateQuote()}
  finally{writing.value=false}
}
async function recover() {
  if(writing.value)return
  writing.value=true
  try{await page.recover();if(alive&&state.orderSn){if(props.managed)emit('ordered',state.orderSn);else uni.navigateTo({url:'/pages/orders/detail?id='+encodeURIComponent(state.orderSn)})}}
  finally{writing.value=false}
}

function changeQuantity(item,delta){if(busy.value||state.busy)return;const value=item.quantity+delta;if(value<1||Number.isFinite(item.availableQuantity)&&value>item.availableQuantity)return;if(state.ready)page.quantity(item.id,value);draftQuantities.value={...draftQuantities.value,[item.id]:value};rememberSelection()}
async function selectSlot(id){if(busy.value||state.busy||String(state.slotId)===String(id))return;state.slotId=id;page.invalidateQuote();await checkout()}

watch(checkoutOpen,value=>emit('checkout',value))
defineExpose({refresh,closeCheckout:()=>{if(!writing.value)checkoutOpen.value=false},isBusy:computed(()=>writing.value)})
onMounted(refresh)
onShow(()=>{if(!props.embedded)void refresh()})
onUnmounted(() => { alive = false; page.dispose() })

</script>

<template>
 <view class="meal-purchase" :class="{'is-embedded':embedded}">
  <scroll-view v-show="!embedded||!checkoutOpen" :scroll-y="embedded" :show-scrollbar="false" class="purchase-scroll">
  <view class="section-head"><text class="section-title">{{route.meal==='daily'&&route.meals?.length>1?'所选餐次食材汇总':'本餐所需食材'}}</text><text>家中已有可取消</text></view>
  <text v-if="reference?.needsMatching&&!state.ready" class="safe-note">将按本餐核对商品；进入结算后可调整包装数量。</text><text v-if="reference" class="safe-note">参考餐单用量未核算，请核对实际需要；未匹配的食材需自行准备。</text><text v-if="busy||state.busy" class="safe-note">正在核对商品与配送…</text>
  <view v-if="error||state.error" class="card status" role="alert"><text>{{error||state.error}}</text><button class="secondary-button" :disabled="busy||state.busy" @click="refresh">重新核对本餐食材</button></view>
  <text v-if="preview&&!preview.available" class="inline-error">{{preview.message||'当前食材暂不可采购，请重新核对。'}}</text><view v-if="reference?.gaps?.length" class="purchase-gaps"><text>这些食材需要自行准备</text><text v-for="(gap,i) in reference.gaps" :key="i">{{gap.ingredient}}：{{gap.detail}}</text></view>
  <view class="products"><view v-for="item in products" :key="item.id" class="product"><button class="product-select" :disabled="busy||state.busy" :aria-pressed="picked.includes(item.id)" :aria-label="(picked.includes(item.id)?'取消选择':'选择')+item.name" @click="toggle(item.id)"><view class="check" :class="{selected:picked.includes(item.id)}">{{picked.includes(item.id)?'✓':''}}</view></button><FoodImageSlot :src="item.imageUrl" :label="item.name" class="product-image"/><view class="product-copy"><text class="product-name">{{item.name}}</text><text>{{item.needLabel}}</text><text>{{item.packLabel}}</text><view class="quantity-control"><button :aria-label="'减少'+item.name+'数量'" :disabled="busy||state.busy||item.quantity<=1" @click="changeQuantity(item,-1)">−</button><text>{{item.quantity}} 包</text><button :aria-label="'增加'+item.name+'数量'" :disabled="busy||state.busy||(Number.isFinite(item.availableQuantity)&&item.quantity>=item.availableQuantity)" @click="changeQuantity(item,1)">＋</button></view><text v-if="Number.isFinite(item.availableQuantity)&&item.availableQuantity<item.quantity" class="stock-alert">库存不足</text></view><text class="product-price">{{Number.isFinite(item.priceCents)?'¥'+money(item.priceCents*item.quantity):'待核价'}}</text></view></view>
  </scroll-view>
  <view v-show="!embedded||!checkoutOpen" class="meal-bottom-bar"><view class="selection-summary"><text>{{route.meal==='daily'?(route.meals||[]).map(m=>({breakfast:'早餐',lunch:'午餐',dinner:'晚餐'}[m])).join('、')+' · 商品小计':'商品小计 · '+picked.length+' 项'}}</text><text class="amount">{{totalKnown?'¥'+money(total):'价格待核对'}}</text></view><button class="checkout-button" :disabled="busy||state.busy||!purchaseReady||(!picked.length&&!reference?.needsMatching)||!!error" @click="checkout">{{preview?.confirmation_pending?'确认上次采购结果':'去结算'}}<text v-if="!preview?.confirmation_pending">→</text></button></view>
  <PurchaseCheckoutSheet :embedded="embedded" :open="checkoutOpen" :title="route.meal==='daily'&&route.meals?.length>1?'确认采购订单':'确认本餐订单'" :address="state.address" :slots="state.slots" :slot-id="state.slotId" :products="products.filter(p=>picked.includes(p.id))" :quote="state.quote" :busy="busy||state.busy" :error="error||state.error||state.checkoutError||state.deliveryMessage" :pending="!!(state.pending||state.orderSn)" :access-required="loginOpen" @close="checkoutOpen=false" @address="chooseAddress" @slot="selectSlot" @confirm="submit" @recover="recover" @quote="checkout"><template #access><CommerceAccess entry @ready="checkout"/></template></PurchaseCheckoutSheet>
 </view>
</template>
<style scoped>
.section-head{display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;gap:10rpx;margin:30rpx 0 14rpx}.section-title{font-size:29rpx;font-weight:500}.section-head>text:last-child{font-size:23rpx;color:var(--ui-muted)}.products{border:1rpx solid #e9edf3;border-radius:26rpx;background:#fff;padding:0 18rpx}.product{display:flex;align-items:center;gap:16rpx;padding:18rpx 0;border-bottom:1rpx solid #eff2f6;width:100%;text-align:left;box-sizing:border-box}.product:last-child{border:0}.check{display:flex;align-items:center;justify-content:center;width:34rpx;height:34rpx;border:2rpx solid #bcc4d3;border-radius:8rpx;flex-shrink:0;font-size:26rpx;color:#fff}.check.selected{background:var(--ui-accent);border-color:var(--ui-accent)}.product-image{width:108rpx;height:116rpx;border-radius:18rpx}.product-copy{flex:1;min-width:0}.product-copy text{display:block;color:var(--ui-muted);font-size:24rpx;line-height:1.6}.product-copy .product-name{color:#252a34;font-size:28rpx;font-weight:500;line-height:1.45;margin-bottom:6rpx;overflow-wrap:anywhere}.product-price{align-self:flex-end;padding-bottom:4rpx;flex-shrink:0;font-size:27rpx;font-weight:500;white-space:nowrap;font-variant-numeric:tabular-nums}.product-copy .stock-alert{color:#b83532}.meal-bottom-bar{position:fixed;z-index:10;left:0;right:0;bottom:0;padding:18rpx 32rpx calc(env(safe-area-inset-bottom) + 18rpx);display:flex;align-items:center;justify-content:space-between;gap:20rpx;background:#fff;border-top:1rpx solid #eceff4;box-sizing:border-box}.selection-summary{display:flex;align-items:baseline;justify-content:space-between;gap:16rpx;flex:1;min-width:0;font-size:24rpx}.selection-summary>text:first-child{line-height:1.5;max-width:50%;color:#465064}.amount{font-size:40rpx;font-weight:500;font-variant-numeric:tabular-nums;color:#20242c;white-space:nowrap}.checkout-button{display:flex;align-items:center;justify-content:center;gap:16rpx;background:var(--ui-accent);border-radius:999rpx;color:#fff;min-height:92rpx;padding:18rpx 24rpx;font-size:28rpx;line-height:1.5;max-width:46%;box-sizing:border-box}.status{padding:24rpx;font-size:27rpx;line-height:1.6}.status button{margin-top:16rpx}button[disabled]{opacity:.45}
@media(max-width:350px){.product{gap:12rpx}.product-image{width:86rpx;height:100rpx}.product-price{font-size:26rpx}.selection-summary{flex-direction:column;gap:0}.selection-summary>text:first-child{max-width:100%}.amount{font-size:38rpx}}
/* #ifdef H5 */
.meal-bottom-bar{max-width:480px;margin:0 auto}
/* #endif */
</style>

<style scoped>
@media(max-width:350px){.product-copy text,.section-head>text:last-child,.selection-summary{font-size:12px}.section-title,.product-copy .product-name{font-size:14px}}
</style>

<style scoped>
.is-embedded.meal-purchase{height:100%;display:flex;flex-direction:column;min-height:0;overflow:hidden}.is-embedded .purchase-scroll{height:0;flex:1;min-height:0;box-sizing:border-box;padding:0 20px 20px}.is-embedded .meal-bottom-bar{position:relative;inset:auto;flex-shrink:0;width:100%;padding:14px 20px calc(env(safe-area-inset-bottom) + 14px);margin:0;max-width:none}.is-embedded .selection-summary .amount{font-size:22px}.purchase-scroll{height:auto}
</style>

<style scoped>
.meal-purchase{color:var(--ui-text)}.products{border:1px solid #fff;border-radius:24px;background:var(--ui-bubble);box-shadow:inset 0 1px 1px #fff,0 4px 18px rgba(62,47,82,.035);padding:0 12px}.product{gap:9px;background:transparent}.product-select{display:flex;justify-content:center;align-items:center;width:30px;min-width:30px;min-height:44px;margin:0;padding:0;background:transparent}.product-select:after{border:0}.product-image{width:52px;height:60px;border-radius:15px}.product-price{font-size:14px;align-self:flex-start;margin-top:8px}.product-copy .product-name{font-size:15px;font-weight:500}.quantity-control{display:flex;align-items:center;gap:9px;margin-top:7px}.quantity-control button{display:flex;align-items:center;justify-content:center;margin:0;padding:0;min-width:32px;width:32px;min-height:36px;border-radius:99px;background:#f1ecf7;font-size:15px;color:var(--ui-accent)}.quantity-control button:after{border:0}.quantity-control>text{font-size:12px;color:var(--ui-text)}.section-head{margin-top:18px}.safe-note{display:block;margin:8px 0;font-size:12px;line-height:1.7;color:var(--ui-muted)}.meal-bottom-bar{background:linear-gradient(150deg,#fff,#faf8fd);border-top:1px solid white}.checkout-button{border-radius:99px;background:var(--ui-accent);box-shadow:none}.is-embedded .purchase-scroll{padding:0 18px 20px}.product-copy text{font-size:12px}.selection-summary>text:first-child{font-size:11px}.is-embedded .selection-summary .amount{font-size:21px}
</style>

<style scoped>.purchase-gaps{padding:14px 16px;margin:12px 0;border:1px solid #eee4d6;border-radius:20px;background:#fbf8f1;color:#9a805c;font-size:12px;line-height:1.8}.purchase-gaps text{display:block}.purchase-gaps text:first-child{font-weight:500;margin-bottom:4px}</style>
