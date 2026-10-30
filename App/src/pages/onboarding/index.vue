<script setup>
import { submitOnboardingPreparation } from '../../services/onboarding-preparation.js'
import { sessionRevision } from '../../services/session.js'
import { scopedStorage, storageScope } from '../../services/storage.js'
import ProfileFormLayout from '../../components/ProfileFormLayout.vue'
import MemberRestrictionsFields from '../../components/MemberRestrictionsFields.vue'
import { computed, nextTick, ref, watch } from 'vue'
import { onLoad, onShow, onUnload, onPageScroll } from '@dcloudio/uni-app'
import MemberFields from '../../components/MemberFields.vue'
import OnboardingBasics from '../../components/OnboardingBasics.vue'
import OnboardingHealthFields from '../../components/OnboardingHealthFields.vue'
import { backHome, getProfile, newMember, normalizeMember, normalizeProfile, saveProfile } from '../../utils/profile.js'
import { dataWarnings } from '../../utils/health.js'
import { onboardingIssue } from '../../utils/onboarding-validation.js'
import { isMockMode } from '../../services/config.js'
import { loadCloudProfile, readCloudReportStatus } from '../../services/cloud-profile.js'
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
const pageScroll=ref(0),fieldError=ref('')
onPageScroll(e=>{pageScroll.value=Math.max(0,e.scrollTop||0)})
let completed = false
const familyDiners = ref([...profile.value.defaultDiners])
const current = computed(() => profile.value.members[memberIndex.value])
const self = computed(() => profile.value.selfMemberId ? profile.value.members.find(m=>String(m.id)===String(profile.value.selfMemberId)) : profile.value.members.find(m=>m.relation==='本人')||profile.value.members[0])
const visibleMembers = computed(() => invited.value ? [current.value] : profile.value.usageMode === '个人使用' ? [self.value] : profile.value.members)
watch(current,()=>{fieldError.value=''}, {deep:true})
const dinerCount = computed(() => profile.value.defaultDiners.length)
const copy = [
  ['先认识每位成员', '更好地为你和家人定制饮食建议。'],
  ['饮食目标与健康', '帮你安排更合适的三餐。'],
  ['重要的限制，\n分开记录', '帮你避开不适合的食物。'],
]
const solo=computed(()=>invited.value||profile.value.usageMode==='个人使用')
const heading=computed(()=>step.value===0?(solo.value?'先认识一下你':'先认识你和家人'):step.value===1?'让三餐更合你心意':'确认重要的饮食限制')
const description=computed(()=>['让之后的饮食建议更适合你','记录健康情况，选一选饮食偏好','逐项确认，帮你避开不适合的食物'][step.value])
function memberComplete(m){return !onboardingIssue(m,step.value)}
watch(step, () => nextTick(() => {fieldError.value='';uni.pageScrollTo?.({scrollTop:pageScroll.value>70?119:0,duration:0})}))

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
      const policy=profile.value.analysisPolicy,configuration=profile.value.healthConfiguration
      const draft = scopedStorage.getStorageSync('frontend-onboarding-progress-v1')
      const canRestore=restoreDraft&&draft?.profile?.householdId===profile.value.householdId&&draft.profile.familyVersion===profile.value.familyVersion
      if (canRestore) {
        profile.value = normalizeProfile(draft.profile); step.value = Math.max(0,Math.min(2,draft.step||0))
        if(!invited.value){const restored=profile.value.members.findIndex(m=>String(m.id)===String(draft.memberId));memberIndex.value=restored>=0?restored:Math.max(0,Math.min(profile.value.members.length-1,draft.memberIndex||0))}
        if(draft.familyDiners)familyDiners.value=draft.familyDiners
        profile.value.analysisPolicy=policy;profile.value.healthConfiguration=configuration
      }
      if(!self.value)throw new Error('尚未读到本人档案，请重新读取。')
      if (!invited.value && !profile.value.defaultDiners.length) profile.value.defaultDiners = profile.value.members.map(member=>member.id)
      familyDiners.value=[...(canRestore&&draft.familyDiners||profile.value.defaultDiners)]
      if (!invited.value) {syncDiners();if(profile.value.usageMode==='个人使用')selectMember(self.value.id)}
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
    version: 2, profile: profile.value, step: step.value, memberIndex: memberIndex.value, memberId: current.value?.id, familyDiners: familyDiners.value,
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
function selectMember(id) { fieldError.value='';memberIndex.value = profile.value.members.findIndex(m => String(m.id) === String(id)) }
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
  if(self.value)self.value.relation='本人'
  if(isMockMode)saveProfile(profile.value)
  if (step.value < 2) { step.value++; return }
  if(!isMockMode){
    const revision=sessionRevision()
    cloudSaving.value=true;cloudError.value=''
    try {
      await submitOnboardingPreparation(profile.value)
      if(!alive)return
      if(revision!==sessionRevision()){clearPrivate();cloudError.value='账号或家庭已变化，请重新读取档案。';return}
      completed=true
      scopedStorage.setStorageSync('frontend-onboarded-v1',true)
      uni.setStorageSync(draftStorageKey,null)
      uni.setStorageSync(draftStorageKey+':conflict',null)
      uni.reLaunch({url:'/pages/chat/index?from=onboarding'})
    }catch(error){
      if(!alive)return
      preserveProgress()
      if([401,403,404,410].includes(Number(error.code))||error.code==='SESSION_CHANGED'||revision!==sessionRevision())clearPrivate()
      cloudError.value=error.message;cloudErrorCode.value=error.code
    }finally{cloudSaving.value=false}
    return
  }


  if (!invited.value) {
    completed = true
    scopedStorage.setStorageSync('frontend-onboarded-v1', true)
    uni.setStorageSync(draftStorageKey, null)
    uni.setStorageSync(draftStorageKey+':conflict',null)
  }
  uni.reLaunch({ url: '/pages/chat/index?from=onboarding' })
}
function revealIssue(issue){
 const key=issue.message.includes('姓名')?'name':issue.message.includes('出生日期')?'birth':issue.message.includes('基础病')?'health':issue.message.includes('饮食目标')?'goals':issue.message.includes('口味')?'taste':issue.message.includes('过敏')?'allergy':issue.message.includes('不耐受')?'intolerance':issue.message.includes('忌口')?'avoidance':issue.message.includes('医生')?'doctor':null
 const selector=key?(issue.step===2?'#restriction-':'#field-')+key:'#onboarding-fields'
 const scroll=rect=>{if(rect){const status=uni.getWindowInfo?.().statusBarHeight||0;uni.pageScrollTo?.({scrollTop:Math.max(0,pageScroll.value+rect.top-(status+130)),duration:180})}}
 // #ifdef H5
 if(typeof document!=='undefined'){scroll(document.querySelector(selector)?.getBoundingClientRect());return}
 // #endif
 const query=uni.createSelectorQuery?.();query?.select(key?'#onboarding-fields >>> '+selector:selector).boundingClientRect(scroll).exec()
}
function flushRestrictionInputs(m){for(const type of ['allergy','intolerance','avoidance']){const field={allergy:'allergies',intolerance:'intolerances',avoidance:'avoidances'}[type],status={allergy:'allergyStatus',intolerance:'intoleranceStatus',avoidance:'avoidanceStatus'}[type],text=m['restrictionDraft_'+type]?.trim();if(m[status]==='set'&&text){if(!m[field].includes(text))m[field].push(text);m['restrictionDraft_'+type]=''}}}
function next() {
  if(cloudSaving.value||cloudLoading.value||cloudError.value&&!profile.value.householdId)return
  const members = step.value === 2 && !invited.value ? profile.value.members : visibleMembers.value
  for (const member of members) {
    flushRestrictionInputs(member)
    const issue = onboardingIssue(member, step.value)
    if (issue) {
      if (!visibleMembers.value.some(value => value.id === member.id)) mode('家庭使用')
      selectMember(member.id); step.value = issue.step
      nextTick(()=>{fieldError.value=member.name+'：'+issue.message;revealIssue(issue)})
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
 <ProfileFormLayout :title="invited?'完善本人档案':'建立营养档案'" :heading="heading" :description="description" :scroll-top="pageScroll" @back="step>0?step--:backHome()">
  <template #navigation><view class="profile-tabs"><button v-for="(label,i) in ['成员信息','健康与偏好','饮食限制']" :key="label" :class="{active:step===i,complete:i<step}" :aria-current="step===i?'step':null" @click="i<step?step=i:null"><text class="step-number">{{i<step?'✓':i+1}}</text>{{label}}</button></view></template>
  <text v-if="cloudLoading" class="form-note">正在读取云端档案…</text>
  <view v-if="cloudError" class="form-notice" role="alert"><text>{{cloudError}}</text><button @click="recoverCloud">{{Number(cloudErrorCode)===401?'重新登录':cloudLoaded?'重试保存':'重新读取档案'}}</button></view>
  <view v-if="conflictDraft&&cloudLoaded" class="form-notice"><text>上次未保存的内容已保留，请对照当前档案核对。</text><button @click="showConflictDraft=!showConflictDraft">{{showConflictDraft?'收起':'查看上次填写'}}</button><MemberFields v-if="showConflictDraft" v-for="m in conflictDraft.members" :key="m.id" :member="m" read-only :sections="['basic','disease','preferences','restrictions']"/></view>
  <template v-if="!cloudLoading&&cloudLoaded&&current">
   <view v-if="step===0&&!invited" class="usage-choice"><button v-for="item in [{v:'个人使用',t:'只为自己'},{v:'家庭使用',t:'自己和家人'}]" :key="item.v" :class="{active:profile.usageMode===item.v}" @click="mode(item.v)">{{item.t}}</button></view>
   <view v-if="!solo" class="family-members"><text class="small-label">为谁填写</text><view class="member-choices"><button v-for="m in visibleMembers" :key="m.id" :class="{active:current.id===m.id}" @click="selectMember(m.id)"><text class="member-initial">{{(m.name||'家').slice(0,1)}}</text><view><text class="member-name">{{m.name||'未命名成员'}}</text><text class="member-completion">{{memberComplete(m)?'本步已完成':'待补充'}}</text></view></button><button v-if="step!==1" class="add-member" @click="add">＋ 添加家人</button></view></view>
   <view id="onboarding-fields"><text v-if="fieldError" class="form-error" role="alert">{{fieldError}}</text><OnboardingBasics v-if="step===0" :key="current.id" :member="current" :show-relationship="String(current.id)!==String(self?.id)"/><OnboardingHealthFields v-else-if="step===1" :key="current.id" :member="current"/><template v-else><MemberRestrictionsFields :key="current.id" :member="current"/><view class="report-later"><view><text class="report-title">体检报告</text><text class="form-note">可在完成建档后补充，不影响本次填写</text></view><text class="optional-badge">可后补</text></view></template></view>
   <view v-if="step===0&&!solo" class="diner-section"><text class="small-label">通常一起吃饭的是哪些人？</text><view class="diner-choices"><button v-for="m in profile.members" :key="m.id" role="checkbox" :aria-checked="profile.defaultDiners.includes(m.id)" :class="{selected:profile.defaultDiners.includes(m.id)}" @click="toggleDiner(m.id)">{{profile.defaultDiners.includes(m.id)?'✓ ':''}}{{m.name||'未命名成员'}}</button></view><text class="form-note">默认按 {{dinerCount}} 人安排，每餐可以调整。</text></view>
   <text v-if="step===2&&!isMockMode&&!invited" class="form-note preparation-disclosure">完成后，将使用已填资料进行营养咨询与今日配餐准备。处理说明以当前服务配置为准。</text>
   <text v-if="step<2" class="draft-note">填写内容会在当前账号下暂存</text><text v-if="isMockMode" class="form-note">前端体验版 · 请使用虚构资料</text>
  </template>
  <template #footer><button :disabled="cloudSaving||cloudLoading||!cloudLoaded||!current" @click="next">{{step===2?(cloudSaving?'正在保存…':invited?'保存，进入家庭':'完成建档，开始对话'):'继续'}} <text class="next-arrow">→</text></button></template>
 </ProfileFormLayout>
</template>
<style scoped>
.usage-choice{display:flex;gap:10px;margin:0 0 26px}.usage-choice button{flex:1;min-height:43px;padding:10px;border:1px solid #eeeaf3;border-radius:12px;background:#f8f7fa;color:#9b8da7;font-size:14px;font-weight:500}.usage-choice button.active{background:#f0eaf8;color:#7a5a9f;border-color:#c8b3de}.family-members{margin-bottom:22px}.small-label{display:block;margin-bottom:12px;color:#94869f;font-size:12px}.member-choices{display:flex;flex-wrap:wrap;gap:10px}.member-choices button{display:flex;align-items:center;gap:9px;min-height:53px;padding:7px 11px;border:1px solid #efecf3;border-radius:13px;background:#faf9fb;text-align:left}.member-choices button.active{border-color:#c5b1dd;background:#f4effa}.member-initial{display:flex;align-items:center;justify-content:center;width:31px;height:31px;border-radius:50%;background:#eae3f3;color:#9475b3;font-size:13px}.member-name{display:block;color:#6c587d;font-size:13px;font-weight:500}.member-completion{display:block;margin-top:4px;color:#ac9db8;font-size:10px}.member-choices .add-member{min-height:44px;border-style:dashed;color:#a18ab5;font-size:12px}.diner-section{margin-top:28px;padding-top:22px;border-top:1px solid #f0edf5}.diner-choices{display:flex;flex-wrap:wrap;gap:9px}.diner-choices button{min-height:42px;padding:9px 14px;border-radius:11px;border:1px solid #eeebf3;color:#a393af;font-size:13px}.diner-choices button.selected{background:#f1ebf8;border-color:#c7b3de;color:#8461a6}.draft-note{display:block;margin-top:25px;text-align:center;color:#b2a7bc;font-size:11px}.report-later{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:17px 14px;border-radius:14px;background:#f8f6fa}.report-title{font-size:14px;color:#8b749f}.report-later .form-note{margin-bottom:0;font-size:11px}.optional-badge{flex-shrink:0;padding:4px 7px;background:#efe8f6;border-radius:7px;color:#a18ab7;font-size:10px}.next-arrow{margin-left:9px}
</style>
