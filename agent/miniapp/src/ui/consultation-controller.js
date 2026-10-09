import { profileLinkSummary, basicProfileSummary } from './member-projection.js'
import { CONSULTATION_SCOPES, consultationMember, consultationPolicy, boundConsultation, consultationList,
  historyProjection, resultProjection, visibleHistory, requestProjection, runProjection, activeRunProjection } from './consultation-projection.js'

const initialState = () => ({ account: null, member: null, link: null, profile: null, policy: null,
  loading: false, busy: false, historyLoading: false, listLoading: false, error: '', notice: '', blocked: false,
  consentChoice: false, consentAccepted: false, consultations: [], hasMore: false, nextOffset: 0,
  thread: null, messages: [], query: '', request: null, run: null, polling: false, pollTimedOut: false,
  submitUnknown: false, createUnknown: false, createMode: '', needsNew: false })

function requestId() {
  if (typeof globalThis.crypto?.randomUUID === 'function') return globalThis.crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, character => {
    const random = Math.floor(Math.random() * 16)
    return (character === 'x' ? random : (random & 3) | 8).toString(16)
  })
}

function protocolFailure(message) { const error = new Error(message); error.code = 'protocol_mismatch'; return error }
// 服务端可能已经提交业务事务，再在投递或返回响应时失败。
const uncertainWriteFailure = error => error?.status === 0 || (error?.status >= 500 && error?.status < 600)

