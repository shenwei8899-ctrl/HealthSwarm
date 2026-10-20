<script setup>
import { ref } from 'vue'
import { onShow, onHide } from '@dcloudio/uni-app'
import AppNavBar from '../../components/AppNavBar.vue'
import { wechatAuth } from '../../services/wechat-auth.js'
import { resolveAppEntry } from '../../services/app-entry.js'
import { request } from '../../services/request.js'
import { sessionRevision } from '../../services/session.js'
const families=ref([]),busy=ref(false),error=ref(''),code=ref('')
let active=true
onShow(async()=>{active=true;busy.value=true;error.value='';try{const account=await wechatAuth.restore();if(!active)return;if(!account){uni.reLaunch({url:'/pages/index/index'});return}families.value=account.families||[]}catch(e){if(active)error.value=e.message}finally{if(active)busy.value=false}})
onHide(()=>{active=false;families.value=[];code.value='';error.value=''})
async function choose(id){if(busy.value)return;busy.value=true;error.value='';try{await wechatAuth.selectFamily(id);if(!active)return;const url=await resolveAppEntry();if(active)uni.redirectTo({url})}catch(e){if(active)error.value=e.message}finally{if(active)busy.value=false}}
async function join(){if(busy.value)return;if(code.value.trim().length<20){error.value='请填写有效的家庭成员邀请码';return}const ticket=sessionRevision();busy.value=true;error.value='';try{await request({path:'/api/family/join',method:'POST',data:{code:code.value.trim()}});if(!active||ticket!==sessionRevision())return;const account=await wechatAuth.restore();if(active){families.value=account.families;code.value=''}}catch(e){if(active)error.value=e.code==='NETWORK_ERROR'?'加入结果尚未确认，请重新进入本页读取家庭列表后再操作。':e.message}finally{if(active)busy.value=false}}
</script>
<template><view class="screen family-choice"><AppNavBar><view class="nav-row"><button class="icon-button" @click="uni.navigateBack({fail:()=>uni.reLaunch({url:'/pages/index/index'})})">‹</button><text class="nav-title">我的家庭</text><text/></view></AppNavBar><view class="page-heading"><text class="display-title">今天为谁安排饮食？</text><text class="muted">选择一个家庭，继续查看档案与今日安排。</text></view><text v-if="error" class="inline-error" role="alert">{{error}}</text><text v-if="busy" class="safe-note">正在读取家庭…</text><button v-for="family in families" :key="family.id" class="card family-option" :disabled="busy" @click="choose(family.id)"><text>{{family.name}}</text><text>继续 ›</text></button><button v-if="!families.length&&!busy" class="primary-button" @click="uni.redirectTo({url:'/pages/onboarding/index'})">开始家庭建档</button><view class="card join-family"><text class="section-title">加入家人的家庭</text><input v-model="code" class="field-input" placeholder="输入家人发来的成员邀请码" :disabled="busy"/><button class="secondary-button" :disabled="busy" @click="join">确认加入</button></view></view></template>
<style scoped>.family-option{display:flex;justify-content:space-between;width:100%;padding:32rpx;margin:22rpx 0;font-size:30rpx;text-align:left}.family-option text+text{color:#767680;font-size:25rpx}.page-heading .muted{display:block;margin-top:24rpx;font-size:27rpx;line-height:1.8}.join-family{padding:28rpx;margin-top:40rpx}.join-family .secondary-button{width:100%}</style>
