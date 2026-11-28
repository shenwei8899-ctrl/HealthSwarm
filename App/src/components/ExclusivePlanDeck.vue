<script setup>
import { reactive, nextTick, onUnmounted } from 'vue'
import { planTierNames, planTierReferencePrices, planTierReferenceRanges } from '../services/exclusive-plan-flow.js'

defineProps({ plans: { type: Array, default: () => [] }, disabled: Boolean, actionLabel: { type: String, default: '查看计划' } })
const emit = defineEmits(['detail'])
const tierArt = {
  economy: '/pages/exclusive-plans/static/economy-v4.jpg',
  standard: '/pages/exclusive-plans/static/standard-v4.jpg',
  premium: '/pages/exclusive-plans/static/premium-v4.jpg',
}
const artState = reactive(Object.fromEntries(Object.keys(tierArt).map(tier => [tier, { status: 'loading', attempt: 0, mounted: true }])))
let alive = true
onUnmounted(() => { alive = false })
function currentArt(tier, event) {
  const state = artState[tier]
  const attempt = Number(event.currentTarget?.dataset?.attempt ?? event.target?.dataset?.attempt)
  return alive && state?.mounted && state.status === 'loading' && attempt === state.attempt ? state : null
}
function artLoaded(tier, event) {
  const state = currentArt(tier, event)
  if (!state) return
  state.status = 'loaded'
  console.info('[plan-art] loaded', { revision: 'jpeg-v4', tier, src: tierArt[tier], attempt: state.attempt, width: event.detail?.width, height: event.detail?.height })
}
async function artError(tier, event) {
  const state = currentArt(tier, event)
  if (!state) return
  console.warn('[plan-art] failed', { revision: 'jpeg-v4', tier, src: tierArt[tier], attempt: state.attempt, error: event.detail?.errMsg || 'image load failed' })
  if (state.attempt >= 1) { state.status = 'failed'; return }
  state.mounted = false
  state.attempt++
  await nextTick()
  if (alive) state.mounted = true
}
const tierCopy = {
  economy: {tag:'日常实惠',description:'更注重日常花费'},
  standard: {tag:'日常之选',description:'兼顾预算与食材选择'},
  premium: {tag:'品质之选',description:'更宽裕的食材预算'},
}
</script>

<template>
  <view class="plan-list">
    <button v-for="plan in plans" :key="plan.tier_code" class="plan-option"
      :class="'tier-' + plan.tier_code" :aria-label="actionLabel + '，' + planTierNames[plan.tier_code] + '，' + planTierReferencePrices[plan.tier_code]"
      :disabled="disabled" hover-class="option-pressed" @click="emit('detail', plan)">
      <view class="option-top">
        <view class="option-copy"><text class="option-tag">{{tierCopy[plan.tier_code].tag}}</text><text class="option-title">{{ planTierNames[plan.tier_code] }}</text><text class="option-caption">{{tierCopy[plan.tier_code].description}}</text></view>
        <view class="option-art-frame" aria-hidden="true">
          <view v-if="artState[plan.tier_code].status !== 'loaded'" class="option-art-placeholder"><view class="art-placeholder-plate"/><text v-if="artState[plan.tier_code].status === 'failed'">配图暂不可用</text></view>
          <image v-if="artState[plan.tier_code].mounted && artState[plan.tier_code].status !== 'failed'" :key="plan.tier_code + ':' + artState[plan.tier_code].attempt" class="option-art" :class="{ 'art-loaded': artState[plan.tier_code].status === 'loaded' }" :data-tier="plan.tier_code" :data-attempt="artState[plan.tier_code].attempt" :src="tierArt[plan.tier_code]" mode="aspectFit" @load="artLoaded(plan.tier_code, $event)" @error="artError(plan.tier_code, $event)"/>
          <view v-if="artState[plan.tier_code].status === 'loaded'" class="option-wash"/>
        </view>
      </view>
      <view class="option-footer">
        <view class="option-reference"><text class="reference-label">参考</text><text class="reference-currency">¥</text><text class="reference-range">{{planTierReferenceRanges[plan.tier_code].min}}–{{planTierReferenceRanges[plan.tier_code].max}}</text><text class="reference-unit">/人/天</text></view>
        <view class="option-action"><text class="option-action-label">{{actionLabel}}</text><text v-if="!disabled" class="option-arrow" aria-hidden="true">↗</text></view>
      </view>
    </button>
  </view>
