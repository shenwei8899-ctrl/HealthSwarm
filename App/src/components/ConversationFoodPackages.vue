<script setup>
import FoodImageSlot from './FoodImageSlot.vue'
import { ref, watch, onUnmounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { request } from '../services/request.js'
import { storageContext } from '../services/storage.js'
import { packagePrice, packageSpec } from '../utils/package-presentation.js'
const props = defineProps({ offers: Array, requestId: String, animate: Boolean })
const emit = defineEmits(['ready'])
const offers = ref([]), error = ref(''), loading = ref(false), opening = ref('')
let alive = true, revision = 0, owner = storageContext(), navigationTimer
async function load() {
  const ticket = ++revision, scope = storageContext(), id = props.requestId
  owner = scope; offers.value = []; error.value = ''; loading.value = false; opening.value = ''
  clearTimeout(navigationTimer)
  if (Array.isArray(props.offers)) { offers.value = props.offers; return }
  if (!id) return
  loading.value = true
  const current = () => alive && ticket === revision && scope === storageContext() && id === props.requestId
  try {
    const { data } = await request({ path: '/api/health/v1/conversation-purchases/' + encodeURIComponent(id) })
    if (!current()) return
    if (!Array.isArray(data?.offers) || data.request_id && data.request_id !== id) throw new Error('invalid receipt')
    offers.value = data.offers
    emit('ready')
  } catch { if (current()) error.value = '食材包暂时未能读取，请重试。' }
  finally { if (current()) loading.value = false }
}
function open(offer) {
  if (!alive || owner !== storageContext() || opening.value || !offer.available || !offer.offer_token || !props.requestId) return
  const ticket = revision, scope = owner
  opening.value = offer.offer_token; error.value = ''
  uni.navigateTo({
    url: '/pages/shop/index?conversation=' + encodeURIComponent(props.requestId) + '&offer=' + encodeURIComponent(offer.offer_token),
    fail: () => { if (alive && ticket === revision && scope === storageContext()) { opening.value = ''; error.value = '未能打开食材包，请再试一次。' } },
    complete: () => { navigationTimer = setTimeout(() => { if (alive && ticket === revision) opening.value = '' }, 500) },
  })
}
watch(() => [props.requestId, props.offers], load, { immediate: true })
onShow(() => { opening.value = '' })
onUnmounted(() => { alive = false; revision++; clearTimeout(navigationTimer) })

</script>
<template>
 <view class="package-results" :class="{'is-entering':animate}">
  <view v-if="loading" class="package-loading" role="status"><view class="loading-image"/><view><text>正在读取食材包</text><text>稍等一下，正在核对商品信息</text></view></view>
  <view v-if="error" class="package-status" role="alert"><text>{{error}}</text><button v-if="!offers.length" @click="load">重新读取</button></view>
  <text v-else-if="!loading&&!offers.length" class="package-empty">这次没有可展示的食材包，可以重新问问营养师。</text>
  <button v-for="(offer,index) in offers" :key="offer.offer_token" class="package-card" :class="{'is-unavailable':!offer.available}" :style="{'animation-delay':index*45+'ms'}" :disabled="!offer.available||!!opening" hover-class="package-pressed" :hover-stay-time="90" :aria-label="offer.name+'，'+packageSpec(offer.spec)+'，'+(packagePrice(offer.price_cent)===null?'价格待核对':'参考价'+packagePrice(offer.price_cent)+'元')+'，'+(offer.available?'查看商品':'暂不可选，请重新询问')" @click="open(offer)">
   <FoodImageSlot :src="offer.image_url" :label="offer.name" :width="76" :height="76" :radius="18" fallback-icon class="package-image"/>
   <view class="package-copy">
    <text class="package-name">{{offer.name}}</text>
    <text v-if="offer.spec" class="package-spec">{{packageSpec(offer.spec)}}</text>
    <view class="package-bottom"><view v-if="packagePrice(offer.price_cent)!==null" class="package-price"><text class="price-currency">¥</text><text class="price-value">{{packagePrice(offer.price_cent)}}</text><text class="price-hint">参考价</text></view><text v-else class="price-pending">价格待核对</text><text class="package-action">{{opening===offer.offer_token?'打开中…':offer.available?'查看 ›':'暂不可选'}}</text></view>
   </view>
  </button>
 </view>
</template>
<style scoped>
.package-results{margin-top:16px;padding:2px 0 0}
.package-card{position:relative;display:flex;align-items:center;gap:14px;width:100%;min-height:108px;margin:0 0 12px;padding:15px;border:1px solid var(--ui-bubble-line,#fff);border-radius:25px;text-align:left;white-space:normal;overflow:hidden;color:var(--ui-text,#323747);background:var(--ui-bubble,#fff);box-shadow:var(--ui-bubble-shadow,0 4px 18px rgba(62,47,82,.04));transition:transform 160ms ease,box-shadow 160ms ease}
.package-card:after{border:0}.package-card[disabled]{opacity:1}.package-pressed{transform:scale(.99);box-shadow:inset 0 1px 0 #fff,0 1px 5px rgba(62,73,112,.05)}
.package-image{border:1px solid rgba(255,255,255,.9);box-shadow:0 2px 7px rgba(44,56,78,.04)}
.package-copy{flex:1;min-width:0}.package-name{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;font-size:16px;font-weight:500;line-height:1.45;color:#323747;overflow-wrap:anywhere}
.package-spec{display:block;font-size:12px;line-height:1.55;color:var(--ui-muted,#687286);margin-top:4px;overflow-wrap:anywhere}
.package-bottom{display:flex;align-items:center;justify-content:space-between;gap:6px;flex-wrap:wrap;margin-top:9px;min-height:30px}.package-price{display:flex;align-items:baseline;gap:2px;line-height:1.4;color:#343b4a;font-variant-numeric:tabular-nums}.price-value{font-size:19px;font-weight:500}.price-currency{font-size:12px}.price-hint{font-size:10px;color:#768092;margin-left:4px}.price-pending{font-size:12px;color:#687286}
.package-action{color:var(--ui-accent,#70558f);font-size:12px;line-height:1.5;white-space:nowrap}.is-unavailable .package-action{color:var(--ui-muted,#6c7483)}
.package-loading{display:flex;align-items:center;gap:14px;min-height:132px;padding:14px;border-radius:25px;background:rgba(255,255,255,.55);color:#65728a;font-size:13px}.loading-image{width:88px;height:88px;border-radius:17px;background:linear-gradient(135deg,#e5ecfa,#f3effa);flex-shrink:0}.package-loading text{display:block;line-height:1.7}.package-loading text+text{font-size:11px;color:#747b8c;margin-top:5px}.package-status{display:flex;align-items:center;gap:10px;padding:12px 4px;color:#6d5c6d;font-size:12px;line-height:1.7}.package-status>text{flex:1}.package-status button{min-height:44px;padding:8px;font-size:12px;color:#66528c}.package-empty{display:block;padding:12px 4px;font-size:12px;line-height:1.7;color:#747b8c}
.is-entering .package-card{animation:package-appear 260ms ease-out backwards}@keyframes package-appear{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
@media(max-width:350px){.package-card{gap:11px;padding:12px}.price-hint{display:none}}
@media(prefers-reduced-motion:reduce){.package-card{animation:none!important;transition:none}}
</style>
