<script setup>
import { computed, ref, watch } from 'vue'
import TodayMealPlanContent from './TodayMealPlanContent.vue'
import { detailGesture } from '../services/meal-detail-client.js'
import { localDate } from '../utils/meal-state.js'
const props=defineProps({open:Boolean,state:{type:Object,required:true},busy:Boolean,interactive:{type:Boolean,default:true},members:{type:Array,default:()=>[]},defaultDiners:{type:Array,default:()=>[]},dinerDraft:Object})
const emit=defineEmits(['close','action','detail','dish','confirm-diners','arrange-diners'])
const expanded=ref(false)
const editing=ref(false),mealType=ref(''),selected=ref([])
const meals=[{type:'breakfast',name:'早餐'},{type:'lunch',name:'午餐'},{type:'dinner',name:'晚餐'}]
const mealName=computed(()=>meals.find(item=>item.type===mealType.value)?.name||'')
const draftMealName=computed(()=>meals.find(item=>item.type===props.dinerDraft?.mealType)?.name||'')
const meal=computed(()=>props.state.plan?.meals.find(item=>item.meal_type===mealType.value))
const readyMeal=computed(()=>props.state.verified&&meal.value&&!props.state.plan.needs_regeneration?.includes(mealType.value))
const canEdit=computed(()=>props.open&&props.interactive&&!props.busy&&props.members.length>0)
function selectMeal(type){
 mealType.value=type
 const ids=(props.dinerDraft?.mealType===type?props.dinerDraft.participantIds:null)||
  meal.value?.members?.map(member=>member.id)||props.defaultDiners
 selected.value=ids.filter(id=>props.members.some(member=>member.id===id))
}
function startEditing(){
 if(!canEdit.value)return
 editing.value=true
 if(props.dinerDraft)selectMeal(props.dinerDraft.mealType)
}
function cancelEditing(){editing.value=false;mealType.value='';selected.value=[]}
function dismiss(){if(editing.value)cancelEditing();else emit('close')}
function toggleMember(id){
 selected.value=selected.value.includes(id)?selected.value.filter(value=>value!==id):[...selected.value,id]
}
function confirm(){
 if(!canEdit.value||!mealType.value||!selected.value.length)return
 emit('confirm-diners',{mealType:mealType.value,participantIds:[...selected.value].sort()})
 cancelEditing()
}
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
 else if(action==='close')dismiss()
}
function detail(item){if(props.state.displayable&&props.interactive&&props.open)emit('detail',item)}
function dish(value){if(props.state.displayable&&props.interactive&&props.open)emit('dish',value)}
function act(){if(!props.busy&&props.interactive&&props.open)emit('action')}
watch(()=>props.open,open=>{touch=null;if(open)expanded.value=false})
watch([()=>props.open,()=>props.state.date,()=>props.members],cancelEditing)
</script>
<template>
 <view v-if="open" class="tm-mask" @click.self="dismiss">
  <view class="tm-sheet" :class="{'tm-expanded':expanded,'tm-paused':!interactive}" role="dialog" aria-modal="true" :aria-label="editing?'调整就餐成员':'今日餐单'" @click.stop>
   <view class="tm-handle" aria-hidden="true" @touchstart="start" @touchend="end" @touchcancel="cancelTouch"><view class="tm-grip"/></view>
   <view class="tm-header">
    <view class="tm-heading-wrap">
     <view class="tm-heading" @touchstart="start" @touchend="end" @touchcancel="cancelTouch"><text class="tm-title">{{editing?'调整就餐成员':'今日餐单'}}</text></view>
     <view class="tm-date-row"><text class="tm-date">{{displayDate}}</text><button v-if="!editing" class="tm-edit" :disabled="!canEdit" @click="startEditing">调整就餐成员</button></view>
    </view>
    <view class="tm-controls"><button class="tm-close" :aria-label="editing?'返回今日餐单':'关闭今日餐单'" @click="dismiss"><text>{{editing?'‹':'×'}}</text></button></view>
   </view>
   <scroll-view class="tm-content" scroll-y :show-scrollbar="false" :aria-busy="!state.plan&&(state.checking||state.phase==='generating')">
    <view v-if="editing" class="tm-diners">
     <text>选哪一餐？</text>
     <view class="tm-diner-tabs"><button v-for="item in meals" :key="item.type" :aria-pressed="mealType===item.type" :class="{'tm-selected':mealType===item.type}" @click="selectMeal(item.type)">{{item.name}}</button></view>
     <view v-if="mealType">
      <text>{{mealName}}谁来吃？</text>
      <button v-for="member in members" :key="member.id" class="tm-diner-member" role="checkbox" :aria-checked="selected.includes(member.id)" @click="toggleMember(member.id)"><text>{{member.name}}</text><text>{{selected.includes(member.id)?'✓':'○'}}</text></button>
     </view>
    </view>
    <view v-else>
     <view v-if="dinerDraft" class="tm-diner-summary">
      <text>{{draftMealName}} {{dinerDraft.participantIds.length}} 人 · {{busy?'正在核对':'待安排'}}</text>
      <button v-if="!busy&&interactive&&!['answer','candidates','regenerate'].includes(state.action)" class="tm-edit" @click="emit('arrange-diners')">重新安排{{draftMealName}}</button>
     </view>
     <TodayMealPlanContent :state="state" :busy="busy" :interactive="interactive&&open" @action="act" @detail="detail" @dish="dish"/>
    </view>
   </scroll-view>
   <view v-if="editing" class="tm-diner-footer">
    <text v-if="mealType">{{mealName}} {{selected.length}} 人{{readyMeal?' · 成员变更后重新安排本餐':' · 确认后可重新安排本餐'}}</text>
    <view class="tm-diner-actions"><button @click="cancelEditing">取消</button><button :disabled="!canEdit||!selected.length" @click="confirm">{{mealName?'确认'+mealName+'成员':'确认成员'}}</button></view>
   </view>
  </view>
 </view>
