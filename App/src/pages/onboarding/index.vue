<script setup>
import { preparationRoute, submitOnboardingPreparation } from '../../services/onboarding-preparation.js'
import { canRestoreOnboardingDraft } from '../../services/onboarding-draft.js'
import { sessionRevision } from '../../services/session.js'
import { scopedStorage, storageScope } from '../../services/storage.js'
import OnboardingLayout from '../../components/OnboardingLayout.vue'
import AppIcon from '../../components/AppIcon.vue'
import MemberRestrictionsFields from '../../components/MemberRestrictionsFields.vue'
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
import { request } from '../../services/request.js'
const cloudLoading=ref(!isMockMode),cloudError=ref(''),cloudSaving=ref(false),cloudLoaded=ref(isMockMode)
const policyLoading=ref(false)
const cloudErrorCode = ref(null)
const conflictDraft=ref(null),showConflictDraft=ref(false)
let progressStorageName = 'frontend-onboarding-progress-v1'
let draftStorageKey = storageScope() + progressStorageName
let pageScope=storageScope()
let readEpoch=0, alive=true
let initialProfile = getProfile()
if (!initialProfile.members.length || !scopedStorage.getStorageSync('family-profile-v2') && !scopedStorage.getStorageSync('frontend-onboarding-progress-v1')) {
  const self = normalizeMember({ ...newMember(0), name: '我', relation: '本人', age: '', claimedBy: 'creator' })
  initialProfile = normalizeProfile({ householdName: '我的家', usageMode: '个人使用', members: [self], defaultDiners: [self.id], goals: [], tastes: [], memories: [] })
}
const profile = ref(JSON.parse(JSON.stringify(initialProfile)))
const step = ref(0), memberIndex = ref(0), invited = ref(false)
const fieldError=ref('')
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
const processingPolicyReady=computed(()=>{
  const config=profile.value.healthConfiguration||{}
  return !!(config.policy_version&&config.consultation?.available&&config.consultation?.processor&&config.meal_plan?.available&&config.meal_plan?.processor)
})
async function reloadProcessingPolicy(){
  if(policyLoading.value)return
  const revision=sessionRevision();policyLoading.value=true;fieldError.value=''
  try{
    const {data}=await request({path:'/api/health/v1/configuration'})
    if(!alive||revision!==sessionRevision())return
    profile.value.healthConfiguration=data
    if(!processingPolicyReady.value)fieldError.value='咨询或配餐服务暂未就绪，请稍后重试。'
  }catch(error){if(alive&&revision===sessionRevision())fieldError.value=error.message||'处理说明暂时无法读取，请重试。'}
  finally{policyLoading.value=false}
}
const solo=computed(()=>invited.value||profile.value.usageMode==='个人使用')
const heading=computed(()=>step.value===0?(solo.value?'先认识一下你':'先认识你和家人'):step.value===1?'让三餐更合你心意':'确认重要的饮食限制')
const description=computed(()=>['让之后的饮食建议更适合你','记录健康情况，选一选饮食偏好','逐项确认，帮你避开不适合的食物'][step.value])
function memberComplete(m){return !onboardingIssue(m,step.value)}
watch(step, () => nextTick(() => {fieldError.value='';uni.pageScrollTo?.({scrollTop:0,duration:0})}))

