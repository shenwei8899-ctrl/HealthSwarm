<script setup>
import { recipeTime, recipeIngredients, recipeNutrition } from '../utils/dish-commerce-presentation.js'
import { computed, ref, watch } from 'vue'
import FoodImageSlot from './FoodImageSlot.vue'
import DishNutritionCard from './DishNutritionCard.vue'
import { normalizeDishNutrition } from '../utils/dish-nutrition.js'
import { dishTitle, recipeDisplay } from '../utils/meal-presentation.js'
import { recipeCover } from '../utils/recipe-cover.js'
const props=defineProps({dishes:{type:Array,default:()=>[]},selected:String,action:String,continuous:Boolean})
defineEmits(['select','action'])
const tab=ref('steps'),nutritionOpen=ref(false)
const key=d=>d.id||d.recipe_ref
const name=d=>dishTitle(d)
const dish=computed(()=>props.dishes.find(d=>key(d)===props.selected)||props.dishes[0])
const display=computed(()=>recipeDisplay(dish.value))
const commerceIngredients=computed(()=>recipeIngredients(dish.value))
const commerceNutrition=computed(()=>recipeNutrition(dish.value))
const cover=computed(()=>recipeCover(dish.value))
const summary=computed(()=>{const n=normalizeDishNutrition(dish.value?.nutrition);return [['energyKcal','能量','千卡'],['proteinG','蛋白质','克']].filter(([k])=>n[k]!==null).map(([k,label,unit])=>({label,unit,value:n[k]}))})
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
 <view v-if="dish" class="cooking-guide" :class="{'is-continuous':continuous}">
  <scroll-view v-if="dishes.length>1" class="dish-tabs" scroll-x><view class="dish-tabs-inner"><button role="button" tabindex="0" v-for="item in dishes" :key="key(item)" :class="{active:key(item)===key(dish)}" :aria-pressed="key(item)===key(dish)" @click="$emit('select',key(item))">{{name(item)}}</button></view></scroll-view>
  <text v-else class="single-dish">{{name(dish)}}</text>
  <FoodImageSlot :src="cover?.image_url" :label="name(dish)" width="100%" :height="continuous?'190px':'310rpx'" :radius="continuous?'20px':'24rpx'" class="cooking-hero"/>
  <text class="cooking-duration">{{recipeTime(dish)}}</text>
  <text v-if="dish.image_source?.image_role==='ai_generated'" class="image-credit">AI 生成示意图</text>
  <text v-if="continuous&&cover?.image_source?.publisher" class="image-credit">图片来源：{{cover.image_source.publisher}} · {{cover.image_source.publication}}</text>
  <view v-if="continuous&&summary.length" class="dish-nutrition-summary"><text>每100克成品可食部分</text><view><text v-for="item in summary" :key="item.label">{{item.label}} {{item.value}} {{item.unit}}</text></view></view><view v-if="!continuous" class="content-tabs"><button role="button" tabindex="0" :class="{active:tab==='ingredients'}" :aria-pressed="tab==='ingredients'" @click="tab='ingredients'">食材<view v-if="tab==='ingredients'" class="active-line"/></button><button role="button" tabindex="0" :class="{active:tab==='steps'}" :aria-pressed="tab==='steps'" @click="tab='steps'">步骤<view v-if="tab==='steps'" class="active-line"/></button><button role="button" tabindex="0" v-if="notes.length" :class="{active:tab==='notes'}" :aria-pressed="tab==='notes'" @click="tab='notes'">注意事项<view v-if="tab==='notes'" class="active-line"/></button></view>
  <text v-if="dish.translation_status==='missing'" class="unavailable">菜谱中文译文暂未就绪，请稍后重新读取。</text>
  <text v-if="continuous" class="guide-section-title">食材清单</text><view v-if="continuous||tab==='ingredients'" class="ingredient-list"><view v-for="item in commerceIngredients" :key="item.key" class="ingredient-row"><FoodImageSlot v-if="item.image" :src="item.image" :label="item.name" :width="44" :height="44" :radius="12"/><view><text v-if="item.skuId" class="ingredient-product-name">{{item.name}}</text><text>{{item.amount}}</text></view></view></view>
  <text v-if="continuous" class="guide-section-title">制作步骤</text><view v-if="continuous||tab==='steps'" class="steps-list"><view v-for="(step,n) in display.steps||[]" :key="n" class="recipe-step"><text class="step-number">{{String(n+1).padStart(2,'0')}}</text><image v-if="(typeof step!=='string'&&step.image_url)||dish.step_images?.[n]" :src="(typeof step!=='string'&&step.image_url)||dish.step_images[n]" mode="widthFix" class="step-image"/><view class="step-copy"><text class="step-title">{{stepCopy(step,n).title}}</text><text class="step-description">{{stepCopy(step,n).text}}</text></view></view><text v-if="!display.steps?.length" class="unavailable">暂无可用制作步骤</text></view>
  <view v-if="!continuous&&tab==='notes'" class="notes-list"><text v-for="(note,n) in notes" :key="n">{{note}}</text></view>
  <view v-if="commerceNutrition.length" class="commerce-nutrition"><text class="guide-section-title">商城食材营养说明</text><view v-for="(item,index) in commerceNutrition" :key="index" class="commerce-nutrition-item"><text class="ingredient-product-name">{{item.name}}</text><text>{{item.quote}}</text></view><text class="image-credit">摘自本菜关联的商城食材资料，不代表整道菜或个人摄入量的实测结果。</text></view>
  <view v-if="dish.nutrition&&(!continuous||summary.length)" class="nutrition"><button role="button" tabindex="0" @click="nutritionOpen=!nutritionOpen"><text>营养信息</text><text>{{nutritionOpen?'收起':'查看'}} ›</text></button><DishNutritionCard v-if="nutritionOpen" :nutrition="dish.nutrition"/></view>
  <view v-if="continuous&&display.nutrition_quote" class="recipe-nutrition-quote"><text class="guide-section-title">原食谱营养说明</text><text>{{display.nutrition_quote}}</text><text v-if="dish.display_zh" class="image-credit">原食谱中文助译；数值及计量范围沿用原文，个人营养量尚未核算。</text></view><button role="button" tabindex="0" v-if="action" class="guide-action" @click="$emit('action')">{{action}}</button>
 </view>
