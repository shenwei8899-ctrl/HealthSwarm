import test from 'node:test'
import assert from 'node:assert/strict'
import { createHealthTaskFlow } from '../src/services/health-task-flow.js'

const uuid = value => `${String(value).padStart(8, '0')}-1111-4111-8111-111111111111`
const memberId = uuid(1), firstConversation = uuid(2), secondConversation = uuid(3), firstThread = uuid(10), secondThread = uuid(11)
const key = (id, type = 'consultation', selection = null) =>
  `health-conversation:${id}:${memberId}:${type}${selection ? ':' + JSON.stringify(selection) : ''}`
const deferred = () => {
  let resolve, reject
  const promise = new Promise((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}
const consultation = (threadId = firstThread, fields = {}) => ({
  member_id: memberId, thread_id: threadId, agent_slug: 'health-consultation', business_date: null,
  feedback_selection: null, ...fields,
})

function fixture(override = () => undefined, flowOptions = {}) {
  let identity = { accountId: 'account-a', householdId: 'family-a', token: 'synthetic' }, nextId = 100
  const calls = [], saved = new Map(), created = [], states = []
  const scope = item => `${identity.accountId}:${identity.householdId}:${item}`
  const storage = {
    getStorageSync: item => structuredClone(saved.get(scope(item))),
    setStorageSync: (item, value) => saved.set(scope(item), structuredClone(value)),
  }
  const send = async options => {
    calls.push(structuredClone(options))
    const custom = override(options)
    if (custom !== undefined) return await custom
    if (options.path === '/api/health/v1/members') return { data: [{ id: memberId, is_owner: true }] }
    if (options.path.endsWith('/readiness')) return { data: { capabilities: { member_id: memberId }, entries:
      ['consultation', 'reference_meal_preview'].map(entry_type => ({ entry_type, status: 'available' })) } }
    if (options.path.endsWith('/daily-conversations')) return { data: { days: [{ date: '2026-10-28', thread_id: uuid(99) }] } }
    if (options.path.includes('/consultations?')) return { data: { items: created, has_more: false, next_offset: null } }
    if (options.path.endsWith('/consultations') && options.method === 'POST') {
      const row = consultation(uuid(10 + created.length))
      created.push(row)
      return { data: row }
    }
    if (options.path.includes('/requests?agent_slug=')) return { data: { requests: [], queue: { status: 'idle' } } }
    if (options.path.endsWith('/task-entries')) return { data: { ...options.data, member_id: memberId,
      entry_status: 'ready', thread_id: uuid(30 + created.length), agent_slug: 'health-meal-planner', request_submit_url: '/api/agent/runs' } }
    if (options.path.endsWith('/daily-consultations')) return { data: consultation(uuid(99), { business_date: '2026-10-28' }) }
    if (options.path === '/api/agent/runs') return { data: { request_id: options.data.meta.request_id, thread_id: options.data.thread_id } }
    if (options.path.includes('/tasks/')) return { data: { request_id: options.path.split('/').at(-1), member_id: memberId,
      task_type: 'consultation', thread_id: firstThread, agent_slug: 'health-consultation', request_status: 'queued', execution_status: 'not_dispatched' } }
    throw new Error(`Unexpected request ${options.path}`)
  }
  const flow = createHealthTaskFlow({ send, storage, session: () => identity, revision: () => 'unchanged-revision',
    daily: true, day: () => '2026-10-28', newId: () => uuid(nextId++), onChange: state => states.push(structuredClone(state)),
    subscribe: () => () => {}, schedule: () => 1, cancel: () => {}, ...flowOptions })
  return { flow, calls, storage, saved, created, states, setIdentity: value => { identity = { ...identity, ...value } } }
}

test('两个显式新咨询发送不同的真实创建请求，独立保存且不恢复 daily 线程', async () => {
  const h = fixture()
  await h.flow.open(memberId, 'consultation', null, { conversationId: firstConversation })
  assert.equal(h.flow.getState().entry, null)
  await h.flow.createEntry()
  assert.equal(h.flow.getState().entry.thread_id, firstThread)
  await h.flow.open(memberId, 'consultation', null, { conversationId: secondConversation })
  assert.equal(h.flow.getState().entry, null)
  await h.flow.createEntry()
  assert.equal(h.flow.getState().entry.thread_id, secondThread)
  const writes = h.calls.filter(call => call.method === 'POST')
  assert.equal(writes.length, 2)
  assert.ok(writes.every(call => call.path === `/api/health/v1/members/${memberId}/consultations`))
  assert.ok(writes.every(call => call.headers['Idempotency-Key'] === call.data.client_request_id))
  assert.notEqual(writes[0].data.client_request_id, writes[1].data.client_request_id)
  assert.equal(h.storage.getStorageSync(key(firstConversation)).entry.thread_id, firstThread)
  assert.equal(h.storage.getStorageSync(key(secondConversation)).entry.thread_id, secondThread)
  assert.equal(h.calls.some(call => call.path.includes('/daily-')), false)
  await h.flow.open(memberId, 'consultation', null, { conversationId: firstConversation })
  assert.equal(h.flow.getState().entry.thread_id, firstThread)
  assert.ok(h.calls.some(call => call.path.includes('/consultations?')))
})

test('指定旧线程逐页核对服务端归属，忽略本地其他线程和旧请求指针', async () => {
  const offsets = []
  const h = fixture(options => {
    if (options.path.includes('/consultations?')) {
      const offset = Number(new URL(options.path, 'https://fixture.invalid').searchParams.get('offset'))
      offsets.push(offset)
      return { data: { items: [consultation(offset === 40 ? firstThread : uuid(50 + offset))],
        has_more: offset < 40, next_offset: offset < 40 ? offset + 20 : null } }
    }
  })
  h.storage.setStorageSync(key(firstConversation), { memberId, taskType: 'consultation',
    entry: consultation(secondThread), requestId: uuid(200), requests: [{ request_id: uuid(200), status: 'completed' }] })
  await h.flow.open(memberId, 'consultation', null, { conversationId: firstConversation, threadId: firstThread })
  assert.deepEqual(offsets, [0, 20, 40])
  assert.equal(h.flow.getState().entry.thread_id, firstThread)
  assert.equal(h.flow.getState().requestId, '')
  assert.deepEqual(h.flow.getState().requests, [])
  assert.equal(h.calls.some(call => call.method === 'POST' || call.path.includes('/tasks/')), false)
})

test('指定或本地恢复线程均拒绝错误成员、错误角色和服务端不存在的指针', async () => {
  for (const fields of [{ member_id: uuid(999) }, { agent_slug: 'health-diet-analyst' }, { thread_id: secondThread }]) {
    for (const explicitThread of [true, false]) {
      const h = fixture(options => options.path.includes('/consultations?')
        ? { data: { items: [consultation(firstThread, fields)], has_more: false, next_offset: null } } : undefined)
      h.storage.setStorageSync(key(firstConversation), { memberId, taskType: 'consultation', entry: consultation(firstThread) })
      await h.flow.open(memberId, 'consultation', null, { conversationId: firstConversation, ...(explicitThread ? { threadId: firstThread } : {}) })
      assert.equal(h.flow.getState().entry, null)
      assert.equal(h.flow.getState().available, false)
      await h.flow.createEntry()
      assert.equal(h.calls.some(call => call.method === 'POST'), false)
    }
  }
})

test('咨询分页游标必须前进，失败不能回落 daily 或创建替代线程', async () => {
  for (const next_offset of [0, -1, '20', 1.5, null]) {
    const h = fixture(options => options.path.includes('/consultations?')
      ? { data: { items: [consultation(secondThread)], has_more: true, next_offset } } : undefined)
    await h.flow.open(memberId, 'consultation', null, { conversationId: firstConversation, threadId: firstThread })
    assert.equal(h.flow.getState().entry, null)
    assert.equal(h.calls.filter(call => call.path.includes('/consultations?')).length, 1)
    assert.equal(h.calls.some(call => call.method === 'POST' || call.path.includes('/daily-')), false)
  }
})

test('新咨询回执必须为当前成员的普通咨询，拒绝其他任务、daily、反馈或非法线程', async () => {
  for (const fields of [{ member_id: uuid(999) }, { agent_slug: 'health-diet-analyst' },
    { business_date: '2026-10-28' }, { feedback_selection: { record_id: uuid(4), source_version: 1 } }, { thread_id: 'invalid' }]) {
    const h = fixture(options => options.path.endsWith('/consultations') && options.method === 'POST'
      ? { data: consultation(firstThread, fields) } : undefined)
    await h.flow.open(memberId, 'consultation', null, { conversationId: firstConversation })
    await h.flow.createEntry()
    assert.equal(h.flow.getState().entry, null)
    assert.equal(h.flow.getState().available, false)
  }
})

test('未知创建结果跨 hide/open 保留同一幂等键重试，其他对话有独立键', async () => {
  let attempts = 0
  const h = fixture(options => {
    if (options.path.endsWith('/consultations') && options.method === 'POST' && ++attempts === 1)
      throw Object.assign(new Error('synthetic timeout'), { code: 'NETWORK_ERROR' })
  })
  await h.flow.open(memberId, 'consultation', null, { conversationId: firstConversation })
  await h.flow.createEntry()
  assert.equal(h.flow.getState().entry.pending, true)
  await h.flow.open(memberId, 'consultation', null, { conversationId: secondConversation })
  await h.flow.createEntry()
  await h.flow.open(memberId, 'consultation', null, { conversationId: firstConversation })
  await h.flow.createEntry()
  const writes = h.calls.filter(call => call.method === 'POST')
  assert.deepEqual(writes[0], writes[2])
  assert.notEqual(writes[0].data.client_request_id, writes[1].data.client_request_id)
})

test('独立咨询提交结果未知时切换再恢复保留原请求，不能用另一个问题覆盖', async () => {
  let submitted = false, requestId = ''
  const h = fixture(options => {
    if (options.path === '/api/agent/runs') {
      requestId = options.data.meta.request_id
      if (!submitted) { submitted = true; throw Object.assign(new Error('synthetic timeout'), { code: 'NETWORK_ERROR' }) }
      return { data: { request_id: requestId, thread_id: firstThread } }
    }
    if (options.path.includes('/tasks/') && h.calls.filter(call => call.path === '/api/agent/runs').length === 1)
      throw Object.assign(new Error('not yet received'), { code: 404 })
  })
  await h.flow.open(memberId, 'consultation', null, { conversationId: firstConversation })
  await h.flow.createEntry()
  await h.flow.submit('原问题')
  await h.flow.open(memberId, 'consultation', null, { conversationId: secondConversation })
  await h.flow.open(memberId, 'consultation', null, { conversationId: firstConversation })
  assert.equal(h.flow.getState().canRetry, true)
  await h.flow.submit('不能覆盖的问题')
  assert.equal(h.calls.filter(call => call.path === '/api/agent/runs').length, 1)
  await h.flow.submit('', true)
  const runs = h.calls.filter(call => call.path === '/api/agent/runs')
  assert.deepEqual(runs[0], runs[1])
  assert.equal(runs[1].data.meta.request_id, requestId)
})

test('同账号切换家庭后迟到创建结果不保存到新家庭', async () => {
  const response = deferred()
  const h = fixture(options => options.path.endsWith('/consultations') && options.method === 'POST' ? response.promise : undefined)
  await h.flow.open(memberId, 'consultation', null, { conversationId: firstConversation })
  const pending = h.flow.createEntry()
  const before = h.states.length
  h.setIdentity({ householdId: 'family-b' })
  response.resolve({ data: consultation(firstThread) })
  await pending
  assert.equal(h.states.length, before)
  assert.equal(h.storage.getStorageSync(key(firstConversation)), undefined)
  assert.equal(h.flow.getState().entry.thread_id, undefined)
})

test('切换会话后迟到的列表结果不能覆盖当前新咨询或写入其命名空间', async () => {
  const response = deferred()
  const h = fixture(options => options.path.includes('/consultations?') ? response.promise : undefined)
  const opening = h.flow.open(memberId, 'consultation', null, { conversationId: firstConversation, threadId: firstThread })
  await new Promise(resolve => setImmediate(resolve))
  await h.flow.open(memberId, 'consultation', null, { conversationId: secondConversation })
  response.resolve({ data: { items: [consultation()], has_more: false, next_offset: null } })
  await opening
  assert.equal(h.flow.getState().entry, null)
  assert.equal(h.storage.getStorageSync(key(secondConversation)), undefined)
  assert.equal(h.calls.some(call => call.path.includes('/requests?')), false)
})

test('同一 conversationId 的参考任务按类型和 selection 隔离，授权重开保留 options', async () => {
  let accepted = false
  const h = fixture(options => {
    if (options.path.endsWith('/readiness')) return { data: { capabilities: { member_id: memberId }, entries: [
      { entry_type: 'reference_meal_preview', status: accepted ? 'available' : 'needs_input', reason_code: accepted ? null : 'consent_required' },
      { entry_type: 'consultation', status: 'available' },
    ] } }
    if (options.path.endsWith('/configuration')) return { data: { policy_version: 'synthetic-v1', meal_plan: { available: true, processor: 'synthetic' } } }
    if (options.path.endsWith('/processing-consents')) { accepted = true; return { data: { accepted: true } } }
  })
  const first = { date: '2026-10-28', plan_kind: 'reference' }, second = { date: '2026-10-29', plan_kind: 'reference' }
  await h.flow.open(memberId, 'reference_meal_preview', first, { conversationId: firstConversation })
  await h.flow.acceptConsent(true)
  await h.flow.createEntry()
  assert.ok(h.storage.getStorageSync(key(firstConversation, 'reference_meal_preview', first)).entry.thread_id)
  await h.flow.open(memberId, 'reference_meal_preview', second, { conversationId: firstConversation })
  assert.equal(h.flow.getState().entry, null)
  await h.flow.createEntry()
  assert.ok(h.storage.getStorageSync(key(firstConversation, 'reference_meal_preview', second)).entry.thread_id)
  await h.flow.open(memberId, 'consultation', null, { conversationId: firstConversation })
  assert.equal(h.flow.getState().entry, null)
  assert.equal(h.calls.some(call => call.path.includes('/daily-')), false)
})

test('旧三参 open 仍恢复当日 daily 并使用原存储 key', async () => {
  const h = fixture()
  await h.flow.open(memberId, 'consultation')
  assert.equal(h.flow.getState().entry.thread_id, uuid(99))
  assert.ok(h.storage.getStorageSync(`health-task:${memberId}:consultation:2026-10-28`))
  assert.equal(h.calls.some(call => call.path.includes('/consultations?')), false)
})

test('旧 daily 显式选定同一线程时迁移未知提交及游标，重试沿用原问题和请求键', async () => {
  const requestId = uuid(500)
  let submitted = false
  const h = fixture(options => {
    if (options.path.includes('/consultations?')) return { data: { items: [consultation(firstThread, { business_date: '2026-10-28' })], has_more: false, next_offset: null } }
    if (options.path.includes('/tasks/') && !submitted) throw Object.assign(new Error('not received yet'), { code: 404 })
    if (options.path === '/api/agent/runs') { submitted = true; return { data: { request_id: requestId, thread_id: firstThread } } }
  })
  const legacy = { memberId, taskType: 'consultation', entry: { thread_id: firstThread, agent_slug: 'health-consultation' },
    requestId, requests: [{ request_id: requestId, status: '提交中' }], cursors: { [uuid(700)]: '8-1' },
    submitUnknown: true, pendingQuery: '原先未确认的提问', pendingImages: [] }
  h.storage.setStorageSync(`health-task:${memberId}:consultation:2026-10-28`, legacy)
  await h.flow.open(memberId, 'consultation', null, { conversationId: firstThread, threadId: firstThread })
  assert.equal(h.flow.getState().canRetry, true)
  assert.equal(h.flow.getState().requestId, requestId)
  const migrated = h.storage.getStorageSync(key(firstThread))
  assert.equal(migrated.pendingQuery, legacy.pendingQuery)
  assert.deepEqual(migrated.cursors, legacy.cursors)
  assert.deepEqual(migrated.requests, legacy.requests)
  await h.flow.submit('', true)
  const write = h.calls.find(call => call.path === '/api/agent/runs')
  assert.equal(write.data.meta.request_id, requestId)
  assert.equal(write.data.query, legacy.pendingQuery)
  assert.equal(write.data.thread_id, firstThread)
})

test('旧缓存成员、类型、selection 或 thread 不一致时不能迁移到选定对话', async () => {
  for (const change of [{ memberId: uuid(999) }, { taskType: 'reference_meal_preview' },
    { entry: { thread_id: secondThread, agent_slug: 'health-consultation' } }]) {
    const h = fixture(options => options.path.includes('/consultations?')
      ? { data: { items: [consultation()], has_more: false, next_offset: null } } : undefined)
    h.storage.setStorageSync(`health-task:${memberId}:consultation:2026-10-28`, { memberId, taskType: 'consultation',
      entry: { thread_id: firstThread, agent_slug: 'health-consultation' }, requestId: uuid(500),
      submitUnknown: true, pendingQuery: '其他线程原文', ...change })
    await h.flow.open(memberId, 'consultation', null, { conversationId: firstConversation, threadId: firstThread })
    assert.equal(h.flow.getState().requestId, '')
    assert.equal(h.flow.getState().canRetry, false)
    assert.equal(h.calls.some(call => call.path.includes('/tasks/')), false)
  }
  const h = fixture(options => options.path.includes('/consultations?')
    ? { data: { items: [consultation()], has_more: false, next_offset: null } } : undefined)
  h.storage.setStorageSync(`health-task:${memberId}:consultation:2026-10-28`, { memberId, taskType: 'consultation',
    entry: { thread_id: firstThread, agent_slug: 'health-consultation' }, requestId: uuid(500), submitUnknown: true, pendingQuery: '其他选择原文' })
  await h.flow.open(memberId, 'consultation', { source: 'different' }, { conversationId: firstConversation, threadId: firstThread })
  assert.equal(h.flow.getState().canRetry, false)
  assert.equal(h.flow.getState().requestId, '')
})

test('往日 daily 只读且不提交，跨日独立咨询继续使用指定 thread', async () => {
  for (const business_date of ['2026-10-27', null]) {
    const h = fixture(options => options.path.includes('/consultations?')
      ? { data: { items: [consultation(firstThread, { business_date })], has_more: false, next_offset: null } } : undefined)
    await h.flow.open(memberId, 'consultation', null, { conversationId: firstConversation, threadId: firstThread })
    assert.equal(h.flow.getState().readOnly, business_date !== null)
    await h.flow.submit('继续咨询')
    assert.equal(h.calls.filter(call => call.path === '/api/agent/runs').length, business_date ? 0 : 1)
    assert.equal(h.flow.getState().entry.thread_id, firstThread)
  }
})

test('已打开的当日 daily 跨北京时间午夜后不能继续提交', async () => {
  let today = '2026-10-28'
  const h = fixture(options => options.path.includes('/consultations?')
    ? { data: { items: [consultation(firstThread, { business_date: '2026-10-28' })], has_more: false, next_offset: null } } : undefined,
  { day: () => today })
  await h.flow.open(memberId, 'consultation', null, { conversationId: firstConversation, threadId: firstThread })
  assert.equal(h.flow.getState().readOnly, false)
  today = '2026-10-29'
  await h.flow.submit('跨日继续')
  assert.equal(h.flow.getState().readOnly, true)
  assert.equal(h.calls.some(call => call.method === 'POST'), false)
})

test('没有 Run 的 queued 请求由真实队列恢复，再读取健康任务验证成员和类型', async () => {
  const requestId = uuid(400)
  const h = fixture(options => {
    if (options.path.includes('/consultations?')) return { data: { items: [consultation()], has_more: false, next_offset: null } }
    if (options.path.includes('/requests?')) return { data: { requests: [{ request_id: requestId, thread_id: firstThread,
      agent_slug: 'health-consultation', status: 'queued', queue_position: 1, content: '私有原提问' }], queue: { status: 'running' } } }
  })
  await h.flow.open(memberId, 'consultation', null, { conversationId: firstConversation, threadId: firstThread })
  assert.equal(h.flow.getState().requestId, requestId)
  assert.equal(h.flow.getState().status, 'queued')
  assert.equal(h.flow.getState().runId, '')
  assert.equal(h.flow.getState().streamPhase, 'queued')
  assert.ok(h.calls.some(call => call.path.endsWith(`/tasks/${requestId}`)))
  assert.equal(JSON.stringify(h.storage.getStorageSync(key(firstConversation))).includes('私有原提问'), false)
})

test('history 的真实 running A 优先于仅恢复的 queued B，保留B且不取消或重发', async () => {
  const queuedId = uuid(400), activeId = uuid(401), runId = uuid(402), otherId = uuid(403), subscriptions = [], closed = []
  const h = fixture(options => {
    if (options.path.includes('/consultations?')) return { data: { items: [consultation()], has_more: false, next_offset: null } }
    if (options.path.includes('/requests?')) return { data: { requests: [{ request_id: queuedId, thread_id: firstThread,
      agent_slug: 'health-consultation', status: 'queued' }] } }
    if (options.path.endsWith(`/tasks/${activeId}`)) return { data: { request_id: activeId, member_id: memberId,
      thread_id: firstThread, agent_slug: 'health-consultation', task_type: 'consultation', request_status: 'dispatched',
      execution_status: 'running', run_id: runId } }
  }, { subscribe: options => { subscriptions.push(options); return () => closed.push(options.requestId) } })
  await h.flow.open(memberId, 'consultation', null, { conversationId: firstConversation, threadId: firstThread })
  assert.equal(h.flow.getState().requestId, queuedId)
  await h.flow.restoreRequest(activeId)
  assert.equal(h.flow.getState().requestId, queuedId, '默认调用保留既有请求')
  await h.flow.restoreRequest(activeId, { preferActive: true })
  const state = h.flow.getState()
  assert.equal(state.requestId, activeId)
  assert.equal(state.runId, runId)
  assert.equal(state.status, 'running')
  assert.ok(state.requests.some(row => row.request_id === queuedId && row.status === 'queued'))
  assert.ok(state.requests.some(row => row.request_id === activeId && row.status === 'running'))
  assert.deepEqual(closed, [queuedId])
  assert.equal(subscriptions.at(-1).requestId, activeId)
  assert.equal(subscriptions.at(-1).runId, runId)
  const afterPromoted = h.calls.length
  await h.flow.restoreRequest(otherId, { preferActive: true })
  assert.equal(h.calls.length, afterPromoted, '已运行的请求不能被另一个history候选覆盖')
  assert.equal(h.calls.some(call => call.method === 'POST'), false)
  assert.deepEqual(h.storage.getStorageSync(key(firstConversation)).requests, state.requests)
})

test('unknown 提交不接受 active 提升，也不会重发原问题或取消原请求', async () => {
  const h = fixture(options => {
    if (options.path === '/api/agent/runs') throw Object.assign(new Error('synthetic timeout'), { code: 'NETWORK_ERROR' })
  })
  await h.flow.open(memberId, 'consultation', null, { conversationId: firstConversation })
  await h.flow.createEntry()
  await h.flow.submit('尚未确认的原问题')
  assert.equal(h.flow.getState().canRetry, true)
  const originalId = h.flow.getState().requestId, calls = h.calls.length
  await h.flow.restoreRequest(uuid(401), { preferActive: true })
  assert.equal(h.flow.getState().requestId, originalId)
  assert.equal(h.flow.getState().canRetry, true)
  assert.equal(h.calls.length, calls)
  assert.equal(h.calls.filter(call => call.path === '/api/agent/runs').length, 1)
  assert.equal(h.calls.some(call => call.path.endsWith('/cancel')), false)
})

test('active 提升仍以健康任务回读核对成员、线程、任务类型和agent', async () => {
  const activeId = uuid(401)
  for (const fields of [{ member_id: uuid(999) }, { thread_id: secondThread }, { task_type: 'diet_analysis' }, { agent_slug: 'health-diet-analyst' }]) {
    const h = fixture(options => {
      if (options.path.includes('/consultations?')) return { data: { items: [consultation()], has_more: false, next_offset: null } }
      if (options.path.includes('/requests?')) return { data: { requests: [{ request_id: uuid(400), thread_id: firstThread,
        agent_slug: 'health-consultation', status: 'queued' }] } }
      if (options.path.endsWith(`/tasks/${activeId}`)) return { data: { request_id: activeId, member_id: memberId,
        thread_id: firstThread, agent_slug: 'health-consultation', task_type: 'consultation', request_status: 'dispatched',
        execution_status: 'running', run_id: uuid(402), ...fields } }
    })
    await h.flow.open(memberId, 'consultation', null, { conversationId: firstConversation, threadId: firstThread })
    await h.flow.restoreRequest(activeId, { preferActive: true })
    assert.equal(h.flow.getState().entry, null)
    assert.equal(h.flow.getState().available, false)
    assert.equal(h.calls.some(call => call.method === 'POST'), false)
  }
})

test('队列或健康任务身份不匹配时拒绝恢复，未知队列读取不能允许重复提交', async () => {
  for (const failure of ['thread', 'agent', 'member', 'type', 'network']) {
    const h = fixture(options => {
      if (options.path.includes('/consultations?')) return { data: { items: [consultation()], has_more: false, next_offset: null } }
      if (options.path.includes('/requests?')) {
        if (failure === 'network') throw Object.assign(new Error('synthetic timeout'), { code: 'NETWORK_ERROR' })
        return { data: { requests: [{ request_id: uuid(400), thread_id: failure === 'thread' ? secondThread : firstThread,
          agent_slug: failure === 'agent' ? 'health-diet-analyst' : 'health-consultation', status: 'queued' }] } }
      }
      if (options.path.includes('/tasks/')) return { data: { request_id: uuid(400), thread_id: firstThread,
        member_id: failure === 'member' ? uuid(999) : memberId, task_type: failure === 'type' ? 'diet_analysis' : 'consultation',
        agent_slug: 'health-consultation', request_status: 'queued', execution_status: 'not_dispatched' } }
    })
    await h.flow.open(memberId, 'consultation', null, { conversationId: firstConversation, threadId: firstThread })
    assert.equal(h.flow.getState().available, false)
    await h.flow.submit('不应重新提交')
    assert.equal(h.calls.some(call => call.method === 'POST'), false)
  }
})

test('无效对话 ID、线程或任务组合在读取前拒绝，不默默恢复 daily', async () => {
  for (const [type, options] of [['consultation', { conversationId: 'invalid' }],
    ['consultation', { conversationId: [firstConversation] }],
    ['consultation', { conversationId: firstConversation, threadId: 'invalid' }],
    ['reference_meal_preview', { conversationId: firstConversation, threadId: firstThread }]]) {
    const h = fixture()
    await h.flow.open(memberId, type, null, options)
    assert.equal(h.calls.length, 0)
    assert.equal(h.flow.getState().entry, null)
  }
})
