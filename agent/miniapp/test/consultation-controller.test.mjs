import test from 'node:test'
import assert from 'node:assert/strict'
import { createConsultationController } from '../src/ui/consultation-controller.js'

const memberId = 'member', threadId = 'thread'
const binding = () => ({ member_id: memberId, thread_id: threadId, agent_slug: 'health-consultation', business_date: null, created_at: '2026-10-10' })
const run = (status = 'completed', id = 'run', request = 'request') => ({ id, status, request_id: request,
  conversation_thread_id: threadId, agent_slug: 'health-consultation', run_type: 'chat' })
const result = () => ({ status: 'completed', agent_run_id: 'run', thread_id: threadId, request_id: 'request',
  agent_slug: 'health-consultation', final_message_id: 22, output: '合成公开回答' })
const history = (completed = true) => ({ thread: { id: threadId, uid: 'uid', agent_id: 'health-consultation' },
  runs: completed ? [{ run_id: 'run', request_id: 'request', status: 'completed', run_type: 'chat' }] : [],
  history: completed ? [{ id: 11, type: 'human', message_type: 'text', content: '合成公开问题', run_id: 'run', request_id: 'request' },
    { id: 22, type: 'ai', message_type: 'text', content: '非权威历史', run_id: 'run', request_id: 'request' }] : [] })
const failure = (status, message = '合成错误', code = 'test_error') => Object.assign(new Error(message), { status, code })
const deferred = () => { let resolve, reject; const promise = new Promise((done, fail) => { resolve = done; reject = fail }); return { promise, resolve, reject } }
const drain = () => new Promise(resolve => setImmediate(resolve))

function setup(overrides = {}, options = {}) {
  let session = { uid: 'uid', username: 'synthetic', access_token: 'NEVER_RENDER_TOKEN' }, listener, clock = 0, serial = 0
  const calls = [], tasks = new Map()
  const client = {
    sessionRevision: 1, getSession: () => session,
    subscribeSession(callback) { listener = callback; callback(session, this.sessionRevision); return () => { listener = null } },
    listHealthMembers: async () => [{ id: memberId, is_owner: true, relationship_label: '本人', display_name: '合成本人',
      scopes: ['profile_view', 'profile_edit', 'ai_use', 'report_view', 'diet_edit'], private_profile: 'SECRET_PROFILE' }],
    readProfileLink: async () => ({ member_id: memberId, family_id: 'family', source_member_id: 'source' }),
    readFamilyProfile: async () => ({ status: 'blocked', code: 'profile_incomplete', private_profile: 'SECRET_PROFILE' }),
    readConsultationConfiguration: async () => ({ policy_version: 'v1', consultation: { available: true, model: 'synthetic-model', processor: 'synthetic-processor' } }),
    listMemberConsultations: async () => ({ items: [binding()], has_more: false, next_offset: null }),
    setConsultationConsent: async (id, data) => { calls.push(['consent', id, data]); return { accepted: data.accepted } },
    createDailyConsultation: async id => { calls.push(['daily', id]); return { ...binding(), business_date: '2026-10-10' } },
    createConsultation: async (id, data) => { calls.push(['create', id, data]); return binding() },
    readThreadHistory: async () => history(), readThreadActiveRun: async () => ({ run: null }),
    readAgentRunResult: async () => result(), readAgentRun: async () => ({ run: run() }),
    submitConsultationRequest: async (id, data) => { calls.push(['submit', id, data]); return { request_id: data.request_id, thread_id: id, status: 'queued', run_id: null } },
    readAgentRequest: async id => ({ request: { request_id: id, uid: 'uid', agent_slug: 'health-consultation', thread_id: threadId, status: 'dispatched', dispatched_run_id: 'run' } }),
    ...overrides,
  }
  const controller = createConsultationController({ client, newId: () => 'request', now: () => clock,
    schedule: callback => { const id = ++serial; tasks.set(id, callback); return id }, cancel: id => tasks.delete(id), ...options })
  return { client, controller, calls, tasks,
    changeSession(next) { session = next; client.sessionRevision += 1; listener?.(session, client.sessionRevision) },
    async tick(ms = 1500) { clock += ms; const [id, callback] = tasks.entries().next().value || []; if (callback) { tasks.delete(id); await callback() } await drain() } }
}