/** 页面内存控制器。会话、页面与线程变化均废弃晚到结果；不保存正文或用途同意。 */
export function createConsultationController({ client, onChange = () => {}, onUnauthorized = () => {},
  schedule = (callback, ms) => setTimeout(callback, ms), cancel = handle => clearTimeout(handle),
  now = () => Date.now(), newId = requestId,
  pollInterval = 1500, pollBudget = 90000 }) {
  let state = initialState(), visible = false, epoch = 0, timer = null, memberId = '', intent = null, creation = null
  const emit = () => onChange({ ...state, messages: [...state.messages], consultations: [...state.consultations] })
  function stopPolling() { if (timer !== null) cancel(timer); timer = null; state.polling = false }
  function reset() { epoch += 1; stopPolling(); intent = null; creation = null; state = initialState(); emit() }
  const ticket = () => ({ epoch, revision: client.sessionRevision })
  const current = token => visible && token.epoch === epoch && token.revision === client.sessionRevision && !!client.getSession()
  const failureText = error => error?.message || '服务暂不可用，请重新读取'
  function invalidateOperations() {
    epoch += 1; stopPolling()
    state.loading = false; state.busy = false; state.historyLoading = false; state.listLoading = false; state.pollTimedOut = false
  }
  function revokeView(message) {
    invalidateOperations(); intent = null; creation = null
    state.messages = []; state.thread = null; state.query = ''; state.request = null; state.run = null
    state.consentAccepted = false; state.consentChoice = false; state.submitUnknown = false; state.createUnknown = false
    state.blocked = true; state.error = message; emit()
  }
  function handleError(error, token) {
    if (!current(token) || error?.code === 'stale_session') return
    if ([401, 403, 404].includes(error?.status) || ['run_not_found', 'protocol_mismatch'].includes(error?.code)) {
      revokeView('当前咨询或成员授权已不可读取。已清除回答，请返回核对身份、授权及档案来源。')
    } else if (error?.status === 410) {
      invalidateOperations(); intent = null; creation = null
      state.messages = []; state.thread = null; state.query = ''; state.request = null; state.run = null
      state.consentAccepted = false; state.consentChoice = false; state.submitUnknown = false; state.createUnknown = false
      state.needsNew = true; state.error = '原咨询来源已变化，不能继续此线程。请重新核对政策并明确新建咨询。'; emit()
    } else {
      state.error = failureText(error)
      if (error?.status === 409) {
        state.consentAccepted = false; state.consentChoice = false
        state.notice = '本次同意已失效，请重新读取当前政策后明确同意。'
      }
      emit()
    }
  }
  const unsubscribe = client.subscribeSession(session => {
    reset()
    state.account = session ? { uid: session.uid, username: session.username } : null
    emit()
    if (!session && visible) onUnauthorized()
  })

  async function show(id) {
    reset(); visible = true; memberId = id
    const session = client.getSession()
    if (!session) { onUnauthorized(); return }
    state.account = { uid: session.uid, username: session.username }; state.loading = true; emit()
    const token = ticket()
    try {
      const rows = await client.listHealthMembers()
      if (!current(token)) return
      state.member = consultationMember(rows, memberId)
      const mapping = profileLinkSummary(await client.readProfileLink(memberId))
      if (!current(token)) return
      if (mapping.member_id !== memberId || !mapping.family_id || !mapping.source_member_id) throw protocolFailure('尚未核对真实本人关联，请返回本人成员接入页')
      state.link = mapping
      const [profile, policy] = await Promise.all([client.readFamilyProfile(memberId), client.readConsultationConfiguration()])
      if (!current(token)) return
      state.profile = basicProfileSummary(profile); state.policy = consultationPolicy(policy)
      await loadConsultations(false, token)
    } catch (error) {
      if (current(token)) { state.blocked = true; handleError(error, token) }
    } finally {
      if (current(token)) { state.loading = false; emit() }
    }
  }
  function hide() { visible = false; reset() }
  function dispose() { hide(); unsubscribe() }
  const eligible = () => !!state.link && !!state.policy?.available && !state.blocked
    && CONSULTATION_SCOPES.every(scope => state.member?.scopes.includes(scope))
  function setConsentChoice(value) { if (!state.busy) { state.consentChoice = value === true; emit() } }
  function setQuery(value) { if (!state.busy && !intent) { state.query = typeof value === 'string' ? value : ''; emit() } }

  async function loadConsultations(more = false, suppliedToken) {
    if (!state.member || state.listLoading || state.blocked || (more && !state.hasMore)) return
    const token = suppliedToken || ticket(), offset = more ? state.nextOffset : 0
    state.listLoading = true; emit()
    try {
      const page = consultationList(await client.listMemberConsultations(memberId, { limit: 20, offset }), memberId)
      if (!current(token)) return
      if (page.has_more && page.next_offset <= offset) throw protocolFailure('咨询分页未向后推进，请重新读取')
      const combined = more ? [...state.consultations, ...page.items] : page.items
      state.consultations = [...new Map(combined.map(row => [row.thread_id, row])).values()]
      state.hasMore = page.has_more; state.nextOffset = page.next_offset; emit()
    } catch (error) { handleError(error, token) }
    finally { if (current(token)) { state.listLoading = false; emit() } }
  }

  async function readHistory(thread, token) {
    const history = historyProjection(await client.readThreadHistory(thread.thread_id), thread.thread_id, state.account.uid)
    if (!current(token)) return null
    const results = []
    // 最近20个完成的顶层运行逐个重新鉴权；任何拒读都不留下半批旧回答。
    for (const run of history.completed) {
      const result = await client.readAgentRunResult(run.run_id)
      if (!current(token)) return null
      results.push(resultProjection(result, { ...run, thread_id: thread.thread_id }))
    }
    return visibleHistory(history, results)
  }

  async function openThread(threadId) {
    if (state.busy || state.historyLoading || state.blocked || intent || state.createUnknown) return
    const thread = state.consultations.find(row => row.thread_id === threadId)
    if (!thread) return
    state.consentAccepted = false; state.consentChoice = false
    await activateThread(thread, ticket())
  }
  async function activateThread(thread, token) {
    stopPolling(); state.thread = thread; state.messages = []; state.query = ''; state.request = null; state.run = null
    state.submitUnknown = false; state.pollTimedOut = false; state.error = ''; state.notice = ''; state.historyLoading = true; emit()
    try {
      const messages = await readHistory(thread, token)
      if (!current(token) || messages === null) return
      const active = activeRunProjection(await client.readThreadActiveRun(thread.thread_id), thread.thread_id)
      if (!current(token)) return
      state.messages = messages
      if (active) {
        state.run = active; state.request = { request_id: active.request_id, status: 'dispatched', run_id: active.run_id }
        intent = { thread_id: thread.thread_id, request_id: active.request_id, uid: state.account.uid, query: null }
      }
      emit()
      if (active && !['completed', 'failed', 'cancelled', 'interrupted'].includes(active.status)) startPolling(token)
      else if (active) {
        intent = null
        if (active.status === 'interrupted') state.notice = '运行待处理。专属营养咨询不支持审批恢复，可明确新建独立咨询后重新提问。'
      }
    } catch (error) { handleError(error, token) }
    finally { if (current(token)) { state.historyLoading = false; emit() } }
  }

  async function refreshPolicy() {
    if (state.busy || state.loading || state.blocked || state.createUnknown || intent) return
    const token = ticket(); state.busy = true; state.consentChoice = false; state.consentAccepted = false; state.error = ''; emit()
    try {
      const policy = await client.readConsultationConfiguration()
      if (current(token)) state.policy = consultationPolicy(policy)
    } catch (error) { handleError(error, token) }
    finally { if (current(token)) { state.busy = false; emit() } }
  }
  async function acceptConsent(token) {
    const policy = state.policy
    const response = await client.setConsultationConsent(memberId, { accepted: true, processor: policy.processor, policy_version: policy.policy_version })
    if (!current(token)) return false
    if (response?.accepted !== true) throw protocolFailure('服务未确认本次用途同意，请重新核对')
    state.consentAccepted = true; state.consentChoice = false; emit(); return true
  }
  async function acceptForThread() {
    if (!eligible() || !state.thread || !state.consentChoice || state.busy || state.historyLoading) return
    const token = ticket(); state.busy = true; state.error = ''; emit()
    try { await acceptConsent(token) }
    catch (error) { handleError(error, token) }
    finally { if (current(token)) { state.busy = false; emit() } }
  }
  async function withdrawConsent() {
    if (!state.policy || state.busy || state.blocked) return
    const token = ticket(); state.busy = true; state.error = ''; emit()
    try {
      const response = await client.setConsultationConsent(memberId, { accepted: false, processor: state.policy.processor, policy_version: state.policy.policy_version })
      if (!current(token)) return
      if (response?.accepted !== false) throw protocolFailure('服务未确认撤回用途同意，请重新核对')
      state.consentAccepted = false; state.consentChoice = false
      state.notice = '已撤回咨询用途同意，禁止新问题与后续模型处理；已授权的历史是否可读仍由服务端判断。'
    } catch (error) { handleError(error, token) }
    finally { if (current(token)) { state.busy = false; emit() } }
  }

  async function createThread(mode, retry = false) {
    if (!eligible() || state.busy || state.historyLoading || intent || (!retry && (!state.consentChoice || state.createUnknown))) return
    if (retry && (!creation || !state.createUnknown || (!state.consentAccepted && !state.consentChoice))) return
    const token = ticket(); state.busy = true; state.error = ''; emit()
    if (!retry) creation = { mode, client_request_id: newId(), policy: { ...state.policy } }
    const original = creation
    let creationSent = false, creationConfirmed = false
    state.createMode = original.mode
    try {
      if (!state.consentAccepted && !(await acceptConsent(token))) return
      creationSent = true
      const response = original.mode === 'daily' ? await client.createDailyConsultation(memberId)
        : await client.createConsultation(memberId, { client_request_id: original.client_request_id })
      if (!current(token)) return
      const thread = boundConsultation(response, memberId)
      creationConfirmed = true
      state.createUnknown = false; state.needsNew = false; creation = null
      state.consultations = [thread, ...state.consultations.filter(row => row.thread_id !== thread.thread_id)]
      await activateThread(thread, token)
    } catch (error) {
      if (current(token)) {
        if (creationSent && !creationConfirmed) {
          state.createUnknown = uncertainWriteFailure(error)
          if (!state.createUnknown) creation = null
        } else if (!state.createUnknown) creation = null
      }
      handleError(error, token)
    } finally { if (current(token)) { state.busy = false; emit() } }
  }

  async function submit(retry = false) {
    if (!eligible() || !state.thread || !state.consentAccepted || state.busy || state.historyLoading || state.run?.status === 'interrupted') return
    if ((!retry && (intent || !state.query.trim())) || (retry && (!intent?.query || !state.submitUnknown))) return
    const token = ticket()
    if (!retry) intent = { thread_id: state.thread.thread_id, request_id: newId(), uid: state.account.uid, query: state.query }
    const original = intent
    state.busy = true; state.error = ''; state.pollTimedOut = false; emit()
    try {
      const response = await client.submitConsultationRequest(original.thread_id, { query: original.query, request_id: original.request_id })
      if (!current(token)) return
      state.request = requestProjection(response, original, true); state.submitUnknown = false; state.query = ''; emit()
      startPolling(token)
    } catch (error) {
      if (current(token)) {
        if (uncertainWriteFailure(error)) state.submitUnknown = true
        else if (![401, 403, 404, 410].includes(error?.status)) { intent = null; state.submitUnknown = false }
      }
      handleError(error, token)
    } finally { if (current(token)) { state.busy = false; emit() } }
  }

  function startPolling(token) {
    stopPolling(); state.polling = true; state.pollTimedOut = false; emit()
    const started = now()
    async function poll() {
      timer = null
      if (!current(token) || !intent) return
      if (now() - started >= pollBudget) {
        state.polling = false; state.pollTimedOut = true
        state.notice = '本次等待已超时，服务端请求仍可能执行。请继续读取同一请求。'; emit(); return
      }
      try {
        const expected = intent
        const request = requestProjection(await client.readAgentRequest(expected.request_id), expected)
        if (!current(token) || intent !== expected) return
        state.request = request
        if (request.run_id) {
          const run = runProjection(await client.readAgentRun(request.run_id), { ...expected, run_id: request.run_id })
          if (!current(token) || intent !== expected) return
          state.run = run
          if (run.status === 'completed') {
            // 运行结果先按ID核对；再从历史精确选择同一最终回答。
            const final = resultProjection(await client.readAgentRunResult(run.run_id), { ...expected, run_id: run.run_id })
            if (!current(token) || intent !== expected) return
            const messages = await readHistory(state.thread, token)
            if (!current(token) || intent !== expected || messages === null) return
            if (!messages.some(row => row.role === 'assistant' && row.id === final.id && row.run_id === final.run_id)) {
              throw new Error('运行已完成，最终回答尚未在历史中核对成功。请继续读取原请求。')
            }
            state.messages = messages; intent = null; state.polling = false; state.notice = '咨询已完成。'; emit(); return
          }
          if (['failed', 'cancelled', 'interrupted'].includes(run.status)) {
            intent = null; state.polling = false
            state.notice = run.status === 'interrupted' ? '运行待处理。专属营养咨询不支持审批恢复，可明确新建独立咨询后重新提问。'
              : run.status === 'failed' ? '运行失败。没有展示未完成回答，可明确提交新问题。' : '运行已取消。'
            emit(); return
          }
        } else if (['failed', 'rejected', 'cancelled'].includes(request.status)) {
          intent = null; state.polling = false; state.notice = '服务端未继续执行此请求，可明确提交新问题。'; emit(); return
        }
        emit()
        timer = schedule(poll, pollInterval)
      } catch (error) {
        if (!current(token)) return
        state.polling = false
        if (![401, 403, 404, 410].includes(error?.status)) state.pollTimedOut = !!intent
        handleError(error, token)
      }
    }
    // 普通有界HTTP轮询，不引入新的运行状态或自动重发正文。
    void poll()
  }
  function continuePolling() {
    if (!intent || state.submitUnknown || state.polling || state.busy || state.blocked || !visible) return
    state.error = ''; state.notice = ''; startPolling(ticket())
  }

  return { show, hide, dispose, setConsentChoice, setQuery, refreshPolicy, loadConsultations, openThread,
    acceptForThread, withdrawConsent, createThread, submit, continuePolling,
    getState: () => ({ ...state, messages: [...state.messages], consultations: [...state.consultations] }) }
}
