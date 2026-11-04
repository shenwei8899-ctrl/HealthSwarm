<script setup>
import {ref,watch,getCurrentInstance} from 'vue'
import {onLoad,onShow,onUnload,onBackPress} from '@dcloudio/uni-app'
import MealDetailSheet from '../../components/MealDetailSheet.vue'
import {openerChannel} from '../../services/address-navigation.js'
import {storageContext} from '../../services/storage.js'
import {request} from '../../services/request.js'
import {getSession} from '../../services/session.js'
const detail=ref(null),received=ref(false),members=ref([]),error=ref(''),instance=getCurrentInstance(),owner=storageContext()
const pendingTarget=ref(null),opened=ref(false)
const leaving=ref(false),returnError=ref('')
let alive=true,openedTarget=null,openingTimer=null
const current=()=>alive&&owner===storageContext()
function clearOpeningTimer(){clearTimeout(openingTimer);openingTimer=null}
function leave(){
 if(!alive||leaving.value)return
 leaving.value=true;returnError.value=''
 function failed(){if(alive){leaving.value=false;returnError.value='暂时无法返回，请再点一次左上角返回。';uni.showToast({title:'暂时无法返回，请重试',icon:'none'})}}
 function fallback(){if(alive){try{uni.reLaunch({url:'/pages/chat/index',fail:failed})}catch{failed()}}}
 const pages=typeof getCurrentPages==='function'?getCurrentPages():[]
 if(pages.length<=1){fallback();return}
 try{uni.navigateBack({delta:1,fail:fallback})}catch{fallback()}
}
async function reload(date){const {data}=await request({path:'/api/family/'+encodeURIComponent(getSession().householdId)+'/daily-meal-plans/'+date});return data}
function waitForDetail(){
 clearOpeningTimer()
 openingTimer=setTimeout(()=>{if(current()&&!opened.value)error.value='详情暂时未能打开，请重试或返回餐单。'},8000)
}
async function openPending(){
 const component=detail.value,target=pendingTarget.value
 if(!current()||!target||typeof component?.open!=='function'||openedTarget===target)return
 openedTarget=target;clearOpeningTimer();error.value=''
 try{
  // The native component ref, rather than Vue's nextTick, proves it is mounted.
  const reading=component.open(target)
  opened.value=true
  await reading
 }catch(e){
  if(current()&&pendingTarget.value===target){opened.value=false;openedTarget=null;error.value=e.message||'详情暂时未能打开，请重试。'}
 }
}
function retry(){if(!current())return;openedTarget=null;error.value='';waitForDetail();void openPending()}
// Native refs may arrive after the EventChannel payload, or before it.
watch([detail,pendingTarget],()=>{void openPending()},{flush:'post'})
onLoad(()=>{openerChannel(instance)?.on('mealWorkspace',value=>{
 if(!current()||value?.owner!==owner)return
 received.value=true
 if(!value.target){error.value='餐单来源不完整，请返回餐单重新打开。';return}
 pendingTarget.value=value.target;waitForDetail()
 void request({path:'/api/family/'+encodeURIComponent(getSession().householdId)+'/miniapp-profile'}).then(({data})=>{
  if(current())members.value=data.members||[]
 }).catch(()=>{/* Member refresh must not prevent opening the saved meal. */})
})})
onShow(()=>{if(owner!==storageContext()){clearOpeningTimer();detail.value?.clear();leave()}})
// Our own navigateBack must not be intercepted again by component state.
onBackPress(event=>event?.from==='navigateBack'?false:detail.value?.handleBack?.()===true)
onUnload(()=>{alive=false;clearOpeningTimer();pendingTarget.value=null})
</script>
<template><view><MealDetailSheet ref="detail" standalone :members="members" :reload="reload" :leaving="leaving" :return-error="returnError" @leave="leave"/><view v-if="!opened" class="detail-route-empty" :role="error||returnError?'alert':'status'"><text>{{returnError||error||(received?'正在打开本餐详情…':'请从今日餐单打开本餐详情')}}</text><button v-if="error&&pendingTarget" @click="retry">重新打开详情</button><button :disabled="leaving" @click="leave">返回餐单</button></view></view></template>
<style scoped>.detail-route-empty{padding:100px 24px;color:#82778e;font-size:15px;line-height:1.8}.detail-route-empty button{margin-top:20px;min-height:44px;color:#78648e}</style>
