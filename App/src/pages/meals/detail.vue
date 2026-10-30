<script setup>
import {ref,getCurrentInstance,nextTick} from 'vue'
import {onLoad,onShow,onUnload} from '@dcloudio/uni-app'
import MealDetailSheet from '../../components/MealDetailSheet.vue'
import {openerChannel} from '../../services/address-navigation.js'
import {storageContext} from '../../services/storage.js'
import {request} from '../../services/request.js'
import {getSession} from '../../services/session.js'
const detail=ref(null),received=ref(false),members=ref([]),error=ref(''),instance=getCurrentInstance(),owner=storageContext()
let alive=true
function leave(){uni.navigateBack({fail:()=>uni.reLaunch({url:'/pages/chat/index'})})}
async function reload(date){const {data}=await request({path:'/api/family/'+encodeURIComponent(getSession().householdId)+'/daily-meal-plans/'+date});return data}
onLoad(()=>{openerChannel(instance)?.on('mealWorkspace',async value=>{if(!alive||owner!==storageContext()||value.owner!==owner)return;received.value=true;await nextTick();void detail.value?.open(value.target);try{const {data}=await request({path:'/api/family/'+encodeURIComponent(getSession().householdId)+'/miniapp-profile'});if(alive&&owner===storageContext())members.value=data.members||[]}catch(e){if(alive){members.value=[];error.value=e.message}}})})
onShow(()=>{if(owner!==storageContext())leave()})
onUnload(()=>{alive=false})
</script>
<template><view><MealDetailSheet v-if="received" ref="detail" standalone :members="members" :reload="reload" @leave="leave"/><view v-else class="detail-route-empty"><text>请从今日餐单打开本餐详情</text><button @click="leave">返回餐单</button></view></view></template>
<style scoped>.detail-route-empty{padding:100px 24px;color:#82778e;font-size:15px}.detail-route-empty button{margin-top:20px;color:#78648e}</style>
