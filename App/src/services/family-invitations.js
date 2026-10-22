import { request } from './request.js'
import { getSession, sessionRevision } from './session.js'

const pendingKey = 'fn-pending-family-invitation-v1'
const valid = code => typeof code === 'string' && /^[A-Za-z0-9_-]{20,100}$/.test(code)
export function pendingInvitation() {
  const value = uni.getStorageSync(pendingKey)
  return valid(value) ? value : ''
}
export function rememberInvitation(code) {
  if (!valid(code)) throw new Error('邀请凭证无效，请重新打开家人发来的卡片。')
  uni.setStorageSync(pendingKey, code)
  return code
}
export function clearInvitation(code = pendingInvitation()) {
  if (pendingInvitation() === code) uni.setStorageSync(pendingKey, '')
}
export const invitationRoute = code => '/pages/invite/index?token=' + encodeURIComponent(code)
export function captureInvitation(options) {
  if (String(options?.path || '').replace(/^\//, '') === 'pages/invite/index' && options?.query?.token) {
    rememberInvitation(options.query.token)
  }
}
export async function prepareFamilyShare(memberId = '') {
  const account = getSession(), revision = sessionRevision()
  if (!account?.token || !account.householdId) throw new Error('请先完成微信登录并选择家庭。')
  const path = '/api/family/' + encodeURIComponent(account.householdId)
    + (memberId ? '/members/' + encodeURIComponent(memberId) : '') + '/invite'
  const { data } = await request({ path, method: 'POST' })
  if (revision !== sessionRevision()) throw new Error('账号已变化，请重新准备邀请。')
  if (!valid(data.code)) throw new Error('邀请尚未准备完成，请重试。')
  return { title: '邀请你加入我的家庭，核对你的健康资料', path: invitationRoute(data.code) }
}
