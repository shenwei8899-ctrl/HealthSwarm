<script setup>
import FoodImageSlot from './FoodImageSlot.vue'
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
<template>
 <view class="package-results"><text v-if="error" class="safe-note">{{error}}</text><view v-for="offer in offers" :key="offer.offer_token" class="package-card"><FoodImageSlot :src="offer.image_url" :label="offer.name" class="package-image"/><view class="package-copy"><text class="package-name">{{offer.name}}</text><text class="package-spec">{{offer.spec}}</text><text v-if="offer.price_cent!=null" class="package-price"><text>¥</text>{{(offer.price_cent/100).toFixed(2)}}</text><text v-if="offer.note" class="package-note">{{offer.note}}</text><button class="package-button" :disabled="!offer.available" @click="open(offer)">{{offer.available?'查看食材包':'暂不可购买'}}<text v-if="offer.available">→</text></button></view></view></view>
</template>
<style scoped>
.package-results{margin:16rpx 0 0}.package-card{border:1rpx solid #e9edf3;border-radius:26rpx;background:#fff;padding:18rpx;margin:16rpx 0}.package-image{width:100%;height:280rpx;border-radius:20rpx}.package-copy{padding:16rpx 8rpx 4rpx}.package-name{display:block;font-size:32rpx;font-weight:500;line-height:1.5}.package-spec,.package-note{display:block;font-size:25rpx;color:#65728c;line-height:1.6;margin-top:8rpx}.package-price{display:block;font-size:50rpx;font-weight:600;line-height:1.3;margin-top:16rpx;font-variant-numeric:tabular-nums;color:#20242b}.package-price>text{font-size:28rpx;font-weight:400;margin-right:4rpx}.package-button{display:flex;justify-content:center;align-items:center;gap:20rpx;width:100%;min-height:88rpx;background:#25262a;border-radius:999rpx;color:#fff;font-size:29rpx;margin-top:18rpx;padding:16rpx}.package-button[disabled]{opacity:.45}
</style>