async function ready(context, create = false) {
  await context.controller.show(memberId)
  if (create) { context.controller.setConsentChoice(true); await context.controller.createThread('new') }
  else await context.controller.openThread(threadId)
}

test('进入只读取真实本人关联与当前政策，没有自动grant/consent/create；基础档案不ready不阻止普通咨询', async () => {
  const context = setup(); await context.controller.show(memberId)
  assert.equal(context.controller.getState().blocked, false); assert.equal(context.controller.getState().profile.ready, false)
  assert.deepEqual(context.calls, []); assert.equal(context.controller.getState().consentAccepted, false)
  assert.equal(JSON.stringify(context.controller.getState()).includes('SECRET_PROFILE'), false)
  assert.equal(JSON.stringify(context.controller.getState()).includes('NEVER_RENDER_TOKEN'), false)
  context.controller.dispose()
})

test('未关联、非本人或欠缺身份档案权限均禁止入口', async () => {
  for (const overrides of [{ readProfileLink: async () => ({ member_id: memberId, source_member_id: null }) },
    { listHealthMembers: async () => [{ id: memberId, is_owner: false, relationship_label: '本人', scopes: ['profile_view', 'profile_edit'] }] }]) {
    const context = setup(overrides); await context.controller.show(memberId)
    context.controller.setConsentChoice(true); await context.controller.createThread('daily')
    assert.equal(context.controller.getState().blocked, true); assert.deepEqual(context.calls, []); context.controller.dispose()
  }
})

test('恢复线程重新读取历史及权威结果；无本次选择时不可提交', async () => {
  const context = setup(); await ready(context)
  assert.deepEqual(context.controller.getState().messages.map(row => row.text), ['合成公开问题', '合成公开回答'])
  context.controller.setQuery('新问题'); await context.controller.submit()
  assert.deepEqual(context.calls, []); assert.equal(context.controller.getState().consentAccepted, false)
  await context.controller.openThread('unbound-thread'); assert.equal(context.controller.getState().thread.thread_id, threadId)
  context.controller.dispose()
})

test('明确同意后创建真实线程，并发送固定原问题；completed才读取并展示权威回答', async () => {
  const context = setup(); await ready(context, true)
  assert.deepEqual(context.calls.map(call => call[0]), ['consent', 'create'])
  assert.deepEqual(context.calls[0][2], { accepted: true, processor: 'synthetic-processor', policy_version: 'v1' })
  context.controller.setQuery(' 合成问题 '); await context.controller.submit(); await drain()
  assert.deepEqual(context.calls.at(-1), ['submit', threadId, { query: ' 合成问题 ', request_id: 'request' }])
  assert.equal(context.controller.getState().run.status, 'completed'); assert.equal(context.controller.getState().polling, false)
  assert.equal(context.controller.getState().messages.at(-1).text, '合成公开回答'); context.controller.dispose()
})

