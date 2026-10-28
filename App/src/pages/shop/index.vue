<script setup>
import { openAddressPicker } from '../../services/address-navigation.js'
import { resolveCheckoutAddress } from '../../services/address-model.js'
const demoPreferredAddressId=ref('')
import { isCommerceEnabled } from '../../services/config.js'
import CommerceAccess from '../../components/CommerceAccess.vue'
import CommerceShop from '../../components/CommerceShop.vue'
import CloudMealDetail from '../../components/CloudMealDetail.vue'
import CloudDailyPurchase from '../../components/CloudDailyPurchase.vue'
import ConversationPackagePurchase from '../../components/ConversationPackagePurchase.vue'
import { request } from '../../services/request.js'
const commerceRoute=ref({}), commercePage=ref(false)

import AppNavBar from '../../components/AppNavBar.vue'
import { computed, ref, watch } from 'vue'
import { useMealCommercePage } from '../../services/meal-commerce-page.js'
import { commerce, commerceSessionEpoch } from '../../services/commerce.js'
import { onLoad,onShow,onUnload } from '@dcloudio/uni-app'
import FlowRibbon from '../../components/FlowRibbon.vue'
import DinerPicker from '../../components/DinerPicker.vue'
import MealNotes from '../../components/MealNotes.vue'
import { getProfile,backHome } from '../../utils/profile.js'
import { service as mockService } from '../../services/index.js'
import { createCheckoutQuote,validateCheckoutQuote,checkoutFingerprint } from '../../utils/checkout-state.js'
import { scopedStorage, storageContext as storageScope } from '../../services/storage.js'
import { mockDelay } from '../../services/mock-control.js'
import { getMealMembers, subtotal } from '../../utils/demo.js'
import { isMockMode } from '../../services/config.js'
import { ensureMealPlan } from '../../services/meal-planning.js'
import { ensureExclusivePlan } from '../../services/exclusive-planning.js'
import { createMealBundles } from '../../utils/meal-bundles.js'
import { createDeliveryBatches,getExclusivePlan,adaptExclusivePlan } from '../../utils/exclusive-plans.js'
import { createDemoOrder,getOrder } from '../../utils/orders.js'
import { getDishSwapOptions,getMealSwap,saveMealSwap } from '../../utils/meal-customization.js'
import { createCookingGuide,mealFromRoute,mealToRoute,DAILY_MEALS } from '../../utils/meal-flow.js'
import { mealProfile,localDate,todayPlan,selectedFor,saveSelection,setMealMembers,changeResult,dailyProcurement,mergeDailyProducts } from '../../utils/meal-state.js'
const demoAddress=ref(isCommerceEnabled ? null : mockService.selectedAddress())
const address=computed({get:()=>isCommerceEnabled?mealCommerce.state.address:demoAddress.value,set:value=>{if(isCommerceEnabled)mealCommerce.state.address=value;else demoAddress.value=value}})
function chooseAddress(){if(isCommerceEnabled&&mealCommerce.state.busy)return;openAddressPicker({selectedId:address.value?.id,onSelected:id=>{if(isCommerceEnabled){mealCommerce.state.preferredAddressId=id;mealCommerce.invalidateQuote()}else demoPreferredAddressId.value=id}})}
const meal=ref('晚餐'),profile=ref(getProfile()),revision=ref(0),daily=ref(false),included=ref(['早餐','午餐','晚餐']),dinersOpen=ref(false),updateNote=ref('')
const savedArrangementMeal=ref(null),savedArrangementError=ref('')
const isDiabetesCase=computed(()=>false),caseId=ref('')
const activeSwap=computed(()=>{revision.value;return isCommerceEnabled?null:getMealSwap(meal.value)})
const plan=computed(()=>{
 revision.value
 if(isCommerceEnabled&&savedArrangementMeal.value){
  const saved=savedArrangementMeal.value,base=mealCommerce.plan.value
  const matched=base.packageSn===saved.purchase?.package_sn&&base.packageVersion===saved.purchase?.package_version
  return {...base,...saved,meal:meal.value,count:saved.members.length,sourceType:'api',blocked:[],paid:false,
   dishes:saved.dishes.map(d=>({...d,recipeId:d.id,recipeVersion:d.recipeVersion,detail:d.ingredients.map(i=>i.name).join(' · '),icon:'菜',color:'#ececef'})),
   memberNotes:saved.memberNotes.map(note=>({...note,id:note.memberId,dishes:note.dishes.map(p=>({...p,recipeId:p.dishId,amount:p.grams,unit:'g'})),notes:[JSON.stringify(saved.nutritionSource)]})),
   products:matched?base.products:[],safetyText:'按当前已保存档案、配方及建议熟重计算。明确医嘱优先。'}
 }
 return isCommerceEnabled?mealCommerce.plan.value:todayPlan(profile.value,meal.value)
})
const procurement=computed(()=>{revision.value;return isCommerceEnabled?{products:[],plans:[],blocked:[],selectedIds:[]}:dailyProcurement(profile.value,included.value)})
const blockers=computed(()=>isCommerceEnabled?plan.value.blocked:daily.value?procurement.value.blocked:plan.value.blocked)
const bundleId=ref(''),bundle=computed(()=>(isCommerceEnabled?[]:createMealBundles(plan.value)).find(b=>b.id===bundleId.value))
const sourcePlanId=ref(''),sourcePlan=computed(()=>!isCommerceEnabled&&sourcePlanId.value?adaptExclusivePlan(getExclusivePlan(sourcePlanId.value),profile.value,planStartDate.value||undefined):null)
const sourcePlanReady=computed(()=>sourcePlan.value?.sourceType===(isMockMode?'demo':'api')&&sourcePlan.value.fixturePlans?.length===(isMockMode?2:21))
const products=computed(()=>isCommerceEnabled?plan.value.products:daily.value?procurement.value.products:sourcePlan.value?sourcePlanReady.value?mergeDailyProducts(sourcePlan.value.fixturePlans[0]):[]:bundle.value?plan.value.products.filter(p=>bundle.value.productIds.includes(p.id)):plan.value.products)
const demoSelected=ref([]),orderOpen=ref(false),paid=ref(false),paidOrderId=ref('')
const planStartDate=ref(''),deliveryBatchCount=ref(0)
const deliveryBatches=computed(()=>sourcePlanReady.value&&planStartDate.value?createDeliveryBatches(sourcePlan.value,planStartDate.value,deliveryBatchCount.value||21):[])
const selectedProducts=computed(()=>products.value.filter(p=>selected.value.includes(p.id)))
const productsSubtotalCents=computed(()=>subtotal(products.value,selected.value))
const totalCents=computed(()=>sourcePlan.value&&deliveryBatches.value.length?sourcePlan.value.totalEstimateCents:productsSubtotalCents.value)
const total=computed(()=>(totalCents.value/100).toFixed(2))
const mealCommerce=isCommerceEnabled?useMealCommercePage(()=>({enabled:!commercePage.value, meal:mealToRoute(meal.value), date:commerceRoute.value.date||localDate(), packageSn:savedArrangementMeal.value?.purchase?.package_sn, packageVersion:savedArrangementMeal.value?.purchase?.package_version, members:getMealMembers(mealProfile(profile.value,meal.value,commerceRoute.value.date||localDate())), unsupported:daily.value||!!sourcePlanId.value||!!bundleId.value})):null
const selected=computed({get:()=>isCommerceEnabled?mealCommerce.state.selected:demoSelected.value,set:value=>{if(isCommerceEnabled)mealCommerce.state.selected=value;else demoSelected.value=value}})
const checkoutQuote=computed(()=>mealCommerce?.state.quote)
const commerceBusy=computed(()=>mealCommerce?.state.busy||false)
const commerceError=computed(()=>mealCommerce?.state.error||'')
const checkoutError=computed(()=>mealCommerce?.state.checkoutError||'')
const pendingCommerceOrder=computed(()=>mealCommerce?.state.pending)
const createdCommerceOrder=computed(()=>mealCommerce?.state.orderSn)
const deliverySlots=computed(()=>mealCommerce?.state.slots||[])
const deliveryMessage=computed(()=>mealCommerce?.state.deliveryMessage||'')
const money=value=>(Number(value||0)/100).toFixed(2)
async function reloadCommerce(){
  if(!isMockMode&&commerceRoute.value.arrangement&&commerceRoute.value.purchase!=='1')return
  if(!isCommerceEnabled||commercePage.value||!commerce.session()?.token)return
  profile.value=getProfile()
  if(!isMockMode&&commerceRoute.value.arrangement){
   savedArrangementError.value=''
   try{
    const options=commerceRoute.value
    const {data}=await request({path:'/api/family/'+encodeURIComponent(profile.value.householdId)+'/daily-arrangements/'+options.date+'/meals/'+options.meal+'?arrangement_id='+encodeURIComponent(options.arrangement)+'&version='+Number(options.version)})
    if(disposed)return
    if(data.arrangement_id!==options.arrangement||data.version!==Number(options.version))throw new Error('本餐安排已更新，请返回重新读取。')
    savedArrangementMeal.value=data.meal
   }catch(error){savedArrangementMeal.value=null;savedArrangementError.value=error.message;return}
  }
  await mealCommerce.load()
  if(savedArrangementMeal.value&&mealCommerce.state.menu&&(mealCommerce.state.menu.package_sn!==savedArrangementMeal.value.purchase?.package_sn||mealCommerce.state.menu.package_version!==savedArrangementMeal.value.purchase?.package_version)){
   mealCommerce.state.ready=false;mealCommerce.state.error='采购内容已更新，请重新核对本餐食材。'
  }
  if(checkoutRequested&&mealCommerce.state.ready&&!mealCommerce.state.error){checkoutRequested=false;await checkout()}
}
async function submitCommerceOrder(){
  profile.value=getProfile()
  const result=await mealCommerce.submit()
  if(result)uni.navigateTo({url:'/pages/orders/detail?id='+encodeURIComponent(result.order_sn)})
}
async function recoverCommerceOrder(){const result=await mealCommerce.recover();if(result)uni.navigateTo({url:'/pages/orders/detail?id='+encodeURIComponent(result.order_sn)})}
function setQuantity(product,delta){mealCommerce.quantity(product.id,Math.min(product.availableQuantity,product.quantity+delta))}
function selectSlot(slot){if(commerceBusy.value)return;mealCommerce.state.slotId=slot.id;mealCommerce.invalidateQuote()}
if(isCommerceEnabled)watch(commerceSessionEpoch,()=>{if(!mealCommerce.state.ready){profile.value=getProfile();orderOpen.value=false;dinersOpen.value=false;updateNote.value=''}})
let knownProducts=[],quote=null,disposed=false,menuVersion=0,retryMenu=null,checkoutRequested=false
const menuUpdating=ref(false),menuError=ref('')
const paying=ref(false),payError=ref(''),paymentState=ref('idle'),paidTotal=ref('')
onUnload(()=>{disposed=true;menuVersion++})
function quoteInput(){return {scope:storageScope(),profileVersion:profile.value.revision||0,members:plan.value.members.map(m=>m.id),dishes:plan.value.dishes,products:selectedProducts.value,address:address.value,meal:meal.value,included:included.value,sourcePlan:sourcePlanId.value,generation:sourcePlan.value?.generation||plan.value.generationId,memberNotes:plan.value.memberNotes,start:planStartDate.value,batches:deliveryBatchCount.value,totalCents:totalCents.value}}
function choosePaymentResult(){return new Promise((resolve,reject)=>uni.showActionSheet({itemList:['测试：支付成功','测试：取消支付','测试：支付失败','测试：结果待确认'],success:({tapIndex})=>resolve(['success','cancel','failure','unknown'][tapIndex]),fail:e=>/cancel/i.test(e.errMsg||'')?resolve('cancel'):reject(new Error('支付窗口未能打开，请重试'))}))}

