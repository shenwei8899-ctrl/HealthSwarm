import { readChatSnapshot, chatBusinessDate } from './cloud-chat.js'
import { scopedStorage, storageContext } from './storage.js'
import { conversationHistory } from './conversation-history.js'

export const conversationPreviewState = () => ({ messages: [], loading: false, error: '', notice: '' })

/** 独立读取历史快照，不切换主会话、不恢复或提交生成任务。 */
export function createConversationPreview({ state, read = readChatSnapshot, cache = read === readChatSnapshot ? conversationHistory : null, context = storageContext, storage = scopedStorage, onDenied = () => {} }) {
  let generation = 0, disposed = false
  function clear() { generation++; Object.assign(state, conversationPreviewState()) }
  async function open(row, prepared = null) {
    clear()
    if (disposed || !row || row.unavailable) return
    const mine = generation, scope = context(), snapshots = new Map(), seen = new Set(), pending = []
    let rejected = false
    const current = () => {
      if (disposed || rejected || mine !== generation) return false
      if (scope !== context()) { clear(); return false }
      return true
    }
    const publish = () => {
      const messages = new Map()
      for (const [threadId, snapshot] of snapshots) {
        for (const message of snapshot.messages) {
          if (message.role === 'user' && !message.text && !message.image) continue
          if (row.business_date && message.createdAt && chatBusinessDate(message.createdAt) !== row.business_date) continue
          messages.set(threadId + ':' + message.id, { ...message, threadId })
        }
      }
      state.messages = [...messages.values()].sort((a, b) => (Date.parse(a.createdAt) || 0) - (Date.parse(b.createdAt) || 0))
    }
    async function readOne(threadId) {
      if (seen.has(threadId)) return
      seen.add(threadId)
      try {
        const snapshot = threadId === row.thread_id && prepared && !prepared.fromCache ? prepared.snapshot
          : cache ? await cache.read(threadId, row.member_id, { refresh: true }) : await read(threadId)
        if (!current()) return
        snapshots.set(threadId, snapshot); publish()
        pending.push(...(snapshot.relatedThreads || []).map(pointer => pointer.thread_id))
      } catch (failure) {
        if (!current()) return
        const denied = [401, 403, 404, 409, 410].includes(Number(failure.code))
        if (threadId === row.thread_id || Number(failure.code) === 401) throw failure
        if (denied) {
          snapshots.delete(threadId)
          cache?.invalidate?.(threadId, row.member_id)
          publish()
        }
        state.notice = denied ? '部分历史记录的授权或资料来源已变化，暂不可访问。' : '部分历史记录暂未读取成功，可以重新读取。'
      }
    }
    const cached = prepared?.snapshot || cache?.peek(row.thread_id, row.member_id)
    if (cached) {
      for (const snapshot of prepared?.snapshots || [{ ...cached, threadId: row.thread_id }]) snapshots.set(snapshot.threadId, snapshot)
      publish()
    }
    state.loading = true
    try {
      await readOne(row.thread_id)
      if (!current()) return
      const saved = storage.getStorageSync('conversation-index:' + row.thread_id)
      const pointers = saved?.memberId === row.member_id && typeof saved.id === 'string'
        ? storage.getStorageSync('conversation-threads:' + saved.id) : []
      pending.push(...(Array.isArray(pointers) ? pointers : []).filter(pointer => pointer.task_type === 'reference_meal_preview').map(pointer => pointer.thread_id))
      while (pending.length && current()) await Promise.all(pending.splice(0).map(readOne))
    } catch (failure) {
      if (!current()) return
      rejected = true; state.loading = false
      if ([401, 403, 404, 409, 410].includes(Number(failure.code))) {
        state.messages = []; state.notice = ''
        state.error = '这段对话已不可访问，请重新核对登录与授权。'
        onDenied(row.thread_id, Number(failure.code))
      } else state.error = '历史记录暂时无法读取，可以重新读取。'
    } finally { if (current()) state.loading = false }
  }
  return { open, clear, dispose() { disposed = true; clear() } }
}
