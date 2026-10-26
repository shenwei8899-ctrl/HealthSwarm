<script setup>
import AppNavBar from './AppNavBar.vue'
import AppIcon from './AppIcon.vue'
defineProps({ scrollTarget: String, voiceBusy: Boolean })
defineEmits(['history', 'profile', 'shortcut'])
const shortcuts = [
  { key: 'plans', icon: 'calendar', name: 'AI专属计划' },
  { key: 'family', icon: 'family', name: '家庭档案' },
  { key: 'camera', icon: 'camera', name: '拍照记餐' },
  { key: 'today', icon: 'record', name: '今日餐单' },
  { key: 'community', icon: 'chat', name: '加入社群' },
]
</script>
<template>
  <view class="screen nutritionist-layout chat-screen" :class="{'voice-is-busy':voiceBusy}">
    <AppNavBar><view class="nav-row chat-nav"><button class="history-button" aria-label="查询历史记录" @click="$emit('history')"><AppIcon name="history" :size="38"/><text class="history-label">历史</text></button><view class="assistant-title"><text>家庭营养师</text><text class="nav-subtitle">你的家庭饮食伙伴</text></view><button class="me-button" aria-label="进入我的页面" @click="$emit('profile')"><AppIcon name="user" :size="40"/></button></view></AppNavBar>
    <scroll-view class="conversation" scroll-y :scroll-into-view="scrollTarget"><slot/><view class="conversation-spacer"/></scroll-view>
    <view class="composer-wrap"><scroll-view class="tool-strip" scroll-x :show-scrollbar="false"><view class="tool-row"><button v-for="item in shortcuts" :key="item.key" class="tool-chip" @click="$emit('shortcut',item.key)"><AppIcon :name="item.icon" :size="40"/><text>{{item.name}}</text></button></view></scroll-view><slot name="composer"/></view>
    <slot name="overlays"/>
  </view>
</template>
<style scoped>
.nutritionist-layout{height:100vh;height:100dvh;display:flex;flex-direction:column;background:#fff;padding:12rpx 28rpx calc(env(safe-area-inset-bottom) + 14rpx);overflow:hidden}.chat-nav{flex-shrink:0;gap:12rpx}.history-button,.me-button{min-width:44px;min-height:44px;display:flex;align-items:center;justify-content:center;gap:8rpx;color:#272b32}.history-label{font-size:25rpx}.me-button{border-radius:50%;color:#52617b}.assistant-title{display:flex;flex-direction:column;align-items:center;gap:2rpx;min-width:0}.assistant-title>text:first-child{font-size:32rpx;font-weight:600;white-space:nowrap}.nav-subtitle{font-size:24rpx;color:#939cb0;white-space:nowrap}.conversation{flex:1;min-height:0;width:100%}.conversation-spacer{height:28rpx}.composer-wrap{flex-shrink:0;background:#fff;padding-top:12rpx}.tool-strip{width:100%;margin-bottom:12rpx;white-space:nowrap}.tool-row{display:flex;gap:8rpx;width:100%}.tool-chip{flex:1;min-width:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12rpx;min-height:68px;padding:14rpx 2rpx;border:1rpx solid #eef0f5;border-radius:22rpx;font-size:26rpx;color:#65728c;line-height:1.4}.tool-chip :deep(.app-icon){color:#252b34}.voice-is-busy .conversation,.voice-is-busy .tool-strip{opacity:.35;pointer-events:none}.voice-is-busy .history-button,.voice-is-busy .me-button{pointer-events:none}
.tool-chip:first-child{flex:1.15}.tool-chip>text{white-space:nowrap}
@media(max-width:350px){.tool-chip{font-size:12px;min-height:64px}.tool-row{gap:7rpx}}
/* #ifdef MP-WEIXIN */
.history-label{display:none}.assistant-title>text:first-child{font-size:30rpx}.nav-subtitle{font-size:22rpx}
/* #endif */

</style>