function refreshSelection(){
 selected.value=daily.value?procurement.value.selectedIds:selectedFor(meal.value,products.value)
 knownProducts=products.value.map(p=>[p.id,p.quantity])
}
onLoad(options=>{commerceRoute.value=options;commercePage.value=isCommerceEnabled&&options.commerce==='1'&&!options.meal;if(commercePage.value)return;meal.value=mealFromRoute(options.meal);daily.value=options.daily==='1';bundleId.value=options.bundle||'';sourcePlanId.value=options.source==='exclusive-plan'?(options.plan||'balanced'):'';planStartDate.value=options.start||'';deliveryBatchCount.value=Number(options.batches||0);checkoutRequested=options.checkout==='1'||options.verify==='1';if(isCommerceEnabled)return;refreshSelection();const reorder=options.reorder?getOrder(options.reorder):null;if(reorder){selected.value=products.value.filter(p=>reorder.items.some(i=>i.id===p.id)).map(p=>p.id);saveSelection(meal.value,products.value,selected.value);}checkoutRequested=options.checkout==='1'||options.verify==='1'})
onShow(async()=>{if(commercePage.value)return;if(isCommerceEnabled){await reloadCommerce();return;}profile.value=getProfile();if(!isMockMode)await refreshPlans();if(disposed)return;address.value=resolveCheckoutAddress(await mockService.addresses(),demoPreferredAddressId.value||mockService.selectedAddress()?.id);revision.value++;refreshSelection();if(orderOpen.value&&!paid.value&&quote&&quote.signature!==checkoutFingerprint(quoteInput())){orderOpen.value=false;updateNote.value='成员、菜品、地址或报价已变化，请重新核对结算。'}if(checkoutRequested&&!menuError.value){checkoutRequested=false;checkout()}})
function toggle(id){if(isCommerceEnabled){mealCommerce.toggle(id);return;}if(paying.value)return;const i=selected.value.indexOf(id);i<0?selected.value.push(id):selected.value.splice(i,1);saveSelection(daily.value?'今日采购':meal.value,products.value,selected.value);if(daily.value){for(const p of procurement.value.plans){const ids=selectedFor(p.meal,p.products);const index=ids.indexOf(id);if(selected.value.includes(id)&&index<0)ids.push(id);else if(!selected.value.includes(id)&&index>=0)ids.splice(index,1);saveSelection(p.meal,p.products,ids)}}}
function toggleMeal(value){if(paying.value)return;const i=included.value.indexOf(value);i<0?included.value.push(value):included.value.splice(i,1);revision.value++;refreshSelection()}
async function checkout(){
 if(isCommerceEnabled){if(commerceBusy.value)return;orderOpen.value=true;profile.value=getProfile();await mealCommerce.prepare();return}

 if(paying.value||menuUpdating.value||menuError.value||blockers.value.length||sourcePlan.value?.blocked.length||(sourcePlanId.value&&!sourcePlanReady.value))return
 if(!selected.value.length)return uni.showToast({title:'请至少选择一件食材',icon:'none'})
 if(paymentState.value==='unknown'){orderOpen.value=true;return}
 paid.value=false;paidOrderId.value='';paymentState.value='idle';payError.value='';quote=createCheckoutQuote(quoteInput());orderOpen.value=true
}
async function pay(){
 if(paying.value||menuUpdating.value||menuError.value||paymentState.value==='unknown')return
 if(!address.value){payError.value='请选择配送地址';return}
 const scope=storageScope();paying.value=true;payError.value=''
 try{
   profile.value=getProfile();revision.value++
   if(blockers.value.length||sourcePlan.value?.blocked.length||(sourcePlanId.value&&!sourcePlanReady.value))throw new Error('饮食限制或计划已变化，请重新检查菜单')
   validateCheckoutQuote(quote,quoteInput())
   const result=await choosePaymentResult()
   if(disposed||scope!==storageScope())return
   validateCheckoutQuote(quote,quoteInput())
   if(result==='cancel'&&!paidOrderId.value){paymentState.value='cancelled';payError.value='已取消支付，可以继续核对后重试';return}
   if(!paidOrderId.value){
     const plans=daily.value?procurement.value.plans:[plan.value]
     const guides=sourcePlan.value?deliveryBatches.value.map(batch=>({index:batch.index,guides:batch.meals.map(meal=>createCookingGuide(plan.value,sourcePlan.value,{batchIndex:batch.index,meal:meal.type}))})):daily.value?[{index:1,guides:plans.map(p=>createCookingGuide(p))}]:[]
     const order=await mockService.createOrder({clientRequestId:quote.clientRequestId,addressSnapshot:address.value,items:selectedProducts.value,totalCents:totalCents.value,meal:daily.value?'今日三餐':meal.value,sourcePlanId:sourcePlanId.value,planName:sourcePlan.value?.name||'',bundleId:bundleId.value,deliveryBatches:deliveryBatches.value,cookingGuide:createCookingGuide(plan.value,sourcePlan.value),cookingGuides:guides})
     if(disposed||scope!==storageScope())return
     paidOrderId.value=order.id;paidTotal.value=(order.totalCents/100).toFixed(2)
   }
   // If a payment call times out after order creation, query first instead of repeating payment.
   paymentState.value='unknown'
   const order=await mockService.payOrder(paidOrderId.value,result)
   if(disposed||scope!==storageScope())return
   applyPayment(order)
 }catch(e){if(!disposed&&scope===storageScope())payError.value=e.message||'支付未完成，请查询订单结果'}
 finally{paying.value=false}
}
function applyPayment(order){
 if(!order)throw new Error('订单结果暂不可用，请重试查询')
 paymentState.value=order.paymentStatus||'unknown';paid.value=paymentState.value==='paid'
 if(paid.value)paidTotal.value=(order.totalCents/100).toFixed(2)
 payError.value=paid.value?'':paymentState.value==='unknown'?'支付结果待确认，请查询订单，勿重复支付':paymentState.value==='failed'?'支付失败，可重试同一订单':paymentState.value==='cancelled'?'已取消支付，可重试同一订单':'订单尚未确认支付'
}
async function queryPayment(){
 if(paying.value||!paidOrderId.value)return;const scope=storageScope();paying.value=true;payError.value=''
 try{const order=await mockService.paymentResult(paidOrderId.value);if(!disposed&&scope===storageScope())applyPayment(order)}catch(e){if(scope===storageScope())payError.value=e.message||'查询失败，请重试'}finally{paying.value=false}
}

