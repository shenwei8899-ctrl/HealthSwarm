<script setup>
defineProps({ src: String, label: { type: String, default: '' } })
</script>
<template>
  <view class="food-image-slot" :aria-label="src ? label : undefined" :aria-hidden="!src">
    <image v-if="src" :src="src" :alt="label" mode="aspectFill" />
  </view>
</template>
<style scoped>
.food-image-slot{overflow:hidden;background:#f2f3f5;border-radius:20rpx;flex-shrink:0;width:128rpx;height:128rpx}
.food-image-slot image{display:block;width:100%;height:100%}
</style>
