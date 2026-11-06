<script setup>
import { recipeTime } from '../utils/dish-commerce-presentation.js'
import FoodImageSlot from './FoodImageSlot.vue'
import AppIcon from './AppIcon.vue'
import { computed } from 'vue'
import { dishTitle, dishKey, mealTypes as allTypes } from '../utils/meal-presentation.js'
import { recipeCover } from '../utils/recipe-cover.js'
import { localDate } from '../utils/meal-state.js'
const props=defineProps({plan:{type:Object,required:true},busy:Boolean,detailMode:Boolean,workspace:Boolean,compact:Boolean,interactive:{type:Boolean,default:true},mealTypes:Array})
const emit=defineEmits(['open','members','shop','detail','all','dish'])
const visibleTypes=computed(()=>allTypes.filter(type=>!props.mealTypes?.length||props.mealTypes.includes(type)))
const names={breakfast:'早餐',lunch:'午餐',dinner:'晚餐'}
function openDetail(item){if(props.interactive)emit('detail',item)}
function openDish(item,dishIndex){if(props.interactive)emit('dish',{item,dishIndex})}
</script>
<template>
 <view class="menu-cards" :class="{'in-chat':!workspace,'is-compact':compact}">
  <view v-if="!workspace&&visibleTypes.length>1" class="heading"><text>{{plan.date===localDate()?'今日餐单':plan.date===localDate(new Date(Date.now()+86400000))?'明日餐单':'餐单'}}</text><text class="date">{{plan.date}}</text></view>
  <template v-for="type in visibleTypes" :key="type">
   <view v-for="item in plan.meals.filter(i=>i.meal_type===type)" :key="item.source.id+type" class="meal-card">
    <view class="meal-head"><AppIcon :name="type==='dinner'?'moon':'sun'" :size="compact?24:32"/><text class="meal-name">{{names[type]}}</text><button role="button" tabindex="0" class="meal-detail" :disabled="!interactive" @click="openDetail(item)" :aria-label="'查看'+names[type]+'详情'">查看详情 <text>›</text></button></view>
    <button role="button" tabindex="0" v-for="(dish,index) in item.meal.dishes" :key="dishKey(dish)" class="meal-dish" :disabled="!interactive" @click="openDish(item,index)" :aria-label="'查看'+dishTitle(dish)">
     <view class="meal-image"><FoodImageSlot :src="recipeCover(dish)?.image_url" :label="dishTitle(dish)" :width="compact?56:72" :height="compact?56:72" :radius="compact?14:18"/></view>
     <view class="dish-copy"><text class="dish-name">{{dishTitle(dish)}}</text><text class="dish-time">{{recipeTime(dish)}}</text></view>
    </button>
   </view>
   <view v-if="workspace&&!plan.meals.some(i=>i.meal_type===type)" class="meal-card"><view class="meal-head"><text class="meal-name">{{names[type]}}</text><text class="meal-empty">尚未安排</text></view></view>
  </template>
 </view>
</template>
<style scoped>
.menu-cards{display:flex;flex-direction:column;padding:0 20px 22px;color:var(--ui-text)}
.in-chat.menu-cards{padding:0;margin:14px 0}
.heading{display:flex;justify-content:space-between;align-items:baseline;margin:0 3px 14px;font-size:18px;font-weight:500}
.date{font-size:12px;color:var(--ui-muted);font-weight:400}
.meal-card{margin-bottom:16px;padding:16px 18px;border-radius:26px;border:1px solid rgba(255,255,255,.92);background:linear-gradient(180deg,rgba(255,255,255,.32),rgba(255,255,255,.94));box-shadow:inset 0 1px 0 #fff,0 6px 22px rgba(48,55,75,.045)}
.meal-card:last-child{margin-bottom:0}
.meal-head{display:flex;align-items:center;margin-bottom:12px;min-height:44px}
.meal-name{margin-left:8px;font-size:18px;line-height:1.5;font-weight:600;white-space:nowrap}
.meal-detail{display:flex;align-items:center;justify-content:center;flex-shrink:0;margin:0 0 0 auto;padding:8px 12px;min-height:44px;border:1px solid rgba(255,255,255,.95);border-radius:14px;background:rgba(255,255,255,.58);box-shadow:inset 0 1px 0 #fff;color:var(--ui-text);font-size:16px;font-weight:600;line-height:1.5}
.meal-detail>text{margin-left:5px;font-size:18px;font-weight:500}
.meal-dish{display:flex;align-items:center;min-height:88px;width:100%;margin:0;padding:8px 0;text-align:left;background:transparent}
.meal-dish+.meal-dish{margin-top:8px}
.meal-image{width:72px;height:72px;flex:0 0 72px;overflow:hidden;border-radius:18px}
.dish-name{flex:1;min-width:0;display:block;margin-left:18px;font-size:16px;font-weight:500;line-height:1.6;color:var(--ui-text);overflow-wrap:anywhere;word-break:break-word}
.meal-empty{margin-left:auto;font-size:13px;color:var(--ui-muted)}
.menu-cards button:after{border:0}
.menu-cards button[disabled]{opacity:.45}
.meal-detail:active,.meal-dish:active{background:rgba(255,255,255,.62)}
.is-compact .meal-card{margin-bottom:12px;padding:10px 14px 14px;border-radius:20px;border-color:#eeedf3;background:#fff;box-shadow:0 3px 12px rgba(48,55,75,.025)}
.is-compact .meal-card:last-child{margin-bottom:0}.is-compact .meal-head{margin-bottom:4px}.is-compact .meal-name{font-size:16px}
.is-compact .meal-detail{padding:8px 4px 8px 10px;border:0;background:transparent;box-shadow:none;font-size:13px;font-weight:400;color:#74717f}
.is-compact .meal-dish{min-height:64px;padding:4px 0}.is-compact .meal-dish+.meal-dish{margin-top:4px}.is-compact .meal-image{width:56px;height:56px;flex-basis:56px;border-radius:14px}
.is-compact .dish-name{margin-left:12px;font-size:15px;line-height:1.6}.is-compact .meal-dish[disabled]{opacity:1;background:transparent}.is-compact .meal-detail[disabled]{opacity:.45;background:transparent}
@media(max-width:350px){.menu-cards{padding-left:16px;padding-right:16px}.in-chat.menu-cards{padding:0}.meal-card{padding-left:15px;padding-right:15px}.meal-detail{padding:8px 10px}}
.dish-copy{flex:1;min-width:0;margin-left:18px}.dish-copy .dish-name{margin-left:0}.dish-time{display:block;margin-top:4px;font-size:12px;line-height:1.6;color:var(--ui-muted)}.is-compact .dish-copy{margin-left:12px}.is-compact .dish-copy .dish-name{margin-left:0}
</style>
