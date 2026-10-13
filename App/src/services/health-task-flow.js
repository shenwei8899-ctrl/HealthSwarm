import { request } from './request.js'
import { getSession, sessionRevision } from './session.js'
import { scopedStorage } from './storage.js'

export const HEALTH_TEXT_TASKS = Object.freeze({
  consultation: '营养咨询', blood_glucose_review: '血糖记录回顾',
  blood_lipids_review: '血脂记录回顾', blood_pressure_review: '血压记录回顾',
})
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const terminalStatuses = new Set(['completed', 'failed', 'cancelled', 'interrupted'])
const privateFailure = error => [401, 403, 404, 409, 410].includes(Number(error?.code))
const uncertainFailure = error => error?.code === 'NETWORK_ERROR' || Number(error?.code) >= 500
const mismatch = () => Object.assign(new Error('任务与当前成员或线程不一致，请返回重新核对'), { code: 'TASK_MISMATCH' })

export function newHealthRequestId() {
  if (typeof globalThis.crypto?.randomUUID === 'function') return globalThis.crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, char => {
    const value = Math.floor(Math.random() * 16)
    return (char === 'x' ? value : (value & 3) | 8).toString(16)
  })
}

export function createHealthTaskFlow({ send = request, session = getSession, revision = sessionRevision,
  storage = scopedStorage, newId = newHealthRequestId, onChange = () => {},
  schedule = (fn, ms) => setTimeout(fn, ms), cancel = handle => clearTimeout(handle),
  pollInterval = 2000, pollLimit = 45 } = {}) {
  let epoch = 0, readVersion = 0, timer = null, polls = 0, pendingQuery = '', storageKey = ''
  let state = { memberId: '', taskType: '', title: '', loading: false, busy: false, available: false,
    consentOption: null, entry: null, requestId: '', submitUnknown: false, status: '', result: null, error: '', notice: '' }
  const emit = () => onChange({ ...state, canRetry: !!pendingQuery && state.submitUnknown,
    entry: state.entry && { ...state.entry }, result: state.result && { ...state.result } })
  const token = () => ({ epoch, revision: revision(), accountId: session()?.accountId })
  const current = ticket => ticket.epoch === epoch && ticket.revision === revision() &&
    ticket.accountId && ticket.accountId === session()?.accountId
  function stop() { if (timer !== null) cancel(timer); timer = null; polls = 0 }
  function forgetPrivate(message) {
    stop(); pendingQuery = ''; state.entry = null; state.requestId = ''; state.submitUnknown = false
    state.result = null; state.available = false; state.consentOption = null; state.status = ''; state.error = message
    if (storageKey) storage.setStorageSync(storageKey, null)
    emit()
  }
  function hide() {
    epoch++; readVersion++; stop(); pendingQuery = ''; storageKey = ''
    state = { memberId: '', taskType: '', title: '', loading: false, busy: false, available: false,
      consentOption: null, entry: null, requestId: '', submitUnknown: false, status: '', result: null, error: '', notice: '' }
    emit()
  }
  function save() {
    storage.setStorageSync(storageKey, { memberId: state.memberId, taskType: state.taskType,
      entry: state.entry, requestId: state.requestId, submitUnknown: state.submitUnknown })
  }
  function handle(error, ticket) {
    if (Number(error?.code) === 401 && ticket.epoch === epoch && !session()?.token) {
      forgetPrivate('登录已过期，请重新登录后核对任务。'); return
    }
    if (!current(ticket)) return
    state.result = null
    if (privateFailure(error) || error?.code === 'TASK_MISMATCH' || error?.code === 'SESSION_CHANGED') {
      forgetPrivate('当前任务或成员已不可读取，请返回核对身份、授权和资料来源。')
    } else { state.error = error?.message || '服务暂不可用，请手动重试'; emit() }
  }
  async function open(memberId, taskType) {
    hide()
    if (!uuidPattern.test(memberId || '') || !Object.prototype.hasOwnProperty.call(HEALTH_TEXT_TASKS, taskType)) {
      state.error = '健康任务参数无效，请返回重新选择'; emit(); return
    }
    state.memberId = memberId; state.taskType = taskType; state.title = HEALTH_TEXT_TASKS[taskType]
    storageKey = `health-task:${memberId}:${taskType}`
    if (!session()?.token) { state.error = '请先登录后再读取健康任务'; emit(); return }
    const ticket = token(); state.loading = true; emit()
    try {
      const [members, readiness] = await Promise.all([
        send({ path: '/api/health/v1/members' }),
        send({ path: `/api/health/v1/members/${memberId}/readiness` }),
      ])
      if (!current(ticket)) return
      if (!Array.isArray(members.data) || !members.data.some(row => row.id === memberId && row.is_owner === true) ||
        readiness.data?.capabilities?.member_id !== memberId || !Array.isArray(readiness.data?.entries)) throw mismatch()
      const entry = readiness.data.entries.find(row => row.entry_type === taskType)
      state.available = entry?.status === 'available'
      if (!state.available) state.notice = '当前成员的该服务尚未就绪，请返回账号页查看授权与依赖状态。'
      if (entry?.reason_code === 'consent_required') {
        const policy = (await send({ path: '/api/health/v1/configuration' })).data
        if (!current(ticket)) return
        if (policy?.consultation?.available === true && typeof policy.consultation.processor === 'string' &&
          policy.consultation.processor && typeof policy.policy_version === 'string' && policy.policy_version) {
          state.consentOption = { processor: policy.consultation.processor, policyVersion: policy.policy_version }
          state.notice = '请先核对当前咨询处理方和政策版本，再明确选择是否同意。'
        }
      }
      const saved = storage.getStorageSync(storageKey)
      if (saved?.memberId === memberId && saved?.taskType === taskType && saved.entry?.thread_id && saved.entry?.agent_slug) {
        state.entry = saved.entry; state.requestId = saved.requestId || ''
        state.submitUnknown = saved.submitUnknown === true
        if (state.requestId) await refresh(ticket)
      } else if (saved?.entry?.client_request_id && saved.entry?.pending === true) {
        state.entry = saved.entry
        state.notice = '上次创建线程的结果未确认，可用原请求键重试。'
      }
      emit()
    } catch (error) { handle(error, ticket) }
    finally { if (current(ticket)) { state.loading = false; emit() } }
  }
  async function acceptConsent(accepted) {
    if (accepted !== true || !state.consentOption || state.busy || state.loading) return
    const ticket = token(), { memberId, taskType, consentOption } = state
    state.busy = true; state.error = ''; emit()
    try {
      const { data } = await send({ path: `/api/health/v1/members/${memberId}/processing-consents`, method: 'POST',
        data: { purpose: 'consultation', accepted: true, processor: consentOption.processor,
          policy_version: consentOption.policyVersion } })
      if (!current(ticket)) return
      if (data?.accepted !== true) throw mismatch()
      await open(memberId, taskType)
    } catch (error) { handle(error, ticket) }
    finally { if (current(ticket)) { state.busy = false; emit() } }
  }
  async function createEntry() {
    if (!state.available || state.busy || state.loading || state.entry?.thread_id) return
    const ticket = token(), id = state.memberId, type = state.taskType
    const clientId = state.entry?.client_request_id || newId()
    if (!uuidPattern.test(clientId)) throw new Error('无法生成有效请求标识')
    state.entry = { client_request_id: clientId, pending: true }; state.busy = true; state.error = ''; save(); emit()
    try {
      const response = await send({ path: `/api/health/v1/members/${id}/task-entries`, method: 'POST',
        headers: { 'Idempotency-Key': clientId }, data: { task_type: type, client_request_id: clientId } })
      if (!current(ticket)) return
      const row = response.data
      if (row?.member_id !== id || row?.task_type !== type || row?.client_request_id !== clientId) throw mismatch()
      if (row.entry_status !== 'ready') {
        state.entry = null; state.available = false; state.notice = row.entry_status === 'needs_input'
          ? '请先完成服务端要求的选择，再重新进入。' : '服务端依赖尚未就绪，请稍后重新读取。'
      } else {
        if (!uuidPattern.test(row.thread_id) || !row.agent_slug || row.request_submit_url !== '/api/agent/runs') throw mismatch()
        state.entry = { client_request_id: clientId, thread_id: row.thread_id, agent_slug: row.agent_slug }
        state.notice = '线程已创建。请明确输入本次问题。'
      }
      save(); emit()
    } catch (error) {
      if (current(ticket)) {
        if (!uncertainFailure(error)) { state.entry = null; save() }
        handle(error, ticket)
      }
    } finally { if (current(ticket)) { state.busy = false; emit() } }
  }
  async function submit(query, retry = false) {
    if (!state.available || !state.entry?.thread_id || state.busy || state.loading) return
    if (state.submitUnknown && !retry) return
    if (state.requestId && !terminalStatuses.has(state.status) && !retry) return
    const text = retry ? pendingQuery : String(query || '').trim()
    if (!text || text.length > 4000 || (retry && !state.submitUnknown)) return
    const ticket = token()
    if (!retry) { state.requestId = newId(); pendingQuery = text; state.submitUnknown = true; state.status = '提交中'; state.result = null; save() }
    state.busy = true; state.error = ''; emit()
    try {
      const response = await send({ path: '/api/agent/runs', method: 'POST',
        data: { agent_slug: state.entry.agent_slug, thread_id: state.entry.thread_id,
          query: text, meta: { request_id: state.requestId } } })
      if (!current(ticket)) return
      if (response.data?.request_id !== state.requestId || response.data?.thread_id !== state.entry.thread_id) throw mismatch()
      state.submitUnknown = false; pendingQuery = ''; save()
      await refresh(ticket)
      return true
    } catch (error) {
      if (current(ticket)) {
        if (!uncertainFailure(error)) { state.requestId = ''; state.submitUnknown = false; pendingQuery = ''; save() }
        handle(error, ticket)
      }
      return false
    } finally { if (current(ticket)) { state.busy = false; emit() } }
  }
  async function refresh(givenTicket = token()) {
    if (!state.requestId || !current(givenTicket)) return
    const expectedId = state.requestId, expectedEntry = state.entry, read = ++readVersion
    state.result = null; state.error = ''; emit()
    try {
      const { data } = await send({ path: `/api/health/v1/tasks/${encodeURIComponent(expectedId)}` })
      if (!current(givenTicket) || read !== readVersion || expectedId !== state.requestId) return
      if (data?.request_id !== expectedId || data?.member_id !== state.memberId ||
        data?.task_type !== state.taskType || data?.thread_id !== expectedEntry?.thread_id ||
        data?.agent_slug !== expectedEntry?.agent_slug) throw mismatch()
      state.submitUnknown = false; pendingQuery = ''; state.status = data.execution_status === 'not_dispatched'
        ? data.request_status : data.execution_status
      if (data.execution_status === 'completed') {
        if (data.result?.result_type === 'general_education_answer' && data.result.scope === 'general_education' &&
          typeof data.result.answer === 'string' && Array.isArray(data.result.citations)) {
          state.result = { type: 'answer', text: data.result.answer,
            citations: data.result.citations.map(item => item.title).filter(Boolean) }
        } else if (data.result?.result_type === 'needs_input' && Array.isArray(data.result.questions)) {
          state.result = { type: 'needs_input', questions: data.result.questions }
        } else throw mismatch()
      } else if (data.result?.result_type === 'error') state.result = { type: 'error', code: data.result.code }
      save(); emit()
      if (!terminalStatuses.has(data.execution_status) && !['cancelled', 'rejected', 'failed'].includes(data.request_status)) startPolling(givenTicket)
      else stop()
    } catch (error) {
      if (!current(givenTicket) || read !== readVersion) return
      if (state.submitUnknown && Number(error?.code) === 404) {
        state.error = pendingQuery
          ? '提交结果尚未确认；可重新读取，或在本页用同一请求键重试。'
          : '提交结果尚未确认；请重新读取同一请求，暂勿重复提问。'
        emit()
      } else handle(error, givenTicket)
    }
  }
  function startPolling(ticket) {
    if (timer !== null || !current(ticket)) return
    if (polls >= pollLimit) { state.notice = '等待已暂停，服务端可能仍在执行。请手动读取同一任务。'; emit(); return }
    timer = schedule(() => { timer = null; polls++; void refresh(ticket) }, pollInterval)
  }
  return { open, hide, acceptConsent, createEntry, submit, refresh, getState: () => ({ ...state, canRetry: !!pendingQuery && state.submitUnknown }) }
}
