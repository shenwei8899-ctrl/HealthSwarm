<script setup>
import { sessionRevision } from '../../services/session.js'
import { scopedStorage, storageScope } from '../../services/storage.js'
import AppNavBar from '../../components/AppNavBar.vue'
import { computed, nextTick, ref, watch } from 'vue'
import { onLoad, onShow, onUnload } from '@dcloudio/uni-app'
import MemberFields from '../../components/MemberFields.vue'
import OnboardingBasics from '../../components/OnboardingBasics.vue'
import OnboardingHealthFields from '../../components/OnboardingHealthFields.vue'
import { backHome, getProfile, newMember, normalizeMember, normalizeProfile, saveProfile } from '../../utils/profile.js'
import { dataWarnings } from '../../utils/health.js'
import { onboardingIssue } from '../../utils/onboarding-validation.js'
import { isMockMode } from '../../services/config.js'
import { loadCloudProfile, saveCloudProfile, readCloudReportStatus } from '../../services/cloud-profile.js'
const cloudLoading=ref(!isMockMode),cloudError=ref(''),cloudSaving=ref(false),cloudLoaded=ref(isMockMode)
const cloudErrorCode = ref(null)
const conflictDraft=ref(null),showConflictDraft=ref(false)
let draftStorageKey = storageScope() + 'frontend-onboarding-progress-v1'
let pageScope=storageScope()
let readEpoch=0, alive=true
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
  ['先认识每位成员', '更好地为你和家人定制饮食建议。'],
  ['饮食目标与健康', '帮你安排更合适的三餐。'],
  ['重要的限制，\n分开记录', '帮你避开不适合的食物。'],
]
watch(step, () => nextTick(() => uni.pageScrollTo?.({ scrollTop: 0, duration: 0 })))

