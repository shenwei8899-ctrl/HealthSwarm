<script setup>
import { ref, computed, onMounted } from 'vue'
import { onShow, onHide, onUnload } from '@dcloudio/uni-app'
import AppNavBar from '../components/AppNavBar.vue'
import { wechatAuth } from '../services/wechat-auth.js'
import { request } from '../services/request.js'
import { getSession, sessionRevision } from '../services/session.js'
import { selfMember, basicProfileInput } from '../services/family-onboarding.js'
import { isCommerceEnabled } from '../services/config.js'

const account = ref(null), families = ref([]), member = ref(null), form = ref({})
const familyName = ref(''), invitation = ref(''), error = ref(''), busy = ref(false), uncertain = ref(false)
const healthMembers = ref([]), selectedHealthId = ref(''), healthLink = ref(null)
const healthBusy = ref(false), healthError = ref(''), healthUncertain = ref(false)
const healthDiagnostics = ref(null)
const healthEntryLabels = { consultation: '营养咨询', meal_preview: '单日配餐', blood_glucose_review: '血糖记录回顾',
  blood_lipids_review: '血脂记录回顾', blood_pressure_review: '血压记录回顾', glucose_plan: '控糖计划', multi_day_plan: '多日计划' }
const healthEntries = computed(() => (healthDiagnostics.value?.entries || []).filter(item => healthEntryLabels[item.entry_type]))
function healthEntryText(item) {
  if (item.status === 'available') return '当前可尝试'
  const reasons = { missing_scopes: '需成员授权', consent_required: '需确认数据处理同意', selection_required: '需先选择来源',
    configuration_unavailable: '服务配置未就绪', external_contract_required: '功能尚未开放',
    dependency_not_ready: '服务或专业资料未就绪', self_member_required: '需使用本人健康成员',
    agent_unavailable: '助手尚未开放', skill_unavailable: '助手资料尚未就绪' }
  if (item.reason_code === 'dependency_not_ready' && Array.isArray(item.missing_dependencies)) {
    const runtime = item.missing_dependencies.some(key => ['postgres', 'redis', 'worker'].includes(key))
    const professional = item.missing_dependencies.some(key => ['nutrition', 'rules', 'published_recipes', 'profile_projection'].includes(key))
    if (runtime && professional) return '暂不可用 · 服务及专业资料未就绪'
    if (runtime) return '暂不可用 · 服务暂不可用'
    if (professional) return '暂不可用 · 专业资料未就绪'
  }
  return (item.status === 'needs_input' ? '需补充信息' : '暂不可用') + (reasons[item.reason_code] ? ' · ' + reasons[item.reason_code] : '')
}
function openHealthTask(entry) {
  if (!selectedHealthId.value || !['consultation', 'blood_glucose_review', 'blood_lipids_review', 'blood_pressure_review'].includes(entry?.entry_type) ||
    !(entry.status === 'available' || entry.reason_code === 'consent_required') || healthBusy.value) return
  uni.navigateTo({ url: `/pages/chat/agent?memberId=${encodeURIComponent(selectedHealthId.value)}&taskType=${encodeURIComponent(entry.entry_type)}` })
}
const unsaved = computed(() => {
  if (!member.value) return true
  try { return JSON.stringify(basicProfileInput(form.value)) !== JSON.stringify(basicProfileInput(member.value.profile)) }
  catch { return true }
})
let generation = 0, mountedRead = null
function active(ticket) { return ticket.generation === generation && ticket.revision === sessionRevision() }
function discard() {
  mountedRead = null
  generation++; wechatAuth.cancelPending(); account.value = null; families.value = []; member.value = null; form.value = {}
  invitation.value = ''; familyName.value = ''; error.value = ''; uncertain.value = false; busy.value = false
  healthMembers.value = []; selectedHealthId.value = ''; healthLink.value = null; healthDiagnostics.value = null
  healthBusy.value = false; healthError.value = ''; healthUncertain.value = false
}
async function load() {
  const mine = ++generation
  busy.value = true; error.value = ''; member.value = null; form.value = {}; families.value = []
  healthMembers.value = []; selectedHealthId.value = ''; healthLink.value = null; healthDiagnostics.value = null
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
async function readHealthMembers() {
  if (healthBusy.value || !member.value?.id || !account.value?.householdId) return
  const ticket = { generation, revision: sessionRevision() }
  healthBusy.value = true; healthError.value = ''
  try {
    const { data } = await request({ path: '/api/health/v1/members' })
    if (!active(ticket)) return
    if (!Array.isArray(data)) throw new Error('健康成员列表格式异常')
    healthMembers.value = data.filter(item => item.is_owner === true)
    selectedHealthId.value = ''; healthLink.value = null; healthDiagnostics.value = null; healthUncertain.value = false
  } catch (e) { if (active(ticket)) healthError.value = e.message }
  finally { if (active(ticket)) healthBusy.value = false }
}
async function selectHealthMember(id) {
  if (healthBusy.value || !healthMembers.value.some(item => item.id === id)) return
  const ticket = { generation, revision: sessionRevision() }
  selectedHealthId.value = id; healthLink.value = null; healthDiagnostics.value = null; healthBusy.value = true; healthError.value = ''
  try {
    const { data } = await request({ path: `/api/health/v1/members/${encodeURIComponent(id)}/family-profile-link` })
    if (active(ticket) && selectedHealthId.value === id) { healthLink.value = data; healthUncertain.value = false }
  } catch (e) { if (active(ticket)) healthError.value = e.message }
  finally { if (active(ticket)) healthBusy.value = false }
}
async function readHealthDiagnostics() {
  const id = selectedHealthId.value
  if (healthBusy.value || !id || !healthMembers.value.some(item => item.id === id)) return
  const ticket = { generation, revision: sessionRevision() }
  healthBusy.value = true; healthError.value = ''; healthDiagnostics.value = null
  try {
    const base = `/api/health/v1/members/${encodeURIComponent(id)}`
    const [capabilities, readiness] = await Promise.all([
      request({ path: base + '/capabilities' }), request({ path: base + '/readiness' }),
    ])
    if (!active(ticket) || selectedHealthId.value !== id) return
    if (capabilities.data?.member_id !== id || readiness.data?.capabilities?.member_id !== id || !Array.isArray(readiness.data?.entries)) {
      throw new Error('健康服务返回的成员诊断不一致')
    }
    healthDiagnostics.value = readiness.data
  } catch (e) { if (active(ticket) && selectedHealthId.value === id) healthError.value = e.message }
  finally { if (active(ticket)) healthBusy.value = false }
}
async function createHealthMember() {
  if (healthBusy.value || healthUncertain.value || !member.value?.id || !account.value?.householdId) return
  const ticket = { generation, revision: sessionRevision() }
  healthBusy.value = true; healthError.value = ''
  try {
    const { data } = await request({ path: '/api/health/v1/members', method: 'POST',
      data: { display_name: account.value.accountName || '本人', relationship_label: '本人', authorized: true } })
    if (!active(ticket)) return
    if (!data?.id) throw new Error('健康成员创建结果缺少 ID，请重新读取成员列表')
    await readHealthMembersAfterCreate(ticket, data.id)
  } catch (e) {
    if (!active(ticket)) return
    healthUncertain.value = e.code === 'NETWORK_ERROR' || Number(e.code) >= 500
    healthError.value = healthUncertain.value ? '创建结果暂未确认，请先重新读取健康成员，不要重复创建。' : e.message
  } finally { if (active(ticket)) healthBusy.value = false }
}
async function readHealthMembersAfterCreate(ticket, id) {
  const { data } = await request({ path: '/api/health/v1/members' })
  if (!active(ticket)) return
  if (!Array.isArray(data) || !data.some(item => item.id === id && item.is_owner === true)) throw new Error('新建成员尚未回读到，请重新读取成员列表')
  healthMembers.value = data.filter(item => item.is_owner === true)
  selectedHealthId.value = id; healthLink.value = null; healthDiagnostics.value = null; healthUncertain.value = false
}
async function linkSelfProfile() {
  const id = selectedHealthId.value, familyId = account.value?.householdId, sourceId = member.value?.id
  if (healthBusy.value || healthUncertain.value || !id || !familyId || !sourceId) return
  if (healthLink.value?.source_member_id && (healthLink.value.source_member_id !== sourceId || healthLink.value.family_id !== familyId)) {
    healthError.value = '这个健康成员已关联其他档案，请核对后重新选择'; return
  }
  const ticket = { generation, revision: sessionRevision() }
  healthBusy.value = true; healthError.value = ''
  try {
    await request({ path: `/api/health/v1/members/${encodeURIComponent(id)}/family-profile-link`, method: 'POST',
      data: { family_id: familyId, source_member_id: sourceId, confirmed_identity: true } })
    const { data } = await request({ path: `/api/health/v1/members/${encodeURIComponent(id)}/family-profile-link` })
    if (!active(ticket) || selectedHealthId.value !== id) return
    if (data?.family_id !== familyId || data?.source_member_id !== sourceId) throw new Error('关联回读与当前本人不一致')
    healthLink.value = data; healthUncertain.value = false
  } catch (e) {
    if (!active(ticket)) return
    healthUncertain.value = e.code === 'NETWORK_ERROR' || Number(e.code) >= 500
    healthError.value = healthUncertain.value ? '关联结果暂未确认，请重新读取该健康成员的关联状态。' : e.message
  } finally { if (active(ticket)) healthBusy.value = false }
}
function openFamilyArchives() { uni.navigateTo({ url: '/pages/family-shared/index' }) }
function logout() { discard(); wechatAuth.logout(); uni.reLaunch({ url: '/pages/index/index' }) }
function showLoad() {
  if (mountedRead) return mountedRead
  const task = load(); mountedRead = task
  task.finally(() => { if (mountedRead === task) mountedRead = null })
  return task
}
onMounted(showLoad); onShow(showLoad); onHide(discard); onUnload(discard)
</script>
<template><view class="self-details"><text v-if="error" class="error-note">{{error}}</text><button class="secondary-button" :disabled="busy" @click="load">重新读取本人资料</button><text v-if="!member&&!busy" class="helper">尚未读到可维护的本人成员，请先保存家庭健康档案。</text>      <view v-if="member" class="card section"><text class="section-title">本人基础资料</text>
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
      <view v-if="member" class="card section"><text class="section-title">关联本人健康档案</text>
        <text class="helper">请明确选择属于本人的健康档案，核对后再关联。</text>
        <text class="helper">基础资料尚未齐全也可核对本人关联与普通科普咨询；个体化建议仍由服务端分别检查当前资料、授权和专业依据。</text>
        <button class="secondary-button" :disabled="healthBusy" @click="readHealthMembers">{{ healthBusy ? '正在读取…' : '读取我的健康档案' }}</button>
        <text v-if="healthError" class="error-note">{{ healthError }}</text>
        <button v-for="item in healthMembers" :key="item.id" class="secondary-button" :disabled="healthBusy" @click="selectHealthMember(item.id)">{{ item.display_name }} · {{ item.relationship_label }}{{ selectedHealthId === item.id ? ' · 已选择' : '' }}</button>
        <text v-if="selectedHealthId && healthLink?.source_member_id" class="helper">当前关联来源：{{ healthLink.source_member_id === member.id && healthLink.family_id === account.householdId ? '已关联这个家庭的本人档案' : '其他档案，请勿覆盖' }}</text>
        <button v-if="selectedHealthId && !healthLink?.source_member_id" class="primary-button" :disabled="healthBusy || healthUncertain || !healthLink" @click="linkSelfProfile">确认这两个成员都是我，并建立关联</button>
        <button v-if="selectedHealthId" class="secondary-button" :disabled="healthBusy" @click="readHealthDiagnostics">查看可用的健康服务</button>
        <text v-if="healthDiagnostics" class="helper">以下状态来自当前服务端，只用于提示；实际提交时仍会重新核对授权与资料。</text>
        <view v-for="entry in healthEntries" :key="entry.entry_type">
          <text class="helper">{{ healthEntryLabels[entry.entry_type] }}：{{ healthEntryText(entry) }}</text>
          <button v-if="(entry.status === 'available' || entry.reason_code === 'consent_required') && ['consultation', 'blood_glucose_review', 'blood_lipids_review', 'blood_pressure_review'].includes(entry.entry_type)" class="secondary-button" :disabled="healthBusy" @click="openHealthTask(entry)">进入{{ healthEntryLabels[entry.entry_type] }}</button>
        </view>
        <button class="secondary-button" :disabled="healthBusy || healthUncertain" @click="createHealthMember">为我创建健康档案</button>
        <text v-if="healthUncertain" class="helper">写入结果未确定，请先回读成员或关联状态。</text>
      </view>
</view></template>
<style scoped>
.account-screen{padding-bottom:48rpx}.section{padding:28rpx;margin:24rpx 0}.section .section-title{display:block;margin-bottom:20rpx}.section button{margin-top:16rpx}.helper{display:block;font-size:25rpx;color:#63636b;line-height:1.7;margin:20rpx 0}.choices{display:flex;flex-wrap:wrap;gap:12rpx}.choices button{font-size:25rpx;padding:12rpx 20rpx;background:#eef2ed}.choices .selected{background:#246b50;color:#fff}.error-note{display:block;color:#a13a30;margin:20rpx 0;line-height:1.6}.text-button{background:transparent;font-size:26rpx;color:#246b50}.field-input{margin:20rpx 0}
</style>
