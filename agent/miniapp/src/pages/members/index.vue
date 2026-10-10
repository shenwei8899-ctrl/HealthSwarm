<script setup>
import { computed, ref } from 'vue'
import { onShow, onHide, onUnload } from '@dcloudio/uni-app'
import { client } from '../../services/runtime.js'
import { familyChoices, familyMemberChoices, eligibleHealthMembers, profileLinkSummary, basicProfileSummary } from '../../ui/member-projection.js'

const account = ref(null)
const families = ref([])
const healthMembers = ref([])
const members = ref([])
const familyId = ref('')
const sourceId = ref('')
const healthId = ref('')
const loading = ref(false)
const familyLoading = ref(false)
const linkLoading = ref(false)
const saving = ref(false)
const error = ref('')
const familyError = ref('')
const linkError = ref('')
const link = ref(null)
const linkKnown = ref(false)
const profile = ref(null)
const confirmed = ref(false)
const success = ref('')
let visible = false
let epoch = 0
let familyEpoch = 0
let healthEpoch = 0
const selfMembers = computed(() => members.value.filter(member => member.is_self && member.is_active))
const selectedSource = computed(() => selfMembers.value.find(member => member.id === sourceId.value))
const selectedHealth = computed(() => healthMembers.value.find(member => member.id === healthId.value))
const canLink = computed(() => selectedSource.value && selectedHealth.value && confirmed.value && linkKnown.value && !link.value?.source_member_id && !linkError.value && !loading.value && !familyLoading.value && !linkLoading.value && !saving.value)
const canConsult = computed(() => selectedHealth.value && linkKnown.value && link.value?.member_id === healthId.value
  && link.value?.source_member_id && link.value?.family_id && !error.value && !linkError.value
  && !loading.value && !linkLoading.value && !saving.value)

function clearData() {
  epoch += 1; familyEpoch += 1; healthEpoch += 1
  families.value = []; healthMembers.value = []; members.value = []
  familyId.value = ''; sourceId.value = ''; healthId.value = ''
  link.value = null; profile.value = null; linkKnown.value = false; confirmed.value = false
  error.value = ''; familyError.value = ''; linkError.value = ''; success.value = ''
  loading.value = false; familyLoading.value = false; linkLoading.value = false; saving.value = false
}

const unsubscribe = client.subscribeSession(session => {
  clearData()
  account.value = session ? { uid: session.uid, username: session.username } : null
  if (!session && visible) uni.reLaunch({ url: '/pages/login/index' })
})

function guard(marker, revision) {
  return visible && marker === epoch && revision === client.sessionRevision && Boolean(client.getSession())
}

function message(failure) { return failure.message || '服务暂不可用，请重试' }

async function reload() {
  clearData()
  const session = client.getSession()
  if (!session) { account.value = null; uni.reLaunch({ url: '/pages/login/index' }); return }
  account.value = { uid: session.uid, username: session.username }
  const marker = epoch, revision = client.sessionRevision
  loading.value = true
  try {
    const [familyRows, healthRows] = await Promise.all([client.listFamilies(), client.listHealthMembers()])
    if (!guard(marker, revision)) return
    families.value = familyChoices(familyRows)
    healthMembers.value = eligibleHealthMembers(healthRows)
  } catch (failure) {
    if (guard(marker, revision) && failure.code !== 'stale_session') error.value = message(failure)
  } finally {
    if (guard(marker, revision)) loading.value = false
  }
}

async function chooseFamily(id) {
  if (saving.value || loading.value) return
  const request = ++familyEpoch, marker = epoch, revision = client.sessionRevision
  familyId.value = id; sourceId.value = ''; members.value = []; confirmed.value = false; familyError.value = ''; success.value = ''
  familyLoading.value = true
  try {
    const result = await client.getFamily(id)
    if (!guard(marker, revision) || request !== familyEpoch) return
    members.value = familyMemberChoices(result)
  } catch (failure) {
    if (guard(marker, revision) && request === familyEpoch && failure.code !== 'stale_session') familyError.value = message(failure)
  } finally {
    if (guard(marker, revision) && request === familyEpoch) familyLoading.value = false
  }
}

function chooseSource(id) {
  if (saving.value || !selfMembers.value.some(member => member.id === id)) return
  sourceId.value = id; confirmed.value = false; success.value = ''
}

