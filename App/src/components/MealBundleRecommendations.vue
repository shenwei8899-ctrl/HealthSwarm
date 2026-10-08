<script setup>
import { computed, ref } from 'vue'
const props = defineProps({ bundles: { type: Array, required: true }, meal: { type: String, required: true } })
defineEmits(['open', 'all'])
const selected = ref('全部')
const categories = computed(() => ['全部', ...new Set(props.bundles.map(b => b.category))])
const visibleBundles = computed(() => props.bundles.filter(b => selected.value === '全部' || b.category === selected.value))
</script>

<template>
  <view v-if="bundles.length" class="recommendations">
    <view class="recommendation-heading"><text>这顿饭的食材，帮你配好了</text><text class="example">示例商品</text></view>
    <scroll-view class="category-scroll" scroll-x :show-scrollbar="false">
      <view class="categories"><button v-for="category in categories" :key="category" class="category" :class="{ selected: selected === category }" @click="selected = category">{{ category }}</button></view>
    </scroll-view>
    <view class="bundle-grid">
      <button v-for="bundle in visibleBundles" :key="bundle.id" class="bundle-product" :aria-label="'选购' + bundle.name" @click="$emit('open', bundle.id)">
        <view class="image-wrap"><image :src="bundle.image" :alt="bundle.name" mode="aspectFill" /><text class="image-tag">{{ bundle.category }}</text></view>
        <text class="product-name">{{ bundle.name }}</text>
        <text class="product-spec">{{ bundle.spec }}</text>
        <view class="product-bottom"><text class="product-price"><text class="currency">¥</text>{{ (bundle.priceCents / 100).toFixed(2) }}</text><text class="product-arrow">↗</text></view>
      </button>
    </view>
    <button class="all-bundles" @click="$emit('all')">查看全部{{ meal }}食材包 <text>→</text></button>
  </view>
</template>

<style scoped>
.recommendations { margin: 0 0 26rpx; padding: 24rpx; border: 1rpx solid #e5e8dc; border-radius: 28rpx; background: #ffffff; box-shadow: 0 12rpx 28rpx rgba(39,70,57,.06); }
.recommendation-heading { display: flex; align-items: center; justify-content: space-between; gap: 8rpx; margin-bottom: 20rpx; color: #1d1d1f; font-size: 24rpx; font-weight: 700; }
.recommendation-heading .example { flex-shrink: 0; color: #88928b; font-size: 18rpx; font-weight: 400; }
.category-scroll { white-space: nowrap; width: 100%; margin-bottom: 22rpx; }
.categories { display: inline-flex; gap: 12rpx; }
.category { display: inline-flex; align-items: center; min-height: 60rpx; padding: 0 22rpx; border: 1rpx solid transparent; border-radius: 18rpx; background: #f1f2eb; color: #6a786e; font-size: 23rpx; line-height: 1.3; }
.category.selected { background: #edf5e6; border-color: #337857; color: #246b50; font-weight: 700; }
.bundle-grid { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 16rpx; }
.bundle-product { width: 100%; min-width: 0; padding: 0; text-align: left; background: none; border-radius: 0; line-height: 1.5; }
.bundle-product::after, .category::after, .all-bundles::after { border: none; }
.image-wrap { position: relative; height: 186rpx; overflow: hidden; border-radius: 18rpx; background: #e9eddd; }
.image-wrap image { display: block; width: 100%; height: 100%; }
.image-tag { position: absolute; left: 9rpx; bottom: 9rpx; padding: 3rpx 8rpx; border-radius: 7rpx; background: rgba(255,254,249,.92); color: #426347; font-size: 17rpx; }
.product-name { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; min-height: 64rpx; margin-top: 13rpx; color: #263f32; font-size: 24rpx; font-weight: 700; line-height: 1.4; }
.product-spec { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-top: 6rpx; color: #849086; font-size: 18rpx; }
.product-bottom { display: flex; align-items: center; justify-content: space-between; margin-top: 10rpx; }
.product-price { color: #9e4d35; font-size: 30rpx; font-weight: 800; letter-spacing: -1rpx; }
.currency { margin-right: 2rpx; font-size: 21rpx; }
.product-arrow { color: #77917b; font-size: 25rpx; }
.all-bundles { display: flex; align-items: center; justify-content: center; gap: 14rpx; width: 100%; min-height: 82rpx; margin-top: 24rpx !important; border-radius: 20rpx; background: #246b50; color: #ffffff; font-size: 26rpx; font-weight: 700; }
</style>
