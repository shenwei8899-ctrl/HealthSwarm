<script setup>
import { ref } from 'vue'
import { localDate } from '../utils/meal-state.js'
const props=defineProps({plan:{type:Object,required:true},busy:Boolean})
const emit=defineEmits(['open','members','shop'])
const expanded=ref({})
const names={breakfast:'早餐',lunch:'午餐',dinner:'晚餐'}
function toggle(type){expanded.value={...expanded.value,[type]:!expanded.value[type]}}
</script>
<template>
 <view class="daily-plan">
  <view class="heading"><text>{{plan.date===localDate()?'今日饮食计划':plan.date===localDate(new Date(Date.now()+86400000))?'明日饮食计划':'饮食计划'}}</text><text class="date">{{plan.date}}</text></view>
  <view v-for="type in ['breakfast','lunch','dinner']" :key="type" class="meal">
   <text class="meal-title">{{names[type]}}</text>
   <template v-if="plan.meals.find(item=>item.meal_type===type)">
    <template v-for="item in plan.meals.filter(item=>item.meal_type===type)" :key="item.source.id">
     <text class="dish">{{item.meal.dishes.map(d=>d.name).join(' · ')}}</text>
     <text class="note">{{(item.members||[]).map(m=>m.name).join('、')}}{{item.source.kind==='reference'?' · 参考餐单，个人营养量未核算，未专业审核':''}}</text>
     <template v-if="item.source.kind==='reference'">
      <button class="text-button" @click="toggle(type)">{{expanded[type]?'收起食谱':'查看食材与做法'}} ›</button>
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
   <button class="buy" :disabled="busy" @click="emit('shop',option)">{{option.kind==='formal'?'一键选购':'确认这些商品并加入购物车'}}</button>
  </view>
 </view>
</template>
<style scoped>
.daily-plan{padding:18px;margin:18px 0;background:#f7f7f7;border-radius:14px;color:#222}.heading{display:flex;justify-content:space-between;font-size:18px;font-weight:600}.date,.note{font-size:12px;color:#777;font-weight:400}.meal{display:flex;flex-direction:column;gap:6px;padding:15px 0;border-bottom:1px solid #e6e6e6}.meal-title{font-size:14px;color:#666}.dish{font-size:16px;line-height:1.7}.text-button{align-self:flex-start;margin:0;padding:4px 0;min-height:36px;color:#444;font-size:13px;background:transparent}.text-button:after,.buy:after{border:0}.details{display:flex;flex-direction:column;gap:6px;color:#777;font-size:12px;line-height:1.7}.buy{margin:14px 0 0 auto;padding:8px 14px;font-size:14px;color:#fff;background:#111;border-radius:8px}
</style>
