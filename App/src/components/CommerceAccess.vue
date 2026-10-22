<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { commerce, commerceSessionEpoch } from '../services/commerce.js'
const props=defineProps({entry:Boolean,memberEntry:Boolean,enabled:{type:Boolean,default:true}})
const emit=defineEmits(['ready'])
const ready=ref(false),busy=ref(false),error=ref(''),loginRequired=ref(false)
let epoch=0,alive=true
async function restore(){
  if(!props.enabled||busy.value)return
  const ticket=++epoch;busy.value=true;error.value='';loginRequired.value=false
  try{await commerce.restore();if(alive&&ticket===epoch){ready.value=true;emit('ready')}}
  catch(e){if(alive&&ticket===epoch){ready.value=false;error.value=e.message;loginRequired.value=[401,40100].includes(Number(e.code))}}
  finally{if(alive&&ticket===epoch)busy.value=false}
}
watch(commerceSessionEpoch,()=>{if(!commerce.session()?.token)ready.value=false})
onMounted(restore);onShow(restore);onUnmounted(()=>{alive=false;epoch++})
</script>
<template><view><slot v-if="enabled===false||ready"/><view v-else class="card commerce-status"><text>{{busy?'正在准备购买服务…':error||'购买服务尚未就绪'}}</text><button v-if="!busy&&!loginRequired" class="secondary-button" @click="restore">重新连接</button><button v-if="loginRequired" class="primary-button" @click="uni.reLaunch({url:'/pages/index/index'})">微信登录后继续</button></view></view></template>
<style scoped>.commerce-status{padding:28rpx;display:flex;flex-direction:column;gap:24rpx;line-height:1.7}</style>
