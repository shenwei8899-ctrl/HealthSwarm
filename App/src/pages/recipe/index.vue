<script setup>
import AppNavBar from '../../components/AppNavBar.vue'
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { backHome, getProfile } from '../../utils/profile.js'
import { todayPlan } from '../../utils/meal-state.js'
import { getOrder } from '../../utils/orders.js'
import { createDiabetesCasePlan, DIABETES_CASE_ID } from '../../utils/health-cases.js'
import { applyMealCustomization, getMealSwap } from '../../utils/meal-customization.js'
import { createDishGuide, mealFromRoute } from '../../utils/meal-flow.js'

const meal = ref('晚餐')
const dishName = ref('')
const caseId = ref('')
const orderId=ref(''),batchIndex=ref(1)
const plan=computed(()=>todayPlan(getProfile(),meal.value))
const guide=computed(()=>{const order=getOrder(orderId.value);const saved=order?.cookingGuides?.find(b=>b.index===batchIndex.value)?.guides.find(g=>g.meal===meal.value)||order?.cookingGuide;return saved?.dishGuides.find(g=>g.name===dishName.value)||createDishGuide(plan.value,dishName.value)})

onLoad(options => {
  orderId.value=options.id||'';batchIndex.value=Number(options.batch)||1
  meal.value = mealFromRoute(options.meal)
  dishName.value = decodeURIComponent(options.dish || '')
  caseId.value = options.case === 'diabetes' ? DIABETES_CASE_ID : ''
})
</script>

<template>
  <view class="screen recipe-screen">
    <AppNavBar><view class="nav-row"><button class="icon-button" @click="backHome">‹</button><text class="nav-title">单道菜做法</text><text class="pill">购买前预览</text></view></AppNavBar>
    <view class="recipe-hero"><image :src="guide.image" mode="aspectFill"/><view><text class="eyebrow">{{meal}} · 做法预览</text><text class="display-title">{{guide.name}}</text><text>{{guide.minutes}} 分钟左右 · 测试菜谱</text></view></view>
    <view class="card info-card"><view><text>预计制作时间</text><text>{{guide.minutes}} 分钟</text></view><view><text>页面用途</text><text>购买前查看做法</text></view></view>
    <video v-if="guide.videoUrl" :src="guide.videoUrl" controls class="guide-video"/>
    <view class="section-block"><text class="section-title">所需食材及用量</text><view class="ingredient-list card"><view v-for="item in guide.ingredients" :key="item"><text>•</text><text>{{item}}</text></view></view></view>
    <view class="section-block"><view class="section-head"><text class="section-title">完整图文制作步骤</text><text>按顺序操作</text></view><view v-for="(step,index) in guide.steps" :key="step" class="step-card card"><text>{{String(index+1).padStart(2,'0')}}</text><view class="step-content"><text>{{step}}</text><image v-if="guide.stepImages?.[index]" :src="guide.stepImages[index]" mode="widthFix" class="step-image"/></view></view></view>
    <view class="notice-card"><text class="section-title">注意事项</text><text v-for="item in guide.notes" :key="item">{{item}}</text></view>
    <button class="primary-button back-button" @click="backHome">返回本餐安排与购买清单</button>
    <text class="safe-note">本页是购买前做法预览，不代表已经收到食材，也不替代收货后的正式制作烹饪页面。</text>
  </view>
</template>

<style scoped>
.step-content{flex:1;display:flex;flex-direction:column;gap:18rpx;font-size:23rpx;line-height:1.7}.step-image{width:100%;border-radius:18rpx}
.recipe-screen{padding-bottom:60rpx}.recipe-hero{position:relative;margin:30rpx 0 20rpx;overflow:hidden;border-radius:34rpx;background:#246b50;color:white;box-shadow:0 20rpx 45rpx rgba(31,107,82,.2)}.recipe-hero image{width:100%;height:310rpx;display:block}.recipe-hero>view{display:flex;flex-direction:column;gap:10rpx;padding:26rpx}.recipe-hero .eyebrow{color:#e0eee5}.recipe-hero .display-title{color:white;font-size:44rpx}.recipe-hero>view>text:last-child{color:#d4e6d9;font-size:20rpx}.info-card{display:grid;grid-template-columns:1fr 1fr;padding:22rpx}.info-card>view{display:flex;flex-direction:column;gap:7rpx}.info-card view text:first-child{color:#71827a;font-size:18rpx}.info-card view text:last-child{font-size:22rpx;font-weight:800}.video-card{margin-top:22rpx;padding:24rpx}.section-head{display:flex;align-items:baseline;justify-content:space-between;gap:12rpx}.section-head>text:last-child{color:#77877f;font-size:18rpx}.guide-video{width:100%;height:360rpx;margin-top:18rpx;border-radius:18rpx}.video-pending{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8rpx;min-height:240rpx;margin-top:18rpx;border:2rpx dashed #cddacb;border-radius:18rpx;background:#f1f4e9;color:#597268}.video-pending text:first-child{width:62rpx;height:62rpx;display:flex;align-items:center;justify-content:center;border-radius:50%;background:#dce9d6;color:#246b50;font-size:26rpx}.video-pending text:nth-child(2){font-size:22rpx;font-weight:800}.video-pending text:last-child{font-size:18rpx}.section-block{margin-top:30rpx}.section-block>.section-title,.section-block>.section-head{display:flex;margin-bottom:16rpx}.ingredient-list{padding:10rpx 22rpx}.ingredient-list>view{display:flex;gap:12rpx;padding:15rpx 0;border-bottom:1rpx solid rgba(24,54,46,.08);font-size:21rpx}.ingredient-list>view:last-child{border:0}.ingredient-list view text:first-child{color:#246b50;font-weight:900}.step-card{display:flex;align-items:flex-start;gap:18rpx;margin-bottom:13rpx;padding:22rpx}.step-card>text:first-child{color:#246b50;font-size:27rpx;font-weight:900}.step-card>text:last-child{color:#334f43;font-size:22rpx;line-height:1.6}.notice-card{display:flex;flex-direction:column;gap:10rpx;margin-top:28rpx;padding:24rpx;border-radius:26rpx;background:#f2dfd3;color:#765348}.notice-card>text:not(:first-child){font-size:19rpx;line-height:1.6}.back-button{margin-top:28rpx}.safe-note{display:block;margin-top:14rpx;text-align:center}
</style>