async function readSelectedHealth() {
  if (!selectedHealth.value || saving.value) return
  const id = healthId.value, request = ++healthEpoch, marker = epoch, revision = client.sessionRevision
  link.value = null; profile.value = null; linkKnown.value = false; confirmed.value = false; linkError.value = ''; success.value = ''
  linkLoading.value = true
  try {
    const mapping = await client.readProfileLink(id)
    if (!guard(marker, revision) || request !== healthEpoch || id !== healthId.value) return
    link.value = profileLinkSummary(mapping)
    linkKnown.value = true
    const state = await client.readFamilyProfile(id)
    if (!guard(marker, revision) || request !== healthEpoch || id !== healthId.value) return
    profile.value = basicProfileSummary(state)
  } catch (failure) {
    if (guard(marker, revision) && request === healthEpoch && failure.code !== 'stale_session') linkError.value = message(failure)
  } finally {
    if (guard(marker, revision) && request === healthEpoch) linkLoading.value = false
  }
}

function chooseHealth(id) {
  if (saving.value || loading.value || !healthMembers.value.some(member => member.id === id)) return
  healthId.value = id
  readSelectedHealth()
}

function identityChanged(event) { confirmed.value = event.detail.value.includes('identity') }

async function associate() {
  if (!canLink.value) return
  const marker = epoch, revision = client.sessionRevision, request = ++healthEpoch
  const target = healthId.value, source = sourceId.value, family = familyId.value
  saving.value = true; linkError.value = ''; success.value = ''; confirmed.value = false
  try {
    await client.linkProfile(target, { family_id: family, source_member_id: source, confirmed_identity: true })
    if (!guard(marker, revision) || request !== healthEpoch) return
    linkKnown.value = false
    const mapping = await client.readProfileLink(target)
    if (!guard(marker, revision) || request !== healthEpoch) return
    link.value = profileLinkSummary(mapping)
    linkKnown.value = true
    if (link.value.source_member_id !== source || link.value.family_id !== family) throw new Error('关联回读未匹配所选身份，请重新读取确认')
    const state = await client.readFamilyProfile(target)
    if (!guard(marker, revision) || request !== healthEpoch) return
    profile.value = basicProfileSummary(state)
    success.value = '本人关联已保存，并已从服务端回读。'
  } catch (failure) {
    if (guard(marker, revision) && request === healthEpoch && failure.code !== 'stale_session') linkError.value = message(failure)
  } finally {
    if (guard(marker, revision) && request === healthEpoch) saving.value = false
  }
}

// 会话订阅统一清理与跳转，避免退出按钮再发起一次并发 reLaunch。
function logout() { client.logout() }
function openConsultation() {
  if (canConsult.value) uni.navigateTo({ url: `/pages/consultation/index?member_id=${encodeURIComponent(healthId.value)}` })
}
function openMealPlans() {
  if (canConsult.value) uni.navigateTo({ url: `/pages/meal-plans/index?member_id=${encodeURIComponent(healthId.value)}` })
}
onShow(() => { visible = true; reload() })
onHide(() => { visible = false; clearData(); account.value = null })
onUnload(() => { unsubscribe(); clearData(); account.value = null })
</script>

