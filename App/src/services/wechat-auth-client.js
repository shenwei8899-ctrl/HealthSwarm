// Dependency injection keeps credential exchange and account-switch races testable.
export function createWechatAuthClient({ send, session, getCode, appId, isWechat, allowPasswordLogin = false }) {
  let generation = 0
  function ticket() { return { generation, revision: session.revision() } }
  function current(t) {
    if (t.generation !== generation || t.revision !== session.revision()) {
      throw Object.assign(new Error('登录状态已变更，请重新操作'), { code: 'SESSION_CHANGED' })
    }
  }
  async function login(binding) {
    const t = ticket()
    if (!isWechat) throw Object.assign(new Error('请在微信小程序中使用微信登录'), { code: 'WECHAT_PLATFORM_REQUIRED' })
    if (!/^wx[0-9a-f]{16}$/i.test(appId || '')) throw Object.assign(new Error('微信登录尚未配置 AppID'), { code: 'WECHAT_NOT_CONFIGURED' })
    const config = (await send({ path: '/api/auth/wechat/config', authenticated: false })).data
    current(t)
    if (!config?.available || config.appid !== appId) throw Object.assign(new Error('微信登录服务尚未配置完成'), { code: 'WECHAT_NOT_CONFIGURED' })
    const code = await getCode()
    current(t)
    const data = { code }
    if (binding) { data.identifier = binding.identifier; data.password = binding.password }
    const response = await send({ path: '/api/auth/wechat/login', method: 'POST', data, authenticated: false })
    current(t)
    const result = projectLogin(response.data)
    session.save(result)
    return result
  }
  async function passwordLogin({ identifier, password }) {
    if (!allowPasswordLogin || isWechat) throw Object.assign(new Error('当前环境未开放账号登录'), { code: 'PASSWORD_LOGIN_DISABLED' })
    const t = ticket()
    if (!identifier?.trim() || !password) throw new Error('请填写已有账号与密码')
    const response = await send({ path: '/api/auth/token', method: 'POST', authenticated: false,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      data: 'username=' + encodeURIComponent(identifier.trim()) + '&password=' + encodeURIComponent(password) })
    current(t)
    const token = response.data?.access_token
    if (typeof token !== 'string' || !token) throw new Error('登录服务返回的会话无效')
    const context = await send({ path: '/api/auth/wechat/session', authenticated: false, authenticationToken: token })
    current(t)
    const result = { ...projectContext(context.data), token, householdId: null, isDemo: false }
    if (result.accountId !== String(response.data.user_id)) throw new Error('登录身份不一致，请重试')
    session.save(result)
    return result
  }
  async function restore() {
    const stored = session.read()
    if (!stored?.token || stored.isDemo) return null
    const t = ticket()
    const response = await send({ path: '/api/auth/wechat/session' })
    current(t)
    if (response.data?.wechat_authenticated !== true) {
      session.clear()
      throw Object.assign(new Error('请重新使用微信登录'), { code: 'WECHAT_LOGIN_REQUIRED' })
    }
    const context = projectContext(response.data)
    if (context.accountId !== stored.accountId) {
      session.clear()
      throw Object.assign(new Error('会话身份不一致，请重新登录'), { code: 'SESSION_IDENTITY_CHANGED' })
    }
    const selected = context.families.find(f => f.id === stored.householdId)
    const result = { ...stored, ...context, authSource: 'wechat', householdId: selected?.id || null }
    session.save(result, { preserveRevision: true })
    return result
  }
  async function selectFamily(id) {
    const restored = await restore()
    if (!restored) throw Object.assign(new Error('请先登录'), { code: 401 })
    const family = restored.families.find(f => f.id === id)
    if (!family) throw new Error('家庭不存在或当前账号无权访问')
    const result = { ...restored, householdId: family.id }
    session.save(result, { preserveRevision: true })
    return result
  }
  function logout() { generation++; session.clear() }
  function cancelPending() { generation++ }
  return { login, passwordLogin, restore, selectFamily, logout, cancelPending }
}

export function projectContext(data) {
  if (!data?.account || !Number.isSafeInteger(data.account.id) || data.account.id <= 0 || !Array.isArray(data.families)) throw new Error('登录服务返回的数据不完整')
  const families = data.families.map(f => {
    if (typeof f.id !== 'string' || !f.id || typeof f.name !== 'string' || typeof f.onboarding_required !== 'boolean') throw new Error('家庭状态不完整')
    return { id: f.id, name: f.name, isOwner: f.is_owner === true, onboardingRequired: f.onboarding_required }
  })
  return { accountId: String(data.account.id), accountName: typeof data.account.name === 'string' ? data.account.name : '', families }
}

export function projectLogin(data) {
  if (typeof data?.access_token !== 'string' || !data.access_token || !Number.isFinite(data.expires_at) || data.expires_at <= Date.now() / 1000) throw new Error('登录服务返回的会话无效')
  return { ...projectContext(data), token: data.access_token, expiresAt: data.expires_at, householdId: null, authSource: 'wechat', isDemo: false }
}