for (const status of [0, 500, 502, 503, 504]) {
  test(`提交返回${status}后显式原包重试，不能换正文、线程或请求键且只写入一次`, async () => {
    let generatedIds = 0; const submits = [], receipts = new Map()
    const context = setup({ submitConsultationRequest: async (id, data) => {
      submits.push([id, { ...data }])
      if (!receipts.has(data.request_id)) receipts.set(data.request_id, {
        body: [id, { ...data }], response: { request_id: data.request_id, thread_id: id, status: 'queued', run_id: null },
      })
      const receipt = receipts.get(data.request_id)
      assert.deepEqual([id, data], receipt.body)
      // 模拟事务已提交、随后投递或响应失败，重试只能取回同一逻辑收据。
      if (submits.length === 1) throw failure(status)
      return receipt.response
    }, readAgentRequest: async id => ({ request: { request_id: id, uid: 'uid', agent_slug: 'health-consultation',
      thread_id: threadId, status: 'queued', dispatched_run_id: null } }) }, { newId: () => `request-${++generatedIds}` })
    await ready(context, true); context.controller.setQuery(' 保留原问题 '); await context.controller.submit()
    assert.equal(context.controller.getState().submitUnknown, true)
    assert.equal(generatedIds, 2)
    context.controller.setQuery('换一个问题'); await context.controller.submit(false)
    await context.controller.openThread(threadId)
    assert.equal(context.controller.getState().query, ' 保留原问题 ')
    assert.equal(submits.length, 1); assert.equal(generatedIds, 2); assert.equal(receipts.size, 1)
    await context.controller.submit(true); await drain()
    assert.deepEqual(submits, [[threadId, { query: ' 保留原问题 ', request_id: 'request-2' }],
      [threadId, { query: ' 保留原问题 ', request_id: 'request-2' }]])
    assert.equal(receipts.size, 1); assert.equal(generatedIds, 2)
    assert.equal(context.controller.getState().submitUnknown, false)
    assert.equal(context.controller.getState().request.request_id, 'request-2')
    assert.equal(context.controller.getState().query, ''); context.controller.dispose()
  })

  test(`创建返回${status}后沿用同一创建键和模式，普通按钮不产生重复线程`, async () => {
    let generatedIds = 0; const creates = [], receipts = new Map()
    const context = setup({ createConsultation: async (id, data) => {
      creates.push([id, { ...data }])
      if (!receipts.has(data.client_request_id)) receipts.set(data.client_request_id, { body: [id, { ...data }], response: binding() })
      const receipt = receipts.get(data.client_request_id)
      assert.deepEqual([id, data], receipt.body)
      if (creates.length === 1) throw failure(status)
      return receipt.response
    } }, { newId: () => `request-${++generatedIds}` })
    await context.controller.show(memberId); context.controller.setConsentChoice(true); await context.controller.createThread('new')
    assert.equal(context.controller.getState().createUnknown, true)
    context.controller.setConsentChoice(true); await context.controller.createThread('new'); await context.controller.createThread('daily')
    assert.equal(creates.length, 1); assert.equal(generatedIds, 1); assert.equal(receipts.size, 1)
    await context.controller.createThread('daily', true)
    assert.deepEqual(creates, [[memberId, { client_request_id: 'request-1' }], [memberId, { client_request_id: 'request-1' }]])
    assert.equal(context.calls.filter(call => call[0] === 'daily').length, 0)
    assert.equal(receipts.size, 1); assert.equal(generatedIds, 1)
    assert.equal(context.controller.getState().createUnknown, false)
    assert.equal(context.controller.getState().thread.thread_id, threadId)
    context.controller.setConsentChoice(true); await context.controller.createThread('new')
    assert.deepEqual(creates.at(-1), [memberId, { client_request_id: 'request-2' }])
    assert.equal(creates.length, 3); assert.equal(receipts.size, 2); context.controller.dispose()
  })

  test(`发送创建前同意返回${status}不会误标为未知创建，可重新明确创建`, async () => {
    let generatedIds = 0, consentCalls = 0; const creates = []
    const context = setup({ setConsultationConsent: async () => {
      if (++consentCalls === 1) throw failure(status)
      return { accepted: true }
    }, createConsultation: async (id, data) => { creates.push([id, { ...data }]); return binding() } },
    { newId: () => `request-${++generatedIds}` })
    await context.controller.show(memberId); context.controller.setConsentChoice(true); await context.controller.createThread('new')
    assert.equal(context.controller.getState().createUnknown, false)
    assert.equal(context.controller.getState().consentAccepted, false); assert.deepEqual(creates, [])
    await context.controller.createThread('new', true); assert.equal(consentCalls, 1)
    context.controller.setConsentChoice(true); await context.controller.createThread('new')
    assert.deepEqual(creates, [[memberId, { client_request_id: 'request-2' }]])
    assert.equal(context.controller.getState().createUnknown, false); context.controller.dispose()
  })
}

