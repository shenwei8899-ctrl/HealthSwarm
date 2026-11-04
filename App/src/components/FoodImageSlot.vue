<script setup>
import {computed,ref,watch} from 'vue'
import {publicImageUrl} from '../services/public-images.js'
const props=defineProps({src:String,label:{type:String,default:''},fallbackIcon:Boolean,width:[Number,String],height:[Number,String],radius:[Number,String]})
const loaded=ref(false),failed=ref(false)
const size=value=>typeof value==='number'?value+'px':value
const dimensions=computed(()=>({width:size(props.width),height:size(props.height),borderRadius:size(props.radius)}))
const imageSource=computed(()=>publicImageUrl(props.src))
watch(()=>props.src,()=>{loaded.value=false;failed.value=false})
</script>
<template><view class="food-image-slot" :style="dimensions" :class="{'is-loading':src&&!loaded&&!failed}" :aria-label="label||undefined"><image v-if="src&&!failed" :key="imageSource" :src="imageSource" :alt="label" mode="aspectFill" @load="loaded=true" @error="failed=true"/><view v-if="(!src||failed)&&fallbackIcon" class="fallback-plate" aria-hidden="true"/><text v-else-if="!src||failed" class="image-fallback">{{label?'暂无图片':'—'}}</text></view></template>
<style scoped>.food-image-slot{position:relative;overflow:hidden;background:#f2f3f5;border-radius:20rpx;flex-shrink:0;width:128rpx;height:128rpx;display:flex;align-items:center;justify-content:center}.food-image-slot image{display:block;width:100%;height:100%}.image-fallback{font-size:12px;color:#92969b;padding:8px;text-align:center}.is-loading:after{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,rgba(255,255,255,.55),transparent);animation:image-shimmer 1.5s infinite}@keyframes image-shimmer{from{transform:translateX(-100%)}to{transform:translateX(100%)}}@media(prefers-reduced-motion:reduce){.is-loading:after{animation:none}}</style>

<style scoped>.fallback-plate{width:36px;height:36px;border:2px solid #aebbd0;border-radius:50%;box-shadow:inset 0 0 0 6px #eef2f9;background:#dbe4f2}</style>
