import { request } from './request.js'
import { getSession, setSession, sessionRevision } from './session.js'
import { scopedStorage } from './storage.js'
import { saveProfile, normalizeProfile } from '../utils/profile.js'
import { newHealthRequestId } from './health-task-flow.js'
import { pendingInvitation } from './family-invitations.js'

export async function readCloudReportStatus(memberId) {
  const [observations,vision]=await Promise.all([
    request({path:`/api/health/v1/members/${memberId}/observations`}),
    request({path:`/api/health/v1/members/${memberId}/vision/page?kind=report&jobs_limit=1&drafts_limit=20`}),
  ])
  if(!Array.isArray(observations.data)||!Array.isArray(vision.data.drafts))throw new Error('报告状态返回不完整，请重新读取')
  return observations.data.length?'done':vision.data.drafts.some(d=>d.review_status==='pending_confirmation')?'review':'empty'
}

export async function loadCloudProfile({openConsultation=true} = {}) {
  let session = getSession()
  if (!session?.token) throw Object.assign(new Error('请先微信登录'), { code: 401 })
  if (pendingInvitation()) throw Object.assign(new Error('请先查看并决定是否接受家庭邀请。'), {code:'INVITATION_PENDING'})
  const revision = sessionRevision()
  if (!session.householdId) {
    let families = (await request({ path: '/api/family' })).data
    const pendingCreation='cloud-family-creation-uncertain'
    if (!families.length) {
      if (pendingInvitation()) throw Object.assign(new Error('请先处理家庭邀请。'), {code:'INVITATION_PENDING'})
      if(scopedStorage.getStorageSync(pendingCreation))throw new Error('家庭创建结果尚未确认，请重新读取档案，不要重复创建。')
      scopedStorage.setStorageSync(pendingCreation,true)
      try { await request({ path: '/api/family', method: 'POST', data: { name: '我的家' } }) }
      catch (error) { if (error.code !== 'NETWORK_ERROR' && Number(error.code) < 500 && Number(error.code) !== 409) { scopedStorage.setStorageSync(pendingCreation,null); throw error } }
      families = (await request({ path: '/api/family' })).data
    }
    if (sessionRevision() !== revision) throw new Error('账号已变化，请重新进入。')
    if (!families.length) throw new Error('家庭创建结果尚未确认，请重新读取档案，不要重复创建。')
    if (families.length !== 1) throw Object.assign(new Error('请先选择当前家庭。'), { code: 'FAMILY_SELECTION_REQUIRED' })
    scopedStorage.setStorageSync(pendingCreation,null)
    session = { ...session, householdId: families[0].id }
    setSession(session)
  }
  const ticket = sessionRevision()
  const { data } = await request({ path: '/api/family/' + encodeURIComponent(session.householdId) + '/miniapp-profile' })
  if (ticket !== sessionRevision()) throw new Error('账号已变化，请重新进入。')
  if (data.source !== 'api' || data.householdId !== session.householdId || !Array.isArray(data.members)) throw new Error('云端档案返回不完整，请重试。')
  let profile = normalizeProfile(data)
  let config = {}
  try { config = (await request({path:'/api/health/v1/configuration'})).data }
  catch(error) { if ([401,403].includes(Number(error.code))) throw error }
  if (ticket !== sessionRevision()) throw new Error('账号已变化，请重新进入。')
  profile.analysisPolicy = config.consultation?.available === true && config.consultation.processor && config.policy_version
    ? {processor:config.consultation.processor,policy_version:config.policy_version} : null
  if(openConsultation&&(profile.completeProfile||profile.onboarded)&&profile.selfMemberId&&profile.analysisPolicy){
    const member=profile.members.find(m=>m.id===profile.selfMemberId)
    if(member){
      const id=newHealthRequestId()
      try{
      const {data:opened}=await request({path:'/api/family/'+encodeURIComponent(session.householdId)+'/miniapp-profile',method:'POST',headers:{'Idempotency-Key':id},data:{action:'open_consultation',client_request_id:id,member_id:member.id,expected_version:member.version}})
      if(ticket!==sessionRevision())throw new Error('账号已变化，请重新进入。')
      if(opened.source!=='api'||opened.householdId!==session.householdId||!Array.isArray(opened.members))throw new Error('云端档案返回不完整，请重新读取。')
      profile=normalizeProfile({...opened,analysisPolicy:profile.analysisPolicy})
      }catch(error){
        if(ticket!==sessionRevision()||[401,403,404,410].includes(Number(error.code)))throw error
        profile.consultationError=error.message||'咨询连接暂未完成，请重新读取。'
      }
    }
  }
  if((profile.completeProfile||profile.onboarded)&&!profile.analysisPolicy)profile.consultationError=config.consultation?.reason||'营养咨询服务暂未就绪，档案已保存。'
  profile.healthConfiguration = config
  saveProfile(profile)
  return profile
}

