<script setup>
import {ref,watch} from 'vue'
const props=defineProps({src:String,label:{type:String,default:''}})
const loaded=ref(false),failed=ref(false)
watch(()=>props.src,()=>{loaded.value=false;failed.value=false})
</script>
<template><view class="food-image-slot" :class="{'is-loading':src&&!loaded&&!failed}" :aria-label="label||undefined"><image v-if="src&&!failed" :key="src" :src="src" :alt="label" mode="aspectFill" @load="loaded=true" @error="failed=true"/><text v-if="!src||failed" class="image-fallback">{{label?'暂无图片':'—'}}</text></view></template>
<style scoped>.food-image-slot{position:relative;overflow:hidden;background:#f2f3f5;border-radius:20rpx;flex-shrink:0;width:128rpx;height:128rpx;display:flex;align-items:center;justify-content:center}.food-image-slot image{display:block;width:100%;height:100%}.image-fallback{font-size:12px;color:#92969b;padding:8px;text-align:center}.is-loading:after{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.55),transparent);animation:image-shimmer 1.5s infinite}@keyframes image-shimmer{from{transform:translateX(-100%)}to{transform:translateX(100%)}}@media(prefers-reduced-motion:reduce){.is-loading:after{animation:none}}</style>
