<script setup>
import NutritionistCharacter from './NutritionistCharacter.vue'

defineProps({ state: { type: String, default: 'idle' } })
</script>

<template>
 <view class="chat-assistant-header">
  <view class="assistant-avatar"><NutritionistCharacter :size="30" unit="px" variant="avatar" :state="state" decorative/></view>
  <text class="assistant-name">家庭营养师</text>
  <text class="assistant-ai-badge">AI</text>
 </view>
</template>

<style scoped>
.chat-assistant-header{display:flex;align-items:center;gap:9px;min-height:32px;margin-bottom:12px;white-space:normal;line-height:1.4;font-weight:400}
.assistant-avatar{display:flex;align-items:center;justify-content:center;flex:none;width:32px;height:32px;box-sizing:border-box;border:1px solid rgba(255,255,255,.95);border-radius:50%;background:#f7f4fb}
.assistant-name{font-size:13px;color:#7c6c91}
.assistant-ai-badge{flex:none;padding:1px 5px;border:1px solid #e6dcf2;border-radius:6px;background:rgba(249,246,253,.8);color:#a38abf;font-size:10px;line-height:1.4}
</style>
