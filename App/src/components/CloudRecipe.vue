<script setup>
import CookingGuide from './CookingGuide.vue'
import { ref, onMounted, onUnmounted } from 'vue'
import { onShow, onHide } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import DishNutritionCard from './DishNutritionCard.vue'
import { request } from '../services/request.js'
import { getSession } from '../services/session.js'
import { storageContext } from '../services/storage.js'
const props=defineProps({route:Object})
const dish=ref(null),error=ref(''),busy=ref(false)
let alive=true,revision=0,loading=null,scope=storageContext()
function back(){uni.navigateBack()}
function load(){
 if(loading)return loading
 const mine=++revision,ticket=storageContext();busy.value=true;error.value='';dish.value=null
 loading=(async()=>{
 try{
  const r=props.route
  const {data}=await request({path:'/api/family/'+encodeURIComponent(getSession().householdId)+'/daily-arrangements/'+r.date+'/meals/'+r.meal+'?arrangement_id='+encodeURIComponent(r.arrangement)+'&version='+Number(r.version)+(r.daily_plan_version!=null?'&daily_plan_version='+Number(r.daily_plan_version):'')})
  if(!alive||mine!==revision||ticket!==storageContext())return
  if(data.arrangement_id!==r.arrangement||data.version!==Number(r.version)||data.meal?.type!==r.meal)throw new Error('本餐已更新，请返回重新核对。')
  const found=data.meal.dishes.find(item=>item.id===r.dish)
  if(!found?.steps?.length)throw new Error('此菜谱版本暂时无法读取，请返回重新核对。')
  dish.value=found
 }catch(e){if(alive&&mine===revision&&ticket===storageContext()){dish.value=null;error.value=e.message}}finally{if(alive&&mine===revision&&ticket===storageContext()){busy.value=false;loading=null}}
 })()
 return loading
}
onMounted(load)
onShow(()=>{if(scope!==storageContext()){scope=storageContext();revision++;loading=null;dish.value=null;busy.value=false};void load()})
onHide(()=>{revision++;loading=null;dish.value=null;busy.value=false})
onUnmounted(()=>{alive=false;revision++})

</script>
<template>
 <view class="screen cloud-recipe"><AppNavBar><view class="nav-row"><button class="icon-button" aria-label="返回本餐" @click="back">‹</button><text class="nav-title">菜品做法</text><view class="nav-spacer"/></view></AppNavBar>
  <text v-if="busy" class="safe-note">正在读取菜谱…</text><view v-if="error" class="card recipe-error" role="alert"><text>{{error}}</text><button class="secondary-button" @click="load">重新读取</button></view>
  <template v-if="dish"><view class="recipe-heading"><text>跟着步骤，</text><text>做好这一餐。</text></view><CookingGuide :dishes="[dish]" :selected="dish.id" action="返回本餐安排" @action="back"/></template>
 </view>
</template>
<style scoped>.cloud-recipe{background:#fafbfc}.nav-spacer{width:80rpx}.recipe-heading{padding:28rpx 4rpx 30rpx}.recipe-heading text{display:block;font-size:50rpx;font-weight:500;line-height:1.35;letter-spacing:-1rpx}.recipe-error{padding:28rpx;font-size:27rpx;line-height:1.6}.recipe-error button{margin-top:20rpx}</style>
