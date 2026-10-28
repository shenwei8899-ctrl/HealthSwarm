import { newHealthRequestId } from './health-request-id.js'
export { newHealthRequestId } from './health-request-id.js'
import { request } from './request.js'
import { getSession, sessionRevision } from './session.js'
import { scopedStorage } from './storage.js'
import { readDietRecord } from './cloud-meals.js'
import { subscribeHealthEvents } from './health-events.js'

export const HEALTH_TEXT_TASKS = Object.freeze({
  consultation: '营养咨询', blood_glucose_review: '血糖记录回顾',
  blood_lipids_review: '血脂记录回顾', blood_pressure_review: '血压记录回顾',
  diet_analysis: '已保存餐次反馈',
  meal_preview: '本餐安排',
  initial_meal_preview: '单日专属计划',
  reference_meal_preview: '日常参考餐单',
})
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const terminalStatuses = new Set(['completed', 'failed', 'cancelled', 'interrupted', 'rejected'])
const privateFailure = error => [401, 403, 404, 409, 410].includes(Number(error?.code))
const uncertainFailure = error => error?.code === 'NETWORK_ERROR' || Number(error?.code) >= 500
const mismatch = () => Object.assign(new Error('任务与当前成员或线程不一致，请返回重新核对'), { code: 'TASK_MISMATCH' })
const streamState = () => ({ streamText: '', streamMessageId: '', streamOffset: 0, streamPhase: '', streamStatus: '', queuePosition: null })
const streamLabels = { queued: '请求已收到，正在排队', running: '正在结合资料整理建议', validating: '正在核对内容与资料来源',
  streaming: '正在生成回答', finalizing: '正在整理最终结果', reconnecting: '连接暂时中断，正在恢复回答', cancelling: '正在停止生成' }
function newerCursor(next, previous = '0-0') {
  if (!/^\d+-\d+$/.test(next || '')) return false
  const a = next.split('-'), b = previous.split('-')
  for (let i = 0; i < 2; i++) {
    if (a[i].length !== b[i].length) return a[i].length > b[i].length
    if (a[i] !== b[i]) return a[i] > b[i]
  }
  return false
}


