// Cache only this page's display summary, never health details or authorization.
const sharedCache = { entry: null }
const loginCodes = new Set([401, 'WECHAT_LOGIN_REQUIRED', 'SESSION_IDENTITY_CHANGED'])
const privateCodes = new Set([401, 403, 404, 410, 'WECHAT_LOGIN_REQUIRED', 'SESSION_IDENTITY_CHANGED', 'SESSION_CHANGED'])

export function createMyProfileLoader({ state, session, context, restore, readProfile, readAccount,
  readCachedProfile = () => null, loginRequired = () => {}, report = () => {}, cache = sharedCache,
  now = Date.now, schedule = setTimeout, cancel = clearTimeout, freshFor = 60000, timeout = 20000 }) {
  let owner = '', pending = null, visible = false, disposed = false, loginNotified = false
  const requireLogin = () => { if (!loginNotified) { loginNotified = true; loginRequired() } }
  const empty = () => { state.profile = null; state.avatar = ''; state.nickname = ''; state.error = ''; state.busy = false }
  function summary(profile) {
    return { usageMode: profile.usageMode, memberCount: profile.members.length,
      selfName: profile.members.find(member => member.relation === '本人')?.name || '' }
  }
  function apply(entry) {
    if (!visible) return
    state.profile = entry?.profile || null
    state.avatar = entry?.account?.avatar || ''
    state.nickname = entry?.account?.nickname || ''
  }
  function clear() {
    const flight = pending
    pending = null
    flight?.stop?.()
    if (cache.entry?.key === owner) cache.entry = null
    empty()
  }
  function show({ force = false } = {}) {
    if (disposed) return Promise.resolve(false)
    const returning = !visible
    visible = true
    const key = context()
    if (key !== owner) { clear(); owner = key }
    if (!session()?.token) { clear(); requireLogin(); return Promise.resolve(false) }
    loginNotified = false
    if (cache.entry?.key !== key) cache.entry = null
    // A confirmed edit elsewhere already refreshed the existing family cache.
    const local = readCachedProfile()
    if (local?.source === 'api' && local.householdId === session()?.householdId &&
      Array.isArray(local.members) && Number.isFinite(local.revision) &&
      (!cache.entry || local.revision > (cache.entry.profileRevision || 0))) {
      cache.entry = { ...cache.entry, key, profile: summary(local), profileRevision: local.revision,
        profileAt: Math.min(now(), local.revision) }
    }
    apply(cache.entry)
    if (pending) return pending.promise
    const fresh = at => Number.isFinite(at) && now() >= at && now() - at < freshFor
    const needProfile = force || !fresh(cache.entry?.profileAt)
    // Settings may have changed the avatar or nickname while this page was hidden.
    const needAccount = force || returning || !fresh(cache.entry?.accountAt)
    if (!needProfile && !needAccount) return Promise.resolve(true)
    const flight = { key, started: now(), stage: needProfile ? 'session' : 'account' }
    pending = flight
    state.error = ''
    state.busy = !state.profile
    const current = () => !disposed && pending === flight && context() === key && !!session()?.token
    const check = () => { if (!current()) throw Object.assign(new Error('账号或家庭已变化，请重新读取。'), { code: 'SESSION_CHANGED' }) }
    const save = patch => {
      check()
      cache.entry = { ...(cache.entry?.key === key ? cache.entry : {}), key, ...patch }
      apply(cache.entry)
      state.busy = !state.profile
    }
    let timer
    const deadline = new Promise((resolve, reject) => {
      flight.stop = () => reject(Object.assign(new Error('读取已停止'), { code: 'CANCELLED' }))
      timer = schedule(() => reject(Object.assign(new Error('资料读取超时，请重试。'), { code: 'PROFILE_TIMEOUT' })), timeout)
    })
    const work = (async () => {
      if (needProfile) {
        const account = await restore()
        check()
        if (!account) throw Object.assign(new Error('请重新登录'), { code: 401 })
      }
      check()
      const waiting = new Set([...(needProfile ? ['profile'] : []), ...(needAccount ? ['account'] : [])])
      const completed = stage => { waiting.delete(stage); flight.stage = [...waiting].join('+') || 'complete' }
      flight.stage = [...waiting].join('+')
      const profileRead = needProfile ? readProfile().then(profile => {
        save({ profile: summary(profile), profileAt: now(), profileRevision: readCachedProfile()?.revision || 0 })
      }).catch(error => { error.profileLoadStage = 'profile'; throw error }).finally(() => completed('profile')) : Promise.resolve()
      const accountRead = needAccount ? readAccount().then(account => {
        save({ account: { avatar: account.avatar, nickname: account.nickname }, accountAt: now() })
      }).catch(error => {
        if (privateCodes.has(Number(error.code)) || privateCodes.has(error.code)) { error.profileLoadStage = 'account'; throw error }
        if (current()) report({ stage: 'account', code: error.code || 'READ_FAILED', elapsedMs: now() - flight.started })
      }).finally(() => completed('account')) : Promise.resolve()
      await Promise.all([profileRead, accountRead])
      check()
      return true
    })()
    flight.promise = Promise.race([work, deadline]).catch(error => {
      if (pending !== flight || disposed) return false
      const code = Number.isFinite(Number(error.code)) ? Number(error.code) : error.code
      if (context() !== key || !session()?.token || privateCodes.has(code)) {
        if (cache.entry?.key === key) cache.entry = null
        empty()
        if (!session()?.token || loginCodes.has(code)) requireLogin()
        else if (visible) state.error = '资料访问状态已变化，请重新读取。'
      } else if (visible && code !== 'CANCELLED') {
        state.error = state.profile ? '资料暂未更新，已保留上次显示的信息，请重试。' :
          code === 'PROFILE_TIMEOUT' ? '资料读取超时，请重试。' : '资料暂时无法读取，请重试。'
      }
      if (code !== 'CANCELLED') report({ stage: error.profileLoadStage || flight.stage, code: code || 'READ_FAILED', elapsedMs: now() - flight.started })
      return false
    }).finally(() => {
      cancel(timer)
      if (pending === flight) { pending = null; state.busy = false }
    })
    return flight.promise
  }
  return { show, hide() { visible = false }, clear,
    dispose() { disposed = true; visible = false; const flight = pending; pending = null; flight?.stop?.() } }
}
