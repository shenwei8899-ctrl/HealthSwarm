<script setup>
import AppIcon from './AppIcon.vue'
defineProps({prompts:{type:Array,default:()=>[]},disabled:Boolean,compact:Boolean})
defineEmits(['ask','shuffle'])
</script>
<template>
 <view class="chat-welcome" :class="{'is-compact':compact}">
  <view class="welcome-intro">
   <view class="welcome-logo" aria-hidden="true"><AppIcon name="assistant" :size="160"/></view>
   <text class="welcome-title">今天想怎么吃？</text>
   <text class="welcome-description">{{'聊聊今天怎么吃，\n也可以一起安排家人的三餐。'}}</text>
  </view>
  <view class="welcome-suggestions">
   <view class="suggestion-heading">
    <text class="suggestion-label">你可以这样问我</text>
    <button class="shuffle-prompts" :disabled="disabled" aria-label="换一换推荐问题" @click="$emit('shuffle')"><text class="refresh-icon" aria-hidden="true">↻</text><text>换一换</text></button>
   </view>
   <view class="prompt-grid"><button v-for="(prompt,index) in prompts" :key="index" :disabled="disabled" @click="$emit('ask',prompt)">{{prompt.text}}</button></view>
   <text class="welcome-note">内容由 AI 生成，仅供参考</text>
  </view>
 </view>
</template>
<style scoped>
/* Keep content in normal flow: a viewport-based minimum used to push prompts below the composer. */
.chat-welcome{box-sizing:border-box;display:flex;flex-direction:column;gap:36px;padding:60px 0 8px;color:#161616}
.chat-welcome.is-compact{padding:20px 0 8px;gap:20px}.is-compact .welcome-logo{display:none}.is-compact .welcome-title{font-size:22px}.is-compact .welcome-description{margin-top:10px}
.welcome-intro{display:flex;flex-direction:column;align-items:center;text-align:center}.welcome-logo{display:flex;align-items:center;justify-content:center;width:160rpx;height:160rpx;color:#111;margin-bottom:32px}.welcome-title{display:block;font-size:25px;font-weight:500;line-height:1.45;letter-spacing:.1px}.welcome-description{display:block;margin-top:16px;white-space:pre-line;font-size:15px;line-height:1.85;color:#858585}
.welcome-suggestions{width:100%;text-align:center}.suggestion-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:44px;margin-bottom:8px}.suggestion-label{display:block;color:#8b8b8b;font-size:13px;text-align:left}.shuffle-prompts{display:inline-flex;align-items:center;justify-content:center;gap:5px;flex-shrink:0;min-height:44px;margin:0;padding:0 2px 0 10px;border:0;background:transparent;color:#8b8b8b;font-size:12px;line-height:1.5;font-weight:400;box-shadow:none}.shuffle-prompts:after{border:0}.shuffle-prompts:active{color:#555}.refresh-icon{font-size:17px;line-height:1}.prompt-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:8px}.prompt-grid button{display:flex;align-items:center;justify-content:flex-start;width:100%;height:52px;min-height:52px;box-sizing:border-box;padding:5px 10px;border:1px solid #e2e2e2;border-radius:8px;background:#fff;text-align:left;font-size:15px;line-height:20px;font-weight:400;color:#242424;white-space:normal;overflow-wrap:anywhere}.prompt-grid button:after{border:0}.prompt-grid button[disabled]{color:#999}.welcome-note{display:block;margin-top:12px;font-size:11px;color:#929292;line-height:1.7;letter-spacing:.5px}
@media(max-height:720px){.chat-welcome{padding-top:16px;gap:20px}.welcome-logo{margin-bottom:16px}.welcome-title{font-size:23px}.welcome-description{margin-top:12px;font-size:14px;line-height:1.7}.suggestion-heading{margin-bottom:4px}}
@media(max-height:660px){.chat-welcome{padding-top:8px;gap:12px;padding-bottom:4px}.welcome-logo{width:96rpx;height:96rpx;margin-bottom:10px}.welcome-logo :deep(.app-icon){width:96rpx!important;height:96rpx!important}.welcome-description{margin-top:8px;line-height:1.6}.welcome-note{margin-top:8px}}
@media(max-width:350px){.welcome-title{font-size:21px}.welcome-description{font-size:14px}.prompt-grid button{font-size:14px;padding:5px 8px}.welcome-note{font-size:11px}}
</style>
