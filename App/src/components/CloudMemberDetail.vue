<script setup>
import { computed,ref,onMounted,onUnmounted } from 'vue'
import { onShow,onHide,onUnload } from '@dcloudio/uni-app'
import ProfileFormLayout from './ProfileFormLayout.vue'
import {preserveMemberEdit,readMemberEdit,clearMemberEdit} from '../services/member-edit-draft.js'
import MemberFields from './MemberFields.vue'
import { readCloudReportStatus } from '../services/cloud-profile.js'
import { readMemberProfile, saveMemberProfile } from '../services/member-profile.js'
import { profileDraft, profileChanges } from '../services/family-archive-fields.js'
import MemberAdditionalFields from './MemberAdditionalFields.vue'
import { request } from '../services/request.js'
import { sessionRevision } from '../services/session.js'
import { ageLabel } from '../utils/member-age.js'
import { diseaseSummary,restrictionFields } from '../utils/health.js'
import {restrictionIssue} from '../utils/onboarding-validation.js'
import { localDate } from '../utils/meal-state.js'
import { mealDate } from '../services/diet-journal-client.js'
// Keep the sheet's flex containers adjacent in WeChat's native component tree.
defineOptions({options:{virtualHost:true}})
const props=defineProps({id:String,shareReady:Boolean,scrollTop:{type:Number,default:0},initialSection:String,embedded:Boolean})
const emit=defineEmits(['close','saved'])
const writing=ref(false)
const profile=ref(null),draft=ref(null),editing=ref(false),busy=ref(false),error=ref(''),records=ref([]),dietError=ref(''),reportError=ref('')
const member=computed(()=>profile.value?.members.find(m=>String(m.id)===props.id))
const source=ref(null),additional=ref({}),analysis=ref(null),analysisError=ref(''),analysisBusy=ref(false),writeUncertain=ref(false)
const canEdit=computed(()=>!!source.value?.editable_fields?.length&&(source.value.is_self||source.value.is_guardian||profile.value?.isOwner))
const canAnalyze=computed(()=>source.value?.is_self||source.value?.is_guardian)
const analysisEntry=computed(()=>analysis.value?.entries?.find(e=>e.entry_type==='consultation'))
const labels={breakfast:'早餐',lunch:'午餐',dinner:'晚餐',snack:'加餐'}
let epoch=0,loadedRevision=-1,initialSectionApplied=false
const section=ref('basic'),conflictEdit=ref(null),showConflictEdit=ref(false)
const sections=[{key:'basic',label:'基本资料'},{key:'health',label:'健康情况'},{key:'preferences',label:'饮食偏好'},{key:'restrictions',label:'饮食限制'}]
const dirty=computed(()=>editing.value&&draft.value&&(JSON.stringify(draft.value)!==JSON.stringify(member.value)||JSON.stringify(additional.value)!==JSON.stringify(profileDraft(source.value?.profile||{}))))
function discardEdit(){clearMemberEdit(props.id);draft.value=null;additional.value=profileDraft(source.value?.profile||{});editing.value=false;conflictEdit.value=null}
function cancelEdit(){if(props.embedded&&dirty.value){const mine=epoch,rev=sessionRevision();uni.showModal({title:'放弃本次修改？',content:'将恢复为上次保存的资料。',cancelText:'继续填写',confirmText:'放弃修改',success:r=>{if(r.confirm&&mine===epoch&&rev===sessionRevision())discardEdit()}});return}discardEdit()}
function stash(){if(loadedRevision===sessionRevision()&&editing.value&&draft.value)preserveMemberEdit({id:props.id,source:source.value,draft:draft.value,additional:additional.value,section:section.value,uncertain:writeUncertain.value||writing.value})}
function requestClose(){
 if(writing.value||analysisBusy.value){uni.showToast({title:'正在保存，请稍候',icon:'none'});return}
 if((editing.value&&dirty.value)||writeUncertain.value){const mine=epoch,rev=sessionRevision();uni.showModal({title:'修改还未保存',content:writeUncertain.value?'上次保存结果还需核对，暂存后下次重新读取确认。':'可以暂存本次填写，下次打开时继续；暂存不会更新云端档案。',cancelText:'继续填写',confirmText:'暂存并关闭',success:r=>{if(r.confirm&&mine===epoch&&rev===sessionRevision()){stash();emit('close')}}});return}
 if(editing.value)discardEdit();emit('close')
}
function back(){if(props.embedded){requestClose();return}if(editing.value){cancelEdit();return}uni.navigateBack()}
function reload(){if(writing.value)return;if(props.embedded)stash();return load()}
defineExpose({requestClose})
function report(){if(member.value?.healthMemberId)uni.navigateTo({url:'/pages/health/vision?kind=report&memberId='+encodeURIComponent(member.value.healthMemberId)})}
function invite(){uni.navigateTo({url:'/pages/profile/member?id='+encodeURIComponent(props.id)})}
function history(){uni.navigateTo({url:'/pages/family-shared/index?memberId='+encodeURIComponent(member.value.id)})}
function hide(){stash();epoch++;conflictEdit.value=null;showConflictEdit.value=false;source.value=null;analysis.value=null;additional.value={};analysisError.value='';analysisBusy.value=false;writeUncertain.value=false;writing.value=false;profile.value=null;records.value=[];busy.value=false;error.value='';dietError.value='';reportError.value='';draft.value=null;editing.value=false}
async function load(){if(busy.value)return;const mine=++epoch,rev=sessionRevision();busy.value=true;error.value='';editing.value=false;draft.value=null;profile.value=null;source.value=null;analysis.value=null;analysisError.value='';dietError.value='';reportError.value='';records.value=[];try{const loaded=await readMemberProfile(props.id,{readOnly:props.embedded===true});if(mine!==epoch||rev!==sessionRevision())return;const p=loaded.profile;profile.value=p;source.value=loaded.source;additional.value=profileDraft(source.value.profile);writeUncertain.value=false;loadedRevision=rev;
 if(!initialSectionApplied){section.value=sections.some(s=>s.key===props.initialSection)?props.initialSection:'basic';initialSectionApplied=true}
 const cached=readMemberEdit(props.id,source.value);conflictEdit.value=null;
 if(cached){if(cached.conflict)conflictEdit.value=cached;else if(canEdit.value){draft.value=cached.draft;additional.value=cached.additional;section.value=sections.some(s=>s.key===cached.section)?cached.section:'basic';editing.value=true}}
 if(!member.value)throw new Error('这位成员已不在当前家庭，请返回重新选择');if(member.value.healthMemberId){if(props.embedded)void extras(member.value,mine,rev);else await extras(member.value,mine,rev)}else dietError.value='尚未开始健康分析，已有家庭资料已保存。'}catch(e){if(mine===epoch){if(rev!==sessionRevision()||[401,403,404,410].includes(Number(e.code))){hide();error.value='当前授权或来源已变化，请重新读取。'}else error.value=e.message}}finally{if(mine===epoch){if(rev!==sessionRevision())hide();else busy.value=false}}}