</template>

<style scoped>
.plan-list{display:flex;flex-direction:column;gap:12px}
.plan-option{--tier-ink:#558d7c;--tier-soft:#e2f2eb;position:relative;display:block;width:100%;min-height:139px;overflow:hidden;margin:0;padding:0;text-align:left;line-height:1.5;color:#3d354c;background:#fff;border:1px solid #fff;border-radius:21px;box-shadow:0 6px 18px #6f4c9007;box-sizing:border-box}
.plan-option::after{border:0}.tier-standard{--tier-ink:#8251b5;--tier-soft:#eee2fa}.tier-premium{--tier-ink:#aa733b;--tier-soft:#fbecd9}
.option-top{position:relative;display:flex;align-items:center;min-height:94px;padding:12px 16px 7px;box-sizing:border-box}
.option-copy{position:relative;z-index:1;min-width:0;width:calc(100% - 130px)}
.option-tag{display:inline-block;padding:3px 6px;border-radius:5px;background:var(--tier-soft);color:var(--tier-ink);font-size:10px;line-height:1.4}
.option-title{display:block;margin-top:5px;font-size:20px;line-height:1.4;font-weight:600;letter-spacing:.3px}
.option-caption{display:block;margin-top:4px;font-size:12px;line-height:1.5;color:#8a7597;overflow-wrap:anywhere}
.option-art-frame{position:absolute;right:12px;top:50%;margin-top:-44px;width:126px;height:88px;overflow:hidden;border-radius:16px;pointer-events:none}
.option-art{position:relative;z-index:1;display:block;width:126px;height:88px;opacity:0}.option-art.art-loaded{opacity:1}.option-wash{position:absolute;z-index:2;inset:0;background:linear-gradient(90deg,#fff,rgba(255,255,255,0) 20%);pointer-events:none}
.option-art-placeholder{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:5px;background:#faf8fc;color:#a494af;font-size:10px}.art-placeholder-plate{width:38px;height:38px;border:2px solid #ddd4e6;border-radius:50%;box-shadow:inset 0 0 0 5px #f0eaf5;background:#e5dcec}
.option-footer{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:44px;padding:8px 16px;border-top:1px solid #ede6f4;box-sizing:border-box}
.option-reference{display:flex;align-items:baseline;gap:3px;white-space:nowrap;flex-shrink:0}.reference-label{margin-right:2px;color:#927c9f;font-size:11px}.reference-currency{color:#5a456b;font-size:12px}.reference-range{color:#46364f;font-size:21px;font-weight:400;letter-spacing:-.7px;line-height:1.2}.reference-unit{margin-left:3px;color:#8a7597;font-size:11px}
.option-action{display:flex;align-items:center;justify-content:flex-end;gap:6px;min-width:0;color:#887197;font-size:12px;line-height:1.5;white-space:nowrap}.option-arrow{color:var(--tier-ink);font-size:17px;line-height:1}.option-pressed{opacity:.82}.plan-option[disabled]{opacity:1}.plan-option[disabled] .option-action{color:#9b8baa}.plan-option:focus-visible{outline:2px solid #8552ce;outline-offset:2px}
@media(max-width:350px){.option-top{padding-left:13px;padding-right:13px;min-height:94px}.option-copy{width:calc(100% - 110px)}.option-art-frame{right:8px;width:106px;height:74px;margin-top:-37px}.option-art{width:106px;height:74px}.option-title{font-size:19px}.option-caption{font-size:11px}.option-footer{padding-left:13px;padding-right:13px;gap:5px}.reference-range{font-size:20px}.reference-label,.reference-unit{font-size:10px}.option-action{font-size:11px;gap:4px}}
</style>
