<script setup>
import { ref } from 'vue'
const layout = ref({ paddingTop: '0px', paddingRight: '0px' })
// #ifdef MP-WEIXIN
try {
  const info = uni.getWindowInfo ? uni.getWindowInfo() : uni.getSystemInfoSync()
  const capsule = uni.getMenuButtonBoundingClientRect()
  layout.value = {
    paddingTop: `${info.statusBarHeight || 24}px`,
    paddingRight: `${Math.max(0, info.windowWidth - capsule.left - 16)}px`,
  }
} catch { layout.value = { paddingTop: '28px', paddingRight: '90px' } }
// #endif
</script>
<template><view class="app-nav" :style="layout"><slot /></view></template>
<style scoped>.app-nav{flex-shrink:0;min-width:0;padding-bottom:12rpx}:deep(.nav-row){position:relative;min-height:88rpx;gap:12rpx}:deep(.nav-title){position:absolute;left:50%;transform:translateX(-50%);max-width:55%;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:30rpx;font-weight:600}:deep(.pill){display:none}</style>
