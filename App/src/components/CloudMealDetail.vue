<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import MealNotes from './MealNotes.vue'
import DinerPicker from './DinerPicker.vue'
import { request } from '../services/request.js'
import { getSession } from '../services/session.js'
import { scopedStorage, storageContext } from '../services/storage.js'
import { loadCloudProfile } from '../services/cloud-profile.js'
import { createDailyArrangementClient, dailyArrangementState } from '../services/daily-arrangement-client.js'
import { newHealthRequestId } from '../services/health-task-flow.js'
const props=defineProps({route:Object})
const meal=ref(null),profile=ref(null),busy=ref(false),error=ref(''),diners=ref(false)
const state=reactive(dailyArrangementState())
const names={breakfast:'早餐',lunch:'午餐',dinner:'晚餐'}
let alive=true,revision=0,scope=storageContext()
const client=createDailyArrangementClient({state,send:request,context:()=>({scope:storageContext(),familyId:getSession()?.householdId}),storage:scopedStorage,newId:newHealthRequestId})
const plan=computed(()=>meal.value && ({...meal.value,sourceType:'api',blocked:[],safetyText:'按已保存档案及批准配方计算。已有明确医嘱时优先遵循。',
  memberNotes:meal.value.memberNotes.map(note=>({...note,id:note.memberId,dishes:note.dishes.map(dish=>({...dish,recipeId:dish.dishId,amount:dish.grams,unit:'g'})),notes:['配方与营养版本：'+JSON.stringify(meal.value.nutritionSource)]}))}))
async function load(){
  const mine=++revision,ticket=storageContext();busy.value=true;meal.value=null;error.value=''
  try{
    const r=props.route
    const {data}=await request({path:'/api/family/'+encodeURIComponent(getSession().householdId)+'/daily-arrangements/'+r.date+'/meals/'+r.meal+'?arrangement_id='+encodeURIComponent(r.arrangement)+'&version='+Number(r.version)})
    if(!alive||mine!==revision||ticket!==storageContext())return
    if(data.arrangement_id!==r.arrangement||data.version!==Number(r.version)||data.meal?.type!==r.meal)throw new Error('本餐已更新，请返回今日安排重新读取。')
    meal.value=data.meal
  }catch(e){if(alive&&mine===revision&&ticket===storageContext())error.value=e.message}
  finally{if(alive&&mine===revision&&ticket===storageContext())busy.value=false}
}
async function editMembers(){
  busy.value=true;error.value='';const ticket=storageContext()
  try{const value=await loadCloudProfile();if(!alive||ticket!==storageContext())return;profile.value=value;diners.value=true}
  catch(e){if(alive&&ticket===storageContext())error.value=e.message}
  finally{if(alive&&ticket===storageContext())busy.value=false}
}
async function confirm(ids){
  diners.value=false;busy.value=true;const ticket=storageContext()
  try{
    await client.load(props.route.date)
    if(!alive||ticket!==storageContext())return
    if(!state.arrangement||state.arrangement.id!==props.route.arrangement||state.arrangement.version!==Number(props.route.version))throw new Error('本餐已更新，请返回今日安排核对。')
    await client.changeMembers(props.route.meal,ids)
    if(!alive||ticket!==storageContext())return
    if(state.error)throw new Error(state.error)
    uni.redirectTo({url:'/pages/chat/index'})
  }catch(e){if(alive&&ticket===storageContext())error.value=e.message}
  finally{if(alive&&ticket===storageContext())busy.value=false}
}
function recipe(dish){const r=props.route;uni.navigateTo({url:'/pages/recipe/index?arrangement='+encodeURIComponent(r.arrangement)+'&meal='+r.meal+'&date='+r.date+'&version='+r.version+'&dish='+encodeURIComponent(dish.id)})}
function purchase(){const r=props.route;uni.navigateTo({url:'/pages/shop/index?purchase=1&arrangement='+encodeURIComponent(r.arrangement)+'&meal='+r.meal+'&date='+r.date+'&version='+r.version})}
onMounted(load)
onShow(()=>{if(scope!==storageContext()){scope=storageContext();revision++;meal.value=null;profile.value=null;client.reset();void load()}})
onUnmounted(()=>{alive=false;revision++;client.dispose()})
</script>
<template>
 <view class="screen cloud-meal-detail"><AppNavBar><view class="nav-row"><button class="icon-button" @click="uni.navigateBack()">‹</button><text class="nav-title">{{names[route.meal]}}安排</text><button class="text-button" @click="uni.redirectTo({url:'/pages/chat/index'})">今日安排</button></view></AppNavBar>
  <text v-if="busy" class="safe-note">正在核对已保存安排…</text><view v-if="error" class="card status"><text>{{error}}</text><button :disabled="busy" class="secondary-button" @click="load">重新读取本餐</button><button v-if="state.error" class="secondary-button" @click="uni.redirectTo({url:'/pages/chat/index'})">返回今日安排恢复调整</button></view>
  <template v-if="meal"><view class="page-heading"><text class="eyebrow">今日已保存安排</text><text class="display-title">{{names[route.meal]}}，好好吃</text><button class="diner-button" :disabled="busy" @click="editMembers">{{meal.members.map(m=>m.name).join('、')}} · 更改成员 ›</button></view>
   <view class="summary"><MealNotes :plan="plan"/></view><view class="section-head"><text class="section-title">本餐菜品与做法</text></view><button v-for="dish in meal.dishes" :key="dish.id" class="dish card" @click="recipe(dish)"><view><text>{{dish.name}}</text><text>{{dish.ingredients.map(i=>i.name).join(' · ')}}</text></view><text>查看做法 ›</text></button>
   <view class="purchase card"><text class="section-title">准备本餐食材</text><text>购买前会重新核对库存与价格，也可以使用家中已有食材。</text><button class="primary-button" @click="purchase">查看本餐采购清单</button></view>
  </template><DinerPicker :open="diners" :members="profile?.members||[]" :selected="meal?.members.map(m=>m.id)||[]" :meal="names[route.meal]" @close="diners=false" @confirm="confirm"/>
 </view>
</template>
<style scoped>
.cloud-meal-detail{background:#fafafa}.text-button{font-size:24rpx;color:#555}.page-heading{padding:36rpx 0}.diner-button{font-size:26rpx;text-align:left;padding:24rpx 0;color:#666}.summary{padding:8rpx 28rpx 28rpx;background:#eeeef1;border-radius:28rpx}.section-head{margin:42rpx 0 24rpx}.dish{display:flex;justify-content:space-between;align-items:center;text-align:left;width:100%;padding:28rpx;margin:18rpx 0;font-size:26rpx}.dish>view{min-width:0}.dish>view text{display:block}.dish>view text+text{font-size:23rpx;color:#888;margin-top:12rpx}.dish>text{font-size:23rpx;color:#777;flex-shrink:0;margin-left:24rpx}.purchase,.status{padding:28rpx;margin:30rpx 0}.purchase>text{display:block;line-height:1.8}.purchase>text+text{color:#777;font-size:25rpx;margin:16rpx 0}.summary :deep(.meal-notes){color:#333}.summary :deep(.nutrition-lines),.summary :deep(.estimate),.summary :deep(.cooked-weight),.summary :deep(.member-tab),.summary :deep(.details-toggle){color:#666}.summary :deep(.member-tab.active){background:#333;color:#fff}.summary :deep(.nutrition-section),.summary :deep(.portion-section){border-color:#d6d6dc}.cloud-meal-detail :deep(.helper),.cloud-meal-detail :deep(.secondary-button){color:#555}
</style>
