import { request } from './request.js'
import { scopedStorage, storageContext } from './storage.js'
import { newHealthRequestId } from './health-request-id.js'

export const chatMealRecordState = () => ({ record: null, busy: false, error: '', pending: null })

export function createChatMealRecordClient({ state, id, send = request, storage = scopedStorage, context = storageContext, newId = newHealthRequestId }) {
  let generation = 0
  const key = 'chat-meal-withdraw:' + id
  const valid = record => record?.id === id && ['saved', 'withdrawn'].includes(record.status) && Number.isInteger(record.source_version) && record.source_version > 0 && Array.isArray(record.items)
  const clearPending = () => { storage.setStorageSync(key, null); state.pending = null }
  async function perform(withdraw) {
    if (state.busy) return null
    const mine = ++generation, scope = context(), current = () => mine === generation && scope === context()
    state.busy = true; state.error = ''
    try {
      state.pending = storage.getStorageSync(key) || null
      if (withdraw) {
        if (!state.pending) {
          if (!state.record || state.record.status !== 'saved') return null
          const requestId = newId()
          state.pending = { path: `/api/health/v1/chat-meals/${id}/withdraw`, method: 'POST',
            headers: { 'Idempotency-Key': requestId, 'If-Match': '"' + state.record.source_version + '"' },
            data: { client_request_id: requestId, expected_version: state.record.source_version } }
          storage.setStorageSync(key, state.pending)
        }
        const { data } = await send(state.pending)
        if (!current()) return null
        if (!valid(data) || data.status !== 'withdrawn') throw new Error('撤销回执尚未确认，请重试原请求')
      }
      const { data } = await send({ path: `/api/health/v1/chat-meals/${id}` })
      if (!current()) return null
      if (!valid(data)) throw new Error('记餐状态返回不完整，请重新读取')
      state.record = data
      if (data.status === 'withdrawn') clearPending()
      return data
    } catch (error) {
      if (!current()) return null
      if ([401, 403, 404, 410].includes(Number(error.code))) { state.record = null; clearPending() }
      else if (Number(error.code) === 409) clearPending()
      state.error = state.pending ? '撤销结果尚未确认，请重试核对原请求。' : error.message
      return null
    } finally {
      if (mine === generation) {
        if (scope !== context()) { state.record = null; state.pending = null; state.error = '' }
        state.busy = false
      }
    }
  }
  return { refresh: () => perform(false), withdraw: () => perform(true),
    hide() { generation++; state.record = null; state.pending = null; state.error = ''; state.busy = false } }
}