test('创建响应已确认后历史或active读取失败不回到未知创建，不重发已成功的创建包', async () => {
  for (const method of ['readThreadHistory', 'readThreadActiveRun']) {
    let generatedIds = 0; const context = setup({ [method]: async () => { throw failure(503) } },
      { newId: () => `request-${++generatedIds}` })
    await context.controller.show(memberId); context.controller.setConsentChoice(true); await context.controller.createThread('new')
    assert.equal(context.controller.getState().createUnknown, false, method)
    assert.equal(context.controller.getState().thread.thread_id, threadId, method)
    assert.equal(context.controller.getState().error, '合成错误', method)
    await context.controller.createThread('new', true)
    assert.equal(context.calls.filter(call => call[0] === 'create').length, 1, method)
    assert.equal(generatedIds, 1, method); context.controller.dispose()
  }
})

test('未知创建恢复前重新同意失败保留此前原包，恢复成功仍只写同一键', async () => {
  let generatedIds = 0; const creates = []
  const context = setup({ createConsultation: async (id, data) => {
    creates.push([id, { ...data }]); if (creates.length === 1) throw failure(503); return binding()
  } }, { newId: () => `request-${++generatedIds}` })
  await context.controller.show(memberId); context.controller.setConsentChoice(true); await context.controller.createThread('new')
  await context.controller.withdrawConsent(); context.controller.setConsentChoice(true)
  context.client.setConsultationConsent = async () => { throw failure(503) }
  await context.controller.createThread('new', true)
  assert.equal(context.controller.getState().createUnknown, true); assert.equal(creates.length, 1)
  context.client.setConsultationConsent = async () => ({ accepted: true })
  await context.controller.createThread('new', true)
  assert.deepEqual(creates, [[memberId, { client_request_id: 'request-1' }], [memberId, { client_request_id: 'request-1' }]])
  assert.equal(context.controller.getState().createUnknown, false); assert.equal(generatedIds, 1); context.controller.dispose()
})

test('未知创建或提交的恢复返回401/403/404/410继续清除原包与私有视图', async () => {
  for (const status of [401, 403, 404, 410]) {
    for (const operation of ['create', 'submit']) {
      let attempts = 0, generatedIds = 0
      const write = async () => { throw failure(++attempts === 1 ? 503 : status) }
      const context = setup(operation === 'create' ? { createConsultation: write } : { submitConsultationRequest: write },
        { newId: () => `request-${++generatedIds}` })
      if (operation === 'create') {
        await context.controller.show(memberId); context.controller.setConsentChoice(true)
        await context.controller.createThread('new'); await context.controller.createThread('new', true)
      } else {
        await ready(context, true); context.controller.setQuery('合成原问题')
        await context.controller.submit(); await context.controller.submit(true)
      }
      const state = context.controller.getState(), label = `${operation}:${status}`
      assert.equal(state.createUnknown, false, label); assert.equal(state.submitUnknown, false, label)
      assert.equal(state.thread, null, label); assert.equal(state.query, '', label); assert.deepEqual(state.messages, [], label)
      assert.equal(state.consentAccepted, false, label); assert.equal(state.blocked, status !== 410, label)
      assert.equal(state.needsNew, status === 410, label)
      await context.controller.createThread('new', true); await context.controller.submit(true)
      assert.equal(attempts, 2, label); context.controller.dispose()
    }
  }
})

test('普通轮询有界；超时不伪造Run失败，继续读取沿用同一Request', async () => {
  const ids = []; const context = setup({ readAgentRequest: async id => { ids.push(id); return { request: { request_id: id,
    uid: 'uid', agent_slug: 'health-consultation', thread_id: threadId, status: 'queued', dispatched_run_id: null } } },
  readThreadHistory: async () => history(false) }, { pollBudget: 1500 })
  await ready(context, true); context.controller.setQuery('等待'); await context.controller.submit(); await drain(); await context.tick(1500)
  assert.equal(context.controller.getState().pollTimedOut, true); assert.equal(context.controller.getState().run, null)
  context.controller.continuePolling(); await drain(); assert.deepEqual(ids, ['request', 'request']); context.controller.dispose()
})

