<script setup>
import { ref, computed } from 'vue'
import { onShow, onHide, onUnload } from '@dcloudio/uni-app'
import AppNavBar from '../../components/AppNavBar.vue'
import { wechatAuth } from '../../services/wechat-auth.js'
import { request } from '../../services/request.js'
import { getSession, sessionRevision } from '../../services/session.js'
import { selfMember, basicProfileInput } from '../../services/family-onboarding.js'

const account = ref(null), families = ref([]), member = ref(null), form = ref({})
const familyName = ref(''), invitation = ref(''), error = ref(''), busy = ref(false), uncertain = ref(false)
const unsaved = computed(() => {
  if (!member.value) return true
  try { return JSON.stringify(basicProfileInput(form.value)) !== JSON.stringify(basicProfileInput(member.value.profile)) }
  catch { return true }
})
let generation = 0
function active(ticket) { return ticket.generation === generation && ticket.revision === sessionRevision() }
function discard() {
  generation++; wechatAuth.cancelPending(); account.value = null; families.value = []; member.value = null; form.value = {}
  invitation.value = ''; familyName.value = ''; error.value = ''; uncertain.value = false; busy.value = false
}
async function load() {
  const mine = ++generation
  busy.value = true; error.value = ''; member.value = null; form.value = {}; families.value = []
  try {
    if (!getSession()?.token) { uni.reLaunch({ url: '/pages/index/index' }); return }
    const result = await wechatAuth.restore()
    if (mine !== generation) return
    account.value = result; families.value = result.families; uncertain.value = false
    if (result.householdId) {
      const ticket = { generation: mine, revision: sessionRevision() }
      const response = await request({ path: '/api/family/' + encodeURIComponent(result.householdId) })
      if (!active(ticket)) return
      member.value = selfMember(response.data)
      form.value = member.value ? { ...member.value.profile } : {}
    }
  } catch (e) {
    if (mine !== generation) return
    account.value = null; families.value = []; member.value = null; form.value = {}
    error.value = e.message
    if (e.code === 401 || e.code === 'SESSION_IDENTITY_CHANGED') uni.reLaunch({ url: '/pages/index/index' })
  } finally { if (mine === generation) busy.value = false }
}
async function select(id) {
  if (busy.value) return
  const mine = generation; busy.value = true; error.value = ''
  try { await wechatAuth.selectFamily(id); if (mine === generation) await load() }
  catch (e) { if (mine === generation) { error.value = e.message; member.value = null; form.value = {} } }
  finally { if (mine === generation) busy.value = false }
}
async function write(options) {
  if (busy.value || uncertain.value) return
  const ticket = { generation, revision: sessionRevision() }; busy.value = true; error.value = ''
  try {
    await request(options)
    if (active(ticket)) { invitation.value = ''; await load() }
  } catch (e) {
    if (ticket.generation === generation && !getSession()?.token) {
      discard(); uni.reLaunch({ url: '/pages/index/index' }); return
    }
    if (!active(ticket)) return
    // An unknown write must be reconciled by a fresh read before another write.
    uncertain.value = e.code === 'NETWORK_ERROR' || Number(e.code) >= 500
    if ([401, 403, 404].includes(e.code)) { member.value = null; form.value = {}; account.value = null; families.value = [] }
    error.value = uncertain.value ? '操作结果暂未确认，请先重新读取家庭状态。' : e.message
  } finally { if (active(ticket)) busy.value = false }
}
function createFamily() {
  const name = familyName.value.trim()
  if (!name || name.length > 80) { error.value = '请填写家庭名称（最多80字）'; return }
  return write({ path: '/api/family', method: 'POST', data: { name } })
}
function joinFamily() {
  const code = invitation.value.trim()
  if (code.length < 20 || code.length > 100) { error.value = '请填写有效的家庭成员邀请码'; return }
  return write({ path: '/api/family/join', method: 'POST', data: { code } })
}
function save() {
  if (!member.value || !account.value?.householdId) return
  try {
    return write({ path: `/api/family/${encodeURIComponent(account.value.householdId)}/members/${encodeURIComponent(member.value.id)}`,
      method: 'PUT', data: { expected_version: member.value.version, profile: basicProfileInput(form.value) } })
  } catch (e) { error.value = e.message }
}
function confirm() {
  if (!member.value || !account.value?.householdId || unsaved.value) return
  return write({ path: `/api/family/${encodeURIComponent(account.value.householdId)}/members/${encodeURIComponent(member.value.id)}/confirm`,
    method: 'POST', data: { expected_version: member.value.version } })
}
function logout() { discard(); wechatAuth.logout(); uni.reLaunch({ url: '/pages/index/index' }) }
onShow(load); onHide(discard); onUnload(discard)
</script>

