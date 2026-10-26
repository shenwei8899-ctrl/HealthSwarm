<script setup>
defineProps({ arrangement: { type: Object, required: true }, disabled: Boolean, family: Boolean })
defineEmits(['open','members','shop'])
const names={breakfast:'早餐',lunch:'午餐',dinner:'晚餐'}
function dateLabel(value){const match=/^\d{4}-(\d{2})-(\d{2})$/.exec(value||'');return match ? `${Number(match[1])}月${Number(match[2])}日` : value}
</script>
<template>
  <view class="daily-arrangement-card">
    <view class="daily-heading"><text class="section-title">{{family?'家庭安排':'今日安排'}}</text><text class="arrangement-date">{{dateLabel(arrangement.date)}}</text></view>
    <view v-for="meal in arrangement.meals" :key="meal.type" class="daily-row">
      <text class="meal-label">{{names[meal.type]}}</text>
      <view class="meal-image" aria-hidden="true" />
      <view class="meal-copy">
        <text class="dish-summary">{{meal.dishes.map(dish=>dish.name).join(' · ')}}</text>
        <view class="meal-actions">
          <button :disabled="disabled" class="people-button" :aria-label="names[meal.type]+'，'+meal.members.length+'人用餐，调整成员'" @click="$emit('members',meal)"><text>{{meal.members.length}}人用餐</text><text class="down-mark" /></button>
          <button class="meal-link" :disabled="disabled" @click="$emit('open',meal)"><text>查看本餐安排</text><text class="chevron">›</text></button>
        </view>
      </view>
    </view>
    <button class="shop-button" :disabled="disabled" @click="$emit('shop',arrangement)"><text>一键选购</text><text class="shop-arrow">→</text></button>
  </view>
</template>
<style scoped>
.daily-arrangement-card{margin-top:24rpx;padding:24rpx 18rpx 18rpx;background:#fff;border:1rpx solid #e9ecf2;border-radius:28rpx}.daily-heading{display:flex;align-items:center;justify-content:space-between;gap:16rpx;padding:0 8rpx 10rpx}.daily-heading .section-title{font-size:34rpx;font-weight:600;color:#202a43}.arrangement-date{font-size:25rpx;color:#65728c;white-space:nowrap}.daily-row{display:flex;align-items:center;gap:16rpx;padding:20rpx 4rpx;min-width:0;border-bottom:1rpx solid #f0f2f5}.daily-row:last-of-type{border-bottom:0}.meal-label{font-size:28rpx;color:#26282f;flex-shrink:0}.meal-image{width:140rpx;height:140rpx;border-radius:20rpx;background:#f3f4f6;flex-shrink:0}.meal-copy{flex:1;min-width:0}.dish-summary{display:block;font-size:29rpx;font-weight:500;line-height:1.55;color:#25272d;overflow-wrap:anywhere}.meal-actions{display:flex;align-items:center;justify-content:space-between;gap:8rpx;flex-wrap:wrap;margin-top:4rpx}.people-button{display:flex;align-items:center;justify-content:center;gap:10rpx;min-height:44px;padding:0 10rpx;font-size:24rpx;color:#0674ed;position:relative;background:transparent;white-space:nowrap}.people-button:before{content:'';position:absolute;left:0;right:0;top:10px;bottom:10px;background:#edf5ff;border-radius:999rpx;z-index:0}.people-button>text{position:relative}.down-mark{width:9rpx;height:9rpx;border-right:2rpx solid currentColor;border-bottom:2rpx solid currentColor;transform:rotate(45deg);margin-top:-5rpx}.meal-link{display:flex;align-items:center;justify-content:flex-end;gap:6rpx;min-height:44px;padding:0;font-size:23rpx;color:#65728c;white-space:nowrap}.chevron{font-size:30rpx}.shop-button{display:flex;align-items:center;justify-content:center;gap:24rpx;width:100%;min-height:48px;margin-top:12rpx;background:#25262a;color:#fff;border-radius:999rpx;font-size:30rpx;font-weight:500}.shop-arrow{font-size:36rpx;font-weight:400}.daily-arrangement-card button[disabled]{opacity:.45}
@media(max-width:350px){.meal-image{width:112rpx;height:124rpx}.daily-row{gap:12rpx}.meal-actions{gap:0}.meal-link,.people-button{font-size:12px}.dish-summary{font-size:14px}.meal-label{font-size:13px}}
</style>

<style scoped>
.daily-arrangement-card{margin-top:28rpx;padding:24rpx 16rpx 16rpx}.daily-heading{padding-bottom:18rpx}.daily-row{border:1rpx solid #edf0f5;border-radius:24rpx;padding:16rpx 12rpx;margin-bottom:12rpx;gap:14rpx;min-height:170rpx}.daily-row:last-of-type{border-bottom:1rpx solid #edf0f5}.meal-image{width:146rpx;height:146rpx}.meal-label{font-weight:500;font-size:27rpx}.dish-summary{font-size:29rpx;font-weight:500}.meal-link{font-size:26rpx}.shop-button{margin-top:6rpx}.daily-heading .section-title{font-size:33rpx;font-weight:500}
@media(max-width:350px){.daily-row{padding:12rpx 8rpx;gap:10rpx}.meal-image{width:108rpx;height:138rpx}.dish-summary{font-size:14px}.meal-label{font-size:13px}.meal-link,.people-button,.arrangement-date{font-size:12px}}
</style>
