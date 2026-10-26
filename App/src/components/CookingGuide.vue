<script setup>
import { computed, ref, watch } from 'vue'
import FoodImageSlot from './FoodImageSlot.vue'
import DishNutritionCard from './DishNutritionCard.vue'
const props=defineProps({dishes:{type:Array,default:()=>[]},selected:String,action:String})
defineEmits(['select','action'])
const tab=ref('steps'),nutritionOpen=ref(false)
const key=d=>d.id||d.recipe_ref
const name=d=>d.name||d.recipe_name
const dish=computed(()=>props.dishes.find(d=>key(d)===props.selected)||props.dishes[0])
const notes=computed(()=>Array.isArray(dish.value?.notes)?dish.value.notes.filter(n=>typeof n==='string'&&n.trim()):[])
watch(dish,()=>{if(tab.value==='notes'&&!notes.value.length)tab.value='steps';nutritionOpen.value=false})
const ingredient=i=>typeof i==='string'?i:[i.name,Number.isFinite(Number(i.planned_grams))&&i.planned_grams!=null?i.planned_grams+'g':null].filter(Boolean).join(' ')
function stepCopy(step,index){
 const text=typeof step==='string'?step:step.text||step.description||''
 const split=text.search(/[：:]/)
 return split>0&&split<14?{title:text.slice(0,split),text:text.slice(split+1)}:{title:'第 '+(index+1)+' 步',text}
}
</script>
<template>
 <view v-if="dish" class="cooking-guide">
  <scroll-view v-if="dishes.length>1" class="dish-tabs" scroll-x><view class="dish-tabs-inner"><button v-for="item in dishes" :key="key(item)" :class="{active:key(item)===key(dish)}" :aria-pressed="key(item)===key(dish)" @click="$emit('select',key(item))">{{name(item)}}</button></view></scroll-view>
  <text v-else class="single-dish">{{name(dish)}}</text>
  <FoodImageSlot :src="dish.image_url" :label="name(dish)" class="cooking-hero"/>
  <view class="content-tabs"><button :class="{active:tab==='ingredients'}" :aria-pressed="tab==='ingredients'" @click="tab='ingredients'">食材<view v-if="tab==='ingredients'" class="active-line"/></button><button :class="{active:tab==='steps'}" :aria-pressed="tab==='steps'" @click="tab='steps'">步骤<view v-if="tab==='steps'" class="active-line"/></button><button v-if="notes.length" :class="{active:tab==='notes'}" :aria-pressed="tab==='notes'" @click="tab='notes'">注意事项<view v-if="tab==='notes'" class="active-line"/></button></view>
  <view v-if="tab==='ingredients'" class="ingredient-list"><view v-for="(item,n) in dish.ingredients||[]" :key="n"><text>{{ingredient(item)}}</text></view></view>
  <view v-else-if="tab==='steps'" class="steps-list"><view v-for="(step,n) in dish.steps||[]" :key="n" class="recipe-step"><text class="step-number">{{String(n+1).padStart(2,'0')}}</text><image v-if="typeof step!=='string'&&step.image_url" :src="step.image_url" mode="aspectFill" class="step-image"/><view class="step-copy"><text class="step-title">{{stepCopy(step,n).title}}</text><text class="step-description">{{stepCopy(step,n).text}}</text></view></view><text v-if="!dish.steps?.length" class="unavailable">暂无可用制作步骤</text></view>
  <view v-else class="notes-list"><text v-for="(note,n) in notes" :key="n">{{note}}</text></view>
  <view v-if="dish.nutrition" class="nutrition"><button @click="nutritionOpen=!nutritionOpen"><text>营养信息</text><text>{{nutritionOpen?'收起':'查看'}} ›</text></button><DishNutritionCard v-if="nutritionOpen" :nutrition="dish.nutrition"/></view>
  <button class="guide-action" @click="$emit('action')">{{action}}</button>
 </view>
</template>
<style scoped>
.dish-tabs{margin:4rpx 0 22rpx;background:#f1f3f6;border-radius:999rpx;white-space:nowrap}.dish-tabs-inner{display:flex;padding:5rpx;min-width:100%;box-sizing:border-box}.dish-tabs button{flex:1;min-width:220rpx;min-height:76rpx;padding:14rpx 24rpx;border-radius:999rpx;color:#7a879d;font-size:29rpx;line-height:1.5}.dish-tabs button.active{color:#252b35;background:#fff;box-shadow:0 2rpx 8rpx rgba(34,43,58,.06);font-weight:500}.single-dish{display:block;font-size:32rpx;font-weight:500;margin:0 0 20rpx}.cooking-hero{width:100%;height:310rpx;border-radius:24rpx}.content-tabs{display:flex;background:#f1f3f6;border-radius:999rpx;margin:22rpx 0 14rpx;padding:4rpx;gap:4rpx}.content-tabs button{flex:1;min-height:68rpx;padding:10rpx 8rpx;font-size:27rpx;color:#7a879d;border-radius:999rpx;position:relative}.content-tabs .active{background:#fff;color:#252b35;font-weight:500}.content-tabs .active-line{position:absolute;bottom:0;left:25%;right:25%;height:3rpx;background:#0879f9}.steps-list,.ingredient-list,.notes-list{background:#fff;border:1rpx solid #e9edf3;border-radius:26rpx;padding:4rpx 22rpx}.recipe-step{display:flex;align-items:flex-start;gap:18rpx;padding:22rpx 0;border-bottom:1rpx solid #eff2f6}.recipe-step:last-child{border:0}.step-number{width:54rpx;height:54rpx;display:flex;align-items:center;justify-content:center;background:#f3f5f8;border-radius:50%;font-size:28rpx;color:#3c485d;flex-shrink:0}.step-image{width:132rpx;height:132rpx;border-radius:18rpx;flex-shrink:0}.step-copy{flex:1;min-width:0}.step-title{display:block;font-size:29rpx;font-weight:500;line-height:1.5}.step-description{display:block;font-size:27rpx;line-height:1.75;color:#65728c;margin-top:5rpx}.ingredient-list>view{padding:22rpx 4rpx;border-bottom:1rpx solid #eff2f6;font-size:28rpx;line-height:1.65}.ingredient-list>view:last-child{border:0}.notes-list>text{display:block;padding:18rpx 0;font-size:27rpx;color:#758198;line-height:1.75}.nutrition>button{display:flex;justify-content:space-between;align-items:center;min-height:44px;width:100%;font-size:25rpx;color:#7a879d}.nutrition>button>text:last-child{color:#0674ed}.nutrition :deep(.dish-nutrition-card){background:#f3f5f8;color:#252b35}.nutrition :deep(.nutrition-title),.nutrition :deep(.nutrition-value){color:#252b35}.nutrition :deep(.nutrition-label),.nutrition :deep(.nutrition-note),.nutrition :deep(.nutrition-basis),.nutrition :deep(.nutrition-unit){color:#7a879d}.guide-action{width:100%;min-height:92rpx;margin-top:24rpx;padding:18rpx;border-radius:999rpx;background:#25262a;color:#fff;font-size:30rpx;display:flex;align-items:center;justify-content:center}.unavailable{display:block;padding:32rpx 0;font-size:27rpx;color:#65728c}
</style>
