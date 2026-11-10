<script setup>
import {reactive,ref,computed,nextTick,onMounted,onUnmounted} from 'vue'
import {onShow} from '@dcloudio/uni-app'
import {referencePurchaseFor} from '../services/meal-workspace.js'
import {addDishToMeal,savedPurchaseScope} from '../services/meal-dish-actions.js'
import {localDate} from '../utils/meal-state.js'
import {recipeCover} from '../utils/recipe-cover.js'
import {dishTitle,dishKey,mealNutrition} from '../utils/meal-presentation.js'
import DetailOverlay from './DetailOverlay.vue'
import FoodImageSlot from './FoodImageSlot.vue'
import CookingGuide from './CookingGuide.vue'
import CloudMealPurchase from './CloudMealPurchase.vue'
import MealPurchaseSheet from './MealPurchaseSheet.vue'
import {detailState,createMealDetailClient,mealNames,formalRoute,detailKey,detailGesture} from '../services/meal-detail-client.js'
import {createDailyArrangementClient,dailyArrangementState} from '../services/daily-arrangement-client.js'
import {request} from '../services/request.js'
import {storageContext,scopedStorage} from '../services/storage.js'
import {newHealthRequestId} from '../services/health-task-flow.js'
const props=defineProps({members:{type:Array,default:()=>[]},reload:Function,standalone:Boolean,leaving:Boolean,returnError:String})
const emit=defineEmits(['open-change','leave'])
const state=reactive(detailState()),shown=ref(false),purchaseRef=ref(null),memberIds=ref([]),memberBusy=ref(false),memberError=ref('')
const dishOpened=ref(false)
const purchaseOpen=ref(false),purchaseMounted=ref(false),purchaseSheet=ref(null)
const cookingOpen=ref(false),cookingMeal=ref('dinner'),cookingBusy=ref(false),cookingError=ref(''),cookingRequest=ref(''),purchaseDish=ref(null)
const viewport=ref(800),safeTop=ref(48),bodyTop=ref(0),bodyRestore=ref(0),scrollPositions={}
const client=createMealDetailClient({state,send:request,context:storageContext})
const memberState=reactive(dailyArrangementState())
const memberClient=createDailyArrangementClient({state:memberState,send:request,context:()=>({scope:storageContext(),familyId:state.target?.familyId}),storage:scopedStorage,newId:newHealthRequestId})
let owner='',touch=null,disposed=false,openRevision=0
const target=computed(()=>state.target||{}),reference=computed(()=>target.value.kind==='reference')
const dish=computed(()=>state.meal?.dishes?.[state.dishIndex])
const title=computed(()=>state.view==='dish'?'菜品详情':state.view==='members'?'调整就餐成员':mealNames[target.value.mealType]+'安排')
const height=computed(()=>Math.round(state.expanded?viewport.value-safeTop.value:Math.min(viewport.value*.82,viewport.value-safeTop.value)))
const busy=computed(()=>Boolean(props.leaving||memberBusy.value||cookingBusy.value||purchaseRef.value?.isBusy))
const purchaseScope=computed(()=>savedPurchaseScope(target.value,purchaseDish.value?[purchaseDish.value]:undefined))
const nutritionSummary=computed(()=>mealNutrition(state.meal))

const referencePurchase=computed(()=>target.value.purchaseOption?referencePurchaseFor(target.value):reference.value?{previewId:target.value.sourceId,mealTypes:target.value.purchaseMeals||[target.value.mealType],items:target.value.referencePlan?.product_matches||target.value.referencePlan?.purchase_items||[]}:null)
const canPurchase=computed(()=>state.phase==='ready'&&target.value.purchaseReady!==false&&(!reference.value||target.value.purchaseReady===true||!!referencePurchase.value?.items.length))
const purchaseRoute=computed(()=>formalRoute(target.value))
const key=computed(()=>detailKey(target.value,owner))



