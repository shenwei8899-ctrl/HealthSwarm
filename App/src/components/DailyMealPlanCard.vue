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
 <view v-if="workspace" class="menu-cards">
  <view v-for="type in ['breakfast','lunch','dinner']" :key="type" class="meal-card">
   <template v-for="item in plan.meals.filter(i=>i.meal_type===type)" :key="item.source.id">
    <view class="meal-head"><text class="meal-icon" aria-hidden="true">{{({breakfast:'☀',lunch:'☼',dinner:'☾'})[type]}}</text><text class="meal-name">{{names[type]}}</text><text class="meal-count">{{item.meal.dishes.length}}道菜</text><button class="meal-detail" @click="emit('detail',item)" :aria-label="'查看'+names[type]+'详情'">查看详情 ›</button></view>
    <view class="meal-summary"><FoodImageSlot v-if="item.meal.image_url||item.meal.dishes[0]?.image_url" class="meal-image" :src="item.meal.image_url||item.meal.dishes[0]?.image_url" :label="names[type]"/><view v-else class="meal-art" :class="type" aria-hidden="true">{{({breakfast:'🥣',lunch:'🍱',dinner:'🥗'})[type]}}</view><view class="meal-copy"><text class="dish-names">{{item.meal.dishes.map(d=>d.name).join(' · ')}}</text><text class="meal-members">{{(item.members||[]).map(m=>m.name).join('、')}}</text></view></view>
    <view class="meal-bottom"><text class="meal-source">{{item.source.kind==='reference'?'参考餐单 · 未专业审核':'已保存餐单'}}</text><button class="meal-buy" :disabled="busy||!plan.purchase_options?.some(o=>o.kind===item.source.kind&&o.id===item.source.id&&o.meal_types.includes(type))" @click="emit('purchase',item)">购买本餐 ↗</button></view>
   </template>
   <view v-if="!plan.meals.some(i=>i.meal_type===type)" class="meal-head"><text class="meal-name">{{names[type]}}</text><text class="meal-empty">尚未安排</text></view>
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
   <template v-if="option.kind==='reference'">
    <text class="meal-title">采购建议 · {{(option.meal_types||[]).map(type=>names[type]).join('、')}}</text>
    <text v-if="detailMode" class="note">{{option.items?.length||0}} 项商品 · {{option.gaps?.length||0}} 项食材待核对</text>
    <template v-else><text class="note">{{option.quantity_notice}}</text><text v-for="product in option.items||[]" :key="product.sku_id">{{product.product_name}} {{product.sku_name||''}} × {{product.quantity}}</text><text v-for="gap in option.gaps||[]" :key="gap.ingredient">{{gap.ingredient}}：{{gap.detail}}</text></template>
   </template>
   <button class="buy" :disabled="busy" @click="emit('shop',option)">{{detailMode?'查看采购食材':option.kind==='formal'?'一键选购':'确认这些商品并加入购物车'}}</button>
  </view>
 </view>
</template>
<style scoped>
.daily-plan{padding:18px;margin:18px 0;background:var(--ui-surface);border-radius:var(--ui-radius);color:var(--ui-text)}.heading{display:flex;justify-content:space-between;font-size:18px;font-weight:500}.date,.note{font-size:12px;color:var(--ui-muted);font-weight:400}.meal{display:flex;flex-direction:column;gap:6px;padding:15px 0;border-bottom:1px solid var(--ui-line)}.meal-title{font-size:14px;color:#666}.dish{font-size:16px;line-height:1.7}.text-button{align-self:flex-start;margin:0;padding:4px 0;min-height:44px;color:#444;font-size:13px;background:transparent}.text-button:after,.buy:after{border:0}.details{display:flex;flex-direction:column;gap:6px;color:var(--ui-muted);font-size:12px;line-height:1.7}.buy{margin:14px 0 0 auto;min-height:44px;padding:10px 16px;font-size:14px;color:#fff;background:var(--ui-accent);border-radius:14px}
</style>

<style scoped>
.menu-cards{display:flex;flex-direction:column;gap:15px;padding:0 20px 22px}.meal-card{padding:16px 17px 10px;border-radius:22px;background:#fff;border:1px solid #fff;box-shadow:0 4px 16px rgba(65,97,147,.05);color:#2b3e55}.meal-head{display:flex;align-items:center;gap:7px;margin-bottom:15px}.meal-icon{color:#839dca;font-size:19px;line-height:1}.meal-name{font-size:17px;font-weight:600;white-space:nowrap}.meal-count{color:#8b9bb0;font-size:11px;white-space:nowrap}.meal-detail{display:flex;align-items:center;justify-content:center;flex-shrink:0;margin:0 0 0 auto;min-height:36px;padding:6px 10px;border:1px solid #c9d5ed;border-radius:9px;background:#f7faff;color:#5f78a2;font-size:12px;line-height:1.5}.meal-detail:after,.meal-buy:after{border:0}.meal-summary{display:flex;align-items:center;gap:13px}.meal-image,.meal-art{width:58px;height:64px;border-radius:15px;flex-shrink:0}.meal-art{display:flex;align-items:center;justify-content:center;font-size:30px;background:#f1f3fb}.meal-art.lunch{background:#f8f1e9}.meal-art.dinner{background:#edf4ed}.meal-copy{flex:1;min-width:0}.dish-names{display:block;font-size:14px;line-height:1.9;overflow-wrap:anywhere}.meal-members{display:block;font-size:11px;line-height:1.6;margin-top:6px;color:#8999af}.meal-bottom{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:8px}.meal-source{font-size:11px;color:#8999af;line-height:1.7}.meal-buy{display:flex;align-items:center;flex-shrink:0;margin:0;min-height:38px;padding:6px 0 6px 10px;border:0;background:transparent;color:#5f78a2;font-size:12px}.meal-empty{margin-left:auto;font-size:12px;color:#8999af}.menu-cards button[disabled]{opacity:.45}.meal-detail:active{background:#eaf0fc}
@media(pointer:coarse){.meal-detail,.meal-buy{min-height:44px}}@media(max-width:350px){.menu-cards{padding-left:16px;padding-right:16px}.meal-card{padding-left:14px;padding-right:14px}.meal-head{gap:5px}.meal-detail{padding:6px 8px;font-size:11px}.dish-names{font-size:13px}.meal-image,.meal-art{width:52px;height:60px}}
</style>