async function extras(person,mine,rev){
 const current=()=>mine===epoch&&rev===sessionRevision()
 await Promise.all([
  readCloudReportStatus(person.healthMemberId).then(status=>{if(current()){person.reportStatus=status;if(draft.value)draft.value.reportStatus=status}}).catch(e=>{if(current())reportError.value=e.message}),
 ])
}

function edit(){if(!canEdit.value)return;draft.value=JSON.parse(JSON.stringify(member.value));additional.value=profileDraft(source.value.profile);editing.value=true}
async function save(){
  if(busy.value||analysisBusy.value||writeUncertain.value||!canEdit.value||!draft.value)return
  if(!draft.value.name?.trim()){error.value='请填写姓名／称呼';section.value='basic';return}
  for(const type of [...Object.keys(restrictionFields),'doctor']){
    const cfg=restrictionFields[type],status=cfg?.status||'doctorStatus',field=cfg?.field||'clinicianGuidance'
    const text=cfg&&draft.value['restrictionDraft_'+type]?.trim()
    if(text&&draft.value[status]==='set'){if(!draft.value[field].includes(text))draft.value[field].push(text);draft.value['restrictionDraft_'+type]=''}
    if(JSON.stringify(member.value[status])!==JSON.stringify(draft.value[status])||JSON.stringify(member.value[field])!==JSON.stringify(draft.value[field])){const issue=restrictionIssue(draft.value,type);if(issue){error.value=issue.message;section.value='restrictions';return}}
  }
  const mine=epoch,rev=sessionRevision();busy.value=true;writing.value=true;error.value=''
  try{
    await saveMemberProfile(profile.value.householdId,source.value,member.value,draft.value,profileChanges(additional.value,source.value))
    if(mine!==epoch||rev!==sessionRevision())return
    clearMemberEdit(props.id);editing.value=false;draft.value=null;busy.value=false;await load()
    if(mine+1===epoch&&rev===sessionRevision()&&profile.value&&!error.value){emit('saved',profile.value);if(props.embedded)uni.showToast({title:'档案已保存',icon:'success'})}
  }catch(e){if(mine===epoch){writeUncertain.value=e.partialSave||e.code==='NETWORK_ERROR'||Number(e.code)>=500||Number(e.code)===409;error.value=e.message;if(rev!==sessionRevision()||[401,403,404,410].includes(Number(e.code))){hide();error.value='当前授权或来源已变化，请重新读取。'}}}
  finally{if((mine===epoch||mine+1===epoch)&&rev===sessionRevision()){busy.value=false;writing.value=false}}
}
async function revokeAnalysis(){
  if(analysisBusy.value||!member.value?.healthMemberId||!canAnalyze.value)return
  const mine=epoch,rev=sessionRevision();analysisBusy.value=true;analysisError.value=''
  try{await request({path:`/api/health/v1/members/${member.value.healthMemberId}/processing-consents`,method:'POST',data:{purpose:'consultation',accepted:false,processor:profile.value.analysisPolicy?.processor||'withdrawn',policy_version:profile.value.analysisPolicy?.policy_version||'withdrawn'}});if(mine!==epoch||rev!==sessionRevision())return;analysisBusy.value=false;await load()}
  catch(e){if(mine===epoch)analysisError.value=e.message}finally{if(mine===epoch)analysisBusy.value=false}
}
function consult(){if(member.value?.healthMemberId)uni.navigateTo({url:'/pages/chat/agent?memberId='+encodeURIComponent(member.value.healthMemberId)+'&taskType=consultation'})}
function record(r){uni.navigateTo({url:'/pages/records/detail?id='+encodeURIComponent(r.id)+'&memberId='+encodeURIComponent(member.value.healthMemberId)})}
onShow(load);onHide(hide);onUnload(hide)
onMounted(()=>{if(props.embedded)void load()});onUnmounted(hide)
</script>
<template>
 <view class="member-detail-shell" :class="{'is-embedded':embedded}">
 <ProfileFormLayout :sheet="embedded" :title="editing?'修改营养档案':'营养档案'" :heading="editing?'让建议更了解你':(member?.name||'成员')+'的营养档案'" :description="member?ageLabel(member)+' · '+member.gender+' · '+member.relation:'每位成员的资料独立保存'" :scroll-top="scrollTop" @back="back">
  <template #navigation><view class="archive-tabs" role="tablist" aria-label="档案分类"><button v-for="s in sections" :key="s.key" class="archive-tab" role="tab" :aria-selected="section===s.key" :class="{'is-active':section===s.key}" @click="section=s.key">{{s.label}}</button></view></template>
  <text v-if="busy" class="form-note">正在核对档案…</text><view v-if="error" class="form-notice" role="alert"><text>{{error}}</text><button :disabled="busy" @click="reload">{{embedded?'重新读取并核对':'重新读取'}}</button></view>
  <template v-if="member">
   <view v-if="conflictEdit" class="form-notice"><text>资料已变化，上次未保存的内容仍保留，请核对当前资料后再修改。</text><button @click="showConflictEdit=!showConflictEdit">{{showConflictEdit?'收起':'查看上次填写'}}</button><MemberFields :archive="embedded" v-if="showConflictEdit" :member="conflictEdit.draft" read-only :show-relationship="!source.is_self" :sections="['basic','disease','preferences','restrictions']" inline-restrictions/><MemberAdditionalFields :archive="embedded" v-if="showConflictEdit" :draft="conflictEdit.additional" :source="source" :editing="false"/></view>
   <template v-if="editing&&draft">
    <view v-show="section==='basic'" class="form-block"><MemberFields :archive="embedded" :member="draft" :source="source" :show-relationship="!source.is_self" :sections="['basic']"/></view>
    <view v-show="section==='health'" class="form-block"><MemberFields :archive="embedded" :member="draft" :source="source" :sections="['disease']"/><MemberAdditionalFields :archive="embedded" :draft="additional" :source="source" editing section="health"/></view>
    <view v-show="section==='preferences'" class="form-block"><MemberFields :archive="embedded" :member="draft" :source="source" :sections="['preferences']"/><MemberAdditionalFields :archive="embedded" :draft="additional" :source="source" editing section="preferences"/></view>
    <view v-show="section==='restrictions'" class="form-block"><MemberFields :archive="embedded" :member="draft" :source="source" :sections="['restrictions']" inline-restrictions/><MemberAdditionalFields :archive="embedded" :draft="additional" :source="source" editing section="restrictions"/></view>
    <text class="form-note">分类切换会保留填写内容，完成后统一保存。</text>
   </template>
   <template v-else>
    <view class="archive-summary"><view class="summary-name"><text class="summary-avatar">{{member.name.slice(0,1)}}</text><view class="summary-copy"><text class="summary-title">{{member.name}}</text><text class="summary-caption">已保存的营养资料</text></view><button v-if="canEdit" class="summary-edit" :disabled="busy||writeUncertain" @click="edit">修改资料 ›</button></view><view class="summary-grid"><view><text class="summary-measure-label">身高</text><text class="summary-measure-value">{{member.height?member.height+' cm':'待补充'}}</text></view><view><text class="summary-measure-label">体重</text><text class="summary-measure-value">{{member.weight?member.weight+' kg':'待补充'}}</text></view></view></view>
    <view v-show="section==='basic'" class="archive-read"><view class="read-row"><text class="read-label">出生日期</text><text class="read-value">{{member.birthDate||'待补充'}}</text></view><view class="read-row"><text class="read-label">性别</text><text class="read-value">{{member.gender||'未填写'}}</text></view><view class="read-row"><text class="read-label">与我的关系</text><text class="read-value">{{member.relation}}</text></view></view>
    <view v-show="section==='health'" class="archive-read"><text class="form-section-title">基础健康</text><text class="read-copy">{{member.healthStatus==='set'?member.conditions.join('、'):member.healthStatus==='none'?'没有已知基础病':'未填写'}}</text><text class="form-note">用户自述 · {{diseaseSummary(member)}}</text><MemberAdditionalFields :archive="embedded" :draft="additional" :source="source" :editing="false" section="health"/></view>
    <view v-show="section==='preferences'" class="archive-read"><view v-for="item in [{t:'饮食目标',v:member.goals},{t:'口味',v:member.tastePreferences},{t:'菜系',v:member.cuisines}]" :key="item.t" class="read-row"><text class="read-label">{{item.t}}</text><text class="read-value">{{item.v.join('、')||'待补充'}}</text></view><MemberAdditionalFields :archive="embedded" :draft="additional" :source="source" :editing="false" section="preferences"/></view>
    <view v-show="section==='restrictions'" class="archive-read"><MemberFields :archive="embedded" :member="member" read-only :sections="['restrictions']" inline-restrictions/><MemberAdditionalFields :archive="embedded" :draft="additional" :source="source" :editing="false" section="restrictions"/></view>
   </template>
   <view class="archive-links"><button :disabled="!member.healthMemberId" @click="report"><view><text>体检报告</text><text>{{!member.healthMemberId?'完成建档后可补充':member.reportStatus==='done'?'已核对':member.reportStatus==='review'?'待核对':'可后补'}}</text></view><text>›</text></button></view><text v-if="reportError" class="form-error">{{reportError}}</text>
   <view v-if="canAnalyze&&!editing" class="analysis-permission"><button v-if="member.healthMemberId" class="archive-share" :disabled="analysisBusy||writing" @click="revokeAnalysis">撤回 AI 咨询授权</button><text v-if="analysisError" class="form-error" role="alert">{{analysisError}}</text></view>
   <template v-if="!editing"><template v-if="profile?.isOwner&&!member.claimed"><button v-if="embedded" class="archive-share" @click="invite">邀请本人加入 ›</button><button v-else class="archive-share" open-type="share" :disabled="!shareReady">邀请本人加入</button></template></template>
  </template>
  <template #footer><view class="profile-footer-actions"><template v-if="editing"><button class="form-cancel archive-cancel" :disabled="busy" @click="cancelEdit">取消</button><button class="archive-submit" :disabled="busy||analysisBusy||writeUncertain" @click="save">{{writing?'正在保存…':'保存修改'}}</button></template><button v-else-if="canEdit" class="archive-submit" :disabled="busy||analysisBusy||writeUncertain" @click="edit">{{embedded?'修改档案':'修改资料'}}</button><button v-else class="archive-submit" @click="back">{{embedded?'关闭档案':'返回'}}</button></view></template>
 </ProfileFormLayout>
 </view>
