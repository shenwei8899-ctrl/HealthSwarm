<script setup>
import AppIcon from './AppIcon.vue'
defineProps({title:String,items:Array});defineEmits(['go'])
</script>
<template><view class="group"><text class="group-title">{{title}}</text><view class="menu-list card"><button v-for="item in items" :key="item.name" :class="{compact:!item.desc}" @click="$emit('go',item.url)"><view class="menu-icon"><AppIcon :name="item.icon" :size="38"/></view><view class="menu-copy"><text>{{item.name}}</text><text v-if="item.desc" class="menu-description">{{item.desc}}</text></view><text class="chevron">›</text></button></view></view></template>
<style scoped>.group{margin-top:36rpx}.group-title{display:block;margin:0 0 14rpx 28rpx;color:#63636b;font-size:25rpx;font-weight:500}.menu-list{padding:0 28rpx}.menu-list button{width:100%;display:flex;align-items:center;gap:20rpx;min-height:130rpx;padding:24rpx 0;border-bottom:1rpx solid #ededf0;text-align:left}.menu-list button:last-child{border:0}.menu-icon{height:64rpx;width:64rpx;display:flex;align-items:center;justify-content:center;border-radius:18rpx;background:#f5f5f7;color:#3c3c43;flex-shrink:0}.menu-copy{display:flex;flex-direction:column;gap:8rpx;flex:1;min-width:0}.menu-copy text:first-child{font-size:30rpx;font-weight:500}.menu-copy .menu-description{font-size:25rpx;color:#767680;line-height:1.45}.chevron{color:#a3a3ab;font-size:36rpx}.menu-list button.compact{min-height:52px;padding:14rpx 0}</style>
<style scoped>
/* Approved v5 presentation. */
.group{margin-top:30rpx}.group-title{font-size:25rpx;font-weight:400;margin-left:20rpx;color:#737580}.menu-list{padding:0 22rpx;border-radius:22rpx}.menu-list button{min-height:110rpx;padding:20rpx 0;gap:18rpx}.menu-icon{width:52rpx;height:52rpx;background:transparent;color:#25262a;border-radius:0}.menu-copy text:first-child{font-size:30rpx;font-weight:400}.menu-copy .menu-description{font-size:25rpx;line-height:1.55;color:#737580}.chevron{font-size:32rpx}
</style>

<style scoped>
@media(max-width:350px){.menu-copy .menu-description,.group-title{font-size:12px}.menu-copy text:first-child{font-size:14px}}
</style>
