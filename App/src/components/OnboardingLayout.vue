<script setup>
import AppNavBar from './AppNavBar.vue'

defineProps({ title: String, heading: String, description: String, step: { type: Number, default: 0 } })
defineEmits(['back'])
const steps = ['基本资料', '健康偏好', '饮食限制']
</script>

<template>
  <view class="onboarding-layout">
    <view class="onboarding-canvas" aria-hidden="true" />
    <view class="onboarding-content">
      <AppNavBar>
        <view class="nav-row onboarding-nav">
          <button class="onboarding-back" aria-label="返回" @click="$emit('back')"><view class="back-chevron" /></button>
          <text class="nav-title">{{ title }}</text>
          <text class="step-count">{{ step + 1 }} / 3</text>
        </view>
      </AppNavBar>

      <view class="onboarding-hero">
        <view class="hero-copy">
          <text class="onboarding-heading">{{ heading }}</text>
          <text class="onboarding-description">{{ description }}</text>
        </view>
        <image class="onboarding-assistant" src="/static/chat/nutrition-boy-v2-poster.png" mode="aspectFit" aria-hidden="true" />
      </view>

      <view class="onboarding-steps" aria-label="建档进度">
        <template v-for="(label, index) in steps" :key="label">
          <view class="onboarding-step" :class="{ active: index === step, complete: index < step }" :aria-current="index === step ? 'step' : undefined">
            <text class="step-dot">{{ index < step ? '✓' : index + 1 }}</text>
            <text class="step-label">{{ label }}</text>
          </view>
          <view v-if="index < 2" class="step-connector" :class="{ complete: index < step }" aria-hidden="true" />
        </template>
      </view>

      <view class="onboarding-body"><slot /></view>
      <view class="onboarding-footer"><view class="footer-content"><slot name="footer" /></view></view>
    </view>
  </view>
</template>

<style scoped>
.onboarding-layout{font-weight:500;--onboarding-accent:#7660ad;--onboarding-ink:#383b50;--onboarding-muted:#7c8299;--onboarding-line:#e9eaf3;--onboarding-tint:#f0ecfa;position:relative;min-height:100vh;color:var(--onboarding-ink);font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;line-height:1.6}
.onboarding-canvas{position:fixed;inset:0;pointer-events:none;background:linear-gradient(180deg,#dfe7fb 0%,#edf0fb 38%,#f3f4fa 72%,#e9ecf8);z-index:0}
.onboarding-content{position:relative;z-index:1;box-sizing:border-box;max-width:480px;margin:0 auto;padding:0 20px calc(env(safe-area-inset-bottom) + 116px)}
.onboarding-nav{min-height:48px}.onboarding-back{display:flex;align-items:center;justify-content:center;flex:none;width:44px;min-height:44px;margin-left:-10px;padding:0;border:0;background:transparent;border-radius:14px}.onboarding-back::after{border:0}.back-chevron{width:9px;height:9px;border-left:1.5px solid #62677c;border-bottom:1.5px solid #62677c;transform:rotate(45deg)}
.nav-title{font-weight:600;color:#61667e;font-size:14px;}.step-count{font-weight:500;margin-left:auto;font-size:11px;letter-spacing:1px;color:#858ba2;font-variant-numeric:tabular-nums}
.onboarding-hero{position:relative;display:flex;align-items:center;min-height:112px;padding:10px 0 15px}.hero-copy{position:relative;z-index:1;flex:1;min-width:0;padding-right:60px}.onboarding-heading{display:block;font-size:25px;font-weight:600;letter-spacing:.2px;line-height:1.5;overflow-wrap:anywhere}.onboarding-description{font-weight:500;display:block;margin-top:7px;color:#767e98;font-size:12px;line-height:1.8}.onboarding-assistant{position:absolute;right:-6px;bottom:8px;width:81px;height:102px;pointer-events:none}
.onboarding-steps{display:flex;align-items:center;gap:10px;padding:5px 0 22px}.onboarding-step{display:flex;align-items:center;gap:6px;flex:none;color:#8d94a9}.step-dot{font-weight:600;display:flex;align-items:center;justify-content:center;box-sizing:border-box;width:20px;height:20px;border:1px solid #cbd1e4;border-radius:50%;font-size:10px;line-height:1}.step-label{font-weight:500;font-size:11px;white-space:nowrap}.active{color:var(--onboarding-accent)}.active .step-dot{border-color:var(--onboarding-accent);background:var(--onboarding-accent);color:#fff;box-shadow:0 2px 6px rgba(104,84,161,.12)}.active .step-label{font-weight:600}.complete .step-dot{background:#e6e0f4;border-color:#e6e0f4;color:#7b66a9}.complete .step-label{color:#737d98}.step-connector{height:1px;flex:1;min-width:8px;background:#d6dced}.step-connector.complete{background:#bcb0db}
.onboarding-body{min-width:0}.onboarding-footer{position:fixed;left:0;right:0;bottom:0;z-index:35;padding:22px 20px calc(env(safe-area-inset-bottom) + 18px);background:linear-gradient(180deg,rgba(237,240,251,0),rgba(237,240,251,.97) 25%,#edf0fb 100%);box-sizing:border-box}.footer-content{max-width:440px;margin:0 auto}
.onboarding-back:active{background:rgba(255,255,255,.5)}
@media(max-width:350px){.onboarding-content{padding-left:16px;padding-right:16px}.onboarding-heading{font-size:22px}.onboarding-description{font-size:11px}.onboarding-assistant{right:-4px;width:66px;height:88px}.hero-copy{padding-right:50px}.onboarding-steps{gap:6px}.step-label{font-size:10px}.step-dot{width:18px;height:18px}.onboarding-footer{padding-left:16px;padding-right:16px}}
</style>
