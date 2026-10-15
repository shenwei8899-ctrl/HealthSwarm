<script setup>
import { ref, onMounted, watch } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import AppNavBar from './AppNavBar.vue'
import { commerce, commerceContext, commerceSessionEpoch, usesCommerceIdentity } from '../services/commerce.js'

const props = defineProps({ entry: Boolean, enabled: { type: Boolean, default: true } })
const emit = defineEmits(['ready'])
const ready = ref(false), busy = ref(false), error = ref('')
const account = ref(''), password = ref(''), revision = ref('guest')
let generation = 0
function sync() {
  if (props.enabled === false) return
  revision.value = commerceContext()
  ready.value = Boolean(commerce.session()?.token)
}
async function restore() {
  if (props.enabled === false) return
  sync()
  if (!ready.value || busy.value) return
  busy.value = true
  try { await commerce.restore(); emit('ready') }
  catch (e) { error.value = e.message }
  finally { sync(); busy.value = false }
}
async function login() {
  if (busy.value) return
  const ticket = ++generation
  busy.value = true; error.value = ''
  try {
    await commerce.login({ account: account.value.trim(), password: password.value })
    if (ticket === generation) { password.value = ''; sync(); emit('ready') }
  } catch (e) { if (ticket === generation) error.value = e.message }
  finally { if (ticket === generation) busy.value = false }
}
async function wechat() {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await commerce.login(); sync(); emit('ready') }
  catch (e) { error.value = e.message }
  finally { busy.value = false }
}
async function logout() {
  if (busy.value) return
  ++generation; busy.value = true; error.value = ''
  try { await commerce.logout() }
  catch (e) { error.value = e.message }
  finally { sync(); busy.value = false; if (usesCommerceIdentity) uni.reLaunch({ url: '/pages/index/index' }) }
}
watch(commerceSessionEpoch, () => {
  const wasReady = ready.value; sync();
  if (wasReady && !ready.value && !busy.value) error.value = '商城登录已过期，请重新登录';
})
onMounted(restore)
onShow(sync)
</script>
<template>
  <view>
    <slot v-if="enabled === false" />
    <view v-else-if="ready" :key="revision">
      <view class="account-row"><text>{{ usesCommerceIdentity ? '会员已登录 · ' + commerce.session()?.userId : '商城账号已登录' }}</text><button :disabled="busy" @click="logout">{{ usesCommerceIdentity ? '退出账号' : '退出商城' }}</button></view>
      <slot />
    </view>
    <view v-else :class="entry ? 'entry-login' : 'screen'">
      <AppNavBar v-if="!entry"><view class="nav-row"><button class="icon-button" @click="uni.navigateBack()">‹</button><text class="nav-title">登录商城</text><text /></view></AppNavBar>
      <view class="page-heading"><text class="display-title">登录后选购食材</text><text class="subtitle">商品、地址和订单由商城服务保存。</text></view>
      <view class="card login-form"><text class="form-label">商城会员账号</text><input v-model="account" class="field-input" placeholder="会员账号" :disabled="busy" /><text class="form-label">密码</text><input v-model="password" class="field-input" password placeholder="会员密码" :disabled="busy" /><button class="primary-button" :disabled="busy || !account.trim() || !password" @click="login">{{ busy ? '正在登录…' : '登录商城' }}</button></view>
      <!-- #ifdef MP-WEIXIN -->
      <button class="secondary-button" :disabled="busy" @click="wechat">微信登录商城</button>
      <!-- #endif -->
      <text class="safe-note">{{ usesCommerceIdentity ? '使用商城会员身份；购物车、地址和订单由后端保存。健康档案与饮食记录暂按该会员保存在本机。' : '商城会员账号与管理后台账号分别管理。' }}</text>
    </view>
    <text v-if="error" class="inline-error">{{ error }}</text>
  </view>
</template>
<style scoped>
.login-form{padding:28rpx;display:flex;flex-direction:column;gap:20rpx}.account-row{display:flex;align-items:center;justify-content:space-between;padding:12rpx 32rpx;background:#edf4ee;font-size:24rpx}.account-row button{font-size:24rpx;color:#246b50;margin:0;padding:8rpx 16rpx;background:transparent}
</style>
