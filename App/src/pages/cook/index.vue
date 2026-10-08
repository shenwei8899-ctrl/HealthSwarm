<script setup>
import AppNavBar from '../../components/AppNavBar.vue'
import { computed, ref, watch } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import FlowRibbon from '../../components/FlowRibbon.vue'
import { backHome, getProfile } from '../../utils/profile.js'
import { createPlan } from '../../utils/demo.js'
import { createCookingGuide, mealToRoute, mealFromRoute } from '../../utils/meal-flow.js'
import { getExclusivePlan } from '../../utils/exclusive-plans.js'
import { getOrder } from '../../utils/orders.js'

const orderId = ref('')
const order = ref(null)
const batchIndex = ref(1)
const selectedMeal = ref('晚餐')
const activeDishName = ref('')
const hasBatches = computed(() => Boolean(order.value?.deliveryBatches?.length))
const batch = computed(() => order.value?.deliveryBatches?.find(item => item.index === batchIndex.value))
const mealChoices = computed(() => batch.value?.meals || (order.value?.cookingGuides?.[0]?.guides.map(g=>({type:g.meal,name:g.dishes.join('、')}))) || (order.value?.sourcePlanId ? getExclusivePlan(order.value.sourcePlanId).days[(batchIndex.value - 1) % getExclusivePlan(order.value.sourcePlanId).days.length].meals : []))
const receivedBatchIndices = computed(() => order.value?.receivedBatchIndices?.length ? order.value.receivedBatchIndices : order.value?.sourcePlanId && order.value?.status === 'delivered' ? [1] : [])
const ready = computed(() => hasBatches.value ? receivedBatchIndices.value.includes(batchIndex.value) : order.value?.status === 'delivered')
const guide = computed(() => {
  if (!order.value) return null
  if (hasBatches.value) {
    const saved = order.value.cookingGuides?.find(item => item.index === batchIndex.value)?.guides.find(item => item.meal === selectedMeal.value)
    if (saved) return saved
    const plan = createPlan(getProfile(), selectedMeal.value)
    return createCookingGuide(plan, getExclusivePlan(order.value.sourcePlanId), { batchIndex: batchIndex.value, meal: selectedMeal.value })
  }
  const savedDaily=order.value.cookingGuides?.[0]?.guides.find(g=>g.meal===selectedMeal.value)
  if(savedDaily)return savedDaily
  if (order.value.cookingGuide) return order.value.cookingGuide
  const plan = createPlan(getProfile(), order.value.meal)
  return createCookingGuide(plan)
})
const dishGuides = computed(() => {
  if (!guide.value) return []
  if (guide.value.dishGuides?.length) return guide.value.dishGuides
  return guide.value.dishes.map(name => ({ name, minutes: guide.value.minutes, image: guide.value.image, ingredients: ['按订单中的本餐食材清单准备'], steps: [...guide.value.steps], notes: ['当前为测试做法，正式做法需由营养与菜谱团队审核。'], videoUrl: guide.value.videoUrl || '' }))
})
const activeDish = computed(() => dishGuides.value.find(item => item.name === activeDishName.value) || dishGuides.value[0])
watch(dishGuides, value => { if (!value.some(item => item.name === activeDishName.value)) activeDishName.value = value[0]?.name || '' }, { immediate: true })
onLoad(options => { orderId.value = options.id || ''; batchIndex.value = Math.max(1, Number(options.batch) || 1);selectedMeal.value=mealFromRoute(options.meal) })
onShow(() => { order.value = getOrder(orderId.value); if (hasBatches.value && !batch.value) batchIndex.value = 1; if (!mealChoices.value.some(item => item.type === selectedMeal.value)) selectedMeal.value = mealChoices.value[0]?.type || '晚餐' })
function viewOrder() { uni.redirectTo({ url: '/pages/orders/detail?id=' + encodeURIComponent(orderId.value) + (hasBatches.value ? '&batch=' + batchIndex.value : '') }) }
function photoUpload() {
  if (!ready.value || !guide.value) return
  uni.navigateTo({ url: '/pages/scan/index?members='+(guide.value.memberIds||[]).join(',')+'&meal=' + mealToRoute(guide.value.meal) + (order.value.caseId ? '&case=diabetes' : '') })
}
</script>

