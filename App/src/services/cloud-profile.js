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

export async function loadCloudProfile() {
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
  const profile = normalizeProfile(data)
  let config = {}
  try { config = (await request({path:'/api/health/v1/configuration'})).data }
  catch(error) { if ([401,403].includes(Number(error.code))) throw error }
  if (ticket !== sessionRevision()) throw new Error('账号已变化，请重新进入。')
  profile.analysisPolicy = config.meal_plan?.available === true && config.meal_plan.processor && config.policy_version
    ? {processor:config.meal_plan.processor,policy_version:config.policy_version} : null
  saveProfile(profile)
  return profile
}

const dietaryKeys = ['healthStatus', 'conditions', 'otherCondition', 'allergyStatus', 'allergies', 'intoleranceStatus', 'intolerances', 'avoidanceStatus', 'avoidances', 'doctorStatus', 'clinicianGuidance', 'goals', 'cuisines', 'tastePreferences', 'flavors', 'recentNote', 'hypoglycemiaRisk', 'kidneyCondition']
export function cloudProfileInput(profile, id = newHealthRequestId()) {
  const uuid = /^[0-9a-f]{8}-[0-9a-f-]{27}$/i
  const selfOnly = profile.isOwner === false
  const members = selfOnly ? profile.members.filter(member => String(member.id) === profile.selfMemberId) : profile.members
  // 家庭建档使用服务端默认范围；仅本人编辑明确提交 self，避免将其扩为全家写入。
  return { client_request_id: id, ...(selfOnly ? { scope: 'self' } : {}), family_version: profile.familyVersion, usage_mode: profile.usageMode, analysis_consent:profile.analysisPolicy||null,
    default_diners: (selfOnly ? members.map(member => member.id) : profile.defaultDiners).map(String), members: members.map(member => ({
      client_ref: String(member.id), member_id: uuid.test(String(member.id)) ? String(member.id) : null,
      version: member.version || null, name: member.name, relation: member.relation,
      birth_date: member.birthDate || null, sex: member.gender === '女' ? 'female' : member.gender === '男' ? 'male' : 'unspecified',
      height_cm: member.height === '' || member.height == null ? null : Number(member.height),
      weight_kg: member.weight === '' || member.weight == null ? null : Number(member.weight),
      dietary: Object.fromEntries(dietaryKeys.filter(key => member[key] !== undefined).map(key => [key, member[key]])),
    })) }
}

export async function saveCloudProfile(profile) {
  const session = getSession()
  if (!session?.token) throw Object.assign(new Error('登录状态已失效，填写内容已保留，请重新登录后继续。'), { code: 401 })
  if (!session.householdId) throw Object.assign(new Error('请先选择当前家庭。'), { code: 'FAMILY_SELECTION_REQUIRED' })
  if (profile.householdId !== session.householdId) throw Object.assign(new Error('家庭已变化，请重新读取档案。'), { code: 'SESSION_CHANGED' })
  const scope = sessionRevision()
  const current = () => { if (scope !== sessionRevision()) throw Object.assign(new Error('账号已变化，请重新进入。'), {code:'SESSION_CHANGED'}) }
  const path = '/api/family/' + encodeURIComponent(session.householdId) + '/miniapp-profile'
  let pending = scopedStorage.getStorageSync('cloud-onboarding-pending')
  if (!pending) { pending = { path, data: cloudProfileInput(profile) }; scopedStorage.setStorageSync('cloud-onboarding-pending', pending) }
  if (pending.path !== path) throw new Error('家庭已变化，请重新读取档案。')
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
  if (!result.onboarded) throw new Error('云端保存尚未确认，请重试原请求。')
  scopedStorage.setStorageSync('cloud-onboarding-pending', null)
  return result
}
