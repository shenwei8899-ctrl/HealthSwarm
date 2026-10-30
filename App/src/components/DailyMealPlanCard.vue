<script setup>
import FoodImageSlot from './FoodImageSlot.vue'
import { ref } from 'vue'
import { localDate } from '../utils/meal-state.js'
const props=defineProps({plan:{type:Object,required:true},busy:Boolean,detailMode:Boolean,workspace:Boolean})
const emit=defineEmits(['open','members','shop','detail','purchase'])
const expanded=ref({})
const names={breakfast:'早餐',lunch:'午餐',dinner:'晚餐'}
function toggle(type){expanded.value={...expanded.value,[type]:!expanded.value[type]}}
</script>
<template>
 <view v-if="workspace" class="today-menu-cards">
  <view v-for="(type,index) in ['breakfast','lunch','dinner']" :key="type" class="today-meal-card">
   <view class="today-meal-heading"><view class="meal-orb" :class="type"><text>{{index+1}}</text></view><text class="today-meal-title">{{names[type]}}</text><text class="today-meal-state">{{plan.meals.some(i=>i.meal_type===type)?'已安排':'待安排'}}</text></view>
   <template v-for="item in plan.meals.filter(i=>i.meal_type===type)" :key="item.source.id">
    <view class="today-dishes"><view v-for="(dish,i) in item.meal.dishes" :key="i" class="today-dish"><FoodImageSlot v-if="dish.image_url" :src="dish.image_url" :label="dish.name" class="today-dish-image"/><text v-else class="dish-mark" aria-hidden="true">·</text><text>{{dish.name}}</text></view></view>
    <view class="today-members"><text v-for="m in item.members||[]" :key="m.id">{{m.name}}</text><text v-if="!item.members?.length">就餐成员以餐单为准</text></view>
    <view class="today-card-bottom"><text class="today-source">{{item.source.kind==='reference'?'参考餐单 · 未专业审核':'已保存餐单'}}</text><button :disabled="busy" class="today-detail" @click="emit('detail',item)">查看详情 ›</button></view>
    <button class="today-buy" :disabled="busy||!plan.purchase_options?.some(o=>o.kind===item.source.kind&&o.id===item.source.id&&o.meal_types.includes(type))" @click="emit('purchase',item)">购买本餐 <text>↗</text></button>
   </template>
   <text v-if="!plan.meals.some(i=>i.meal_type===type)" class="today-empty">本餐还没有安排</text>
  </view>
 </view>
 <view v-else class="daily-plan">
  <view class="heading"><text>{{plan.date===localDate()?'今日饮食计划':plan.date===localDate(new Date(Date.now()+86400000))?'明日饮食计划':'饮食计划'}}</text><text class="date">{{plan.date}}</text></view>
  <view v-for="type in ['breakfast','lunch','dinner']" :key="type" class="meal">
   <text class="meal-title">{{names[type]}}</text>
   <template v-if="plan.meals.find(item=>item.meal_type===type)">
    <template v-for="item in plan.meals.filter(item=>item.meal_type===type)" :key="item.source.id">
     <text class="dish">{{item.meal.dishes.map(d=>d.name).join(' · ')}}</text>
     <text class="note">{{(item.members||[]).map(m=>m.name).join('、')}}{{item.source.kind==='reference'?' · 参考餐单，个人营养量未核算，未专业审核':''}}</text>
     <template v-if="item.source.kind==='reference'">
      <button class="text-button" @click="detailMode?emit('detail',item):toggle(type)">{{expanded[type]?'收起食谱':'查看食材与做法'}} ›</button>
      <view v-if="expanded[type]" v-for="(dish,i) in item.meal.dishes" :key="i" class="details">
       <text>{{dish.name}} · 来源：{{dish.source?.filename}}</text>
       <text>食材：{{(dish.ingredients||[]).join('；')}}</text>
       <text v-for="(step,j) in dish.steps||[]" :key="j">{{j+1}}. {{step}}</text>
       <text>{{dish.portion_note}}</text>
      </view>
     </template>
     <template v-else>
      <button class="text-button" :disabled="busy" @click="emit('open',item)">查看本餐安排 ›</button>
      <button class="text-button" :disabled="busy" @click="emit('members',item)">调整就餐成员 ›</button>
     </template>
    </template>
   </template>
   <text v-else class="note">尚未安排</text>
  </view>
  <view v-for="option in plan.purchase_options||[]" :key="option.kind+option.id" class="details">
   <template v-if="option.kind==='reference'"><text class="meal-title">采购建议 · {{option.meal_types.map(type=>names[type]).join('、')}}</text><text class="note">{{option.quantity_notice}}</text><text v-for="product in option.items" :key="product.sku_id">{{product.product_name}} {{product.sku_name||''}} × {{product.quantity}}</text><text v-for="gap in option.gaps" :key="gap.ingredient">{{gap.ingredient}}：{{gap.detail}}</text></template>
   <button class="buy" :disabled="busy" @click="emit('shop',option)">{{detailMode?'查看采购食材':option.kind==='formal'?'一键选购':'确认这些商品并加入购物车'}}</button>
  </view>
 </view>
