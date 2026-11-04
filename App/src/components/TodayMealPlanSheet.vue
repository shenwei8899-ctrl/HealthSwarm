<script setup>
import { computed, reactive, ref, watch, onUnmounted } from 'vue'
import { onShow, onHide } from '@dcloudio/uni-app'
import DailyMealPlanCard from './DailyMealPlanCard.vue'
import { todayMealPlanState,createTodayMealPlan } from '../services/today-meal-plan.js'
import { detailGesture } from '../services/meal-detail-client.js'
import { localDate } from '../utils/meal-state.js'
const props=defineProps({open:Boolean,profile:Object,busy:Boolean,unavailable:Boolean})
const emit=defineEmits(['close','plan','detail','all','dish','continue'])
const state=reactive(todayMealPlanState())
const client=createTodayMealPlan({state,onPlan:plan=>emit('plan',plan)})
const visible=ref(true)
const expanded=ref(false)
const meals=[{type:'breakfast',name:'早餐'},{type:'lunch',name:'午餐'},{type:'dinner',name:'晚餐'}]
const displayDate=computed(()=>{
 const [year,month,day]=(state.date||localDate()).split('-').map(Number)
 return `${month}月${day}日 · 周${'日一二三四五六'[new Date(year,month-1,day).getDay()]}`
})
const loadingLabel=computed(()=>state.phase==='generating'?'正在搭配今天的三餐':'正在读取今日餐单')
const actionLabels={refresh:'刷新状态',regenerate:'重新安排餐次',answer:'继续回答'}
let touch=null
function load(){
 if(!props.profile||props.unavailable){client.clear();if(props.open&&props.unavailable)state.phase='error';return}
 if(!visible.value||!props.open){client.pause();return}
 void client.open(props.profile)
}
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
function detail(item){if(state.verified&&visible.value&&props.open)emit('detail',item)}
function dish(value){if(state.verified&&visible.value&&props.open)emit('dish',value)}
function act(){
 if(props.busy||!visible.value||!props.open)return
 if(state.action==='answer')emit('continue',state.pending)
 else if(state.action==='refresh'&&props.profile)void client.open(props.profile,{readOnly:true})
 else if(state.action==='regenerate'||state.phase==='error')load()
}
watch(()=>[props.open,props.profile?.householdId,props.profile?.selfMemberId,props.profile?.familyVersion,props.unavailable],load,{immediate:true})
watch(()=>props.open,open=>{touch=null;if(open)expanded.value=false})
onHide(()=>{visible.value=false;touch=null;client.pause()})
onShow(()=>{if(!visible.value){visible.value=true;load()}})
onUnmounted(()=>client.dispose())
</script>
<template>
 <view v-if="open" class="tm-mask" @click.self="emit('close')">
  <view class="tm-sheet" :class="{'tm-expanded':expanded,'tm-paused':!visible}" role="dialog" aria-modal="true" aria-label="今日餐单" @click.stop>
   <view class="tm-handle" aria-hidden="true" @touchstart="start" @touchend="end" @touchcancel="cancelTouch"><view class="tm-grip"/></view>
   <view class="tm-header" @touchstart="start" @touchend="end" @touchcancel="cancelTouch">
    <view class="tm-heading"><text class="tm-title">今日餐单</text><text class="tm-date">{{displayDate}}</text></view>
    <view class="tm-controls" @touchstart.stop @touchend.stop><button class="tm-expand" :aria-label="expanded?'收起今日餐单':'展开今日餐单'" :aria-expanded="expanded" @click="expanded=!expanded">{{expanded?'收起':'展开'}}</button><button class="tm-close" aria-label="关闭今日餐单" @click="emit('close')"><text>×</text></button></view>
   </view>
   <scroll-view class="tm-content" scroll-y :show-scrollbar="false" :aria-busy="state.checking||state.phase==='generating'">
    <view v-if="state.plan&&state.notice" class="tm-status" role="status" aria-live="polite">
     <text>{{state.notice}}</text>
     <text v-for="(question,index) in state.pending?.status==='needs_input'?state.pending.questions:[]" :key="index" class="tm-question">{{question}}</text>
     <button v-if="state.action" class="tm-retry" :disabled="busy" @click="act">{{actionLabels[state.action]}}</button>
    </view>
    <DailyMealPlanCard v-if="state.plan" workspace detail-mode compact :plan="state.plan" :busy="busy" :interactive="state.verified&&visible&&open" @dish="dish" @detail="detail"/>
    <view v-else-if="state.phase==='error'" class="tm-error" role="status" aria-live="polite"><text class="tm-error-title">暂时无法读取餐单</text><text>{{state.notice||'请稍后重试，我们会重新核对餐单状态。'}}</text><text v-for="(question,index) in state.pending?.status==='needs_input'?state.pending.questions:[]" :key="index" class="tm-question">{{question}}</text><button class="tm-retry" :disabled="busy" @click="act">{{actionLabels[state.action]||'重新读取'}}</button></view>
    <view v-else class="tm-loading" :aria-busy="true">
     <view class="tm-loading-status" role="status" aria-live="polite"><view class="tm-pulse" aria-hidden="true"/><text>{{loadingLabel}}</text></view>
     <view class="tm-skeletons" aria-hidden="true"><view v-for="meal in meals" :key="meal.type" class="tm-skeleton-card"><view class="tm-skeleton-head"><text>{{meal.name}}</text><view class="tm-placeholder tm-skeleton-link"/></view><view class="tm-skeleton-row"><view class="tm-placeholder tm-skeleton-image"/><view class="tm-skeleton-lines"><view class="tm-placeholder tm-skeleton-line"/><view class="tm-placeholder tm-skeleton-line tm-skeleton-short"/></view></view></view></view>
    </view>
   </scroll-view>
  </view>
 </view>
