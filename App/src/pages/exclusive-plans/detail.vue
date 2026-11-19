<script setup>
import { computed, ref } from 'vue'
import { onLoad, onShow, onHide, onUnload } from '@dcloudio/uni-app'
import AppNavBar from '../../components/AppNavBar.vue'
import FoodImageSlot from '../../components/FoodImageSlot.vue'
import CloudMealPurchase from '../../components/CloudMealPurchase.vue'
import { request } from '../../services/request.js'
import { getSession, sessionRevision } from '../../services/session.js'
import { commerce } from '../../services/commerce.js'
import { useCommercePage } from '../../services/commerce-page.js'
import { selectedDay, dayMeals, validPlanRoute } from '../../services/plan-presentation.js'
import { recipeCover } from '../../utils/recipe-cover.js'
import { planTiers, readExclusivePreview, exclusiveImages } from '../../services/exclusive-planning.js'
import { createExclusiveImageFlow } from '../../services/exclusive-image-flow.js'
const route = ref(null), plan = ref(null), dayNo = ref(1), mealType = ref('breakfast')
const purchasing = ref(false), purchaseData = ref(null)
const visible = ref(false)
const imageFlow = createExclusiveImageFlow({send:exclusiveImages,
  scope:()=>String(sessionRevision())+':'+getSession()?.householdId,
  status:()=>{},
  apply:images=>{
    if(!visible.value)return
    const found=new Map(images.map(image=>[image.file_id,image]))
    for(const item of day.value?.meals||[]){
      const image=found.get(item.source?.file_id)
      if(image?.image_url)item.recipe_snapshot={...item.recipe_snapshot,...image}
    }
  },
})
const { busy, error, run } = useCommercePage(() => { plan.value = null; purchaseData.value = null; selectDay(1) })
const purchasePath = computed(() => '/api/health/v1/families/' + encodeURIComponent(getSession()?.householdId) + '/exclusive-plans/' + encodeURIComponent(route.value?.groupId) + '/tiers/' + encodeURIComponent(route.value?.tier) + '/purchase')
const purchaseReference = computed(() => purchaseData.value ? {
  previewId: route.value.groupId, gaps: purchaseData.value.gaps,
  items: purchaseData.value.items.map(item=>({sku_id:item.sku_id,product_id:item.sku.product_id,product_name:item.sku.product_name,sku_name:item.sku.sku_name,quantity:item.quantity,image_url:item.sku.image_url,
    price_cent:item.sku.price_cent,available_quantity:item.sku.available_quantity,sale_status:item.sku.sale_status})),
} : null)
const purchaseRoute = computed(() => ({arrangement:route.value.groupId+':'+route.value.tier,version:purchaseData.value.scope_hash,date:'',meal:'daily',meals:['breakfast','lunch','dinner']}))
const day = computed(() => selectedDay(plan.value, dayNo.value))
const meals = computed(() => dayMeals(day.value))
const meal = computed(() => meals.value.find(item => item.type === mealType.value))
const dayLabels = computed(() => (plan.value?.days || []).map(item => '第 ' + item.day_no + ' 天'))
onLoad(options => {
  purchasing.value = options.purchase === '1'
  try {
    if (options.group_id) {
      if (!planTiers.includes(options.tier)) throw new Error('请从专属计划页重新选择方案')
      route.value = {groupId: options.group_id, tier: options.tier}
    } else route.value = validPlanRoute(options)
  } catch (e) { error.value = e.message }
})
onShow(()=>{visible.value=true;load()})
onHide(()=>{visible.value=false;imageFlow.stop()})
onUnload(()=>{visible.value=false;imageFlow.stop()})
function refreshImages(start=false){
  if(!visible.value||!route.value?.groupId||purchasing.value||!plan.value)return
  void imageFlow.open({groupId:route.value.groupId,tier:route.value.tier,dayNo:dayNo.value},{start})
}
function selectDay(number) {
  dayNo.value = Number(number)
  mealType.value = 'breakfast'
  refreshImages()
}
function jumpToDay(event) {
  const selected = plan.value?.days?.[Number(event.detail.value)]
  if (selected) selectDay(selected.day_no)
}
function load() {
  if (!route.value) return
  imageFlow.stop()
  return run(async active => {
    plan.value = null
    purchaseData.value = null
    const {groupId, tier, sn, version} = route.value
    if (purchasing.value && groupId) {
      const {data} = await request({path:purchasePath.value})
      if (active()) {
        plan.value = {tier_name:data.tier_name,members:data.members}
        purchaseData.value = data
      }
      return
    }
    const result = groupId ? await readExclusivePreview(groupId, tier) : await commerce.servicePlan(sn, version)
    if (active()) {plan.value = result;refreshImages(true)}
  })
}
function next() { if (plan.value?.status === 'available') uni.navigateTo({url:'/pages/exclusive-plans/schedule?plan_sn='+encodeURIComponent(route.value.sn)+'&plan_version='+route.value.version}) }
function purchase() {
  if (busy.value || !plan.value) return
  if (!route.value.groupId) { next(); return }
  uni.navigateTo({url:'/pages/exclusive-plans/detail?group_id='+encodeURIComponent(route.value.groupId)+'&tier='+encodeURIComponent(route.value.tier)+'&purchase=1'})
}
const back = () => uni.navigateBack()
</script>
<template>
  <view class="screen exclusive-screen detail-screen">
    <AppNavBar :title="purchasing?'计划采购':'计划详情'"><template #left><button class="icon-button" aria-label="返回" @click="back">‹</button></template></AppNavBar>
    <view v-if="error" class="plan-surface plan-empty"><text class="plan-caption">{{error}}</text><button class="plan-secondary" :disabled="busy" @click="load">重新读取</button><button class="plan-text-link" @click="back">返回选择计划</button></view>
    <text v-else-if="busy && !plan" class="plan-notice">正在读取计划…</text>
    <template v-if="plan && purchasing">
      <view class="plan-heading"><text class="plan-title">{{plan.tier_name}}</text><text class="plan-caption">整份 21 天计划</text></view>
      <template v-if="purchaseData">
        <text class="plan-notice purchase-coverage">{{purchaseData.notice}}</text>
        <text v-if="purchaseData.items.some(item=>item.quantity_confirmed===false)" class="plan-notice quantity-warning">部分商品包装数量待确认，请按家庭实际需要调整，当前数量不能视为足够 21 天。</text>
        <view v-if="purchaseData.gaps?.length" class="plan-surface purchase-coverage-gaps"><text class="plan-notice">以下食材未加入购物车，需自行准备或确认：</text><text v-for="(gap,index) in purchaseData.gaps" :key="index" class="plan-notice">{{gap.label||gap.ingredient}}：{{gap.detail}}</text></view>
        <CloudMealPurchase v-if="purchaseData.available" :key="purchaseData.scope_hash" :meal="{members:plan.members}" :route="purchaseRoute" :reference="purchaseReference" :exclusive="{path:purchasePath,scopeHash:purchaseData.scope_hash,initialPurchase:purchaseData}"/>
        <view v-else class="plan-surface plan-empty"><text class="plan-caption">暂无可购买商品</text><button class="plan-secondary" :disabled="busy" @click="load">重新核对</button></view>
      </template>
    </template>
    <template v-if="plan && !purchasing">
      <view class="plan-heading"><text class="plan-title">{{plan.tier_name}}</text></view>
      <view class="plan-surface menu-controls">
        <view class="section-top">
          <text class="plan-section-title">计划菜谱</text>
          <picker :range="dayLabels" :value="plan.days.findIndex(item => Number(item.day_no) === dayNo)" @change="jumpToDay"><view class="day-picker"><text>选择日期</text><text aria-hidden="true">›</text></view></picker>
        </view>
        <scroll-view scroll-x class="day-tabs" :scroll-into-view="'plan-day-' + dayNo" :show-scrollbar="false">
          <view class="day-tabs-inner"><button v-for="item in plan.days" :id="'plan-day-' + item.day_no" :key="item.day_no" :class="{chosen:Number(item.day_no)===dayNo}" :aria-pressed="Number(item.day_no)===dayNo" @click="selectDay(item.day_no)">第 {{item.day_no}} 天</button></view>
        </scroll-view>
        <view class="meal-tabs" role="group" aria-label="选择餐次">
          <button v-for="item in meals" :id="'plan-meal-' + item.type" :key="item.type" :class="{chosen:mealType===item.type}" :aria-pressed="mealType===item.type" @click="mealType=item.type">{{item.name}}</button>
        </view>
      </view>
      <view class="section-top meal-title">
        <text class="plan-section-title">第 {{dayNo}} 天 · {{meal.name}}</text>
      </view>
      <view class="meal-list">
        <view v-for="dish in meal.dishes" :key="dish.id" class="plan-surface recipe-block">
          <FoodImageSlot class="dish-photo" :src="recipeCover(dish.recipe_snapshot)?.image_url" :label="dish.recipe_name" fallback-icon/>
          <text class="dish-name">{{dish.recipe_name}}</text>
        </view>
        <view v-if="!meal.dishes.length" class="plan-surface plan-empty"><text class="plan-caption">这一餐的菜品暂不可用</text></view>
      </view>
      <view class="plan-fixed"><button class="plan-primary" :disabled="busy || (!route.groupId && plan.status!=='available')" @click="purchase">购买</button></view>
    </template>
  </view>
