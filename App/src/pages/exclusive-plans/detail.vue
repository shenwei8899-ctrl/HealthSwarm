<script setup>
import { computed, ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import AppNavBar from '../../components/AppNavBar.vue'
import FoodImageSlot from '../../components/FoodImageSlot.vue'
import { commerce } from '../../services/commerce.js'
import { useCommercePage } from '../../services/commerce-page.js'
import { selectedDay, dayMeals, memberName, selectedProducts, priceText, validPlanRoute } from '../../services/plan-presentation.js'
const route = ref(null), plan = ref(null), dayNo = ref(1), expanded = ref('')
const { busy, error, run } = useCommercePage(() => { plan.value = null; expanded.value = '' })
const day = computed(() => selectedDay(plan.value, dayNo.value))
const meals = computed(() => dayMeals(day.value))
const products = computed(() => selectedProducts(plan.value, dayNo.value))
const names = computed(() => plan.value?.members?.map(member => member.display_alias || '家庭成员').join('、'))
onLoad(options => { try { route.value = validPlanRoute(options) } catch (e) { error.value = e.message } })
onShow(load)
function load() { if (route.value) return run(async active => { plan.value = null; const result = await commerce.servicePlan(route.value.sn, route.value.version); if (active()) plan.value = result }) }
function next() { if (plan.value?.status === 'available') uni.navigateTo({url:'/pages/exclusive-plans/schedule?plan_sn='+encodeURIComponent(route.value.sn)+'&plan_version='+route.value.version}) }
const back = () => uni.navigateBack()
</script>
<template>
  <view class="screen exclusive-screen detail-screen">
    <AppNavBar><view class="nav-row"><button class="icon-button" aria-label="返回" @click="back">‹</button><text class="nav-title">计划详情</text></view></AppNavBar>
    <view v-if="error" class="plan-surface plan-empty"><text class="plan-caption">{{error}}</text><button class="plan-secondary" :disabled="busy" @click="load">重新读取</button><button class="plan-text-link" @click="back">返回选择计划</button></view>
    <text v-else-if="busy && !plan" class="plan-notice">正在读取计划…</text>
    <template v-if="plan">
      <view class="plan-heading"><text class="plan-title">{{plan.tier_name}}</text><text class="plan-caption">{{plan.difference}}</text><text class="plan-tiny">21 天 · {{names}}</text></view>
      <FoodImageSlot class="plan-photo" :src="plan.display?.image_url" :label="plan.tier_name"/>
      <view class="section-top"><text class="plan-section-title">每天，好好吃饭</text><text class="plan-tiny">完整三餐</text></view>
      <scroll-view scroll-x class="day-tabs" :show-scrollbar="false"><view class="day-tabs-inner"><button v-for="item in plan.days" :key="item.day_no" :class="{chosen:Number(item.day_no)===dayNo}" @click="dayNo=Number(item.day_no); expanded=''">第 {{item.day_no}} 天</button></view></scroll-view>
      <view class="plan-surface meal-list">
        <view v-for="meal in meals" :key="meal.type" class="meal-group">
          <text class="meal-label">{{meal.name}}</text>
          <view v-for="dish in meal.dishes" :key="dish.id" class="dish">
            <button class="dish-heading" @click="expanded=expanded===dish.id?'':dish.id"><FoodImageSlot class="dish-photo" :src="dish.recipe_snapshot?.image_url" :label="dish.recipe_name"/><view><text>{{dish.recipe_name}}</text><text class="plan-tiny">查看份量与做法</text></view><text class="plan-caption">{{expanded===dish.id?'−':'›'}}</text></button>
            <view v-if="expanded===dish.id" class="dish-details"><view v-for="portion in dish.recipe_snapshot?.member_portions || []" :key="portion.member_ref" class="portion"><text>{{memberName(plan, portion.member_ref)}}</text><text>{{portion.grams}} g</text></view><text v-for="(step,index) in dish.recipe_snapshot?.steps || []" :key="index" class="step">{{index+1}}. {{typeof step==='string'?step:step.instruction || step.description || step.text}}</text></view>
          </view>
        </view>
      </view>
      <view class="section-top"><text class="plan-section-title">第 {{dayNo}} 天食材</text></view>
      <view class="plan-surface"><view v-for="item in products" :key="item.sku_id" class="ingredient"><FoodImageSlot class="ingredient-photo" :src="item.product_snapshot?.image_url" :label="item.product_snapshot?.product_name"/><view><text>{{item.product_snapshot?.product_name}}</text><text class="plan-tiny">{{item.product_snapshot?.specification || item.product_snapshot?.spec || ''}} × {{item.quantity}}</text></view><text>{{priceText(item.total_price_cent)}}</text></view><text v-if="!products.length" class="plan-caption">食材正在核对，暂不可购买</text></view>
      <view class="plan-surface"><view class="plan-row"><text>首批食材预估</text><text>{{priceText(plan.first_batch_goods_cent)}}</text></view><view class="plan-row"><text>21 天食材与服务</text><text>{{priceText(plan.estimated_subtotal_cent)}}</text></view><text class="plan-tiny">配送费选址后计算，结算时确认最终金额。</text></view>
      <text v-if="plan.status!=='available'" class="plan-notice">计划仍在核对，暂不可购买。</text>
      <view class="plan-fixed"><button class="plan-primary" :disabled="busy || plan.status!=='available'" @click="next">选择配送安排 <text>→</text></button></view>
    </template>
  </view>
</template>
<style scoped>
@import '../../styles/exclusive-plan.css';
.detail-screen{padding-bottom:calc(160rpx + env(safe-area-inset-bottom))}.section-top{display:flex;align-items:center;justify-content:space-between;margin:38rpx 2rpx 18rpx}.day-tabs{white-space:nowrap;width:100%}.day-tabs-inner{display:inline-flex;gap:12rpx}.day-tabs button{font-size:26rpx;padding:16rpx 22rpx;border-radius:40rpx;background:#eef1f6;color:#748199;line-height:1.5}.day-tabs button.chosen{background:#292d35;color:white}.meal-list{padding:8rpx 26rpx}.meal-group{padding:26rpx 0;border-bottom:1rpx solid #eef1f5}.meal-group:last-child{border:0}.meal-label{font-size:26rpx;color:#6d7e99}.dish-heading{display:flex;align-items:center;text-align:left;gap:20rpx;background:none;padding:18rpx 0;width:100%;font-size:29rpx;line-height:1.6}.dish-heading>view:not(.food-image-slot){flex:1;min-width:0}.dish-heading>view>text{display:block}.dish-photo{width:108rpx;height:94rpx;border-radius:16rpx;flex-shrink:0}.dish-details{padding:4rpx 0 18rpx;font-size:26rpx;color:#65738d;line-height:1.7}.portion{display:flex;justify-content:space-between;gap:20rpx}.step{display:block;margin-top:12rpx}.ingredient{display:flex;align-items:center;gap:18rpx;padding:16rpx 0;font-size:27rpx}.ingredient-photo{width:88rpx;height:88rpx;flex-shrink:0;border-radius:16rpx}.ingredient>view:not(.food-image-slot){flex:1;min-width:0}.ingredient>view>text{display:block}.ingredient>text{flex-shrink:0}
</style>
