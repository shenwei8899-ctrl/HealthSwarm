<script setup>
import { sessionRevision } from '../../services/session.js'
import { scopedStorage } from '../../services/storage.js'
import AppNavBar from '../../components/AppNavBar.vue'
import { computed, nextTick, ref, watch } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import MemberFields from '../../components/MemberFields.vue'
import OnboardingHealthFields from '../../components/OnboardingHealthFields.vue'
import { backHome, getProfile, newMember, normalizeMember, normalizeProfile, saveProfile } from '../../utils/profile.js'
import { dataWarnings } from '../../utils/health.js'
import { isMockMode } from '../../services/config.js'
import { loadCloudProfile, saveCloudProfile, readCloudReportStatus } from '../../services/cloud-profile.js'
const cloudLoading=ref(!isMockMode),cloudError=ref(''),cloudSaving=ref(false),cloudLoaded=ref(isMockMode)
let initialProfile = getProfile()
if (!initialProfile.members.length || !scopedStorage.getStorageSync('family-profile-v2') && !scopedStorage.getStorageSync('frontend-onboarding-progress-v1')) {
  const self = normalizeMember({ ...newMember(0), name: '我', relation: '本人', age: '', claimedBy: 'creator' })
  initialProfile = normalizeProfile({ householdName: '我的家', usageMode: '个人使用', members: [self], defaultDiners: [self.id], goals: [], tastes: [], memories: [] })
}
const profile = ref(JSON.parse(JSON.stringify(initialProfile)))
const step = ref(0), memberIndex = ref(0), invited = ref(false)
let completed = false
const familyDiners = ref([...profile.value.defaultDiners])
const current = computed(() => profile.value.members[memberIndex.value])
const self = computed(() => profile.value.members.find(m => m.relation === '本人') || profile.value.members[0])
const visibleMembers = computed(() => invited.value ? [current.value] : profile.value.usageMode === '个人使用' ? [self.value] : profile.value.members)
const dinerCount = computed(() => profile.value.defaultDiners.length)
const copy = [
  ['先认识每位成员', '添加需要照顾的人，资料可以逐步补充。'],
  ['饮食目标与健康', '了解你的需要，逐步完善资料。'],
  ['重要的限制，分开记录', '未填写不等于没有，记录过敏、不耐受、忌口和医嘱。'],
]
watch(step, () => nextTick(() => uni.pageScrollTo?.({ scrollTop: 0, duration: 0 })))

async function readCloud() {
    cloudLoading.value=true;cloudError.value=''
    try {
      profile.value = await loadCloudProfile()
      const policy=profile.value.analysisPolicy
      const draft = scopedStorage.getStorageSync('frontend-onboarding-progress-v1')
      if (draft?.profile?.householdId === profile.value.householdId && draft.profile.familyVersion === profile.value.familyVersion) {
        profile.value = normalizeProfile(draft.profile); step.value = draft.step || 0
        profile.value.analysisPolicy=policy
      }
      if (!profile.value.defaultDiners.length) profile.value.defaultDiners = profile.value.members.map(member=>member.id)
      familyDiners.value=[...profile.value.defaultDiners]
      syncDiners()
      cloudLoaded.value=true
    } catch(error) { cloudError.value=error.message }
    finally { cloudLoading.value=false }
}
onLoad(async options => {
  if (!isMockMode) { await readCloud(); return }
  if (options.member) {
    invited.value = true
    memberIndex.value = Math.max(0, profile.value.members.findIndex(m => String(m.id) === options.member))
    return
  }
  const progress = scopedStorage.getStorageSync('frontend-onboarding-progress-v1')
  if (progress?.profile?.members?.length) {
    profile.value = normalizeProfile(progress.profile)
    // Old steps 0/1 become basic information; old steps 2/3 become steps 1/2.
    step.value = Math.max(0, Math.min(2, progress.version === 2 ? progress.step || 0 : (progress.step || 0) - 1))
    memberIndex.value = Math.max(0, Math.min(profile.value.members.length - 1, progress.memberIndex || 0))
    familyDiners.value = progress.familyDiners || [...profile.value.defaultDiners]
  }
  syncDiners()
  if (profile.value.usageMode === '个人使用') selectMember(self.value.id)
})
watch([profile, step, memberIndex, familyDiners], () => {
  if (!invited.value && !completed) scopedStorage.setStorageSync('frontend-onboarding-progress-v1', {
    version: 2, profile: profile.value, step: step.value, memberIndex: memberIndex.value, familyDiners: familyDiners.value,
  })
}, { deep: true })
onShow(async () => {
  if(!isMockMode){if(!cloudLoaded.value)return;const revision=sessionRevision();const rows=await Promise.allSettled(profile.value.members.filter(m=>m.healthMemberId).map(async m=>({id:m.id,healthId:m.healthMemberId,status:await readCloudReportStatus(m.healthMemberId)})));if(revision!==sessionRevision())return;for(const row of rows){if(row.status!=='fulfilled')continue;const m=profile.value.members.find(m=>m.id===row.value.id&&m.healthMemberId===row.value.healthId);if(m)m.reportStatus=row.value.status}return}
  const fresh = getProfile()
  for (const m of profile.value.members) {
    const updated = fresh.members.find(n => n.id === m.id)
    if (updated) { m.reports = updated.reports; m.reportStatus = updated.reportStatus }
  }
})