async function readCloud(restoreDraft = true) {
    const mine=++readEpoch
    cloudLoading.value=true;cloudError.value='';cloudErrorCode.value=null
    try {
      const loaded = await loadCloudProfile()
      if(!alive||mine!==readEpoch)return
      draftStorageKey = storageScope() + 'frontend-onboarding-progress-v1'
      pageScope=storageScope()
      conflictDraft.value=uni.getStorageSync(draftStorageKey+':conflict')||null
      profile.value = loaded
      invited.value = profile.value.isOwner === false
      if (invited.value) {
        memberIndex.value = profile.value.members.findIndex(member => String(member.id) === profile.value.selfMemberId)
        if (memberIndex.value < 0) throw new Error('尚未读到本人档案，请重新打开邀请并确认加入。')
      }
      const policy=profile.value.analysisPolicy
      const draft = scopedStorage.getStorageSync('frontend-onboarding-progress-v1')
      if (restoreDraft && draft?.profile?.householdId === profile.value.householdId && draft.profile.familyVersion === profile.value.familyVersion) {
        profile.value = normalizeProfile(draft.profile); step.value = draft.step || 0
        profile.value.analysisPolicy=policy
      }
      if (!invited.value && !profile.value.defaultDiners.length) profile.value.defaultDiners = profile.value.members.map(member=>member.id)
      familyDiners.value=[...profile.value.defaultDiners]
      if (!invited.value) syncDiners()
      cloudLoaded.value=true
    } catch(error) { if(alive&&mine===readEpoch){if([401,403,404,410].includes(Number(error.code))||error.code==='SESSION_CHANGED')clearPrivate();cloudError.value=error.message;cloudErrorCode.value=error.code} }
    finally { if(alive&&mine===readEpoch)cloudLoading.value=false }
}
function clearPrivate(){cloudLoaded.value=false;conflictDraft.value=null;showConflictDraft.value=false;profile.value=normalizeProfile({members:[]});familyDiners.value=[]}
onUnload(()=>{alive=false;readEpoch++})
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
function preserveProgress() {
  if (!invited.value && !completed && (isMockMode || cloudLoaded.value)) uni.setStorageSync(draftStorageKey, JSON.parse(JSON.stringify({
    version: 2, profile: profile.value, step: step.value, memberIndex: memberIndex.value, familyDiners: familyDiners.value,
  })))
}
watch([profile, step, memberIndex, familyDiners], preserveProgress, { deep: true })
async function recoverCloud() {
  if (Number(cloudErrorCode.value) === 401) { preserveProgress(); uni.reLaunch({ url: '/pages/index/index' }); return }
  if (Number(cloudErrorCode.value) === 409) {
    preserveProgress()
    uni.setStorageSync(draftStorageKey+':conflict',JSON.parse(JSON.stringify(profile.value)))
    await readCloud(false)
    if (!cloudError.value) cloudError.value='档案已变化，已读取当前版本，请重新核对后保存。'
    return
  }
  if (cloudLoaded.value) next(); else void readCloud()
}
onShow(async () => {
  if(!isMockMode&&pageScope!==storageScope()) {clearPrivate();await readCloud();return}
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
    const revision=sessionRevision()
    cloudSaving.value=true;cloudError.value=''
    try { const saved=await saveCloudProfile(profile.value);if(!alive)return;if(revision!==sessionRevision()){clearPrivate();cloudError.value='账号或家庭已变化，请重新读取档案。';return}profile.value=saved }
    catch(error){if(!alive)return;preserveProgress();if([401,403,404,410].includes(Number(error.code))||error.code==='SESSION_CHANGED'||revision!==sessionRevision())clearPrivate();cloudError.value=error.message;cloudErrorCode.value=error.code;return}
    finally{cloudSaving.value=false}
  }
  if (!invited.value) {
    completed = true
    scopedStorage.setStorageSync('frontend-onboarded-v1', true)
    uni.setStorageSync(draftStorageKey, null)
    uni.setStorageSync(draftStorageKey+':conflict',null)
  }
  uni.reLaunch({ url: '/pages/chat/index?from=onboarding' })
}
function next() {
  if(cloudSaving.value||cloudLoading.value||cloudError.value&&!profile.value.householdId)return
  const members = step.value === 2 && !invited.value ? profile.value.members : visibleMembers.value
  for (const member of members) {
    const issue = onboardingIssue(member, step.value)
    if (issue) {
      if (!visibleMembers.value.some(value => value.id === member.id)) mode('家庭使用')
      selectMember(member.id); step.value = issue.step
      uni.showToast({ title: member.name + '：' + issue.message, icon: 'none' }); return
    }
  }
  const warnings = members.flatMap(m => dataWarnings(m).map(w => `${m.name}：${w}`))
  if (warnings.length) {
    uni.showModal({ title: '请复核档案信息', content: warnings.join('；') + '。此提示不是医疗诊断。', cancelText: '返回修改', confirmText: '继续保存', success: result => { if (result.confirm) commit() } })
    return
  }
  commit()
}
</script>
<template>
  <view v-if="cloudLoading" class="screen"><text class="safe-note">正在读取云端档案…</text></view>
  <view v-if="cloudError" class="cloud-onboarding-error" role="alert"><text>{{cloudError}}</text><button @click="recoverCloud">{{Number(cloudErrorCode)===401?'重新登录':cloudLoaded?'重试保存':'重新读取档案'}}</button></view>
  <view v-if="conflictDraft&&cloudLoaded" class="cloud-onboarding-error"><text>上次未保存的填写内容已保留。当前表单已读取云端版本，请对照核对后再保存。</text><button @click="showConflictDraft=!showConflictDraft">{{showConflictDraft?'收起':'查看'}}上次未保存内容</button><template v-if="showConflictDraft"><MemberFields v-for="member in conflictDraft.members" :key="member.id" :member="member" :read-only="true" :sections="['basic','disease','preferences','restrictions']"/></template></view>
  <view v-if="!cloudLoading && cloudLoaded && current" class="screen onboarding-screen" :class="{ 'health-step': step === 1, 'first-step': step === 0, 'detail-step': step > 0, 'restriction-step': step === 2, 'allergy-unanswered': !['none','set'].includes(current.allergyStatus), 'intolerance-unanswered': !['none','set'].includes(current.intoleranceStatus), 'avoidance-unanswered': !['none','set'].includes(current.avoidanceStatus), 'doctor-unanswered': !['none','set'].includes(current.doctorStatus) }">
    <AppNavBar><view class="nav-row"><button class="icon-button" @click="step > 0 ? step-- : backHome()">‹</button><text class="nav-title">{{ invited ? '受邀成员建档' : '家庭建档' }}</text></view></AppNavBar>
    <view class="step-progress"><text class="step-caption">第 {{step + 1}} 步，共 3 步</text><view class="progress"><view v-for="n in 3" :key="n" :class="{complete:n <= step + 1, 'current-step':n === step + 1}"><view class="step-node"/><text class="step-name">{{ ['成员信息', '健康与偏好', '饮食限制'][n - 1] }}</text></view></view></view>
    <view class="question-head"><text class="display-title">{{ step === 2 ? '确认饮食限制' : copy[step][0] }}</text><text class="helper">{{ invited && step === 0 ? '先填写你的成员信息。' : copy[step][1] }}</text></view>
    <template v-if="step === 0 && !invited">
      <view class="mode-grid"><button v-for="item in [{ value: '个人使用', label: '只为自己' }, { value: '家庭使用', label: '自己和家人' }]" :key="item.value" :class="{ active: profile.usageMode === item.value }" @click="mode(item.value)">{{ item.label }}</button></view>
    </template>
    <text class="current">{{ step === 1 ? (invited ? '为谁填写：' + current.name : '为谁填写') : '正在填写：' + (current.name || '未命名成员') }}</text>
    <view v-if="!invited" class="member-tabs">
      <button v-for="m in visibleMembers" :key="m.id" :class="{ active: current.id === m.id }" @click="selectMember(m.id)"><view class="member-monogram" aria-hidden="true">{{ (m.name || '家').slice(0,1) }}</view><text>{{ m.name || '未命名成员' }}</text></button>
      <button v-if="profile.usageMode === '家庭使用' && step !== 1" class="add-member" @click="add">＋ 添加家人</button>
    </view>
    <OnboardingHealthFields v-if="step === 1" :key="current.id" :member="current" />
    <OnboardingBasics v-else-if="step === 0" :key="current.id" :member="current"/><MemberFields v-else :key="current.id" :member="current" :sections="['restrictions', 'reports']" compact/>
    <view v-if="step === 0 && !invited" class="diner-section">
      <template v-if="profile.usageMode === '家庭使用'">
        <text class="label">通常一起吃饭的是哪些人？</text>
        <view class="diner-choices"><button v-for="m in profile.members" :key="m.id" role="checkbox" :aria-checked="profile.defaultDiners.includes(m.id)" :class="{ selected: profile.defaultDiners.includes(m.id) }" @click="toggleDiner(m.id)"><text class="checkmark">{{ profile.defaultDiners.includes(m.id) ? '✓' : '' }}</text><text>{{ m.name || '未命名成员' }}</text></button></view>
      </template>
      <text class="helper diner-summary">默认按 {{ dinerCount }} 人安排，每餐可以调整。</text>
    </view>
    <view class="onboarding-footer"><button class="primary-button next" :disabled="cloudSaving||cloudLoading" @click="next"><text>{{ step === 2 ? (cloudSaving ? '正在保存…' : invited ? '保存，进入家庭' : '完成建档，开始对话') : '保存并继续' }}</text><text>{{ step === 1 ? '›' : '→' }}</text></button></view>
    <text v-if="isMockMode" class="demo-label">前端体验版 · 资料保存于本机，请勿输入真实病历</text>
  </view>
