<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { commerce, commerceSessionEpoch } from '../services/commerce.js'
import AppNavBar from './AppNavBar.vue'
const props=defineProps({entry:Boolean,memberEntry:Boolean,enabled:{type:Boolean,default:true},pageTitle:String,loadingText:{type:String,default:'正在准备购买服务…'},unavailableText:{type:String,default:'购买服务尚未就绪'}})
const emit=defineEmits(['ready','unavailable','back'])
const ready=ref(false),busy=ref(false),error=ref(''),loginRequired=ref(false)
let epoch=0,alive=true
async function restore(){
  if(!props.enabled||busy.value)return
  const ticket=++epoch;busy.value=true;error.value='';loginRequired.value=false
  try{await commerce.restore();if(alive&&ticket===epoch){ready.value=true;emit('ready')}}
  catch(e){if(alive&&ticket===epoch){ready.value=false;emit('unavailable');error.value=e.message;loginRequired.value=[401,40100].includes(Number(e.code))}}
  finally{if(alive&&ticket===epoch)busy.value=false}
}
watch(commerceSessionEpoch,()=>{if(!commerce.session()?.token){ready.value=false;emit('unavailable')}})
onMounted(restore);onShow(restore);onUnmounted(()=>{alive=false;epoch++})
</script>
<template>
 <view>
  <slot v-if="enabled===false||ready"/>
  <view v-else :class="{'screen commerce-access-screen':pageTitle}">
   <AppNavBar v-if="pageTitle" centered><view class="nav-row"><button class="icon-button" aria-label="返回" @click="emit('back')">‹</button><text class="nav-title">{{pageTitle}}</text><view class="nav-spacer"/></view></AppNavBar>
   <view class="card commerce-status" :class="{'page-status':pageTitle}" :role="error?'alert':'status'" :aria-busy="busy">
    <text>{{busy?loadingText:error||unavailableText}}</text>
    <button v-if="!busy&&!loginRequired" class="secondary-button" @click="restore">重新连接</button>
    <button v-if="loginRequired" class="primary-button" @click="uni.reLaunch({url:'/pages/index/index'})">微信登录后继续</button>
   </view>
  </view>
 </view>
</template>
<style scoped>
.commerce-status{padding:28rpx;display:flex;flex-direction:column;gap:24rpx;line-height:1.7}
.commerce-access-screen{padding-left:24rpx;padding-right:24rpx;background:var(--ui-canvas-gradient,var(--ui-canvas))}.nav-spacer{width:80rpx;flex-shrink:0}
.page-status{margin-top:32rpx;min-height:280rpx;align-items:center;justify-content:center;text-align:center;color:var(--ui-muted);font-size:27rpx;overflow-wrap:anywhere}
</style>
