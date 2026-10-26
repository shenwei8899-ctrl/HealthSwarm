import { request } from './request.js'
import { loadCloudProfile } from './cloud-profile.js'
import { getSession, sessionRevision } from './session.js'
import { scopedStorage } from './storage.js'
import { newHealthRequestId } from './health-request-id.js'

const dietaryKeys = ['healthStatus','conditions','otherCondition','allergyStatus','allergies','intoleranceStatus','intolerances','avoidanceStatus','avoidances','doctorStatus','clinicianGuidance','goals','cuisines','tastePreferences','flavors','recentNote','hypoglycemiaRisk','kidneyCondition']
const same = (a,b) => JSON.stringify(a) === JSON.stringify(b)
const number = value => {
  if (value === '' || value == null) return null
  const result = Number(value)
  if (!Number.isFinite(result) || result <= 0) throw new Error('身高、体重须填写有效的正数。')
  return result
}

// Compare the selected member's draft, keeping every unedited source field intact.
export function memberProfileChanges(original, draft, source) {
  const changes = {}, dietary = { ...(source.profile?.dietary_details || {}) }
  for (const [field,key,convert] of [['sex','gender',v=>v==='女'?'female':v==='男'?'male':'unspecified'],['birth_date','birthDate',v=>v||null],['height_cm','height',number]]) {
    if (!same(original[key],draft[key])) changes[field] = convert(draft[key])
  }
  let dietaryChanged = false
  for (const key of dietaryKeys) if (!same(original[key],draft[key])) { dietary[key]=draft[key]; dietaryChanged=true }
  if (number(original.weight)!==number(draft.weight)) { dietary.statedWeightKg=number(draft.weight); dietaryChanged=true }
  if (dietaryChanged) changes.dietary_details = dietary
  if (!same(original.goals,draft.goals)) changes.goal = draft.goals?.join('、') || null
  if (['allergyStatus','allergies'].some(k=>!same(original[k],draft[k]))) changes.allergens = draft.allergyStatus==='unknown'?null:draft.allergyStatus==='none'?[]:draft.allergies
  if (['avoidanceStatus','avoidances'].some(k=>!same(original[k],draft[k]))) changes.avoidances = draft.avoidanceStatus==='unknown'?null:draft.avoidanceStatus==='none'?[]:draft.avoidances
  if (['doctorStatus','clinicianGuidance'].some(k=>!same(original[k],draft[k]))) changes.doctor_instructions = draft.doctorStatus==='set'?draft.clinicianGuidance:null
  for (const key of Object.keys(changes)) if (!source.editable_fields?.includes(key)) throw new Error('当前资料字段不可修改，请重新读取权限。')
  return changes
}

function currentSession(familyId) {
  const revision=sessionRevision()
  if(!getSession()?.token||getSession()?.householdId!==familyId)throw Object.assign(new Error('账号或家庭已变化，请重新读取。'),{code:'SESSION_CHANGED'})
  return ()=>{if(sessionRevision()!==revision||getSession()?.householdId!==familyId)throw Object.assign(new Error('账号或家庭已变化，请重新读取。'),{code:'SESSION_CHANGED'})}
}

export async function readMemberProfile(id) {
  const profile=await loadCloudProfile(),current=currentSession(profile.householdId)
  const {data}=await request({path:'/api/family/'+encodeURIComponent(profile.householdId)})
  current()
  const member=profile.members.find(m=>m.id===id),source=data.members?.find(m=>m.id===id&&m.is_active)
  if(data.id!==profile.householdId||!member||!source)throw Object.assign(new Error('该成员已不可访问，请返回家庭档案核查。'),{code:404})
  if(source.version!==member.version)throw Object.assign(new Error('成员资料已变化，请重新读取后再编辑。'),{code:409})
  return {profile,member,source}
}

export async function saveMemberProfile(familyId, source, original, draft, extraChanges={}, send=request) {
  const current=currentSession(familyId),path=`/api/family/${encodeURIComponent(familyId)}/members/${encodeURIComponent(source.id)}`
  const changes={...memberProfileChanges(original,draft,source),...extraChanges}
  if(Object.keys(changes).some(k=>!source.editable_fields?.includes(k)))throw new Error('当前字段不可修改')
  let savedProfile=false
  if(Object.keys(changes).length){await send({path,method:'PUT',data:{expected_version:source.version,profile:changes}});savedProfile=true;current()}
  if(draft.name!==original.name||!source.is_self&&draft.relation!==original.relation){
    try { await send({path:path+'/relationship',method:'PUT',data:{expected_version:source.relationship_version,name:draft.name,relationship:source.is_self?source.relationship:draft.relation}});current() }
    catch(error){if(savedProfile){error.partialSave=true;error.message='健康资料已保存，姓名或关系未确认保存。请重新读取后核对。'}throw error}
  }
}

export async function startMemberAnalysis(familyId, member, policy, purpose='consultation', send=request) {
  const current=currentSession(familyId),key=`member-analysis-pending:${familyId}:${member.id}:${purpose}`
  if(!policy?.processor||!policy?.policy_version)throw new Error('分析服务尚未配置，请稍后再试。资料仍可查看和修改。')
  const body={action:'start_analysis',member_id:member.id,expected_version:member.version,accepted:true,purpose,processor:policy.processor,policy_version:policy.policy_version}
  let pending=scopedStorage.getStorageSync(key)
  // 已重新读取并明确同意新版本时，提交新的确认；旧请求仍受服务端版本和政策校验。
  if(pending&&!same({...pending,client_request_id:undefined},body))pending=null
  if(!pending){pending={...body,client_request_id:newHealthRequestId()};scopedStorage.setStorageSync(key,pending)}
  try{
    const response=await send({path:`/api/family/${encodeURIComponent(familyId)}/miniapp-profile`,method:'POST',headers:{'Idempotency-Key':pending.client_request_id},data:pending})
    current();scopedStorage.setStorageSync(key,null);return response.data
  }catch(error){current();if(Number(error.code)<500&&Number(error.code)!==401)scopedStorage.setStorageSync(key,null);throw error}
}
