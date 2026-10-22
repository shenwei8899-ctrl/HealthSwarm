// Both login and session restoration use this decision; no demo completion flags.
export function createEntryResolver({ auth, readProfile, session, invitation = () => '', invitationRoute = code => '/pages/invite/index?token=' + encodeURIComponent(code) }) {
  let generation = 0
  return async function resolve() {
    const mine = ++generation
    const account = await auth.restore()
    if (!account?.token) return '/pages/index/index'
    const current = () => {
      const now = session()
      if (mine !== generation || now?.accountId !== account.accountId || now?.token !== account.token) {
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
      current()
      id = families[0].id
    }
    const profile = await readProfile()
    current()
    if (session()?.householdId !== id || profile.householdId !== id) throw new Error('家庭已变化，请重新选择。')
    return profile.onboarded === true ? '/pages/chat/index' : '/pages/onboarding/index'
  }
}
