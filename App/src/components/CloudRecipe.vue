<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import DishNutritionCard from './DishNutritionCard.vue'
import { request } from '../services/request.js'
import { getSession } from '../services/session.js'
import { storageContext } from '../services/storage.js'
const props=defineProps({route:Object})
const dish=ref(null),error=ref(''),busy=ref(false)
let alive=true,revision=0,scope=storageContext()
function back(){uni.navigateBack()}
async function load(){
 const mine=++revision,ticket=storageContext();busy.value=true;error.value='';dish.value=null
 try{
  const r=props.route
  const {data}=await request({path:'/api/family/'+encodeURIComponent(getSession().householdId)+'/daily-arrangements/'+r.date+'/meals/'+r.meal+'?arrangement_id='+encodeURIComponent(r.arrangement)+'&version='+Number(r.version)})
  if(!alive||mine!==revision||ticket!==storageContext())return
  if(data.arrangement_id!==r.arrangement||data.version!==Number(r.version)||data.meal?.type!==r.meal)throw new Error('本餐已更新，请返回重新核对。')
  const found=data.meal.dishes.find(item=>item.id===r.dish)
  if(!found?.steps?.length)throw new Error('此菜谱版本暂时无法读取，请返回重新核对。')
  dish.value=found
 }catch(e){if(alive&&mine===revision&&ticket===storageContext()){dish.value=null;error.value=e.message}}finally{if(alive&&mine===revision&&ticket===storageContext())busy.value=false}
}
onMounted(load)
onShow(()=>{if(scope!==storageContext()){scope=storageContext();dish.value=null;void load()}})
onUnmounted(()=>{alive=false;revision++})
</script>
<template>
 <view class="screen cloud-recipe"><AppNavBar><view class="nav-row"><button class="icon-button" @click="back">‹</button><text class="nav-title">菜品做法</text><text></text></view></AppNavBar>
  <text v-if="busy" class="safe-note">正在读取已保存菜谱…</text><view v-if="error" class="card recipe-error"><text>{{error}}</text><button class="secondary-button" @click="load">重新读取</button></view>
  <template v-if="dish"><view class="recipe-title"><text class="eyebrow">本餐已保存菜谱</text><text class="display-title">{{dish.name}}</text></view><DishNutritionCard :nutrition="dish.nutrition"/>
   <view class="recipe-section"><text class="section-title">所需食材 · 本餐合计</text><view class="card ingredient-list"><text v-for="ingredient in dish.ingredients" :key="ingredient.food_id">{{ingredient.name}} {{ingredient.planned_grams}}g</text></view></view>
   <view class="recipe-section"><text class="section-title">制作步骤</text><view v-for="(step,index) in dish.steps" :key="index" class="card recipe-step"><text class="step-number">{{String(index+1).padStart(2,'0')}}</text><text>{{step}}</text></view></view>
   <view class="recipe-source"><text>营养依据</text><text>{{dish.nutritionSource?.source}} · {{dish.nutritionSource?.edition}} · {{dish.nutritionSource?.dataset_version}}</text></view>
  </template><button class="primary-button" @click="back">返回本餐安排</button>
 </view>
</template>
<style scoped>.cloud-recipe{background:#fafafa}.recipe-title{padding:40rpx 0}.recipe-section{margin:34rpx 0}.ingredient-list{padding:24rpx;margin-top:18rpx}.ingredient-list text{display:block;font-size:28rpx;line-height:1.9;color:#555}.recipe-step{display:flex;gap:24rpx;padding:28rpx;margin-top:18rpx;font-size:28rpx;line-height:1.8}.step-number{color:#999;flex-shrink:0}.recipe-source{padding:24rpx 0;font-size:23rpx;line-height:1.8;color:#888}.recipe-source text{display:block}.recipe-error{padding:28rpx}.cloud-recipe .secondary-button{color:#333}.cloud-recipe :deep(.nutrition-card){background:#f0f0f3;color:#333}</style>

<style scoped>
.cloud-recipe :deep(.dish-nutrition-card){background:#f1f1f3}.cloud-recipe :deep(.nutrition-title),.cloud-recipe :deep(.nutrition-value){color:#333}.cloud-recipe :deep(.nutrition-badge){background:#e6e6ea;color:#555}.cloud-recipe :deep(.nutrition-label),.cloud-recipe :deep(.nutrition-unit),.cloud-recipe :deep(.nutrition-note),.cloud-recipe :deep(.nutrition-basis){color:#777}
</style>
