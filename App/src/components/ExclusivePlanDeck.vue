<script setup>
import { reactive, watch, onUnmounted } from 'vue'
import FoodImageSlot from './FoodImageSlot.vue'
import { planTiers, planTierNames } from '../services/exclusive-plan-flow.js'
import { priceText } from '../services/plan-presentation.js'
import { createPlanDeck, planDeckState } from '../services/exclusive-plan-deck.js'

const props = defineProps({ plans: { type: Array, default: () => [] }, selected: { type: String, default: 'standard' }, busy: Boolean, active: Boolean })
const emit = defineEmits(['select', 'detail'])
const state = reactive(planDeckState())
function reducedMotion() {
  // #ifdef H5
  return typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  // #endif
  // #ifndef H5
  return false
  // #endif
}
const deck = createPlanDeck({ state, commit: tier => emit('select', tier), reducedMotion })
const captions = { economy: '精打细算', standard: '日常之选', premium: '讲究一点' }
const descriptions = { economy: '精打细算，也把三餐安排妥当。', standard: '熟悉的家常味，也有每天的小变化。', premium: '食材更讲究，日常也值得好好对待。' }
watch(() => props.plans, () => deck.reset(props.selected), { immediate: true })
watch(() => props.selected, tier => { if (!state.moving && tier !== state.front) deck.reset(tier) })
watch(() => props.active, () => deck.reset(props.selected))
onUnmounted(deck.dispose)
function choose(tier) { if (props.active && !props.busy) deck.request(tier) }
function layer(tier) {
  if (state.moving && tier === state.to) return 'card-in card-in-' + state.direction
  if (state.moving && tier === state.from) return 'card-out card-out-' + state.direction
  const depth = (planTiers.indexOf(tier) - planTiers.indexOf(state.front) + 3) % 3
  return ['card-front', 'card-back-right', 'card-back-left'][depth]
}
function finish(tier, event) {
  if (tier !== state.to) return
  const name = event.detail?.animationName || event.animationName || ''
  if (name && !name.includes('plan-card-in-')) return
  deck.finish(state.token, true)
}
function detail(plan) {
  if (props.active && !props.busy && !state.moving && state.front === plan.tier_code) emit('detail', plan)
}
</script>

<template>
  <view class="exclusive-deck">
    <view class="tier-switch" role="group" aria-label="选择21天计划档位">
      <button v-for="tier in planTiers" :key="tier" :class="{ chosen: state.requested === tier }" :disabled="busy" :aria-pressed="state.requested === tier" @click="choose(tier)">
        <text>{{ planTierNames[tier] }}</text><text class="tier-caption">{{ captions[tier] }}</text>
      </button>
    </view>
    <view class="plan-stack" :class="{ 'is-moving': state.moving }" :aria-busy="state.moving">
      <view v-for="plan in plans" :id="'exclusive-card-' + plan.tier_code" :key="plan.tier_code" class="plan-card" :class="layer(plan.tier_code)" :aria-hidden="state.moving || state.front !== plan.tier_code" @animationend="finish(plan.tier_code, $event)">
        <view class="card-intro">
          <view class="card-copy"><text class="card-overline">21 天家庭饮食计划</text><text class="card-title">{{ planTierNames[plan.tier_code] }}</text><text class="card-description">{{ plan.difference || descriptions[plan.tier_code] }}</text></view>
          <view class="card-photo-wrap"><FoodImageSlot class="card-photo" :src="plan.display?.image_url || '/static/plans/meal-preview.webp'" :label="planTierNames[plan.tier_code]"/><text v-if="!plan.display?.image_url" class="photo-caption">餐食示意</text></view>
        </view>
        <view class="card-tags"><text>▢ &nbsp;21 天安排</text><text>早 餐 · 午 餐 · 晚 餐</text></view>
        <view class="card-summary"><text>把 21 天的早、午、晚餐提前安排好，</text><text>每天的菜品与家人份量，展开就能看。</text></view>
        <view class="card-price"><view><text class="price-caption">21 天食材与服务预估</text><text class="price-value">{{ priceText(plan.estimated_subtotal_cent) }}</text></view><text class="delivery-caption">配送费选址后计算</text></view>
        <button class="card-primary" :disabled="busy || state.moving || state.front !== plan.tier_code" @click="detail(plan)">查看完整计划 <text>→</text></button>
      </view>
    </view>
    <text class="deck-note">三档均依据家庭档案安排，菜品与食材选择有所不同。</text>
  </view>
