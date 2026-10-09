<script setup>
import { ref } from 'vue'
import { onShow, onHide, onUnload } from '@dcloudio/uni-app'
import { client } from '../../services/runtime.js'

const identifier = ref('')
const password = ref('')
const busy = ref(false)
const restoring = ref(false)
const error = ref('')
let operation = 0
let visible = false
const unsubscribe = client.subscribeSession(session => { if (!session) password.value = '' })

function enterMembers() {
  password.value = ''
  uni.reLaunch({ url: '/pages/members/index' })
}

onShow(async () => {
  visible = true
  password.value = ''
  error.value = ''
  const current = ++operation
  if (client.getSession()) { enterMembers(); return }
  restoring.value = true
  try {
    await client.restoreSession()
    if (visible && current === operation && client.getSession()) enterMembers()
  } catch (failure) {
    if (visible && current === operation && failure.code !== 'stale_session') error.value = failure.message || '会话校验失败，请重新登录'
  } finally {
    if (current === operation) restoring.value = false
  }
})

async function login() {
  if (busy.value || restoring.value) return
  if (!identifier.value.trim() || !password.value) { error.value = '请填写 UID 或手机号，以及密码'; return }
  const current = ++operation
  const account = identifier.value.trim()
  const secret = password.value
  busy.value = true
  error.value = ''
  password.value = ''
  try {
    await client.login(account, secret)
    if (visible && current === operation && client.getSession()) enterMembers()
  } catch (failure) {
    if (visible && current === operation && failure.code !== 'stale_session') error.value = failure.message || '登录失败，请重试'
  } finally {
    if (current === operation) busy.value = false
  }
}

onHide(() => { visible = false; operation += 1; password.value = ''; busy.value = false; restoring.value = false })
onUnload(() => { unsubscribe(); password.value = '' })
</script>

<template>
  <view class="screen access-screen">
    <AppNavBar><view class="nav-row"><view><AppIcon name="user" :size="36" /></view><text class="nav-title">家庭营养师</text><view /></view></AppNavBar>
    <view class="page-heading"><text class="eyebrow">账号接入</text><text class="display-title">登录你的账号</text><text class="subtitle">使用已有账号，读取你可访问的家庭与本人档案关系。</text></view>
    <view class="card access-card">
      <text class="section-title">账号登录</text>
      <text class="body-copy">账号由管理员创建，并需设置所属部门。</text>
      <text class="field-label">UID 或手机号</text>
      <input v-model="identifier" class="field-input" placeholder="请输入 UID 或手机号" :disabled="busy || restoring" :maxlength="128" confirm-type="next" aria-label="UID 或手机号" />
      <text class="field-label">密码</text>
      <input v-model="password" class="field-input" placeholder="请输入密码" password :disabled="busy || restoring" :maxlength="256" confirm-type="done" aria-label="密码" @confirm="login" />
      <view v-if="error" class="error-box" role="alert"><text>{{ error }}</text></view>
      <button class="primary-button" :disabled="busy || restoring" @click="login">{{ restoring ? '正在校验会话…' : busy ? '正在登录…' : '登录并查看家庭' }}</button>
    </view>
    <view class="notice"><text>本阶段使用现有账号密码登录。微信快捷登录将另行接入。</text></view>
    <text class="safe-note">本入口仅用于账号及本人成员接入。首次登录没有家庭或健康成员时，请联系管理员或先在已有后台完成准备。</text>
  </view>
</template>
