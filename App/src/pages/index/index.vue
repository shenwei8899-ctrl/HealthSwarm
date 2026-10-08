<script setup>
import AppIcon from '../../components/AppIcon.vue'
import AppNavBar from '../../components/AppNavBar.vue'
import { ref } from 'vue'
import { getProfile,saveProfile,newMember,normalizeMember } from '../../utils/profile.js'
import { mockService } from '../../services/mock.js'

const loginOpen = ref(false)
const phone = ref('13800000000')
const loggingIn = ref(false)

function start() {
  loginOpen.value = true
}

async function continueLogin() {
  if(loggingIn.value)return
  loggingIn.value=true
  try {
  if(!uni.getStorageSync('frontend-onboarded-v1')&&!uni.getStorageSync('frontend-onboarding-progress-v1')){uni.setStorageSync('frontend-sample-profile-v1',getProfile());const member=normalizeMember({...newMember(0),name:'我',relation:'本人',claimedBy:'creator'});saveProfile({householdName:'我的家',usageMode:'个人使用',sharedDinerCount:2,members:[member],defaultDiners:[member.id],goals:[],tastes:[],memories:[]})}
  await mockService.login()
  loginOpen.value = false
  uni.navigateTo({url:uni.getStorageSync('frontend-onboarded-v1')?'/pages/chat/index':'/pages/onboarding/index',fail:()=>uni.showToast({title:'打开失败，请重试',icon:'none'})})
  } catch(error) {uni.showToast({title:error.message||'登录失败，请重试',icon:'none'})} finally {loggingIn.value=false}
}
</script>

<template>
<view class="screen welcome-screen"><AppNavBar><view class="nav-row"><view class="brand"><AppIcon name="chat" :size="38"/><text>家庭营养师</text></view><text></text></view></AppNavBar><view class="hero-copy"><text class="eyebrow">为一家人的日常饮食</text><text class="display-title">好好吃饭，
一起把日子过好。</text><text class="hero-description">从今天吃什么，到家人的饮食记录。
让每个家庭，拥有自己的 AI 营养师。</text></view><image class="hero-food" src="/static/food/family-meal.jpg" mode="aspectFill"/><view class="login-panel"><button class="primary-button" @click="start">微信登录，开始使用</button><button class="secondary-button preview-button" @click="uni.navigateTo({url:'/pages/chat/index'})">先体验示例家庭</button><text class="safe-note">前端体验版 · 登录、推荐与交易均为模拟</text></view><view v-if="loginOpen" class="sheet-mask" @click.self="loginOpen=false"><view class="sheet"><view class="sheet-head"><text class="section-title">微信登录</text><button @click="loginOpen=false">×</button></view><text class="demo-label">当前模拟建立测试账号。正式版将由服务端验证微信身份；本阶段不会上传资料。</text><button class="primary-button" :disabled="loggingIn" @click="continueLogin">{{loggingIn?'正在登录…':'模拟登录并继续'}}</button></view></view></view>
</template>
<style scoped>
.welcome-screen{display:flex;flex-direction:column;background:#fff;min-height:100vh}.brand{display:flex;align-items:center;gap:14rpx;font-size:30rpx;font-weight:600}.hero-copy{margin-top:52rpx}.hero-copy .display-title{font-size:62rpx;line-height:1.3}.hero-description{display:block;white-space:pre-line;color:#63636b;font-size:29rpx;line-height:1.8;margin-top:26rpx}.hero-food{width:100%;height:430rpx;margin:34rpx 0;border-radius:32rpx}.login-panel{margin-top:auto}.preview-button{margin-top:20rpx}.safe-note{font-size:23rpx;margin-top:24rpx}
</style>
