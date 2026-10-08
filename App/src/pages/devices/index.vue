<script setup>
import AppNavBar from '../../components/AppNavBar.vue'
import {backHome} from '../../utils/profile.js'</script>
<template><view class="screen"><AppNavBar><view class="nav-row"><button class="icon-button" @click="backHome">‹</button><text class="nav-title">健康设备</text><text></text></view></AppNavBar><view class="coming-soon"><view>♧</view><text class="display-title">敬请期待</text></view></view></template>
<style scoped>.coming-soon{min-height:65vh;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:32rpx}.coming-soon>view{width:170rpx;height:170rpx;border-radius:50%;background:#e3ecd5;color:#246b50;font-size:90rpx;display:flex;align-items:center;justify-content:center}.coming-soon .display-title{font-size:50rpx}</style>
