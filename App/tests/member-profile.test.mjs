import {restrictionIssue} from '../src/utils/onboarding-validation.js'
import {restrictionFields} from '../src/utils/health.js'
import {preserveMemberEdit,readMemberEdit,clearMemberEdit} from '../src/services/member-edit-draft.js'
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { ref, computed } from 'vue'
import { memberProfileChanges, saveMemberProfile, startMemberAnalysis } from '../src/services/member-profile.js'
import { setSession } from '../src/services/session.js'
import { profileDraft, profileChanges } from '../src/services/family-archive-fields.js'
import { createFamilyArchivesClient, archiveState } from '../src/services/family-archives-client.js'
import { readCloudReportStatus } from '../src/services/report-entry.js'

function setup(){const values=new Map();globalThis.uni={getStorageSync:k=>values.get(k),setStorageSync:(k,v)=>values.set(k,structuredClone(v))};setSession({accountId:'creator',householdId:'family',token:'synthetic'});return values}
const source=()=>({id:'mother',is_active:true,is_self:false,version:7,relationship_version:2,confirmed:true,editable_fields:['sex','birth_date','height_cm','dietary_details','goal','allergens','avoidances','doctor_instructions'],profile:{dietary_details:{statedWeightKg:55,conditions:['合成情况'],recentNote:'保留原文'},medications:'保留用药记录'}})
const member=()=>({id:'mother',name:'妈妈',relation:'妈妈',weight:55,gender:'女',conditions:['合成情况'],recentNote:'保留原文',allergyStatus:'none',allergies:[],goals:['饮食均衡']})

test('report status checks report grants before reading private reports',async()=>{
  setup();const calls=[]
  const status=await readCloudReportStatus('health',async o=>{calls.push(o.path);return {data:[{id:'health',scopes:['ai_use','diet_edit','profile_view']}]}})
  assert.equal(status,'restricted');assert.deepEqual(calls,['/api/health/v1/members'])
})

test('report status distinguishes an empty authorized archive from missing access and expired login',async()=>{
  const granted=async o=>({data:o.path.endsWith('/members')?[{id:'health',scopes:['report_view']}]:o.path.includes('/observations')?[]:{drafts:[]}})
  assert.equal(await readCloudReportStatus('health',granted),'empty')
  assert.equal(await readCloudReportStatus('health',async()=>({data:[]})),'unavailable')
  assert.equal(await readCloudReportStatus('health',async o=>{if(o.path.endsWith('/members'))return {data:[{id:'health',scopes:['report_view']}]};throw Object.assign(new Error('revoked'),{code:404})}),'restricted')
  await assert.rejects(readCloudReportStatus('health',async()=>{throw Object.assign(new Error('login expired'),{code:401})}),/login expired/)
})

test('family report status uses server member permissions without an enable write',async()=>{
  setup();const calls=[]
  const result=await readCloudReportStatus('health',async o=>{calls.push(o);return {data:o.path.endsWith('/members')?[{id:'health',scopes:['report_view','report_upload','profile_edit']}]:o.path.endsWith('/observations')?[]:{drafts:[]}}})
  assert.equal(result,'empty');assert.equal(calls.length,3);assert.ok(calls.every(o=>!o.method||o.method==='GET'))
})

test('editing a claimed mother changes only her weight without confirming her or submitting consent',async()=>{
  setup();const original=member(),draft={...original,weight:57},calls=[]
  await saveMemberProfile('family',source(),original,draft,{},async options=>{calls.push(options);return {data:{}}})
  assert.equal(calls.length,1);assert.equal(calls[0].path,'/api/family/family/members/mother')
  assert.deepEqual(calls[0].data,{expected_version:7,profile:{dietary_details:{statedWeightKg:57,conditions:['合成情况'],recentNote:'保留原文'}}})
  assert.equal(source().confirmed,true);assert.equal(Object.hasOwn(calls[0].data,'analysis_consent'),false)
})

test('unchanged fields do not overwrite hidden health facts and denied fields fail before a write',()=>{
  const original=member();assert.deepEqual(memberProfileChanges(original,{...original},source()),{})
  assert.throws(()=>memberProfileChanges(original,{...original,weight:57},{...source(),editable_fields:[]}),/不可修改/)
})