function viewOrder(){uni.navigateTo({url:'/pages/orders/detail?id='+encodeURIComponent(paidOrderId.value)})}
function nutritionist(){uni.reLaunch({url:'/pages/chat/index'})}
function openDish(dish){if(savedArrangementMeal.value){const r=commerceRoute.value;uni.navigateTo({url:'/pages/recipe/index?arrangement='+encodeURIComponent(r.arrangement)+'&meal='+r.meal+'&date='+r.date+'&version='+r.version+'&dish='+encodeURIComponent(dish.id)});return}if(isCommerceEnabled){uni.navigateTo({url:'/pages/recipe/index?commerce=1&meal='+mealToRoute(meal.value)+'&date='+encodeURIComponent(mealCommerce.state.menu.date)+'&package='+encodeURIComponent(plan.value.packageSn)+'&packageVersion='+plan.value.packageVersion+'&recipe='+encodeURIComponent(dish.recipeId)+'&version='+encodeURIComponent(dish.recipeVersion)});return;}uni.navigateTo({url:'/pages/recipe/index?meal='+mealToRoute(meal.value)+'&dish='+encodeURIComponent(dish.name)+(plan.value.paid?'&id='+plan.value.orderId+'&batch='+plan.value.batchIndex:'' )})}
function changeDiners(){dinersOpen.value=true}
async function updateMenu(work,retry){
 const version=++menuVersion,scope=storageScope();menuUpdating.value=true;menuError.value='';retryMenu=retry;orderOpen.value=false;quote=null
 try{await mockDelay('menu');if(disposed||version!==menuVersion||scope!==storageScope())return;await work()}
 catch(e){if(!disposed&&version===menuVersion&&scope===storageScope())menuError.value=e.message||'更新失败，请重试'}
 finally{if(version===menuVersion)menuUpdating.value=false}
}
async function refreshPlans(){
 return updateMenu(async()=>{
   if(sourcePlanId.value)await ensureExclusivePlan(getExclusivePlan(sourcePlanId.value),profile.value,{startDate:planStartDate.value||undefined})
   else await Promise.all((daily.value?included.value:[meal.value]).map(name=>ensureMealPlan(profile.value,name)))
   if(disposed)return;revision.value++;refreshSelection()
 },refreshPlans)
}
function discuss(){uni.navigateTo({url:'/pages/chat/index?meal='+mealToRoute(meal.value)})}
function chooseDinersFor(name){meal.value=name;changeDiners()}
function retryMenuUpdate(){if(retryMenu&&!menuUpdating.value)return retryMenu()}
async function confirmDiners(ids){
  if(savedArrangementMeal.value){
   if(menuUpdating.value)return
   menuUpdating.value=true;menuError.value=''
   try{
    const {newHealthRequestId}=await import('../../services/health-task-flow.js')
    const r=commerceRoute.value,key='daily-arrangement-change:'+r.arrangement,scope=storageScope()
    let pending=scopedStorage.getStorageSync(key)
    if(!pending){const id=newHealthRequestId();pending={client_request_id:id,version:Number(r.version),meal:r.meal,member_ids:ids};scopedStorage.setStorageSync(key,pending)}
    await request({path:'/api/family/'+encodeURIComponent(profile.value.householdId)+'/daily-arrangements/'+r.date+'/members',method:'POST',headers:{'Idempotency-Key':pending.client_request_id},data:pending})
    if(disposed||scope!==storageScope())return
    scopedStorage.setStorageSync(key,null)
    dinersOpen.value=false;uni.redirectTo({url:'/pages/chat/index'})
   }catch(error){menuError.value=error.message}finally{menuUpdating.value=false}
   return
  }
 if(isCommerceEnabled){if(commerceBusy.value)return;setMealMembers(profile.value,meal.value,ids,commerceRoute.value.date||localDate());profile.value=getProfile();mealCommerce.membersChanged();orderOpen.value=false;dinersOpen.value=false;updateNote.value=mealCommerce.state.contextIssue;return;}if(paying.value)return;const before=plan.value,previous=[...selected.value],targetMeal=meal.value
 return updateMenu(async()=>{saveSelection(targetMeal,products.value,previous);setMealMembers(profile.value,targetMeal,ids);await ensureMealPlan(profile.value,targetMeal);if(disposed)return;revision.value++;refreshSelection();updateNote.value=changeResult(before,plan.value,previous);dinersOpen.value=false},()=>confirmDiners(ids))
}
function canSwapDish(dish){if(isCommerceEnabled)return false;return !plan.value.paid&&getDishSwapOptions(meal.value,dish.name,plan.value.members).length>0}
function applySwap(option){const targetMeal=meal.value;return updateMenu(async()=>{saveSelection(targetMeal,products.value,selected.value);saveMealSwap(targetMeal,option);await ensureMealPlan(profile.value,targetMeal);if(disposed)return;revision.value++;refreshSelection();updateNote.value='菜品、营养、做法、食材包装数量与预计金额已同步更新。'},()=>applySwap(option))}
function switchDish(dish){if(isCommerceEnabled){uni.showToast({title:'换菜服务尚未接入，请在对话中说明需求',icon:'none'});return;}if(paying.value||menuUpdating.value)return;const options=getDishSwapOptions(meal.value,dish.name,plan.value.members);if(!options.length)return;uni.showActionSheet({itemList:options.map(o=>o.name+' · '+o.direction),success:({tapIndex})=>applySwap(options[tapIndex]),fail:e=>{if(!/cancel/i.test(e.errMsg||'')){retryMenu=()=>switchDish(dish);menuError.value='换菜窗口未能打开，请重试'}}})}