</template>
<style scoped>
.member-detail-shell{width:100%;min-width:0}.member-detail-shell.is-embedded{display:flex;flex-direction:column;flex:1;height:0;min-height:0}.profile-footer-actions{display:flex;align-items:stretch;gap:12px;flex:1;width:100%;min-width:0}.profile-footer-actions>button{min-width:0;flex:1}.profile-footer-actions>.form-cancel{flex:0 0 80px}
.archive-summary{padding:18px;margin:0 0 24px;border-radius:17px;background:#f7f4fb}.summary-name{display:flex;align-items:center;gap:11px}.summary-avatar{display:flex;align-items:center;justify-content:center;width:39px;height:39px;border-radius:50%;background:#e8dff3;color:#9b7bb8;font-size:17px}.summary-title{display:block;font-size:16px;font-weight:600;color:#715985}.summary-caption{display:block;margin-top:5px;font-size:10px;color:#aa98b9}.summary-name button{margin-left:auto;min-height:44px;font-size:11px;color:#9d80b5}.summary-grid{display:flex;gap:20px;margin-top:18px;padding-top:16px;border-top:1px solid #eae1f2}.summary-grid>view{flex:1}.summary-grid text{display:block;font-size:11px;color:#9b92ac}.summary-grid text+text{margin-top:7px;font-size:16px;color:#806390;font-weight:500}.archive-read{margin-bottom:22px}.read-row{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;min-height:49px;padding:15px 0;border-bottom:1px solid #f0edf4;font-size:13px;line-height:1.7}.read-label{flex-shrink:0}.read-value{text-align:right}.read-copy{font-size:14px;line-height:1.8;color:#80708b}.archive-links{padding-top:5px;margin-top:20px}.archive-links>button{display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%;min-height:56px;padding:15px 0;border-top:1px solid #f0edf4;text-align:left;color:#9e88af;font-size:20px}.archive-links>button>view{display:flex;align-items:center;justify-content:space-between;gap:15px;flex:1;font-size:13px;color:#8d769f}.archive-links>button>view>text+text{color:#b3a5bc;font-size:11px}.archive-share{min-height:44px;color:#9474ac;font-size:13px;text-align:left}

/* Slot content is styled by its owner; no cross-component deep selectors. */
.archive-tabs{display:flex;gap:5px;box-sizing:border-box;width:100%;padding:4px;border-radius:14px;background:#f5f4f8}
.archive-tab{display:flex;align-items:center;justify-content:center;flex:1;min-width:0;min-height:40px;margin:0;padding:7px 3px;border-radius:11px;background:transparent;color:#89818f;font-size:13px;font-weight:500;line-height:1.4;white-space:nowrap}.archive-tab:after{border:0}.archive-tab.is-active{background:#fff;color:#7544e0;font-weight:600;box-shadow:0 1px 4px rgba(66,45,95,.05)}
.summary-avatar{flex:none}.summary-copy{flex:1;min-width:0}.summary-title{font-size:17px;color:#47415d;line-height:1.45;overflow-wrap:anywhere;word-break:break-word}.summary-edit{flex:none;margin:0 0 0 auto;padding:0;white-space:nowrap;line-height:1.5}.summary-caption{color:#878098;font-size:11px}.archive-summary{background:#f3f1ff}.summary-measure-label{font-size:11px;color:#9b92ac}.summary-grid .summary-measure-value{font-size:16px;font-weight:600;color:#575069}.read-row{font-size:14px}.read-label{flex:none;font-weight:600;color:#686a80}.read-value,.read-copy{font-weight:500;color:#3f4055;overflow-wrap:anywhere}
.profile-footer-actions .archive-submit,.profile-footer-actions .archive-cancel{display:flex;align-items:center;justify-content:center;min-height:48px;padding:8px 12px;border:0;border-radius:15px;font-size:16px;font-weight:600;line-height:1.5}.profile-footer-actions .archive-submit{background:linear-gradient(120deg,#9a6cf1,#7340f3);color:#fff}.profile-footer-actions .archive-cancel{background:#f0ecfa;color:#765ba2}.archive-submit:after,.archive-cancel:after{border:0}.profile-footer-actions button[disabled]{opacity:.55}
.form-note{display:block;margin:12px 0;font-size:12px;line-height:1.7;color:#908796}.form-notice{padding:12px 14px;margin-bottom:18px;border-radius:13px;background:#f6f2fa;color:#7a648c;font-size:12px;line-height:1.8}.form-notice button{min-height:40px;color:#7660bc;font-size:13px}.form-block{margin-bottom:26px}.form-section-title{display:block;margin:5px 0 16px;font-size:16px;font-weight:600;color:#3d3852}.form-error{display:block;color:#a45f65;font-size:12px;line-height:1.7;margin:8px 0}
@media(max-width:350px){.archive-tab{font-size:11px}.summary-name{gap:8px}.summary-edit{font-size:10px}}
</style>
