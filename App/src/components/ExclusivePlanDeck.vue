<script setup>
import { planTierNames } from '../services/exclusive-plan-flow.js'

defineProps({ plans: { type: Array, default: () => [] }, disabled: Boolean, actionLabel: { type: String, default: '查看计划' } })
const emit = defineEmits(['detail'])
const tierArt = {
  economy: '/static/plans/economy-v2.webp',
  standard: '/static/plans/standard-v2.webp',
  premium: '/static/plans/premium-v2.webp',
}
</script>

<template>
  <view class="plan-list">
    <button v-for="plan in plans" :key="plan.tier_code" class="plan-option"
      :class="'tier-' + plan.tier_code" :aria-label="'查看' + planTierNames[plan.tier_code] + '计划'"
      :disabled="disabled" hover-class="option-pressed" @click="emit('detail', plan)">
      <image class="option-art" :src="tierArt[plan.tier_code]" mode="aspectFill" aria-hidden="true"/>
      <view class="option-wash" aria-hidden="true"/>
      <view class="option-copy">
        <text class="option-title">{{ planTierNames[plan.tier_code] }}</text>
        <text class="option-caption">21 天 · 每日三餐</text>
        <view class="option-link"><text>{{ actionLabel }}</text><text v-if="!disabled" class="option-arrow" aria-hidden="true">›</text></view>
      </view>
    </button>
  </view>
</template>

<style scoped>
.plan-list{display:flex;flex-direction:column;gap:26rpx}
.plan-option{--card-base:#fff;--card-rgb:255,255,255;--card-ink:#5c7eaf;position:relative;isolation:isolate;display:flex;align-items:center;width:100%;height:340rpx;overflow:hidden;margin:0;padding:40rpx;text-align:left;line-height:1.5;color:#424b60;background:linear-gradient(110deg,#fff,#edf5ff);border:2rpx solid rgba(224,233,246,.85);border-radius:40rpx;box-shadow:0 12rpx 30rpx rgba(71,99,148,.045);box-sizing:border-box}
.plan-option::after{border:0}
.option-art{position:absolute;inset:0;width:100%;height:100%;z-index:0;pointer-events:none}
.option-wash{position:absolute;inset:0;z-index:1;pointer-events:none;background:linear-gradient(90deg,var(--card-base) 0%,rgba(var(--card-rgb),.97) 28%,rgba(var(--card-rgb),.7) 43%,rgba(var(--card-rgb),0) 64%)}
.option-copy{position:relative;z-index:2;width:52%;min-width:0}
.option-title,.option-caption{display:block}.option-title{font-size:42rpx;line-height:1.4;font-weight:600;letter-spacing:2rpx}.option-caption{margin-top:18rpx;color:#8b97aa;font-size:23rpx;font-weight:400;white-space:nowrap}
.option-link{display:flex;align-items:center;gap:14rpx;margin-top:38rpx;color:var(--card-ink);font-size:24rpx;font-weight:500}
.option-arrow{display:flex;align-items:center;justify-content:center;width:42rpx;height:42rpx;flex:none;border-radius:50%;border:1rpx solid rgba(112,144,190,.2);background:rgba(238,245,255,.8);font-size:32rpx;font-weight:400;line-height:1;padding-bottom:3rpx;box-sizing:border-box}
.option-pressed{opacity:.75}.plan-option[disabled]{opacity:1;color:#424b60}.plan-option[disabled] .option-link{color:#8794aa}
@media(max-width:350px){.plan-option{padding:34rpx;height:350rpx}.option-title{font-size:42rpx}.option-caption{font-size:24rpx}.option-link{font-size:25rpx}}
</style>
