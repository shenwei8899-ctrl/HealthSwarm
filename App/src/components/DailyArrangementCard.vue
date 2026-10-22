<script setup>
defineProps({ arrangement: Object, disabled: Boolean, family: Boolean })
defineEmits(['open', 'members', 'shop'])
const names = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐' }
</script>

<template>
  <view class="daily-arrangement-card">
    <view class="daily-heading"><view><text class="eyebrow">{{arrangement.date}} · {{family?'家庭安排':'今日安排'}}</text><text class="section-title">{{family?'按成员核对每一餐':'好好吃饭，从今天开始'}}</text></view><text class="saved-label">服务端餐单</text></view>
    <view v-for="meal in arrangement.meals" :key="meal.type" class="daily-row">
      <view class="meal-heading"><text>{{names[meal.type]}}</text><button :disabled="disabled" class="people-button" @click="$emit('members',meal)">{{meal.members.length}} 人用餐 <text>⌄</text></button></view>
      <text class="dish-summary">{{meal.dishes.map(dish=>dish.name).join(' · ')}}</text>
      <view class="meal-bottom"><text>{{meal.members.map(member=>member.name).join('、')}}</text><button :disabled="disabled" @click="$emit('open',meal)">查看本餐安排 ›</button></view>
    </view>
    <button class="shop-button" :disabled="disabled" @click="$emit('shop',arrangement)">一键选购 <text>↗</text></button>
  </view>
</template>

<style scoped>
.daily-arrangement-card{margin-top:20rpx;padding:28rpx;border-radius:30rpx;background:#f5f5f7}.daily-heading,.meal-heading,.meal-bottom{display:flex;align-items:center;justify-content:space-between;gap:12rpx}.daily-heading{align-items:flex-start}.daily-heading .section-title{font-size:34rpx}.saved-label{font-size:20rpx;color:#767680;white-space:nowrap}.daily-row{padding:20rpx 0;border-top:1rpx solid #e5e5ea}.daily-row:nth-child(2){border-top:0;margin-top:16rpx}.meal-heading>text{font-size:29rpx;font-weight:600}.people-button{font-size:23rpx;background:#fff;padding:10rpx 18rpx;border:1rpx solid #e0e0e5;border-radius:99rpx;color:#246b50;min-height:64rpx}.dish-summary{display:block;font-size:26rpx;line-height:1.5;margin-top:4rpx}.meal-bottom>text{font-size:21rpx;color:#767680}.meal-bottom button{font-size:24rpx;color:#246b50;min-height:72rpx}.shop-button{display:flex;gap:16rpx;align-items:center;justify-content:space-between;width:100%;padding:20rpx 24rpx;min-height:80rpx;margin-top:20rpx;border-radius:18rpx;background:#1d1d1f;color:#fff;font-size:26rpx;text-align:left}
</style>
