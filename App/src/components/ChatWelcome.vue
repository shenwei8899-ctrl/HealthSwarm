<script setup>
import NutritionistCharacter from './NutritionistCharacter.vue'
defineProps({prompts:{type:Array,default:()=>[]},disabled:Boolean,compact:Boolean,density:String})
defineEmits(['ask','shuffle'])
</script>
<template>
 <view class="chat-welcome" :class="[{'is-compact':compact},density?'density-'+density:'']">
  <view class="welcome-intro">
   <view v-if="!compact" class="welcome-logo" aria-hidden="true"><NutritionistCharacter :size="density==='small'?64:density==='medium'?76:88" decorative/></view>
   <text class="welcome-title">你好，我是家庭营养师。</text>
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
.chat-welcome{box-sizing:border-box;display:flex;flex-direction:column;gap:36px;padding:46px 4px 12px;color:var(--ui-text)}.welcome-intro{display:flex;flex-direction:column;align-items:center;text-align:center}.welcome-logo{display:flex;align-items:center;justify-content:center;width:88px;height:88px;margin-bottom:24px}.welcome-title{display:block;font-size:24px;font-weight:500;line-height:1.5;letter-spacing:.3px}.welcome-description{display:block;margin-top:14px;white-space:pre-line;font-size:15px;line-height:1.85;color:var(--ui-muted)}
.welcome-suggestions{width:100%}.suggestion-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:44px;margin-bottom:8px}.suggestion-label{color:var(--ui-muted);font-size:12px}.shuffle-prompts{display:inline-flex;align-items:center;justify-content:center;gap:5px;flex-shrink:0;min-height:44px;margin:0;padding:0 4px 0 10px;border:0;background:transparent;color:var(--ui-muted);font-size:12px;line-height:1.5;font-weight:400}.shuffle-prompts:after{border:0}.refresh-icon{font-size:16px;line-height:1}.prompt-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px}.prompt-grid button{display:flex;align-items:center;justify-content:flex-start;width:100%;height:62px;min-height:62px;box-sizing:border-box;margin:0;padding:10px 14px;border:0;border-radius:16px;background:var(--ui-surface);text-align:left;font-size:14px;line-height:1.65;font-weight:400;color:var(--ui-text);white-space:normal;overflow-wrap:anywhere}.prompt-grid button:after{border:0}.prompt-grid button:active{background:var(--ui-accent-soft)}.prompt-grid button[disabled]{opacity:.5}.welcome-note{display:block;margin-top:16px;text-align:center;font-size:11px;color:var(--ui-muted);line-height:1.7}
.chat-welcome.is-compact{padding-top:20px;gap:20px}.is-compact .welcome-logo{display:none}.is-compact .welcome-title{font-size:22px}.is-compact .welcome-description{margin-top:10px}
.chat-welcome.density-medium{padding-top:22px;gap:24px}.density-medium .welcome-logo{margin-bottom:18px;width:76px;height:76px}.chat-welcome.density-small{padding-top:8px;gap:14px}.density-small .welcome-logo{width:56px;height:56px;margin-bottom:12px}.density-small .welcome-title{font-size:21px}.density-small .welcome-description{margin-top:8px;font-size:14px;line-height:1.65}.density-small .prompt-grid button{height:54px;min-height:54px}.density-small .welcome-note{margin-top:10px}
@media(max-width:350px){.welcome-title{font-size:21px}.prompt-grid button{font-size:13px;padding:8px 11px}}@media(max-height:660px){.chat-welcome:not([class*="density-"]){padding-top:8px;gap:14px}}
</style>