function syncDiners() {
  familyDiners.value = [...new Set(familyDiners.value)].filter(id => profile.value.members.some(m => m.id === id))
  profile.value.defaultDiners = profile.value.usageMode === '个人使用' ? [self.value.id] : [...familyDiners.value]
  if (!profile.value.defaultDiners.length) profile.value.defaultDiners = [self.value.id]
  profile.value.sharedDinerCount = profile.value.defaultDiners.length
}
function mode(value) {
  profile.value.usageMode = value
  syncDiners()
  if (value === '个人使用') selectMember(self.value.id)
}
function selectMember(id) { memberIndex.value = profile.value.members.findIndex(m => m.id === id) }
function add() {
  const member = normalizeMember({ ...newMember(profile.value.members.length), age: '' })
  while (profile.value.members.some(m => m.id === member.id)) member.id++
  profile.value.members.push(member)
  selectMember(member.id)
}
function toggleDiner(id) {
  const selected = profile.value.defaultDiners
  if (selected.includes(id) && selected.length === 1) return uni.showToast({ title: '请至少选择一位就餐成员', icon: 'none' })
  familyDiners.value = selected.includes(id) ? selected.filter(value => value !== id) : [...selected, id]
  syncDiners()
}
async function commit() {
  if(cloudSaving.value||cloudLoading.value||!cloudLoaded.value)return
  if (!invited.value) syncDiners()
  if(isMockMode)saveProfile(profile.value)
  if (step.value < 2) { step.value++; return }
  if(!isMockMode){
    cloudSaving.value=true;cloudError.value=''
    try { profile.value=await saveCloudProfile(profile.value) }
    catch(error){cloudError.value=error.message;return}
    finally{cloudSaving.value=false}
  }
  if (!invited.value) {
    completed = true
    scopedStorage.setStorageSync('frontend-onboarded-v1', true)
    scopedStorage.setStorageSync('frontend-onboarding-progress-v1', null)
  }
  uni.redirectTo({ url: invited.value ? '/pages/profile/index' : '/pages/chat/index?from=onboarding' })
}
function next() {
  if(cloudSaving.value||cloudLoading.value||cloudError.value&&!profile.value.householdId)return
  for (const member of visibleMembers.value) {
    const message = !member.name.trim() ? '请填写姓名／称呼' : step.value === 1 && member.healthStatus === 'set' &&
      (!member.conditions.length || member.conditions.includes('其他') && !member.otherCondition.trim()) ? '请补充具体基础病' : ''
    if (message) { selectMember(member.id); uni.showToast({ title: message, icon: 'none' }); return }
  }
  const warnings = visibleMembers.value.flatMap(m => dataWarnings(m).map(w => `${m.name}：${w}`))
  if (warnings.length) {
    uni.showModal({ title: '请复核档案信息', content: warnings.join('；') + '。此提示不是医疗诊断。', cancelText: '返回修改', confirmText: '继续保存', success: result => { if (result.confirm) commit() } })
    return
  }
  commit()
}
</script>
<template>
  <view v-if="cloudLoading" class="screen"><text class="safe-note">正在读取云端档案…</text></view>
  <view v-if="cloudError" class="cloud-onboarding-error" role="alert"><text>{{cloudError}}</text><button @click="cloudLoaded ? next() : readCloud()">{{cloudLoaded?'重试保存':'重新读取档案'}}</button></view>
  <view v-show="!cloudLoading && cloudLoaded" class="screen onboarding-screen" :class="{ 'health-step': step === 1 }">
    <AppNavBar><view class="nav-row"><button class="icon-button" @click="step > 0 ? step-- : backHome()">‹</button><text class="nav-title">{{ invited ? '受邀成员建档' : '家庭建档' }}</text><text v-if="step !== 1" class="step-count">{{ step + 1 }} / 3</text></view></AppNavBar>
    <text v-if="step === 1" class="step-caption">第 2 步，共 3 步</text>
    <view class="progress"><view :style="{ width: (step + 1) / 3 * 100 + '%' }"></view></view>
    <view class="question-head"><text class="display-title">{{ copy[step][0] }}</text><text class="helper">{{ invited && step === 0 ? '先核对你的成员信息，资料可以逐步补充。' : copy[step][1] }}</text></view>
    <template v-if="step === 0 && !invited">
      <text class="label">使用方式</text>
      <view class="mode-grid"><button v-for="item in [{ value: '个人使用', label: '只为自己' }, { value: '家庭使用', label: '自己和家人' }]" :key="item.value" :class="{ active: profile.usageMode === item.value }" @click="mode(item.value)">{{ item.label }}</button></view>
    </template>
    <text class="current">{{ step === 1 ? (invited ? '为谁填写：' + current.name : '为谁填写') : '正在填写：' + (current.name || '未命名成员') }}</text>
    <view v-if="!invited" class="member-tabs">
      <button v-for="m in visibleMembers" :key="m.id" :class="{ active: current.id === m.id }" @click="selectMember(m.id)">{{ m.name || '未命名成员' }}</button>
      <button v-if="profile.usageMode === '家庭使用' && step !== 1" class="add-member" @click="add">＋ 添加家人</button>
    </view>
    <OnboardingHealthFields v-if="step === 1" :key="current.id" :member="current" />
    <MemberFields v-else :key="current.id" :member="current" :sections="step === 0 ? ['basic'] : ['restrictions', 'reports']"/>
    <view v-if="step === 0 && !invited" class="diner-section">
      <template v-if="profile.usageMode === '家庭使用'">
        <text class="label">通常一起吃饭的是哪些人？</text>
        <view class="diner-choices"><button v-for="m in profile.members" :key="m.id" role="checkbox" :aria-checked="profile.defaultDiners.includes(m.id)" :class="{ selected: profile.defaultDiners.includes(m.id) }" @click="toggleDiner(m.id)"><text class="checkmark">{{ profile.defaultDiners.includes(m.id) ? '✓' : '' }}</text><text>{{ m.name || '未命名成员' }}</text></button></view>
      </template>
      <text class="helper diner-summary">默认按 {{ dinerCount }} 人安排饮食，每餐可以单独调整。</text>
    </view>
    <text v-if="step === 1" class="later-note">资料可稍后补充</text>
    <text v-if="!isMockMode && step===2 && profile.analysisPolicy" class="analysis-policy">点击“保存并分析”，将使用上述成员档案安排三餐。处理方：{{profile.analysisPolicy.processor}}；政策版本：{{profile.analysisPolicy.policy_version}}。</text>
    <button class="primary-button next" :disabled="cloudSaving||cloudLoading" @click="next"><text>{{ step === 2 ? (cloudSaving ? '正在保存…' : !isMockMode && profile.analysisPolicy ? '保存并分析今日饮食' : invited ? '保存，进入家庭' : '完成建档，进入首页') : '保存并继续' }}</text><text>{{ step === 1 ? '›' : '→' }}</text></button>
    <text v-if="isMockMode" class="demo-label">前端体验版 · 资料保存于本机，请勿输入真实病历</text>
  </view>