</template>
<style scoped>
.onboarding-screen{background:#fff;color:#22252b;padding:12rpx 32rpx calc(env(safe-area-inset-bottom) + 96px)}
.step-progress{display:flex;align-items:center;gap:22rpx;margin:16rpx 4rpx 0}.step-caption{font-size:24rpx;color:#858da0;white-space:nowrap}.progress{display:flex;flex:1;gap:10rpx}.progress>view{height:10rpx;flex:1;border-radius:999rpx;background:#e9ecf2}.progress>view.complete{background:#0879f9}
.question-head{display:flex;flex-direction:column;gap:12rpx;margin:28rpx 4rpx 24rpx}.question-head .display-title{font-size:56rpx;font-weight:500;line-height:1.32;letter-spacing:-.6rpx;white-space:pre-line}.helper{display:block;font-size:27rpx;line-height:1.6;color:#7d8699}.label{display:block;font-size:29rpx;font-weight:500}.question-head .helper{font-size:28rpx}
.mode-grid{display:flex;gap:8rpx;padding:6rpx;background:#f5f6f8;border-radius:22rpx;margin-bottom:28rpx}.mode-grid button{flex:1;min-height:44px;font-size:29rpx;color:#7a8498;border:1rpx solid transparent;border-radius:18rpx}.mode-grid .active{background:#fff;color:#0879f9;border-color:#7bb1ff}
.current{display:block;font-size:28rpx;font-weight:500;margin:0 0 10rpx}.member-tabs{display:flex;gap:14rpx;flex-wrap:wrap;margin:0 0 20rpx}.member-tabs button{display:flex;align-items:center;justify-content:center;gap:12rpx;min-width:146rpx;max-width:100%;min-height:48px;padding:8rpx 22rpx;border:1rpx solid #e9ecf2;border-radius:20rpx;background:#fff;color:#788297;font-size:28rpx;overflow-wrap:anywhere}.member-tabs .active{border-color:#72aaff;background:#f1f6ff;color:#242831}.member-monogram{display:flex;align-items:center;justify-content:center;flex-shrink:0;width:60rpx;height:60rpx;border-radius:50%;background:#edf0f5;color:#6b788f;font-size:28rpx}.member-tabs .add-member{min-width:80rpx;border-style:dashed;background:#fafbfc;color:#7b879f}.member-tabs .add-member .member-monogram{background:none}
.diner-section{padding:22rpx 24rpx;border:1rpx solid #e9ecf2;border-radius:24rpx;margin-top:18rpx}.diner-choices{display:flex;gap:14rpx;flex-wrap:wrap;margin:14rpx 0 0}.diner-choices button{display:flex;align-items:center;gap:14rpx;min-height:44px;flex:1;min-width:180rpx;padding:10rpx 18rpx;background:#f6f7f9;border-radius:16rpx;font-size:28rpx}.checkmark{width:34rpx;height:34rpx;border:1rpx solid #c3cada;border-radius:8rpx;color:transparent;display:flex;align-items:center;justify-content:center;font-size:24rpx;flex-shrink:0}.selected .checkmark{background:#0879f9;border-color:#0879f9;color:#fff}.diner-summary{margin-top:16rpx;font-size:24rpx;color:#858da0}
.onboarding-footer{position:fixed;left:0;right:0;bottom:0;z-index:20;padding:18rpx 32rpx calc(env(safe-area-inset-bottom) + 22rpx);background:rgba(255,255,255,.98);border-top:1rpx solid #f1f2f5}.onboarding-footer .next{min-height:48px;border-radius:999rpx;font-size:30rpx;font-weight:500;gap:20rpx}.analysis-policy{display:block;margin:24rpx 4rpx 0;font-size:24rpx;line-height:1.65;color:#7b8495;overflow-wrap:anywhere}.demo-label{font-size:24rpx;text-align:center;margin-top:20rpx}
.cloud-onboarding-error{padding:24rpx;margin:24rpx 32rpx;background:#fff5f3;border-radius:20rpx;color:#8d4238;font-size:27rpx;line-height:1.65}.cloud-onboarding-error button{min-height:44px;margin-top:8rpx;color:#0674ed}
.onboarding-screen :deep(.member-sheet){border-radius:32rpx 32rpx 0 0;padding:28rpx 32rpx calc(env(safe-area-inset-bottom) + 28rpx)}.onboarding-screen :deep(.member-sheet .chips button){min-height:44px}.onboarding-screen :deep(.member-sheet .sheet-head){padding-bottom:10rpx}.onboarding-screen :deep(.member-sheet .actions button){min-height:48px;border-radius:999rpx}
/* #ifdef H5 */
.onboarding-footer{max-width:480px;width:100%;left:50%;right:auto;transform:translateX(-50%)}
/* #endif */

</style>

<style scoped>

/* The Qixian-inspired treatment belongs to the first onboarding step only. */
.step-node,.step-name{display:none}
.onboarding-screen.first-step{padding:12rpx 40rpx calc(env(safe-area-inset-bottom) + 110px);background:#fff;color:#111}
.first-step .step-progress{display:block;margin:22rpx -6rpx 0}
.first-step .step-caption{display:none}
.first-step .progress{display:flex;gap:0}
.first-step .progress>view{position:relative;height:auto;min-height:68rpx;padding-top:2rpx;background:transparent;border-radius:0;text-align:center}
.first-step .progress>view::before,.first-step .progress>view::after{content:'';position:absolute;top:11rpx;width:calc(50% - 18rpx);height:2rpx;background:#dedee2}
.first-step .progress>view::before{left:0}.first-step .progress>view::after{right:0}
.first-step .progress>view:first-child::before,.first-step .progress>view:last-child::after{display:none}
.first-step .progress .step-node{position:relative;z-index:1;display:block;width:20rpx;height:20rpx;margin:0 auto;border:2rpx solid #d9d9df;border-radius:50%;background:#fff}
.first-step .progress>.complete .step-node{border-color:#111;background:#111}
.first-step .progress .step-name{display:block;margin-top:14rpx;color:#a3a3ab;font-size:25rpx;line-height:1.4;white-space:nowrap}
.first-step .progress>.complete .step-name{color:#111;font-weight:500}
.first-step .question-head{gap:14rpx;margin:34rpx 0 28rpx}
.first-step .question-head .display-title{font-size:56rpx;font-weight:600;line-height:1.35;letter-spacing:0;color:#111}
.first-step .question-head .helper{font-size:27rpx;line-height:1.7;color:#68686f}
.first-step .mode-grid{gap:8rpx;padding:6rpx;margin:0 0 24rpx;background:#f5f5f6;border-radius:16rpx}
.first-step .mode-grid button{display:flex;align-items:center;justify-content:center;min-height:44px;border:0;border-radius:12rpx;font-size:28rpx;color:#6b6b72}
.first-step .mode-grid button.active{border:0;background:#111;color:#fff}
.first-step .current{margin:0 0 14rpx;color:#6d6d74;font-size:25rpx;font-weight:400}
.first-step .member-tabs{align-items:flex-start;gap:22rpx;margin:0 0 28rpx}
.first-step .member-tabs button{flex-direction:column;gap:10rpx;min-width:100rpx;max-width:180rpx;min-height:0;padding:0 4rpx;background:transparent;border:0;border-radius:0;color:#77777f;font-size:26rpx;line-height:1.4}
.first-step .member-monogram{width:88rpx;height:88rpx;border:3rpx solid transparent;background:#f3f3f5;color:#55555d;font-size:32rpx}
.first-step .member-tabs button.active{background:transparent;border:0;color:#111}
.first-step .member-tabs button.active .member-monogram{border-color:#111;color:#111;background:#f5f5f6}
.first-step .member-tabs button.active>text{font-weight:600}
.first-step .member-tabs .add-member{align-self:center;min-width:120rpx;min-height:44px;padding:8rpx 14rpx;border:1rpx dashed #d7d7dc;border-radius:12rpx;background:#fafafa;color:#66666e;font-size:25rpx}
.first-step :deep(.basic-fields){padding:0;border:0;border-radius:0;background:#fff;color:#111}
.first-step :deep(.basic-row){display:flex;flex-direction:column;align-items:stretch;gap:14rpx;min-height:0;margin-bottom:28rpx;border:0;font-size:28rpx}
.first-step :deep(.basic-row>text){color:#777780;line-height:1.5}
.first-step :deep(.basic-row input){display:block;flex:none;width:100%;height:48px;padding:0 24rpx;border:0;border-radius:14rpx;background:#f6f6f7;color:#19191d;font-size:30rpx;text-align:left}
.first-step :deep(.basic-row picker){display:block;flex:none;width:100%;min-height:48px;border-radius:14rpx;background:#f6f6f7}
.first-step :deep(.picker-value){justify-content:space-between;width:100%;min-height:48px;padding:12rpx 24rpx;color:#19191d;font-size:30rpx}
.first-step :deep(.picker-value.placeholder){color:#96969f}
.first-step :deep(.chevron){font-size:32rpx;color:#8b8b94}
.first-step :deep(.measurements){gap:24rpx;padding:0}
.first-step :deep(.measure){min-width:0;padding:0;border:0;border-radius:0;color:#777780;font-size:28rpx}
.first-step :deep(.unit){font-size:24rpx;color:#8a8a94}
.first-step :deep(.measure input){width:100%;height:48px;margin-top:14rpx;padding:0 24rpx;border-radius:14rpx;background:#f6f6f7;color:#19191d;font-size:30rpx}
.first-step .diner-section{margin-top:30rpx;padding:0;border:0;border-radius:0}
.first-step .diner-section>.label{font-size:28rpx;font-weight:400;color:#777780}
.first-step .diner-choices{gap:14rpx;margin-top:16rpx}
.first-step .diner-choices button{flex:initial;min-width:150rpx;min-height:44px;padding:12rpx 20rpx;border-radius:14rpx;background:#f6f6f7;color:#35353d;font-size:27rpx}
.first-step .checkmark{border-color:#bcbcc5;border-radius:6rpx}
.first-step .selected .checkmark{background:#111;border-color:#111;color:#fff}
.first-step .diner-summary{margin-top:22rpx;font-size:24rpx;line-height:1.7;color:#777780}
.first-step .onboarding-footer{padding:22rpx 40rpx calc(env(safe-area-inset-bottom) + 24rpx);background:rgba(255,255,255,.98);border-top:1rpx solid #f3f3f5}
.first-step .onboarding-footer .next{min-height:52px;padding:18rpx 24rpx;border-radius:14rpx;background:#080808;color:#fff;font-size:31rpx;font-weight:500;gap:20rpx}
@media(max-width:350px){.onboarding-screen.first-step{padding-left:36rpx;padding-right:36rpx}.first-step .question-head .display-title{font-size:54rpx}.first-step .member-tabs{gap:18rpx}.first-step .onboarding-footer{padding-left:36rpx;padding-right:36rpx}}
</style>

<style scoped>

/* Steps two and three share the approved first-step visual language. */
.onboarding-screen.detail-step{padding:12rpx 40rpx calc(env(safe-area-inset-bottom) + 110px);background:#fff;color:#111}
.detail-step .step-progress{display:block;margin:22rpx -6rpx 0}.detail-step .step-caption{display:none}.detail-step .progress{display:flex;gap:0}
.detail-step .progress>view{position:relative;height:auto;min-height:68rpx;padding-top:2rpx;background:transparent;border-radius:0;text-align:center}
.detail-step .progress>view::before,.detail-step .progress>view::after{content:'';position:absolute;top:11rpx;width:calc(50% - 18rpx);height:2rpx;background:#dedee2}
.detail-step .progress>view::before{left:0}.detail-step .progress>view::after{right:0}.detail-step .progress>view:first-child::before,.detail-step .progress>view:last-child::after{display:none}
.detail-step .progress>.complete::before,.detail-step .progress>.complete::after{background:#111}.detail-step .progress>.current-step::after{background:#dedee2}
.detail-step .progress .step-node{position:relative;z-index:1;display:block;width:20rpx;height:20rpx;margin:0 auto;border:2rpx solid #d9d9df;border-radius:50%;background:#fff}
.detail-step .progress>.complete .step-node{background:#111;border-color:#111}.detail-step .progress>.complete .step-node::after{content:'✓';display:block;color:#fff;font-size:15rpx;line-height:16rpx;text-align:center}
.detail-step .progress>.current-step .step-node{background:#fff;border-color:#111}.detail-step .progress>.current-step .step-node::after{content:'';width:8rpx;height:8rpx;margin:4rpx auto;background:#111;border-radius:50%}
.detail-step .progress .step-name{display:block;margin-top:14rpx;color:#96969f;font-size:25rpx;line-height:1.4;white-space:nowrap}.detail-step .progress>.complete .step-name{color:#333}.detail-step .progress>.current-step .step-name{color:#111;font-weight:600}
.detail-step .question-head{gap:14rpx;margin:34rpx 0 28rpx}.detail-step .question-head .display-title{font-size:56rpx;font-weight:600;line-height:1.35;letter-spacing:0;color:#111}.detail-step .question-head .helper{font-size:27rpx;line-height:1.7;color:#68686f}
.detail-step .current{margin:0 0 14rpx;color:#6d6d74;font-size:25rpx;font-weight:400}.detail-step .member-tabs{align-items:flex-start;gap:22rpx;margin:0 0 30rpx}
.detail-step .member-tabs button{flex-direction:column;gap:10rpx;min-width:100rpx;max-width:180rpx;min-height:0;padding:0 4rpx;background:transparent;border:0;border-radius:0;color:#77777f;font-size:26rpx;line-height:1.4}
.detail-step .member-monogram{width:88rpx;height:88rpx;border:3rpx solid transparent;background:#f3f3f5;color:#55555d;font-size:32rpx}.detail-step .member-tabs button.active{background:transparent;border:0;color:#111}.detail-step .member-tabs button.active .member-monogram{border-color:#111;color:#111;background:#f5f5f6}.detail-step .member-tabs button.active>text{font-weight:600}
.detail-step .member-tabs .add-member{align-self:center;min-width:120rpx;min-height:44px;padding:8rpx 14rpx;border:1rpx dashed #d7d7dc;border-radius:12rpx;background:#fafafa;color:#66666e;font-size:25rpx}
.detail-step :deep(.health-card){margin-bottom:30rpx;color:#111}.detail-step :deep(.card-heading){gap:12rpx;margin-bottom:16rpx}.detail-step :deep(.card-title){font-size:30rpx;font-weight:600;line-height:1.5;color:#111}.detail-step :deep(.multiple-hint){font-size:24rpx;color:#74747c}
.detail-step :deep(.health-options){gap:12rpx;margin-top:16rpx}.detail-step :deep(.health-option){min-height:48px;padding:14rpx 22rpx;border:1rpx solid transparent;border-radius:14rpx;background:#f6f6f7;color:#222;font-size:28rpx}.detail-step :deep(.health-option.chosen){background:#f6f6f7;border-color:#222}
.detail-step :deep(.radio-mark){border-color:#bcbcc5}.detail-step :deep(.chosen .radio-mark){border-color:#111;background:#111}.detail-step :deep(.chosen .radio-mark view){background:#fff}
.detail-step :deep(.condition-area){margin-top:22rpx}.detail-step :deep(.field-label){font-size:26rpx;line-height:1.6;color:#6d6d76}.detail-step :deep(.support-copy){font-size:24rpx;line-height:1.7;color:#74747d}
.detail-step :deep(.option-grid){gap:14rpx}.detail-step :deep(.option-grid button){min-height:44px;padding:12rpx 8rpx;border:1rpx solid transparent;border-radius:14rpx;background:#f6f6f7;color:#33333b;font-size:28rpx;line-height:1.5}.detail-step :deep(.condition-grid button){font-size:26rpx}.detail-step :deep(.option-grid button.selected){border-color:#111;background:#111;color:#fff}
.detail-step :deep(.other-row){min-height:48px;margin-top:6rpx;padding:12rpx 2rpx;border-color:#ededf0;color:#55555d;font-size:27rpx}.detail-step :deep(.chevron){color:#85858f;font-size:32rpx}.detail-step :deep(.extra-summary){color:#66666f;font-size:25rpx;line-height:1.7}
.detail-step :deep(.cuisine-summary){min-height:48px;padding:16rpx 22rpx;border:0;border-radius:14rpx;background:#f6f6f7;color:#222;font-size:28rpx}.detail-step :deep(.cuisine-label){color:#222}.detail-step :deep(.optional-label){color:#797982;font-size:24rpx}.detail-step :deep(.cuisine-placeholder){color:#8a8a94}
.detail-step :deep(.custom-input),.detail-step :deep(.member-sheet .field-input){height:46px;padding:0 22rpx;border:0;border-radius:14rpx;background:#f6f6f7;color:#222;font-size:28rpx}.detail-step :deep(.custom-row button){color:#222;font-size:27rpx}
.detail-step :deep(.extras-sheet),.detail-step :deep(.member-sheet){max-height:80vh;padding:28rpx 40rpx calc(env(safe-area-inset-bottom) + 28rpx);border-radius:28rpx 28rpx 0 0;color:#111;background:#fff}
.detail-step :deep(.sheet-heading),.detail-step :deep(.member-sheet .sheet-head){align-items:center;gap:20rpx;margin-bottom:24rpx;padding-bottom:0}.detail-step :deep(.sheet-heading .card-title),.detail-step :deep(.member-sheet .section-title){font-size:34rpx;font-weight:600;color:#111;line-height:1.5}
.detail-step :deep(.sheet-heading .support-copy),.detail-step :deep(.member-sheet .eyebrow){margin:0 0 8rpx;color:#74747d;font-size:25rpx}.detail-step :deep(.close-sheet),.detail-step :deep(.member-sheet .sheet-head>button){width:44px;min-width:44px;height:44px;min-height:44px;font-size:38rpx;color:#333}
.detail-step :deep(.sheet-actions),.detail-step :deep(.member-sheet .actions){position:sticky;bottom:0;gap:20rpx;margin-top:24rpx;padding-top:16rpx;background:#fff}
.detail-step :deep(.sheet-actions button),.detail-step :deep(.member-sheet .actions button){min-height:50px;padding:16rpx 18rpx;border:0;border-radius:14rpx;background:#f2f2f4;color:#222;font-size:30rpx}
.detail-step :deep(.sheet-actions button.selected),.detail-step :deep(.member-sheet .actions .primary-button){border:0;background:#080808;color:#fff}
.detail-step :deep(.member-sheet .chips){gap:14rpx;margin:18rpx 0}.detail-step :deep(.member-sheet .chips button){min-height:44px;padding:12rpx 18rpx;border:1rpx solid transparent;border-radius:14rpx;background:#f6f6f7;color:#333;font-size:27rpx}.detail-step :deep(.member-sheet .chips button.active){background:#111;border-color:#111;color:#fff}
.detail-step :deep(.member-sheet .chips>text){padding:8rpx 14rpx;border-radius:10rpx;background:#f2f2f4;color:#333;font-size:26rpx}.detail-step :deep(.member-sheet .text-area){min-height:180rpx;padding:20rpx 22rpx;border:0;border-radius:14rpx;background:#f6f6f7;color:#222;font-size:29rpx;line-height:1.7}
.restriction-step :deep(.compact-restrictions){margin-bottom:28rpx;padding:0;border:0;border-radius:0;background:transparent}.restriction-step :deep(.compact-restrictions .field-row){min-height:56px;margin-bottom:14rpx;padding:18rpx 22rpx;border:0;border-radius:14rpx;background:#f6f6f7}
.restriction-step :deep(.compact-restrictions .field-row>view){gap:18rpx}.restriction-step :deep(.compact-restrictions .field-row>view>text:first-child){font-size:28rpx;color:#222}.restriction-step :deep(.compact-restrictions .field-row>view>text:last-child){flex:1;min-width:0;max-width:58%;font-size:26rpx;line-height:1.6;color:#222;text-align:right;overflow-wrap:anywhere}
.restriction-step.allergy-unanswered :deep(.compact-restrictions .field-row:nth-child(1)>view>text:last-child),.restriction-step.intolerance-unanswered :deep(.compact-restrictions .field-row:nth-child(2)>view>text:last-child),.restriction-step.avoidance-unanswered :deep(.compact-restrictions .field-row:nth-child(3)>view>text:last-child),.restriction-step.doctor-unanswered :deep(.compact-restrictions .field-row:nth-child(4)>view>text:last-child){color:#7b7b85}
.restriction-step :deep(.compact-reports){margin-bottom:20rpx;padding:0 22rpx;border:0;border-radius:14rpx;background:#f6f6f7}.restriction-step :deep(.compact-reports .field-row){min-height:56px;padding:18rpx 0;border:0}.restriction-step :deep(.compact-reports .field-row>view>text:first-child){font-size:28rpx;color:#222}.restriction-step :deep(.compact-reports .field-row>view>text:last-child){font-size:26rpx;color:#777780}.restriction-step :deep(.compact-reports .helper){margin:0;padding-bottom:20rpx;color:#74747d;font-size:24rpx;line-height:1.7}
.detail-step .onboarding-footer{padding:22rpx 40rpx calc(env(safe-area-inset-bottom) + 24rpx);background:rgba(255,255,255,.98);border-top:1rpx solid #f3f3f5}.detail-step .onboarding-footer .next{min-height:52px;padding:18rpx 24rpx;border-radius:14rpx;background:#080808;color:#fff;font-size:31rpx;font-weight:500;gap:20rpx}
@media(max-width:350px){.onboarding-screen.detail-step{padding-left:36rpx;padding-right:36rpx}.detail-step .question-head .display-title{font-size:54rpx}.detail-step .member-tabs{gap:18rpx}.detail-step .onboarding-footer{padding-left:36rpx;padding-right:36rpx}.detail-step :deep(.extras-sheet),.detail-step :deep(.member-sheet){padding-left:36rpx;padding-right:36rpx}}
</style>