const dietaryKeys = ['healthStatus', 'conditions', 'otherCondition', 'allergyStatus', 'allergies', 'intoleranceStatus', 'intolerances', 'avoidanceStatus', 'avoidances', 'doctorStatus', 'clinicianGuidance', 'goals', 'cuisines', 'tastePreferences', 'flavors', 'recentNote', 'hypoglycemiaRisk', 'kidneyCondition']
export function cloudProfileInput(profile, id = newHealthRequestId(), consent = null) {
  const uuid = /^[0-9a-f]{8}-[0-9a-f-]{27}$/i
  const selfOnly = profile.isOwner === false
  const members = selfOnly ? profile.members.filter(member => String(member.id) === profile.selfMemberId) : profile.members
  // 家庭建档使用服务端默认范围；仅本人编辑明确提交 self，避免将其扩为全家写入。
  return { client_request_id: id, ...(selfOnly ? { scope: 'self' } : {}), family_version: profile.familyVersion, usage_mode: profile.usageMode, analysis_consent:consent,
    default_diners: (selfOnly ? members.map(member => member.id) : profile.defaultDiners).map(String), members: members.map(member => ({
      client_ref: String(member.id), member_id: uuid.test(String(member.id)) ? String(member.id) : null,
      version: member.version || null, name: member.name, relation: member.relation,
      birth_date: member.birthDate || null, sex: member.gender === '女' ? 'female' : member.gender === '男' ? 'male' : 'unspecified',
      height_cm: member.height === '' || member.height == null ? null : Number(member.height),
      weight_kg: member.weight === '' || member.weight == null ? null : Number(member.weight),
      dietary: Object.fromEntries(dietaryKeys.filter(key => member[key] !== undefined).map(key => [key, member[key]])),
    })) }
}

export async function saveCloudProfile(profile, { analysisConsent = null } = {}) {
  const session = getSession()
  if (!session?.token) throw Object.assign(new Error('登录状态已失效，填写内容已保留，请重新登录后继续。'), { code: 401 })
  if (!session.householdId) throw Object.assign(new Error('请先选择当前家庭。'), { code: 'FAMILY_SELECTION_REQUIRED' })
  if (profile.householdId !== session.householdId) throw Object.assign(new Error('家庭已变化，请重新读取档案。'), { code: 'SESSION_CHANGED' })
  const scope = sessionRevision()
  const current = () => { if (scope !== sessionRevision()) throw Object.assign(new Error('账号已变化，请重新进入。'), {code:'SESSION_CHANGED'}) }
  const path = '/api/family/' + encodeURIComponent(session.householdId) + '/miniapp-profile'
  let pending = scopedStorage.getStorageSync('cloud-onboarding-pending')
  const submitted = cloudProfileInput(profile, pending?.data?.client_request_id, analysisConsent)
  const changed = !!pending && JSON.stringify(pending.data) !== JSON.stringify(submitted)
  if (!pending) { pending = { path, data: submitted }; scopedStorage.setStorageSync('cloud-onboarding-pending', pending) }
  if (pending.path !== path) throw new Error('家庭已变化，请重新读取档案。')
  if (JSON.stringify(pending.data.analysis_consent || null) !== JSON.stringify(analysisConsent)) throw new Error('上次保存结果尚未确认，请先恢复原操作；普通保存不会重放分析同意。')
  try {
    await request({ path, method: 'POST', data: pending.data, headers: { 'Idempotency-Key': pending.data.client_request_id }, timeout: 30000 })
  } catch (error) {
    if (Number(error.code) === 401) throw error
    current()
    if (error.code !== 'NETWORK_ERROR' && Number(error.code) < 500) { scopedStorage.setStorageSync('cloud-onboarding-pending', null); throw error }
    // 先读服务端，再用原请求取得幂等收据；不依据本机草稿标记完成。
    await request({ path })
    current()
    await request({ path, method: 'POST', data: pending.data, headers: { 'Idempotency-Key': pending.data.client_request_id }, timeout: 30000 })
  }
  current()
  const result = await loadCloudProfile()
  if (!result.completeProfile && !result.onboarded) throw new Error('云端保存尚未确认，请重试原请求。')
  scopedStorage.setStorageSync('cloud-onboarding-pending', null)
  if (changed) throw Object.assign(new Error('上次提交已确认，本次修改尚未提交。请重新读取当前档案，核对本次修改后再次保存。'), {code:409,businessCode:'previous_profile_submission_settled'})
  return result
}
