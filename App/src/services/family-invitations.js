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
  return { title: '邀请你加入家庭', path: invitationRoute(data.code), imageUrl: '/static/food/welcome-kitchen-20261026.jpg' }
}

export function familyShareState() {
  return { options: [], busy: false, error: '', revoking: '' }
}

// Each page owns its credentials; only the clicked native button selects a target.
export function createFamilyShareController({ state, send = request, session = getSession, revision = sessionRevision, now = Date.now }) {
  let epoch = 0, owner = '', familyId = ''
  const context = () => JSON.stringify([session()?.accountId, session()?.householdId, revision()])
  const cover = '/static/food/welcome-kitchen-20261026.jpg'
  function discard() { epoch++; owner = ''; familyId = ''; state.options = []; state.busy = false; state.revoking = ''; state.error = '' }
  async function prepare() {
    if (state.busy && owner === context()) return
    const account = session()
    discard()
    if (!account?.token || !account.householdId) { state.error = '请先登录并选择家庭。'; return }
    const mine = epoch, scope = context()
    owner = scope; familyId = account.householdId; state.busy = true
    try {
      const { data } = await send({ path: '/api/family/' + encodeURIComponent(familyId) + '/invitations/prepare', method: 'POST' })
      if (mine !== epoch) return
      if (scope !== context()) { discard(); return }
      if (!Array.isArray(data?.options) || !data.options.length || data.options.some(o => !o.key || !valid(o.code) || !o.name || (o.expires_at && !Number.isFinite(Date.parse(o.expires_at))))) throw new Error('邀请准备结果不完整，请重试。')
      state.options = data.options
    } catch (error) { if (mine === epoch) { if (scope !== context()) discard(); else state.error = error.message } }
    finally { if (mine === epoch) state.busy = false }
  }
  function share(event) {
    const key = event?.from === 'button' ? event.target?.dataset?.inviteKey : ''
    const option = state.options.find(o => o.key === key)
    if (owner === context() && option?.code && (!option.expires_at || Date.parse(option.expires_at) > now())) {
      return { title: '邀请你加入家庭', path: invitationRoute(option.code), imageUrl: cover }
    }
    return { title: '家庭营养师', path: '/pages/index/index', imageUrl: cover }
  }
  async function revoke(key) {
    if (state.busy || state.revoking || owner !== context()) return
    const option = state.options.find(o => o.key === key)
    if (!option?.code) return
    const code = option.code, mine = epoch, scope = owner
    option.code = ''; state.revoking = key; state.error = ''
    const root = '/api/family/' + encodeURIComponent(familyId)
    try {
      await send({ path: root + (option.member_id ? '/members/' + encodeURIComponent(option.member_id) : '') + '/invite/revoke',
        method: 'POST', data: option.member_id ? { code } : { expected_version: option.version } })
      if (mine === epoch && scope === context()) option.revoked = true
    } catch (error) {
      if (mine === epoch) state.error = error.code === 'NETWORK_ERROR' ? '撤销结果尚未确认，请重新准备邀请；旧邀请将由服务端核对。' : error.message
    } finally { if (mine === epoch) { if (scope !== context()) discard(); else state.revoking = '' } }
  }
  return { prepare, share, revoke, discard }
}
