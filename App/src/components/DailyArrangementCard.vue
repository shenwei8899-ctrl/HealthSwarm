<script setup>
defineProps({ arrangement: Object, disabled: Boolean })
defineEmits(['open', 'members', 'shop'])
const names = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐' }
</script>

<template>
  <view class="daily-arrangement-card">
    <view class="daily-heading"><view><text class="eyebrow">{{arrangement.date}} · 今日安排</text><text class="section-title">好好吃饭，从今天开始</text></view><text class="saved-label">已安排</text></view>
    <view v-for="meal in arrangement.meals" :key="meal.type" class="daily-row">
      <view class="meal-heading"><text>{{names[meal.type]}}</text><button :disabled="disabled" class="people-button" @click="$emit('members',meal)">{{meal.members.length}} 人用餐 <text>⌄</text></button></view>
      <text class="dish-summary">{{meal.dishes.map(dish=>dish.name).join(' · ')}}</text>
      <view class="meal-bottom"><text>{{meal.members.map(member=>member.name).join('、')}}</text><button :disabled="disabled" @click="$emit('open',meal)">查看本餐安排 ›</button></view>
    </view>
    <button class="shop-button" @click="$emit('shop')">选购商城食材 <text>↗</text></button>
  </view>
</template>

<style scoped>
.daily-arrangement-card{padding:30rpx;background:#f1f1f3;border:1rpx solid #e7e7eb;border-radius:28rpx}.daily-heading,.meal-heading,.meal-bottom{display:flex;align-items:center;justify-content:space-between;gap:20rpx}.saved-label{font-size:22rpx;color:#777;white-space:nowrap}.daily-row{padding:30rpx 0;border-bottom:1rpx solid #dedee3}.meal-heading>text{font-size:34rpx;font-weight:600}.people-button{font-size:23rpx;background:#fff;padding:12rpx 18rpx;border:1rpx solid #ddd;border-radius:99rpx;color:#46464e;min-height:72rpx}.people-button text{margin-left:10rpx}.dish-summary{display:block;font-size:28rpx;line-height:1.7;margin:14rpx 0 20rpx;color:#38383d}.meal-bottom>text{font-size:23rpx;color:#777}.meal-bottom button{font-size:25rpx;color:#242428;min-height:64rpx;text-decoration:underline;text-underline-offset:6rpx}.shop-button{display:flex;justify-content:space-between;width:100%;padding:24rpx;margin-top:26rpx;border-radius:20rpx;background:#202023;color:#fff;font-size:28rpx;text-align:left}
</style>
