<script setup>
import AppNavBar from '../../components/AppNavBar.vue'
import { computed, ref } from 'vue'
import { onLoad,onShow } from '@dcloudio/uni-app'
import FlowRibbon from '../../components/FlowRibbon.vue'
import DinerPicker from '../../components/DinerPicker.vue'
import MealNotes from '../../components/MealNotes.vue'
import { getProfile,backHome } from '../../utils/profile.js'
import { mockService } from '../../services/mock.js'
import { subtotal } from '../../utils/demo.js'
import { createMealBundles } from '../../utils/meal-bundles.js'
import { createDeliveryBatches,getExclusivePlan,adaptExclusivePlan } from '../../utils/exclusive-plans.js'
import { createDemoOrder,getOrder } from '../../utils/orders.js'
import { getDishSwapOptions,getMealSwap,saveMealSwap } from '../../utils/meal-customization.js'
import { createCookingGuide,mealFromRoute,mealToRoute,DAILY_MEALS } from '../../utils/meal-flow.js'
import { todayPlan,selectedFor,saveSelection,setMealMembers,changeResult,dailyProcurement } from '../../utils/meal-state.js'
const address=ref(mockService.selectedAddress())
function chooseAddress(){uni.navigateTo({url:'/pages/address/index'})}
const meal=ref('晚餐'),profile=ref(getProfile()),revision=ref(0),daily=ref(false),included=ref(['早餐','午餐','晚餐']),dinersOpen=ref(false),updateNote=ref('')
const isDiabetesCase=computed(()=>false),caseId=ref('')
const activeSwap=computed(()=>{revision.value;return getMealSwap(meal.value)})
const plan=computed(()=>{revision.value;return todayPlan(profile.value,meal.value)})
const procurement=computed(()=>{revision.value;return dailyProcurement(profile.value,included.value)})
const blockers=computed(()=>daily.value?procurement.value.blocked:plan.value.blocked)
const bundleId=ref(''),bundle=computed(()=>createMealBundles(plan.value).find(b=>b.id===bundleId.value))
const sourcePlanId=ref(''),sourcePlan=computed(()=>sourcePlanId.value?adaptExclusivePlan(getExclusivePlan(sourcePlanId.value),profile.value):null)
const products=computed(()=>daily.value?procurement.value.products:sourcePlan.value?sourcePlan.value.fixturePlans[0].flatMap(p=>p.products).reduce((list,p)=>{const same=list.find(x=>x.id===p.id);if(same){same.need+=p.need;same.quantity=Math.ceil(same.need/same.pack)}else list.push({...p});return list},[]):bundle.value?plan.value.products.filter(p=>bundle.value.productIds.includes(p.id)):plan.value.products)
const selected=ref([]),orderOpen=ref(false),paid=ref(false),paidOrderId=ref('')
const planStartDate=ref(''),deliveryBatchCount=ref(0)
const deliveryBatches=computed(()=>sourcePlan.value&&planStartDate.value?createDeliveryBatches(sourcePlan.value,planStartDate.value,deliveryBatchCount.value||21):[])
const selectedProducts=computed(()=>products.value.filter(p=>selected.value.includes(p.id)))
const productsSubtotalCents=computed(()=>subtotal(products.value,selected.value))
const totalCents=computed(()=>sourcePlan.value&&deliveryBatches.value.length?sourcePlan.value.totalEstimateCents:productsSubtotalCents.value)
const total=computed(()=>(totalCents.value/100).toFixed(2))
let knownProducts=[],quoteSignature=''
function refreshSelection(){
 selected.value=daily.value?procurement.value.selectedIds:selectedFor(meal.value,products.value)
 knownProducts=products.value.map(p=>[p.id,p.quantity])
}
onLoad(options=>{meal.value=mealFromRoute(options.meal);daily.value=options.daily==='1';bundleId.value=options.bundle||'';sourcePlanId.value=options.source==='exclusive-plan'?(options.plan||'balanced'):'';planStartDate.value=options.start||'';deliveryBatchCount.value=Number(options.batches||0);refreshSelection();const reorder=options.reorder?getOrder(options.reorder):null;if(reorder){selected.value=products.value.filter(p=>reorder.items.some(i=>i.id===p.id)).map(p=>p.id);saveSelection(meal.value,products.value,selected.value);}if(options.checkout==='1'||options.verify==='1')checkout()})
onShow(()=>{address.value=mockService.selectedAddress();profile.value=getProfile();revision.value++;const previous=JSON.stringify(knownProducts);refreshSelection();if(orderOpen.value&&!paid.value&&previous!==JSON.stringify(knownProducts)){orderOpen.value=false;updateNote.value='菜品或成员已变化，报价已重新计算，请重新核对结算。'}})
function toggle(id){const i=selected.value.indexOf(id);i<0?selected.value.push(id):selected.value.splice(i,1);saveSelection(daily.value?'今日采购':meal.value,products.value,selected.value);if(daily.value){for(const p of procurement.value.plans){const ids=selectedFor(p.meal,p.products);const index=ids.indexOf(id);if(selected.value.includes(id)&&index<0)ids.push(id);else if(!selected.value.includes(id)&&index>=0)ids.splice(index,1);saveSelection(p.meal,p.products,ids)}}}
function toggleMeal(value){const i=included.value.indexOf(value);i<0?included.value.push(value):included.value.splice(i,1);revision.value++;refreshSelection()}
function checkout(){if(blockers.value.length||sourcePlan.value?.blocked.length)return;if(!selected.value.length)return uni.showToast({title:'请至少选择一件食材',icon:'none'});paid.value=false;quoteSignature=JSON.stringify(selectedProducts.value);orderOpen.value=true}
function pay(){
 if(!address.value){uni.showToast({title:"请选择配送地址",icon:"none"});return}

 profile.value=getProfile();revision.value++
 if(blockers.value.length || sourcePlan.value?.blocked.length){orderOpen.value=false;return}
 if(quoteSignature!==JSON.stringify(selectedProducts.value)){refreshSelection();orderOpen.value=false;updateNote.value='报价已变化，请重新核对后再支付。';return}
 if(!paidOrderId.value){
 const plans=daily.value?procurement.value.plans:[plan.value]
 const guides=sourcePlan.value?deliveryBatches.value.map(b=>({index:b.index,guides:b.meals.map(m=>createCookingGuide(plan.value,sourcePlan.value,{batchIndex:b.index,meal:m.type}))})):daily.value?[{index:1,guides:plans.map(p=>createCookingGuide(p))}]:[]
 const order=createDemoOrder({addressSnapshot:address.value,items:selectedProducts.value,totalCents:totalCents.value,meal:daily.value?'今日三餐':meal.value,sourcePlanId:sourcePlanId.value,planName:sourcePlan.value?.name||'',bundleId:bundleId.value,deliveryBatches:deliveryBatches.value,cookingGuide:createCookingGuide(plan.value,sourcePlan.value),cookingGuides:guides})
 paidOrderId.value=order.id
 }paid.value=true
}
function viewOrder(){uni.navigateTo({url:'/pages/orders/detail?id='+encodeURIComponent(paidOrderId.value)})}
function nutritionist(){uni.reLaunch({url:'/pages/chat/index'})}
function openDish(dish){uni.navigateTo({url:'/pages/recipe/index?meal='+mealToRoute(meal.value)+'&dish='+encodeURIComponent(dish.name)+(plan.value.paid?'&id='+plan.value.orderId+'&batch='+plan.value.batchIndex:'' )})}
function changeDiners(){dinersOpen.value=true}
function confirmDiners(ids){const before=plan.value;const previous=[...selected.value];saveSelection(meal.value,products.value,previous);setMealMembers(profile.value,meal.value,ids);revision.value++;refreshSelection();updateNote.value=changeResult(before,plan.value,previous);dinersOpen.value=false;if(orderOpen.value&&!paid.value)orderOpen.value=false}
function canSwapDish(dish){return !plan.value.paid&&getDishSwapOptions(meal.value,dish.name,plan.value.members).length>0}
function switchDish(dish){const options=getDishSwapOptions(meal.value,dish.name,plan.value.members);if(!options.length)return;uni.showActionSheet({itemList:options.map(o=>o.name+' · '+o.direction),success:({tapIndex})=>{saveSelection(meal.value,products.value,selected.value);saveMealSwap(meal.value,options[tapIndex]);revision.value++;refreshSelection();updateNote.value='菜品、营养、做法、食材包装数量与预计金额已同步更新。'}})}
function editProfile(){uni.navigateTo({url:'/pages/profile/index'})}
</script>
<template>
  <view class="screen shop-screen">
    <AppNavBar><view class="nav-row"><button class="icon-button" @click="backHome">‹</button><text class="nav-title">{{ daily ? '今日采购清单' : sourcePlan ? '食材商城' : meal + '安排与购买' }}</text><text class="pill">演示</text></view></AppNavBar>
    <FlowRibbon :current="orderOpen ? 4 : 3" class="shop-flow" />
    <view v-if="(!plan.paid && blockers.length) || sourcePlan?.blocked.length" class="card safety-card">
      <view><text>暂无法完成饮食安全适配</text><text class="small">{{ [...blockers,...(sourcePlan?.blocked||[])].join('；') }}</text><button class="secondary-button" @click="editProfile">核对档案</button></view>
    </view>
    <template v-else>
      <view class="shop-head"><text class="eyebrow">{{ isDiabetesCase ? '虚拟糖尿病家庭案例 · 一桌共享菜单' : sourcePlan ? 'AI专属计划 · 首批采购' : '本餐安排与购买清单 · 同一页面' }}</text><text class="display-title">{{daily?'把今天三餐，一次备齐':sourcePlan?'核对计划，准备开始':meal+'安排与购买'}}</text><text class="shop-desc">{{ isDiabetesCase ? '已按三人共享晚餐汇总菜品与食材。商品与价格均为演示；爸爸的实际主食份量仍需按专业要求确认。' : sourcePlan ? sourcePlan.name + '已自动检查已知饮食限制并安排' + (deliveryBatches.length || 21) + '次配送确认。这里演示首批食材采购。' : '先看本餐菜品与做法，再直接勾选需要购买的整包装食材。' }}</text></view>
      <view v-if="!daily" class="meal-summary-card"><view class="summary-title"><view><text class="eyebrow">本餐基本信息</text><text>{{meal}} · {{plan.count}} 人用餐</text></view></view><button class="diner-control" @click="changeDiners"><view><text>本餐就餐者</text><text>{{plan.members.map(m=>m.name).join('、')}}</text></view><text>更改 ›</text></button><MealNotes :plan="plan"/></view>
      <view v-else class="card daily-meals"><text class="section-title">选择今日需要采购的餐次</text><button v-for="m in DAILY_MEALS" :key="m.name" @click="toggleMeal(m.name)">{{included.includes(m.name)?'✓':'○'}} {{m.name}}</button><text class="demo-label">跨餐合并同一食材与 SKU 后计算包装数量；仍需核对商品、地址和金额后结算。</text></view>
      <text v-if="updateNote" class="update-note">{{updateNote}}</text>
      <view v-if="bundle" class="bundle-card">
        <view class="bundle-top"><view><text>{{ bundle.name }}</text><text class="small">按 {{ plan.count }} 位成员的菜单需求匹配 · 示例商品</text></view><view class="bundle-badge">单包</view></view>
        <image v-if="bundle" class="selected-bundle-image" :src="bundle.image" mode="aspectFill" />
      </view>
      <view v-if="!daily" class="section-head"><text class="section-title">本餐全部菜品</text><text>点击查看独立做法页</text></view>
      <view v-if="!daily" class="dish-list"><view v-for="dish in plan.dishes" :key="dish.name" class="dish-card card"><button class="dish-main" @click="openDish(dish)"><view class="dish-visual" :style="{background:dish.color}">{{dish.icon}}</view><view><text>{{dish.name}}</text><text>{{dish.detail}}</text><text>{{dish.kcal?'约 '+dish.kcal+' kcal · ':''}}查看做法与注意事项</text></view><text>›</text></button><button v-if="canSwapDish(dish)" class="swap-button" @click="switchDish(dish)">换一换</button></view></view>
      <view class="section-head ingredient-head"><view><text class="section-title">{{daily?'今日所需食材和购买清单':'本餐所需食材和购买清单'}}</text><text>包装数量按本餐人数计算</text></view><text>已选 {{ selected.length }} 项</text></view>
      <view class="product-list">
        <view v-for="product in products" :key="product.id" class="product-card card" @click="toggle(product.id)">
          <view class="select-box" :class="{ selected: selected.includes(product.id) }">{{ selected.includes(product.id) ? '✓' : '' }}</view>
          <view class="product-image">{{ product.icon }}</view>
          <view class="product-copy"><text>{{ product.name }}</text><text class="small">需要 {{ product.need }}{{ product.unit }}</text><text class="em">{{ product.pack }}{{ product.unit }}/包 × {{ product.quantity }} 包</text></view>
          <text class="price">¥{{ (product.priceCents * product.quantity / 100).toFixed(2) }}</text>
        </view>
      </view>
      <view class="safety-card"><view class="shield">i</view><view><text>结算前核对采购内容</text><text class="small">商品、包装数量、配送地址和价格。饮食限制已在推荐前自动检查。当前为购买流程演示，不会生成真实订单或扣款。</text></view></view>
      <view class="bottom-bar"><view><text>已选 {{selected.length}} 项</text><text class="strong">¥{{ total }}</text><text class="small">示例合计</text></view><button v-if="!plan.paid && (!daily || procurement.plans.every(p=>!p.paid))" class="primary-button" @click="checkout">去结算／直接购买 →</button></view>
    </template>
    <DinerPicker :open="dinersOpen" :members="profile.members" :selected="plan.members.map(m=>m.id)" :meal="meal" @close="dinersOpen=false" @confirm="confirmDiners"/>
    <view v-if="orderOpen" class="sheet-mask"><view class="sheet order-sheet">
      <template v-if="!paid">
        <view class="order-title"><view><text class="eyebrow">演示订单</text><text class="section-title">确认订单</text></view><button @click="orderOpen = false">×</button></view>
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
        <button class="primary-button" @click="pay">模拟支付 ¥{{ total }}</button>
        <button class="secondary-button" @click="orderOpen = false">返回调整商品</button>
      </template>
      <template v-else>
        <view class="success-mark">✓</view>
        <text class="section-title success-title">购买成功 · 演示订单</text>
        <text class="demo-label success-copy">已模拟支付 ¥{{ total }}，订单当前为“待配送”。本原型不会产生真实配送。</text>
        <view class="status-track"><view class="done"><text>1</text><text>已模拟支付</text></view><view></view><view><text>2</text><text>商家备货</text></view><view></view><view><text>3</text><text>配送完成</text></view></view>
        <button class="primary-button" @click="viewOrder">查看订单 →</button>
        <button class="secondary-button" @click="nutritionist">返回营养师</button>
      </template>
    </view></view>
  </view>
