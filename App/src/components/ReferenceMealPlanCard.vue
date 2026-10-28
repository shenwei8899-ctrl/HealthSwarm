<script setup>
import {ref,onUnmounted} from 'vue'
import {request} from '../services/request.js'
import {commerce} from '../services/commerce.js'
import {storageContext} from '../services/storage.js'
const props=defineProps({plan:{type:Object,required:true}})
const expanded=ref(false),busy=ref(false),error=ref('')
const names={breakfast:'早餐',lunch:'午餐',dinner:'晚餐'}
const gapNames={no_match:'暂无匹配商品',needs_confirmation:'商品资料待确认',not_sold:'自行准备',catalog_unavailable:'商品目录暂不可用'}
let alive=true
const scope=storageContext(),current=()=>alive&&scope===storageContext()
onUnmounted(()=>{alive=false})
async function purchase(){
  if(busy.value||!current())return
  busy.value=true;error.value=''
  const previewId=props.plan.preview_id,active=()=>current()&&props.plan.preview_id===previewId
  try{
    await commerce.connect();if(!active())return
    const {data}=await request({path:'/api/health/v1/reference-meal-plans/'+encodeURIComponent(previewId)+'/purchase',method:'POST'})
    if(!active())return
    if(data.preview_id!==previewId||!data.package?.package_sn)throw new Error('参考采购来源未确认，请重试原操作。')
    const menu=await commerce.mealPackage(data.package.package_sn,data.package.package_version)
    if(!active())return
    if(!menu.available||menu.scope!=='daily_reference')throw new Error('参考商品或来源已变化，请重新生成后核对。')
    await commerce.addMeal(menu);if(!active())return
    uni.navigateTo({url:'/pages/shop/index?commerce=1&cart=1'})
  }catch(e){if(current())error.value=e.message||'采购尚未完成，可以重试。'}
  finally{if(current())busy.value=false}
}
</script>
<template>
 <view class="reference-plan">
  <view class="reference-heading"><text>{{plan.plan_date}} · 日常参考餐单</text><text class="reference-tag">参考</text></view>
  <text class="reference-note">{{plan.notice}}</text>
  <text class="reference-members">就餐成员：{{(plan.members||[]).map(m=>m.name).join('、')}}</text>
  <view v-for="meal in plan.meals" :key="meal.meal_type" class="reference-meal">
   <text class="meal-title">{{names[meal.meal_type]}}</text>
   <view v-for="(dish,index) in meal.dishes" :key="dish.file_id+index" class="reference-dish">
    <text class="dish-name">{{dish.name}}</text><text>{{dish.portion_note}}</text><text v-if="dish.portion_quote">原食谱份量：{{dish.portion_quote}}</text>
    <text class="source-name">来源：{{dish.source.filename}}</text>
    <template v-if="expanded"><text>食材原文：{{dish.ingredients.join('；')}}</text><text v-for="(step,i) in dish.steps" :key="i">{{i+1}}. {{step}}</text><text v-if="dish.nutrition_quote">原食谱营养说明：{{dish.nutrition_quote}}</text><text class="reference-note">个人营养量尚未核算，未知值不按零处理。</text></template>
   </view>
  </view>
  <button class="reference-detail" @click="expanded=!expanded">{{expanded?'收起原文详情':'查看食材、做法与营养说明'}}</button>
  <view v-if="plan.purchase_items?.length" class="reference-products"><text class="meal-title">采购建议 · 请核对商品与包装数量</text><view v-for="item in plan.purchase_items" :key="item.sku_id"><text>{{item.product_name}} {{item.sku_name||''}} × {{item.quantity}}</text><text v-if="item.ingredient_refs?.length">用于：{{item.ingredient_refs.join('、')}}</text><text v-if="item.composition_notice" class="reference-note">{{item.composition_notice}}</text></view><button :disabled="busy" @click="purchase">{{busy?'正在核对来源…':'确认这些商品并加入购物车'}}</button></view>
  <text v-else class="reference-note">{{plan.purchase_gaps?.length?'本次未选定采购商品，原因见下方。':'这份餐单未记录采购商品及原因，可重新生成参考餐单。'}}</text>
  <view v-if="plan.purchase_gaps?.length" class="reference-products"><text class="meal-title">{{plan.purchase_items?.length?'其余食材':'食材采购说明'}}</text><view v-for="gap in plan.purchase_gaps" :key="gap.ingredient"><text>{{gap.ingredient}} · {{gapNames[gap.reason]||'待核对'}}</text><text class="reference-note">{{gap.detail}}</text></view></view>
  <text v-if="error" class="reference-error" role="alert">{{error}}</text>
 </view>
</template>
<style scoped>
.reference-plan{display:flex;flex-direction:column;gap:14px;margin:18px 0;padding:18px;border:1px solid #e5e6df;border-radius:14px;background:#fbfbf7;color:#302e28;font-size:14px;line-height:1.8}.reference-heading{display:flex;align-items:center;justify-content:space-between;font-size:17px;font-weight:600}.reference-tag{font-size:11px;padding:2px 9px;background:#e9eadc;border-radius:12px;color:#62684c}.reference-note,.source-name,.reference-members{font-size:12px;color:#77766b;overflow-wrap:anywhere}.reference-meal,.reference-dish,.reference-products,.reference-products>view{display:flex;flex-direction:column;gap:7px}.reference-meal{padding-top:10px;border-top:1px solid #e9e9df}.meal-title,.dish-name{font-weight:600}.reference-plan button{align-self:flex-start;min-height:44px;padding:8px 14px;font-size:14px;line-height:1.8;border-radius:8px;background:#556349;color:#fff}.reference-plan .reference-detail{background:transparent;color:#556349;padding-left:0}.reference-plan button:after{border:0}.reference-error{color:#9a453c}.reference-plan button[disabled]{opacity:.5}
</style>
