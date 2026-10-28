<script setup>
import AppIcon from './AppIcon.vue'
defineProps({prompts:{type:Array,default:()=>[]},disabled:Boolean})
defineEmits(['ask','today'])
</script>
<template>
 <view class="chat-welcome">
  <view class="welcome-intro">
   <view class="welcome-logo" aria-hidden="true"><AppIcon name="assistant" :size="160"/></view>
   <text class="welcome-title">今天想怎么吃？</text>
   <text class="welcome-description">{{'我是你的家庭营养师，\n聊聊想吃的、忌口的，一起把三餐安排好。'}}</text>
   <button class="welcome-today" @click="$emit('today')"><text>查看今日安排</text><text aria-hidden="true">→</text></button>
  </view>
  <view class="welcome-suggestions">
   <text class="suggestion-label">从一个问题开始</text>
   <view class="prompt-grid"><button v-for="prompt in prompts" :key="prompt" :disabled="disabled" @click="$emit('ask',prompt)">{{prompt}}</button></view>
   <text class="welcome-note">内容由 AI 生成，仅供参考</text>
  </view>
 </view>
</template>
<style scoped>
.chat-welcome{min-height:calc(100vh - 228px);min-height:calc(100dvh - 228px);box-sizing:border-box;display:flex;flex-direction:column;justify-content:space-between;gap:48px;padding:72px 0 8px;color:#161616}
.welcome-intro{display:flex;flex-direction:column;align-items:center;text-align:center}.welcome-logo{display:flex;align-items:center;justify-content:center;width:160rpx;height:160rpx;color:#111;margin-bottom:36px}.welcome-title{display:block;font-size:25px;font-weight:500;line-height:1.45;letter-spacing:.1px}.welcome-description{display:block;margin-top:16px;white-space:pre-line;font-size:15px;line-height:1.85;color:#858585}.welcome-today{display:flex;align-items:center;justify-content:center;gap:14px;min-height:44px;margin-top:14px;padding:4px 16px;background:transparent;color:#434343;font-size:14px}.welcome-today:after{border:0}
.welcome-suggestions{width:100%;text-align:center}.suggestion-label{display:block;margin-bottom:16px;color:#8b8b8b;font-size:13px}.prompt-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px}.prompt-grid button{display:flex;align-items:center;justify-content:flex-start;width:100%;min-height:48px;box-sizing:border-box;padding:11px 13px;border:1px solid #e2e2e2;border-radius:8px;background:#fff;text-align:left;font-size:15px;line-height:1.55;font-weight:400;color:#242424;white-space:normal}.prompt-grid button:after{border:0}.prompt-grid button[disabled]{color:#999}.welcome-note{display:block;margin-top:24px;font-size:11px;color:#929292;line-height:1.7;letter-spacing:.5px}
@media(max-height:720px){.chat-welcome{padding-top:28px;gap:30px}.welcome-logo{margin-bottom:22px}.welcome-title{font-size:23px}.welcome-description{margin-top:12px;font-size:14px;line-height:1.7}.welcome-today{margin-top:8px}.suggestion-label{margin-bottom:12px}.welcome-note{margin-top:15px}.prompt-grid button{min-height:44px;padding:9px 11px}}
@media(max-width:350px){.welcome-title{font-size:21px}.welcome-description{font-size:14px}.prompt-grid{gap:8px}.prompt-grid button{font-size:14px;padding:10px}.welcome-note{font-size:11px}}
</style>
