<script setup>
import { computed,ref } from 'vue'
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
const props=defineProps({id:String,shareReady:Boolean,scrollTop:{type:Number,default:0}})
const profile=ref(null),draft=ref(null),editing=ref(false),busy=ref(false),error=ref(''),records=ref([]),dietError=ref(''),reportError=ref('')
const member=computed(()=>profile.value?.members.find(m=>String(m.id)===props.id))
const source=ref(null),additional=ref({}),analysis=ref(null),analysisError=ref(''),analysisBusy=ref(false),writeUncertain=ref(false)
const canEdit=computed(()=>!!source.value?.editable_fields?.length&&(source.value.is_self||source.value.is_guardian||profile.value?.isOwner))
const canAnalyze=computed(()=>source.value?.is_self||source.value?.is_guardian)
const analysisEntry=computed(()=>analysis.value?.entries?.find(e=>e.entry_type==='consultation'))
const labels={breakfast:'早餐',lunch:'午餐',dinner:'晚餐',snack:'加餐'}
let epoch=0,loadedRevision=-1
const section=ref('basic'),conflictEdit=ref(null),showConflictEdit=ref(false)
const sections=[{key:'basic',label:'基本资料'},{key:'health',label:'健康情况'},{key:'preferences',label:'饮食偏好'},{key:'restrictions',label:'饮食限制'}]
function cancelEdit(){clearMemberEdit(props.id);draft.value=null;additional.value=profileDraft(source.value.profile);editing.value=false;conflictEdit.value=null}
function back(){if(editing.value){cancelEdit();return}uni.navigateBack()}
function report(){if(member.value?.healthMemberId)uni.navigateTo({url:'/pages/health/vision?kind=report&memberId='+encodeURIComponent(member.value.healthMemberId)})}
function history(){uni.navigateTo({url:'/pages/family-shared/index?memberId='+encodeURIComponent(member.value.id)})}
function hide(){if(loadedRevision===sessionRevision()&&editing.value&&draft.value)preserveMemberEdit({id:props.id,source:source.value,draft:draft.value,additional:additional.value,section:section.value,uncertain:writeUncertain.value});epoch++;conflictEdit.value=null;showConflictEdit.value=false;source.value=null;analysis.value=null;additional.value={};analysisError.value='';analysisBusy.value=false;writeUncertain.value=false;profile.value=null;records.value=[];busy.value=false;error.value='';dietError.value='';reportError.value='';draft.value=null;editing.value=false}
async function load(){if(busy.value)return;const mine=++epoch,rev=sessionRevision();busy.value=true;error.value='';editing.value=false;draft.value=null;profile.value=null;source.value=null;analysis.value=null;analysisError.value='';dietError.value='';reportError.value='';records.value=[];try{const loaded=await readMemberProfile(props.id);if(mine!==epoch||rev!==sessionRevision())return;const p=loaded.profile;profile.value=p;source.value=loaded.source;additional.value=profileDraft(source.value.profile);writeUncertain.value=false;loadedRevision=rev;
 const cached=readMemberEdit(props.id,source.value);conflictEdit.value=null;
 if(cached){if(cached.conflict)conflictEdit.value=cached;else if(canEdit.value){draft.value=cached.draft;additional.value=cached.additional;section.value=sections.some(s=>s.key===cached.section)?cached.section:'basic';editing.value=true}}
 if(!member.value)throw new Error('这位成员已不在当前家庭，请返回重新选择');if(member.value.healthMemberId){try{const {data}=await request({path:'/api/health/v1/members/'+member.value.healthMemberId+'/readiness'});if(mine!==epoch||rev!==sessionRevision())return;analysis.value=data}catch(e){if(mine===epoch)analysisError.value=e.message}try{const status=await readCloudReportStatus(member.value.healthMemberId);if(mine!==epoch||rev!==sessionRevision())return;member.value.reportStatus=status;if(draft.value)draft.value.reportStatus=status}catch(e){if(mine===epoch)reportError.value=e.message}try{const {data}=await request({path:'/api/health/v1/members/'+member.value.healthMemberId+'/diet-logs'});if(mine!==epoch||rev!==sessionRevision())return;records.value=data.filter(r=>mealDate(r.snapshot?.meal?.eaten_at)===localDate())}catch(e){if(mine===epoch)dietError.value=e.message}}else dietError.value='尚未开始健康分析，已有家庭资料已保存。'}catch(e){if(mine===epoch){if(rev!==sessionRevision()||[401,403,404,410].includes(Number(e.code))){hide();error.value='当前授权或来源已变化，请重新读取。'}else error.value=e.message}}finally{if(mine===epoch){if(rev!==sessionRevision())hide();else busy.value=false}}}
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
  const mine=epoch,rev=sessionRevision();busy.value=true;error.value=''
  try{
    await saveMemberProfile(profile.value.householdId,source.value,member.value,draft.value,profileChanges(additional.value,source.value))
    if(mine!==epoch||rev!==sessionRevision())return
    clearMemberEdit(props.id);editing.value=false;draft.value=null;busy.value=false;await load()
  }catch(e){if(mine===epoch){writeUncertain.value=e.partialSave||e.code==='NETWORK_ERROR'||Number(e.code)>=500||Number(e.code)===409;error.value=e.message;if(rev!==sessionRevision()||[401,403,404,410].includes(Number(e.code))){hide();error.value='当前授权或来源已变化，请重新读取。'}}}
  finally{if(mine===epoch)busy.value=false}
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
</script>
<template>
 <ProfileFormLayout :title="editing?'修改营养档案':'营养档案'" :heading="editing?'让建议更了解你':(member?.name||'成员')+'的营养档案'" :description="member?ageLabel(member)+' · '+member.gender+' · '+member.relation:'每位成员的资料独立保存'" :scroll-top="scrollTop" @back="back">
  <template #navigation><view class="profile-tabs" role="tablist" aria-label="档案分类"><button v-for="s in sections" :key="s.key" role="tab" :aria-selected="section===s.key" :class="{active:section===s.key}" @click="section=s.key">{{s.label}}</button></view></template>
  <text v-if="busy" class="form-note">正在核对档案…</text><view v-if="error" class="form-notice" role="alert"><text>{{error}}</text><button :disabled="busy" @click="load">重新读取</button></view>
  <template v-if="member">
   <view v-if="conflictEdit" class="form-notice"><text>资料已变化，上次未保存的内容仍保留，请核对当前资料后再修改。</text><button @click="showConflictEdit=!showConflictEdit">{{showConflictEdit?'收起':'查看上次填写'}}</button><MemberFields v-if="showConflictEdit" :member="conflictEdit.draft" read-only :show-relationship="!source.is_self" :sections="['basic','restrictions']" inline-restrictions/></view>
   <template v-if="editing&&draft">
    <view v-show="section==='basic'" class="form-block"><MemberFields :member="draft" :source="source" :show-relationship="!source.is_self" :sections="['basic']"/></view>
    <view v-show="section==='health'" class="form-block"><MemberFields :member="draft" :source="source" :sections="['disease']"/><MemberAdditionalFields :draft="additional" :source="source" editing section="health"/></view>
    <view v-show="section==='preferences'" class="form-block"><MemberFields :member="draft" :source="source" :sections="['preferences']"/><MemberAdditionalFields :draft="additional" :source="source" editing section="preferences"/></view>
    <view v-show="section==='restrictions'" class="form-block"><MemberFields :member="draft" :source="source" :sections="['restrictions']" inline-restrictions/><MemberAdditionalFields :draft="additional" :source="source" editing section="restrictions"/></view>
    <text class="form-note">分类切换会保留填写内容，完成后统一保存。</text>
   </template>
   <template v-else>
    <view class="archive-summary"><view class="summary-name"><text class="summary-avatar">{{member.name.slice(0,1)}}</text><view><text class="summary-title">{{member.name}}</text><text class="summary-caption">已保存的营养资料</text></view><button v-if="canEdit" :disabled="busy||writeUncertain" @click="edit">修改资料 ›</button></view><view class="summary-grid"><view><text>身高</text><text>{{member.height?member.height+' cm':'待补充'}}</text></view><view><text>体重</text><text>{{member.weight?member.weight+' kg':'待补充'}}</text></view></view></view>
    <view v-show="section==='basic'" class="archive-read"><view class="read-row"><text>出生日期</text><text>{{member.birthDate||'待补充'}}</text></view><view class="read-row"><text>性别</text><text>{{member.gender||'未填写'}}</text></view><view class="read-row"><text>与我的关系</text><text>{{member.relation}}</text></view></view>
    <view v-show="section==='health'" class="archive-read"><text class="form-section-title">基础健康</text><text class="read-copy">{{member.healthStatus==='set'?member.conditions.join('、'):member.healthStatus==='none'?'没有已知基础病':'未填写'}}</text><text class="form-note">用户自述 · {{diseaseSummary(member)}}</text><MemberAdditionalFields :draft="additional" :source="source" :editing="false" section="health"/></view>
    <view v-show="section==='preferences'" class="archive-read"><view v-for="item in [{t:'饮食目标',v:member.goals},{t:'口味',v:member.tastePreferences},{t:'菜系',v:member.cuisines}]" :key="item.t" class="read-row"><text>{{item.t}}</text><text>{{item.v.join('、')||'待补充'}}</text></view><MemberAdditionalFields :draft="additional" :source="source" :editing="false" section="preferences"/></view>
    <view v-show="section==='restrictions'" class="archive-read"><MemberFields :member="member" read-only :sections="['restrictions']" inline-restrictions/><MemberAdditionalFields :draft="additional" :source="source" :editing="false" section="restrictions"/></view>
   </template>
   <view class="archive-links"><button :disabled="!member.healthMemberId" @click="report"><view><text>体检报告</text><text>{{!member.healthMemberId?'完成建档后可补充':member.reportStatus==='done'?'已核对':member.reportStatus==='review'?'待核对':'可后补'}}</text></view><text>›</text></button><button @click="history"><view><text>实测指标与修改历史</text><text>查看记录</text></view><text>›</text></button></view><text v-if="reportError" class="form-error">{{reportError}}</text>
   <template v-if="!editing"><button v-if="profile?.isOwner&&!member.claimed" class="archive-share" open-type="share" :disabled="!shareReady">邀请本人加入</button><view class="daily-archive"><text class="form-section-title">今日饮食记录</text><text v-if="dietError" class="form-error">{{dietError}}</text><button v-for="r in records" :key="r.id" class="record" @click="record(r)"><text>{{labels[r.snapshot.meal.meal_type]}}</text><text>{{r.snapshot.meal.items.filter(i=>!i.excluded).map(i=>i.name).join('、')}} ›</text></button><text v-if="!records.length&&!dietError" class="form-note">今天尚未保存饮食记录，不代表没有用餐。</text></view><view class="analysis-block"><text class="form-section-title">营养咨询</text><text v-if="!canAnalyze" class="form-note">该成员本人登录并完成建档后即可使用营养咨询。</text><template v-else><text v-if="analysisError" class="form-error">{{analysisError}}</text><button v-if="analysisEntry?.status==='available'" class="archive-share" @click="consult">开始对话 ›</button><text v-else-if="!analysisError" class="form-note">{{analysisEntry?.reason_code==='consent_required'?'营养咨询已停用。':'档案或咨询服务尚未就绪，请重新读取。'}}</text><button v-if="member.healthMemberId" class="archive-share" :disabled="analysisBusy||busy" @click="revokeAnalysis">停用营养咨询</button></template></view></template>
  </template>
  <template #footer><template v-if="editing"><button class="form-cancel" :disabled="busy" @click="cancelEdit">取消</button><button :disabled="busy||analysisBusy||writeUncertain" @click="save">{{busy?'正在保存…':'保存修改'}}</button></template><button v-else-if="canEdit" :disabled="busy||analysisBusy||writeUncertain" @click="edit">修改资料</button><button v-else @click="back">返回</button></template>
 </ProfileFormLayout>