export function createHealthTaskFlow({ send = request, session = getSession, revision = sessionRevision,
  storage = scopedStorage, newId = newHealthRequestId, onChange = () => {},
  subscribe = subscribeHealthEvents,
  schedule = (fn, ms) => setTimeout(fn, ms), cancel = handle => clearTimeout(handle),
  pollInterval = 2000, pollLimit = 45, daily = false, day = () => new Date(Date.now() + 8 * 3600000).toISOString().slice(0, 10) } = {}) {
  let indicatorSelection = null
  let epoch = 0, readVersion = 0, timer = null, polls = 0, pendingQuery = '', storageKey = ''
  let streams = [], streamKey = '', streamAttempts = 0, streamEpoch = 0, cursors = {}, pendingImages = [], cancelRequested = false
  let state = { memberId: '', taskType: '', title: '', loading: false, busy: false, available: false,
    consentOption: null, entry: null, requestId: '', runId: '', requests: [], submitUnknown: false, status: '', result: null, error: '', notice: '', ...streamState() }
  const emit = () => onChange({ ...state, canRetry: (!!pendingQuery || pendingImages.length > 0) && state.submitUnknown,
    pendingText:state.submitUnknown?pendingQuery:'',pendingImages:state.submitUnknown?[...pendingImages]:[],
    entry: state.entry && { ...state.entry }, result: state.result && { ...state.result } })
  const token = () => ({ epoch, revision: revision(), accountId: session()?.accountId })
  const current = ticket => ticket.epoch === epoch && ticket.revision === revision() &&
    ticket.accountId && ticket.accountId === session()?.accountId
  function stopStreams() { streamEpoch++; const old = streams; streams = []; streamKey = ''; old.forEach(close => close?.()) }
  function stop() { if (timer !== null) cancel(timer); timer = null; polls = 0; streamAttempts = 0; stopStreams() }
  function phase(value) { state.streamPhase = value; state.streamStatus = streamLabels[value] || '' }
  function clearStream() { Object.assign(state, streamState()); cancelRequested = false }
  const invalidKey = () => `health-chat-invalid:${state.memberId}:${day()}`
  function invalidateThread() {
    if (daily && state.entry?.thread_id) {
      const old = storage.getStorageSync(invalidKey()) || []
      storage.setStorageSync(invalidKey(), [...new Set([...old, state.entry.thread_id])])
    }
    forgetPrivate('这段对话的资料来源已变化，请开始新咨询，重新核对当前资料。')
  }
  function forgetPrivate(message) {
    epoch++; readVersion++; state.busy = false; state.loading = false
    stop(); pendingQuery = ''; pendingImages = []; state.entry = null; state.requestId = ''; state.submitUnknown = false
    state.result = null; state.requests = []; state.runId = ''; state.available = false; state.consentOption = null; state.status = ''; state.error = message;state.invalidated=true
    clearStream()
    if (storageKey) storage.setStorageSync(storageKey, null)
    emit()
  }
  function hide() {
    epoch++; readVersion++; stop(); pendingQuery = ''; pendingImages = []; storageKey = ''; cursors = {}; cancelRequested = false
    state = { memberId: '', taskType: '', title: '', loading: false, busy: false, available: false,
      consentOption: null, entry: null, requestId: '', runId: '', requests: [], submitUnknown: false, status: '', result: null, error: '', notice: '', ...streamState() }
    emit()
  }
  function save() {
    storage.setStorageSync(storageKey, { memberId: state.memberId, taskType: state.taskType,
      entry: state.entry, requestId: state.requestId, requests: state.requests, cursors, submitUnknown: state.submitUnknown,
      // 仅结果未知时保留原提交；回读确认后立即清除，不缓存模型正文。
      pendingQuery: state.submitUnknown ? pendingQuery : '', pendingImages: state.submitUnknown ? pendingImages : [] })
  }
  function handle(error, ticket) {
    if (Number(error?.code) === 401 && ticket.epoch === epoch && !session()?.token) {
      forgetPrivate('登录已过期，请重新登录后核对任务。'); return
    }
    if (!current(ticket)) return
    state.result = null
    if (privateFailure(error) || error?.code === 'TASK_MISMATCH' || error?.code === 'SESSION_CHANGED') {
      if ([409, 410].includes(Number(error?.code))) invalidateThread()
      else forgetPrivate('当前任务或成员已不可读取，请返回核对身份、授权和资料来源。')
    } else { state.error = error?.message || '服务暂不可用，请手动重试'; emit() }
  }
  async function open(memberId, taskType, selection = null) {
    hide()
    indicatorSelection = selection
    if (!uuidPattern.test(memberId || '') || !Object.prototype.hasOwnProperty.call(HEALTH_TEXT_TASKS, taskType)) {
      state.error = '健康任务参数无效，请返回重新选择'; emit(); return
    }
    state.memberId = memberId; state.taskType = taskType; state.title = HEALTH_TEXT_TASKS[taskType]
    if (taskType === 'diet_analysis' && (!uuidPattern.test(selection?.record_id || '') || !Number.isInteger(selection?.source_version) || selection.source_version < 1)) {
      state.error = '请从已保存餐次进入反馈。'; emit(); return
    }
    storageKey = `health-task:${memberId}:${taskType}${selection ? ':' + JSON.stringify(selection) : ''}${daily ? ':' + day() : ''}`
    if (!session()?.token) { state.error = '请先登录后再读取健康任务'; emit(); return }
    const ticket = token(); state.loading = true; emit()
    try {
      const [members, readiness] = await Promise.all([
        send({ path: '/api/health/v1/members' }),
        send({ path: `/api/health/v1/members/${memberId}/readiness` }),
      ])
      if (!current(ticket)) return
      if (taskType === 'diet_analysis') {
        const source = await readDietRecord(memberId,selection.record_id,send)
        if (!current(ticket)) return
        if (source.id !== selection.record_id || source.source_version !== selection.source_version) throw mismatch()
      }
      const indicatorTask = taskType.startsWith('blood_')
      if (!Array.isArray(members.data) || !members.data.some(row => row.id === memberId && (!indicatorTask || row.is_owner === true)) ||
        readiness.data?.capabilities?.member_id !== memberId || !Array.isArray(readiness.data?.entries)) throw mismatch()
      const entry = readiness.data.entries.find(row => row.entry_type === taskType)
      state.available = entry?.status === 'available' || (['initial_meal_preview','reference_meal_preview'].includes(taskType) && selection && entry?.status === 'needs_input' && entry?.reason_code === 'selection_required')
      if (!state.available) state.notice = ({budget_price_unavailable:'营养咨询计费配置尚未就绪，请联系管理员。',budget_exceeded:'本月健康 AI 可用额度不足或待核账，请稍后再试。',consent_required:'此项服务已停用，请在隐私设置中管理。',missing_scopes:'该成员尚未授权此项健康服务，请核查成员授权。',configuration_unavailable:'此项服务尚未配置，资料仍可查看和修改。',dependency_not_ready:'此项服务所需的运行服务或专业资料尚未就绪。',agent_unavailable:'营养助手尚未就绪，请稍后再试。',skill_unavailable:'营养助手资料尚未就绪。'})[entry?.configuration_reason_code||entry?.reason_code] || '请打开该成员的家庭档案核对资料与授权。'
      if (entry?.reason_code === 'consent_required' && taskType !== 'consultation') {
        const policy = (await send({ path: '/api/health/v1/configuration' })).data
        if (!current(ticket)) return
        const purpose = taskType === 'diet_analysis' ? 'diet_analysis' : ['meal_preview','initial_meal_preview','reference_meal_preview'].includes(taskType) ? 'meal_plan' : 'consultation'
        const configured = policy?.[purpose]
        if (configured?.available === true && typeof configured.processor === 'string' &&
          configured.processor && typeof policy.policy_version === 'string' && policy.policy_version) {
          state.consentOption = { processor: configured.processor, policyVersion: policy.policy_version, ...(purpose !== 'consultation' ? {purpose} : {}) }
          state.notice = '请先核对当前咨询处理方和政策版本，再明确选择是否同意。'
        }
      }
      const saved = storage.getStorageSync(storageKey)
      if (saved?.memberId === memberId && saved?.taskType === taskType && saved.entry?.thread_id && saved.entry?.agent_slug) {
        state.entry = saved.entry; state.requestId = saved.requestId || ''
        state.requests = Array.isArray(saved.requests) ? saved.requests.filter(row => uuidPattern.test(row.request_id)).slice(-50) : []
        state.submitUnknown = saved.submitUnknown === true
        cursors = saved.cursors && typeof saved.cursors === 'object' ? Object.fromEntries(Object.entries(saved.cursors).filter(([id, value]) => uuidPattern.test(id) && /^\d+-\d+$/.test(value))) : {}
        pendingQuery = state.submitUnknown && typeof saved.pendingQuery === 'string' && saved.pendingQuery.length <= 4000 ? saved.pendingQuery : ''
        pendingImages = state.submitUnknown && Array.isArray(saved.pendingImages) ? saved.pendingImages.filter(validImage).slice(0, 1) : []
        if (state.requestId) await refresh(ticket)
      } else if (saved?.entry?.client_request_id && saved.entry?.pending === true) {
        state.entry = saved.entry
        state.notice = '上次创建线程的结果未确认，可用原请求键重试。'
      }
      if (daily && taskType === 'consultation' && state.available && !state.entry?.thread_id && !state.entry?.pending) {
        const { data } = await send({ path: `/api/health/v1/members/${memberId}/daily-conversations` })
        if (!current(ticket)) return
        const today = data.days?.find(row => row.date === day())
        if (today && uuidPattern.test(today.thread_id) && !(storage.getStorageSync(invalidKey()) || []).includes(today.thread_id)) {
          state.entry = { thread_id: today.thread_id, agent_slug: 'health-consultation', business_date: day() }
          save()
        }
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
        data: { purpose: consentOption.purpose || 'consultation', accepted: true, processor: consentOption.processor,
          policy_version: consentOption.policyVersion } })
      if (!current(ticket)) return
      if (data?.accepted !== true) throw mismatch()
      await open(memberId, taskType, indicatorSelection)
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
      const useDaily = daily && type === 'consultation' && !(storage.getStorageSync(invalidKey()) || []).length
      const response = useDaily
        ? await send({ path: `/api/health/v1/members/${id}/daily-consultations`, method: 'POST' })
        : type === 'diet_analysis'
        ? await send({ path: `/api/health/v1/diet-logs/${indicatorSelection.record_id}/feedback-conversation`, method: 'POST',
          data: { client_request_id: clientId, source_version: indicatorSelection.source_version } })
        : await send({ path: `/api/health/v1/members/${id}/task-entries`, method: 'POST',
          headers: { 'Idempotency-Key': clientId }, data: { task_type: type, client_request_id: clientId, ...(indicatorSelection ? { selection: indicatorSelection } : {}) } })
      if (!current(ticket)) return
      let row = response.data
      if (useDaily) {
        if (row.member_id !== id || row.agent_slug !== 'health-consultation' || row.business_date !== day()) throw mismatch()
        row = { ...row, task_type: type, client_request_id: clientId, entry_status: 'ready', request_submit_url: '/api/agent/runs' }
      }
      if (type === 'diet_analysis') {
        if (row.member_id !== id || row.agent_slug !== 'health-diet-analyst' ||
          row.feedback_selection?.record_id !== indicatorSelection.record_id || row.feedback_selection?.source_version !== indicatorSelection.source_version) throw mismatch()
        row = { ...row, task_type: type, client_request_id: clientId, entry_status: 'ready', request_submit_url: '/api/agent/runs' }
      }
      if (row?.member_id !== id || row?.task_type !== type || row?.client_request_id !== clientId) throw mismatch()
      if (row.entry_status !== 'ready') {
        state.entry = null; state.available = false; state.notice = row.entry_status === 'needs_input'
          ? '请先完成服务端要求的选择，再重新进入。' : '服务端依赖尚未就绪，请稍后重新读取。'
      } else {
        if (!uuidPattern.test(row.thread_id) || !row.agent_slug || row.request_submit_url !== '/api/agent/runs') throw mismatch()
        state.entry = { client_request_id: clientId, thread_id: row.thread_id, agent_slug: row.agent_slug }
        state.notice = ''
      }
      save(); emit()
    } catch (error) {
      if (current(ticket)) {
        if (!uncertainFailure(error)) { state.entry = null; save() }
        handle(error, ticket)
      }
    } finally { if (current(ticket)) { state.busy = false; emit() } }
  }
  function validImage(value) { return typeof value === 'string' && value.length <= 3 * 1024 * 1024 && /^data:image\/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$/.test(value) }
  async function submit(query, retry = false, images = []) {
    if (!state.available || !state.entry?.thread_id || state.busy || state.loading) return
    if (state.submitUnknown && !retry) return
    const text = retry ? pendingQuery : String(query || '').trim()
    const selectedImages = retry ? pendingImages : images
    if ((!text && !selectedImages.length) || text.length > 4000 || selectedImages.length > 1 || !selectedImages.every(validImage) || (retry && !state.submitUnknown)) return
    const ticket = token()
    if (!retry) {
      stop(); readVersion++; state.requestId = newId(); state.runId = ''; pendingQuery = text; pendingImages = [...selectedImages]
      clearStream(); phase('queued')
      state.requests = [...state.requests, { request_id: state.requestId, status: '提交中' }].slice(-50)
      state.submitUnknown = true; state.status = '提交中'; state.result = null; save()
    }
    state.busy = true; state.error = ''; emit()
    try {
      const response = await send({ path: '/api/agent/runs', method: 'POST',
        data: { agent_slug: state.entry.agent_slug, thread_id: state.entry.thread_id,
          query: text, meta: { request_id: state.requestId }, ...(selectedImages.length ? { image_content: selectedImages } : {}) } })
      if (!current(ticket)) return
      if (response.data?.request_id !== state.requestId || response.data?.thread_id !== state.entry.thread_id) throw mismatch()
      state.submitUnknown = false; pendingQuery = ''; pendingImages = []; save()
      await refresh(ticket)
      return true
    } catch (error) {
      if (current(ticket)) {
        if (!uncertainFailure(error)) { state.requestId = ''; state.submitUnknown = false; pendingQuery = ''; pendingImages = []; save() }
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
      state.submitUnknown = false; pendingQuery = ''; pendingImages = []; state.status = data.execution_status === 'not_dispatched'
        ? data.request_status : data.execution_status
      state.runId = data.run_id || ''
      if (!state.streamText && !cancelRequested && !['validating', 'reconnecting', 'finalizing'].includes(state.streamPhase))
        phase(state.status === 'queued' || state.status === 'pending' ? 'queued' : 'running')
      const known = state.requests.some(row => row.request_id === expectedId)
      state.requests = known ? state.requests.map(row => row.request_id === expectedId ? { ...row, status: state.status } : row) : [...state.requests, { request_id: expectedId, status: state.status }]
      if (data.result?.result_type === 'error') state.result = { type: 'error', code: data.result.code, retryable: data.result.retryable === true }
      else if (data.execution_status === 'completed') {
        if (data.result?.result_type === 'general_education_answer' && data.result.scope === 'general_education' &&
          typeof data.result.answer === 'string' && Array.isArray(data.result.citations)) {
          state.result = { type: 'answer', text: data.result.answer,
            purchaseOffers: Array.isArray(data.result.purchase_offers) ? data.result.purchase_offers : [],
            citations: data.result.citations.map(item => item.title).filter(Boolean) }
        } else if (data.result?.result_type === 'meal_feedback' && data.result.data) {
          const receipt = data.result.data
          if (receipt.status !== 'saved' || receipt.feedback?.status !== 'active' ||
            receipt.feedback?.diet_log_id !== indicatorSelection?.record_id ||
            receipt.records?.length !== 1 || receipt.records[0].record_id !== indicatorSelection?.record_id ||
            receipt.records[0].source_version !== indicatorSelection?.source_version ||
            typeof receipt.feedback.details?.comment !== 'string') throw mismatch()
          state.result = { type: 'answer', text: `这餐反馈已保存（v${receipt.feedback.version}）：${receipt.feedback.details.comment}`, citations: [] }
        } else if (data.result?.result_type === 'needs_input' && Array.isArray(data.result.questions)) {
          state.result = { type: 'needs_input', questions: data.result.questions }
        } else if (['meal_plan_preview', 'diet_analysis', 'quality_check', 'ingredient_requirements'].includes(data.result?.result_type) && data.result.validation === 'current_business_sources' && data.result.data) {
          state.result = { type: 'business', kind: data.result.result_type, data: data.result.data }
        } else throw mismatch()
      }
      const terminal = terminalStatuses.has(data.execution_status) || ['cancelled', 'rejected', 'failed'].includes(data.request_status)
      if (terminal) {
        // 增量只用于当前生成预览；完成内容与失败状态始终由业务结果决定。
        clearStream(); state.streamPhase = state.status
      }
      save(); emit()
      if (!terminal) {
        startPolling(givenTicket); startStreams(givenTicket)
      }
      else stop()
    } catch (error) {
      if (!current(givenTicket) || read !== readVersion) return
      if (state.submitUnknown && Number(error?.code) === 404) {
        state.error = pendingQuery
          ? '提交结果尚未确认；可重新读取，或在本页用同一请求键重试。'
          : '提交结果尚未确认；请重新读取同一请求，暂勿重复提问。'
        emit()
      } else {
        handle(error, givenTicket)
        if (current(givenTicket) && uncertainFailure(error) && !state.submitUnknown && !terminalStatuses.has(state.status)) {
          phase('reconnecting'); emit(); startPolling(givenTicket)
        }
      }
    }
  }
  function startPolling(ticket) {
    if (timer !== null || !current(ticket)) return
    if (polls >= pollLimit) {
      stopStreams(); state.notice = '等待已暂停，服务端可能仍在执行。请手动读取同一任务。'
      state.streamPhase = 'paused'; state.streamStatus = state.notice; emit(); return
    }
    timer = schedule(() => { timer = null; polls++; void refresh(ticket) }, pollInterval)
  }
  function startStreams(ticket) {
    const id = state.requestId, runId = state.runId, key = `${id}:${runId}`
    if (streamKey === key || streamAttempts >= 5 || cancelRequested) return
    stopStreams(); streamKey = key; streamAttempts++
    const generation = streamEpoch
    const active = () => current(ticket) && generation === streamEpoch && id === state.requestId && runId === state.runId
    const options = { requestId: id, onEvent(event) {
      if (!active() || (event.requestId && event.requestId !== id) || (event.runId && runId && event.runId !== runId) ||
        (event.threadId && event.threadId !== state.entry?.thread_id)) return
      if (event.id && runId) {
        if (!newerCursor(event.id, cursors[runId])) return
        cursors[runId] = event.id; save()
      }
      if (Number.isInteger(event.queuePosition)) { state.queuePosition = event.queuePosition; phase('queued'); emit() }
      if (['running', 'validating'].includes(event.phase)) { phase(event.phase); emit() }
      if (event.phase === 'streaming' && typeof event.content === 'string' && event.content &&
        event.requestId === id && event.runId === runId && event.threadId === state.entry?.thread_id && event.id &&
        Number.isInteger(event.offset) && event.offset >= 0 && typeof event.messageId === 'string' && event.messageId) {
        if (event.messageId !== state.streamMessageId && event.offset === 0) {
          state.streamMessageId = event.messageId; state.streamText = ''; state.streamOffset = 0
        }
        if (event.messageId !== state.streamMessageId || event.offset > state.streamOffset) {
          // 游标仍在而页面未保留正文，或分帧缺失：从头重放公开增量，避免展示残缺拼接。
          cursors[runId] = '0-0'; state.streamText = ''; state.streamMessageId = ''; state.streamOffset = 0; save()
          stopStreams(); phase('reconnecting'); emit(); return
        }
        if (event.offset < state.streamOffset) return
        if (state.streamText.length + event.content.length <= 200000) {
          state.streamText += event.content
          // 服务端 Python len 按 Unicode 码点计数，emoji 不能按 JS UTF-16 长度计算。
          state.streamOffset += Array.from(event.content).length
          streamAttempts = 0; polls = 0; phase('streaming'); emit()
        }
      }
      if (event.type === 'end') { phase('finalizing'); emit() }
      if (['cancelled', 'failed', 'rejected', 'error'].includes(event.type)) {
        state.streamText = ''; state.streamMessageId = ''; state.streamOffset = 0
        if (runId) cursors[runId] = '0-0'
        stopStreams(); phase('finalizing'); save(); emit()
      }
      if (['run_created', 'end', 'cancelled', 'failed', 'rejected', 'error'].includes(event.type)) void refresh(ticket)
    }, onEnd() {
      if (!active()) return
      stopStreams()
      if (!['finalizing', 'cancelling'].includes(state.streamPhase)) { phase('reconnecting'); emit() }
    }, onError(error) {
      if (!active()) return
      if ([401, 403, 404, 409, 410].includes(Number(error?.code))) { readVersion++; forgetPrivate('当前授权或来源已变化，请返回重新核对。') }
      else { stopStreams(); phase('reconnecting'); emit() }
    } }
    streams.push(subscribe({ ...options, runId: runId || undefined, cursor: cursors[runId] || '0-0' }))
  }
  async function selectRequest(id) {
    if (state.busy || state.loading || state.submitUnknown || !state.requests.some(row => row.request_id === id)) return
    stop(); readVersion++; clearStream(); state.requestId = id; state.runId = ''; state.result = null; state.status = ''; save()
    await refresh()
  }
  async function restoreRequest(id) {
    if(!uuidPattern.test(id||'')||!state.entry?.thread_id||state.requestId||state.busy||state.loading)return
    state.requestId=id;save();await refresh()
  }
  async function cancelRequest() {
    if (state.busy || !state.requestId || state.submitUnknown || terminalStatuses.has(state.status)) return
    const ticket = token(), id = state.requestId, runId = state.runId
    cancelRequested = true; stopStreams(); state.streamText = ''; state.streamMessageId = ''; state.streamOffset = 0; phase('cancelling')
    state.busy = true; state.error = ''; emit()
    try {
      await send({ path: runId ? `/api/agent/runs/${encodeURIComponent(runId)}/cancel` : `/api/agent/requests/${encodeURIComponent(id)}/cancel`, method: 'POST' })
      if (!current(ticket)) return
      await refresh(ticket)
    } catch (error) { handle(error, ticket) }
    finally { if (current(ticket)) { state.busy = false; emit() } }
  }
  return { open, hide, acceptConsent, createEntry, submit, refresh, selectRequest, restoreRequest, cancelRequest, invalidateThread,
    getState: () => ({ ...state, canRetry: (!!pendingQuery || pendingImages.length > 0) && state.submitUnknown }) }
}
