<script setup>
import { computed } from 'vue'
import DailyMealPlanCard from './DailyMealPlanCard.vue'
import { localDate } from '../utils/meal-state.js'

const props = defineProps({ state: { type: Object, required: true }, busy: Boolean, heading: Boolean, interactive: { type: Boolean, default: true } })
const emit = defineEmits(['action', 'detail', 'dish'])
const meals = [{type:'breakfast',name:'早餐'},{type:'lunch',name:'午餐'},{type:'dinner',name:'晚餐'}]
const displayDate = computed(() => {
 const [year, month, day] = (props.state.date || localDate()).split('-').map(Number)
 return `${month}月${day}日 · 周${'日一二三四五六'[new Date(year,month-1,day).getDay()]}`
})
const loadingLabel = computed(() => props.state.label)
const actionLabels = {refresh:'刷新状态',regenerate:'重新安排餐次',answer:'继续回答',candidates:'查看待核对候选'}
function detail(item) { if (props.state.verified && props.interactive) emit('detail', item) }
function dish(value) { if (props.state.verified && props.interactive) emit('dish', value) }
function act() { if (!props.busy && props.interactive) emit('action') }
</script>
<template>
 <view class="tm-body" :class="{'tm-inline':heading,'tm-body-paused':!interactive}">
  <view v-if="heading" class="tm-inline-heading"><text class="tm-inline-title">今日餐单</text><text class="tm-inline-date">{{displayDate}}</text></view>
    <view v-if="state.plan&&state.notice" class="tm-status" role="status" aria-live="polite">
     <text>{{state.notice}}</text>
     <text v-for="(question,index) in state.pending?.status==='needs_input'?state.pending.questions:[]" :key="index" class="tm-question">{{question}}</text>
     <button v-if="state.action" class="tm-retry" :disabled="busy" @click="act">{{actionLabels[state.action]}}</button>
    </view>
    <DailyMealPlanCard v-if="state.plan" workspace detail-mode compact :plan="state.plan" :busy="busy" :interactive="state.verified&&interactive" @dish="dish" @detail="detail"/>
    <view v-else-if="state.phase==='error'" class="tm-error" role="status" aria-live="polite"><text class="tm-error-title">{{state.pending?.status==='reference_candidates'?'待核对候选':'暂时无法读取餐单'}}</text><text>{{state.notice||'请稍后重试，我们会重新核对餐单状态。'}}</text><text v-for="(question,index) in state.pending?.status==='needs_input'?state.pending.questions:[]" :key="index" class="tm-question">{{question}}</text><button class="tm-retry" :disabled="busy" @click="act">{{actionLabels[state.action]||'重新读取'}}</button></view>
    <view v-else class="tm-loading" :aria-busy="true">
     <view class="tm-loading-status" role="status" aria-live="polite"><view class="tm-pulse" aria-hidden="true"/><text>{{loadingLabel}}</text></view>
     <view class="tm-skeletons" aria-hidden="true"><view v-for="meal in meals" :key="meal.type" class="tm-skeleton-card"><view class="tm-skeleton-head"><text>{{meal.name}}</text><view class="tm-placeholder tm-skeleton-link"/></view><view class="tm-skeleton-row"><view class="tm-placeholder tm-skeleton-image"/><view class="tm-skeleton-lines"><view class="tm-placeholder tm-skeleton-line"/><view class="tm-placeholder tm-skeleton-line tm-skeleton-short"/></view></view></view></view>
    </view>
 </view>
</template>
<style>
.tm-status{margin:0 20px 12px;padding:10px 12px;border-radius:14px;background:#f0f0f7;color:#676578;font-size:13px;line-height:1.7}.tm-status>text,.tm-question{display:block;overflow-wrap:anywhere}.tm-status .tm-retry{margin:8px 0 0}
.tm-loading{padding-bottom:22px}.tm-loading-status{display:flex;align-items:center;gap:8px;margin:0 22px 14px;font-size:13px;line-height:1.7;color:#74717f}.tm-pulse{width:6px;height:6px;border-radius:50%;background:#a8a4c4;animation:tm-breathe 1.8s ease-in-out infinite;flex-shrink:0}
.tm-skeletons{padding:0 20px}.tm-skeleton-card{margin-bottom:12px;padding:10px 14px 14px;border:1px solid #eeedf3;border-radius:20px;background:#fff}.tm-skeleton-card:last-child{margin-bottom:0}.tm-skeleton-head{display:flex;align-items:center;justify-content:space-between;min-height:44px;margin-bottom:4px;font-size:16px;font-weight:600}.tm-skeleton-row{display:flex;align-items:center;gap:12px;min-height:64px;padding:4px 0}.tm-placeholder{background:#eeedf4;animation:tm-breathe 1.8s ease-in-out infinite}.tm-skeleton-link{width:46px;height:10px;border-radius:5px}.tm-skeleton-image{width:56px;height:56px;border-radius:14px;flex-shrink:0}.tm-skeleton-lines{flex:1;min-width:0}.tm-skeleton-line{width:78%;height:12px;border-radius:6px}.tm-skeleton-short{width:48%;height:9px;margin-top:12px}.tm-body-paused .tm-placeholder,.tm-body-paused .tm-pulse{animation-play-state:paused}
.tm-error{display:flex;flex-direction:column;align-items:flex-start;gap:14px;margin:8px 20px 22px;padding:22px 18px;border:1px solid #eeedf3;border-radius:20px;background:#fff;font-size:14px;line-height:1.7;color:#74717f;overflow-wrap:anywhere}.tm-error-title{font-size:16px;font-weight:500;color:#35343f}.tm-retry{display:flex;align-items:center;justify-content:center;min-height:44px;margin:0;padding:10px 16px;border-radius:14px;background:#e9e9f3;color:#514f6d;font-size:13px}
@keyframes tm-breathe{0%,100%{opacity:.55}50%{opacity:1}}
@media(max-width:350px){.tm-skeletons{padding:0 16px}.tm-status{margin-left:16px;margin-right:16px}.tm-loading-status{margin-left:18px}.tm-error{margin-left:16px;margin-right:16px}}

@media(prefers-reduced-motion:reduce){.tm-placeholder,.tm-pulse{animation:none}}

.tm-inline{margin:8px -20px 16px}.tm-inline-heading{display:flex;align-items:baseline;justify-content:space-between;gap:12px;padding:8px 22px 16px}.tm-inline-title{font-size:20px;font-weight:600;line-height:1.4;color:var(--ui-text,#35343f)}.tm-inline-date{font-size:12px;line-height:1.6;color:#74717f}.tm-body button:after{border:0}
</style>
