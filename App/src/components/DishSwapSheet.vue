<script setup>
import FoodImageSlot from './FoodImageSlot.vue'
import { dishTitle, recipeDisplay } from '../utils/meal-presentation.js'
import { recipeCover } from '../utils/recipe-cover.js'
import { recipeTime } from '../utils/dish-commerce-presentation.js'
defineProps({state:{type:Object,required:true}})
defineEmits(['close','choose'])
</script>
<template>
 <view v-if="state.open" class="swap-mask" @click.self="$emit('close')">
  <view class="swap-sheet" role="dialog" aria-modal="true" aria-label="选择替换菜品">
   <view class="swap-heading"><view><text class="swap-title">换一道菜</text><text class="swap-subtitle">替换「{{dishTitle(state.target?.dish)}}」</text></view><button class="swap-close" :disabled="state.busy" aria-label="关闭换菜" @click="$emit('close')">×</button></view>
   <scroll-view scroll-y class="swap-options">
    <view v-for="candidate in state.target?.candidates||[]" :key="candidate.candidate_id" class="swap-candidate">
     <FoodImageSlot :src="recipeCover(candidate.dish)?.image_url" :label="dishTitle(candidate.dish)" :width="76" :height="76" :radius="14"/>
     <view class="swap-copy"><text class="swap-name">{{dishTitle(candidate.dish)}}</text><text class="swap-ingredients">{{recipeDisplay(candidate.dish).ingredients.slice(0,4).join('、')}}</text><view v-if="candidate.dish.tags?.length" class="swap-tags"><text v-for="tag in candidate.dish.tags" :key="tag">{{tag}}</text></view><text class="swap-time">{{recipeTime(candidate.dish)}}</text></view>
     <button class="swap-choose" :disabled="state.busy||!!state.selected&&state.selected!==candidate.candidate_id" @click="$emit('choose',candidate)">{{state.busy&&state.selected===candidate.candidate_id?'保存中':state.selected===candidate.candidate_id?'重试替换':'选这道'}}</button>
    </view>
   </scroll-view>
   <text v-if="state.error" class="swap-error" role="alert">{{state.error}}</text>
   <text class="swap-note">只替换这道菜，本餐其他菜品保持不变</text>
  </view>
 </view>
</template>
<style scoped>
.swap-mask{position:fixed;inset:0;z-index:1600;background:rgba(30,34,40,.3);display:flex;align-items:flex-end}.swap-sheet{width:100%;max-height:85vh;box-sizing:border-box;padding:24px 20px calc(22px + env(safe-area-inset-bottom));border-radius:26px 26px 0 0;background:var(--ui-surface,#fff);color:var(--ui-text,#303739)}.swap-heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}.swap-title{display:block;font-size:21px;font-weight:600}.swap-subtitle{display:block;margin-top:7px;font-size:13px;color:var(--ui-muted,#74717f);overflow-wrap:anywhere}.swap-close{flex-shrink:0;min-width:44px;margin:0;padding:0;background:transparent;font-size:28px;line-height:44px;color:inherit}.swap-options{max-height:56vh}.swap-candidate{display:flex;align-items:center;gap:12px;padding:16px 0;border-top:1px solid var(--ui-line,#eeedf3)}.swap-copy{flex:1;min-width:0}.swap-name{display:block;font-size:16px;font-weight:600;line-height:1.5;overflow-wrap:anywhere}.swap-ingredients,.swap-time{display:block;margin-top:6px;font-size:12px;line-height:1.6;color:var(--ui-muted,#74717f)}.swap-tags{display:flex;flex-wrap:wrap;gap:5px;margin-top:7px}.swap-tags text{padding:2px 6px;border-radius:5px;background:#f1f3ee;color:#56614d;font-size:11px}.swap-choose{flex-shrink:0;margin:0;padding:0 10px;min-height:44px;line-height:44px;border-radius:12px;background:var(--ui-accent,#303739);color:#fff;font-size:13px}.swap-sheet button:after{border:0}.swap-sheet button[disabled]{opacity:.45}.swap-error{display:block;margin-top:12px;color:#a34c39;font-size:13px;line-height:1.6}.swap-note{display:block;margin-top:16px;font-size:12px;line-height:1.6;text-align:center;color:var(--ui-muted,#74717f)}
@media(min-width:680px){.swap-sheet{max-width:560px;margin:0 auto}}@media(max-width:350px){.swap-sheet{padding-left:14px;padding-right:14px}.swap-candidate{gap:8px}.swap-choose{padding:0 8px}}
</style>
