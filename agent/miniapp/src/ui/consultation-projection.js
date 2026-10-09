export const CONSULTATION_AGENT = 'health-consultation'
export const CONSULTATION_SCOPES = ['ai_use', 'report_view', 'diet_edit']
export const RUN_STATUSES = ['pending', 'running', 'cancel_requested', 'completed', 'failed', 'cancelled', 'interrupted']

function invalid(message) { const error = new Error(message); error.code = 'protocol_mismatch'; return error }

// Message.id 是 PostgreSQL Integer；兼容JSON正整数及其十进制字符串，保持精确匹配。
function messageId(value) {
  const number = typeof value === 'number' ? value
    : typeof value === 'string' && /^[0-9]+$/.test(value) ? Number(value) : NaN
  return Number.isSafeInteger(number) && number > 0 ? String(number) : null
}

function required(value, description) {
  if (typeof value !== 'string' || !value) throw invalid(`服务未返回可核对的${description}`)
  return value
}

export function consultationMember(rows, memberId) {
  const row = (Array.isArray(rows) ? rows : []).find(item => item?.id === memberId)
  if (!row || row.is_owner !== true || row.relationship_label !== '本人'
    || !Array.isArray(row.scopes) || !['profile_view', 'profile_edit'].every(scope => row.scopes.includes(scope))) {
    throw invalid('当前账号没有此本人成员的身份与档案权限，请返回重新核对')
  }
  return { id: memberId, display_name: typeof row.display_name === 'string' ? row.display_name : '本人',
    scopes: ['profile_view', 'profile_edit', ...CONSULTATION_SCOPES].filter(scope => row.scopes.includes(scope)) }
}

export function consultationPolicy(value) {
  const policy = value?.consultation
  if (!policy || typeof policy.available !== 'boolean') throw invalid('服务未返回当前咨询政策')
  const displayed = (field, description) => policy.available ? required(field, description) : typeof field === 'string' ? field : ''
  return { available: policy.available, reason: typeof policy.reason === 'string' ? policy.reason : '',
    policy_version: displayed(value.policy_version, '政策版本'),
    processor: displayed(policy.processor, '处理方'), model: displayed(policy.model, '咨询模型') }
}

export function boundConsultation(value, memberId) {
  if (value?.member_id !== memberId || value.agent_slug !== CONSULTATION_AGENT) throw invalid('咨询线程与当前本人成员不一致，请重新核对')
  return { thread_id: required(value.thread_id, '咨询线程'), member_id: memberId, agent_slug: CONSULTATION_AGENT,
    business_date: typeof value.business_date === 'string' ? value.business_date : null,
    created_at: typeof value.created_at === 'string' ? value.created_at : '' }
}

export function consultationList(value, memberId) {
  if (!Array.isArray(value?.items) || typeof value.has_more !== 'boolean'
    || (value.has_more && (!Number.isInteger(value.next_offset) || value.next_offset < 0))) throw invalid('服务未返回有效咨询分页')
  return { items: value.items.map(row => boundConsultation(row, memberId)), has_more: value.has_more,
    next_offset: value.has_more ? value.next_offset : null }
}

export function historyProjection(value, threadId, uid) {
  if (value?.thread?.id !== threadId || value.thread.agent_id !== CONSULTATION_AGENT
    || (value.thread.uid && value.thread.uid !== uid) || !Array.isArray(value.runs) || !Array.isArray(value.history)) {
    throw invalid('咨询历史与当前账号或线程不一致，请重新核对')
  }
  const completed = value.runs.filter(run => run?.status === 'completed' && run.run_type === 'chat'
    && !run.created_by_run_id && typeof run.run_id === 'string' && typeof run.request_id === 'string').slice(-20)
    .map(run => ({ run_id: run.run_id, request_id: run.request_id }))
  const allowed = new Map(completed.map(run => [run.run_id, run.request_id]))
  // 工具、系统、审计和子运行完全不进入页面状态；正文只允许纯文本。
  const rows = value.history.filter(row => row && ['human', 'ai'].includes(row.type) && row.message_type === 'text'
    && !row.tool_calls?.length && !['queued', 'cancelled', 'rejected'].includes(row.delivery_status)
    && allowed.get(row.run_id) === row.request_id && messageId(row.id) !== null
    && typeof row.content === 'string').map(row => ({ id: messageId(row.id), type: row.type, run_id: row.run_id,
      request_id: row.request_id, text: row.type === 'human' ? row.content : '' }))
  return { completed, rows }
}

export function resultProjection(value, expected) {
  if (value?.error?.type === 'run_not_found') {
    const error = new Error('此咨询结果已不可读取，请重新核对成员授权与来源')
    error.code = 'run_not_found'; error.status = 404; throw error
  }
  if (value?.status !== 'completed' || value.error || value.agent_slug !== CONSULTATION_AGENT
    || value.agent_run_id !== expected.run_id || value.thread_id !== expected.thread_id
    || value.request_id !== expected.request_id || typeof value.output !== 'string') throw invalid('服务未返回可核对的已完成咨询结果')
  const finalId = messageId(value.final_message_id)
  if (finalId === null) throw invalid('服务未返回有效的最终回答标识')
  return { id: finalId, run_id: expected.run_id,
    request_id: expected.request_id, text: value.output }
}

export function visibleHistory(history, results) {
  const byRun = new Map(results.map(result => [result.run_id, result]))
  return history.rows.flatMap(row => {
    const result = byRun.get(row.run_id)
    if (!result || result.request_id !== row.request_id) return []
    if (row.type === 'human') return [{ ...row, role: 'user' }]
    return row.id === result.id ? [{ id: row.id, role: 'assistant', run_id: row.run_id,
      request_id: row.request_id, text: result.text }] : []
  })
}

export function requestProjection(value, expected, post = false) {
  const row = post ? value : value?.request
  if (row?.request_id !== expected.request_id || row.thread_id !== expected.thread_id
    || (!post && (row.agent_slug !== CONSULTATION_AGENT || row.uid !== expected.uid))
    || typeof row.status !== 'string') throw invalid('请求状态与当前咨询不一致，请重新核对')
  const runId = post ? row.run_id : row.dispatched_run_id
  if (runId !== null && runId !== undefined && typeof runId !== 'string') throw invalid('服务未返回有效运行标识')
  return { request_id: row.request_id, status: row.status, run_id: runId || null }
}

export function runProjection(value, expected) {
  const row = value?.run
  if (row?.id !== expected.run_id || row.agent_slug !== CONSULTATION_AGENT
    || row.conversation_thread_id !== expected.thread_id || row.request_id !== expected.request_id
    || typeof row.id !== 'string' || typeof row.request_id !== 'string' || !RUN_STATUSES.includes(row.status)
    || row.created_by_run_id || row.run_type !== 'chat') throw invalid('运行状态与当前咨询不一致，请重新核对')
  return { run_id: row.id, request_id: row.request_id, status: row.status }
}

export function activeRunProjection(value, threadId) {
  if (!value || !Object.hasOwn(value, 'run')) throw invalid('服务未返回当前线程运行状态')
  if (value.run === null) return null
  const row = value.run
  return runProjection(value, { run_id: row.id, thread_id: threadId, request_id: row.request_id })
}

export function runStatusLabel(status) {
  return { pending: '等待运行', running: '正在咨询', cancel_requested: '正在取消', completed: '咨询完成',
    failed: '运行失败', cancelled: '已取消', interrupted: '待处理', queued: '排队中', dispatched: '已调度',
    accepted: '已接收', rejected: '请求未接受' }[status] || '正在核对请求状态'
}