<template>
  <view class="screen access-screen">
    <AppNavBar><view class="nav-row"><AppIcon name="family" :size="36" /><text class="nav-title">本人成员接入</text><view /></view></AppNavBar>
    <view v-if="account" class="account-bar card access-card"><view><text>{{ account.username || '当前账号' }}</text><text class="account-id">UID：{{ account.uid }}</text></view><button class="text-button" @click="logout">退出账号</button></view>
    <view class="page-heading"><text class="display-title">连接你的本人档案</text><text class="subtitle">选择家庭里的本人关系与本人健康成员，再确认二者属于你。关联沿用服务端的身份与授权校验。</text></view>
    <button class="secondary-button" :disabled="saving" @click="reload">{{ loading ? '重新读取中…' : '重新读取家庭与成员' }}</button>
    <text v-if="loading" class="status-loading">正在读取当前账号的家庭与健康成员…</text>
    <view v-if="error" class="error-box" role="alert"><text>{{ error }}</text><text>请重试读取，或联系管理员核对账号所属部门及权限。</text></view>
    <template v-if="!loading && !error && account">
      <view class="card access-card">
        <text class="section-title">1. 选择已有家庭</text>
        <text v-if="!families.length" class="body-copy">当前账号没有可访问家庭。请联系管理员，或先在已有后台创建家庭、接受本人邀请。</text>
        <view v-else class="choice-list"><button v-for="family in families" :key="family.id" class="choice-button" :class="{ selected: familyId === family.id }" :disabled="saving" @click="chooseFamily(family.id)"><view class="choice-indicator" /><view class="choice-copy"><text>{{ family.name }}</text><text class="choice-detail">{{ family.is_owner ? '家庭管理员' : '家庭成员' }}</text></view></button></view>
        <text v-if="familyLoading" class="status-loading">正在读取所选家庭关系…</text>
        <view v-if="familyError" class="error-box" role="alert"><text>{{ familyError }}</text><button class="text-button" @click="chooseFamily(familyId)">重试读取家庭</button></view>
        <template v-if="familyId && !familyLoading && !familyError">
          <text class="field-label">家庭关系</text>
          <view v-for="member in members" :key="member.id" class="member-row"><text>{{ member.name }}</text><text class="member-relation">{{ member.relationship }}{{ member.is_self ? ' · 当前账号本人' : '' }}</text></view>
          <text v-if="!selfMembers.length" class="body-copy">此家庭没有当前账号已认领的本人关系，请先在后台核对或接受本人邀请。</text>
          <view v-else class="choice-list"><button v-for="member in selfMembers" :key="member.id" class="choice-button" :class="{ selected: sourceId === member.id }" :disabled="saving || Boolean(link?.source_member_id)" @click="chooseSource(member.id)"><view class="choice-indicator" /><view class="choice-copy"><text>选择 {{ member.name }} · 本人</text><text class="choice-detail">家庭成员 ID：{{ member.id }}</text></view></button></view>
        </template>
      </view>
      <view class="card access-card">
        <text class="section-title">2. 选择本人健康成员</text>
        <text class="body-copy">仅显示当前账号拥有且具备档案读取、编辑权限的本人健康成员。</text>
        <text v-if="!healthMembers.length" class="notice">没有可用于关联的本人健康成员。请联系管理员或先在已有健康后台准备本人对象及权限。</text>
        <view v-else class="choice-list"><button v-for="member in healthMembers" :key="member.id" class="choice-button" :class="{ selected: healthId === member.id }" :disabled="saving" @click="chooseHealth(member.id)"><view class="choice-indicator" /><view class="choice-copy"><text>{{ member.display_name }} · 本人</text><text class="choice-detail">健康成员 ID：{{ member.id }}</text></view></button></view>
        <text v-if="linkLoading" class="status-loading">正在读取真实关联与基础档案状态…</text>
        <view v-if="linkError" class="error-box" role="alert"><text>{{ linkError }}</text><button class="text-button" :disabled="saving || linkLoading" @click="readSelectedHealth">重新读取关联</button></view>
        <template v-if="linkKnown && !linkLoading">
          <view v-if="link?.source_member_id" class="notice"><text>已有本人关联，不能改绑。</text><view class="result-row"><text class="result-label">家庭 ID</text><text>{{ link.family_id }}</text></view><view class="result-row"><text class="result-label">家庭成员 ID</text><text>{{ link.source_member_id }}</text></view><view class="result-row"><text class="result-label">健康成员 ID</text><text>{{ link.member_id }}</text></view></view>
          <text v-else class="body-copy">此健康成员尚未关联家庭档案。</text>
          <view v-if="profile" class="result-row"><text class="result-label">基础档案状态</text><text>{{ profile.description }}</text><text v-if="profile.confirmed_version !== null">本人确认版本：{{ profile.confirmed_version }}</text></view>
          <button v-if="canConsult" class="primary-button" @click="openConsultation">进入本人营养咨询</button>
          <button v-if="canConsult" class="secondary-button" @click="openMealPlans">查看与安排本人餐单</button>
        </template>
      </view>
      <view v-if="healthId && linkKnown && !link?.source_member_id" class="card access-card">
        <text class="section-title">3. 确认身份并关联</text>
        <text class="body-copy">{{ selectedSource && selectedHealth ? '已选择：' + selectedSource.name + ' 与 ' + selectedHealth.display_name : '请分别选择家庭中的本人关系与本人健康成员。' }}</text>
        <checkbox-group @change="identityChanged"><label class="identity-confirm"><checkbox value="identity" :checked="confirmed" :disabled="saving || linkLoading || !selectedSource" color="#246b50" /><text>我确认所选家庭成员与健康成员均为我本人，并同意建立这一身份关联。</text></label></checkbox-group>
        <button class="primary-button" :disabled="!canLink" @click="associate">{{ saving ? '正在保存并回读…' : '确认本人身份并关联' }}</button>
      </view>
      <text v-if="success" class="success-note">{{ success }}</text>
      <text class="safe-note">身份关联与基础档案状态独立保存。完整专业档案、营养安全规则及模型处理同意需在各自流程中完成。</text>
    </template>
  </view>
</template>