function editProfile(){uni.navigateTo({url:isMockMode?'/pages/profile/index':'/pages/family-shared/index'})}
</script>
<template>
<ConversationPackagePurchase v-if="!isMockMode && commerceRoute.conversation" :route="commerceRoute"/>
<CloudDailyPurchase v-else-if="!isMockMode && commerceRoute.arrangement && commerceRoute.daily==='1'" :route="commerceRoute"/>
<CloudMealDetail v-else-if="!isMockMode && commerceRoute.arrangement && commerceRoute.purchase!=='1'" :route="commerceRoute"/>
<CommerceAccess v-else :enabled="isCommerceEnabled" @ready="reloadCommerce"><CommerceShop v-if="commercePage && commerceRoute.cart==='1'" :route="commerceRoute"/><view v-else-if="commercePage" class="screen"><text>请返回 AI 首页选择餐单或询问食材包。</text><button @click="nutritionist">返回营养师</button></view>

  <view v-else class="screen shop-screen" :class="{'cloud-meal-screen':!isMockMode}">
    <AppNavBar><view class="nav-row"><button class="icon-button" @click="backHome">‹</button><text class="nav-title">{{ daily ? '今日采购清单' : sourcePlan ? '食材商城' : meal + '安排与购买' }}</text><text class="pill">{{isCommerceEnabled?(plan.isLocalFixture?'本地联调':'商城'):'演示'}}</text></view></AppNavBar>
    <FlowRibbon :current="orderOpen ? 4 : 3" class="shop-flow" />
    <view v-if="savedArrangementError" class="card commerce-message"><text>{{savedArrangementError}}</text><button class="secondary-button" @click="reloadCommerce">重新读取本餐安排</button></view>
    <view v-if="!savedArrangementError && (blockers.length || sourcePlan?.blocked.length) && isMockMode" class="card safety-card">
      <view><text>本餐需要调整</text><text class="small">{{ [...new Set([...blockers,...(sourcePlan?.blocked||[])])].join('；') }}</text><button class="secondary-button" :disabled="menuUpdating" @click="discuss">在对话中补充信息</button><button v-if="!daily" class="secondary-button" :disabled="menuUpdating" @click="changeDiners">调整本餐成员</button><button v-for="name in daily?included:[]" :key="name" class="secondary-button" @click="chooseDinersFor(name)">调整{{name}}成员</button><button class="secondary-button" @click="editProfile">核对已有档案</button></view>
    </view>
      <view class="shop-head"><text class="eyebrow">{{ isDiabetesCase ? '虚拟糖尿病家庭案例 · 一桌共享菜单' : sourcePlan ? 'AI专属计划 · 首批采购' : '本餐安排与购买清单 · 同一页面' }}</text><text class="display-title">{{daily?'把今天三餐，一次备齐':sourcePlan?'核对计划，准备开始':meal+'安排与购买'}}</text><text class="shop-desc">{{ isCommerceEnabled ? '先看本餐菜品与做法，再勾选需要的商城食材。采购量调整不会自动重新计算营养与个人份量。' : isDiabetesCase ? '已按三人共享晚餐汇总菜品与食材。商品与价格均为演示；爸爸的实际主食份量仍需按专业要求确认。' : sourcePlan ? sourcePlan.name + '已自动检查已知饮食限制并安排' + (deliveryBatches.length || 21) + '次配送确认。这里演示首批食材采购。' : '先看本餐菜品与做法，再直接勾选需要购买的整包装食材。' }}</text></view>
      <view v-if="!daily" class="meal-summary-card"><view class="summary-title"><view><text class="eyebrow">本餐基本信息</text><text>{{meal}} · {{plan.count}} 人用餐</text></view></view><button class="diner-control" @click="changeDiners"><text class="diner-names">就餐者：{{plan.members.map(m=>m.name).join('、')}}</text><text class="diner-change">更改 ›</text></button><MealNotes :plan="plan"/></view>
      <view v-else class="card daily-meals"><text class="section-title">选择今日需要采购的餐次</text><button v-for="m in DAILY_MEALS" :key="m.name" @click="toggleMeal(m.name)">{{included.includes(m.name)?'✓':'○'}} {{m.name}}</button><text class="demo-label">跨餐合并同一食材与 SKU 后计算包装数量；仍需核对商品、地址和金额后结算。</text></view>
      <text v-if="isCommerceEnabled" class="safe-note">{{savedArrangementMeal?'已保存安排 · 按逐人熟重与配方汇总':plan.isLocalFixture?'本地联调菜单与商品 · 未经个体化营养评估':'服务端已保存菜单 · 个体化营养与个人份量尚未接入'}}</text><text v-if="commerceBusy" class="safe-note">正在核对菜单、商品和配送…</text><view v-if="commerceError" class="card commerce-message"><text class="inline-error">{{commerceError}}</text><button class="secondary-button" :disabled="commerceBusy" @click="reloadCommerce">重新读取本餐安排</button></view><view v-if="isCommerceEnabled && (pendingCommerceOrder || createdCommerceOrder)" class="card commerce-message"><text>{{createdCommerceOrder?'订单已创建，请前往订单详情继续处理':'上次下单结果尚未确认，请重试原订单，避免重复购买'}}</text><button class="primary-button" :disabled="commerceBusy" @click="recoverCommerceOrder">{{createdCommerceOrder?'查看已创建订单':'重试并确认原订单'}}</button></view><text v-if="menuUpdating" class="safe-note">正在复核成员、菜单和报价…</text><view v-if="menuError" class="card"><text class="inline-error">{{menuError}}</text><button :disabled="menuUpdating" @click="retryMenuUpdate">重试更新</button></view>
      <text v-if="updateNote" class="update-note">{{updateNote}}</text>
      <view v-if="bundle" class="bundle-card">
        <view class="bundle-top"><view><text>{{ bundle.name }}</text><text class="small">按 {{ plan.count }} 位成员的菜单需求匹配 · 示例商品</text></view><view class="bundle-badge">单包</view></view>
        <image v-if="bundle" class="selected-bundle-image" :src="bundle.image" mode="aspectFill" />
      </view>
      <view v-if="!daily" class="section-head"><text class="section-title">本餐全部菜品</text><text>点击查看独立做法页</text></view>
      <view v-if="!daily" class="dish-list"><view v-for="dish in plan.dishes" :key="dish.name" class="dish-card card"><button class="dish-main" @click="openDish(dish)"><view class="dish-visual" :style="{background:dish.color}"><image v-if="dish.image" :src="dish.image" mode="aspectFill"/><text v-else>{{dish.icon}}</text></view><view><text>{{dish.name}}</text><text>{{dish.detail}}</text><text>{{dish.kcal?'约 '+dish.kcal+' kcal · ':''}}查看做法与注意事项</text></view><text>›</text></button><button v-if="canSwapDish(dish)" class="swap-button" :disabled="menuUpdating||paying||commerceBusy" @click="switchDish(dish)">换一换</button></view></view>
      <view class="section-head ingredient-head"><view><text class="section-title">{{daily?'今日所需食材和购买清单':'本餐所需食材和购买清单'}}</text><text>{{isCommerceEnabled?'按已保存菜单匹配包装，可调整采购数量':'包装数量按本餐人数计算'}}</text></view><text>已选 {{ selected.length }} 项</text></view>
      <view class="product-list">
        <view v-for="product in products" :key="product.id" class="product-card card" @click="toggle(product.id)">
          <view class="select-box" :class="{ selected: selected.includes(product.id) }">{{ selected.includes(product.id) ? '✓' : '' }}</view>
          <view class="product-image"><image v-if="product.imageUrl" :src="product.imageUrl" mode="aspectFill"/><text v-else>{{ product.icon }}</text></view>
          <view class="product-copy"><text>{{ product.name }}</text><text class="small">{{isCommerceEnabled?product.needLabel:'需要 '+product.need+product.unit}}</text><text class="em">{{isCommerceEnabled?product.packLabel:product.pack+product.unit+'/包'}} × {{ product.quantity }} 包</text><text v-if="isCommerceEnabled" class="small">¥{{money(product.priceCents)}} / 包 · 可售 {{product.availableQuantity}} 包</text><view v-if="isCommerceEnabled" class="quantity-control" @click.stop><button :disabled="commerceBusy||product.quantity<=1" @click.stop="setQuantity(product,-1)">−</button><text>{{product.quantity}}</text><button :disabled="commerceBusy||product.quantity>=product.availableQuantity" @click.stop="setQuantity(product,1)">＋</button></view></view>
          <text class="price">¥{{ (product.priceCents * product.quantity / 100).toFixed(2) }}</text>
        </view>
      </view>
      <view v-if="isCommerceEnabled && !products.length && !commerceBusy" class="card commerce-message"><text>这一餐暂无可购买食材，请先确认菜单或稍后重试。</text></view><view class="safety-card"><view class="shield">i</view><view><text>结算前核对采购内容</text><text class="small">{{isCommerceEnabled?'核对商品、包装数量、配送范围与后端报价。菜单尚未完成个体化营养与个人份量评估，请结合已知饮食限制确认。':'商品、包装数量、配送地址和价格。饮食限制已在推荐前自动检查。当前为购买流程演示，不会生成真实订单或扣款。'}}</text></view></view>
      <view class="bottom-bar"><view><text>已选 {{selected.length}} 项</text><text class="strong">¥{{ total }}</text><text class="small">{{isCommerceEnabled?'商品小计 · 运费结算确认':'示例合计'}}</text></view><button v-if="!plan.paid && (!daily || procurement.plans.every(p=>!p.paid))" class="primary-button" :disabled="commerceBusy||(isCommerceEnabled&&(!mealCommerce.state.ready||!selected.length||!!pendingCommerceOrder||!!createdCommerceOrder))||menuUpdating||paying||Boolean(menuError)||Boolean(blockers.length)||Boolean(sourcePlan?.blocked.length)" @click="checkout">去结算／直接购买 →</button></view>
    <DinerPicker :open="dinersOpen" :members="profile.members" :selected="plan.members.map(m=>m.id)" :meal="meal" @close="dinersOpen=false" @confirm="confirmDiners"/>
    <view v-if="orderOpen" class="sheet-mask"><view class="sheet order-sheet">
      <template v-if="isCommerceEnabled">
        <view class="order-title"><view><text class="eyebrow">本餐食材订单</text><text class="section-title">确认订单</text></view><button :disabled="commerceBusy" @click="orderOpen=false">×</button></view>
        <view class="delivery-card" @click="chooseAddress"><view class="delivery-icon">⌂</view><view><text>{{address?address.name+' · '+address.phone:'请选择配送地址'}}</text><text>{{address?address.region+' '+address.detail:'选择地址后核对配送范围与价格'}}</text></view><text>›</text></view>
        <view v-if="checkoutQuote" class="order-lines"><view v-for="item in checkoutQuote.items" :key="item.sku_id"><text>{{item.snapshot?.product_name}} × {{item.quantity}}</text><text>¥{{money(item.line_amount_cent)}}</text></view></view><view v-else class="order-lines"><view v-for="product in selectedProducts" :key="product.id"><text>{{product.name}} × {{product.quantity}}</text><text>¥{{money(product.priceCents*product.quantity)}}</text></view></view>
        <view v-if="deliverySlots.length" class="delivery-options"><text class="section-title">配送时段</text><button v-for="slot in deliverySlots" :key="slot.id" :disabled="commerceBusy" :class="{chosen:String(mealCommerce.state.slotId)===String(slot.id)}" @click="selectSlot(slot)">{{slot.name||slot.start_time+'—'+slot.end_time}} · ¥{{money(slot.extra_fee_cent)}}</button></view><text v-if="deliveryMessage" class="inline-error">{{deliveryMessage}}</text>
        <view v-if="checkoutQuote" class="price-lines"><view><text>商品金额</text><text>¥{{money(checkoutQuote.goods_amount_cent)}}</text></view><view><text>配送费</text><text>¥{{money(checkoutQuote.shipping_fee_cent)}}</text></view><view><text>优惠</text><text>−¥{{money(checkoutQuote.discount_amount_cent)}}</text></view><view class="pay-total"><text>应付金额</text><text>¥{{money(checkoutQuote.payable_amount_cent)}}</text></view></view>
        <text class="demo-label">{{checkoutQuote?'配送地址、范围和价格已由后端核对。提交后在订单详情完成支付，并以服务端支付状态为准。':'请先选择地址并核对商品与价格。'}}</text><text v-if="checkoutError" class="inline-error">{{checkoutError}}</text>
        <button v-if="pendingCommerceOrder || createdCommerceOrder" class="primary-button" :disabled="commerceBusy" @click="recoverCommerceOrder">{{createdCommerceOrder?'查看已创建订单':'重试并确认原订单'}}</button><button v-else-if="checkoutQuote" class="primary-button" :disabled="commerceBusy" @click="submitCommerceOrder">{{commerceBusy?'正在提交…':'确认下单 ¥'+money(checkoutQuote.payable_amount_cent)}}</button><button v-else class="primary-button" :disabled="commerceBusy" @click="checkout">{{commerceBusy?'正在核对…':'核对商品与价格'}}</button><button class="secondary-button" :disabled="commerceBusy" @click="orderOpen=false">返回调整商品</button>
      </template>
      <template v-else-if="!paid">
        <view class="order-title"><view><text class="eyebrow">演示订单</text><text class="section-title">确认订单</text></view><button :disabled="paying" @click="orderOpen = false">×</button></view>
        <view class="delivery-card" @click="chooseAddress">
          <view class="delivery-icon">⌂</view>
          <view><text>{{address?address.name+' · '+address.phone:'请选择配送地址'}}</text><text>{{address?address.region+' '+address.detail:'点击选择或新增测试地址'}}</text></view>
          <text>›</text>
        </view>
        <view class="order-lines">
          <view v-for="product in selectedProducts" :key="product.id"><text>{{ product.name }} × {{ product.quantity }}</text><text>¥{{ (product.priceCents * product.quantity / 100).toFixed(2) }}</text></view>
        </view>
        <view class="delivery-time"><text>预计送达</text><text>{{sourcePlan?planStartDate+' 起逐批配送':'测试时段 · 18:00–19:00'}}</text></view>
        <view v-if="deliveryBatches.length" class="delivery-time"><text>计划配送</text><text>{{ deliveryBatches.length }} 次 · {{ planStartDate }} 生效 ›</text></view>
        <view class="price-lines"><view><text>首批三餐商品价（测试）</text><text>¥{{ sourcePlan ? (sourcePlan.estimateCents / 100).toFixed(2) : (productsSubtotalCents / 100).toFixed(2) }}</text></view><view v-if="sourcePlan"><text>21批商品价（测试）</text><text>¥{{ total }}</text></view><view><text>计划服务费</text><text>¥0.00 · 待定稿</text></view><view><text>配送费</text><text>¥0.00 · 待定稿</text></view><view class="pay-total"><text>一次支付（测试）</text><text>¥{{ total }}</text></view></view>
        <text class="demo-label">此页面仅演示“直接购买”的完整操作，不会调用真实支付。测试地址与模拟订单仅保存在本机。</text>
        <text v-if="payError" class="inline-error">{{payError}}</text><button v-if="paymentState==='unknown'" class="primary-button" :disabled="paying" @click="queryPayment">{{paying?'正在查询…':'查询支付结果'}}</button><button v-else class="primary-button" :disabled="paying" @click="pay">{{paying?'正在处理…':'模拟支付 ¥'+total}}</button><button v-if="paidOrderId" class="secondary-button" :disabled="paying" @click="viewOrder">查看当前订单</button>
        <button class="secondary-button" :disabled="paying" @click="orderOpen = false">返回调整商品</button>
      </template>
      <template v-else>
        <view class="success-mark">✓</view>
        <text class="section-title success-title">购买成功 · 演示订单</text>
        <text class="demo-label success-copy">已模拟支付 ¥{{ paidTotal }}，订单当前为“待配送”。本原型不会产生真实配送。</text>
        <view class="status-track"><view class="done"><text>1</text><text>已模拟支付</text></view><view></view><view><text>2</text><text>商家备货</text></view><view></view><view><text>3</text><text>配送完成</text></view></view>
        <button class="primary-button" @click="viewOrder">查看订单 →</button>
        <button class="secondary-button" @click="nutritionist">返回营养师</button>
      </template>
    </view></view>
  </view>
