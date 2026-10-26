<script setup>
import FoodImageSlot from './FoodImageSlot.vue'
import PurchaseCheckoutSheet from './PurchaseCheckoutSheet.vue'
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import CommerceAccess from './CommerceAccess.vue'
import { commerce } from '../services/commerce.js'
import { useMealCommercePage } from '../services/meal-commerce-page.js'
import { commerceMealView } from '../services/meal-commerce-state.js'
import { request } from '../services/request.js'
import { getSession } from '../services/session.js'
import { scopedStorage, storageContext } from '../services/storage.js'

const props = defineProps({ meal: Object, route: Object })
const preview = ref(null), publication = ref(null), selected = ref([])
const busy = ref(false), error = ref(''), checkoutOpen = ref(false), loginOpen = ref(false)
let alive = true, initialized = false, ownerScope = storageContext()
const page = useMealCommercePage(() => ({
  enabled: Boolean(publication.value), meal: props.route.meal, date: props.route.date,
  packageSn: publication.value?.package_sn, packageVersion: publication.value?.package_version,
  members: props.meal.members,
}))
const state = page.state
const purchaseReady = computed(() => Boolean(preview.value?.available || preview.value?.confirmation_pending))
const products = computed(() => state.ready ? page.plan.value.products : commerceMealView({
  items: (preview.value?.items || []).filter(item => item.sku?.sku_id),
  ingredient_requirements: preview.value?.ingredient_requirements || [],
  available: preview.value?.available,
}).products)
const picked = computed(() => state.ready ? state.selected : selected.value)
const total = computed(() => products.value.filter(item => picked.value.includes(item.id)).reduce((sum, item) => sum + item.priceCents * item.quantity, 0))
const money = cents => (Number(cents || 0) / 100).toFixed(2)
const active = scope => alive && scope === storageContext()
function failure(e,scope){
  if(!alive||ownerScope!==scope)return
  if(scope!==storageContext()||[401,403,404,409,410].includes(Number(e.code))||e.code==='SESSION_CHANGED'){
    preview.value=null;publication.value=null;selected.value=[];checkoutOpen.value=false;loginOpen.value=false;initialized=false;page.reset()
  }
  error.value=e.message;busy.value=false
}
const path = () => '/api/family/' + encodeURIComponent(getSession().householdId) + '/daily-arrangements/' + props.route.date + (props.route.meal === 'daily' ? '' : '/meals/' + props.route.meal) + '/purchase'
const version = () => ({ arrangement_id: props.route.arrangement, version: Number(props.route.version), ...(props.route.meal === 'daily' ? { meals: props.route.meals } : {}) })
const selectionKey = () => 'meal-purchase-selection:' + props.route.arrangement + ':' + props.route.meal + ':' + (props.route.meals || []).join(',')
function rememberSelection() { scopedStorage.setStorageSync(selectionKey(), { known: products.value.map(item => item.id), selected: [...picked.value] }) }
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
  uni.navigateTo({ url: '/pages/address/index', fail: () => { if (active(scope)) scopedStorage.setStorageSync(key, null) } })
}
async function resumeCheckout(scope) {
  if (!active(scope)) return
  const key = returnKey(), pending = scopedStorage.getStorageSync(key)
  if (!pending) return
  scopedStorage.setStorageSync(key, null)
  if (!preview.value?.available || error.value || pending.scope !== scope || !Number.isFinite(pending.at) || Date.now() - pending.at > 15 * 60 * 1000 || pending.at > Date.now()) return
  await checkout()
}
async function refresh() {
  if (ownerScope !== storageContext()) {
    ownerScope = storageContext(); preview.value = null; publication.value = null; selected.value = []
    initialized = false; checkoutOpen.value = false; loginOpen.value = false; busy.value = false; page.reset()
  }
  if (busy.value) return
  const scope = storageContext(); busy.value = true; error.value = ''; page.invalidateQuote()
  try {
    const { data } = await request({ path: path() + '?arrangement_id=' + encodeURIComponent(props.route.arrangement) + '&version=' + Number(props.route.version) + (props.route.meals || []).map(meal => '&meals=' + meal).join('') })
    if (!active(scope)) return
    preview.value = receipt(data)
    if (!initialized) {
      const saved = scopedStorage.getStorageSync(selectionKey())
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
  const scope = storageContext(); busy.value = true; error.value = ''; checkoutOpen.value = true
  try {
    try { await commerce.connect() }
    catch (e) { if (active(scope)) loginOpen.value = true; throw e }
    if (!active(scope)) return
    loginOpen.value = false
    if (publication.value && state.ready) {
      await page.prepare()
      return
    }
    const previous = [...picked.value], previousIds = products.value.map(item => item.id)
    const { data } = await request({ path: path(), method: 'POST', data: version(), timeout: 30000 })
    if (!active(scope)) return
    publication.value = receipt(data)
    await page.load()
    if (!active(scope) || !state.ready || state.error) return
    state.selected = page.plan.value.products.filter(item => previous.includes(item.id) || !previousIds.includes(item.id)).map(item => item.id)
    rememberSelection()
    await page.prepare()
  } catch (e) { failure(e,scope) }
  finally { if (active(scope)) busy.value = false }
}
async function submit() {
  await page.submit()
  if (alive && state.orderSn) uni.navigateTo({ url: '/pages/orders/detail?id=' + encodeURIComponent(state.orderSn) })
}
async function recover() {
  await page.recover()
  if (alive && state.orderSn) uni.navigateTo({ url: '/pages/orders/detail?id=' + encodeURIComponent(state.orderSn) })
}
onMounted(refresh)
onShow(refresh)
onUnmounted(() => { alive = false; page.dispose() })

</script>

<template>
 <view class="meal-purchase">
  <view class="section-head"><text class="section-title">{{route.meal==='daily'?'所选餐次食材汇总':'本餐所需食材'}}</text><text>家中已有可取消</text></view>
  <text v-if="busy||state.busy" class="safe-note">正在核对商品与配送…</text>
  <view v-if="error||state.error" class="card status" role="alert"><text>{{error||state.error}}</text><button class="secondary-button" :disabled="busy||state.busy" @click="refresh">重新核对本餐食材</button></view>
  <text v-if="preview&&!preview.available" class="inline-error">{{preview.message}}</text>
  <view class="products"><button v-for="item in products" :key="item.id" class="product" :disabled="busy||state.busy" :aria-pressed="picked.includes(item.id)" @click="toggle(item.id)"><view class="check" :class="{selected:picked.includes(item.id)}">{{picked.includes(item.id)?'✓':''}}</view><FoodImageSlot :src="item.imageUrl" :label="item.name" class="product-image"/><view class="product-copy"><text class="product-name">{{item.name}}</text><text>本餐需 {{item.needLabel}}</text><text>{{item.packLabel}} × {{item.quantity}} 包</text><text v-if="item.availableQuantity<item.quantity" class="stock-alert">库存不足</text></view><text class="product-price">¥{{money(item.priceCents*item.quantity)}}</text></button></view>
  <view class="meal-bottom-bar"><view class="selection-summary"><text>{{route.meal==='daily'?(route.meals||[]).map(m=>({breakfast:'早餐',lunch:'午餐',dinner:'晚餐'}[m])).join('、'):'已选 '+picked.length+' 项'}}</text><text class="amount">¥{{money(total)}}</text></view><button class="checkout-button" :disabled="busy||state.busy||!purchaseReady||!picked.length||!!error" @click="checkout">{{preview?.confirmation_pending?'确认上次采购结果':'去结算'}}<text v-if="!preview?.confirmation_pending">→</text></button></view>
  <PurchaseCheckoutSheet :open="checkoutOpen" :title="route.meal==='daily'?'确认采购订单':'确认本餐订单'" :address="state.address" :slots="state.slots" :slot-id="state.slotId" :products="products" :quote="state.quote" :busy="busy||state.busy" :error="error||state.error||state.checkoutError||state.deliveryMessage" :pending="!!(state.pending||state.orderSn)" :access-required="loginOpen" @close="checkoutOpen=false" @address="chooseAddress" @slot="state.slotId=$event;page.invalidateQuote()" @confirm="submit" @recover="recover" @quote="checkout"><template #access><CommerceAccess entry @ready="checkout"/></template></PurchaseCheckoutSheet>
 </view>
</template>
<style scoped>
.section-head{display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;gap:10rpx;margin:30rpx 0 14rpx}.section-title{font-size:29rpx;font-weight:500}.section-head>text:last-child{font-size:23rpx;color:#65728c}.products{border:1rpx solid #e9edf3;border-radius:26rpx;background:#fff;padding:0 18rpx}.product{display:flex;align-items:center;gap:16rpx;padding:18rpx 0;border-bottom:1rpx solid #eff2f6;width:100%;text-align:left;box-sizing:border-box}.product:last-child{border:0}.check{display:flex;align-items:center;justify-content:center;width:34rpx;height:34rpx;border:2rpx solid #bcc4d3;border-radius:8rpx;flex-shrink:0;font-size:26rpx;color:#fff}.check.selected{background:#0879f9;border-color:#0879f9}.product-image{width:108rpx;height:116rpx;border-radius:18rpx}.product-copy{flex:1;min-width:0}.product-copy text{display:block;color:#65728c;font-size:24rpx;line-height:1.6}.product-copy .product-name{color:#252a34;font-size:28rpx;font-weight:500;line-height:1.45;margin-bottom:6rpx;overflow-wrap:anywhere}.product-price{align-self:flex-end;padding-bottom:4rpx;flex-shrink:0;font-size:27rpx;font-weight:500;white-space:nowrap;font-variant-numeric:tabular-nums}.product-copy .stock-alert{color:#b83532}.meal-bottom-bar{position:fixed;z-index:10;left:0;right:0;bottom:0;padding:18rpx 32rpx calc(env(safe-area-inset-bottom) + 18rpx);display:flex;align-items:center;justify-content:space-between;gap:20rpx;background:#fff;border-top:1rpx solid #eceff4;box-sizing:border-box}.selection-summary{display:flex;align-items:baseline;justify-content:space-between;gap:16rpx;flex:1;min-width:0;font-size:24rpx}.selection-summary>text:first-child{line-height:1.5;max-width:50%;color:#465064}.amount{font-size:40rpx;font-weight:600;font-variant-numeric:tabular-nums;color:#20242c;white-space:nowrap}.checkout-button{display:flex;align-items:center;justify-content:center;gap:16rpx;background:#25262a;border-radius:999rpx;color:#fff;min-height:92rpx;padding:18rpx 24rpx;font-size:28rpx;line-height:1.5;max-width:46%;box-sizing:border-box}.status{padding:24rpx;font-size:27rpx;line-height:1.6}.status button{margin-top:16rpx}button[disabled]{opacity:.45}
@media(max-width:350px){.product{gap:12rpx}.product-image{width:86rpx;height:100rpx}.product-price{font-size:26rpx}.selection-summary{flex-direction:column;gap:0}.selection-summary>text:first-child{max-width:100%}.amount{font-size:38rpx}}
/* #ifdef H5 */
.meal-bottom-bar{max-width:480px;margin:0 auto}
/* #endif */
</style>

<style scoped>
@media(max-width:350px){.product-copy text,.section-head>text:last-child,.selection-summary{font-size:12px}.section-title,.product-copy .product-name{font-size:14px}}
</style>
