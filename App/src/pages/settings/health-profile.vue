<script setup>
import AppNavBar from '../../components/AppNavBar.vue'
import SelfAccountDetails from '../../components/SelfAccountDetails.vue'

function back() {
  uni.navigateBack({ fail: () => uni.reLaunch({ url: '/pages/my/index' }) })
}
</script>

<template>
  <view class="screen health-profile">
    <AppNavBar title="我的健康资料"><template #left><button class="icon-button" aria-label="返回我的页面" @click="back">‹</button></template></AppNavBar>
    <SelfAccountDetails/>
  </view>
</template>

<style scoped>
.health-profile{padding-bottom:60rpx}
</style>
