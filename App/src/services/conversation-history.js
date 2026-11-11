import { readChatSnapshot } from './cloud-chat.js'
import { storageContext } from './storage.js'

/** 仅在当前登录会话内保留有限正文；缓存不授予发送或业务操作权限。 */
export function createConversationHistoryCache({ read = readChatSnapshot, context = storageContext, maxEntries = 8, maxBytes = 2 * 1024 * 1024 } = {}) {
  const entries = new Map(), flights = new Map(), versions = new Map()
  let owner, generation = 0, bytes = 0
  const clone = value => JSON.parse(JSON.stringify(value))
  function clear() { generation++; entries.clear(); flights.clear(); versions.clear(); bytes = 0; owner = context() }
  function identity() { if (owner !== context()) clear() }
  const keyFor = (threadId, memberId) => memberId + ':' + threadId
  function remove(key) { bytes -= entries.get(key)?.bytes || 0; entries.delete(key) }
  function invalidate(threadId, memberId) {
    identity(); const key = keyFor(threadId, memberId)
    remove(key); flights.delete(key); versions.set(key, (versions.get(key) || 0) + 1)
  }
  function peek(threadId, memberId) {
    identity(); const key = keyFor(threadId, memberId), entry = entries.get(key)
    if (!entry) return null
    entries.delete(key); entries.set(key, entry)
    return clone(entry.snapshot)
  }
  async function load(threadId, memberId, { refresh = false } = {}) {
    identity()
    if (!refresh) { const saved = peek(threadId, memberId); if (saved) return saved }
    const key = keyFor(threadId, memberId)
    if (flights.has(key)) return clone(await flights.get(key))
    const scope = owner, mine = generation, version = versions.get(key) || 0
    const current = () => scope === context() && mine === generation && version === (versions.get(key) || 0)
    const operation = Promise.resolve().then(async () => {
      try {
        const snapshot = await read(threadId)
        if (!current()) throw Object.assign(new Error('历史读取已失效'), { code: 'STALE_HISTORY' })
        const saved = clone(snapshot), size = JSON.stringify(saved).length * 2
        remove(key)
        if (size <= maxBytes) {
          entries.set(key, { snapshot: saved, bytes: size }); bytes += size
          while (entries.size > maxEntries || bytes > maxBytes) remove(entries.keys().next().value)
        }
        return saved
      } catch (failure) {
        if (current() && [401, 403, 404, 409, 410].includes(Number(failure.code))) invalidate(threadId, memberId)
        if (scope !== context() && mine === generation) clear()
        throw failure
      } finally { if (flights.get(key) === operation) flights.delete(key) }
    })
    flights.set(key, operation)
    return clone(await operation)
  }
  return { peek, read: load, invalidate, clear }
}

export const conversationHistory = createConversationHistoryCache()
