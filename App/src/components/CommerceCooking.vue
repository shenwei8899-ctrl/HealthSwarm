<script setup>
import { ref, computed, onMounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import FlowRibbon from './FlowRibbon.vue'
import { commerce } from '../services/commerce.js'
import { useCommercePage } from '../services/commerce-page.js'
const props=defineProps({ id:{type:String,required:true} })
const context=ref(null),selected=ref('')
const {busy,error,run}=useCommercePage(()=>{context.value=null;selected.value=''})
const menu=computed(()=>context.value?.meal_snapshot)
const dishes=computed(()=>menu.value?.dishes||[])
const dish=computed(()=>dishes.value.find(d=>d.recipe_ref===selected.value)||dishes.value[0])
function load(){return run(async active=>{const result=await commerce.cooking(props.id);if(active()){context.value=result;selected.value=dishes.value[0]?.recipe_ref||''}})}
onMounted(load);onShow(load)
function record(){uni.navigateTo({url:'/pages/scan/index?commerce=1&id='+encodeURIComponent(props.id)})}
function viewOrder(){uni.redirectTo({url:'/pages/orders/detail?id='+encodeURIComponent(props.id)})}
</script>
<template>
  <view class="screen">
    <AppNavBar><view class="nav-row"><button class="icon-button" @click="viewOrder">‹</button><text class="nav-title">本餐制作</text><text/></view></AppNavBar>
    <FlowRibbon :current="5"/>
    <text v-if="error" class="inline-error">{{error}}</text>
    <button class="secondary-button" :disabled="busy" @click="load">{{busy?'正在读取…':'刷新订单菜谱'}}</button>
    <template v-if="context">
      <view class="page-heading"><text class="display-title">收到食材，开始做饭</text><text class="subtitle">订单 {{context.order_sn}} · 使用购买时保存的菜谱</text></view>
      <text v-if="menu.is_local_fixture" class="safe-note">本地联调菜谱 · 未经个体化营养评估</text>
      <view class="card cooking-card"><button v-for="item in dishes" :key="item.recipe_ref" class="secondary-button" @click="selected=item.recipe_ref">{{item.recipe_name}}</button></view>
      <view v-if="dish" class="card cooking-card"><text class="section-title">{{dish.recipe_name}}所需食材</text><text v-for="(ingredient,n) in dish.ingredients" :key="n">{{typeof ingredient==='string'?ingredient:ingredient.name}}</text></view>
      <view v-for="(step,n) in dish?.steps||[]" :key="n" class="card cooking-card"><text class="section-title">{{n+1}} · {{typeof step==='string'?step:step.text||step.description}}</text></view>
      <text class="safe-note">请按实际采购及家中已有食材核对。份量、油盐和营养数值没有自动推算。</text>
      <button class="primary-button" @click="record">吃完后记录这一餐</button>
    </template>
  </view>
</template>
<style scoped>.cooking-card{padding:28rpx;margin:22rpx 0;display:flex;flex-direction:column;gap:18rpx}</style>
