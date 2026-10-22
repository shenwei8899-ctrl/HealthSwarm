<script setup>
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
    <view class="section-head"><text class="section-title">{{route.meal === 'daily' ? '所选餐次食材汇总' : '本餐所需食材和购买清单'}}</text><text>已选 {{ picked.length }} 项</text></view>
    <text class="safe-note">{{route.meal === 'daily' ? '按所选餐次需求' : '按本餐需求'}}匹配整包装食材，家中已有的可以取消购买。</text>
    <text v-if="busy || state.busy" class="safe-note">正在核对本餐商品与配送…</text>
    <view v-if="error || state.error" class="card status"><text>{{ error || state.error }}</text><button class="secondary-button" :disabled="busy || state.busy" @click="refresh">重新核对本餐食材</button></view>
    <text v-if="preview && !preview.available" class="inline-error">{{ preview.message }}</text>
    <view v-for="item in products" :key="item.id" class="card product" @click="toggle(item.id)">
      <view class="check" :class="{ selected: picked.includes(item.id) }">{{ picked.includes(item.id) ? '✓' : '' }}</view>
      <image v-if="item.imageUrl" :src="item.imageUrl" mode="aspectFill" />
      <view class="product-copy"><text>{{ item.name }}</text><text>{{ item.needLabel }}</text><text>{{ item.packLabel }} × {{ item.quantity }} 包</text><text>可售 {{ item.availableQuantity }} 包</text></view>
      <text>¥{{ money(item.priceCents * item.quantity) }}</text>
    </view>
    <text v-if="preview" class="safe-note">商品小计供采购核对；配送费、优惠和应付金额以结算报价为准。</text>
    <view class="meal-bottom-bar"><view><text>已选 {{ picked.length }} 项</text><text class="amount">¥{{ money(total) }}</text></view><button class="primary-button" :disabled="busy || state.busy || !purchaseReady || !picked.length || !!error" @click="checkout">{{ preview?.confirmation_pending ? '确认上次采购结果' : '去结算／直接购买' }}</button></view>
    <view v-if="checkoutOpen" class="sheet-mask"><view class="sheet checkout-sheet">
      <view class="sheet-head"><text class="section-title">{{route.meal === 'daily' ? '确认采购订单' : '确认本餐订单'}}</text><button :disabled="busy || state.busy" @click="checkoutOpen = false">×</button></view>
      <CommerceAccess v-if="loginOpen" entry @ready="checkout" />
      <template v-else>
        <button class="card address" :disabled="busy || state.busy" @click="uni.navigateTo({url:'/pages/address/index'})"><text>{{ state.address ? state.address.name + ' · ' + state.address.phone : '请选择配送地址' }}</text><text v-if="state.address">{{ state.address.region }} {{ state.address.detail }}</text></button>
        <view v-for="slot in state.slots" :key="slot.id"><button :disabled="busy || state.busy" :class="{chosen: state.slotId === slot.id}" @click="state.slotId = slot.id; page.invalidateQuote()">{{ slot.name || slot.start_time + '—' + slot.end_time }}</button></view>
        <text v-if="state.deliveryMessage" class="inline-error">{{ state.deliveryMessage }}</text>
        <text v-if="error || state.error || state.checkoutError" class="inline-error">{{ error || state.error || state.checkoutError }}</text>
        <view v-if="state.quote" class="quote"><view v-for="line in state.quote.items" :key="line.sku_id"><text>{{ line.snapshot?.product_name }} × {{ line.quantity }}</text><text>¥{{ money(line.line_amount_cent) }}</text></view><text>商品 ¥{{ money(state.quote.goods_amount_cent) }} · 配送 ¥{{ money(state.quote.shipping_fee_cent) }} · 优惠 ¥{{ money(state.quote.discount_amount_cent) }}</text><text class="amount">应付 ¥{{ money(state.quote.payable_amount_cent) }}</text></view>
        <button v-if="state.pending || state.orderSn" class="primary-button" :disabled="busy || state.busy" @click="recover">确认原订单结果</button>
        <button v-else-if="state.quote" class="primary-button" :disabled="busy || state.busy" @click="submit">确认下单 ¥{{ money(state.quote.payable_amount_cent) }}</button>
        <button v-else class="primary-button" :disabled="busy || state.busy" @click="checkout">核对商品与价格</button>
        <text class="safe-note">下单后进入订单详情支付，以服务端支付结果为准。</text>
      </template>
    </view></view>
  </view>
</template>

<style scoped>
.section-head{display:flex;align-items:center;justify-content:space-between;gap:16rpx;margin:36rpx 0 18rpx}.section-head>text:last-child{color:#777;font-size:24rpx}.product{display:flex;align-items:center;gap:16rpx;padding:22rpx;margin:16rpx 0}.product image{width:90rpx;height:90rpx;border-radius:16rpx}.product-copy{flex:1;min-width:0}.product-copy text{display:block;line-height:1.7;font-size:23rpx;color:#777}.product-copy text:first-child{font-size:28rpx;color:#222}.check{width:36rpx;height:36rpx;border:1rpx solid #999;border-radius:8rpx;flex-shrink:0;text-align:center}.check.selected{background:#222;color:white}.meal-bottom-bar{position:fixed;z-index:10;left:0;right:0;bottom:0;padding:20rpx 32rpx calc(env(safe-area-inset-bottom) + 20rpx);display:flex;align-items:center;gap:24rpx;border-top:1rpx solid #ddd;background:#fff}.meal-bottom-bar>view{display:flex;flex-direction:column;gap:6rpx;font-size:23rpx}.meal-bottom-bar .primary-button{flex:1}.amount{font-size:34rpx;font-weight:600}.checkout-sheet{max-height:85vh;overflow:auto}.address{width:100%;padding:24rpx;text-align:left;margin:24rpx 0}.address text{display:block;line-height:1.7}.quote{display:flex;flex-direction:column;gap:20rpx;margin:28rpx 0}.quote>view{display:flex;justify-content:space-between;gap:18rpx}.chosen{background:#eee}.status{padding:24rpx}
</style>
