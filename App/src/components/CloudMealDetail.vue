<script setup>
import FoodImageSlot from './FoodImageSlot.vue'
import AppIcon from './AppIcon.vue'
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { onShow, onHide } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import MealNotes from './MealNotes.vue'
import DinerPicker from './DinerPicker.vue'
import CloudMealPurchase from './CloudMealPurchase.vue'
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
let alive=true,revision=0,scope=storageContext(),loading=null
const client=createDailyArrangementClient({state,send:request,context:()=>({scope:storageContext(),familyId:getSession()?.householdId}),storage:scopedStorage,newId:newHealthRequestId})
const plan=computed(()=>meal.value && ({...meal.value,sourceType:'api',blocked:[],safetyText:'按已保存档案及批准配方计算。已有明确医嘱时优先遵循。',
  memberNotes:meal.value.memberNotes.map(note=>({...note,id:note.memberId,dishes:note.dishes.map(dish=>({...dish,recipeId:dish.dishId,amount:dish.grams,unit:'g'})),notes:[]}))}))
function failure(e,mine,ticket){
  if(!alive||mine!==revision)return
  if(ticket!==storageContext()||[401,403,404,410].includes(Number(e.code))||e.code==='SESSION_CHANGED'){meal.value=null;profile.value=null;diners.value=false;client.reset()}
  busy.value=false;error.value=e.message
}
function load(){
  if(loading)return loading
  const mine=++revision,ticket=storageContext();busy.value=true;meal.value=null;error.value=''
  loading=(async()=>{
  try{
    const r=props.route
    const {data}=await request({path:'/api/family/'+encodeURIComponent(getSession().householdId)+'/daily-arrangements/'+r.date+'/meals/'+r.meal+'?arrangement_id='+encodeURIComponent(r.arrangement)+'&version='+Number(r.version)+(r.daily_plan_version!=null?'&daily_plan_version='+Number(r.daily_plan_version):'')})
    if(!alive||mine!==revision)return
    if(ticket!==storageContext()){failure({code:'SESSION_CHANGED',message:'账号或家庭已变化，请重新读取。'},mine,ticket);return}
    if(data.arrangement_id!==r.arrangement||data.version!==Number(r.version)||data.meal?.type!==r.meal)throw new Error('本餐已更新，请返回今日安排重新读取。')
    meal.value=data.meal
  }catch(e){failure(e,mine,ticket)}
  finally{if(alive&&mine===revision){busy.value=false;loading=null}}
  })()
  return loading
}
async function editMembers(){
  busy.value=true;error.value='';const ticket=storageContext(),mine=revision
  try{const value=await loadCloudProfile();if(!alive||mine!==revision)return;if(ticket!==storageContext()){failure({code:'SESSION_CHANGED',message:'账号或家庭已变化，请重新读取。'},mine,ticket);return};profile.value=value;diners.value=true}
  catch(e){failure(e,mine,ticket)}
  finally{if(alive&&mine===revision)busy.value=false}
}
async function confirm(ids){
  diners.value=false;busy.value=true;const ticket=storageContext(),mine=revision
  try{
    await client.load(props.route.date)
    if(!alive||mine!==revision)return
    if(ticket!==storageContext()){failure({code:'SESSION_CHANGED',message:'账号或家庭已变化，请重新读取。'},mine,ticket);return}
    if(!state.arrangement||state.arrangement.id!==props.route.arrangement||state.arrangement.version!==Number(props.route.version)){meal.value=null;profile.value=null;throw new Error(state.error||'本餐已更新，请返回今日安排核对。')}
    await client.changeMembers(props.route.meal,ids,{dailyPlanVersion:props.route.daily_plan_version!=null?Number(props.route.daily_plan_version):undefined})
    if(!alive||mine!==revision)return
    if(ticket!==storageContext()){failure({code:'SESSION_CHANGED',message:'账号或家庭已变化，请重新读取。'},mine,ticket);return}
    if(state.error){if(!state.arrangement||state.arrangement.version!==Number(props.route.version)){meal.value=null;profile.value=null};throw new Error(state.error)}
    uni.redirectTo({url:'/pages/chat/index'})
  }catch(e){failure(e,mine,ticket)}
  finally{if(alive&&mine===revision)busy.value=false}
}
function recipe(dish){const r=props.route;uni.navigateTo({url:'/pages/recipe/index?arrangement='+encodeURIComponent(r.arrangement)+'&meal='+r.meal+'&date='+r.date+'&version='+r.version+'&dish='+encodeURIComponent(dish.id)+(r.daily_plan_version!=null?'&daily_plan_version='+Number(r.daily_plan_version):'')})}
onMounted(load)
onShow(()=>{if(scope!==storageContext()){scope=storageContext();revision++;loading=null;meal.value=null;profile.value=null;busy.value=false;client.reset()};void load()})
onHide(()=>{revision++;loading=null;meal.value=null;profile.value=null;diners.value=false;busy.value=false;client.reset()})
onUnmounted(()=>{alive=false;revision++;client.dispose()})
const nutritionOpen=ref(false)
</script>
<template>
 <view class="screen cloud-meal-detail">
  <AppNavBar><view class="nav-row"><button class="icon-button" aria-label="返回" @click="uni.navigateBack()">‹</button><text class="nav-title">{{names[route.meal]}}安排</text><button class="nav-link" @click="uni.redirectTo({url:'/pages/chat/index'})">今日安排</button></view></AppNavBar>
  <text v-if="busy" class="safe-note">正在核对本餐…</text>
  <view v-if="error" class="card status" role="alert"><text>{{error}}</text><button :disabled="busy" class="secondary-button" @click="load">重新读取本餐</button><button v-if="state.error" class="secondary-button" @click="uni.redirectTo({url:'/pages/chat/index'})">返回今日安排恢复调整</button></view>
  <template v-if="meal">
   <view class="meal-hero"><view class="hero-copy"><view class="hero-title"><text>今天这顿，</text><text>一起吃好。</text></view><button class="diner-button" :disabled="busy" @click="editMembers"><AppIcon name="user" :size="32"/><text>{{meal.members.map(m=>m.name).join(' · ')}}</text><text class="edit-label">编辑 ›</text></button></view><FoodImageSlot :src="meal.image_url" class="hero-image"/></view>
   <view class="meal-section"><text class="section-title">本餐菜品</text><button v-for="dish in meal.dishes" :key="dish.id" class="dish" @click="recipe(dish)"><FoodImageSlot :src="dish.image_url" :label="dish.name" class="dish-image"/><view class="dish-copy"><text class="dish-name">{{dish.name}}</text><text class="dish-description">{{dish.ingredients.map(i=>i.name).join(' · ')}}</text></view><text class="dish-link">看做法 ›</text></button></view>
   <view class="nutrition-disclosure"><button class="nutrition-toggle" :aria-expanded="nutritionOpen" @click="nutritionOpen=!nutritionOpen"><text>份量与营养</text><text>{{nutritionOpen?'收起':'查看'}} <text>{{nutritionOpen?'−':'›'}}</text></text></button><view v-if="nutritionOpen" class="nutrition-detail"><MealNotes :plan="plan"/></view></view>
   <CloudMealPurchase :key="route.arrangement + ':' + route.version + ':' + route.meal" :meal="meal" :route="route"/>
  </template>
  <DinerPicker :open="diners" :members="profile?.members||[]" :selected="meal?.members.map(m=>m.id)||[]" :meal="names[route.meal]" @close="diners=false" @confirm="confirm"/>
 </view>