test('pending/running与interrupted不展示部分回答、不自动resume', async () => {
  for (const status of ['pending', 'running', 'interrupted']) {
    const context = setup({ readThreadHistory: async () => history(false), readAgentRun: async () => ({ run: run(status) }) })
    await ready(context, true); context.controller.setQuery('问题'); await context.controller.submit(); await drain()
    assert.deepEqual(context.controller.getState().messages, []); assert.equal(context.controller.getState().run.status, status)
    assert.equal(context.controller.getState().polling, status !== 'interrupted'); context.controller.dispose()
  }
})

test('history404、run404、result200 run_not_found都清除回答并禁止继续', async () => {
  for (const endpoint of ['history', 'run', 'result']) {
    const context = setup(); await ready(context, true); assert.equal(context.controller.getState().messages.length, 2)
    if (endpoint === 'history') context.client.readThreadHistory = async () => { throw failure(404) }
    if (endpoint === 'run') context.client.readAgentRun = async () => { throw failure(404) }
    if (endpoint === 'result') context.client.readAgentRunResult = async () => ({ status: 'failed', output: '', error: { type: 'run_not_found' } })
    if (endpoint === 'history') await context.controller.openThread(threadId)
    else { context.controller.setQuery('新问题'); await context.controller.submit(); await drain() }
    assert.equal(context.controller.getState().blocked, true, endpoint); assert.deepEqual(context.controller.getState().messages, [])
    assert.equal(context.controller.getState().thread, null); context.controller.dispose()
  }
})

test('410来源变化清回答并要求明确新建，不自动替换旧thread', async () => {
  const context = setup({ submitConsultationRequest: async () => { throw failure(410) } })
  await ready(context, true); context.controller.setQuery('问题'); await context.controller.submit()
  assert.equal(context.controller.getState().needsNew, true); assert.equal(context.controller.getState().thread, null)
  assert.equal(context.controller.getState().consentAccepted, false); assert.deepEqual(context.controller.getState().messages, [])
  assert.equal(context.calls.filter(call => call[0] === 'create').length, 1); context.controller.dispose()
})

test('撤回咨询用途同意仅禁止新提交，保留当前仍授权的公开历史', async () => {
  const context = setup(); await ready(context, true); await context.controller.withdrawConsent()
  assert.equal(context.controller.getState().consentAccepted, false); assert.equal(context.controller.getState().messages.length, 2)
  assert.equal(context.calls.at(-1)[2].accepted, false); context.controller.setQuery('问题'); await context.controller.submit()
  assert.equal(context.calls.filter(call => call[0] === 'submit').length, 0); context.controller.dispose()
})

test('隐藏、切号和401同时清私有UI；迟到历史与回答不能恢复旧账号状态', async () => {
  for (const change of ['hide', 'account', '401']) {
    const delayed = deferred(), context = setup({ readAgentRunResult: async () => delayed.promise })
    await context.controller.show(memberId); const opening = context.controller.openThread(threadId); await drain()
    if (change === 'hide') context.controller.hide()
    else context.changeSession(change === '401' ? null : { uid: 'next', username: 'next', access_token: 'new-secret' })
    delayed.resolve(result()); await opening
    assert.deepEqual(context.controller.getState().messages, []); assert.equal(context.controller.getState().thread, null)
    assert.equal(context.controller.getState().query, ''); context.controller.dispose()
  }
})

test('隐藏后迟到配置、创建、POST和轮询结果均被丢弃，定时器停止', async () => {
  for (const method of ['readConsultationConfiguration', 'createConsultation', 'submitConsultationRequest', 'readAgentRequest']) {
    const delayed = deferred(), context = setup(); let pending
    if (method === 'readConsultationConfiguration') {
      context.client[method] = async () => delayed.promise; pending = context.controller.show(memberId)
    } else {
      await ready(context, method !== 'createConsultation')
      context.client[method] = async () => delayed.promise
      if (method === 'createConsultation') { context.controller.setConsentChoice(true); pending = context.controller.createThread('new') }
      else { context.controller.setQuery('问题'); pending = context.controller.submit() }
    }
    await drain(); context.controller.hide(); delayed.resolve(method === 'createConsultation' ? binding()
      : method === 'submitConsultationRequest' ? { request_id: 'request', thread_id: threadId, status: 'queued', run_id: null }
        : method === 'readAgentRequest' ? { request: { request_id: 'request', uid: 'uid', agent_slug: 'health-consultation', thread_id: threadId, status: 'queued', dispatched_run_id: null } }
          : { policy_version: 'v1', consultation: { available: true, model: 'model', processor: 'processor' } })
    await pending; await drain(); assert.deepEqual(context.controller.getState().messages, [], method)
    assert.equal(context.controller.getState().thread, null, method); assert.equal(context.tasks.size, 0, method); context.controller.dispose()
  }
})

