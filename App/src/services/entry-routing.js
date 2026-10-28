// Both login and session restoration use this decision; no demo completion flags.
export function createEntryResolver({ auth, readProfile, session, pendingPreparation = () => false, invitation = () => '', invitationRoute = code => '/pages/invite/index?token=' + encodeURIComponent(code) }) {
  let generation = 0
  return async function resolve() {
    const mine = ++generation
    const account = await auth.restore()
    if (!account?.token) return '/pages/index/index'
    let expectedFamily=account.householdId, expectedRevision=account.clientRevision
    const current = () => {
      const now = session()
      if (mine !== generation || now?.accountId !== account.accountId || now?.token !== account.token || now?.householdId !== expectedFamily || now?.clientRevision !== expectedRevision) {
        throw Object.assign(new Error('账号已变化，请重新进入。'), { code: 'SESSION_CHANGED' })
      }
    }
    current()
    const pending = invitation()
    if (pending) return invitationRoute(pending)
    const families = account.families || []
    if (!families.length) return '/pages/onboarding/index'
    let id = account.householdId
    if (!families.some(family => family.id === id)) {
      if (families.length !== 1) return '/pages/family-select/index'
      await auth.selectFamily(families[0].id)
      expectedFamily=families[0].id;expectedRevision=session()?.clientRevision
      current()
      id = families[0].id
    }
    // The fresh WeChat session already proves this member's confirmed profile
    // is ready. It is only a routing decision; chat still reads its own current
    // profile and consultation consent before enabling business actions.
    if (invitation()) return invitationRoute(invitation())
    if (pendingPreparation()) return '/pages/onboarding/preparing'
    const selected = (session()?.families || families).find(family => family.id === id)
    if (selected?.onboardingRequired === false) return '/pages/chat/index'
    const profile = await readProfile()
    current()
    if (session()?.householdId !== id || profile.householdId !== id) throw new Error('家庭已变化，请重新选择。')
    if (invitation()) return invitationRoute(invitation())
    if (pendingPreparation()) return '/pages/onboarding/preparing'
    if (profile.completeProfile === true || profile.onboarded === true) {
      return '/pages/chat/index'
    }
    return '/pages/onboarding/index'
  }
}

// A navigation chain can ask for the same entry several times (App foreground,
// welcome restoration and the native navigation guard). Reuse its verified
// decision briefly, never a demo flag or an old account's result.
export function createEntryCoordinator({ resolve, session, invitation = () => '', pendingPreparation = () => false,
  profileState = () => null, now = Date.now, lifetime = 5000 }) {
  let pending = null, verified = null
  function context() {
    const account = session()
    return JSON.stringify([account?.accountId, account?.token, account?.householdId,
      account?.authSource, account?.clientRevision,
      (account?.families || []).map(family => [family.id, family.onboardingRequired]),
      invitation(), pendingPreparation(), profileState()])
  }
  return function resolveEntry({ fresh = false } = {}) {
    const key = context(), account = session(), time = now()
    const owner = JSON.stringify([account?.accountId, account?.token, account?.householdId, account?.authSource, account?.clientRevision])
    const expired = Number.isFinite(account?.expiresAt) && account.expiresAt * 1000 <= time
    if (!fresh && !expired && verified?.key === key && time >= verified.at && time - verified.at < lifetime) {
      return Promise.resolve(verified.route)
    }
    // The resolver rereads invitation/preparation after its awaited work. A new
    // invitation must not spawn a competing generation for the same identity.
    if (pending?.owner === owner) return pending.promise
    const flight = { owner }
    flight.promise = Promise.resolve().then(resolve).then(route => {
      const current = session()
      const sameIdentity = ['accountId','token','authSource'].every(field => current?.[field] === account?.[field])
      const sameSelection = !account?.householdId || current?.householdId === account.householdId && current?.clientRevision === account.clientRevision
      if (pending === flight && sameIdentity && sameSelection) verified = { key: context(), route, at: now() }
      return route
    }, error => {
      if (pending === flight) verified = null
      throw error
    }).finally(() => { if (pending === flight) pending = null })
    pending = flight
    return flight.promise
  }
}