</template>
<style scoped>
.health-step .step-caption{display:block;font-size:25rpx;color:#86868f;margin:18rpx 0 12rpx}
.health-step .progress{height:7rpx;background:#dcdce2;margin:0}
.health-step .progress view{background:#1d1d1f}
.health-step .question-head{margin:40rpx 0 30rpx;gap:10rpx}
.health-step .question-head .display-title{font-size:44rpx;font-weight:600;letter-spacing:0}
.health-step .question-head .helper{font-size:27rpx;color:#92929c}
.health-step .current{font-size:27rpx;color:#7c7c85;margin:0 0 14rpx}
.health-step .member-tabs{gap:14rpx;margin:0 0 30rpx}
.health-step .member-tabs button{min-width:156rpx;min-height:60rpx;padding:12rpx 26rpx;background:#fff;border:1rpx solid #dcdce3;border-radius:14rpx;color:#1d1d1f;font-size:28rpx}
.health-step .member-tabs button.active{background:#1d1d1f!important;border-color:#1d1d1f;color:#fff!important}
.health-step .later-note{display:block;text-align:center;color:#92929c;font-size:23rpx;margin:24rpx 0 12rpx}
.health-step .next{margin-top:0;border-radius:18rpx;min-height:72rpx;font-size:28rpx}
.health-step .demo-label{font-size:20rpx;margin-top:20rpx}
.onboarding-screen :deep(.field-card > .section-title){display:block;margin-bottom:18rpx}
.onboarding-screen :deep(.field-card .label){display:block}
.onboarding-screen{padding-bottom:50rpx}.step-count{font-size:25rpx;color:#63636b;flex-shrink:0}.progress{height:6rpx;background:#dcdce2;margin:16rpx 0;border-radius:99rpx}.progress view{height:100%;background:#1d1d1f;border-radius:99rpx}.question-head{display:flex;flex-direction:column;gap:12rpx;margin:34rpx 0}.question-head .display-title{font-size:48rpx}.helper{font-size:25rpx;line-height:1.7;color:#92929c;display:block}.question-head .helper{margin:0}.label{display:block;font-size:28rpx;font-weight:500}.mode-grid,.member-tabs{display:flex;flex-wrap:wrap;gap:14rpx;margin:18rpx 0 28rpx}.mode-grid button,.member-tabs button{padding:18rpx 24rpx;background:#fff;border:1rpx solid #dcdce3;border-radius:14rpx;font-size:26rpx;color:#1d1d1f}.active{background:#1d1d1f!important;border-color:#1d1d1f!important;color:#fff!important}.member-tabs .add-member{background:transparent;border:1rpx dashed #dcdce3}.current{display:block;font-size:25rpx;color:#7c7c85;margin:28rpx 0 16rpx}.diner-section{margin:30rpx 0}.diner-choices{display:flex;flex-wrap:wrap;gap:18rpx;margin:20rpx 0}.diner-choices button{display:flex;align-items:center;gap:12rpx;padding:12rpx 8rpx;font-size:27rpx}.checkmark{display:flex;align-items:center;justify-content:center;width:36rpx;height:36rpx;border:2rpx solid #9a9a9c;border-radius:9rpx;font-size:26rpx;color:#fff}.selected .checkmark{background:#1d1d1f;border-color:#1d1d1f}.diner-summary{margin-top:16rpx}.next{margin-top:30rpx}.secondary-button{margin-top:16rpx}.demo-label{margin-top:28rpx;font-size:22rpx;text-align:center}

/* MemberFields is shared with profile pages; the neutral palette belongs only to onboarding. */
.onboarding-screen :deep(.field-card){background:#fff;border-color:#e7e7ed;border-radius:24rpx;color:#1d1d1f}
.onboarding-screen :deep(.field-card > .section-title){font-size:34rpx;font-weight:600}
.onboarding-screen :deep(.field-input){background:#f5f5f7;border-color:#e3e3e9;color:#1d1d1f}
.onboarding-screen :deep(.helper){color:#92929c}
.onboarding-screen :deep(.field-row){color:#1d1d1f;border-color:#e7e7ed}
.onboarding-screen :deep(.field-row > view > text:first-child){font-weight:600}
.onboarding-screen :deep(.field-row > view > text:last-child){color:#86868f}
.onboarding-screen :deep(.field-row > text){color:#8e8e93}
.onboarding-screen :deep(.chips button){background:#fff;border:1rpx solid #e3e3e9;color:#1d1d1f;border-radius:14rpx}
.onboarding-screen :deep(.chips button.active){background:#1d1d1f;border-color:#1d1d1f;color:#fff}
.onboarding-screen :deep(.custom-row button){color:#1d1d1f}
.onboarding-screen :deep(.text-area){background:#f5f5f7;border-color:#e3e3e9;color:#1d1d1f}
.onboarding-screen :deep(.secondary-button){background:#fff;border-color:#dedee3;color:#1d1d1f}
</style>

<style scoped>.cloud-onboarding-error{padding:28rpx;margin:24rpx 32rpx;background:#eeeef1;border-radius:20rpx;color:#444;font-size:27rpx;line-height:1.7}.cloud-onboarding-error button{margin-top:16rpx;text-decoration:underline;color:#222}.onboarding-screen :deep(.secondary-button){color:#333}</style>

<style scoped>.analysis-policy{display:block;font-size:23rpx;color:#888;line-height:1.8;margin:24rpx 0;overflow-wrap:anywhere}</style>
