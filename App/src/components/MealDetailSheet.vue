<script setup>
import {reactive,ref,computed,nextTick,onMounted,onUnmounted} from 'vue'
import {onShow} from '@dcloudio/uni-app'
import {referencePurchaseFor} from '../services/meal-workspace.js'
import DetailOverlay from './DetailOverlay.vue'
import FoodImageSlot from './FoodImageSlot.vue'
import CookingGuide from './CookingGuide.vue'
import MealNotes from './MealNotes.vue'
import CloudMealPurchase from './CloudMealPurchase.vue'
import {detailState,createMealDetailClient,mealNames,formalRoute,detailKey,detailGesture} from '../services/meal-detail-client.js'
import {createDailyArrangementClient,dailyArrangementState} from '../services/daily-arrangement-client.js'
import {request} from '../services/request.js'
import {storageContext,scopedStorage} from '../services/storage.js'
import {newHealthRequestId} from '../services/health-task-flow.js'
const props=defineProps({members:{type:Array,default:()=>[]},reload:Function,standalone:Boolean})
const emit=defineEmits(['open-change','leave'])
const state=reactive(detailState()),shown=ref(false),purchaseRef=ref(null),memberIds=ref([]),memberBusy=ref(false),memberError=ref('')
const viewport=ref(800),safeTop=ref(48),bodyTop=ref(0),bodyRestore=ref(0),scrollPositions={}
const client=createMealDetailClient({state,send:request,context:storageContext})
const memberState=reactive(dailyArrangementState())
const memberClient=createDailyArrangementClient({state:memberState,send:request,context:()=>({scope:storageContext(),familyId:state.target?.familyId}),storage:scopedStorage,newId:newHealthRequestId})
let owner='',touch=null,disposed=false
const target=computed(()=>state.target||{}),reference=computed(()=>target.value.kind==='reference')
const dish=computed(()=>state.meal?.dishes?.[state.dishIndex])
const title=computed(()=>state.view==='dish'?dish.value?.name||'菜品详情':state.view==='members'?'调整就餐成员':state.view==='checkout'?'确认采购订单':state.view==='purchase'?'准备所需食材':mealNames[target.value.mealType]+'详情')
const height=computed(()=>Math.round(state.expanded?viewport.value-safeTop.value:Math.min(viewport.value*.82,viewport.value-safeTop.value)))
const isPurchaseView=computed(()=>state.phase==='ready'&&['purchase','checkout'].includes(state.view))
const busy=computed(()=>memberBusy.value||purchaseRef.value?.isBusy)
const purchaseOption=computed(()=>target.value.purchaseOption)
const referencePurchase=computed(()=>target.value.purchaseOption?referencePurchaseFor(target.value):reference.value?{previewId:target.value.sourceId,mealTypes:target.value.purchaseMeals||[target.value.mealType],items:target.value.referencePlan?.purchase_items||[]}:null)
const canPurchase=computed(()=>!reference.value||!!(referencePurchase.value?.items.length||referencePurchase.value?.needsMatching))
const purchaseRoute=computed(()=>formalRoute(target.value))
const key=computed(()=>detailKey(target.value,owner))
const portionPlan=computed(()=>({...state.meal,sourceType:'api',members:state.meal?.members||[],memberNotes:(state.meal?.memberNotes||[]).map(note=>({...note,id:note.memberId,dishes:(note.dishes||[]).map(d=>({...d,recipeId:d.dishId,amount:d.grams,unit:'g'}))})),dishes:(state.meal?.dishes||[]).map(d=>({...d,recipeId:d.id})),safetyText:'按本版本已保存资料展示，已有明确医嘱优先。'}))
const gaps=computed(()=>purchaseOption.value?.gaps||target.value.referencePlan?.purchase_gaps||[])
function measure(){try{const info=uni.getWindowInfo?uni.getWindowInfo():uni.getSystemInfoSync();viewport.value=info.windowHeight||800;safeTop.value=(info.statusBarHeight||24)+44;try{safeTop.value=Math.max(safeTop.value,uni.getMenuButtonBoundingClientRect().bottom+8)}catch{}}catch{}}
function open(value){if(disposed)return;owner=storageContext();measure();Object.keys(scrollPositions).forEach(k=>delete scrollPositions[k]);bodyTop.value=0;bodyRestore.value=0;memberError.value='';shown.value=true;emit('open-change',true);uni.hideKeyboard?.();return client.open(value).then(()=>{if(state.view==='members')memberIds.value=(state.meal?.members||[]).map(m=>m.id)}).catch(e=>{state.open=true;state.target={...value};state.view='meal';state.phase='error';state.error=e.message})}
function close(force=false){if(busy.value&&force!==true)return;if(props.standalone){emit('leave');return}shown.value=false}
function closed(){if(shown.value)return;client.close();memberClient.reset();emit('open-change',false)}
function clear(){shown.value=false;client.clear();memberClient.reset();emit('open-change',false)}
function scrollKey(){return state.view==='dish'?'dish:'+state.dishIndex:state.view}
async function switchView(view,index=state.dishIndex){scrollPositions[scrollKey()]=bodyTop.value;state.dishIndex=index;state.view=view;bodyTop.value=scrollPositions[scrollKey()]||0;bodyRestore.value=-1;await nextTick();bodyRestore.value=bodyTop.value}
function back(){if(busy.value)return;if(state.view==='checkout'){purchaseRef.value?.closeCheckout();state.view='purchase'}else switchView('meal')}
function referenceMeal(meal){open({...target.value,mealType:meal.meal_type,seed:{...meal,members:target.value.referencePlan?.members||[]},initialView:'meal'})}
function showDish(index){switchView('dish',index)}
function showPurchase(){if(state.phase==='ready'&&canPurchase.value)switchView('purchase')}
function startMembers(){memberIds.value=(state.meal?.members||[]).map(m=>m.id);memberError.value='';switchView('members')}
function toggleMember(id){memberIds.value=memberIds.value.includes(id)?memberIds.value.filter(x=>x!==id):[...memberIds.value,id]}
async function saveMembers(){
 if(memberBusy.value||!memberIds.value.length||state.phase!=='ready')return
 const original={...target.value},scope=storageContext();memberBusy.value=true;memberError.value=''
 try{
  await memberClient.load(original.date)
  if(!state.open||scope!==storageContext())return
  if(memberState.arrangement?.id!==original.sourceId||memberState.arrangement?.version!==original.version)throw new Error(memberState.error||'本餐版本已变化，请重新读取后调整。')
  await memberClient.changeMembers(original.mealType,[...memberIds.value],{dailyPlanVersion:original.dailyPlanVersion})
  if(!state.open||scope!==storageContext())return
  if(memberState.error||!memberState.arrangement)throw new Error(memberState.error||'成员调整结果尚未确认，请重试核对。')
  const plan=await props.reload?.(original.date)
  if(!state.open||scope!==storageContext())return
  await client.open({...original,initialView:'meal',version:memberState.arrangement.version,dailyPlanVersion:plan?.version??original.dailyPlanVersion,seed:memberState.arrangement.meals.find(m=>m.type===original.mealType)})
 }catch(e){if(state.open&&scope===storageContext())memberError.value=e.message}
 finally{memberBusy.value=false}
}
function touchStart(e){if(props.standalone)return;const t=e.touches?.[0];if(t)touch={y:t.clientY,x:t.clientX,top:bodyTop.value}}
function touchEnd(e){const t=e.changedTouches?.[0];if(!touch||!t)return;const start=touch;touch=null;if(Math.abs(t.clientX-start.x)>Math.abs(t.clientY-start.y))return;const action=detailGesture({delta:t.clientY-start.y,expanded:state.expanded,scrollTop:start.top});if(action==='expand')state.expanded=true;else if(action==='collapse')state.expanded=false;else if(action==='close')close()}
function checkoutChanged(opened){if(opened)state.view='checkout';else if(state.view==='checkout')state.view='purchase'}
function keydown(e){
 if(!state.open)return
 if(e.key==='Escape'){e.preventDefault();close()}
 if(e.key==='Tab'&&typeof document!=='undefined'){
  const nodes=[...document.querySelectorAll('.meal-detail-panel [tabindex="0"],.meal-detail-panel input')].filter(n=>n.getClientRects().length&&!n.hasAttribute('disabled'))
  if(!nodes.length)return
  const i=nodes.indexOf(document.activeElement)
  if(i<0||e.shiftKey&&i===0||!e.shiftKey&&i===nodes.length-1){e.preventDefault();nodes[e.shiftKey?nodes.length-1:0].focus()}
 }
}
// Selecting an address temporarily hides the page. Keep the sheet and its order state.
onShow(()=>{if(!state.open)return;if(owner!==storageContext()){clear();return}void purchaseRef.value?.refresh()})
onMounted(()=>{measure();uni.onWindowResize?.(measure);/* #ifdef H5 */
 if(typeof window!=='undefined'){window.addEventListener('resize',measure);window.addEventListener('keydown',keydown)}
 /* #endif */})
