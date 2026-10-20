<script setup>
import AppNavBar from './AppNavBar.vue'
import AppIcon from './AppIcon.vue'
defineProps({ scrollTarget: String, voiceBusy: Boolean })
defineEmits(['history', 'profile', 'shortcut'])
const shortcuts = [
  { key: 'plans', icon: 'calendar', name: 'AI专属计划' },
  { key: 'family', icon: 'family', name: '家庭健康档案' },
  { key: 'camera', icon: 'camera', name: '拍照看热量' },
  { key: 'today', icon: 'record', name: '今日饮食计划' },
  { key: 'community', icon: 'chat', name: '加入社群' },
]
</script>
<template>
  <view class="screen nutritionist-layout chat-screen" :class="{'voice-is-busy':voiceBusy}">
    <AppNavBar><view class="nav-row chat-nav"><button class="history-button" aria-label="查询历史记录" @click="$emit('history')"><AppIcon name="history" :size="40"/></button><view class="assistant-title"><text>家庭营养师</text><text class="nav-subtitle">你的家庭饮食伙伴</text></view><button class="me-button" aria-label="进入我的页面" @click="$emit('profile')"><AppIcon name="user" :size="40"/></button></view></AppNavBar>
    <scroll-view class="conversation" scroll-y :scroll-into-view="scrollTarget"><slot/><view class="conversation-spacer"/></scroll-view>
    <view class="composer-wrap"><scroll-view class="tool-strip" scroll-x :show-scrollbar="false"><view class="tool-row"><button v-for="item in shortcuts" :key="item.key" class="tool-chip" @click="$emit('shortcut',item.key)"><AppIcon :name="item.icon" :size="28"/><text>{{item.name}}</text></button></view></scroll-view><slot name="composer"/></view>
    <slot name="overlays"/>
  </view>
</template>
<style scoped>
.nutritionist-layout{height:100vh;height:100dvh;display:flex;flex-direction:column;background:#fff;padding-bottom:calc(env(safe-area-inset-bottom) + 12rpx)}.chat-nav{flex-shrink:0}.history-button,.me-button{width:72rpx;height:80rpx;display:flex;align-items:center;justify-content:center}.assistant-title{text-align:center;display:flex;flex-direction:column;gap:4rpx;min-width:0}.assistant-title>text:first-child{font-size:32rpx;font-weight:600}.nav-subtitle{font-size:21rpx;color:#767680}.conversation{flex:1;min-height:0}.conversation-spacer{height:32rpx}.composer-wrap{padding-top:14rpx;background:#fff;border-top:1rpx solid #f0f0f3;flex-shrink:0}.tool-strip{width:calc(100% + 32rpx);white-space:nowrap;margin-bottom:16rpx}.tool-row{display:inline-flex;gap:12rpx;padding-right:32rpx;align-items:center}.tool-chip{display:inline-flex;align-items:center;gap:8rpx;min-height:76rpx;padding:12rpx 18rpx;border:1rpx solid #e5e5ea;border-radius:18rpx;background:#fff;color:#3c3c43;font-size:23rpx;flex-shrink:0}
.voice-is-busy .conversation,.voice-is-busy .tool-strip{opacity:.35;pointer-events:none}.voice-is-busy .history-button,.voice-is-busy .me-button{pointer-events:none}
</style>
