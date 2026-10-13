<script setup>
import { computed } from 'vue'
import { dishNutritionItems, normalizeDishNutrition } from '../utils/dish-nutrition.js'

const props = defineProps({ nutrition: Object })
const normalized = computed(() => normalizeDishNutrition(props.nutrition))
const items = computed(() => dishNutritionItems(normalized.value))
const note = computed(() => ({
  demo: '测试数据 · 示例估算，不是实际营养检测结果',
  calculated: '依据菜谱配方及成品重量估算',
  measured: '依据该版本菜谱成品的营养检测数据',
  unavailable: '营养数据尚未提供，缺失指标显示“暂无数据”',
}[normalized.value.source]))
</script>

<template>
  <view class="card dish-nutrition-card" aria-label="本菜营养信息">
    <view class="nutrition-heading"><text class="nutrition-title">营养信息</text><text class="nutrition-badge">{{ normalized.source === 'measured' ? '营养检测' : '营养估算' }}</text></view>
    <text class="nutrition-basis">每 100 克可食部分 · 熟制后</text>
    <view class="nutrition-grid">
      <view v-for="item in items" :key="item.key" class="nutrition-item">
        <text class="nutrition-label">{{ item.label }}</text>
        <view class="nutrition-value" :class="{ missing: !item.available }"><text>{{ item.text }}</text><text v-if="item.available" class="nutrition-unit">{{ item.unit }}</text></view>
      </view>
    </view>
    <text class="nutrition-note">{{ note }}</text>
  </view>
</template>

<style scoped>
.dish-nutrition-card{margin:20rpx 0;padding:28rpx 24rpx 20rpx;border-radius:32rpx}
.nutrition-heading{display:flex;align-items:center;justify-content:space-between;gap:12rpx}
.nutrition-title{color:#244d3c;font-size:28rpx;font-weight:600;line-height:1.4}
.nutrition-badge{flex-shrink:0;padding:6rpx 12rpx;border-radius:10rpx;background:#edf5f0;color:#367057;font-size:18rpx;line-height:1.5}
.nutrition-basis{display:block;margin:8rpx 0 26rpx;color:#74847b;font-size:20rpx;line-height:1.5}
.nutrition-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:28rpx 16rpx}
.nutrition-item{min-width:0;display:flex;flex-direction:column;gap:8rpx}
.nutrition-label{color:#6d7e75;font-size:21rpx;line-height:1.5}
.nutrition-value{display:flex;align-items:baseline;flex-wrap:wrap;gap:6rpx;color:#234c3c;font-size:36rpx;font-weight:600;line-height:1.3;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.nutrition-unit{color:#77867e;font-size:20rpx;font-weight:400}
.nutrition-value.missing{color:#77867e;font-size:23rpx;font-weight:400;min-height:47rpx;align-items:center}
.nutrition-note{display:block;margin-top:26rpx;padding-top:16rpx;border-top:1rpx solid #eef1ef;color:#78867f;font-size:19rpx;line-height:1.5}
</style>