</template>
<style scoped>
.daily-plan{padding:18px;margin:18px 0;background:var(--ui-surface);border-radius:var(--ui-radius);color:var(--ui-text)}.heading{display:flex;justify-content:space-between;font-size:18px;font-weight:500}.date,.note{font-size:12px;color:var(--ui-muted);font-weight:400}.meal{display:flex;flex-direction:column;gap:6px;padding:15px 0;border-bottom:1px solid var(--ui-line)}.meal-title{font-size:14px;color:#666}.dish{font-size:16px;line-height:1.7}.text-button{align-self:flex-start;margin:0;padding:4px 0;min-height:44px;color:#444;font-size:13px;background:transparent}.text-button:after,.buy:after{border:0}.details{display:flex;flex-direction:column;gap:6px;color:var(--ui-muted);font-size:12px;line-height:1.7}.buy{margin:14px 0 0 auto;min-height:44px;padding:10px 16px;font-size:14px;color:#fff;background:var(--ui-accent);border-radius:14px}
</style>

<style scoped>
.today-menu-cards{display:flex;flex-direction:column;gap:16px;padding:0 18px 20px}.today-meal-card{position:relative;padding:20px;border-radius:26px;background:var(--ui-bubble);border:1px solid rgba(255,255,255,.95);box-shadow:inset 0 1px 1px #fff,0 6px 22px rgba(61,55,85,.045);color:var(--ui-text)}.today-meal-heading{display:flex;align-items:center;gap:10px;margin-bottom:16px}.meal-orb{height:32px;width:32px;display:flex;align-items:center;justify-content:center;border-radius:50%;background:linear-gradient(145deg,#fff8ed,#f6ead8);box-shadow:inset 0 1px 2px #fff;color:#9d8057;font-size:13px;font-weight:600}.meal-orb.lunch{background:linear-gradient(145deg,#f8fcf4,#e9f0df);color:#74845d}.meal-orb.dinner{background:linear-gradient(145deg,#faf8ff,#e9e3f5);color:var(--ui-accent)}.today-meal-title{font-size:20px;font-weight:600;letter-spacing:.5px}.today-meal-state{margin-left:auto;font-size:12px;color:var(--ui-muted)}.today-dishes{display:flex;flex-direction:column;gap:12px}.today-dish{display:flex;align-items:center;gap:10px;font-size:16px;font-weight:500;line-height:1.55}.today-dish-image{width:48px;height:48px;border-radius:15px}.dish-mark{font-size:22px;color:#b6adc4;padding:0 5px}.today-members{display:flex;flex-wrap:wrap;gap:6px;margin:16px 0 12px}.today-members text{padding:5px 10px;border-radius:99px;background:linear-gradient(160deg,#fff,#f4f1f8);box-shadow:inset 0 1px 0 #fff;border:1px solid #f1edf5;font-size:12px;color:var(--ui-muted)}.today-card-bottom{display:flex;align-items:center;justify-content:space-between;gap:6px}.today-source{font-size:12px;line-height:1.5;color:var(--ui-muted)}.today-detail{background:transparent;color:var(--ui-accent);min-height:44px;padding:0;margin:0;font-size:13px;display:flex;align-items:center}.today-buy{margin:8px 0 0;width:100%;min-height:44px;display:flex;align-items:center;justify-content:center;gap:6px;border-radius:99px;background:#eef0f2;color:var(--ui-text);border:0;box-shadow:none;font-size:14px;font-weight:500}.today-menu-cards button:after{border:0}.today-empty{display:block;padding:18px 0;color:var(--ui-muted);font-size:14px}.today-menu-cards button[disabled]{opacity:.45}
</style>

<style scoped>.today-buy:active{background:#e4e7eb}</style>