<template>
  <view class="screen account-screen">
    <AppNavBar><view class="nav-row"><text class="nav-title">账号与家庭</text><button class="text-button" @click="logout">退出登录</button></view></AppNavBar>
    <view class="page-heading"><text class="display-title">建立自己的家庭</text><text v-if="account" class="subtitle">已登录：{{ account.accountName }}</text></view>
    <text v-if="error" class="error-note">{{ error }}</text>
    <button class="secondary-button" :disabled="busy" @click="load">{{ busy ? '正在读取…' : '重新读取家庭状态' }}</button>
    <template v-if="account">
      <view class="card section"><text class="section-title">选择家庭</text>
        <text v-if="!families.length" class="helper">你还没有加入家庭，可以创建自己的家庭或使用成员邀请码加入。</text>
        <button v-for="family in families" :key="family.id" class="secondary-button" :disabled="busy" @click="select(family.id)">{{ family.name }}{{ account.householdId === family.id ? ' · 当前家庭' : '' }}</button>
      </view>
      <view v-if="!families.some(f => f.isOwner)" class="card section"><text class="section-title">创建家庭</text><input v-model="familyName" class="field-input" maxlength="80" placeholder="家庭名称" :disabled="busy || uncertain"/><button class="primary-button" :disabled="busy || uncertain" @click="createFamily">确认创建家庭</button></view>
      <view class="card section"><text class="section-title">加入已有家庭</text><input v-model="invitation" class="field-input" maxlength="100" placeholder="家庭成员邀请码" :disabled="busy || uncertain"/><button class="secondary-button" :disabled="busy || uncertain" @click="joinFamily">确认加入并认领本人</button></view>
      <view v-if="member" class="card section"><text class="section-title">本人基础资料</text>
        <text class="helper">填写自己的资料，未填写的项目保持未知。保存后请核对，再确认当前版本。</text>
        <text class="label">性别</text><view class="choices"><button v-for="item in [{v:'female',n:'女'},{v:'male',n:'男'},{v:'unspecified',n:'暂不说明'}]" :key="item.v" :class="{ selected: form.sex === item.v }" :disabled="busy || uncertain" @click="form.sex=item.v">{{ item.n }}</button></view>
        <input v-model="form.birth_date" class="field-input" maxlength="10" placeholder="生日 YYYY-MM-DD" :disabled="busy || uncertain"/>
        <input v-model="form.height_cm" class="field-input" type="digit" placeholder="身高（厘米，可稍后补充）" :disabled="busy || uncertain"/>
        <text class="label">日常活动量</text><view class="choices"><button v-for="item in [{v:'sedentary',n:'久坐'},{v:'light',n:'轻度'},{v:'moderate',n:'中等'},{v:'high',n:'较高'}]" :key="item.v" :class="{ selected: form.activity_level === item.v }" :disabled="busy || uncertain" @click="form.activity_level=item.v">{{ item.n }}</button></view>
        <input v-model="form.goal" class="field-input" maxlength="200" placeholder="你的饮食目标（可稍后补充）" :disabled="busy || uncertain"/>
        <button class="primary-button" :disabled="busy || uncertain" @click="save">保存本人资料</button>
        <text class="helper">服务端档案版本：{{ member.version }} · {{ member.confirmed ? '已确认' : '待本人确认' }}</text>
        <text v-if="unsaved" class="helper">有尚未保存的修改，请先保存，再确认。</text>
        <button class="secondary-button" :disabled="busy || uncertain || member.confirmed || unsaved" @click="confirm">已核对，确认已保存的资料</button>
        <text class="helper">{{ member.ready ? '本人基础资料已完成。' : '尚有基础项目待补充或确认。' }}健康授权和营养安全审核按各自流程办理。</text>
      </view>
      <text v-if="account.householdId && !member && !busy" class="helper">当前家庭没有可维护的本人成员，请使用对应成员邀请完成关联。</text>
      <text class="helper">饮食首页、AI 和商城正在接入真实服务，完成后开放。当前可保存和核对自己的家庭及本人基础资料。</text>
    </template>
  </view>
</template>
<style scoped>
.account-screen{padding-bottom:48rpx}.section{padding:28rpx;margin:24rpx 0}.section .section-title{display:block;margin-bottom:20rpx}.section button{margin-top:16rpx}.helper{display:block;font-size:25rpx;color:#63636b;line-height:1.7;margin:20rpx 0}.choices{display:flex;flex-wrap:wrap;gap:12rpx}.choices button{font-size:25rpx;padding:12rpx 20rpx;background:#eef2ed}.choices .selected{background:#246b50;color:#fff}.error-note{display:block;color:#a13a30;margin:20rpx 0;line-height:1.6}.text-button{background:transparent;font-size:26rpx;color:#246b50}.field-input{margin:20rpx 0}
</style>
