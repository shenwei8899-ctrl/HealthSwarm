<script setup>
import NutritionistCharacter from './NutritionistCharacter.vue'
defineProps({prompts:{type:Array,default:()=>[]},disabled:Boolean,shuffleDisabled:Boolean,compact:Boolean,density:String,refined:Boolean})
defineEmits(['ask','shuffle'])
</script>
<template>
 <view class="chat-welcome" :class="[{'is-compact':compact,'is-refined':refined},density?'density-'+density:'']">
  <view class="welcome-intro">
   <view v-if="!compact" class="welcome-logo" aria-hidden="true"><NutritionistCharacter :size="refined?(density==='small'?104:density==='medium'?136:160):(density==='small'?88:density==='medium'?112:128)" decorative/></view>
   <text class="welcome-title">你好，我是家庭营养师。</text>
   <text class="welcome-description">{{'聊聊今天怎么吃，\n也可以一起安排家人的三餐。'}}</text>
  </view>
  <view class="welcome-suggestions">
   <view class="suggestion-heading">
    <text class="suggestion-label">你可以这样问我</text>
    <button class="shuffle-prompts" :disabled="shuffleDisabled" aria-label="换一换推荐问题" @click="$emit('shuffle')"><text class="refresh-icon" aria-hidden="true">↻</text><text>换一换</text></button>
   </view>
   <view class="prompt-grid"><button v-for="(prompt,index) in prompts" :key="index" :disabled="disabled" @click="$emit('ask',prompt)">{{prompt.text}}</button></view>
  </view>
 </view>
</template>
<style scoped>
.chat-welcome{box-sizing:border-box;display:flex;flex-direction:column;gap:36px;padding:46px 4px 12px;color:var(--ui-text)}.welcome-intro{display:flex;flex-direction:column;align-items:center;text-align:center}.welcome-logo{display:flex;align-items:center;justify-content:center;width:128px;height:128px;margin-bottom:16px}.welcome-title{display:block;font-size:24px;font-weight:500;line-height:1.5;letter-spacing:.3px}.welcome-description{display:block;margin-top:14px;white-space:pre-line;font-size:15px;line-height:1.85;color:var(--ui-muted)}
.welcome-suggestions{width:100%}.suggestion-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:44px;margin-bottom:8px}.suggestion-label{color:var(--ui-muted);font-size:12px}.shuffle-prompts{display:inline-flex;align-items:center;justify-content:center;gap:5px;flex-shrink:0;min-height:44px;margin:0;padding:0 4px 0 10px;border:0;background:transparent;color:var(--ui-muted);font-size:12px;line-height:1.5;font-weight:400}.shuffle-prompts:after{border:0}.refresh-icon{font-size:16px;line-height:1}.prompt-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:10px}.prompt-grid button{display:flex;align-items:center;justify-content:flex-start;width:100%;height:62px;min-height:62px;box-sizing:border-box;margin:0;padding:10px 14px;border:0;border-radius:16px;background:var(--ui-surface);text-align:left;font-size:14px;line-height:1.65;font-weight:400;color:var(--ui-text);white-space:nowrap}.prompt-grid button:after{border:0}.prompt-grid button:active{background:var(--ui-accent-soft)}.prompt-grid button[disabled]{opacity:.5}
.chat-welcome.is-compact{padding-top:20px;gap:20px}.is-compact .welcome-logo{display:none}.is-compact .welcome-title{font-size:22px}.is-compact .welcome-description{margin-top:10px}
.chat-welcome.density-medium{padding-top:22px;gap:24px}.density-medium .welcome-logo{margin-bottom:16px;width:112px;height:112px}.chat-welcome.density-small{padding-top:8px;gap:14px}.density-small .welcome-logo{width:88px;height:88px;margin-bottom:12px}.density-small .welcome-title{font-size:21px}.density-small .welcome-description{margin-top:8px;font-size:14px;line-height:1.65}.density-small .prompt-grid button{height:54px;min-height:54px}
@media(max-width:350px){.welcome-title{font-size:21px}.prompt-grid button{font-size:13px;padding:8px 10px}}@media(max-height:660px){.chat-welcome:not([class*="density-"]){padding-top:8px;gap:14px}}

/* Only the home slot opts into these refinements. */
.chat-welcome.is-refined{min-height:100%;padding:24px 4px 18px;gap:32px}
.is-refined .welcome-intro{flex:1;justify-content:center}
.is-refined .welcome-suggestions{flex-shrink:0}
.is-refined .welcome-title{color:#575268;font-size:22px;font-weight:500;letter-spacing:.2px}
.is-refined .welcome-description{margin-top:14px;color:#77717f;font-size:14px;line-height:1.9}
.is-refined .welcome-logo{width:160px;height:160px;flex-shrink:0;margin-bottom:24px}
.is-refined .suggestion-label,.is-refined .shuffle-prompts{color:#92899f}
.is-refined .prompt-grid button{border:1px solid #eeebf6;background:rgba(255,255,255,.92);border-radius:18px;color:#746d84;box-shadow:0 3px 12px rgba(117,96,155,.025)}
.is-refined .prompt-grid button:active{background:#f5f1fc}

.chat-welcome.is-refined.density-medium{padding-top:4px;padding-bottom:10px;gap:8px}
.is-refined.density-medium .prompt-grid button{height:54px;min-height:54px}
.is-refined.density-medium .welcome-logo{width:136px;height:136px;margin-bottom:12px}
.is-refined.density-medium .welcome-description{margin-top:8px;line-height:1.65}
.chat-welcome.is-refined.density-small{padding-top:14px;gap:16px}
.is-refined.density-small .welcome-logo{width:104px;height:104px;margin-bottom:16px}
.is-refined.density-small .welcome-title{font-size:21px}
.is-refined.density-small .welcome-description{margin-top:10px;line-height:1.75}
@media(max-width:350px){.is-refined .welcome-title{font-size:20px}}

.chat-welcome.is-refined.density-small{padding:4px 4px 8px;gap:8px}
.is-refined.density-small .welcome-logo{width:88px;height:88px;margin-bottom:8px}
.is-refined.density-small .welcome-description{margin-top:6px;font-size:13px;line-height:1.55}
</style>
