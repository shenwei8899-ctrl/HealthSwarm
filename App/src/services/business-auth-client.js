// Existing business accounts authenticate separately from commerce and WeChat identities.
export function createBusinessAuthClient({ send, session }) {
  let generation = 0
  const ticket = () => ({ generation, revision: session.revision() })
  function current(t) {
    if (t.generation !== generation || t.revision !== session.revision()) throw Object.assign(new Error('账号已切换，请重新登录'), { code: 'SESSION_CHANGED' })
  }
  async function restore() {
    const stored = session.read()
    if (!stored?.token || stored.authSource !== 'business') return null
    const t = ticket()
    const me = (await send({ path: '/api/auth/me' })).data
    current(t)
    if (!Number.isSafeInteger(me?.id) || String(me.id) !== stored.accountId) {
      session.clear()
      throw Object.assign(new Error('会话身份不一致，请重新登录'), { code: 'SESSION_IDENTITY_CHANGED' })
    }
    const rows = (await send({ path: '/api/family' })).data
    current(t)
    if (!Array.isArray(rows) || rows.some(row => typeof row.id !== 'string' || typeof row.name !== 'string')) throw new Error('家庭列表格式异常')
    const families = rows.map(row => ({ id: row.id, name: row.name, isOwner: row.is_owner === true }))
    const result = { ...stored, accountName: me.username || me.uid, families,
      householdId: families.some(row => row.id === stored.householdId) ? stored.householdId : null }
    session.save(result)
    return result
  }
  async function login(identifier, password) {
    if (!identifier?.trim() || !password) throw new Error('请填写业务账号和密码')
    const t = ticket()
    const data = 'username=' + encodeURIComponent(identifier.trim()) + '&password=' + encodeURIComponent(password)
    const result = (await send({ path: '/api/auth/token', method: 'POST', authenticated: false,
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, data })).data
    current(t)
    if (!Number.isSafeInteger(result?.user_id) || !result.access_token) throw new Error('登录返回的身份不完整')
    session.save({ accountId: String(result.user_id), token: result.access_token, authSource: 'business', householdId: null, isDemo: false })
    const own = ticket()
    try { return await restore() }
    catch (error) {
      if (own.generation === generation && own.revision === session.revision()) session.clear()
      throw error
    }
  }
  async function selectFamily(id) {
    const restored = await restore()
    if (!restored?.families.some(row => row.id === id)) throw new Error('家庭不存在或不可访问')
    const result = { ...restored, householdId: id }; session.save(result); return result
  }
  return { login, restore, selectFamily, cancelPending: () => { generation++ } }
}
