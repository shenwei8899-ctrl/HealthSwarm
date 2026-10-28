// Reuse only an in-flight validation of this exact session. No credentials or
// authorization result survive in a separate persistent cache.
export function createSharedSessionRestore(restore, session) {
  let pending = null
  const owner = () => {
    const account = session()
    return JSON.stringify([account?.accountId, account?.token, account?.householdId,
      account?.authSource, account?.clientRevision])
  }
  return function sharedRestore(...args) {
    const key = owner()
    if (pending?.key === key) return pending.promise
    const flight = { key }
    flight.promise = Promise.resolve().then(() => {
      if (owner() !== key) throw Object.assign(new Error('登录状态已变化，请重新进入。'), { code: 'SESSION_CHANGED' })
      return restore(...args)
    }).finally(() => {
      if (pending === flight) pending = null
    })
    pending = flight
    return flight.promise
  }
}