<template>
  <view class="screen cook-screen">
    <AppNavBar><view class="nav-row"><button class="icon-button" @click="backHome">‹</button><text class="nav-title">{{guide?.meal||selectedMeal}}制作</text><text class="pill">演示</text></view></AppNavBar>
    <FlowRibbon :current="5" class="cook-flow" />
    <view v-if="!order" class="state-card card"><text class="section-title">未找到这笔订单</text><text>请从订单详情进入烹饪步骤。</text><button class="primary-button" @click="backHome">返回</button></view>
    <view v-else-if="!ready" class="state-card card"><text class="section-title">收到食材后再开始</text><text>请先在订单详情确认已收到食材，然后查看对应的烹饪步骤。</text><button class="primary-button" @click="viewOrder">查看订单配送进度 →</button></view>
    <template v-else>
      <view class="cook-hero">
        <text class="eyebrow">{{ hasBatches ? order.planName + ' · 第' + batchIndex + '批' : guide.meal + ' · 已确认收货' }}</text>
        <text class="display-title">{{ activeDish?.name || guide.title }}</text>
        <text class="hero-meta">{{ activeDish?.minutes || guide.minutes }} 分钟左右 · 当前查看 {{ activeDish?.name || '本餐做法' }} · 固定演示做法</text>
        <image v-if="activeDish?.image || guide.image" :src="activeDish?.image || guide.image" mode="aspectFill" class="guide-image" />
      </view>
      <view v-if="mealChoices.length>1" class="meal-choices"><button v-for="item in mealChoices" :key="item.type" :class="{ selected: selectedMeal === item.type }" @click="selectedMeal = item.type">{{ item.type }} · {{ item.name }}</button></view>
      <view class="dishes-card card"><view class="dish-tags"><button v-for="dish in dishGuides" :key="dish.name" :class="{selected:activeDish?.name===dish.name}" @click="activeDishName=dish.name">{{ dish.name }}</button></view></view>
      <view class="ingredients-card card"><view class="section-head"><text class="section-title">{{activeDish?.name}}所需食材</text><text>{{activeDish?.minutes}} 分钟</text></view><view class="ingredient-list"><view v-for="item in activeDish?.ingredients" :key="item"><text>•</text><text>{{item}}</text></view></view></view>
      <video v-if="activeDish?.videoUrl" :src="activeDish.videoUrl" controls class="guide-video"/>
      <view class="steps-section"><view class="section-head"><text class="section-title">{{activeDish?.name}}图文制作步骤</text><text>按顺序操作</text></view><view v-for="(step, index) in activeDish?.steps" :key="index" class="step-card card"><text class="step-number">{{ String(index + 1).padStart(2, '0') }}</text><view class="step-content"><text>{{ step }}</text><image v-if="activeDish?.stepImages?.[index]" :src="activeDish.stepImages[index]" mode="widthFix" class="step-image"/></view></view></view>
      <view class="attention-card"><text class="section-title">注意事项</text><text v-for="item in activeDish?.notes" :key="item">{{item}}</text></view>
      <view class="finish-card"><text class="section-title">吃完这一餐，留一张记录</text><text>无需逐道确认完成；查看需要的菜品做法后，可直接记录整餐。</text><button class="primary-button photo-button" @click="photoUpload">去拍照记录这一餐</button></view>
    </template>
  </view>
</template>