onUnmounted(()=>{uni.offWindowResize?.(measure);disposed=true;client.dispose();memberClient.dispose();/* #ifdef H5 */
 if(typeof window!=='undefined'){window.removeEventListener('resize',measure);window.removeEventListener('keydown',keydown)}
 /* #endif */})
defineExpose({open,close,clear})
</script>
<template>
 <DetailOverlay :standalone="standalone" :open="shown" @close="close" @closed="closed">
  <view v-if="state.open" class="meal-detail-panel" :class="{'is-page':standalone}" :style="standalone?{'--detail-safe-top':Math.max(0,safeTop-44)+'px'}:{height:height+'px'}" role="dialog" aria-modal="true" :aria-label="title">
   <view v-if="!standalone" class="detail-grip" @touchstart="touchStart" @touchend="touchEnd"><view/></view>
   <view class="detail-header" @touchstart="touchStart" @touchend="touchEnd"><button tabindex="0" role="button" v-if="state.view!=='meal'||standalone" class="detail-back" :disabled="busy" aria-label="返回本餐" @click="state.view==='meal'?close():back()">‹</button><view><text class="detail-title">{{title}}</text><text class="detail-subtitle">{{target.date}} · {{reference?'日常参考餐单':'已保存餐单'}}</text></view><button tabindex="0" role="button" v-if="!standalone" class="detail-expand" :disabled="busy" :aria-label="state.expanded?'收拢详情':'展开详情'" @click="state.expanded=!state.expanded">{{state.expanded?'收拢':'展开'}}</button><button tabindex="0" role="button" v-if="!standalone" class="detail-close" :disabled="busy" aria-label="关闭餐单详情" @click="close">×</button></view>
   <CloudMealPurchase v-if="state.phase==='ready'&&canPurchase" v-show="state.view==='purchase'||state.view==='checkout'" :key="key" ref="purchaseRef" embedded :meal="target.purchaseMembers?{...state.meal,members:target.purchaseMembers}:state.meal" :route="purchaseRoute" :reference="referencePurchase" @checkout="checkoutChanged"/>
   <scroll-view v-show="!isPurchaseView" class="detail-body" :scroll-y="standalone||state.expanded" :scroll-top="bodyRestore" :show-scrollbar="false" @scroll="bodyTop=$event.detail.scrollTop" @touchstart="touchStart" @touchend="touchEnd">
    <view v-if="state.phase==='loading'" class="detail-status" role="status">正在核对本餐来源…</view>
    <view v-if="state.phase==='error'" class="detail-error" role="alert"><text>{{state.error}}</text><button tabindex="0" role="button" @click="client.retry()">重新读取详情</button></view>
    <view v-if="!state.meal&&state.phase==='loading'" class="detail-skeleton" aria-hidden="true"><view class="skeleton-image"/><view/><view/><view/></view>
    <template v-if="state.meal">
     <view v-if="reference" class="reference-disclosure"><text>参考餐单 · 未专业审核</text><text>个人营养量尚未核算，缺失数据保持未知。{{target.referencePlan?.notice||''}}</text></view>
     <template v-if="state.view==='meal'">
      <view v-if="target.referencePlan?.meals?.length>1" class="reference-meal-tabs"><button v-for="meal in target.referencePlan.meals" :key="meal.meal_type" :aria-pressed="target.mealType===meal.meal_type" @click="referenceMeal(meal)">{{mealNames[meal.meal_type]}}</button></view>
      <text class="detail-members">就餐成员：{{(state.meal.members||[]).map(m=>m.name).join('、')||'以餐单来源为准'}}</text>
      <view class="detail-section-label">本餐菜品</view>
      <button tabindex="0" role="button" v-for="(item,index) in state.meal.dishes" :key="index" class="detail-dish-row" @click="showDish(index)"><FoodImageSlot :src="item.image_url" :label="item.name" class="detail-thumb"/><view><text class="detail-dish-name">{{item.name}}</text><text class="detail-dish-note">{{item.portion_note||'查看食材与制作步骤'}}</text></view><text class="detail-chevron">›</text></button>
      <view v-if="!reference" class="detail-nutrition"><MealNotes card-mode hide-details :plan="portionPlan"/></view>
      <view v-if="gaps.length" class="detail-gaps"><text class="detail-section-label">食材准备说明</text><text v-for="gap in gaps" :key="gap.ingredient">{{gap.ingredient}}：{{gap.detail}}</text></view>
     </template>
     <template v-else-if="state.view==='dish'&&dish"><text v-if="dish.portion_note" class="detail-copy">{{dish.portion_note}}</text><text v-if="dish.portion_quote" class="detail-copy">原食谱份量：{{dish.portion_quote}}</text><CookingGuide :dishes="[dish]" action=""/><view class="detail-source"><text>来源：{{dish.source?.filename||dish.recipeVersion||'当前保存菜谱'}}</text><text v-if="reference&&dish.nutrition_quote">原食谱营养说明：{{dish.nutrition_quote}}</text><text v-if="reference">本页未计算个人营养量。</text></view></template>
     <template v-else-if="state.view==='members'"><text class="detail-copy">只调整本餐，确认后重新核对餐单与采购。</text><button tabindex="0" role="button" v-for="member in members" :key="member.id" class="detail-member-choice" :aria-pressed="memberIds.includes(member.id)" :disabled="memberBusy" @click="toggleMember(member.id)"><text>{{member.name}}</text><text>{{memberIds.includes(member.id)?'✓':'○'}}</text></button><text v-if="memberError" class="detail-error">{{memberError}}</text></template>
    </template>
    <view class="detail-bottom-space"/>
   </scroll-view>
   <view v-if="!isPurchaseView" class="detail-footer">
    <template v-if="state.view==='members'"><button tabindex="0" role="button" class="detail-secondary" :disabled="busy" @click="back">取消调整</button><button tabindex="0" role="button" class="detail-primary" :disabled="busy||!memberIds.length||state.phase!=='ready'" @click="saveMembers">{{memberBusy?'正在核对…':'确认成员'}}</button></template>
    <template v-else><button tabindex="0" role="button" v-if="state.view==='dish'" class="detail-secondary" @click="back">返回本餐</button><button tabindex="0" role="button" v-else-if="!reference" class="detail-secondary" :disabled="state.phase!=='ready'" @click="startMembers">调整成员</button><button tabindex="0" role="button" class="detail-primary" :disabled="state.phase!=='ready'" @click="canPurchase?showPurchase():showDish(0)">{{state.phase==='loading'?'正在核对…':canPurchase?'准备食材':'查看做法'}}</button></template>
   </view>
  </view>
 </DetailOverlay>