</CommerceAccess>
</template>
<style scoped>
.commerce-message{margin-top:24rpx;padding:24rpx;display:flex;flex-direction:column;gap:18rpx;line-height:1.7}.product-image image,.dish-visual image{width:100%;height:100%;border-radius:inherit}.product-image>text{font-size:25rpx}.quantity-control{display:flex;align-items:center;gap:18rpx;margin-top:8rpx}.quantity-control button{margin:0;padding:4rpx 16rpx;font-size:25rpx;border:1rpx solid #dfe1e6;border-radius:12rpx}.quantity-control text{font-size:25rpx}.delivery-options{display:flex;flex-direction:column;gap:12rpx;margin-top:18rpx}.delivery-options button{padding:16rpx;border:1rpx solid #dfe1e6;border-radius:18rpx;text-align:left;font-size:25rpx}.delivery-options .chosen{background:#f0f1f4;color:#292a2e}
.daily-meals{margin-top:28rpx;padding:26rpx;display:flex;flex-direction:column;gap:20rpx}.daily-meals button{padding:20rpx;border:1rpx solid #d3dfcc;border-radius:18rpx;color:#292a2e;text-align:left;font-size:26rpx}.update-note{display:block;padding:22rpx;margin-top:20rpx;background:#e6efdc;border-radius:22rpx;font-size:25rpx;line-height:1.7}
.selected-bundle-image { display: block; width: 100%; height: 260rpx; margin-top: 24rpx; border-radius: 22rpx; }
.shop-screen { padding-bottom: calc(env(safe-area-inset-bottom) + 190rpx); }.shop-flow { margin-top: 20rpx; }.shop-head { margin-top: 54rpx; }.shop-head .display-title { display: block; font-size: 52rpx; }.shop-desc { display: block; margin-top: 22rpx; color: #6e6e78; font-size:25rpx; line-height: 1.75; }
.meal-summary-card{margin-top:30rpx;padding:26rpx;border-radius:30rpx;background:#292a2e;color:white;box-shadow:0 18rpx 40rpx rgba(31,107,82,.18)}.summary-title{display:flex;align-items:flex-start;justify-content:space-between}.summary-title>view{display:flex;flex-direction:column;gap:8rpx}.summary-title .eyebrow{color:#f0f1f4}.summary-title>view text:last-child{font-family:inherit;font-size:32rpx;font-weight:500}.summary-title>text:last-child{padding:8rpx 12rpx;border-radius:999rpx;background:rgba(255,255,255,.14);font-size:25rpx}.nutrition-strip{display:grid;grid-template-columns:repeat(3,1fr);gap:10rpx;margin-top:22rpx}.nutrition-strip>view{display:flex;flex-direction:column;gap:5rpx;padding:16rpx;border-radius:18rpx;background:rgba(255,255,255,.11)}.nutrition-strip text:first-child{font-size:25rpx;font-weight:500}.nutrition-strip text:last-child{color:#d2e6d7;font-size:25rpx}.diner-control{width:100%;display:flex;align-items:center;justify-content:space-between;gap:20rpx;margin-top:20rpx;padding:6rpx 0;min-height:60rpx;border-radius:0;background:transparent;color:#fff;text-align:left;font-size:25rpx;line-height:1.7}.diner-control::after{border:0}.diner-names{min-width:0;overflow-wrap:anywhere}.diner-change{color:#d2f19e;font-weight:500;white-space:nowrap;flex-shrink:0}
.bundle-card { margin-top: 32rpx; padding: 28rpx; overflow: hidden; border-radius: 34rpx; background: #292a2e; color: white; box-shadow: 0 20rpx 45rpx rgba(31,107,82,.2); }.bundle-top { display: flex; align-items: flex-start; justify-content: space-between; }.bundle-top view:first-child { display: flex; flex-direction: column; gap: 10rpx; }.bundle-top text { font-family:inherit; font-size: 34rpx; font-weight:500; }.bundle-top .small { color: #cde0d2; font-size:25rpx; }.bundle-badge { padding: 10rpx 14rpx; border-radius: 999rpx; background: #f0f1f4; color: #1d1d1f; font-size:25rpx; font-weight:500; }.bundle-visual { display: flex; align-items: center; justify-content: space-around; height: 150rpx; margin-top: 24rpx; border-radius: 26rpx; background: #f0eadc; font-size: 52rpx; }.bundle-visual text:last-child { width: 70rpx; height: 70rpx; display: flex; align-items: center; justify-content: center; border: 2rpx dashed #8aa092; border-radius: 50%; color: #577165; font-size: 28rpx; }
.section-head { display: flex; align-items: flex-end; justify-content: space-between; margin: 46rpx 0 18rpx; }.section-head > text:last-child { color: #6e6e78; font-size:25rpx; }.ingredient-head>view{display:flex;flex-direction:column;gap:6rpx}.ingredient-head>view text:last-child{color:#6e6e78;font-size:25rpx}.dish-list{display:flex;flex-direction:column;gap:13rpx}.dish-card{width:100%;display:flex;align-items:center;gap:10rpx;padding:12rpx}.dish-main{min-width:0;flex:1;display:flex;align-items:center;gap:16rpx;text-align:left}.dish-visual{width:94rpx;height:82rpx;display:flex;align-items:center;justify-content:center;flex:0 0 auto;border-radius:21rpx;font-size:42rpx}.dish-main>view:nth-child(2){min-width:0;flex:1;display:flex;flex-direction:column;gap:6rpx}.dish-main>view:nth-child(2) text:first-child{font-size:25rpx;font-weight:500}.dish-main>view:nth-child(2) text:nth-child(2){color:#6e6e78;font-size:25rpx}.dish-main>view:nth-child(2) text:last-child{color:#292a2e;font-size:25rpx;font-weight:500}.dish-main>text:last-child{color:#7b8b84;font-size:34rpx}.swap-button{flex:0 0 auto;min-height:58rpx;padding:0 13rpx;border:1rpx solid #99b6a8;border-radius:17rpx;background:#f4f8ef;color:#292a2e;font-size:25rpx;font-weight:500}.product-list { display: flex; flex-direction: column; gap: 14rpx; }.product-card { display: flex; align-items: center; gap: 16rpx; padding: 18rpx; }.select-box { width: 34rpx; height: 34rpx; display: flex; align-items: center; justify-content: center; flex: 0 0 auto; border: 1rpx solid #91a098; border-radius: 10rpx; color: white; font-size:25rpx; }.select-box.selected { border-color: #292a2e; background: #292a2e; }.product-image { width: 82rpx; height: 82rpx; display: flex; align-items: center; justify-content: center; flex: 0 0 auto; border-radius: 22rpx; background: #edf1df; font-size: 42rpx; }.product-copy { flex: 1; display: flex; flex-direction: column; gap: 6rpx; }.product-copy > text { font-size: 25rpx; font-weight:500; }.product-copy .small { color: #6e6e78; font-size:25rpx; }.product-copy .em { color: #292a2e; font-size:25rpx; font-style: normal; }.price { color: #b44d35; font-family:inherit; font-size: 26rpx; font-weight:500; }
.supplier-link{width:100%;margin-top:24rpx;color:#14563f;font-size:25rpx;font-weight:500;text-align:center}.verify-intro{display:block;margin:18rpx 0;color:#6b7c74;font-size:25rpx;line-height:1.55}.member-check{display:flex;align-items:center;justify-content:space-between;padding:16rpx 0;border-bottom:1rpx solid rgba(24,54,46,.08)}.member-check>view{display:flex;flex-direction:column;gap:5rpx}.member-check>view text:first-child{font-size:25rpx;font-weight:500}.member-check>view text:not(:first-child){color:#6e6e78;font-size:25rpx}.member-check>text:last-child{color:#292a2e;font-size:25rpx;font-weight:500}.ingredient-review,.conflict,.unknown{display:flex;flex-direction:column;gap:7rpx;margin-top:16rpx;padding:17rpx;border-radius:17rpx;background:#f5f5f7}.ingredient-review text:first-child,.conflict text:first-child,.unknown text:first-child{font-size:25rpx;font-weight:500}.ingredient-review text:not(:first-child),.conflict text:not(:first-child),.unknown text:not(:first-child){color:#687970;font-size:25rpx;line-height:1.5}.conflict{background:#f1d6cc;color:#8a4333}.unknown{background:#f3ead6;color:#735e35}.verify-sheet .primary-button{margin-top:19rpx}.verify-sheet .primary-button[disabled]{opacity:.45}.verify-sheet .secondary-button{margin-top:10rpx}
.safety-card { display: flex; gap: 18rpx; margin-top: 24rpx; padding: 24rpx; border-radius: 26rpx; background: #f8f5ef; }.shield { width: 48rpx; height: 54rpx; display: flex; align-items: center; justify-content: center; flex: 0 0 auto; border-radius: 24rpx 24rpx 14rpx 14rpx; background: #292a2e; color: white; font-size:25rpx; }.safety-card > view:last-child { display: flex; flex-direction: column; gap: 8rpx; }.safety-card text { color: #6b4539; font-size:25rpx; font-weight:500; }.safety-card .small { color: #785e55; font-size:25rpx; line-height: 1.55; }
.bottom-bar { position: fixed; z-index: 10; left: 0; right: 0; bottom: 0; display: flex; align-items: center; gap: 18rpx; padding: 22rpx 30rpx calc(env(safe-area-inset-bottom) + 22rpx); border-top: 1rpx solid rgba(24,54,46,.08); background: rgba(255,253,247,.96); }.bottom-bar > view:first-child { width: 168rpx; flex: 0 0 auto; display: flex; flex-direction: column; }.bottom-bar text,.bottom-bar .small { color: #6e6e78; font-size:25rpx; }.bottom-bar .strong { margin: 4rpx 0; color: #b44d35; font-family:inherit; font-size: 34rpx; }.bottom-bar .primary-button { flex: 1; min-height: 84rpx; font-size: 26rpx; }.bundle-bottom-actions { min-width: 0; flex: 1; display: grid !important; grid-template-columns: 1fr 1fr; gap: 10rpx; }.bundle-bottom-actions button { min-width: 0; min-height: 84rpx; padding: 0 10rpx; border-radius: 22rpx; font-size:25rpx; font-weight:500; }.clean-buy-button { border: 2rpx solid #292a2e; background: #ffffff; color: #292a2e; }.cook-today-button { background: #292a2e; color: white; box-shadow: 0 9rpx 20rpx rgba(31,107,82,.17); }
.order-title { display: flex; align-items: flex-start; justify-content: space-between; }.order-title .eyebrow { margin-bottom: 6rpx; }.order-title > button { color: #6e6e78; font-size: 40rpx; }
.delivery-card { display: flex; align-items: center; gap: 16rpx; margin-top: 26rpx; padding: 20rpx; border-radius: 22rpx; background: #f0f1f4; }.delivery-icon { width: 52rpx; height: 52rpx; display: flex; align-items: center; justify-content: center; flex: 0 0 auto; border-radius: 18rpx; background: #292a2e; color: white; font-size: 26rpx; }.delivery-card > view:nth-child(2) { flex: 1; display: flex; flex-direction: column; gap: 8rpx; }.delivery-card text { font-size:25rpx; line-height: 1.45; }.delivery-card > view:nth-child(2) text:first-child { color: #21493b; font-weight:500; }.delivery-card > view:nth-child(2) text:last-child { color: #62776d; }
.order-lines { margin-top: 18rpx; padding: 8rpx 0; border-top: 1rpx solid rgba(24,54,46,.09); border-bottom: 1rpx solid rgba(24,54,46,.09); }.order-lines view,.price-lines view,.delivery-time { display: flex; align-items: center; justify-content: space-between; padding: 13rpx 2rpx; color: #516b61; font-size:25rpx; }.delivery-time { margin-top: 8rpx; }.delivery-time text:last-child { color: #292a2e; font-weight:500; }.price-lines { padding-top: 6rpx; }.price-lines .pay-total { padding-top: 18rpx; border-top: 1rpx solid rgba(24,54,46,.09); color: #1d1d1f; font-weight:500; }.pay-total text:last-child { color: #b44d35; font-family:inherit; font-size: 32rpx; }
.success-mark { width: 96rpx; height: 96rpx; display: flex; align-items: center; justify-content: center; margin: 4rpx auto 22rpx; border-radius: 50%; background: #292a2e; color: #f0f1f4; font-size: 48rpx; font-weight:500; box-shadow: 0 16rpx 34rpx rgba(31,107,82,.2); }.success-title,.success-copy { display: block; text-align: center; }.success-copy { margin: 16rpx auto 28rpx; }
.status-track { display: grid; grid-template-columns: 1fr 38rpx 1fr 38rpx 1fr; align-items: start; margin: 12rpx 0 30rpx; }.status-track > view:nth-child(even) { height: 2rpx; margin-top: 22rpx; background: #cfdbd0; }.status-track > view:nth-child(odd) { display: flex; flex-direction: column; align-items: center; gap: 8rpx; color: #7a8a83; font-size:25rpx; text-align: center; line-height: 1.4; }.status-track > view:nth-child(odd) text:first-child { width: 44rpx; height: 44rpx; display: flex; align-items: center; justify-content: center; border-radius: 50%; background: #e5ece2; color: #6e6e78; font-weight:500; }.status-track .done text:first-child { background: #292a2e !important; color: white !important; }.status-track .done text:last-child { color: #292a2e; font-weight:500; }
</style>

<style scoped>.cloud-meal-screen .meal-summary-card{background:#303036;box-shadow:none}.cloud-meal-screen .diner-change,.cloud-meal-screen .secondary-button{color:#333}.cloud-meal-screen .diner-change{color:#eee}.cloud-meal-screen .shop-desc,.cloud-meal-screen .section-head>text:last-child{color:#777}.cloud-meal-screen .select-box.selected{background:#333;border-color:#333}.cloud-meal-screen .swap-button{color:#333;border-color:#ccc}.cloud-meal-screen .safety-card{background:#f1f1f3;color:#555}.cloud-meal-screen :deep(.member-tab.active){background:#fff;color:#222}.cloud-meal-screen :deep(.checked){color:#222}</style>