</template>
<style scoped>
.dish-tabs{margin:4rpx 0 22rpx;background:var(--ui-soft);border-radius:999rpx;white-space:nowrap}.dish-tabs-inner{display:flex;padding:5rpx;min-width:100%;box-sizing:border-box}.dish-tabs button{flex:1;min-width:220rpx;min-height:76rpx;padding:14rpx 24rpx;border-radius:999rpx;color:var(--ui-muted);font-size:29rpx;line-height:1.5}.dish-tabs button.active{color:#252b35;background:#fff;box-shadow:0 2rpx 8rpx rgba(34,43,58,.06);font-weight:500}.single-dish{display:block;font-size:32rpx;font-weight:500;margin:0 0 20rpx}.cooking-hero{width:100%;height:310rpx;border-radius:24rpx}.content-tabs{display:flex;background:var(--ui-soft);border-radius:999rpx;margin:22rpx 0 14rpx;padding:4rpx;gap:4rpx}.content-tabs button{flex:1;min-height:68rpx;padding:10rpx 8rpx;font-size:27rpx;color:var(--ui-muted);border-radius:999rpx;position:relative}.content-tabs .active{background:#fff;color:#252b35;font-weight:500}.content-tabs .active-line{position:absolute;bottom:0;left:25%;right:25%;height:3rpx;background:var(--ui-accent)}.steps-list,.ingredient-list,.notes-list{background:#fff;border:1rpx solid #e9edf3;border-radius:26rpx;padding:4rpx 22rpx}.recipe-step{display:flex;align-items:flex-start;gap:18rpx;padding:22rpx 0;border-bottom:1rpx solid #eff2f6}.recipe-step:last-child{border:0}.step-number{width:54rpx;height:54rpx;display:flex;align-items:center;justify-content:center;background:var(--ui-soft);border-radius:50%;font-size:28rpx;color:#3c485d;flex-shrink:0}.step-image{width:132rpx;height:132rpx;border-radius:18rpx;flex-shrink:0}.step-copy{flex:1;min-width:0}.step-title{display:block;font-size:29rpx;font-weight:500;line-height:1.5}.step-description{display:block;font-size:27rpx;line-height:1.75;color:var(--ui-muted);margin-top:5rpx}.ingredient-list>view{padding:22rpx 4rpx;border-bottom:1rpx solid #eff2f6;font-size:28rpx;line-height:1.65}.ingredient-list>view:last-child{border:0}.notes-list>text{display:block;padding:18rpx 0;font-size:27rpx;color:var(--ui-muted);line-height:1.75}.nutrition>button{display:flex;justify-content:space-between;align-items:center;min-height:44px;width:100%;font-size:25rpx;color:var(--ui-muted)}.nutrition>button>text:last-child{color:var(--ui-accent)}.nutrition :deep(.dish-nutrition-card){background:var(--ui-soft);color:#252b35}.nutrition :deep(.nutrition-title),.nutrition :deep(.nutrition-value){color:#252b35}.nutrition :deep(.nutrition-label),.nutrition :deep(.nutrition-note),.nutrition :deep(.nutrition-basis),.nutrition :deep(.nutrition-unit){color:var(--ui-muted)}.guide-action{width:100%;min-height:92rpx;margin-top:24rpx;padding:18rpx;border-radius:999rpx;background:var(--ui-accent);color:#fff;font-size:30rpx;display:flex;align-items:center;justify-content:center}.unavailable{display:block;padding:32rpx 0;font-size:27rpx;color:var(--ui-muted)}
</style>

<style scoped>
.cooking-duration{display:block;margin:10px 0;font-size:13px;line-height:1.6;color:var(--ui-muted)}.ingredient-row{display:flex;align-items:center;gap:12px}.ingredient-row>view{min-width:0;overflow-wrap:anywhere}.ingredient-product-name{display:block;font-weight:500;color:var(--ui-text);margin-bottom:4px}.commerce-nutrition-item{font-size:14px;line-height:1.8;margin:12px 0;white-space:pre-wrap;overflow-wrap:anywhere}
.image-credit{display:block;margin-top:8px;font-size:11px;line-height:1.6;color:var(--ui-muted)}.recipe-nutrition-quote{font-size:13px;line-height:1.8;color:var(--ui-muted);padding-bottom:12px}.dish-nutrition-summary{padding:12px 2px;color:var(--ui-muted);font-size:12px}.dish-nutrition-summary>view{display:flex;gap:14px;flex-wrap:wrap;margin-top:5px;color:var(--ui-text);font-size:14px}.is-continuous .single-dish{font-size:20px;line-height:1.5;color:var(--ui-text)}.is-continuous .cooking-hero{height:190px;border-radius:20px}.guide-section-title{display:block;font-size:16px;font-weight:500;margin:22px 0 10px;color:var(--ui-text)}.is-continuous .ingredient-list,.is-continuous .steps-list{border-color:var(--ui-line);border-radius:18px;background:var(--ui-bubble)}.is-continuous .recipe-step{position:relative;display:flex;flex-direction:column;gap:12px;padding:18px 0}.is-continuous .step-number{width:30px;height:30px;font-size:14px;background:var(--ui-accent-soft);color:var(--ui-text)}.is-continuous .step-image{width:100%;height:auto;border-radius:14px;order:3}.is-continuous .step-copy{width:100%}.is-continuous .step-title{font-size:15px;color:var(--ui-text)}.is-continuous .step-description{font-size:14px;line-height:1.8;color:var(--ui-muted)}.is-continuous .ingredient-list>view{font-size:14px;line-height:1.7;border-color:var(--ui-line)}
</style>
