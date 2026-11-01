<script setup>
import { reactive, ref, watch, onUnmounted } from 'vue'
import { onShow, onHide } from '@dcloudio/uni-app'
import DailyMealPlanCard from './DailyMealPlanCard.vue'
import MealLoadingMotion from './MealLoadingMotion.vue'
import { todayMealPlanState,createTodayMealPlan } from '../services/today-meal-plan.js'
const props=defineProps({open:Boolean,profile:Object,busy:Boolean,unavailable:Boolean})
const emit=defineEmits(['close','plan','detail','purchase','all'])
const state=reactive(todayMealPlanState())
const client=createTodayMealPlan({state,onPlan:plan=>emit('plan',plan)})
const visible=ref(true)
function load(){if(visible.value&&props.open&&props.profile)void client.open(props.profile);else{client.clear();if(props.open&&props.unavailable)state.phase='error'}}
watch(()=>[props.open,props.profile?.householdId,props.profile?.selfMemberId,props.profile?.familyVersion,props.unavailable],load,{immediate:true})
onHide(()=>{visible.value=false;client.pause()})
onShow(()=>{if(!visible.value){visible.value=true;load()}})
onUnmounted(()=>client.dispose())
</script>
<template>
 <view v-if="open" class="tm-mask" @click.self="emit('close')">
  <view class="tm-sheet" role="dialog" aria-modal="true" aria-label="今日餐单">
   <view class="tm-grip" aria-hidden="true"/>
   <view class="tm-header"><view><text class="tm-title">今日餐单</text><text class="tm-date">{{state.date}} · 好好吃饭，轻松安排</text></view><text v-if="state.issue&&state.plan" class="tm-issue" role="img" aria-label="餐单更新未完成">!</text><button class="tm-close" aria-label="关闭今日餐单" @click="emit('close')">×</button></view>
   <scroll-view v-if="state.phase==='ready'&&state.plan" class="tm-content" scroll-y :show-scrollbar="false">
    <DailyMealPlanCard workspace detail-mode :plan="state.plan" :busy="busy" @detail="emit('detail',$event)" @purchase="emit('purchase',$event)"/>
   </scroll-view>
   <view v-else class="tm-center" aria-live="polite">
    <text v-if="state.phase==='error'" class="tm-issue" role="img" aria-label="餐单未完成">!</text>
    <view v-else class="tm-loading" :class="{'tm-paused':!visible}" role="status">
     <MealLoadingMotion :active="visible&&open"/>
     <view class="tm-copy"><text>{{state.phase==='generating'?'正在安排今天的三餐':state.label}}</text><view class="tm-dots" aria-hidden="true"><text>·</text><text>·</text><text>·</text></view></view><text class="tm-note">{{state.phase==='generating'?'为你搭配一日饮食':'好好吃饭，轻松安排'}}</text>
    </view>
   </view>
   <view v-if="state.phase==='ready'&&state.plan?.purchase_options?.length" class="tm-footer"><view><text>一天所需，一起准备</text><text class="tm-buy-note">先核对食材与配送，再确认下单</text></view><button :disabled="busy" @click="emit('all')">一键购买 ↗</button></view>
  </view>
 </view>
</template>
<style>
/* All selectors use this component's tm- namespace; avoid repeated scope IDs in the upload. */
.tm-mask{position:fixed;inset:0;z-index:70;display:flex;align-items:flex-end;background:rgba(34,41,58,.34)}
.tm-sheet{display:flex;flex-direction:column;box-sizing:border-box;width:100%;max-width:480px;margin:0 auto;height:90vh;height:90dvh;max-height:calc(100vh - 68px);overflow:hidden;padding:0 0 env(safe-area-inset-bottom);border:1px solid rgba(255,255,255,.94);border-bottom:0;border-radius:32px 32px 0 0;color:#293a52;background-color:#fff;background-image:radial-gradient(ellipse at 0% 0%,rgba(125,174,255,.65),rgba(125,174,255,0) 72%),radial-gradient(ellipse at 100% 0%,rgba(206,178,245,.55),rgba(206,178,245,0) 75%),linear-gradient(180deg,#dfecff,#fff);background-size:100% 320px,100% 320px,100% 100%;background-repeat:no-repeat;box-shadow:0 -10px 36px rgba(36,55,87,.16)}
.tm-grip{width:30px;height:4px;margin:10px auto 0;border-radius:4px;background:#b0bed9;flex-shrink:0}
.tm-header{display:flex;align-items:center;gap:12px;padding:20px 22px 24px;border-bottom:1px solid rgba(255,255,255,.65);flex-shrink:0}
.tm-header>view{flex:1;min-width:0}.tm-title{display:block;font-size:26px;font-weight:600;line-height:1.4;letter-spacing:.5px}.tm-date{display:block;margin-top:8px;color:#667994;font-size:12px;line-height:1.7}
.tm-close{display:flex;align-items:center;justify-content:center;width:44px;height:44px;min-width:44px;min-height:44px;margin:0;padding:0;border:1px solid #fff;border-radius:50%;background:rgba(255,255,255,.84);color:#62768f;font-size:28px;line-height:1}.tm-close:after,.tm-footer button:after{border:0}
.tm-content{height:0;flex:1;min-height:0;padding-top:20px}.tm-center{flex:1;min-height:0;display:flex;align-items:center;justify-content:center;padding:20px}.tm-loading{text-align:center;padding-bottom:18px;max-width:100%}
.tm-issue{display:flex;align-items:center;justify-content:center;flex-shrink:0;width:24px;height:24px;line-height:24px;border-radius:50%;background:#d83a3a;color:#fff;font-size:18px;font-weight:600}.tm-header .tm-issue{width:18px;height:18px;font-size:13px;line-height:18px}

.tm-copy{position:relative;display:inline-flex;font-size:18px;line-height:1.6;font-weight:500}.tm-dots{position:absolute;right:-20px;display:flex;color:#8c9cc9;letter-spacing:1px}.tm-dots>text{opacity:.3;animation:tm-dot 1.2s ease-in-out infinite}.tm-dots>text:nth-child(2){animation-delay:.2s}.tm-dots>text:nth-child(3){animation-delay:.4s}.tm-paused .tm-dots>text{animation-play-state:paused}.tm-note{display:block;margin-top:9px;font-size:13px;line-height:1.7;color:#7b8ba2;letter-spacing:.4px}
.tm-footer{display:flex;align-items:center;gap:10px;flex-shrink:0;padding:15px 20px;background:rgba(255,255,255,.95);border-top:1px solid #e3eaf5}.tm-footer>view{flex:1;min-width:0}.tm-footer>view>text{display:block;font-size:14px;font-weight:500}.tm-footer .tm-buy-note{margin-top:4px;font-size:11px;font-weight:400;color:#7b889a}.tm-footer button{min-height:44px;padding:11px 17px;border-radius:24px;background:#e5edfa;color:#456386;font-size:14px;font-weight:500}
@keyframes tm-dot{0%,70%,100%{opacity:.3}35%{opacity:1}}
@media(max-width:350px){.tm-header{padding:17px 18px 20px}.tm-title{font-size:24px}.tm-footer{padding-left:18px;padding-right:18px}.tm-footer button{padding:10px 12px}}
@media(max-height:480px){.tm-sheet{height:calc(100vh - 44px);max-height:calc(100vh - 44px)}.tm-header{padding-top:8px;padding-bottom:10px}.tm-loading{padding-bottom:0}}
@media(prefers-reduced-motion:reduce){.tm-dots>text{animation:none;opacity:.6}}
</style>
