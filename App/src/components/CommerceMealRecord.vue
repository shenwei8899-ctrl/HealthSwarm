<script setup>
import { ref, computed, onMounted } from 'vue'
import AppNavBar from './AppNavBar.vue'
import FlowRibbon from './FlowRibbon.vue'
import { commerce } from '../services/commerce.js'
import { useCommercePage } from '../services/commerce-page.js'
import { makeCommerceMealRecord } from '../services/commerce-meal-record.js'
import { getProfile, saveRecord } from '../utils/profile.js'
import { createPortionDraft, portionOptions } from '../utils/scan-portions.js'
const props=defineProps({id:{type:String,required:true}})
const context=ref(null),photo=ref(''),draft=ref({oil:'不确定',people:[]}),selectedMembers=ref([]),saved=ref(false)
const profile=ref(getProfile())
const {busy,error,run}=useCommercePage(()=>{context.value=null;draft.value={oil:'不确定',people:[]};selectedMembers.value=[];photo.value='';saved.value=false})
const names=computed(()=>[...new Set((context.value?.meal_snapshot.dishes||[]).map(d=>d.recipe_name))])
function resetPeople(){
  const old=new Map(draft.value.people.map(p=>[p.memberId,p]))
  const people=profile.value.members.filter(m=>selectedMembers.value.includes(m.id)).map(m=>old.get(m.id)||{memberId:m.id,memberName:m.name,dishes:[],portion:'不确定',grams:null,noneConfirmed:false})
  draft.value=createPortionDraft(people,names.value,draft.value.oil)
}
function load(){return run(async active=>{const result=await commerce.cooking(props.id);if(active()){context.value=result;profile.value=getProfile();selectedMembers.value=profile.value.defaultDiners||[];resetPeople()}})}
onMounted(load)
function toggleMember(id){selectedMembers.value=selectedMembers.value.includes(id)?selectedMembers.value.filter(v=>v!==id):[...selectedMembers.value,id];resetPeople()}
function toggleDish(person,name){person.dishes=person.dishes.includes(name)?person.dishes.filter(v=>v!==name):[...person.dishes,name];person.noneConfirmed=false}
function choosePhoto(){return run(async active=>{
  const result=await new Promise((resolve,reject)=>uni.chooseImage({count:1,success:resolve,fail:reject}))
  if(!active())return
  const path=result.tempFilePaths[0]
  try {const kept=await new Promise((resolve,reject)=>uni.saveFile({tempFilePath:path,success:resolve,fail:reject}));if(active())photo.value=kept.savedFilePath}
  catch {if(active())photo.value=path}
})}
function save(){return run(async active=>{
  if(saved.value)return
  // Verify ownership and receipt again before persisting this account's local record.
  const verified=await commerce.cooking(props.id)
  if(!active())return
  const record=makeCommerceMealRecord(verified,draft.value,{id:'commerce-meal-'+Date.now(),photoPath:photo.value||null})
  saveRecord(record);saved.value=true
  uni.redirectTo({url:'/pages/records/detail?id='+encodeURIComponent(record.id)})
})}
</script>
<template>
  <view class="screen">
    <AppNavBar><view class="nav-row"><button class="icon-button" @click="uni.navigateBack()">‹</button><text class="nav-title">记录这一餐</text><text/></view></AppNavBar>
    <FlowRibbon :current="6"/>
    <view class="page-heading"><text class="display-title">实际吃了哪些菜？</text><text class="subtitle">按订单菜谱逐人确认食量，可附上餐盘照片。</text></view>
    <text class="safe-note">记录按当前会员保存在本机。照片用于回看；AI 识别和营养计算尚未接入。</text>
    <text v-if="error" class="inline-error">{{error}}</text>
    <button v-if="!context" class="secondary-button" :disabled="busy" @click="load">重新读取订单</button>
    <template v-if="context">
      <text v-if="context.meal_snapshot.is_local_fixture" class="safe-note">本地联调菜谱 · 记录保留测试来源标记</text>
      <view class="card record-card"><text class="section-title">本餐成员</text><button v-for="m in profile.members" :key="m.id" class="secondary-button" @click="toggleMember(m.id)">{{selectedMembers.includes(m.id)?'☑':'□'}} {{m.name}}</button></view>
      <view v-for="person in draft.people" :key="person.memberId" class="card record-card">
        <text class="section-title">{{person.memberName}}实际吃过</text>
        <button v-for="name in names" :key="name" class="secondary-button" @click="toggleDish(person,name)">{{person.dishes.includes(name)?'☑':'□'}} {{name}}</button>
        <button class="secondary-button" @click="person.dishes=[];person.noneConfirmed=true;person.grams='';person.portion='不确定'">本餐未吃</button>
        <picker :range="portionOptions" @change="person.portion=portionOptions[$event.detail.value]"><view class="field-input">粗略份量：{{person.portion}} ›</view></picker>
        <input v-model="person.grams" class="field-input" type="digit" placeholder="实际克数（可不填）"/>
      </view>
      <image v-if="photo" :src="photo" mode="widthFix" class="meal-photo"/>
      <button class="secondary-button" :disabled="busy" @click="choosePhoto">拍照或选择照片</button>
      <button class="primary-button" :disabled="busy || saved" @click="save">{{busy?'正在保存…':'确认并保存记录'}}</button>
    </template>
  </view>
</template>
<style scoped>.record-card{padding:28rpx;margin:22rpx 0;display:flex;flex-direction:column;gap:18rpx}.meal-photo{width:100%;border-radius:22rpx;margin:22rpx 0}</style>