test('ordinary whole-family save never adopts the available provider policy as consent',()=>{
  const code=readFileSync(new URL('../src/services/cloud-profile.js',import.meta.url),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
  const input=new Function('newHealthRequestId',code+';return cloudProfileInput')(()=> 'synthetic-id')
  const p={familyVersion:1,members:[member()],defaultDiners:['mother'],analysisPolicy:{processor:'synthetic',policy_version:'v1'}}
  assert.equal(input(p).analysis_consent,null)
  assert.deepEqual(input(p,'id',{...p.analysisPolicy,purpose:'consultation'}).analysis_consent,{processor:'synthetic',policy_version:'v1',purpose:'consultation'})
})

test('unknown analysis submission reuses the exact confirmation receipt',async()=>{
  setup();const calls=[],policy={processor:'synthetic',policy_version:'v1'},person={id:'self',version:3}
  const send=async o=>{calls.push(structuredClone(o));if(calls.length===1)throw Object.assign(new Error('timeout'),{code:'NETWORK_ERROR'});return {data:{}}}
  await assert.rejects(startMemberAnalysis('family',person,policy,'consultation',send))
  await startMemberAnalysis('family',person,policy,'consultation',send)
  assert.deepEqual(calls[0],calls[1]);assert.equal(calls[0].data.action,'start_analysis');assert.equal(calls[0].data.accepted,true)
})

test('explicit confirmation of a newly read version and policy is not stuck behind an old pending request',async()=>{
  setup();const calls=[],policy={processor:'synthetic',policy_version:'v1'},person={id:'self',version:3}
  const send=async o=>{calls.push(structuredClone(o));if(calls.length===1)throw Object.assign(new Error('timeout'),{code:'NETWORK_ERROR'});return {data:{}}}
  await assert.rejects(startMemberAnalysis('family',person,policy,'consultation',send))
  await startMemberAnalysis('family',{...person,version:4},{...policy,policy_version:'v2'},'consultation',send)
  assert.notEqual(calls[0].data.client_request_id,calls[1].data.client_request_id)
  assert.equal(calls[1].data.expected_version,4);assert.equal(calls[1].data.policy_version,'v2')
})

test('partial identity failure requires a reread instead of resubmitting a stale profile',async()=>{
  setup();let calls=0
  await assert.rejects(saveMemberProfile('family',source(),member(),{...member(),weight:57,name:'新称呼'},{},async()=>{
    if(++calls===2)throw Object.assign(new Error('identity conflict'),{code:422})
  }),e=>e.partialSave===true&&/健康资料已保存/.test(e.message))
})

test('a switched account cannot finish another members multi-part save',async()=>{
  setup();const original=member(),calls=[]
  await assert.rejects(saveMemberProfile('family',source(),original,{...original,weight:57,name:'新称呼'},{},async o=>{calls.push(o);setSession({accountId:'other',householdId:'elsewhere',token:'other'})}),/账号或家庭已变化/)
  assert.equal(calls.length,1)
})

test('an unavailable requested member never falls back to the current self',async()=>{
  const state=archiveState(),calls=[]
  const client=createFamilyArchivesClient({state,session:{read:()=>({token:'t',householdId:'family'}),revision:()=>1},send:async o=>{calls.push(o.path);return {data:o.path==='/api/family'?[{id:'family'}]:{id:'family',members:[{id:'self',is_self:true,is_active:true,profile_access:'family_shared'}]}}}})
  await client.refresh('family','removed-mother');assert.equal(state.member,null);assert.match(state.error,/指定成员/);assert.equal(calls.length,2)
})

function detail(overrides={}){
  setup()
  const src=readFileSync(new URL('../src/components/CloudMemberDetail.vue',import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
  const raw=source(),m=member();let revision=1;const writes=[]
  const deps={ref,computed,defineOptions(){},defineProps:()=>({id:'mother'}),defineEmits:()=>()=>{},defineExpose(){},onMounted(){},onUnmounted(){},onShow(){},onHide(){},onUnload(){},sessionRevision:()=>revision,profileDraft,profileChanges,
    restrictionIssue,restrictionFields,preserveMemberEdit,readMemberEdit,clearMemberEdit,readMemberProfile:async()=>({profile:{householdId:'family',isOwner:true,selfMemberId:'creator',members:[m]},member:m,source:raw}),
    saveMemberProfile:async(...args)=>writes.push(args),request:async()=>({data:{}}),...overrides}
  const page=new Function('deps',`const {${Object.keys(deps)}}=deps;${src};return {load,edit,save,hide,cancelEdit,section,conflictEdit,canEdit,profile,source,draft,error,busy,editing,requestClose,reload,writing,dirty,writeUncertain,report,reportError,reportBusy,reportHint,canOpenReport}`)(deps)
  return {...page,writes,changeAccount:()=>revision++}
}

test('self report entry opens the linked member directly without an enable request',async()=>{
  const opened=[]
  const p=detail({readMemberProfile:async()=>({profile:{householdId:'family',members:[{...member(),healthMemberId:'same-health'}]},source:{...source(),is_self:true}}),readCloudReportStatus:async()=> 'empty'})
  uni.navigateTo=o=>opened.push(o.url)
  await p.load();assert.equal(p.reportError.value,'');assert.equal(p.reportHint.value,'可添加')
  await p.report();assert.deepEqual(opened,['/pages/health/vision?kind=report&memberId=same-health'])
})

test('ordinary family members can open the shared members report directly',async()=>{
  const opened=[]
  const p=detail({readMemberProfile:async()=>({profile:{householdId:'family',isOwner:true,members:[{...member(),healthMemberId:'family-health'}]},source:source()}),readCloudReportStatus:async()=> 'empty'})
  uni.navigateTo=o=>opened.push(o.url)
  await p.load();assert.equal(p.reportError.value,'');assert.equal(p.reportHint.value,'可添加');assert.equal(p.canOpenReport.value,true)
  await p.report();assert.deepEqual(opened,['/pages/health/vision?kind=report&memberId=family-health'])
})

test('report navigation ignores overlapping clicks and hidden archives cannot start another navigation',async()=>{
  let resolve;const opened=[]
  const p=detail({readMemberProfile:async()=>({profile:{householdId:'family',members:[{...member(),healthMemberId:'family-health'}]},source:source()}),readCloudReportStatus:async()=> 'empty'})
  uni.navigateTo=o=>{opened.push(o.url);return new Promise(r=>resolve=r)}
  await p.load();const first=p.report();await p.report();assert.equal(opened.length,1)
  p.hide();resolve();await first;await p.report();assert.equal(opened.length,1);assert.equal(p.profile.value,null)
})

test('creator can edit a claimed relative but gets no confirm or analysis authority',async()=>{
  const p=detail();await p.load();assert.equal(p.canEdit.value,true)
  p.edit();p.draft.value.weight=57;await p.save();assert.equal(p.writes.length,1);assert.equal(p.writes[0][1].id,'mother')
  assert.equal(p.busy.value,false)
})

test('a late member read cannot expose an earlier accounts details',async()=>{
  let release;const p=detail({readMemberProfile:()=>new Promise(r=>release=r)})
  const loading=p.load();p.changeAccount();release({profile:{members:[member()]},source:source()});await loading
  assert.equal(p.profile.value,null);assert.equal(p.source.value,null);assert.equal(p.busy.value,false)
})

test('conflict reread discards the old draft so another editors allergy change cannot be overwritten',async()=>{
  let latest=member(),raw=source()
  const p=detail({readMemberProfile:async()=>({profile:{householdId:'family',isOwner:true,members:[latest]},source:raw}),saveMemberProfile:async()=>{throw Object.assign(new Error('conflict'),{code:409})}})
  await p.load();p.edit();p.draft.value.weight=57;await p.save()
  latest={...latest,allergyStatus:'set',allergies:['新的合成过敏原']};raw={...raw,version:8}
  await p.load();assert.equal(p.editing.value,false);assert.equal(p.draft.value,null)
  p.edit();assert.deepEqual(p.draft.value.allergies,['新的合成过敏原']);assert.equal(p.source.value.version,8)
})

test('a verified non-owner guardian retains the unified editor',async()=>{
  const p=detail({readMemberProfile:async()=>({profile:{householdId:'family',isOwner:false,members:[member()]},source:{...source(),is_guardian:true}})})
  await p.load();assert.equal(p.canEdit.value,true)
})

test('profile reading does not write a separate consultation processing consent',async()=>{
  const writes=[]
  const p=detail({readMemberProfile:async()=>({profile:{householdId:'family',analysisPolicy:null,members:[{...member(),healthMemberId:'health'}]},source:{...source(),is_self:true}}),readCloudReportStatus:async()=>{throw new Error('unavailable')},request:async o=>{if(o.method==='POST'){writes.push(o);return {data:{}}}throw new Error('unavailable')}})
  await p.load();assert.equal(writes.length,0)
  const template=readFileSync(new URL('../src/components/CloudMemberDetail.vue',import.meta.url),'utf8')
  assert.doesNotMatch(template,/revokeAnalysis|撤回 AI 咨询授权|AI 咨询需要另行同意/)
})

test('ordinary users have one profile editor and no manual link page',()=>{
  const pages=JSON.parse(readFileSync(new URL('../src/pages.json',import.meta.url),'utf8'))
  assert.equal(pages.pages.some(p=>p.path==='pages/settings/health-profile'),false)
  const history=readFileSync(new URL('../src/pages/family-shared/index.vue',import.meta.url),'utf8')
  assert.doesNotMatch(history,/client\.saveProfile|toggleEditing|为我创建健康档案/)
  assert.match(history,/查看与编辑该成员档案/)
})

test('typed requests can select their own purpose before readiness is checked',()=>{
  const chat=readFileSync(new URL('../src/components/CloudNutritionChat.vue',import.meta.url),'utf8')
  const disabled=chat.match(/class="send-button" aria-label="发送"[^>]*:disabled="([^"]+)"/)[1]
  const canSend=new Function('chatBusy','draftSaving','draftError','task','profileLoading=false','returning=false','entryError=""',`return !(${disabled})`)
  assert.equal(canSend(false,false,'',{available:false}),true)
  assert.equal(canSend(true,false,'',{available:true}),false)
})


test('leaving for a report and returning restores all editor sections without a write',async()=>{
 const p=detail();await p.load();assert.equal(p.error.value,'');p.edit();p.draft.value.weight=59;p.section.value='preferences';p.hide();assert.equal(p.draft.value,null);await p.load();assert.equal(p.error.value,'');assert.equal(p.editing.value,true);assert.equal(p.draft.value.weight,59);assert.equal(p.section.value,'preferences');assert.equal(p.writes.length,0)
})
test('a version change retains the old edit for comparison without restoring it over current facts',async()=>{
 let raw=source(),m=member();const p=detail({readMemberProfile:async()=>({profile:{householdId:'family',isOwner:true,members:[m]},source:raw})});await p.load();p.edit();p.draft.value.weight=59;p.hide();raw={...raw,version:8};m={...m,weight:60};await p.load();assert.equal(p.editing.value,false);assert.equal(p.draft.value,null);assert.equal(p.conflictEdit.value.draft.weight,59);assert.equal(p.profile.value.members[0].weight,60)
})
test('cancelled edits are not restored on a later return',async()=>{
 const p=detail();await p.load();p.edit();p.draft.value.weight=59;p.hide();await p.load();p.cancelEdit();p.hide();await p.load();assert.equal(p.editing.value,false);assert.equal(p.draft.value,null)
})
test('an account revision change cannot persist the previous private draft under the new context',async()=>{
 const p=detail();await p.load();p.edit();p.draft.value.weight=59;p.changeAccount();p.hide();assert.equal(readMemberEdit('mother',source()),null)
})

test('a newly selected restriction with no details blocks saving in its own category',async()=>{
 const p=detail();await p.load();p.edit();p.draft.value.allergyStatus='set';p.draft.value.allergies=[];await p.save();assert.equal(p.writes.length,0);assert.equal(p.section.value,'restrictions');assert.match(p.error.value,/具体食物过敏/)
})

test('stored member edits remain isolated between accounts and households',()=>{
 setup();preserveMemberEdit({id:'mother',source:source(),draft:{name:'私有草稿'},additional:{},section:'health'});assert.ok(readMemberEdit('mother',source()));setSession({accountId:'other',householdId:'family',token:'other'});assert.equal(readMemberEdit('mother',source()),null);setSession({accountId:'creator',householdId:'other-family',token:'other'});assert.equal(readMemberEdit('mother',source()),null)
})
test('a removed editing permission discards a cached private edit',()=>{
 setup();preserveMemberEdit({id:'mother',source:source(),draft:{weight:59},additional:{},section:'basic'});assert.equal(readMemberEdit('mother',{...source(),editable_fields:[]}),null);assert.equal(readMemberEdit('mother',source()),null)
})

test('empty identity returns to basic information with feedback and no save',async()=>{
 const p=detail();await p.load();p.edit();p.draft.value.name=' ';p.section.value='preferences';await p.save();assert.equal(p.writes.length,0);assert.equal(p.section.value,'basic');assert.match(p.error.value,/姓名/)
})

test('sheet opening is read-only and dirty close can retain a draft without any cloud write',async()=>{
 const events=[],options=[],modals=[]
 const p=detail({defineProps:()=>({id:'mother',embedded:true}),defineEmits:()=> (...args)=>events.push(args),readMemberProfile:async(id,opts)=>{options.push(opts);return {profile:{householdId:'family',isOwner:true,members:[member()]},source:source()}}})
 await p.load();assert.deepEqual(options,[{readOnly:true}]);p.edit();p.draft.value.weight=59
 uni.showModal=spec=>modals.push(spec);p.requestClose();assert.equal(events.length,0);assert.equal(p.writes.length,0)
 assert.equal(modals[0].confirmText,'暂存并关闭');modals[0].success({confirm:true});assert.equal(events[0][0],'close')
 assert.equal(readMemberEdit('mother',source()).draft.weight,59)
 p.hide();await p.load();assert.equal(p.editing.value,true);assert.equal(p.draft.value.weight,59);assert.equal(p.writes.length,0)
})
test('sheet cancel explicitly discards local edits only after confirmation',async()=>{
 const p=detail({defineProps:()=>({id:'mother',embedded:true})});await p.load();p.edit();p.draft.value.weight=59
 let modal;uni.showModal=value=>{modal=value};p.cancelEdit();assert.equal(p.editing.value,true)
 modal.success({confirm:false});assert.equal(p.draft.value.weight,59)
 p.cancelEdit();modal.success({confirm:true});assert.equal(p.editing.value,false);assert.equal(p.profile.value.members[0].weight,55);assert.equal(p.writes.length,0)
})
test('sheet blocks close during a write and emits only freshly reread saved facts',async()=>{
 let release,reads=0;const events=[],toasts=[]
 const p=detail({defineProps:()=>({id:'mother',embedded:true}),defineEmits:()=> (...args)=>events.push(args),saveMemberProfile:()=>new Promise(resolve=>{release=resolve}),readMemberProfile:async()=>({profile:{householdId:'family',isOwner:true,members:[{...member(),weight:reads++?59:55}]},source:source()})})
 await p.load();p.edit();p.draft.value.weight=59;uni.showToast=value=>toasts.push(value)
 const saving=p.save();assert.equal(p.writing.value,true);p.requestClose();assert.equal(events.length,0);assert.equal(toasts[0].title,'正在保存，请稍候')
 release();await saving;assert.equal(p.writing.value,false);assert.equal(events[0][0],'saved');assert.equal(events[0][1].members[0].weight,59);assert.equal(p.editing.value,false)
})
test('uncertain sheet save keeps a comparison draft and never automatically replays a write',async()=>{
 let writes=0,reads=0
 const p=detail({defineProps:()=>({id:'mother',embedded:true}),saveMemberProfile:async()=>{writes++;throw Object.assign(new Error('timeout'),{code:'NETWORK_ERROR'})},readMemberProfile:async()=>({profile:{householdId:'family',isOwner:true,members:[{...member(),weight:reads++?60:55}]},source:source()})})
 await p.load();p.edit();p.draft.value.weight=59;await p.save();assert.equal(p.writeUncertain.value,true);assert.equal(p.draft.value.weight,59)
 await p.reload();assert.equal(writes,1);assert.equal(p.editing.value,false);assert.equal(p.conflictEdit.value.draft.weight,59);assert.equal(p.profile.value.members[0].weight,60)
})
