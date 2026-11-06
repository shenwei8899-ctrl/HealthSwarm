<script setup>
import { computed } from 'vue'
import AppIcon from './AppIcon.vue'
import { localDate } from '../utils/meal-state.js'

const props = defineProps({ state: { type: Object, required: true }, busy: Boolean, heading: Boolean, interactive: { type: Boolean, default: true } })
const emit = defineEmits(['action', 'detail', 'dish'])
const meals = [
 {type:'breakfast',name:'早餐',icon:'sunrise'},
 {type:'lunch',name:'午餐',icon:'sun'},
 {type:'dinner',name:'晚餐',icon:'moon-stars'},
]
const displayDate = computed(() => {
 const [year, month, day] = (props.state.date || localDate()).split('-').map(Number)
 return `${month}月${day}日 · 周${'日一二三四五六'[new Date(year,month-1,day).getDay()]}`
})
const loadingLabel = computed(() => props.state.label)
const actionLabels = {refresh:'刷新状态',regenerate:'重新安排餐次',answer:'继续回答',candidates:'查看待核对候选'}
const mealEntries = computed(() => meals.map(meal => ({ ...meal,
 item: props.state.plan?.meals.find(item => item.meal_type === meal.type && item.meal?.dishes?.length),
})))
const missingMeals = computed(() => mealEntries.value.filter(meal => !meal.item).map(meal => meal.name).join('、'))
function detail(item) { if (item && props.state.verified && props.interactive) emit('detail', item) }
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
    <view class="tm-meal-entries" :aria-busy="state.checking||state.phase==='generating'">
     <button v-for="meal in mealEntries" :key="meal.type" class="tm-meal-entry" :disabled="!meal.item||!state.verified||!interactive" :aria-label="'查看'+meal.name+'安排'" @click="detail(meal.item)">
      <view class="tm-meal-symbol" :class="'tm-symbol-'+meal.type" aria-hidden="true"><view class="tm-meal-glyph"><AppIcon :name="meal.icon" :size="44"/></view></view>
      <text>{{meal.name}}</text>
     </button>
    </view>
    <text v-if="state.plan&&missingMeals" class="tm-missing">{{missingMeals}}尚未安排</text>
    <view v-if="!state.plan&&state.phase==='error'" class="tm-error" role="status" aria-live="polite"><text class="tm-error-title">{{state.pending?.status==='reference_candidates'?'待核对候选':'暂时无法读取餐单'}}</text><text>{{state.notice||'请稍后重试，我们会重新核对餐单状态。'}}</text><text v-for="(question,index) in state.pending?.status==='needs_input'?state.pending.questions:[]" :key="index" class="tm-question">{{question}}</text><button class="tm-retry" :disabled="busy" @click="act">{{actionLabels[state.action]||'重新读取'}}</button></view>
    <view v-else-if="!state.plan" class="tm-loading" :aria-busy="true">
     <view class="tm-loading-status" role="status" aria-live="polite"><view class="tm-pulse" aria-hidden="true"/><text>{{loadingLabel}}</text></view>
    </view>
 </view>
</template>
<style>
.tm-body{padding:0 20px 20px;color:var(--ui-text,#35343f)}
.tm-inline{margin:8px 0 16px;padding:18px;border:1px solid var(--ui-line,#eae8f0);border-radius:22px;background:var(--ui-surface,#fff)}
.tm-inline-heading{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:18px}
.tm-inline-title{font-size:18px;font-weight:600;line-height:1.4}
.tm-inline-date{font-size:12px;line-height:1.6;color:var(--ui-muted,#74717f)}
.tm-meal-entries{display:flex;align-items:stretch;gap:12px}
.tm-meal-entry{
 display:flex;
 flex-direction:column;
 align-items:center;
 justify-content:center;
 flex:1;
 gap:11px;
 min-width:0;
 min-height:102px;
 margin:0;
 padding:15px 8px 12px;
 border:1px solid #edf0f6;
 border-radius:18px;
 background:linear-gradient(150deg,#f6f8fc,#fff);
 color:#454252;
 font-size:15px;
 font-weight:600;
 line-height:1.5;
 letter-spacing:.5px;
 transition:transform 160ms ease,background-color 160ms ease;
}
.tm-meal-symbol{
 display:flex;
 align-items:center;
 justify-content:center;
 flex-shrink:0;
 width:36px;
 height:36px;
 border-radius:11px;
 color:#fff;
 background:linear-gradient(140deg,#ffcfaa,#f18e64);
 box-shadow:inset 1px 1px 1px rgba(255,255,255,.8),0 4px 8px rgba(225,139,93,.18);
 transform:rotate(-7deg);
}
.tm-meal-glyph{display:flex;align-items:center;justify-content:center;transform:rotate(7deg)}
.tm-symbol-lunch{background:linear-gradient(140deg,#ffdf94,#efb04e);box-shadow:inset 1px 1px 1px rgba(255,255,255,.8),0 4px 8px rgba(226,173,71,.18);transform:rotate(6deg)}
.tm-symbol-lunch .tm-meal-glyph{transform:rotate(-6deg)}
.tm-symbol-dinner{background:linear-gradient(140deg,#c9bbff,#8d75dc);box-shadow:inset 1px 1px 1px rgba(255,255,255,.8),0 4px 8px rgba(146,121,213,.18);transform:rotate(-6deg)}
.tm-symbol-dinner .tm-meal-glyph{transform:rotate(6deg)}
.tm-meal-entry:active{transform:translateY(1px) scale(.98);background:#f0f2f7}
.tm-meal-entry[disabled]{opacity:.5;color:#858995}
.tm-status,.tm-error{margin:0 0 14px;padding:12px;border-radius:14px;background:#f5f4f8;color:var(--ui-muted,#74717f);font-size:13px;line-height:1.7}
.tm-status>text,.tm-question{display:block;overflow-wrap:anywhere}
.tm-status .tm-retry{margin-top:8px}
.tm-error{display:flex;flex-direction:column;align-items:flex-start;gap:10px;margin:14px 0 0}
.tm-error-title{font-size:15px;font-weight:500;color:var(--ui-text,#35343f)}
.tm-retry{display:flex;align-items:center;justify-content:center;min-height:44px;margin:0;padding:10px 16px;border-radius:12px;background:#e9e9f3;color:#514f6d;font-size:13px}
.tm-missing{display:block;margin-top:12px;font-size:12px;line-height:1.6;color:var(--ui-muted,#74717f)}
.tm-loading-status{display:flex;align-items:center;gap:8px;margin-top:14px;font-size:13px;line-height:1.7;color:var(--ui-muted,#74717f)}
.tm-pulse{width:6px;height:6px;flex-shrink:0;border-radius:50%;background:#a8a4c4;animation:tm-breathe 1.8s ease-in-out infinite}
.tm-body-paused .tm-pulse{animation-play-state:paused}
.tm-body button:after{border:0}
@keyframes tm-breathe{0%,100%{opacity:.55}50%{opacity:1}}
@media(max-width:350px){.tm-inline{padding:16px}.tm-inline-heading{gap:6px}.tm-inline-date{font-size:11px}.tm-meal-entries{gap:8px}.tm-meal-entry{min-height:94px;padding:12px 6px 10px;font-size:14px}.tm-meal-symbol{width:34px;height:34px}}
@media(prefers-reduced-motion:reduce){.tm-pulse{animation:none}.tm-meal-entry{transition:none}}
</style>