</template>

<style scoped>
.exclusive-deck{min-width:0}.tier-switch{display:flex;gap:12rpx;padding:10rpx;background:#e9eef7;border:1rpx solid rgba(255,255,255,.65);border-radius:34rpx;margin:0 0 48rpx}.tier-switch button{flex:1;min-width:0;min-height:122rpx;margin:0;padding:18rpx 8rpx;border:1rpx solid transparent;border-radius:24rpx;background:transparent;color:#778292;font-size:30rpx;line-height:1.5}.tier-switch button::after,.card-primary::after{border:0}.tier-switch button.chosen{color:#476fc3;background:#fff;border-color:#e4ebf7;box-shadow:0 6rpx 18rpx #3e578012}.tier-caption{display:block;margin-top:6rpx;font-size:22rpx;color:#8993a3}.chosen .tier-caption{color:#6c8cc1}
.plan-stack{display:grid;grid-template-columns:minmax(0,1fr);position:relative;isolation:isolate;perspective:1400px;margin:0 4rpx}.plan-card{grid-area:1/1;min-width:0;display:flex;flex-direction:column;position:relative;padding:38rpx;background:#fff;border:1rpx solid #fefeff;border-radius:48rpx;box-shadow:0 14rpx 48rpx #4e65820a;transform-origin:50% 57%;backface-visibility:hidden;pointer-events:none}.plan-card::after{content:'';position:absolute;inset:0;border-radius:inherit;background:#dce6f8;opacity:0;pointer-events:none}.card-front{z-index:3;pointer-events:auto;transform:translate(0,0) rotate(0deg) scale(1)}.card-back-right{z-index:2;transform:translate(10rpx,-20rpx) rotate(2.4deg) scale(.974);opacity:.96}.card-back-right::after{opacity:.5}.card-back-left{z-index:1;transform:translate(-10rpx,-30rpx) rotate(-2.6deg) scale(.953);opacity:.9}.card-back-left::after{opacity:.65}.is-moving .plan-card{will-change:transform,opacity;pointer-events:none}.card-in{z-index:4;animation-duration:800ms;animation-timing-function:cubic-bezier(.38,0,.2,1);animation-fill-mode:both}.card-out{z-index:3;animation-duration:800ms;animation-timing-function:cubic-bezier(.38,0,.2,1);animation-fill-mode:both}.card-in-forward{animation-name:plan-card-in-forward}.card-in-backward{animation-name:plan-card-in-backward}.card-out-forward{animation-name:plan-card-out-forward}.card-out-backward{animation-name:plan-card-out-backward}
.card-intro{display:flex;align-items:center;justify-content:space-between;gap:20rpx;min-height:228rpx}.card-copy{flex:1;min-width:0}.card-overline{display:block;color:#8793a4;font-size:22rpx;letter-spacing:1rpx}.card-title{display:block;margin:6rpx 0 12rpx;font-size:50rpx;font-weight:500;line-height:1.5;letter-spacing:2rpx;color:#353b46}.card-description{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;color:#747e8d;font-size:25rpx;line-height:1.8;min-height:3.6em}.card-photo-wrap{position:relative;width:220rpx;height:220rpx;flex-shrink:0}.card-photo{width:220rpx;height:220rpx;border-radius:50%;border:10rpx solid #f6f8fb;box-sizing:border-box;box-shadow:0 14rpx 26rpx #576f8412}.photo-caption{position:absolute;bottom:-6rpx;left:50%;transform:translateX(-50%);padding:2rpx 10rpx;white-space:nowrap;background:#ffffffed;border-radius:10rpx;color:#8a93a1;font-size:21rpx;line-height:1.5}.card-tags{display:flex;gap:28rpx;flex-wrap:wrap;padding:32rpx 0 38rpx;font-size:22rpx;color:#7c8aa0;line-height:1.6}.card-summary{padding-top:30rpx;border-top:1rpx solid #eef1f6;color:#7b899e;font-size:25rpx;line-height:1.9}.card-summary text{display:block}.card-price{display:flex;align-items:flex-end;justify-content:space-between;gap:20rpx;margin-top:auto;padding:30rpx 0 34rpx;border-top:1rpx solid #eef1f6;margin-top:38rpx}.card-price>view{display:flex;flex-direction:column;gap:6rpx}.price-caption{font-size:22rpx;color:#8b95a4}.price-value{font-size:38rpx;line-height:1.5;font-weight:500;color:#596d89}.delivery-caption{font-size:21rpx;color:#929baa;text-align:right}.card-primary{display:flex;align-items:center;justify-content:space-between;gap:20rpx;min-height:94rpx;margin:0;padding:24rpx 36rpx;width:100%;box-sizing:border-box;border-radius:28rpx;background:linear-gradient(110deg,#5a7dca,#476fc3);color:#fff;font-size:29rpx;line-height:1.5;font-weight:500;box-shadow:0 10rpx 20rpx #476fc315}.card-primary text{font-size:36rpx;font-weight:400}.card-primary[disabled]{color:#fff;opacity:1}.deck-note{display:block;margin:36rpx 12rpx 0;text-align:center;color:#929baa;font-size:22rpx;line-height:1.8}
@keyframes plan-card-in-forward{0%{transform:translate(7%,-24rpx) rotate(6.5deg) scale(.94);opacity:.22}38%{transform:translate(8%,6rpx) rotate(5.5deg) scale(.96);opacity:.57}75%{transform:translate(2%,2rpx) rotate(1.8deg) scale(.992);opacity:.94}100%{transform:translate(0,0) rotate(0deg) scale(1);opacity:1}}
@keyframes plan-card-in-backward{0%{transform:translate(-7%,-24rpx) rotate(-6.5deg) scale(.94);opacity:.22}38%{transform:translate(-8%,6rpx) rotate(-5.5deg) scale(.96);opacity:.57}75%{transform:translate(-2%,2rpx) rotate(-1.8deg) scale(.992);opacity:.94}100%{transform:translate(0,0) rotate(0deg) scale(1);opacity:1}}
@keyframes plan-card-out-forward{0%{transform:translate(0,0) rotate(0deg) scale(1);opacity:1}43%{transform:translate(-8%,20rpx) rotate(-7deg) scale(.945);opacity:.36}66%{transform:translate(-5%,0) rotate(-4deg) scale(.945);opacity:.55}100%{transform:translate(-10rpx,-30rpx) rotate(-2.6deg) scale(.953);opacity:.9}}
@keyframes plan-card-out-backward{0%{transform:translate(0,0) rotate(0deg) scale(1);opacity:1}43%{transform:translate(8%,20rpx) rotate(7deg) scale(.945);opacity:.36}66%{transform:translate(5%,0) rotate(4deg) scale(.945);opacity:.55}100%{transform:translate(10rpx,-20rpx) rotate(2.4deg) scale(.974);opacity:.96}}
@media(max-width:350px){.plan-card{padding:30rpx}.card-photo-wrap,.card-photo{width:176rpx;height:176rpx}.card-intro{gap:14rpx}.card-title{font-size:46rpx}.card-tags{gap:20rpx}.card-overline{letter-spacing:0}.card-description,.card-summary{font-size:24rpx}}
@media(prefers-reduced-motion:reduce){.card-in,.card-out{animation-duration:1ms}}
</style>
