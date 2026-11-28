// Guest receipts survive welcome redirects; the server owns their validity.
export function createReferralEntry({ storage, send, session, now = Date.now }) {
  const key = 'fn-friend-referral-v1'
  let flight = Promise.resolve(), generation = 0
  function read() {
    const value = storage.getStorageSync(key)
    return value?.receipt && Number.isFinite(value.expires_at) && value.expires_at * 1000 > now() ? value : null
  }
  function clear() { generation++; storage.setStorageSync(key, null) }
  function capture(options) {
    const query = options?.query || {}
    let code = query.ref, channel = 'share'
    if (!code && typeof query.scene === 'string') {
      try { code = /^r=([A-Za-z0-9_-]{24})$/.exec(decodeURIComponent(query.scene))?.[1]; channel = 'qr' } catch { return flight }
    }
    if (!/^[A-Za-z0-9_-]{24}$/.test(code || '') || session()?.token) return flight
    const mine = generation
    flight = flight.then(async () => {
      if (mine !== generation || session()?.token || read()) return
      try {
        const { data } = await send({ path: '/api/referrals/resolve', method: 'POST', data: { code, channel }, authenticated: false })
        if (mine === generation && !session()?.token && data?.valid === true && typeof data.receipt === 'string' &&
            Number.isFinite(data.expires_at) && data.expires_at * 1000 > now()) storage.setStorageSync(key, data)
      } catch { /* An unavailable invitation must not block ordinary login. */ }
    })
    return flight
  }
  async function pending() { await flight; return read()?.receipt || '' }
  function consume(receipt) { if (read()?.receipt === receipt) clear() }
  return { capture, pending, consume, clear }
}
