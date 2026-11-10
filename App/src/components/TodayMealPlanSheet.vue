<script setup>
import { computed, ref, watch } from 'vue'
import TodayMealPlanContent from './TodayMealPlanContent.vue'
import { detailGesture } from '../services/meal-detail-client.js'
import { localDate } from '../utils/meal-state.js'
const props=defineProps({open:Boolean,state:{type:Object,required:true},busy:Boolean,interactive:{type:Boolean,default:true}})
const emit=defineEmits(['close','action','detail','dish'])
const expanded=ref(false)
const displayDate=computed(()=>{
 const [year,month,day]=(props.state.date||localDate()).split('-').map(Number)
 return `${month}月${day}日 · 周${'日一二三四五六'[new Date(year,month-1,day).getDay()]}`
})
let touch=null
function start(event){const point=event.touches?.[0];touch=point?{x:point.clientX,y:point.clientY}:null}
function cancelTouch(){touch=null}
function end(event){
 const point=event.changedTouches?.[0],origin=touch;touch=null
 if(!point||!origin||Math.abs(point.clientX-origin.x)>Math.abs(point.clientY-origin.y))return
 const action=detailGesture({delta:point.clientY-origin.y,expanded:expanded.value})
 if(action==='expand')expanded.value=true
 else if(action==='collapse')expanded.value=false
 else if(action==='close')emit('close')
}
function detail(item){if(props.state.displayable&&props.interactive&&props.open)emit('detail',item)}
function dish(value){if(props.state.displayable&&props.interactive&&props.open)emit('dish',value)}
function act(){if(!props.busy&&props.interactive&&props.open)emit('action')}
watch(()=>props.open,open=>{touch=null;if(open)expanded.value=false})
</script>
<template>
 <view v-if="open" class="tm-mask" @click.self="emit('close')">
  <view class="tm-sheet" :class="{'tm-expanded':expanded,'tm-paused':!interactive}" role="dialog" aria-modal="true" aria-label="今日餐单" @click.stop>
   <view class="tm-handle" aria-hidden="true" @touchstart="start" @touchend="end" @touchcancel="cancelTouch"><view class="tm-grip"/></view>
   <view class="tm-header">
    <view class="tm-heading" @touchstart="start" @touchend="end" @touchcancel="cancelTouch"><text class="tm-title">今日餐单</text><text class="tm-date">{{displayDate}}</text></view>
    <view class="tm-controls"><button class="tm-expand" :aria-label="expanded?'收起今日餐单':'展开今日餐单'" :aria-expanded="expanded" @click="expanded=!expanded">{{expanded?'收起':'展开'}}</button><button class="tm-close" aria-label="关闭今日餐单" @click="emit('close')"><text>×</text></button></view>
   </view>
   <scroll-view class="tm-content" scroll-y :show-scrollbar="false" :aria-busy="!state.plan&&(state.checking||state.phase==='generating')">
    <TodayMealPlanContent :state="state" :busy="busy" :interactive="interactive&&open" @action="act" @detail="detail" @dish="dish"/>
   </scroll-view>
  </view>
 </view>
</template>
<style>
/* All selectors use this component's tm- namespace; avoid repeated scope IDs in the upload. */
.tm-mask{position:fixed;inset:0;z-index:70;display:flex;align-items:flex-end;background:rgba(34,41,58,.28)}
.tm-sheet{display:flex;flex-direction:column;box-sizing:border-box;width:100%;max-width:480px;margin:0 auto;height:auto;max-height:calc(100vh - 68px);overflow:hidden;padding:0 0 env(safe-area-inset-bottom);border:1px solid rgba(255,255,255,.9);border-bottom:0;border-radius:26px 26px 0 0;color:var(--ui-text,#35343f);background-color:#fafafc;background-image:radial-gradient(ellipse at 0% 0%,rgba(159,192,249,.24),transparent 72%),radial-gradient(ellipse at 100% 0%,rgba(205,186,237,.22),transparent 75%);background-size:100% 150px;background-repeat:no-repeat;box-shadow:0 -8px 32px rgba(36,55,87,.1);transition:height 240ms cubic-bezier(.2,.7,.2,1)}
.tm-sheet.tm-expanded{height:90vh;height:90dvh}.tm-handle{height:20px;min-height:20px;display:flex;align-items:center;justify-content:center;flex-shrink:0}.tm-grip{width:30px;height:4px;border-radius:4px;background:#d0d2de}
.tm-header{display:flex;align-items:center;gap:10px;padding:4px 16px 16px 20px;flex-shrink:0}.tm-heading{flex:1;min-width:0}.tm-title{display:block;font-size:21px;font-weight:600;line-height:1.4}.tm-date{display:block;margin-top:4px;color:#74717f;font-size:12px;line-height:1.6}
.tm-controls{display:flex;align-items:center;gap:2px}.tm-expand,.tm-close{display:flex;align-items:center;justify-content:center;width:44px;height:44px;min-width:44px;margin:0;padding:0;background:transparent;color:#74717f}.tm-expand{font-size:12px}.tm-close>text{display:flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:50%;background:rgba(229,230,239,.6);font-size:24px;line-height:1}.tm-sheet button:after{border:0}
.tm-content{height:auto;max-height:50vh;min-height:0}.tm-expanded .tm-content{height:0;max-height:none;flex:1}
@media(max-width:350px){.tm-header{padding-left:16px;padding-right:12px}}
@media(max-height:480px){.tm-sheet{max-height:calc(100vh - 44px)}.tm-content{max-height:calc(100vh - 150px)}.tm-header{padding-bottom:10px}}
@media(prefers-reduced-motion:reduce){.tm-sheet{transition:none}}
</style>
