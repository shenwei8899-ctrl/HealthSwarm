<script setup>
import { mealLabels } from '../utils/meal-presentation.js'

defineProps({plan:{type:Object,required:true},busy:Boolean,openDate:String,detail:Object})
const emit=defineEmits(['day','retry','exclusive'])
const dayLabel=value=>{const [,month,day]=String(value||'').match(/^\d{4}-(\d{2})-(\d{2})$/)||[];return month?Number(month)+'月'+Number(day)+'日':value}
const ingredientLabel=value=>[value.name||value.food_name||'食材',value.planned_grams==null?'':value.planned_grams+'g'].filter(Boolean).join(' ')
</script>

<template>
  <view class="weekly-card" role="status">
    <view class="weekly-head"><text class="weekly-title">{{plan.total_days}} 天三餐</text><text class="weekly-range">{{dayLabel(plan.start_date)}}起</text></view>
    <view v-if="plan.status==='generating'" class="weekly-progress">正在安排，已完成 {{plan.completed_days}}/{{plan.total_days}} 天。离开页面后可继续读取进度。</view>
    <view v-else-if="plan.status==='failed'" class="weekly-progress">部分日期暂未完成，已保存可恢复的进度。<button :disabled="busy" @click="emit('retry')">重试未完成日期</button></view>
    <view v-else-if="plan.status==='stale'" class="weekly-progress">档案或餐单依据已变化，请重新提出安排请求。</view>
    <template v-else-if="plan.status==='ready'">
      <template v-for="day in plan.days" :key="day.date"><button class="weekly-day" :class="{active:openDate===day.date}" @click="emit('day',day.date)">
        <text class="weekly-date">{{dayLabel(day.date)}}</text>
        <text v-for="meal in day.meals" :key="meal.meal_type" class="weekly-meal">{{mealLabels[meal.meal_type]}}：{{meal.dishes.join('、')}}</text>
        <text class="weekly-more">{{openDate===day.date?'收起详情':'查看食材与做法 ›'}}</text>
      </button><view v-if="openDate===day.date&&detail?.date===day.date" class="weekly-detail">
        <text class="weekly-check">{{detail.validation?.status==='passed'?'已通过餐单核对':'餐单核对状态待确认'}}</text>
        <view v-for="meal in detail.meals||[]" :key="meal.type" class="weekly-detail-meal"><text class="weekly-date">{{mealLabels[meal.type]}}</text>
          <view v-for="dish in meal.dishes||[]" :key="dish.id" class="weekly-detail-dish"><text class="weekly-dish-name">{{dish.name}}</text><text>食材：{{(dish.ingredients||[]).map(ingredientLabel).join('、')}}</text><text v-for="(step,index) in dish.steps||[]" :key="index">{{index+1}}. {{step}}</text></view>
        </view>
      </view></template>
      <view class="weekly-handoff"><text>想看更长期的安排？可以查看 21 天 AI 专属计划。</text><button @click="emit('exclusive')">查看专属计划 ›</button></view>
    </template>
  </view>
</template>

<style scoped>
.weekly-card{margin:18rpx 0;padding:24rpx;border-radius:30rpx;background:#fff;box-shadow:0 8rpx 28rpx #20283b0b;color:#30333d}
.weekly-head{display:flex;justify-content:space-between;align-items:center;gap:16rpx;margin-bottom:16rpx}.weekly-title{font-size:32rpx;font-weight:600}.weekly-range{font-size:23rpx;color:#777b88}
.weekly-progress{padding:18rpx 4rpx;font-size:26rpx;line-height:1.7;color:#606675}.weekly-progress button,.weekly-handoff button{margin:16rpx 0 0;padding:14rpx 18rpx;border-radius:16rpx;background:#edf0fa;color:#455e9f;font-size:25rpx}
.weekly-day{display:flex;flex-direction:column;align-items:flex-start;width:100%;margin:10rpx 0;padding:20rpx;border:1rpx solid #e9e9f0;border-radius:20rpx;background:#fafafe;text-align:left;line-height:1.55}.weekly-day.active{border-color:#8e9fd1;background:#f4f6ff}.weekly-date{font-size:27rpx;font-weight:600}.weekly-meal{font-size:24rpx;color:#595e6b;word-break:break-word}.weekly-more{align-self:flex-end;margin-top:8rpx;font-size:23rpx;color:#586ba9}.weekly-handoff{margin-top:20rpx;padding:20rpx;border-radius:20rpx;background:#f3f4fa;font-size:24rpx;line-height:1.6;color:#5f6270}
.weekly-detail{margin:0 0 14rpx;padding:20rpx;border-radius:18rpx;background:#f8f9fc;font-size:24rpx;line-height:1.7;color:#565d68}.weekly-check{color:#4a6c57}.weekly-detail-meal,.weekly-detail-dish{display:flex;flex-direction:column;gap:6rpx;margin-top:14rpx}.weekly-detail-dish{padding:12rpx;border-radius:12rpx;background:#fff}.weekly-dish-name{font-weight:600;color:#30333d}
</style>