test('历史分页只接受当前member真实绑定并向后推进', async () => {
  const offsets = [], context = setup({ listMemberConsultations: async (id, page) => { offsets.push(page.offset)
    return { items: [{ ...binding(), thread_id: `thread-${page.offset}` }], has_more: page.offset === 0, next_offset: page.offset === 0 ? 20 : null } } })
  await context.controller.show(memberId); await context.controller.loadConsultations(true)
  assert.deepEqual(offsets, [0, 20]); assert.equal(context.controller.getState().consultations.length, 2)
  context.controller.dispose()
})

test('列表403或410废弃同时在途的历史、同意撤回和列表结果，晚到不能回填且加载标记收敛', async () => {
  for (const status of [403, 410]) {
    const delayedHistory = deferred(), delayedConsent = deferred(), context = setup()
    await ready(context, true)
    context.client.readThreadHistory = async () => delayedHistory.promise
    context.client.setConsultationConsent = async () => delayedConsent.promise
    const opening = context.controller.openThread(threadId), withdrawing = context.controller.withdrawConsent()
    await drain()
    context.client.listMemberConsultations = async () => { throw failure(status) }
    await context.controller.loadConsultations(false)
    assert.deepEqual(context.controller.getState().messages, [])
    assert.equal(context.controller.getState().thread, null)
    delayedHistory.resolve(history()); delayedConsent.resolve({ accepted: false }); await opening; await withdrawing
    const state = context.controller.getState()
    assert.deepEqual(state.messages, [], String(status)); assert.equal(state.thread, null, String(status))
    assert.equal(state.consentAccepted, false); assert.equal(state.loading, false); assert.equal(state.busy, false)
    assert.equal(state.historyLoading, false); assert.equal(state.listLoading, false)
    assert.equal(state.blocked, status === 403); assert.equal(state.needsNew, status === 410)
    context.controller.dispose()
  }
})

test('历史拒读使在途列表无权重新写入旧绑定记录', async () => {
  const delayedList = deferred(), context = setup(); await ready(context, true)
  context.client.listMemberConsultations = async () => delayedList.promise
  const listing = context.controller.loadConsultations(false)
  context.client.readThreadHistory = async () => { throw failure(404) }
  await context.controller.openThread(threadId)
  delayedList.resolve({ items: [{ ...binding(), thread_id: 'late-private-binding' }], has_more: false, next_offset: null }); await listing
  assert.equal(context.controller.getState().blocked, true)
  assert.equal(context.controller.getState().consultations.some(item => item.thread_id === 'late-private-binding'), false)
  assert.deepEqual(context.controller.getState().messages, []); assert.equal(context.controller.getState().listLoading, false)
  context.controller.dispose()
})

test('上一次页面的创建失败晚到不能清除新页面的原包重试键', async () => {
  const delayed = deferred(); let count = 0
  const context = setup({ createConsultation: async () => {
    count += 1
    if (count === 1) return delayed.promise
    if (count === 2) throw failure(0)
    return binding()
  } })
  await context.controller.show(memberId); context.controller.setConsentChoice(true)
  const previous = context.controller.createThread('new'); await drain()
  context.controller.hide(); await context.controller.show(memberId)
  context.controller.setConsentChoice(true); await context.controller.createThread('new')
  assert.equal(context.controller.getState().createUnknown, true)
  delayed.reject(failure(0)); await previous
  await context.controller.createThread('new', true)
  assert.equal(count, 3); assert.equal(context.controller.getState().createUnknown, false)
  assert.equal(context.controller.getState().thread.thread_id, threadId); context.controller.dispose()
})
