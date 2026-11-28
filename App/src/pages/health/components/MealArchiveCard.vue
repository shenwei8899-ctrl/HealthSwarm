<script setup>
import AppIcon from '../../../components/AppIcon.vue'
import FoodImageSlot from '../../../components/FoodImageSlot.vue'
defineProps({card:{type:Object,required:true},disabled:Boolean})
defineEmits(['open'])
</script>
<template>
 <view class="archive-photo-card">
  <view class="archive-photo-head">
   <view class="archive-calendar" aria-hidden="true"><AppIcon name="calendar" :size="40"/></view>
   <view class="archive-date"><text class="archive-caption">{{card.date.caption}}</text><text class="archive-title">{{card.title}}</text></view>
   <text class="archive-saved">已保存</text>
  </view>
  <view class="archive-meals">
   <view v-for="meal in card.meals" :key="meal.type" class="archive-meal">
    <FoodImageSlot :key="card.plan.version+':'+meal.type+':'+meal.image" :src="meal.image" :label="meal.imageLabel||meal.name" fallback-icon lazy-load width="128rpx" height="128rpx" radius="28rpx"/>
    <view class="archive-meal-copy"><text class="archive-meal-tag">{{meal.name}}</text><text class="archive-meal-dishes">{{meal.summary}}</text></view>
   </view>
  </view>
  <view class="archive-photo-footer"><text class="archive-summary">{{card.summary}}</text><button class="archive-open" :disabled="disabled" :aria-label="'查看'+card.title" @click="$emit('open',card.plan)"><text>查看餐单</text><text class="archive-open-arrow" aria-hidden="true">→</text></button></view>
 </view>
</template>
<style scoped>
.archive-photo-card{margin-bottom:28rpx;overflow:hidden;border:2rpx solid rgba(255,255,255,.96);border-radius:42rpx;background:linear-gradient(125deg,#fff,#fcfbff);box-shadow:0 12rpx 30rpx rgba(89,72,133,.045);color:#353747}
.archive-photo-head{display:flex;align-items:center;gap:18rpx;min-height:130rpx;padding:26rpx 24rpx;box-sizing:border-box;background:linear-gradient(110deg,#f6f2ff,#f2edfc 78%,#f6f3ff)}
.archive-calendar{display:flex;align-items:center;justify-content:center;flex:none;width:62rpx;height:66rpx;border-radius:22rpx;color:#9670c8;background:linear-gradient(140deg,#faf7ff,#e9dcfc);box-shadow:inset 0 2rpx 2rpx #fff}
.archive-date{flex:1;min-width:0}.archive-caption{display:block;margin-bottom:8rpx;color:#808092;font-size:23rpx;line-height:1.45}.archive-title{display:block;color:#343448;font-size:32rpx;font-weight:600;line-height:1.45;overflow-wrap:anywhere}
.archive-saved{flex:none;padding:8rpx 13rpx;border:2rpx solid rgba(255,255,255,.9);border-radius:24rpx;background:#f3f0ff;color:#687bb8;font-size:22rpx;line-height:1.4;white-space:nowrap}
.archive-meals{padding:0 24rpx}.archive-meal{display:flex;align-items:center;gap:24rpx;min-height:158rpx;padding:16rpx 0;box-sizing:border-box}.archive-meal+.archive-meal{border-top:1rpx solid #eee8f6}.archive-meal-copy{display:flex;flex:1;flex-direction:column;align-items:flex-start;gap:9rpx;min-width:0;padding:4rpx 0}.archive-meal-tag{padding:3rpx 13rpx;border-radius:13rpx;background:#efe7fc;color:#8762b8;font-size:23rpx;line-height:1.5;font-weight:500}.archive-meal-dishes{display:block;width:100%;color:#3d3b4c;font-size:26rpx;line-height:1.65;overflow-wrap:anywhere;word-break:break-word}
.archive-photo-footer{display:flex;align-items:center;justify-content:space-between;gap:12rpx;min-height:88rpx;padding:0 24rpx;background:linear-gradient(100deg,#f6f0fc,#f0e8fc);box-sizing:border-box}.archive-summary{min-width:0;color:#858094;font-size:23rpx;line-height:1.6;overflow-wrap:anywhere}.archive-open{display:flex;flex:none;align-items:center;justify-content:center;gap:17rpx;min-height:88rpx;margin:0;padding:10rpx 0 10rpx 16rpx;background:transparent;color:#8060ad;font-size:25rpx;line-height:1.5}.archive-open:after{border:0}.archive-open[disabled]{background:transparent;color:#9b8bac;opacity:.65}.archive-open-arrow{font-size:32rpx}
@media(max-width:350px){.archive-photo-head{gap:12rpx;padding-left:20rpx;padding-right:20rpx}.archive-calendar{width:54rpx;height:60rpx}.archive-title{font-size:30rpx}.archive-saved{font-size:20rpx;padding:7rpx 10rpx}.archive-meal{gap:18rpx}.archive-meals{padding:0 20rpx}.archive-photo-footer{padding:0 20rpx}.archive-summary{font-size:22rpx}}
</style>
