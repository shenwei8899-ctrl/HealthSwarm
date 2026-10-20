<script setup>
import { scopedStorage } from '../../services/storage.js'
import AppIcon from '../../components/AppIcon.vue'
import AppNavBar from '../../components/AppNavBar.vue'
import { ref } from 'vue'
import { onShow, onHide, onUnload } from '@dcloudio/uni-app'
import { wechatAuth } from '../../services/wechat-auth.js'
import { getSession } from '../../services/session.js'
import { resolveAppEntry } from '../../services/app-entry.js'
import { isMockMode, canUseBusinessLogin, isCommerceEnabled } from '../../services/config.js'
import CommerceAccess from '../../components/CommerceAccess.vue'
import CommerceMemberEntry from '../../components/CommerceMemberEntry.vue'
import { usesCommerceIdentity } from '../../services/commerce.js'
import { getProfile,saveProfile,newMember,normalizeMember } from '../../utils/profile.js'
import { service as mockService } from '../../services/index.js'

const loginOpen = ref(false)
const testAccount = ref('creator')
const loggingIn = ref(false)
const loginError = ref(''), needsBinding = ref(false), identifier = ref(''), password = ref('')
let visible = true
let generation = 0
onShow(async () => {
  visible = true
  const mine = ++generation
  if (isMockMode || !getSession()?.token) return
  loggingIn.value = true
  try { const url = await resolveAppEntry(); if (visible && mine === generation) uni.redirectTo({ url }) }
  catch (error) { if (visible && mine === generation) loginError.value = error.message }
  finally { if (visible && mine === generation) loggingIn.value = false }
})
function closeLoginSheet() { generation++; loginOpen.value = false; password.value = ''; wechatAuth.cancelPending(); loggingIn.value = false }
function abandon() { visible = false; closeLoginSheet() }
onHide(abandon); onUnload(abandon)

function commerceReady() {
  if (visible) uni.redirectTo({ url: scopedStorage.getStorageSync('frontend-onboarded-v1') ? '/pages/chat/index' : '/pages/onboarding/index' })
}
function start() {
  if (!isMockMode && (needsBinding.value || canUseBusinessLogin)) { loginOpen.value = true; return }
  if (!isMockMode) { continueLogin(); return }
  loginOpen.value = true
}

async function continueLogin() {
  if(loggingIn.value)return
  const mine = generation
  loggingIn.value=true; loginError.value=''
  try {
  if(!isMockMode) {
    const binding = (needsBinding.value || canUseBusinessLogin) ? { identifier: identifier.value.trim(), password: password.value } : undefined
    if(binding && (!binding.identifier || !binding.password)) throw new Error('请填写已有账号与密码')
    if (canUseBusinessLogin) await wechatAuth.loginWithPassword(binding.identifier, binding.password)
    else await mockService.login(binding)
    const url = await resolveAppEntry()
    if(visible && mine === generation) { loginOpen.value=false; uni.redirectTo({url}) }
    return
  }
  await mockService.login(isMockMode?testAccount.value:undefined)
  if(isMockMode&&!scopedStorage.getStorageSync('frontend-onboarded-v1')&&!scopedStorage.getStorageSync('frontend-onboarding-progress-v1')){scopedStorage.setStorageSync('frontend-sample-profile-v1',getProfile());const member=normalizeMember({...newMember(0),name:'我',relation:'本人',age:'',claimedBy:'creator'});saveProfile({householdName:'我的家',usageMode:'个人使用',sharedDinerCount:1,members:[member],defaultDiners:[member.id],goals:[],tastes:[],memories:[]})}
  loginOpen.value = false
  uni.navigateTo({url:scopedStorage.getStorageSync('frontend-onboarded-v1')?'/pages/chat/index':'/pages/onboarding/index',fail:()=>uni.showToast({title:'打开失败，请重试',icon:'none'})})
  } catch(error) {
    if(!visible || mine !== generation)return
    loginError.value=error.message||'登录失败，请重试'
    if(error.businessCode==='WECHAT_ACCOUNT_UNBOUND'){needsBinding.value=true;loginOpen.value=true}
    uni.showToast({title:loginError.value,icon:'none'})
  } finally {if(mine === generation){password.value='';if(visible)loggingIn.value=false}}
}
</script>

<template>
<view class="screen welcome-screen"><AppNavBar><view class="nav-row"><view class="brand"><AppIcon name="chat" :size="38"/><text>家庭营养师</text></view><text></text></view></AppNavBar><view class="hero-copy"><text class="eyebrow">为一家人的日常饮食</text><text class="display-title">好好吃饭，
一起把日子过好。</text><text class="hero-description">从今天吃什么，到家人的饮食记录。
让每个家庭，拥有自己的 AI 营养师。</text></view><image class="hero-food" src="/static/food/family-meal.jpg" mode="aspectFill"/><view class="login-panel"><CommerceAccess v-if="usesCommerceIdentity" entry @ready="commerceReady"/><button v-else class="primary-button" :disabled="loggingIn" @click="start">{{ loggingIn ? '正在登录…' : canUseBusinessLogin ? '账号登录，开始使用' : '微信登录，开始使用' }}</button><CommerceMemberEntry v-if="isCommerceEnabled && !usesCommerceIdentity" :disabled="loggingIn"/><text v-if="loginError" class="login-error">{{ loginError }}</text><text v-if="isMockMode && !usesCommerceIdentity" class="safe-note">前端体验版 · 登录、推荐与交易均为模拟</text></view><view v-if="loginOpen" class="sheet-mask" @click.self="closeLoginSheet"><view class="sheet"><view class="sheet-head"><text class="section-title">{{ canUseBusinessLogin ? '账号登录' : '微信登录' }}</text><button @click="closeLoginSheet">×</button></view><text v-if="isMockMode" class="demo-label">当前模拟建立测试账号。正式版将由服务端验证微信身份；本阶段不会上传资料。</text><input v-if="isMockMode" v-model="testAccount" class="field-input" maxlength="40" placeholder="测试账号名称，不同账号资料分别保存"/><template v-if="!isMockMode && (needsBinding || canUseBusinessLogin)"><text class="demo-label">{{ canUseBusinessLogin ? '使用已有业务账号登录，家庭档案、采购清单和商城共用当前账号。' : '此微信尚未关联业务账号。验证已有普通账号后完成关联。' }}</text><input v-model="identifier" class="field-input" maxlength="100" placeholder="已有账号 UID 或手机号"/><input v-model="password" class="field-input" password maxlength="128" placeholder="已有账号密码"/></template><button class="primary-button" :disabled="loggingIn" @click="continueLogin">{{loggingIn?'正在登录…':isMockMode?'模拟登录并继续':'登录并继续'}}</button></view></view></view>
</template>
<style scoped>
.welcome-screen{display:flex;flex-direction:column;background:#fff;min-height:100vh}.brand{display:flex;align-items:center;gap:14rpx;font-size:30rpx;font-weight:600}.hero-copy{margin-top:52rpx}.hero-copy .display-title{font-size:62rpx;line-height:1.3}.hero-description{display:block;white-space:pre-line;color:#63636b;font-size:29rpx;line-height:1.8;margin-top:26rpx}.hero-food{width:100%;height:430rpx;margin:34rpx 0;border-radius:32rpx}.login-panel{margin-top:auto}.login-error{display:block;color:#a13a30;font-size:25rpx;margin-top:20rpx;line-height:1.6}.safe-note{font-size:23rpx;margin-top:24rpx}
</style>