</template>
<style scoped>
.detail-screen{min-height:100vh;box-sizing:border-box;overflow:hidden;padding:0 36rpx calc(160rpx + env(safe-area-inset-bottom));color:#424b60;background-color:#f5f6fa;background-image:radial-gradient(ellipse at 5% 0%,rgba(171,203,250,.38),transparent 72%),linear-gradient(180deg,#eff5ff,rgba(245,246,250,0));background-size:100% 380rpx;background-repeat:no-repeat}
.detail-screen button::after{border:0}.detail-screen button[disabled]{opacity:.5}
.icon-button{min-width:88rpx;min-height:88rpx;margin-left:-14rpx;padding:0 14rpx;background:transparent;color:#59657a;font-size:60rpx;line-height:1.4;text-align:left}
.plan-heading{margin:38rpx 8rpx 32rpx}.plan-title{display:block;font-size:52rpx;font-weight:600;letter-spacing:2rpx;line-height:1.5}
.plan-surface{box-sizing:border-box;background:linear-gradient(135deg,rgba(255,255,255,.84),#fff);border:2rpx solid rgba(255,255,255,.95);border-radius:36rpx;box-shadow:0 10rpx 32rpx rgba(71,99,148,.035)}
.menu-controls{padding:28rpx 24rpx 24rpx}.section-top{display:flex;align-items:center;justify-content:space-between;gap:18rpx}.menu-controls .section-top{padding:0 8rpx 24rpx}
.plan-section-title{font-size:30rpx;font-weight:500;line-height:1.6}.day-picker{display:flex;align-items:center;gap:10rpx;min-height:56rpx;padding:0 4rpx;color:#59657a;font-size:23rpx}.day-picker>text:last-child{font-size:32rpx}
.day-tabs{white-space:nowrap;width:100%}.day-tabs-inner{display:inline-flex;gap:12rpx}.day-tabs button{flex:none;min-width:114rpx;margin:0;padding:18rpx 22rpx;border:2rpx solid transparent;border-radius:24rpx;font-size:25rpx;line-height:1.5;background:#f5f7fb;color:#626d80;box-sizing:border-box}.day-tabs button.chosen{background:#e6eaf1;border-color:#b5becd;color:#424b60;font-weight:600}
.meal-tabs{display:flex;gap:8rpx;margin-top:26rpx;padding:8rpx;border-radius:24rpx;background:#f1f4f9}.meal-tabs button{flex:1;margin:0;padding:16rpx 8rpx;border-radius:18rpx;font-size:27rpx;line-height:1.5;background:transparent;color:#626d80}.meal-tabs button.chosen{background:#fff;color:#424b60;box-shadow:0 4rpx 14rpx rgba(73,105,158,.06);font-weight:500}
.meal-title{margin:34rpx 10rpx 20rpx}.meal-title .plan-section-title{font-size:28rpx;color:#59657a}.meal-list{display:flex;flex-direction:column;gap:20rpx}.recipe-block{display:flex;align-items:center;gap:28rpx;min-height:180rpx;padding:24rpx}.dish-photo{width:132rpx;height:132rpx;border-radius:26rpx;flex-shrink:0}.dish-name{flex:1;min-width:0;font-size:31rpx;font-weight:500;line-height:1.65;overflow-wrap:anywhere}
.plan-caption{font-size:27rpx;color:#626d80;line-height:1.7}.plan-empty{display:flex;align-items:center;flex-direction:column;gap:24rpx;padding:56rpx 32rpx;text-align:center}.plan-notice{display:block;color:#626d80;font-size:25rpx;line-height:1.7;padding:22rpx 8rpx}.plan-secondary{min-height:80rpx;padding:18rpx 30rpx;border-radius:24rpx;background:#e6eaf1;color:#424b60;font-size:27rpx}.plan-text-link{padding:14rpx;background:transparent;color:#59657a;font-size:26rpx}.plan-fixed{position:fixed;z-index:10;left:0;right:0;bottom:0;padding:20rpx 32rpx calc(20rpx + env(safe-area-inset-bottom));background:#ffffffef;border-top:1rpx solid #edf1f8}.plan-primary{width:100%;display:flex;justify-content:center;align-items:center;gap:22rpx;min-height:90rpx;padding:20rpx 28rpx;border-radius:28rpx;background:#424b60;color:#fff;font-size:28rpx;line-height:1.5}
.day-tabs button:focus-visible,.meal-tabs button:focus-visible{outline:2px solid #59657a;outline-offset:2px}
@media(max-width:350px){.detail-screen{padding-left:24rpx;padding-right:24rpx}.menu-controls{padding:24rpx 18rpx 20rpx}.dish-photo{width:120rpx;height:120rpx}.recipe-block{gap:22rpx;padding:22rpx}.dish-name{font-size:30rpx}}
@media(min-width:600px){.detail-screen{max-width:480px;margin:0 auto}.plan-fixed{max-width:480px;margin:0 auto;box-sizing:border-box}}
</style>