</template>
<style scoped>
.archive-summary{padding:18px;margin:0 0 24px;border-radius:17px;background:#f7f4fb}.summary-name{display:flex;align-items:center;gap:11px}.summary-avatar{display:flex;align-items:center;justify-content:center;width:39px;height:39px;border-radius:50%;background:#e8dff3;color:#9b7bb8;font-size:17px}.summary-title{display:block;font-size:16px;font-weight:600;color:#715985}.summary-caption{display:block;margin-top:5px;font-size:10px;color:#aa98b9}.summary-name button{margin-left:auto;min-height:44px;font-size:11px;color:#9d80b5}.summary-grid{display:flex;gap:20px;margin-top:18px;padding-top:16px;border-top:1px solid #eae1f2}.summary-grid>view{flex:1}.summary-grid text{display:block;font-size:11px;color:#aa99b7}.summary-grid text+text{margin-top:7px;font-size:16px;color:#806390;font-weight:500}.archive-read{margin-bottom:22px}.read-row{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;min-height:49px;padding:15px 0;border-bottom:1px solid #f0edf4;font-size:13px;line-height:1.7}.read-row>text:first-child{flex-shrink:0;color:#a08cae}.read-row>text:last-child{text-align:right;color:#74617f}.read-copy{font-size:14px;line-height:1.8;color:#80708b}.archive-links{padding-top:5px;margin-top:20px}.archive-links>button{display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%;min-height:56px;padding:15px 0;border-top:1px solid #f0edf4;text-align:left;color:#9e88af;font-size:20px}.archive-links>button>view{display:flex;align-items:center;justify-content:space-between;gap:15px;flex:1;font-size:13px;color:#8d769f}.archive-links>button>view>text+text{color:#b3a5bc;font-size:11px}.archive-share{min-height:44px;color:#9474ac;font-size:13px;text-align:left}.daily-archive,.analysis-block{margin-top:26px;padding-top:22px;border-top:1px solid #f0edf4}.record{width:100%;text-align:left;font-size:13px;line-height:1.8;color:#967ba8}.record text{display:block}
</style>
