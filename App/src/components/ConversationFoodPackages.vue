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
.package-results{margin:18px 0 0}.package-card{border:0;border-radius:12px;background:#f7f7f7;padding:16px;margin:14px 0}.package-image{width:100%;height:180px;border-radius:8px}.package-copy{padding:14px 0 0}.package-name{display:block;font-size:18px;font-weight:600;line-height:1.5;color:#222}.package-spec,.package-note{display:block;font-size:13px;color:#808080;line-height:1.75;margin-top:6px}.package-price{display:block;font-size:26px;font-weight:500;line-height:1.4;margin-top:12px;font-variant-numeric:tabular-nums;color:#222}.package-price>text{font-size:15px;font-weight:400;margin-right:3px}.package-button{display:flex;justify-content:center;align-items:center;gap:16px;width:auto;min-height:44px;background:#111;border-radius:8px;color:#fff;font-size:15px;line-height:1.5;margin:14px 0 0 auto;padding:10px 18px}.package-button:after{border:0}.package-button[disabled]{opacity:.45}
</style>