function measure(){try{const info=uni.getWindowInfo?uni.getWindowInfo():uni.getSystemInfoSync();viewport.value=info.windowHeight||800;safeTop.value=(info.statusBarHeight||24)+44;try{safeTop.value=Math.max(safeTop.value,uni.getMenuButtonBoundingClientRect().bottom+8)}catch{}}catch{}}
function open(value){if(disposed)return;const revision=++openRevision;purchaseOpen.value=false;purchaseMounted.value=false;dishOpened.value=value.initialView==='dish';owner=storageContext();measure();Object.keys(scrollPositions).forEach(k=>delete scrollPositions[k]);bodyTop.value=0;bodyRestore.value=0;memberError.value='';cookingOpen.value=false;cookingError.value='';purchaseDish.value=null;shown.value=true;emit('open-change',true);uni.hideKeyboard?.();return client.open({...value,initialView:value.initialView==='purchase'?'meal':value.initialView}).then(()=>{if(revision!==openRevision||!shown.value)return;if(state.view==='members')memberIds.value=(state.meal?.members||[]).map(m=>m.id);if(value.initialView==='purchase'&&state.phase==='ready')showPurchase()}).catch(e=>{if(revision!==openRevision||!shown.value)return;state.open=true;state.target={...value};state.view='meal';state.phase='error';state.error=e.message})}
function close(force=false){if(busy.value&&force!==true)return;if(purchaseOpen.value&&force!==true){closePurchase();return}purchaseOpen.value=false;if(props.standalone){emit('leave');return}shown.value=false}
function closed(){if(shown.value)return;client.close();memberClient.reset();emit('open-change',false)}
function clear(){openRevision++;shown.value=false;purchaseOpen.value=false;purchaseMounted.value=false;client.clear();memberClient.reset();emit('open-change',false)}
function scrollKey(){return state.view==='dish'?'dish:'+state.dishIndex:state.view}
async function switchView(view,index=state.dishIndex){scrollPositions[scrollKey()]=bodyTop.value;state.dishIndex=index;state.view=view;bodyTop.value=scrollPositions[scrollKey()]||0;bodyRestore.value=-1;await nextTick();bodyRestore.value=bodyTop.value}
// Native back may leave the page itself; button back must explicitly request it.
function requestBack(native=false){
 if(busy.value)return true
 if(purchaseOpen.value){closePurchase();return true}
 if(cookingOpen.value){cookingOpen.value=false;return true}
 if(state.view==='members'||state.view==='dish'&&target.value.initialView!=='dish'){void switchView('meal');return true}
 if(native===true)return false
 close();return true
}
function showDish(index){dishOpened.value=true;switchView('dish',index)}
function showPurchase(){if(state.phase==='ready'&&canPurchase.value){purchaseDish.value=state.view==='dish'?dish.value:null;purchaseMounted.value=true;purchaseOpen.value=true}}
function closePurchase(){if(!purchaseRef.value?.isBusy)purchaseOpen.value=false}
function startCooking(){cookingMeal.value=target.value.mealType;cookingRequest.value=newHealthRequestId();cookingError.value='';cookingOpen.value=true}
async function confirmCooking(){
 if(cookingBusy.value||!dish.value)return
 const scope=storageContext(),chosen=target.value,selected=dish.value
 cookingBusy.value=true;cookingError.value=''
 try{const plan=await addDishToMeal(chosen,selected,cookingMeal.value,cookingRequest.value);if(scope!==storageContext())return;const item=plan.meals.find(m=>m.meal_type===chosen.mealType);state.target={...chosen,dailyPlanVersion:plan.version,...(item?{kind:item.source.kind,sourceId:item.source.id,version:item.source.version}:{} )};await props.reload?.(plan.date);if(scope!==storageContext())return;cookingOpen.value=false;uni.showToast({title:'已加入今日餐单',icon:'none'})}
 catch(e){if(scope===storageContext())cookingError.value=e.message}
 finally{cookingBusy.value=false}
}
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
function touchStart(e){if(props.standalone||purchaseOpen.value)return;const t=e.touches?.[0];if(t)touch={y:t.clientY,x:t.clientX,top:bodyTop.value}}
function touchEnd(e){const t=e.changedTouches?.[0];if(!touch||!t)return;const start=touch;touch=null;if(Math.abs(t.clientX-start.x)>Math.abs(t.clientY-start.y))return;const action=detailGesture({delta:t.clientY-start.y,expanded:state.expanded,scrollTop:start.top});if(action==='expand')state.expanded=true;else if(action==='collapse')state.expanded=false;else if(action==='close')close()}
function keydown(e){
 if(!state.open)return
 if(e.key==='Escape'){e.preventDefault();requestBack()}
 if(e.key==='Tab'&&typeof document!=='undefined'){
  const root=purchaseOpen.value?'.mp-sheet-panel':'.meal-detail-panel'
  const nodes=[...document.querySelectorAll(root+' button,'+root+' uni-button,'+root+' [tabindex="0"],'+root+' input')].filter(n=>n.getClientRects().length&&!n.hasAttribute('disabled'))
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
defineExpose({open,close,clear,handleBack:()=>requestBack(true)})
</script>
<template>
 <DetailOverlay :standalone="standalone" :open="shown" @close="close" @closed="closed">
  <view v-if="state.open" class="meal-detail-panel" :class="{'is-page':standalone}" :style="standalone?{'--detail-safe-top':Math.max(0,safeTop-44)+'px'}:{height:height+'px'}" role="dialog" aria-modal="true" :aria-label="title">
   <view v-if="!standalone" class="detail-grip" @touchstart="touchStart" @touchend="touchEnd"><view/></view>
   <view class="detail-header" @touchstart="touchStart" @touchend="touchEnd"><button tabindex="0" role="button" v-if="state.view!=='meal'||standalone" class="detail-back" :disabled="busy" aria-label="返回本餐" @click="requestBack()">‹</button><view><text class="detail-title">{{title}}</text><text class="detail-subtitle">{{target.date}} · {{reference?'日常参考餐单':'已保存餐单'}}</text></view><button tabindex="0" role="button" v-if="!standalone" class="detail-expand" :disabled="busy" :aria-label="state.expanded?'收拢详情':'展开详情'" @click="state.expanded=!state.expanded">{{state.expanded?'收拢':'展开'}}</button><button tabindex="0" role="button" v-if="!standalone" class="detail-close" :disabled="busy" aria-label="关闭餐单详情" @click="close">×</button></view>
   <scroll-view class="detail-body" :scroll-y="!purchaseOpen&&(standalone||state.expanded)" :scroll-top="bodyRestore" :show-scrollbar="false" @scroll="bodyTop=$event.detail.scrollTop" @touchstart="touchStart" @touchend="touchEnd">
    <text v-if="returnError" class="detail-error" role="alert">{{returnError}}</text>
    <view v-if="state.phase==='loading'" class="detail-status" role="status">正在核对本餐来源…</view>
    <view v-if="state.phase==='error'" class="detail-error" role="alert"><text>{{state.error}}</text><button tabindex="0" role="button" @click="client.retry()">重新读取详情</button></view>
    <view v-if="!state.meal&&state.phase==='loading'" class="detail-skeleton" aria-hidden="true"><view class="skeleton-image"/><view/><view/><view/></view>
    <template v-if="state.meal">

     <template v-if="state.view==='meal'">

      <view class="meal-overview"><text class="meal-overview-title">好好吃饭，轻松安排</text><text v-if="(state.meal.members||[]).length" class="detail-members">{{(state.meal.members||[]).map(m=>m.name).join(' · ')}}</text><view v-if="nutritionSummary.length" class="meal-nutrition-summary"><text>{{(state.meal.members||[]).length>1?'全餐合计':'本餐份量'}}</text><text v-for="item in nutritionSummary" :key="item.key">{{item.label}} {{item.value}} {{item.unit}}</text></view></view>
      <view class="detail-section-heading"><text>本餐菜品</text><text>共 {{state.meal.dishes.length}} 道</text></view>
      <button tabindex="0" role="button" v-for="(item,index) in state.meal.dishes" :key="dishKey(item)" class="detail-dish-row" :aria-label="dishTitle(item)" @click="showDish(index)"><FoodImageSlot :src="recipeCover(item)?.image_url" :label="dishTitle(item)" :width="72" :height="72" :radius="18" fallback-icon class="detail-thumb"/><view><text class="detail-dish-name">{{dishTitle(item)}}</text></view></button>


     </template>
     <view v-if="dishOpened&&dish" v-show="state.view==='dish'"><CookingGuide :dishes="[dish]" continuous action=""/></view>
     <template v-if="state.view==='members'"><text class="detail-copy">只调整本餐，确认后重新核对餐单与采购。</text><button tabindex="0" role="button" v-for="member in members" :key="member.id" class="detail-member-choice" :aria-pressed="memberIds.includes(member.id)" :disabled="memberBusy" @click="toggleMember(member.id)"><text>{{member.name}}</text><text>{{memberIds.includes(member.id)?'✓':'○'}}</text></button><text v-if="memberError" class="detail-error">{{memberError}}</text></template>
    </template>
    <view class="detail-bottom-space"/>
   </scroll-view>
   <view class="detail-footer" :class="{'dish-actions':state.view==='dish'}">
    <template v-if="state.view==='members'"><button tabindex="0" role="button" class="detail-secondary" :disabled="busy" @click="requestBack()">取消调整</button><button tabindex="0" role="button" class="detail-primary" :disabled="busy||!memberIds.length||state.phase!=='ready'" @click="saveMembers">{{memberBusy?'正在核对…':'确认成员'}}</button></template>
    <template v-else-if="state.view==='dish'"><button role="button" tabindex="0" class="detail-secondary" :disabled="busy||state.phase!=='ready'||!purchaseScope" @click="showPurchase">购买</button><button role="button" tabindex="0" class="detail-primary" :disabled="busy||state.phase!=='ready'||target.dailyPlanVersion==null||target.date!==localDate()" @click="startCooking">烹饪</button></template>
    <template v-else><button role="button" tabindex="0" class="detail-primary" :disabled="busy||!canPurchase" @click="showPurchase">购买</button></template>
   </view>
   <view v-if="cookingOpen" class="cook-mask" @click.self="!cookingBusy&&(cookingOpen=false)"><view class="cook-sheet" role="dialog" aria-modal="true" aria-label="选择烹饪餐段"><view class="cook-heading"><text>加入今日哪一餐？</text><button role="button" tabindex="0" :disabled="cookingBusy" @click="cookingOpen=false">×</button></view><view class="cook-choices"><button role="button" tabindex="0" v-for="(label,type) in {breakfast:'早餐',lunch:'午餐',dinner:'晚餐'}" :key="type" :aria-pressed="cookingMeal===type" :class="{selected:cookingMeal===type}" :disabled="cookingBusy" @click="cookingMeal=type">{{label}}</button></view><text v-if="cookingError" class="detail-error" role="alert">{{cookingError}}</text><button role="button" tabindex="0" class="detail-primary" :disabled="cookingBusy" @click="confirmCooking">{{cookingBusy?'正在加入…':'确认加入'}}</button></view></view>
   <MealPurchaseSheet v-if="purchaseMounted&&state.phase==='ready'&&canPurchase" ref="purchaseSheet" :open="purchaseOpen" :busy="!!purchaseRef?.isBusy" @close="closePurchase"><CloudMealPurchase :key="key+':'+(purchaseDish?dishKey(purchaseDish):'meal')" ref="purchaseRef" embedded unified :visible="purchaseOpen" :meal="target.purchaseMembers?{...state.meal,members:target.purchaseMembers}:state.meal" :route="purchaseRoute" :reference="purchaseScope?null:referencePurchase" :selection="purchaseScope" @scroll="purchaseSheet?.setScrollTop($event)"/></MealPurchaseSheet>
  </view>
 </DetailOverlay>
</template>
<style scoped>
.meal-detail-panel{--meal-surface:radial-gradient(ellipse at 0% 0%,rgba(125,174,255,.44),transparent 72%),radial-gradient(ellipse at 100% 0%,rgba(206,178,245,.38),transparent 76%),var(--ui-canvas-gradient);position:relative;display:flex;flex-direction:column;width:100%;max-width:480px;margin:0 auto;min-height:0;overflow:hidden;background:var(--meal-surface);border-radius:28px 28px 0 0;color:var(--ui-text);box-sizing:border-box;transition:height 240ms cubic-bezier(.2,.7,.2,1)}
.meal-detail-panel.is-page{height:100vh;height:100dvh;border-radius:0}.detail-grip{display:flex;justify-content:center;align-items:center;height:22px;min-height:22px}.detail-grip>view{width:34px;height:4px;background:#b9bfce;border-radius:4px}
.detail-header{display:flex;align-items:center;gap:12px;padding:8px 18px 20px 20px;flex-shrink:0}.is-page .detail-header{padding-top:calc(var(--detail-safe-top) + 12px)}.detail-header>view{flex:1;min-width:0}.detail-title{display:block;font-size:22px;line-height:1.4;font-weight:600;overflow-wrap:anywhere}.detail-subtitle{display:block;font-size:12px;line-height:1.7;color:#687b96;margin-top:7px}.detail-close,.detail-back,.detail-expand{display:flex;align-items:center;justify-content:center;min-width:44px;min-height:44px;margin:0;padding:0;background:transparent}.detail-close{font-size:28px;color:var(--ui-muted)}.detail-back{font-size:30px;width:44px;margin-left:-10px;border:1px solid var(--ui-bubble-line);border-radius:50%;background:rgba(255,255,255,.6);color:#62738e}.detail-expand{font-size:12px;color:var(--ui-muted)}
.detail-body{height:0;flex:1;min-height:0;box-sizing:border-box;padding:10px 20px 0}.detail-status{font-size:12px;color:var(--ui-muted);margin-bottom:12px}.detail-error{display:block;font-size:14px;line-height:1.8;color:#a63c35;padding:12px 0}.detail-error>text{display:block}.detail-error button{min-height:44px;text-align:left;font-size:14px;color:var(--ui-accent)}
.meal-overview{margin:0 2px 26px}.meal-overview-title{display:block;font-size:22px;line-height:1.5;font-weight:500}.detail-members,.detail-copy{display:block;color:var(--ui-muted);font-size:13px;line-height:1.8;margin-top:9px}.meal-nutrition-summary{display:flex;align-items:center;flex-wrap:wrap;gap:5px 14px;margin-top:12px;font-size:13px;line-height:1.8}.meal-nutrition-summary>text:not(:first-child){font-weight:500}.meal-nutrition-summary>text:first-child{color:var(--ui-muted);font-size:12px}
.detail-section-heading{display:flex;align-items:center;justify-content:space-between;margin:4px 2px 15px;font-size:16px;font-weight:600}.detail-section-heading>text+text{font-size:12px;font-weight:400;color:var(--ui-muted)}.detail-dish-row{display:flex;align-items:center;width:100%;gap:18px;min-height:108px;padding:16px 18px;margin:0 0 14px;border:1px solid var(--ui-bubble-line);border-radius:26px;background:var(--ui-bubble);box-shadow:var(--ui-bubble-shadow);text-align:left}.detail-thumb{width:72px;height:72px;flex-shrink:0;border-radius:18px}.detail-dish-row>view:not(.detail-thumb){flex:1;min-width:0}.detail-dish-name{display:block;font-size:17px;line-height:1.6;font-weight:600;overflow-wrap:anywhere}.detail-dish-row:active{background:rgba(255,255,255,.96)}
.detail-footer{display:flex;gap:10px;flex-shrink:0;background:rgba(255,255,255,.92);padding:16px 20px calc(env(safe-area-inset-bottom) + 14px);border-top:1px solid var(--ui-bubble-line)}.detail-primary,.detail-secondary{display:flex;align-items:center;justify-content:center;min-height:48px;padding:10px 18px;margin:0;box-sizing:border-box;border-radius:99px;font-size:15px;line-height:1.5}.detail-primary{flex:1;background:var(--ui-accent);color:#fff;font-weight:600}.detail-secondary{background:var(--ui-accent-soft);color:var(--ui-accent)}.dish-actions .detail-secondary{flex:1}.detail-member-choice{display:flex;width:100%;justify-content:space-between;align-items:center;min-height:56px;border-bottom:1px solid var(--ui-line);font-size:16px;text-align:left}.detail-bottom-space{height:22px}
.detail-skeleton>view{height:14px;border-radius:14px;margin-bottom:18px;background:#f0f1f3}.detail-skeleton>view:nth-child(3){width:75%}.detail-skeleton .skeleton-image{height:180px}.meal-detail-panel button:after{border:0}.meal-detail-panel button[disabled]{opacity:.45}.detail-body :deep(.guide-action){display:none}
.cook-mask{position:absolute;inset:0;z-index:10;background:var(--ui-overlay);display:flex;align-items:flex-end}.cook-sheet{width:100%;padding:20px 20px calc(env(safe-area-inset-bottom) + 20px);border-radius:24px 24px 0 0;background:var(--ui-surface)}.cook-heading{display:flex;align-items:center;justify-content:space-between;font-size:18px;font-weight:500}.cook-heading button{min-width:44px;min-height:44px;font-size:26px}.cook-choices{display:flex;gap:10px;margin:15px 0 20px}.cook-choices button{flex:1;min-height:48px;border:1px solid var(--ui-line);border-radius:13px;background:var(--ui-soft);font-size:15px}.cook-choices .selected{background:var(--ui-accent-soft);border-color:var(--ui-accent);color:var(--ui-accent)}.cook-sheet>.detail-primary{width:100%}
@media(max-width:350px){.detail-header,.detail-body{padding-left:16px;padding-right:16px}.detail-dish-row{gap:12px;padding:14px}.meal-overview-title{font-size:20px}}@media(prefers-reduced-motion:reduce){.meal-detail-panel{transition:none}}
</style>