</template>
<style scoped>
.meal-detail-panel{display:flex;flex-direction:column;width:100%;max-width:480px;margin:0 auto;min-height:0;overflow:hidden;background:#fff;border-radius:28px 28px 0 0;color:var(--ui-text);box-sizing:border-box;transition:height 240ms cubic-bezier(.2,.7,.2,1)}.detail-grip{display:flex;justify-content:center;align-items:center;height:22px;min-height:22px}.detail-grip>view{width:34px;height:4px;background:#d5d7da;border-radius:4px}.detail-header{display:flex;align-items:center;gap:8px;padding:0 12px 12px 20px;border-bottom:1px solid #f0f1f2;flex-shrink:0}.detail-header>view{flex:1;min-width:0}.detail-title{display:block;font-size:18px;line-height:1.5;font-weight:500;overflow-wrap:anywhere}.detail-subtitle{display:block;font-size:12px;line-height:1.7;color:var(--ui-muted);margin-top:3px}.detail-close,.detail-back,.detail-expand{display:flex;align-items:center;justify-content:center;min-width:44px;min-height:44px;margin:0;padding:0;background:transparent}.detail-close{font-size:28px;color:var(--ui-muted)}.detail-back{font-size:30px;width:30px;min-width:30px;margin-left:-8px}.detail-expand{font-size:12px;color:#72767e}.detail-body{height:0;flex:1;min-height:0;box-sizing:border-box;padding:18px 20px 0}.detail-status{font-size:12px;color:var(--ui-muted);margin-bottom:12px}.detail-error{display:block;font-size:14px;line-height:1.8;color:#a63c35;padding:12px 0}.detail-error>text{display:block}.detail-error button{min-height:44px;text-align:left;font-size:14px;color:#34363a}.reference-disclosure{display:flex;flex-direction:column;gap:5px;padding:12px 14px;border-radius:12px;background:var(--ui-soft);font-size:12px;line-height:1.8;color:var(--ui-muted);margin-bottom:16px}.reference-disclosure>text:first-child{font-weight:500;color:#5f5a47}.detail-members,.detail-copy{display:block;color:var(--ui-muted);font-size:13px;line-height:1.8;margin-bottom:14px}.detail-section-label{font-size:14px;font-weight:500;margin:8px 0}.detail-dish-row{display:flex;align-items:center;width:100%;gap:12px;min-height:96px;padding:12px 0;text-align:left;border-bottom:1px solid #eee}.detail-thumb{width:72px;height:72px;border-radius:12px}.detail-dish-row>view:not(.detail-thumb){flex:1;min-width:0}.detail-dish-name{display:block;font-size:16px;line-height:1.6}.detail-dish-note{display:block;font-size:12px;color:var(--ui-muted);line-height:1.8;margin-top:4px}.detail-chevron{font-size:24px;color:#92969c}.detail-nutrition :deep(.meal-notes){color:var(--ui-text)}.detail-nutrition :deep(.member-tab.active){background:var(--ui-accent-soft);color:var(--ui-accent)}.detail-source,.detail-gaps{display:flex;flex-direction:column;gap:7px;font-size:12px;color:var(--ui-muted);line-height:1.9;margin-top:18px;overflow-wrap:anywhere}.detail-footer{display:flex;gap:10px;flex-shrink:0;border-top:1px solid var(--ui-line);background:#fff;padding:14px 20px calc(env(safe-area-inset-bottom) + 14px)}.detail-primary,.detail-secondary{display:flex;align-items:center;justify-content:center;min-height:48px;padding:10px 18px;margin:0;box-sizing:border-box;border-radius:12px;font-size:15px;line-height:1.5}.detail-primary{flex:1;background:var(--ui-accent);color:#fff}.detail-secondary{background:var(--ui-soft);color:#4b4e54}.detail-member-choice{display:flex;width:100%;justify-content:space-between;align-items:center;min-height:56px;border-bottom:1px solid #eee;font-size:16px;text-align:left}.detail-bottom-space{height:22px}.detail-skeleton>view{height:14px;border-radius:14px;margin-bottom:18px;background:#f0f1f3}.detail-skeleton>view:nth-child(3){width:75%}.detail-skeleton .skeleton-image{height:180px}.meal-detail-panel button:after{border:0}.meal-detail-panel button[disabled]{opacity:.45}.detail-body :deep(.guide-action){display:none}@media(prefers-reduced-motion:reduce){.meal-detail-panel{transition:none}}
</style>

<style scoped>.reference-meal-tabs{display:flex;gap:8px;margin-bottom:16px}.reference-meal-tabs button{flex:1;min-height:44px;border-radius:10px;background:var(--ui-soft);font-size:14px}.reference-meal-tabs button[aria-pressed="true"]{background:var(--ui-accent-soft);color:var(--ui-accent)}</style>

<style scoped>
.meal-detail-panel.is-page{height:100vh;height:100dvh;max-width:480px;border-radius:0;background:var(--ui-canvas-gradient);margin:auto}.is-page .detail-header{padding:calc(var(--detail-safe-top) + 12px) 20px 16px;background:rgba(255,255,255,.5);border-bottom:1px solid #fff}.is-page .detail-title{font-size:20px;font-weight:600}.is-page .detail-body{padding:20px}.is-page .reference-disclosure{background:rgba(255,255,255,.7);border:1px solid #fff;border-radius:18px}.is-page .detail-dish-row{background:var(--ui-bubble);padding:14px;border:1px solid #fff;border-radius:22px;margin:10px 0;box-shadow:inset 0 1px 1px #fff,0 4px 16px rgba(60,48,80,.03)}.is-page .detail-dish-name{font-weight:500}.is-page .detail-footer{background:rgba(255,255,255,.94);border-top:1px solid #fff}.is-page .detail-primary{border-radius:99px;background:var(--ui-accent);box-shadow:none}.is-page .detail-secondary{border-radius:99px;background:var(--ui-accent-soft);color:var(--ui-accent)}
</style>