async function readCloud(restoreDraft = true) {
    const mine=++readEpoch
    cloudLoading.value=true;cloudError.value='';cloudErrorCode.value=null
    try {
      const loaded = await loadCloudProfile({openConsultation:false})
      if(!alive||mine!==readEpoch)return
      progressStorageName = loaded.isOwner===false?'frontend-invited-onboarding-progress-v1:'+loaded.selfMemberId:'frontend-onboarding-progress-v1'
      draftStorageKey = storageScope() + progressStorageName
      pageScope=storageScope()
      conflictDraft.value=uni.getStorageSync(draftStorageKey+':conflict')||null
      profile.value = loaded
      invited.value = profile.value.isOwner === false
      if (invited.value) {
        memberIndex.value = profile.value.members.findIndex(member => String(member.id) === profile.value.selfMemberId)
        if (memberIndex.value < 0) throw new Error('尚未读到本人档案，请重新打开邀请并确认加入。')
      }
      const policy=profile.value.analysisPolicy,configuration=profile.value.healthConfiguration
      const draft = scopedStorage.getStorageSync(progressStorageName)
      const canRestore=restoreDraft&&canRestoreOnboardingDraft(draft,profile.value)
      if (canRestore) {
        if(invited.value){const saved=draft.profile.members.find(m=>m.id===profile.value.selfMemberId);profile.value.members[memberIndex.value]=normalizeMember(saved)}
        else profile.value = normalizeProfile(draft.profile)
        step.value = Math.max(0,Math.min(2,draft.step||0))
        if(!invited.value){const restored=profile.value.members.findIndex(m=>String(m.id)===String(draft.memberId));memberIndex.value=restored>=0?restored:Math.max(0,Math.min(profile.value.members.length-1,draft.memberIndex||0))}
        if(draft.familyDiners)familyDiners.value=draft.familyDiners
        profile.value.analysisPolicy=policy;profile.value.healthConfiguration=configuration
      }
      if(restoreDraft&&draft?.profile?.householdId===profile.value.householdId&&!canRestore){conflictDraft.value=draft.profile;uni.setStorageSync(draftStorageKey+':conflict',draft.profile)}
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
    progressStorageName='frontend-invited-onboarding-progress-v1:'+current.value.id
    draftStorageKey=storageScope()+progressStorageName
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
  if (!completed && (isMockMode || cloudLoaded.value)) uni.setStorageSync(draftStorageKey, JSON.parse(JSON.stringify({
    version: 2, profile: invited.value?{...profile.value,members:profile.value.members.filter(m=>String(m.id)===String(current.value?.id))}:profile.value, step: step.value, memberIndex: memberIndex.value, memberId: current.value?.id, familyDiners: familyDiners.value,
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
async function commit(consentAccepted = false) {
  if(cloudSaving.value||cloudLoading.value||!cloudLoaded.value)return
  if (!invited.value) syncDiners()
  if(self.value)self.value.relation='本人'
  if(isMockMode)saveProfile(profile.value)
  if (step.value < 2) { step.value++; return }
  if(!isMockMode){
    if(!invited.value&&!consentAccepted){
      const config=profile.value.healthConfiguration||{}
      if(!processingPolicyReady.value){
        fieldError.value='咨询与配餐处理说明尚未读取，请点击下方按钮重新读取。'
        return
      }
      uni.showModal({title:'确认数据处理',content:`咨询由 ${config.consultation.processor} 处理，配餐由 ${config.meal_plan.processor} 处理。政策版本：${config.policy_version}。是否同意使用档案资料进行这两项处理？`,cancelText:'暂不同意',confirmText:'同意继续',success:result=>{if(result.confirm)void commit(true)}})
      return
    }
    const revision=sessionRevision()
    cloudSaving.value=true;cloudError.value=''
    try {
      let receipt=null
      if(invited.value){
        const saved=await saveCloudProfile(profile.value,{reviewOnly:true})
        if(!alive||revision!==sessionRevision())return
        profile.value=saved
      }else receipt=await submitOnboardingPreparation(profile.value,{consentAccepted})
      if(!alive)return
      if(revision!==sessionRevision()){clearPrivate();cloudError.value='账号或家庭已变化，请重新读取档案。';return}
      completed=true
      scopedStorage.setStorageSync('frontend-onboarded-v1',true)
      uni.setStorageSync(draftStorageKey,null)
      uni.setStorageSync(draftStorageKey+':conflict',null)
      uni.reLaunch({url:invited.value?'/pages/chat/index?from=onboarding':preparationRoute(receipt)})
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
 <OnboardingLayout :title="invited?'完善本人档案':'建立营养档案'" :heading="heading" :description="description" :step="step" @back="step>0?step--:backHome()">
  <text v-if="cloudLoading" class="form-note">正在读取云端档案…</text>
  <view v-if="cloudError" class="form-notice" role="alert"><text>{{cloudError}}</text><button @click="recoverCloud">{{Number(cloudErrorCode)===401?'重新登录':cloudLoaded?'重试保存':'重新读取档案'}}</button></view>
  <view v-if="conflictDraft&&cloudLoaded" class="form-notice"><text>上次未保存的内容已保留，请对照当前档案核对。</text><button @click="showConflictDraft=!showConflictDraft">{{showConflictDraft?'收起':'查看上次填写'}}</button><MemberFields v-if="showConflictDraft" v-for="m in conflictDraft.members" :key="m.id" :member="m" read-only :sections="['basic','disease','preferences','restrictions']"/></view>
  <template v-if="!cloudLoading&&cloudLoaded&&current">
   <view v-if="step===0&&!invited" class="usage-block"><text class="small-label">这份照顾，为谁准备？</text><view class="usage-choice"><button v-for="item in [{v:'个人使用',t:'只为自己',icon:'user'},{v:'家庭使用',t:'自己和家人',icon:'family'}]" :key="item.v" class="usage-option" :class="{active:profile.usageMode===item.v}" :aria-pressed="profile.usageMode===item.v" @click="mode(item.v)"><AppIcon :name="item.icon" :size="30"/><text>{{item.t}}</text><view v-if="profile.usageMode===item.v" class="usage-check">✓</view></button></view></view>
   <view v-if="!solo" class="family-members"><text class="small-label">为谁填写</text><view class="member-choices"><button v-for="m in visibleMembers" :key="m.id" :class="{active:current.id===m.id}" @click="selectMember(m.id)"><text class="member-initial">{{(m.name||'家').slice(0,1)}}</text><view><text class="member-name">{{m.name||'未命名成员'}}</text><text class="member-completion">{{memberComplete(m)?'本步已完成':'待补充'}}</text></view></button><button v-if="step!==1" class="add-member" @click="add">＋ 添加家人</button></view></view>
   <view id="onboarding-fields"><text v-if="fieldError" class="form-error" role="alert">{{fieldError}}</text><OnboardingBasics v-if="step===0" :key="current.id" :member="current" :show-relationship="String(current.id)!==String(self?.id)" onboarding/><OnboardingHealthFields v-else-if="step===1" :key="current.id" :member="current" onboarding/><template v-else><MemberRestrictionsFields :key="current.id" :member="current" onboarding/><view class="report-later"><view class="report-icon"><AppIcon name="record" :size="34"/></view><view class="report-copy"><text class="report-title">体检报告，可以稍后补充</text><text class="form-note">完成后可在家庭档案中上传</text></view><text class="optional-badge">可选</text></view></template></view>
   <view v-if="step===0&&!solo" class="diner-section"><text class="small-label">通常一起吃饭的是哪些人？</text><view class="diner-choices"><button v-for="m in profile.members" :key="m.id" role="checkbox" :aria-checked="profile.defaultDiners.includes(m.id)" :class="{selected:profile.defaultDiners.includes(m.id)}" @click="toggleDiner(m.id)">{{profile.defaultDiners.includes(m.id)?'✓ ':''}}{{m.name||'未命名成员'}}</button></view><text class="form-note">默认按 {{dinerCount}} 人安排，每餐可以调整。</text></view>
    <text v-if="step===2&&!isMockMode&&!invited" class="form-note preparation-disclosure">完成前请核对咨询与配餐的数据处理方及政策版本，并明确选择是否同意。确认后保存档案，等待今日安排准备完成。</text>
    <view v-if="step===2&&!isMockMode&&!invited" class="processing-policy"><text v-if="processingPolicyReady">咨询处理方：{{profile.healthConfiguration.consultation.processor}}；配餐处理方：{{profile.healthConfiguration.meal_plan.processor}}；政策版本：{{profile.healthConfiguration.policy_version}}</text><text v-else>处理说明暂未就绪</text><button v-if="!processingPolicyReady" :disabled="policyLoading" @click="reloadProcessingPolicy">{{policyLoading?'正在读取…':'重新读取处理说明'}}</button></view>
   <view v-if="step<2" class="draft-note"><AppIcon name="shield" :size="24"/><text>填写内容自动暂存，可随时继续</text></view><text v-if="isMockMode" class="preview-note">前端体验版 · 请使用虚构资料</text>
  </template>
  <template #footer><button class="onboarding-next" :disabled="cloudSaving||cloudLoading||!cloudLoaded||!current" @click="next"><text>{{step===2?(cloudSaving?'正在保存…':invited?'保存，进入家庭':'完成建档，开始对话'):step===0?'下一步，饮食偏好':'下一步，饮食限制'}}</text><text class="next-arrow" aria-hidden="true">→</text></button><text class="footer-note">之后也可以在家庭档案中修改</text></template>
 </OnboardingLayout>
</template>
<style scoped>
.usage-block{margin-bottom:18px}.small-label{font-weight:600;display:block;margin-bottom:9px;color:#747d97;font-size:11px;line-height:1.6}.usage-choice{display:flex;gap:6px;padding:5px;border:1px solid rgba(255,255,255,.8);border-radius:16px;background:rgba(255,255,255,.36)}.usage-option{font-weight:600;display:flex;align-items:center;justify-content:center;gap:9px;flex:1;min-width:0;min-height:44px;padding:9px 8px;border:1px solid transparent;border-radius:12px;background:transparent;color:#858ba0;font-size:13px;line-height:1.5}.usage-option.active{background:rgba(255,255,255,.95);border-color:#fff;color:#7660ad;box-shadow:0 2px 7px rgba(65,69,105,.04)}.usage-check{font-weight:600;display:flex;align-items:center;justify-content:center;width:15px;height:15px;border-radius:50%;background:#ede8f8;font-size:10px}
.family-members{margin-bottom:18px}.member-choices{display:flex;flex-wrap:wrap;gap:8px;align-items:stretch}.member-choices button{display:flex;align-items:center;gap:9px;min-width:0;max-width:100%;min-height:54px;padding:9px 12px;border:1px solid rgba(255,255,255,.8);border-radius:15px;background:rgba(255,255,255,.45);text-align:left;line-height:1.5}.member-choices button.active{border-color:#fff;background:#fff;box-shadow:0 3px 12px rgba(65,69,105,.04)}.member-choices button>view{min-width:0}.member-initial{display:flex;align-items:center;justify-content:center;flex:none;width:30px;height:30px;border:1px solid #fff;border-radius:50%;background:#eae6f8;color:#8672ba;font-size:13px}.member-name{font-weight:600;display:block;font-size:13px;color:#55566f;overflow-wrap:anywhere}.member-completion{display:block;margin-top:3px;font-size:10px;color:#8a90a5}.member-choices .add-member{min-height:44px;background:transparent;border-color:#d6daeb;border-style:dashed;color:#8986a4;font-size:12px}
.diner-section{margin-top:14px;padding:18px;border:1px solid rgba(255,255,255,.95);border-radius:20px;background:rgba(255,255,255,.77)}.diner-choices{display:flex;flex-wrap:wrap;gap:8px}.diner-choices button{font-weight:600;min-height:44px;padding:10px 15px;border:1px solid #e9eaf2;border-radius:12px;background:#f7f8fc;color:#858ba1;font-size:13px;line-height:1.5}.diner-choices button.selected{background:#f0ecfa;border-color:#d5c9ec;color:#7863a7}
.draft-note{display:flex;align-items:center;justify-content:center;gap:6px;margin-top:19px;color:#8b91a6;font-size:10px;line-height:1.7}.preview-note{display:block;margin-top:9px;text-align:center;color:#8b91a6;font-size:10px}.form-note{display:block;margin:10px 0 0;color:#858ca2;font-size:11px;line-height:1.8}.form-error{display:block;margin-bottom:14px;padding:10px 14px;border-radius:12px;background:#fff2ee;color:#a96156;font-size:12px;line-height:1.7}.form-notice{margin-bottom:14px;padding:16px;border:1px solid #fff;border-radius:18px;background:rgba(255,255,255,.85);color:#75627f;font-size:12px;line-height:1.8}.form-notice button{min-height:44px;margin-top:8px;color:#7660ad;font-size:13px}.preparation-disclosure{padding:0 8px}
.report-later{display:flex;align-items:center;gap:12px;margin-top:14px;padding:17px 16px;border:1px solid rgba(255,255,255,.9);border-radius:20px;background:rgba(255,255,255,.5)}.report-icon{display:flex;align-items:center;justify-content:center;flex:none;width:35px;height:39px;border-radius:11px;background:#e9e8f6;color:#9686b5}.report-copy{flex:1;min-width:0}.report-title{font-weight:600;display:block;font-size:12px;color:#666b83}.report-later .form-note{margin-top:4px;font-size:10px}.optional-badge{flex:none;color:#9296ac;font-size:10px}
 .processing-policy{margin:14px 8px 0;padding:12px;border-radius:12px;background:#fff;color:#635977;font-size:11px;line-height:1.8;overflow-wrap:anywhere}.processing-policy>text{display:block}.processing-policy button{min-height:44px;margin-top:8px;color:#66509e;font-size:12px}
.onboarding-next{font-weight:600;display:flex;align-items:center;justify-content:center;gap:14px;width:100%;min-height:50px;padding:12px 18px;border:1px solid rgba(255,255,255,.15);border-radius:17px;background:#7964b2;color:#fff;font-size:15px;line-height:1.6;box-shadow:0 5px 15px rgba(92,78,151,.12)}.onboarding-next::after{border:0}.onboarding-next:active{background:#6c59a3}.onboarding-next[disabled]{opacity:.5}.next-arrow{font-size:20px;font-weight:400;line-height:1}.footer-note{font-weight:500;display:block;margin-top:9px;text-align:center;font-size:10px;line-height:1.6;color:#9197ad}
@media(max-width:350px){.usage-option{font-size:12px;gap:6px}.member-choices button{padding:8px 10px}.onboarding-next{font-size:14px}}
</style>
