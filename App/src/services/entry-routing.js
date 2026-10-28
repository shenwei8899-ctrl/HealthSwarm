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
    const profile = await readProfile()
    current()
    if (session()?.householdId !== id || profile.householdId !== id) throw new Error('家庭已变化，请重新选择。')
    if (pendingPreparation()) return '/pages/onboarding/preparing'
    if (profile.completeProfile === true || profile.onboarded === true) {
      return '/pages/chat/index'
    }
    return '/pages/onboarding/index'
  }
}
