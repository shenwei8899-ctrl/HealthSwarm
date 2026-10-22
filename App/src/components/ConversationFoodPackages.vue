<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { request } from '../services/request.js'
import { storageContext } from '../services/storage.js'
const props=defineProps({offers:Array,requestId:String})
const offers=ref(props.offers||[]),error=ref('')
let alive=true
onMounted(async()=>{
  if(props.offers)return
  const scope=storageContext()
  try{const {data}=await request({path:'/api/health/v1/conversation-purchases/'+encodeURIComponent(props.requestId)});if(alive&&scope===storageContext())offers.value=data.offers}
  catch(e){if(alive&&scope===storageContext())error.value='这次食材包暂不能读取，可重新询问营养师。'}
})
onUnmounted(()=>alive=false)
function open(offer){if(offer.available)uni.navigateTo({url:'/pages/shop/index?conversation='+encodeURIComponent(props.requestId)+'&offer='+encodeURIComponent(offer.offer_token)})}
</script>
<template><view class="package-results"><text v-if="error" class="safe-note">{{error}}</text><view v-for="offer in offers" :key="offer.offer_token" class="card package-card"><image v-if="offer.image_url" :src="offer.image_url" mode="aspectFill"/><view><text class="section-title">{{offer.name}}</text><text>{{offer.spec}}</text><text v-if="offer.price_cent!=null">¥{{(offer.price_cent/100).toFixed(2)}}</text><text>{{offer.note}}</text><button class="primary-button" :disabled="!offer.available" @click="open(offer)">{{offer.available?'查看食材包':'已变化或暂不可购买，请重新询问'}}</button></view></view></view></template>
<style scoped>.package-results{margin:16rpx 0}.package-card{display:flex;gap:20rpx;padding:24rpx;margin:16rpx 0}.package-card image{width:140rpx;height:140rpx;border-radius:20rpx}.package-card>view{flex:1;min-width:0;display:flex;flex-direction:column;gap:16rpx;font-size:25rpx;line-height:1.6}</style>
