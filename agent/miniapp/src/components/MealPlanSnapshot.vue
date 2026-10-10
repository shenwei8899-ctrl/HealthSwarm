<script setup>
defineProps({ snapshot: { type: Object, required: true } })

const mealNames = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐' }
const nutrients = [
  ['energy_kcal', '能量', 'kcal'],
  ['protein_g', '蛋白质', 'g'],
  ['fat_g', '脂肪', 'g'],
  ['carbohydrate_g', '碳水化合物', 'g'],
  ['sodium_mg', '钠', 'mg'],
]

/** 将服务端科学记数文本展开为十进制文本，不改精度、不重算营养。 */
function decimalText(value) {
  const match = /^(\d+)(?:\.(\d+))?[eE]([+-]?\d+)$/.exec(String(value))
  if (!match) return String(value)
  const exponent = Number(match[3])
  if (!Number.isInteger(exponent) || Math.abs(exponent) > 350) return String(value)
  const digits = match[1] + (match[2] || ''), point = match[1].length + exponent
  const expanded = point <= 0 ? `0.${'0'.repeat(-point)}${digits}`
    : point >= digits.length ? digits + '0'.repeat(point - digits.length)
      : `${digits.slice(0, point)}.${digits.slice(point)}`
  return expanded.replace(/^0+(?=\d)/, '')
}
/** 只显示服务端计划数值，未知量与零值分别呈现。 */
function amount(value, unit) {
  return value === null || value === undefined || value === '' ? '未确定' : `${decimalText(value)} ${unit}`
}
</script>

<template>
  <view class="plan-snapshot">
    <text class="body-copy">计划日期：{{ snapshot.plan_date }}</text>
    <view v-for="meal in snapshot.meals" :key="meal.meal_type" class="meal-block">
      <text class="meal-heading">{{ mealNames[meal.meal_type] }}</text>
      <view v-for="dish in meal.dishes" :key="dish.dish_index" class="snapshot-dish">
        <view class="dish-title"><text>{{ dish.name }}</text><text>{{ amount(dish.planned_grams, 'g') }}</text></view>
        <text class="small-copy">{{ dish.planned_grams === null ? '计划份量尚未确定' : '计划用量，不代表实际摄入' }}</text>
        <view v-if="dish.ingredients?.length" class="ingredient-list">
          <text v-for="(ingredient, index) in dish.ingredients" :key="index">{{ ingredient.name }} · {{ amount(ingredient.planned_grams, 'g') }}</text>
        </view>
        <view class="nutrient-grid">
          <view v-for="[key, name, unit] in nutrients" :key="key"><text>{{ name }}</text><text>{{ amount(dish.nutrition?.[key], unit) }}</text></view>
        </view>
      </view>
      <view class="meal-summary"><text class="small-copy">本餐计划合计</text><view class="nutrient-grid"><view v-for="[key, name, unit] in nutrients" :key="key"><text>{{ name }}</text><text>{{ amount(meal.nutrition?.totals?.[key], unit) }}</text></view></view></view>
    </view>
    <view class="day-summary"><text class="section-title">三餐计划合计</text><view class="nutrient-grid"><view v-for="[key, name, unit] in nutrients" :key="key"><text>{{ name }}</text><text>{{ amount(snapshot.nutrition?.totals?.[key], unit) }}</text></view></view></view>
    <text class="small-copy">{{ snapshot.nutrition?.complete ? '所列营养数据完整，计划量仍是估计。' : '部分营养或份量数据缺失，未确定项没有按零计算。' }}</text>
    <text v-if="snapshot.notice" class="small-copy">{{ snapshot.notice }}</text>
  </view>
</template>

<style scoped>
.meal-block{margin-top:28rpx;border-top:1rpx solid #e6ebe7;padding-top:24rpx}
.meal-heading{display:block;font-size:31rpx;font-weight:600;color:#246b50;margin-bottom:16rpx}
.snapshot-dish{padding:22rpx 0;border-bottom:1rpx solid #edf0ed}
.dish-title{display:flex;justify-content:space-between;align-items:flex-start;gap:20rpx;font-size:29rpx;font-weight:600}
.dish-title text:last-child{flex:none;font-size:26rpx;font-weight:400}
.small-copy{display:block;font-size:23rpx;color:#63636b;line-height:1.65;margin:10rpx 0}
.ingredient-list{display:flex;flex-wrap:wrap;gap:8rpx 18rpx;color:#63636b;font-size:23rpx;line-height:1.6;margin:14rpx 0}
.nutrient-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14rpx 22rpx;margin:16rpx 0;font-size:24rpx}
.nutrient-grid>view{display:flex;flex-direction:column;gap:4rpx;min-width:0}
.nutrient-grid>view>text:first-child{color:#63636b;font-size:22rpx}
.meal-summary{padding:8rpx 0}
.day-summary{padding:26rpx;margin:22rpx 0;border-radius:20rpx;background:#f0f6f1}
</style>
