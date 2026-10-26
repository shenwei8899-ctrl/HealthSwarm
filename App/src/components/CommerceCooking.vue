<script setup>
import CookingGuide from './CookingGuide.vue'
import { ref, computed, onMounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import FlowRibbon from './FlowRibbon.vue'
import { commerce } from '../services/commerce.js'
import { useCommercePage } from '../services/commerce-page.js'
const props=defineProps({ id:{type:String,required:true} })
const context=ref(null),selected=ref('')
const {busy,error,run}=useCommercePage(()=>{context.value=null;selected.value=''})
const menu=computed(()=>context.value?.meal_snapshot)
const dishes=computed(()=>menu.value?.dishes||[])
const dish=computed(()=>dishes.value.find(d=>d.recipe_ref===selected.value)||dishes.value[0])
function load(){return run(async active=>{const result=await commerce.cooking(props.id);if(active()){context.value=result;selected.value=dishes.value[0]?.recipe_ref||''}})}
onMounted(load);onShow(load)
function record(){uni.navigateTo({url:'/pages/scan/index?commerce=1&id='+encodeURIComponent(props.id)})}
function viewOrder(){uni.redirectTo({url:'/pages/orders/detail?id='+encodeURIComponent(props.id)})}

</script>
<template>
 <view class="screen cooking-screen"><AppNavBar><view class="nav-row"><button class="icon-button" aria-label="返回订单" @click="viewOrder">‹</button><text class="nav-title">制作烹饪</text><button class="refresh-link" :disabled="busy" @click="load">{{busy?'读取中':'刷新'}}</button></view></AppNavBar>
  <text v-if="error" class="inline-error" role="alert">{{error}}</text><template v-if="context"><view class="cooking-heading"><text>食材到了，</text><text>一起做顿好饭。</text></view><text v-if="menu.is_local_fixture" class="safe-note">本地联调菜谱</text><CookingGuide :dishes="dishes" :selected="selected" action="吃完拍照，记一餐" @select="selected=$event" @action="record"/></template>
 </view>
</template>
<style scoped>.cooking-screen{background:#fafbfc}.refresh-link{min-width:80rpx;min-height:44px;font-size:25rpx;color:#0674ed}.cooking-heading{padding:28rpx 4rpx 30rpx}.cooking-heading text{display:block;font-size:50rpx;font-weight:500;line-height:1.35;letter-spacing:-1rpx}</style>