</template>
<style scoped>
.cloud-meal-detail{background:#fafbfc;padding-bottom:calc(env(safe-area-inset-bottom) + 180rpx)}.nav-link{min-height:44px;color:#0674ed;font-size:24rpx}.meal-hero{display:flex;align-items:center;position:relative;gap:20rpx;margin:26rpx 0 32rpx;min-height:264rpx}.hero-copy{flex:1;min-width:0;position:relative;z-index:1}.hero-title{display:block;white-space:pre-line;font-size:50rpx;line-height:1.3;font-weight:500;letter-spacing:-1rpx;color:#1f242b}.hero-title>text{display:block;white-space:nowrap}.hero-image{width:256rpx;height:264rpx;border-radius:32rpx}.diner-button{display:inline-flex;align-items:center;gap:12rpx;max-width:100%;padding:8rpx 18rpx;margin-top:26rpx;min-height:44px;border:1rpx solid #e9edf3;border-radius:999rpx;background:#fff;font-size:25rpx;text-align:left}.diner-button>text:first-of-type{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.edit-label{white-space:nowrap;color:#0674ed}.section-title{font-size:31rpx;font-weight:500}.dish{display:flex;align-items:center;width:100%;gap:20rpx;border:1rpx solid #e9edf3;border-radius:26rpx;background:#fff;padding:18rpx;margin-top:14rpx;text-align:left}.dish-image{width:132rpx;height:132rpx}.dish-copy{flex:1;min-width:0}.dish-name{display:block;font-size:29rpx;font-weight:500;line-height:1.5;overflow-wrap:anywhere}.dish-description{display:block;font-size:24rpx;line-height:1.6;color:#65728c;margin-top:8rpx}.dish-link{flex-shrink:0;font-size:25rpx;color:#0674ed}.nutrition-disclosure{margin-top:18rpx;border-bottom:1rpx solid #e9edf3}.nutrition-toggle{display:flex;align-items:center;justify-content:space-between;width:100%;min-height:44px;color:#65728c;font-size:25rpx}.nutrition-toggle>text:last-child{color:#0674ed}.nutrition-detail{padding:0 20rpx 24rpx}.nutrition-detail :deep(.meal-notes){color:#384354}.nutrition-detail :deep(.nutrition-unavailable),.nutrition-detail :deep(.nutrition-lines),.nutrition-detail :deep(.estimate),.nutrition-detail :deep(.cooked-weight),.nutrition-detail :deep(.member-tab),.nutrition-detail :deep(.details-toggle){color:#65728c}.nutrition-detail :deep(.member-tab.active){background:#edf5ff;color:#0674ed}.nutrition-detail :deep(.nutrition-section),.nutrition-detail :deep(.portion-section){border-color:#e7ebf0}.status{padding:24rpx;font-size:27rpx;line-height:1.6}.status button{margin-top:18rpx}
@media(max-width:350px){.hero-title{font-size:46rpx}.hero-image{width:210rpx;height:244rpx}.dish-image{width:116rpx;height:116rpx}.dish{gap:14rpx}.dish-link{font-size:24rpx}}
</style>

<style scoped>
@media(max-width:350px){.dish-description,.dish-link,.nutrition-toggle,.nav-link,.nutrition-detail :deep(.nutrition-unavailable),.nutrition-detail :deep(.estimate),.nutrition-detail :deep(.nutrition-lines){font-size:12px}}
</style>
