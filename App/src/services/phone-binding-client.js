// Phone grants stay in the current callback; never use commerce.mutate/local storage here.
const invalid = () => Object.assign(new Error('手机号服务返回异常，请重新读取'), { code: 'INVALID_RESPONSE' })
const changed = () => Object.assign(new Error('账号已变化，请重新读取手机号状态'), { code: 'SESSION_CHANGED' })
export function createPhoneBindingClient({ commerce, accountContext, appId, randomKey, update, now = Date.now }) {
  let generation = 0, ticket = null, blockedUntil = 0
  let state = { loading: false, binding: false, ready: false, config: null, status: null, error: '', uncertain: false }
  const emit = patch => { state = { ...state, ...patch }; update({ ...state }) }
  const matches = t => t && t.generation === generation && t.account === accountContext() &&
    t.revision === commerce.sessionRevision() && t.userId === String(commerce.session()?.userId || '')
  const assertCurrent = t => { if (!matches(t)) throw changed() }
  function validateStatus(value, t) {
    if (!value || String(value.user_id) !== t.userId || typeof value.phone_bound !== 'boolean' ||
        (value.phone_bound && (value.verification_source !== 'wechat_phone' || typeof value.phone_masked !== 'string' ||
          !value.phone_masked.includes('****') || !Number.isFinite(value.verified_at)))) throw invalid()
    return value
  }
  async function load() {
    if (state.binding) return
    const mine = ++generation, account = accountContext()
    ticket = null
    emit({ loading: true, ready: false, config: null, status: null, error: '' })
    try {
      await commerce.connect()
      if (mine !== generation || account !== accountContext()) throw changed()
      const t = { generation: mine, account, revision: commerce.sessionRevision(), userId: String(commerce.session()?.userId || '') }
      if (!t.userId) throw changed()
      const [config, result] = await Promise.all([commerce.request('/account/phone/config'), commerce.request('/account/phone')])
      assertCurrent(t)
      if (!config || typeof config.available !== 'boolean') throw invalid()
      if (config.available && config.appid !== appId) throw Object.assign(new Error('小程序来源不一致，请联系管理员'), { code: 40961 })
      const status = validateStatus(result, t)
      ticket = t
      if (status.phone_bound) blockedUntil = 0
      const uncertain = !status.phone_bound && now() < blockedUntil
      emit({ config, status, ready: true, uncertain, error: uncertain ? '上次授权结果正在确认，请稍后刷新状态。' : '' })
    } catch (e) {
      if (mine === generation) emit({ ready: false, error: e.message || '手机号状态读取失败，请重试' })
    } finally { if (mine === generation) emit({ loading: false }) }
  }
  async function authorize(detail) {
    if (state.binding || state.loading) return
    const t = ticket
    if (!matches(t)) { emit({ ready: false, error: changed().message }); return }
    if (!state.ready || !state.config?.available || state.status?.phone_bound) return
    if (now() < blockedUntil) { emit({ uncertain: true, error: '上次授权仍待确认，请稍后刷新状态。' }); return }
    if (!detail?.code || detail.errMsg && detail.errMsg !== 'getPhoneNumber:ok') {
      emit({ error: detail?.errMsg?.includes('deny') || detail?.errMsg?.includes('cancel') ? '你已取消手机号授权，登录状态保持不变。' : '未取得手机号授权，请确认微信权限后重试。' })
      return
    }
    emit({ binding: true, error: '' })
    try {
      const key = randomKey()
      if (!/^[A-Za-z0-9_-]{16,64}$/.test(key)) throw new Error('请求编号生成失败，请重新进入页面')
      assertCurrent(t)
      const result = await commerce.request('/account/phone/wechat', { method: 'POST', data: { phone_code: detail.code }, key })
      assertCurrent(t)
      const status = validateStatus(result, t)
      if (!status.phone_bound) throw invalid()
      blockedUntil = 0
      emit({ status, uncertain: false, error: '' })
    } catch (e) {
      if (!matches(t)) {
        if (t.generation === generation) { ticket = null; emit({ binding: false, ready: false, config: null, status: null, error: changed().message }) }
        return
      }
      const code = Number(e.code)
      const uncertain = e.code === 'NETWORK_ERROR' || e.code === 'INVALID_RESPONSE' || code >= 50000 || [40963, 40966].includes(code) || Number(e.status) >= 500
      if (uncertain) {
        blockedUntil = now() + 45000
        emit({ uncertain: true, error: '授权结果暂未确认，正在查询绑定状态，请勿重复提交。' })
        try {
          const status = validateStatus(await commerce.request('/account/phone'), t)
          assertCurrent(t)
          if (status.phone_bound) { blockedUntil = 0; emit({ status, uncertain: false, error: '' }) }
          else emit({ status, error: '暂未确认绑定，请稍后刷新状态；不会自动重新提交授权。' })
        } catch { if (matches(t)) emit({ error: '暂时无法确认绑定结果，请稍后刷新状态。' }) }
      } else {
        emit({ error: e.message || '手机号绑定未完成，请重试' })
        if ([401, 40100, 40301, 40961, 40967, 50311].includes(code)) emit({ ready: false })
      }
    } finally { if (matches(t)) emit({ binding: false }) }
  }
  function dispose() {
    generation++; ticket = null
    emit({ loading: false, binding: false, ready: false, config: null, status: null, error: '', uncertain: false })
  }
  return { load, authorize, dispose }
}
