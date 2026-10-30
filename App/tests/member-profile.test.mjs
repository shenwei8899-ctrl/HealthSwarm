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

function setup(){const values=new Map();globalThis.uni={getStorageSync:k=>values.get(k),setStorageSync:(k,v)=>values.set(k,structuredClone(v))};setSession({accountId:'creator',householdId:'family',token:'synthetic'});return values}
const source=()=>({id:'mother',is_active:true,is_self:false,version:7,relationship_version:2,confirmed:true,editable_fields:['sex','birth_date','height_cm','dietary_details','goal','allergens','avoidances','doctor_instructions'],profile:{dietary_details:{statedWeightKg:55,conditions:['合成情况'],recentNote:'保留原文'},medications:'保留用药记录'}})
const member=()=>({id:'mother',name:'妈妈',relation:'妈妈',weight:55,gender:'女',conditions:['合成情况'],recentNote:'保留原文',allergyStatus:'none',allergies:[],goals:['饮食均衡']})

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
  const deps={ref,computed,defineProps:()=>({id:'mother'}),onShow(){},onHide(){},onUnload(){},sessionRevision:()=>revision,profileDraft,profileChanges,
    restrictionIssue,restrictionFields,preserveMemberEdit,readMemberEdit,clearMemberEdit,readMemberProfile:async()=>({profile:{householdId:'family',isOwner:true,selfMemberId:'creator',members:[m]},member:m,source:raw}),
    saveMemberProfile:async(...args)=>writes.push(args),request:async()=>({data:{}}),...overrides}
  const page=new Function('deps',`const {${Object.keys(deps)}}=deps;${src};return {load,edit,save,hide,cancelEdit,section,conflictEdit,canEdit,canAnalyze,profile,source,draft,error,busy,analysisBusy,editing,revokeAnalysis}`)(deps)
  return {...page,writes,changeAccount:()=>revision++}
}

test('creator can edit a claimed relative but gets no confirm or analysis authority',async()=>{
  const p=detail();await p.load();assert.equal(p.canEdit.value,true);assert.equal(Boolean(p.canAnalyze.value),false)
  p.edit();p.draft.value.weight=57;await p.save();assert.equal(p.writes.length,1);assert.equal(p.writes[0][1].id,'mother')
  assert.equal(p.analysisBusy.value,false)
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
  await p.load();assert.equal(p.canEdit.value,true);assert.equal(p.canAnalyze.value,true)
})

test('consent can be withdrawn even when model configuration and readiness are unavailable',async()=>{
  const writes=[]
  const p=detail({readMemberProfile:async()=>({profile:{householdId:'family',analysisPolicy:null,members:[{...member(),healthMemberId:'health'}]},source:{...source(),is_self:true}}),readCloudReportStatus:async()=>{throw new Error('unavailable')},request:async o=>{if(o.method==='POST'){writes.push(o);return {data:{}}}throw new Error('unavailable')}})
  await p.load();await p.revokeAnalysis();assert.equal(writes.length,1);assert.equal(writes[0].data.accepted,false)
  const template=readFileSync(new URL('../src/components/CloudMemberDetail.vue',import.meta.url),'utf8')
  assert.match(template,/v-if="member.healthMemberId"[^>]*@click="revokeAnalysis"/)
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
  const canSend=new Function('chatBusy','draftSaving','draftError','task',`return !(${disabled})`)
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