</template>
<style>
/* All selectors use this component's tm- namespace; avoid repeated scope IDs in the upload. */
.tm-mask{position:fixed;inset:0;z-index:70;display:flex;align-items:flex-end;background:rgba(34,41,58,.28)}
.tm-sheet{display:flex;flex-direction:column;box-sizing:border-box;width:100%;max-width:480px;margin:0 auto;height:auto;max-height:calc(100vh - 68px);overflow:hidden;padding:0 0 env(safe-area-inset-bottom);border:1px solid rgba(255,255,255,.9);border-bottom:0;border-radius:26px 26px 0 0;color:var(--ui-text,#35343f);background-color:#fafafc;background-image:radial-gradient(ellipse at 0% 0%,rgba(159,192,249,.24),transparent 72%),radial-gradient(ellipse at 100% 0%,rgba(205,186,237,.22),transparent 75%);background-size:100% 150px;background-repeat:no-repeat;box-shadow:0 -8px 32px rgba(36,55,87,.1);transition:height 240ms cubic-bezier(.2,.7,.2,1)}
.tm-sheet.tm-expanded{height:90vh;height:90dvh}.tm-handle{height:20px;min-height:20px;display:flex;align-items:center;justify-content:center;flex-shrink:0}.tm-grip{width:30px;height:4px;border-radius:4px;background:#d0d2de}
.tm-header{display:flex;align-items:center;gap:10px;padding:4px 16px 16px 20px;flex-shrink:0}.tm-heading{flex:1;min-width:0}.tm-title{display:block;font-size:21px;font-weight:600;line-height:1.4}.tm-date{display:block;margin-top:4px;color:#74717f;font-size:12px;line-height:1.6}
.tm-controls{display:flex;align-items:center;gap:2px}.tm-close{display:flex;align-items:center;justify-content:center;width:44px;height:44px;min-width:44px;margin:0;padding:0;background:transparent;color:#74717f}.tm-close>text{display:flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:50%;background:rgba(229,230,239,.6);font-size:24px;line-height:1}.tm-sheet button:after{border:0}
.tm-content{height:auto;max-height:50vh;min-height:0}.tm-expanded .tm-content{height:0;max-height:none;flex:1}
.tm-heading-wrap{flex:1;min-width:0}.tm-date-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.tm-edit{min-height:32px;padding:0 10px;margin:0;border-radius:12px;background:#e9e8f2;color:#51496b;font-size:12px;line-height:32px}
.tm-diners,.tm-diner-summary{padding:0 20px 12px;font-size:14px}.tm-diner-tabs,.tm-diner-actions{display:flex;gap:8px;margin:8px 0 12px}
.tm-diner-tabs button,.tm-diner-actions button{flex:1;min-height:44px;margin:0;border-radius:14px;background:#eeedf3;font-size:14px;line-height:44px}.tm-diner-tabs .tm-selected,.tm-diner-actions button:last-child{background:#343442;color:#fff}
.tm-diner-member{display:flex;align-items:center;justify-content:space-between;min-height:44px;padding:0 8px;margin:0;border-radius:0;border-bottom:1px solid #e8e6ee;background:transparent;font-size:14px}
.tm-diner-footer{flex-shrink:0;padding:10px 20px 0;background:#fafafc;font-size:13px}.tm-diner-summary{color:#51496b}
@media(max-width:350px){.tm-header{padding-left:16px;padding-right:12px}}
@media(max-height:480px){.tm-sheet{max-height:calc(100vh - 44px)}.tm-content{max-height:calc(100vh - 150px)}.tm-header{padding-bottom:10px}}
@media(prefers-reduced-motion:reduce){.tm-sheet{transition:none}}
</style>
