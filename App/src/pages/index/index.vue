<script setup>
import { ref } from 'vue'
import { onShow, onHide, onUnload } from '@dcloudio/uni-app'
import AppIcon from '../../components/AppIcon.vue'
import AppNavBar from '../../components/AppNavBar.vue'
import { isMockMode, canUseBusinessLogin, canUseH5TestLogin, isCommerceEnabled, phoneBindingDemo, wechatAppId } from '../../services/config.js'
import { commerce } from '../../services/commerce.js'
import { getSession } from '../../services/session.js'
import { wechatAuth } from '../../services/wechat-auth.js'
import { resolveAppEntry } from '../../services/app-entry.js'
import { service } from '../../services/index.js'
import { createPhoneLogin } from '../../services/phone-login.js'
import { scopedStorage, storageContext } from '../../services/storage.js'
import { getProfile, saveProfile, newMember, normalizeMember } from '../../utils/profile.js'
const loggingIn = ref(false), loginError = ref(''), loginOpen = ref(false), testAccount = ref('creator')
const identifier = ref(''), password = ref(''), phoneUncertain = ref(false)
let isWechat = false
// #ifdef MP-WEIXIN
isWechat = true
// #endif
const isPhoneLogin = isWechat && isCommerceEnabled && !canUseBusinessLogin
let phoneFlow = null
function phoneLogin() {
  if (!phoneFlow) phoneFlow = createPhoneLogin({
    auth: { restore: () => wechatAuth.restore(), login: () => service.login() },
    session: getSession, commerce, accountContext: storageContext,
    appId: wechatAppId,
    randomKey: () => 'phone-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2) + '-' + Math.random().toString(36).slice(2),
    resolveEntry: resolveAppEntry,
    navigate: url => new Promise((resolve,reject) => uni.reLaunch({url,success:resolve,fail:reject})),
    update: state => { loggingIn.value=state.busy;loginError.value=state.error;phoneUncertain.value=state.uncertain },
  })
  return phoneFlow
}
function authorizePhone(event) { if(isPhoneLogin)void phoneLogin().authorize(event.detail) }
function retryPhoneLogin() { if(isPhoneLogin)void phoneLogin().restore() }
let visible = true, generation = 0
async function loginDestination() {
  if (isCommerceEnabled) await commerce.connect()
  return resolveAppEntry()
}
async function restore() {
  if (isPhoneLogin) { await phoneLogin().restore(); return }
  if (isMockMode || !getSession()?.token || loggingIn.value) return
  const mine = generation; loggingIn.value = true; loginError.value = ''
  try { const url = await loginDestination(); if (visible && mine === generation && url !== '/pages/index/index') uni.reLaunch({url}) }
  catch (e) { if (visible && mine === generation) loginError.value = e.message }
  finally { if (visible && mine === generation) loggingIn.value = false }
}
onShow(() => { visible = true; void restore() })
function closeLoginSheet() { generation++; loginOpen.value = false; loggingIn.value = false; password.value = ''; wechatAuth.cancelPending() }
function hide() { visible = false; phoneFlow?.dispose(); closeLoginSheet() }
onHide(hide); onUnload(hide)
function start() { if (isMockMode || canUseBusinessLogin) { loginError.value = ''; loginOpen.value = true } else void continueLogin() }
async function continueLogin() {
  if (loggingIn.value) return
  const mine = generation; loggingIn.value = true; loginError.value = ''
  try {
    await service.login(isMockMode ? testAccount.value : canUseBusinessLogin ? { identifier: identifier.value, password: password.value } : undefined)
    password.value = ''
    if (!visible || mine !== generation) return
    let url
    if (isMockMode) {
      if (!scopedStorage.getStorageSync('frontend-onboarded-v1') && !scopedStorage.getStorageSync('frontend-onboarding-progress-v1')) {
        scopedStorage.setStorageSync('frontend-sample-profile-v1',getProfile())
        const member=normalizeMember({...newMember(0),name:'我',relation:'本人',age:'',claimedBy:'creator'})
        saveProfile({householdName:'我的家',usageMode:'个人使用',members:[member],defaultDiners:[member.id],goals:[],tastes:[],memories:[]})
      }
      url=scopedStorage.getStorageSync('frontend-onboarded-v1')?'/pages/chat/index':'/pages/onboarding/index'
    } else url=await loginDestination()
    if (visible && mine === generation) { loginOpen.value=false; uni.reLaunch({url}) }
  } catch (e) { if (visible && mine === generation) loginError.value=e.message||'微信登录未完成，请重试。' }
  finally { if (visible && mine === generation) loggingIn.value=false }
}
</script>
<template>
<view class="screen welcome-screen"><image class="welcome-backdrop" src="/static/food/welcome-kitchen-20261026.jpg" mode="aspectFill" aria-hidden="true"/><view class="welcome-shade" aria-hidden="true"/><AppNavBar><view class="nav-row"><text class="brand">家庭营养师</text></view></AppNavBar><view class="hero-copy"><text class="display-title">{{ '好好吃饭\n照顾全家' }}</text><text class="hero-description">{{ '让每个家庭，\n拥有自己的 AI 营养师。' }}</text></view><view class="login-panel">
<!-- #ifdef MP-WEIXIN -->
<button v-if="isPhoneLogin" class="primary-button" open-type="getPhoneNumber" :disabled="loggingIn || phoneUncertain" :loading="loggingIn" @getphonenumber="authorizePhone">{{loggingIn?'正在登录…':'微信登录，开始使用'}}</button>
<!-- #endif -->
<button v-if="!isPhoneLogin" class="primary-button" :disabled="loggingIn" @click="start">{{loggingIn?'正在登录…':canUseBusinessLogin?'测试账号登录，开始使用':'微信登录，开始使用'}}</button><text v-if="loginError" class="login-error" role="alert">{{loginError}}</text><button v-if="isPhoneLogin && (loginError || phoneUncertain)" class="secondary-button" :disabled="loggingIn" @click="retryPhoneLogin">重新检查登录状态</button><text v-if="isPhoneLogin" class="safe-note">微信授权手机号后继续使用，手机号绑定到当前账号。</text><text v-if="phoneBindingDemo" class="safe-note">隔离环境演示</text><text v-if="canUseBusinessLogin" class="safe-note">{{canUseH5TestLogin?'功能测试 · 使用独立测试账号':'本机联调 · 使用真实业务账号'}}</text><text v-if="isMockMode" class="safe-note">前端体验版 · 登录、推荐与交易均为模拟</text></view><view v-if="loginOpen && canUseBusinessLogin" class="sheet-mask" @click="closeLoginSheet"><view class="sheet" @click.stop><view class="sheet-head"><text class="section-title">测试账号登录</text><button aria-label="关闭登录" @click="closeLoginSheet">×</button></view><text class="demo-label">使用业务账号连接真实服务，资料会保存到服务端。</text><input v-model="identifier" class="field-input" maxlength="100" placeholder="业务测试账号" aria-label="业务测试账号" :disabled="loggingIn"/><input v-model="password" class="field-input" password maxlength="128" placeholder="密码" aria-label="密码" :disabled="loggingIn" confirm-type="done" @confirm="continueLogin"/><text v-if="loginError" class="login-error" role="alert">{{loginError}}</text><button class="primary-button" :disabled="loggingIn || !identifier.trim() || !password" @click="continueLogin">{{loggingIn?'正在登录…':'登录并继续'}}</button></view></view><view v-if="loginOpen && isMockMode" class="sheet-mask" @click.self="closeLoginSheet"><view class="sheet"><view class="sheet-head"><text class="section-title">模拟微信登录</text><button @click="closeLoginSheet">×</button></view><text class="demo-label">此处仅创建本机测试身份，不是真实微信授权。</text><input v-model="testAccount" class="field-input" maxlength="40" placeholder="测试账号名称"/><button class="primary-button" :disabled="loggingIn" @click="continueLogin">模拟登录并继续</button></view></view></view>
</template>
<style scoped>
.welcome-screen.screen{position:relative;z-index:0;isolation:isolate;display:flex;flex-direction:column;min-height:100vh;min-height:100svh;padding:24rpx 40rpx calc(env(safe-area-inset-bottom) + 38rpx);background:#67472f;color:#fff;overflow:hidden}
.welcome-backdrop{position:absolute;z-index:-2;top:0;right:0;width:125%;min-width:56.25vh;height:100%;pointer-events:none}
.welcome-shade{position:absolute;z-index:-1;inset:0;background:linear-gradient(180deg,rgba(24,13,7,.12) 0%,rgba(24,13,7,0) 52%,rgba(24,13,7,.12) 72%,rgba(24,13,7,.64) 100%);pointer-events:none}
.welcome-screen :deep(.app-nav){position:relative;z-index:1;padding-bottom:0}
.welcome-screen .nav-row{justify-content:flex-start;min-height:88rpx}
.brand{font-size:32rpx;font-weight:500;line-height:1.4;letter-spacing:2rpx;color:#fff}
.hero-copy{position:relative;z-index:1;margin-top:9vh;flex-shrink:0}
.hero-copy .display-title{font-size:86rpx;font-weight:400;line-height:1.28;letter-spacing:3rpx;color:#fff}
.hero-description{display:block;white-space:pre-line;margin-top:30rpx;font-size:29rpx;font-weight:400;line-height:1.85;letter-spacing:1rpx;color:#fff}
.login-panel{position:relative;z-index:1;margin-top:auto;padding-top:30vh;flex-shrink:0}
.login-panel>.primary-button{width:100%;min-height:108rpx;padding:24rpx 20rpx;border:1rpx solid rgba(255,255,255,.12);border-radius:16rpx;background:#111;color:#fff;font-size:31rpx;font-weight:500;line-height:1.5;letter-spacing:1rpx;box-shadow:0 8rpx 30rpx rgba(0,0,0,.1)}
.login-panel>.primary-button:active{background:#24211e}
.login-panel>.primary-button[disabled]{opacity:.65}
.login-panel>.secondary-button{margin-top:18rpx;background:rgba(255,255,255,.96);color:#30251f;border-color:transparent;border-radius:16rpx;font-size:28rpx}
.login-panel>.login-error{display:block;margin-top:18rpx;padding:16rpx 20rpx;background:rgba(42,18,12,.86);border:1rpx solid rgba(255,255,255,.25);border-radius:12rpx;color:#fff;font-size:27rpx;line-height:1.6;overflow-wrap:anywhere}
.login-panel>.safe-note{display:block;margin-top:20rpx;color:rgba(255,255,255,.94);font-size:24rpx;line-height:1.6;text-align:center}
.sheet-mask{color:#202126}.sheet .primary-button{background:#25262a}.sheet .login-error{display:block;color:#b83532;font-size:27rpx;line-height:1.6;margin-top:18rpx}
@media(max-height:740px){.hero-copy{margin-top:6vh}.hero-copy .display-title{font-size:80rpx}.hero-description{margin-top:22rpx;font-size:28rpx;line-height:1.7}.login-panel{padding-top:32vh}}
@media(max-width:350px){.welcome-screen.screen{padding-left:36rpx;padding-right:36rpx}.hero-copy .display-title{font-size:82rpx;letter-spacing:2rpx}.hero-description{font-size:28rpx}}
/* #ifdef MP-WEIXIN */
.welcome-screen.screen{padding-top:0}
/* #endif */
</style>