</template>
<style scoped>
.daily-meals{margin-top:28rpx;padding:26rpx;display:flex;flex-direction:column;gap:20rpx}.daily-meals button{padding:20rpx;border:1rpx solid #d3dfcc;border-radius:18rpx;color:#246b50;text-align:left;font-size:26rpx}.update-note{display:block;padding:22rpx;margin-top:20rpx;background:#e6efdc;border-radius:22rpx;font-size:22rpx;line-height:1.7}
.selected-bundle-image { display: block; width: 100%; height: 260rpx; margin-top: 24rpx; border-radius: 22rpx; }
.shop-screen { padding-bottom: calc(env(safe-area-inset-bottom) + 190rpx); }.shop-flow { margin-top: 20rpx; }.shop-head { margin-top: 54rpx; }.shop-head .display-title { display: block; font-size: 52rpx; }.shop-desc { display: block; margin-top: 22rpx; color: #65776f; font-size: 24rpx; line-height: 1.75; }
.meal-summary-card{margin-top:30rpx;padding:26rpx;border-radius:30rpx;background:#246b50;color:white;box-shadow:0 18rpx 40rpx rgba(31,107,82,.18)}.summary-title{display:flex;align-items:flex-start;justify-content:space-between}.summary-title>view{display:flex;flex-direction:column;gap:8rpx}.summary-title .eyebrow{color:#e0eee5}.summary-title>view text:last-child{font-family:inherit;font-size:32rpx;font-weight:800}.summary-title>text:last-child{padding:8rpx 12rpx;border-radius:999rpx;background:rgba(255,255,255,.14);font-size:18rpx}.nutrition-strip{display:grid;grid-template-columns:repeat(3,1fr);gap:10rpx;margin-top:22rpx}.nutrition-strip>view{display:flex;flex-direction:column;gap:5rpx;padding:16rpx;border-radius:18rpx;background:rgba(255,255,255,.11)}.nutrition-strip text:first-child{font-size:23rpx;font-weight:900}.nutrition-strip text:last-child{color:#d2e6d7;font-size:17rpx}.diner-control{width:100%;display:flex;align-items:center;justify-content:space-between;margin-top:14rpx;padding:18rpx 20rpx;border-radius:20rpx;background:#ffffff;color:#1d1d1f;text-align:left}.diner-control>view{display:flex;flex-direction:column;gap:5rpx}.diner-control view text:first-child{color:#71827a;font-size:17rpx}.diner-control view text:last-child{font-size:21rpx;font-weight:900}.diner-control>text:last-child{color:#246b50;font-size:19rpx;font-weight:800}
.bundle-card { margin-top: 32rpx; padding: 28rpx; overflow: hidden; border-radius: 34rpx; background: #246b50; color: white; box-shadow: 0 20rpx 45rpx rgba(31,107,82,.2); }.bundle-top { display: flex; align-items: flex-start; justify-content: space-between; }.bundle-top view:first-child { display: flex; flex-direction: column; gap: 10rpx; }.bundle-top text { font-family:inherit; font-size: 34rpx; font-weight: 700; }.bundle-top .small { color: #cde0d2; font-size: 20rpx; }.bundle-badge { padding: 10rpx 14rpx; border-radius: 999rpx; background: #e0eee5; color: #1d1d1f; font-size: 18rpx; font-weight: 700; }.bundle-visual { display: flex; align-items: center; justify-content: space-around; height: 150rpx; margin-top: 24rpx; border-radius: 26rpx; background: #f0eadc; font-size: 52rpx; }.bundle-visual text:last-child { width: 70rpx; height: 70rpx; display: flex; align-items: center; justify-content: center; border: 2rpx dashed #8aa092; border-radius: 50%; color: #577165; font-size: 28rpx; }
.section-head { display: flex; align-items: flex-end; justify-content: space-between; margin: 46rpx 0 18rpx; }.section-head > text:last-child { color: #71827a; font-size: 21rpx; }.ingredient-head>view{display:flex;flex-direction:column;gap:6rpx}.ingredient-head>view text:last-child{color:#71827a;font-size:18rpx}.dish-list{display:flex;flex-direction:column;gap:13rpx}.dish-card{width:100%;display:flex;align-items:center;gap:10rpx;padding:12rpx}.dish-main{min-width:0;flex:1;display:flex;align-items:center;gap:16rpx;text-align:left}.dish-visual{width:94rpx;height:82rpx;display:flex;align-items:center;justify-content:center;flex:0 0 auto;border-radius:21rpx;font-size:42rpx}.dish-main>view:nth-child(2){min-width:0;flex:1;display:flex;flex-direction:column;gap:6rpx}.dish-main>view:nth-child(2) text:first-child{font-size:25rpx;font-weight:900}.dish-main>view:nth-child(2) text:nth-child(2){color:#71827a;font-size:18rpx}.dish-main>view:nth-child(2) text:last-child{color:#246b50;font-size:18rpx;font-weight:800}.dish-main>text:last-child{color:#7b8b84;font-size:34rpx}.swap-button{flex:0 0 auto;min-height:58rpx;padding:0 13rpx;border:1rpx solid #99b6a8;border-radius:17rpx;background:#f4f8ef;color:#246b50;font-size:18rpx;font-weight:800}.product-list { display: flex; flex-direction: column; gap: 14rpx; }.product-card { display: flex; align-items: center; gap: 16rpx; padding: 18rpx; }.select-box { width: 34rpx; height: 34rpx; display: flex; align-items: center; justify-content: center; flex: 0 0 auto; border: 1rpx solid #91a098; border-radius: 10rpx; color: white; font-size: 20rpx; }.select-box.selected { border-color: #246b50; background: #246b50; }.product-image { width: 82rpx; height: 82rpx; display: flex; align-items: center; justify-content: center; flex: 0 0 auto; border-radius: 22rpx; background: #edf1df; font-size: 42rpx; }.product-copy { flex: 1; display: flex; flex-direction: column; gap: 6rpx; }.product-copy > text { font-size: 25rpx; font-weight: 700; }.product-copy .small { color: #75867e; font-size: 19rpx; }.product-copy .em { color: #246b50; font-size: 18rpx; font-style: normal; }.price { color: #b44d35; font-family:inherit; font-size: 26rpx; font-weight: 700; }
.supplier-link{width:100%;margin-top:24rpx;color:#14563f;font-size:20rpx;font-weight:900;text-align:center}.verify-intro{display:block;margin:18rpx 0;color:#6b7c74;font-size:19rpx;line-height:1.55}.member-check{display:flex;align-items:center;justify-content:space-between;padding:16rpx 0;border-bottom:1rpx solid rgba(24,54,46,.08)}.member-check>view{display:flex;flex-direction:column;gap:5rpx}.member-check>view text:first-child{font-size:21rpx;font-weight:900}.member-check>view text:not(:first-child){color:#74847d;font-size:17rpx}.member-check>text:last-child{color:#246b50;font-size:17rpx;font-weight:800}.ingredient-review,.conflict,.unknown{display:flex;flex-direction:column;gap:7rpx;margin-top:16rpx;padding:17rpx;border-radius:17rpx;background:#edf2e5}.ingredient-review text:first-child,.conflict text:first-child,.unknown text:first-child{font-size:20rpx;font-weight:900}.ingredient-review text:not(:first-child),.conflict text:not(:first-child),.unknown text:not(:first-child){color:#687970;font-size:18rpx;line-height:1.5}.conflict{background:#f1d6cc;color:#8a4333}.unknown{background:#f3ead6;color:#735e35}.verify-sheet .primary-button{margin-top:19rpx}.verify-sheet .primary-button[disabled]{opacity:.45}.verify-sheet .secondary-button{margin-top:10rpx}
.safety-card { display: flex; gap: 18rpx; margin-top: 24rpx; padding: 24rpx; border-radius: 26rpx; background: #f8f5ef; }.shield { width: 48rpx; height: 54rpx; display: flex; align-items: center; justify-content: center; flex: 0 0 auto; border-radius: 24rpx 24rpx 14rpx 14rpx; background: #246b50; color: white; font-size: 22rpx; }.safety-card > view:last-child { display: flex; flex-direction: column; gap: 8rpx; }.safety-card text { color: #6b4539; font-size: 23rpx; font-weight: 700; }.safety-card .small { color: #785e55; font-size: 20rpx; line-height: 1.55; }
.bottom-bar { position: fixed; z-index: 10; left: 0; right: 0; bottom: 0; display: flex; align-items: center; gap: 18rpx; padding: 22rpx 30rpx calc(env(safe-area-inset-bottom) + 22rpx); border-top: 1rpx solid rgba(24,54,46,.08); background: rgba(255,253,247,.96); }.bottom-bar > view:first-child { width: 168rpx; flex: 0 0 auto; display: flex; flex-direction: column; }.bottom-bar text,.bottom-bar .small { color: #71827a; font-size: 18rpx; }.bottom-bar .strong { margin: 4rpx 0; color: #b44d35; font-family:inherit; font-size: 34rpx; }.bottom-bar .primary-button { flex: 1; min-height: 84rpx; font-size: 26rpx; }.bundle-bottom-actions { min-width: 0; flex: 1; display: grid !important; grid-template-columns: 1fr 1fr; gap: 10rpx; }.bundle-bottom-actions button { min-width: 0; min-height: 84rpx; padding: 0 10rpx; border-radius: 22rpx; font-size: 22rpx; font-weight: 900; }.clean-buy-button { border: 2rpx solid #246b50; background: #ffffff; color: #246b50; }.cook-today-button { background: #246b50; color: white; box-shadow: 0 9rpx 20rpx rgba(31,107,82,.17); }
.order-title { display: flex; align-items: flex-start; justify-content: space-between; }.order-title .eyebrow { margin-bottom: 6rpx; }.order-title > button { color: #60736a; font-size: 40rpx; }
.delivery-card { display: flex; align-items: center; gap: 16rpx; margin-top: 26rpx; padding: 20rpx; border-radius: 22rpx; background: #eaf2e3; }.delivery-icon { width: 52rpx; height: 52rpx; display: flex; align-items: center; justify-content: center; flex: 0 0 auto; border-radius: 18rpx; background: #246b50; color: white; font-size: 26rpx; }.delivery-card > view:nth-child(2) { flex: 1; display: flex; flex-direction: column; gap: 8rpx; }.delivery-card text { font-size: 21rpx; line-height: 1.45; }.delivery-card > view:nth-child(2) text:first-child { color: #21493b; font-weight: 700; }.delivery-card > view:nth-child(2) text:last-child { color: #62776d; }
.order-lines { margin-top: 18rpx; padding: 8rpx 0; border-top: 1rpx solid rgba(24,54,46,.09); border-bottom: 1rpx solid rgba(24,54,46,.09); }.order-lines view,.price-lines view,.delivery-time { display: flex; align-items: center; justify-content: space-between; padding: 13rpx 2rpx; color: #516b61; font-size: 21rpx; }.delivery-time { margin-top: 8rpx; }.delivery-time text:last-child { color: #246b50; font-weight: 700; }.price-lines { padding-top: 6rpx; }.price-lines .pay-total { padding-top: 18rpx; border-top: 1rpx solid rgba(24,54,46,.09); color: #1d1d1f; font-weight: 700; }.pay-total text:last-child { color: #b44d35; font-family:inherit; font-size: 32rpx; }
.success-mark { width: 96rpx; height: 96rpx; display: flex; align-items: center; justify-content: center; margin: 4rpx auto 22rpx; border-radius: 50%; background: #246b50; color: #e0eee5; font-size: 48rpx; font-weight: 800; box-shadow: 0 16rpx 34rpx rgba(31,107,82,.2); }.success-title,.success-copy { display: block; text-align: center; }.success-copy { margin: 16rpx auto 28rpx; }
.status-track { display: grid; grid-template-columns: 1fr 38rpx 1fr 38rpx 1fr; align-items: start; margin: 12rpx 0 30rpx; }.status-track > view:nth-child(even) { height: 2rpx; margin-top: 22rpx; background: #cfdbd0; }.status-track > view:nth-child(odd) { display: flex; flex-direction: column; align-items: center; gap: 8rpx; color: #7a8a83; font-size: 17rpx; text-align: center; line-height: 1.4; }.status-track > view:nth-child(odd) text:first-child { width: 44rpx; height: 44rpx; display: flex; align-items: center; justify-content: center; border-radius: 50%; background: #e5ece2; color: #61776d; font-weight: 700; }.status-track .done text:first-child { background: #246b50 !important; color: white !important; }.status-track .done text:last-child { color: #246b50; font-weight: 700; }
</style>
