<script setup>
import {onLoad} from '@dcloudio/uni-app'
import {resolveAppEntry} from '../../services/app-entry.js'
onLoad(async()=>{
  try {
    const route=await resolveAppEntry({fresh:true})
    uni.reLaunch({url:route})
  } catch {
    uni.reLaunch({url:'/pages/index/index'})
  }
})
</script>
<template><view/></template>
