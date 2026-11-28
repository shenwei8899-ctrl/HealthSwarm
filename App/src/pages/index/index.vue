<script setup>
import { ref } from 'vue'
import { request } from '../../services/request.js'
import { readServiceNotice, viewNoticeDocument, acknowledgeReadNotice } from '../../services/service-notice.js'
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
const awaitingPhoneAuthorization = ref(false)
let isWechat = false, isWechatDevtools = false
// #ifdef MP-WEIXIN
isWechat = true
isWechatDevtools = typeof uni !== 'undefined' && uni.getDeviceInfo?.().platform === 'devtools'
// #endif
const isPhoneLogin = isWechat && isCommerceEnabled && !canUseBusinessLogin
const needsPhoneAuthorization = ref(!isWechatDevtools)
const loginNotice=ref(null),noticeDocument=ref(null),noticeLoading=ref(false),noticeViewing=ref(false)
let noticeRead=null,selectedNoticeOwner=null
function noticeIdentity(){const account=getSession();return JSON.stringify([account?.accountId,account?.token])}
function clearNoticeSelection(){loginNotice.value=null;selectedNoticeOwner=null}
function loadLoginNotice(){
  if(noticeRead)return noticeRead.promise
  const flight={generation};noticeRead=flight;noticeLoading.value=true
  flight.promise=(async()=>{
    try{
      const document=await readServiceNotice(request)
      if(!visible||flight.generation!==generation)return null
      if(loginNotice.value&&(loginNotice.value.version!==document.version||loginNotice.value.content_hash!==document.content_hash))clearNoticeSelection()
      noticeDocument.value=document
      return document
    }catch(error){
      if(visible&&flight.generation===generation)loginError.value=error.message||'服务声明暂时无法读取，请点击声明重试。'
      throw error
    }finally{if(noticeRead===flight){noticeRead=null;noticeLoading.value=false}}
  })()
  return flight.promise
}
async function showLoginNotice(){
  if(loggingIn.value||awaitingPhoneAuthorization.value||noticeViewing.value)return
  const mine=generation;noticeViewing.value=true
  try{const document=await loadLoginNotice();if(document&&visible&&mine===generation)await viewNoticeDocument(document)}
  catch(error){if(visible&&mine===generation)loginError.value=error.message||'服务声明暂时无法读取，请重试。'}
  finally{if(mine===generation)noticeViewing.value=false}
}
function changeLoginNotice(event){
  if(loggingIn.value||awaitingPhoneAuthorization.value||noticeViewing.value||noticeLoading.value)return
  clearNoticeSelection()
  if(!event.detail.value.includes('yes')||!noticeDocument.value)return
  const document=noticeDocument.value
  loginNotice.value={version:document.version,content_hash:document.content_hash,acknowledged:true}
  selectedNoticeOwner=noticeIdentity();loginError.value=''
}
function requireLoginNotice(){
  if(loginNotice.value&&selectedNoticeOwner===noticeIdentity())return true
  clearNoticeSelection();loginError.value='请先阅读并勾选下方的服务声明与健康提示。'
  return false
}
function refreshRejectedNotice(){
  clearNoticeSelection();noticeDocument.value=null
  if(visible)void loadLoginNotice().catch(()=>{})
}
async function saveLoginNotice(account, notice, login = false) {
  if(!account?.token||account.accountId!==getSession()?.accountId||account.token!==getSession()?.token)
    throw Object.assign(new Error('登录账号已变化，请重新操作'),{code:'SESSION_CHANGED'})
  if(account.serviceNotice?.acknowledged&&(!notice||account.serviceNotice.version===notice.version&&account.serviceNotice.content_hash===notice.content_hash))return account
  // 恢复旧会话不等于确认；只有本页明确勾选的版本才能提交。
  if(!notice||notice!==loginNotice.value||!login&&!requireLoginNotice())
    throw Object.assign(new Error('请先阅读并勾选下方的服务声明与健康提示，再点击微信登录。'),{code:'LOGIN_NOTICE_REQUIRED'})
  const status=await acknowledgeReadNotice(request,notice)
  return {...account,serviceNotice:status}
}
let phoneFlow = null
function phoneLogin() {
  if (!phoneFlow) phoneFlow = createPhoneLogin({
    auth: { restore: async () => {
      const notice=loginNotice.value,account=await wechatAuth.restore()
      return account?.token?saveLoginNotice(account,notice):account
    }, login: async () => {
      if(!requireLoginNotice())throw new Error(loginError.value)
      const notice=loginNotice.value,account=await service.login({serviceNotice:notice})
      return saveLoginNotice(account,notice,true)
    } },
    session: getSession, commerce, accountContext: storageContext,
    appId: wechatAppId,
    randomKey: () => 'phone-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2) + '-' + Math.random().toString(36).slice(2),
    resolveEntry: resolveAppEntry,
    navigate: url => new Promise((resolve,reject) => uni.reLaunch({url,success:resolve,fail:reject})),
    update: state => { if(['SERVICE_NOTICE_CHANGED','SERVICE_NOTICE_REQUIRED'].includes(state.failureCode))refreshRejectedNotice();loggingIn.value=state.busy;loginError.value=state.error;phoneUncertain.value=state.uncertain;awaitingPhoneAuthorization.value=state.awaitingAuthorization;if(state.needsAuthorization)needsPhoneAuthorization.value=true },
  })
  return phoneFlow
}
function authorizePhone(event) { if(isPhoneLogin&&requireLoginNotice())void phoneLogin().authorize(event.detail) }
function beginPhoneAuthorization() { if(isPhoneLogin&&requireLoginNotice())phoneLogin().beginAuthorization() }
function loginWechatAccount() { if(isPhoneLogin&&requireLoginNotice())void phoneLogin().login() }
function retryPhoneLogin() { if(isPhoneLogin)void phoneLogin().restore() }
let visible = true, generation = 0
async function loginDestination() {
  if (isCommerceEnabled) await commerce.connect()
  return resolveAppEntry()
}
function openEntry(url) {
  return new Promise((resolve, reject) => uni.reLaunch({ url, success: resolve,
    fail: () => reject(new Error('登录成功，但页面打开失败，请重试。')) }))
}
async function restore() {
  if (isPhoneLogin) { await phoneLogin().restore(); return }
  if (isMockMode || !getSession()?.token || loggingIn.value) return
  const mine = generation; loggingIn.value = true; loginError.value = ''
  try {
    if(!canUseBusinessLogin){const account=await wechatAuth.restore();if(account?.token)await saveLoginNotice(account,loginNotice.value)}
    const url = await loginDestination(); if (visible && mine === generation && url !== '/pages/index/index') await openEntry(url) }
  catch (e) { if (visible && mine === generation) loginError.value = e.message }
  finally { if (visible && mine === generation) loggingIn.value = false }
}
onShow(() => { visible = true; if(!isMockMode&&!canUseBusinessLogin)void loadLoginNotice().catch(()=>{});void restore() })
function closeLoginSheet() { generation++; loginOpen.value = false; loggingIn.value = false; password.value = ''; wechatAuth.cancelPending() }
function hide() { visible = false; clearNoticeSelection();noticeDocument.value=null;noticeRead=null;noticeLoading.value=false;noticeViewing.value=false;phoneFlow?.dispose(); closeLoginSheet() }
onHide(hide); onUnload(hide)
function start() { if(!isMockMode&&!canUseBusinessLogin&&!requireLoginNotice())return; if (isMockMode || canUseBusinessLogin) { loginError.value = ''; loginOpen.value = true } else void continueLogin() }
async function continueLogin() {
  if (loggingIn.value) return
  if(!isMockMode&&!canUseBusinessLogin&&!requireLoginNotice())return
  const mine = generation; loggingIn.value = true; loginError.value = ''
  try {
    const account=await service.login(isMockMode ? testAccount.value : canUseBusinessLogin ? { identifier: identifier.value, password: password.value } : {serviceNotice:loginNotice.value})
    if(!isMockMode&&!canUseBusinessLogin)await saveLoginNotice(account,loginNotice.value,true)
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
    if (visible && mine === generation) {
      await openEntry(url)
      if (visible && mine === generation) loginOpen.value = false
    }
  } catch (e) { if (visible && mine === generation) {loginError.value=e.message||'微信登录未完成，请重试。';if(e.businessCode==='SERVICE_NOTICE_CHANGED'||e.businessCode==='SERVICE_NOTICE_REQUIRED')refreshRejectedNotice()} }
  finally { if (visible && mine === generation) loggingIn.value=false }
}
</script>
<template>
<view class="screen welcome-screen"><image class="welcome-backdrop" src="/static/food/welcome-family-dining-20261111.jpg" mode="aspectFill" aria-hidden="true"/><view class="welcome-shade" aria-hidden="true"/><AppNavBar><view class="nav-row"><text class="brand">家庭营养师</text></view></AppNavBar><view class="hero-copy"><text class="display-title">{{ '好好吃饭\n照顾全家' }}</text><text class="hero-description">{{ '让每个家庭，\n拥有自己的 AI 营养师。' }}</text></view><view class="login-panel">
<!-- #ifdef MP-WEIXIN -->
<button v-if="isPhoneLogin && !loginNotice" class="primary-button" :disabled="loggingIn || noticeLoading || noticeViewing" @click="requireLoginNotice">微信登录，开始使用</button>
<button v-if="isPhoneLogin && loginNotice && needsPhoneAuthorization" class="primary-button" open-type="getPhoneNumber" :disabled="loggingIn || phoneUncertain || noticeLoading || noticeViewing" :loading="loggingIn" @click="beginPhoneAuthorization" @getphonenumber="authorizePhone">{{loggingIn?'正在登录…':awaitingPhoneAuthorization?'请在微信弹窗中授权手机号':'微信登录，开始使用'}}</button>
<button v-if="isPhoneLogin && loginNotice && !needsPhoneAuthorization" class="primary-button" :disabled="loggingIn || phoneUncertain || noticeLoading || noticeViewing" :loading="loggingIn" @click="loginWechatAccount">{{loggingIn?'正在登录…':'微信登录，开始使用'}}</button>
<!-- #endif -->
<button v-if="!isPhoneLogin" class="primary-button" :disabled="loggingIn || noticeLoading || noticeViewing" @click="start">{{loggingIn?'正在登录…':canUseBusinessLogin?'测试账号登录，开始使用':'微信登录，开始使用'}}</button>
<checkbox-group v-if="!isMockMode&&!canUseBusinessLogin" class="login-notice" @change="changeLoginNotice"><view class="login-notice-row"><label class="login-notice-toggle"><checkbox value="yes" :checked="!!loginNotice" :disabled="loggingIn||awaitingPhoneAuthorization||noticeLoading||noticeViewing||!noticeDocument" color="#292d20" aria-label="确认已阅读并理解服务声明与健康提示"/></label><view class="login-notice-copy"><text>我已阅读并理解</text><button class="login-notice-link" :disabled="loggingIn||awaitingPhoneAuthorization||noticeViewing" @tap.stop="showLoginNotice">《服务声明与健康提示》</button></view></view></checkbox-group>
<text v-if="loginError" class="login-error" role="alert">{{loginError}}</text><button v-if="isPhoneLogin && (loginError || phoneUncertain)" class="secondary-button" :disabled="loggingIn" @click="retryPhoneLogin">重新检查登录状态</button><text v-if="isPhoneLogin" class="safe-note">微信授权手机号后继续使用，手机号绑定到当前账号。</text><text v-if="phoneBindingDemo" class="safe-note">隔离环境演示</text><text v-if="canUseBusinessLogin" class="safe-note">{{canUseH5TestLogin?'功能测试 · 使用独立测试账号':'本机联调 · 使用真实业务账号'}}</text><text v-if="isMockMode" class="safe-note">前端体验版 · 登录、推荐与交易均为模拟</text></view><view v-if="loginOpen && canUseBusinessLogin" class="sheet-mask" @click="closeLoginSheet"><view class="sheet" @click.stop><view class="sheet-head"><text class="section-title">测试账号登录</text><button aria-label="关闭登录" @click="closeLoginSheet">×</button></view><text class="demo-label">使用业务账号连接真实服务，资料会保存到服务端。</text><input v-model="identifier" class="field-input" maxlength="100" placeholder="业务测试账号" aria-label="业务测试账号" :disabled="loggingIn"/><input v-model="password" class="field-input" password maxlength="128" placeholder="密码" aria-label="密码" :disabled="loggingIn" confirm-type="done" @confirm="continueLogin"/><text v-if="loginError" class="login-error" role="alert">{{loginError}}</text><button class="primary-button" :disabled="loggingIn || !identifier.trim() || !password" @click="continueLogin">{{loggingIn?'正在登录…':'登录并继续'}}</button></view></view><view v-if="loginOpen && isMockMode" class="sheet-mask" @click="closeLoginSheet"><view class="sheet" @click.stop><view class="sheet-head"><text class="section-title">模拟微信登录</text><button @click="closeLoginSheet">×</button></view><text class="demo-label">此处仅创建本机测试身份，不是真实微信授权。</text><input v-model="testAccount" class="field-input" maxlength="40" placeholder="测试账号名称"/><text v-if="loginError" class="login-error" role="alert">{{loginError}}</text><button class="primary-button" :disabled="loggingIn" :loading="loggingIn" @click="continueLogin">{{loggingIn?'正在登录…':'模拟登录并继续'}}</button></view></view></view>
</template>
<style scoped>
.welcome-screen.screen{position:relative;z-index:0;isolation:isolate;display:flex;flex-direction:column;min-height:100vh;min-height:100svh;padding:24rpx 40rpx calc(env(safe-area-inset-bottom) + 38rpx);background:#75784e;color:#fff;overflow:hidden}
.welcome-backdrop{position:absolute;z-index:-2;inset:0;width:100%;height:100%;pointer-events:none}
.welcome-shade{position:absolute;z-index:-1;inset:0;background:linear-gradient(180deg,rgba(34,40,19,.06) 0%,rgba(34,40,19,0) 40%,rgba(34,40,19,0) 76%,rgba(27,30,15,.62) 100%);pointer-events:none}
.welcome-screen :deep(.app-nav){position:relative;z-index:1;padding-bottom:0}
.welcome-screen .nav-row{justify-content:flex-start;min-height:88rpx}
.brand{font-size:32rpx;font-weight:500;line-height:1.4;letter-spacing:2rpx;color:#fff}
.hero-copy{position:relative;z-index:1;margin-top:2vh;flex-shrink:0}
.hero-copy .display-title{font-size:80rpx;font-weight:400;line-height:1.18;letter-spacing:3rpx;color:#fff}
.hero-description{display:block;white-space:pre-line;margin-top:24rpx;font-size:30rpx;font-weight:400;line-height:1.5;letter-spacing:1rpx;color:#fff}
.login-panel{position:relative;z-index:1;margin-top:auto;padding-top:18vh;flex-shrink:0}
.login-panel>.primary-button{width:100%;min-height:108rpx;padding:24rpx 20rpx;border:1rpx solid rgba(255,255,255,.12);border-radius:999rpx;background:#111;color:#fff;font-size:31rpx;font-weight:500;line-height:1.5;letter-spacing:1rpx;box-shadow:0 8rpx 30rpx rgba(0,0,0,.1)}
.login-panel>.primary-button:active{background:#24211e}
.login-panel>.primary-button[disabled]{opacity:.65}
.login-notice{display:block;margin-top:22rpx;padding:16rpx 16rpx 12rpx;border-radius:16rpx;background:rgba(25,29,15,.62);color:#fff}.login-notice-row{display:flex;align-items:center;gap:8rpx}.login-notice-toggle{display:flex;align-items:center;justify-content:center;width:48rpx;min-height:48rpx;flex-shrink:0}.login-notice-toggle checkbox{transform:scale(.8);transform-origin:center}.login-notice-copy{display:flex;align-items:center;flex-wrap:wrap;flex:1;min-width:0;font-size:23rpx;line-height:1.7;text-align:left}.login-notice-link{display:inline-flex;align-items:center;width:auto;margin:0;padding:0;min-height:44rpx;border:0;border-radius:0;background:transparent;color:#fff;font-size:inherit;line-height:inherit;white-space:nowrap;text-decoration:underline;text-underline-offset:4rpx;text-align:left}.login-notice-link:after{border:0}.login-notice-link[disabled]{background:transparent;color:rgba(255,255,255,.65)}
.login-panel>.secondary-button{margin-top:18rpx;background:rgba(255,255,255,.96);color:#30251f;border-color:transparent;border-radius:16rpx;font-size:28rpx}
.login-panel>.login-error{display:block;margin-top:18rpx;padding:16rpx 20rpx;background:rgba(42,18,12,.86);border:1rpx solid rgba(255,255,255,.25);border-radius:12rpx;color:#fff;font-size:27rpx;line-height:1.6;overflow-wrap:anywhere}
.login-panel>.safe-note{display:block;margin-top:20rpx;color:rgba(255,255,255,.94);font-size:24rpx;line-height:1.6;text-align:center}
.sheet-mask{color:#202126}.sheet .primary-button{background:#25262a}.sheet .login-error{display:block;color:#b83532;font-size:27rpx;line-height:1.6;margin-top:18rpx}
@media(max-height:740px){.hero-copy{margin-top:1vh}.hero-copy .display-title{font-size:76rpx}.hero-description{margin-top:20rpx;font-size:28rpx;line-height:1.5}.login-panel{padding-top:12vh}}
@media(max-width:350px){.welcome-screen.screen{padding-left:36rpx;padding-right:36rpx}.hero-copy .display-title{font-size:76rpx;letter-spacing:2rpx}.hero-description{font-size:28rpx}}
/* #ifdef MP-WEIXIN */
.welcome-screen.screen{padding-top:0}
.hero-copy{margin-top:1vh}
/* #endif */
</style>