</template>
<style>
/* All selectors use this component's tm- namespace; avoid repeated scope IDs in the upload. */
.tm-mask{position:fixed;inset:0;z-index:70;display:flex;align-items:flex-end;background:rgba(34,41,58,.28)}
.tm-sheet{display:flex;flex-direction:column;box-sizing:border-box;width:100%;max-width:480px;margin:0 auto;height:72vh;height:72dvh;max-height:calc(100vh - 68px);overflow:hidden;padding:0 0 env(safe-area-inset-bottom);border:1px solid rgba(255,255,255,.9);border-bottom:0;border-radius:26px 26px 0 0;color:var(--ui-text,#35343f);background-color:#fafafc;background-image:radial-gradient(ellipse at 0% 0%,rgba(159,192,249,.24),transparent 72%),radial-gradient(ellipse at 100% 0%,rgba(205,186,237,.22),transparent 75%);background-size:100% 150px;background-repeat:no-repeat;box-shadow:0 -8px 32px rgba(36,55,87,.1);transition:height 240ms cubic-bezier(.2,.7,.2,1)}
.tm-sheet.tm-expanded{height:90vh;height:90dvh}.tm-handle{height:20px;min-height:20px;display:flex;align-items:center;justify-content:center;flex-shrink:0}.tm-grip{width:30px;height:4px;border-radius:4px;background:#d0d2de}
.tm-header{display:flex;align-items:center;gap:10px;padding:4px 16px 16px 20px;flex-shrink:0}.tm-heading{flex:1;min-width:0}.tm-title{display:block;font-size:21px;font-weight:600;line-height:1.4}.tm-date{display:block;margin-top:4px;color:#74717f;font-size:12px;line-height:1.6}
.tm-controls{display:flex;align-items:center;gap:2px}.tm-expand,.tm-close{display:flex;align-items:center;justify-content:center;width:44px;height:44px;min-width:44px;margin:0;padding:0;background:transparent;color:#74717f}.tm-expand{font-size:12px}.tm-close>text{display:flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:50%;background:rgba(229,230,239,.6);font-size:24px;line-height:1}.tm-sheet button:after{border:0}
.tm-content{height:0;flex:1;min-height:0}.tm-status{margin:0 20px 12px;padding:10px 12px;border-radius:14px;background:#f0f0f7;color:#676578;font-size:13px;line-height:1.7}.tm-status>text,.tm-question{display:block;overflow-wrap:anywhere}.tm-status .tm-retry{margin:8px 0 0}
.tm-loading{padding-bottom:22px}.tm-loading-status{display:flex;align-items:center;gap:8px;margin:0 22px 14px;font-size:13px;line-height:1.7;color:#74717f}.tm-pulse{width:6px;height:6px;border-radius:50%;background:#a8a4c4;animation:tm-breathe 1.8s ease-in-out infinite;flex-shrink:0}
.tm-skeletons{padding:0 20px}.tm-skeleton-card{margin-bottom:12px;padding:10px 14px 14px;border:1px solid #eeedf3;border-radius:20px;background:#fff}.tm-skeleton-card:last-child{margin-bottom:0}.tm-skeleton-head{display:flex;align-items:center;justify-content:space-between;min-height:44px;margin-bottom:4px;font-size:16px;font-weight:600}.tm-skeleton-row{display:flex;align-items:center;gap:12px;min-height:64px;padding:4px 0}.tm-placeholder{background:#eeedf4;animation:tm-breathe 1.8s ease-in-out infinite}.tm-skeleton-link{width:46px;height:10px;border-radius:5px}.tm-skeleton-image{width:56px;height:56px;border-radius:14px;flex-shrink:0}.tm-skeleton-lines{flex:1;min-width:0}.tm-skeleton-line{width:78%;height:12px;border-radius:6px}.tm-skeleton-short{width:48%;height:9px;margin-top:12px}.tm-paused .tm-placeholder,.tm-paused .tm-pulse{animation-play-state:paused}
.tm-error{display:flex;flex-direction:column;align-items:flex-start;gap:14px;margin:8px 20px 22px;padding:22px 18px;border:1px solid #eeedf3;border-radius:20px;background:#fff;font-size:14px;line-height:1.7;color:#74717f;overflow-wrap:anywhere}.tm-error-title{font-size:16px;font-weight:500;color:#35343f}.tm-retry{display:flex;align-items:center;justify-content:center;min-height:44px;margin:0;padding:10px 16px;border-radius:14px;background:#e9e9f3;color:#514f6d;font-size:13px}
@keyframes tm-breathe{0%,100%{opacity:.55}50%{opacity:1}}
@media(max-width:350px){.tm-header{padding-left:16px;padding-right:12px}.tm-skeletons{padding:0 16px}.tm-status{margin-left:16px;margin-right:16px}.tm-loading-status{margin-left:18px}.tm-error{margin-left:16px;margin-right:16px}}
@media(max-height:480px){.tm-sheet{height:calc(100vh - 44px);max-height:calc(100vh - 44px)}.tm-header{padding-bottom:10px}}
@media(prefers-reduced-motion:reduce){.tm-sheet{transition:none}.tm-placeholder,.tm-pulse{animation:none}}
</style>