<style scoped>
.step-content{flex:1;display:flex;flex-direction:column;gap:18rpx;font-size:23rpx;line-height:1.7}.step-image{width:100%;border-radius:18rpx}
.cook-screen { padding-bottom: calc(env(safe-area-inset-bottom) + 56rpx); }.cook-flow { margin-top: 20rpx; }.cook-hero { display: flex; flex-direction: column; gap: 13rpx; margin-top: 38rpx; padding: 30rpx; border-radius: 32rpx; background: #246b50; color: #ffffff; }.cook-hero .eyebrow { color: #e0eee5; }.cook-hero .display-title { color: #ffffff; font-size: 43rpx; line-height: 1.3; }.hero-meta { color: #d6e8da; font-size: 20rpx; }.guide-image { width: 100%; height: 265rpx; margin-top: 10rpx; border-radius: 20rpx; }.dishes-card,.ingredients-card,.video-card { margin-top: 22rpx; padding: 26rpx; }.dish-tags { display: flex; flex-wrap: wrap; gap: 10rpx; margin-top: 18rpx; }.dish-tags button { padding: 10rpx 15rpx; border:1rpx solid #cfdccc;border-radius: 13rpx; background: #edf3e3; color: #285b45; font-size: 20rpx; }.dish-tags button.selected{border-color:#246b50;background:#246b50;color:white;font-weight:800}.switch-note{display:block;margin-top:14rpx;color:#74847d;font-size:18rpx;line-height:1.5}.section-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12rpx; }.section-head > text:last-child { color: #77877f; font-size: 18rpx; }.ingredient-list{margin-top:14rpx}.ingredient-list>view{display:flex;gap:10rpx;padding:10rpx 0;border-bottom:1rpx solid rgba(24,54,46,.08);font-size:20rpx}.ingredient-list>view:last-child{border:0}.ingredient-list view text:first-child{color:#246b50;font-weight:900}.guide-video { width: 100%; height: 380rpx; margin-top: 18rpx; border-radius: 18rpx; }.video-pending { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8rpx; min-height: 240rpx; margin-top: 18rpx; border: 2rpx dashed #cddacb; border-radius: 18rpx; background: #f1f4e9; color: #597268; }.video-pending text:first-child { width: 62rpx; height: 62rpx; display: flex; align-items: center; justify-content: center; border-radius: 50%; background: #dce9d6; color: #246b50; font-size: 26rpx; }.video-pending text:nth-child(2) { font-size: 22rpx; font-weight: 800; }.video-pending text:last-child { font-size: 18rpx; }.steps-section { margin-top: 32rpx; }.steps-section .section-head { margin-bottom: 18rpx; }.step-card { display: flex; align-items: flex-start; gap: 18rpx; margin-bottom: 13rpx; padding: 22rpx; }.step-number { flex: 0 0 auto; color: #246b50; font-size: 27rpx; font-weight: 900; }.step-card > text:last-child { color: #334f43; font-size: 22rpx; line-height: 1.6; }.attention-card{display:flex;flex-direction:column;gap:9rpx;margin-top:26rpx;padding:24rpx;border-radius:24rpx;background:#f2dfd3;color:#765348}.attention-card>text:not(:first-child){font-size:19rpx;line-height:1.55}.finish-card { display: flex; flex-direction: column; gap: 14rpx; margin-top: 30rpx; padding: 28rpx; border-radius: 28rpx; background: #e6edda; }.finish-card > text:nth-child(2) { color: #62776a; font-size: 20rpx; line-height: 1.6; }.photo-button { align-self: flex-end; min-width: 240rpx; margin-top: 8rpx; }.state-card { display: flex; flex-direction: column; gap: 18rpx; margin-top: 38rpx; padding: 30rpx; }.state-card > text:nth-child(2) { color: #718179; font-size: 21rpx; line-height: 1.6; }
.meal-choices { display: flex; flex-direction: column; gap: 10rpx; margin-top: 20rpx; }.meal-choices button { width: 100%; padding: 16rpx 20rpx; border: 1rpx solid #d9e4d8; border-radius: 18rpx; background: #ffffff; color: #5c7066; font-size: 21rpx; text-align: left; }.meal-choices button.selected { border-color: #246b50; background: #e6f2dd; color: #246b50; font-weight: 800; }
</style>
