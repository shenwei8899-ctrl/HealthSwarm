import test from 'node:test'
import assert from 'node:assert/strict'
import { createHealthTaskFlow } from '../src/services/health-task-flow.js'

const memberId = '11111111-1111-4111-8111-111111111111'
const entryId = '22222222-2222-4222-8222-222222222222'
const requestId = '33333333-3333-4333-8333-333333333333'
const threadId = '44444444-4444-4444-8444-444444444444'
const taskType = 'blood_glucose_review'
function fixture(overrides = {}) {
  let account = { accountId: '17', token: 'synthetic' }, revision = 'one'
  const calls = [], saved = new Map(), scheduled = []
  const storage = { getStorageSync: key => saved.get(key), setStorageSync: (key, value) => saved.set(key, structuredClone(value)) }
  const send = async options => {
    calls.push(options)
    if (options.path === '/api/health/v1/members') return { data: [{ id: memberId, is_owner: true }] }
    if (options.path.endsWith('/readiness')) return { data: { capabilities: { member_id: memberId }, entries: [{ entry_type: taskType, status: 'available' }] } }
    if (options.path.endsWith('/task-entries')) return { data: { member_id: memberId, task_type: taskType,
      client_request_id: entryId, entry_status: 'ready', thread_id: threadId, agent_slug: 'health-blood-glucose', request_submit_url: '/api/agent/runs' } }
    if (options.path === '/api/agent/runs') return { data: { request_id: requestId, thread_id: threadId, status: 'dispatched' } }
    if (options.path.endsWith('/tasks/' + requestId)) return { data: { request_id: requestId, member_id: memberId,
      task_type: taskType, thread_id: threadId, agent_slug: 'health-blood-glucose', request_status: 'dispatched',
      execution_status: 'running', result: null } }
    throw new Error('unexpected request ' + options.path)
  }
  const flow = createHealthTaskFlow({ send: options => overrides.send ? (calls.push(options), overrides.send(options)) : send(options), session: () => account,
    revision: () => revision, storage, newId: (() => { const ids = [entryId, requestId]; return () => ids.shift() })(),
    schedule: fn => { scheduled.push(fn); return scheduled.length }, cancel: () => {}, ...overrides.flow })
  return { flow, calls, saved, scheduled, storage, setAccount: value => { account = value; revision = String(Number(revision === 'one' ? 1 : revision) + 1) } }
}

test('indicator task uses separate entry and run IDs, and displays only the authorized Task result', async () => {
  let completed = false
  const h = fixture({ send: async options => {
    if (options.path.endsWith('/tasks/' + requestId)) return { data: { request_id: requestId, member_id: memberId,
      task_type: taskType, thread_id: threadId, agent_slug: 'health-blood-glucose', request_status: 'dispatched',
      execution_status: completed ? 'completed' : 'running', result: completed ? { result_type: 'general_education_answer',
        scope: 'general_education', answer: '请记录实际测量时间。', citations: [{ title: '审核资料' }] } : null } }
    return fixtureBase(options)
  } })
  await h.flow.open(memberId, taskType); await h.flow.createEntry()
  await h.flow.submit('看看我的血糖记录')
  assert.equal(h.flow.getState().result, null)
  const sent = h.calls.find(call => call.path === '/api/agent/runs')
  assert.equal(sent.data.meta.request_id, requestId)
  assert.equal(sent.data.thread_id, threadId)
  assert.equal(sent.data.agent_slug, 'health-blood-glucose')
  assert.equal(h.calls.find(call => call.path.endsWith('/task-entries')).headers['Idempotency-Key'], entryId)
  completed = true; await h.flow.refresh()
  assert.ok(h.flow.getState().result, JSON.stringify(h.flow.getState()))
  assert.equal(h.flow.getState().result.text, '请记录实际测量时间。')
  assert.deepEqual(h.flow.getState().result.citations, ['审核资料'])
  const persisted = h.saved.get(`health-task:${memberId}:${taskType}`)
  assert.equal(persisted.requestId, requestId)
  assert.equal(JSON.stringify(persisted).includes('看看我的血糖'), false)
  assert.equal(JSON.stringify(persisted).includes('请记录实际测量'), false)
  h.flow.hide(); assert.equal(h.flow.getState().result, null)
})

function fixtureBase(options) {
  if (options.path === '/api/health/v1/members') return { data: [{ id: memberId, is_owner: true }] }
  if (options.path.endsWith('/readiness')) return { data: { capabilities: { member_id: memberId }, entries: [{ entry_type: taskType, status: 'available' }] } }
  if (options.path.endsWith('/task-entries')) return { data: { member_id: memberId, task_type: taskType,
    client_request_id: entryId, entry_status: 'ready', thread_id: threadId, agent_slug: 'health-blood-glucose', request_submit_url: '/api/agent/runs' } }
  if (options.path === '/api/agent/runs') return { data: { request_id: requestId, thread_id: threadId } }
  throw new Error('unexpected request ' + options.path)
}

test('lost submit response keeps the same request ID and blocks a different question', async () => {
  let attempts = 0
  const h = fixture({ send: async options => {
    if (options.path === '/api/agent/runs' && ++attempts === 1) throw Object.assign(new Error('timeout'), { code: 'NETWORK_ERROR' })
    if (options.path.endsWith('/tasks/' + requestId)) {
      if (attempts === 1) throw Object.assign(new Error('not found'), { code: 404 })
      return { data: { request_id: requestId, member_id: memberId, task_type: taskType, thread_id: threadId,
        agent_slug: 'health-blood-glucose', request_status: 'dispatched', execution_status: 'running', result: null } }
    }
    return fixtureBase(options)
  } })
  await h.flow.open(memberId, taskType); await h.flow.createEntry(); await h.flow.submit('原问题')
  assert.equal(h.flow.getState().submitUnknown, true)
  await h.flow.submit('另一个问题')
  assert.equal(attempts, 1)
  await h.flow.refresh()
  assert.equal(h.flow.getState().canRetry, true)
  await h.flow.submit('', true)
  assert.equal(attempts, 2)
  assert.equal(h.calls.filter(call => call.path === '/api/agent/runs').every(call =>
    call.data.meta.request_id === requestId && call.data.query === '原问题'), true)
})

test('a late task response after account switch cannot reveal a health answer', async () => {
  let release
  const h = fixture({ send: async options => {
    if (options.path.endsWith('/tasks/' + requestId)) return await new Promise(resolve => { release = resolve })
    return fixtureBase(options)
  } })
  await h.flow.open(memberId, taskType); await h.flow.createEntry()
  const pending = h.flow.submit('问题')
  await new Promise(resolve => setImmediate(resolve))
  h.setAccount({ accountId: '18', token: 'other' }); h.flow.hide()
  release({ data: { request_id: requestId, member_id: memberId, task_type: taskType, thread_id: threadId,
    agent_slug: 'health-blood-glucose', request_status: 'dispatched', execution_status: 'completed',
    result: { result_type: 'general_education_answer', scope: 'general_education', answer: '旧账号内容', citations: [] } } })
  await pending
  assert.equal(h.flow.getState().result, null)
})

test('consent is explicit, uses current server policy, and rechecks readiness', async () => {
  let accepted = false
  const h = fixture({ send: async options => {
    if (options.path.endsWith('/readiness')) return { data: { capabilities: { member_id: memberId }, entries: [
      { entry_type: taskType, status: accepted ? 'available' : 'needs_input', reason_code: accepted ? null : 'consent_required' },
    ] } }
    if (options.path === '/api/health/v1/configuration') return { data: { policy_version: 'approved-v2',
      consultation: { available: true, processor: 'approved-provider' } } }
    if (options.path.endsWith('/processing-consents')) { accepted = true; return { data: { accepted: true } } }
    return fixtureBase(options)
  } })
  await h.flow.open(memberId, taskType)
  assert.equal(h.flow.getState().available, false)
  assert.deepEqual(h.flow.getState().consentOption, { processor: 'approved-provider', policyVersion: 'approved-v2' })
  await h.flow.acceptConsent(false)
  assert.equal(h.calls.some(call => call.path.endsWith('/processing-consents')), false)
  await h.flow.acceptConsent(true)
  assert.equal(h.flow.getState().available, true)
  assert.deepEqual(h.calls.find(call => call.path.endsWith('/processing-consents')).data,
    { purpose: 'consultation', accepted: true, processor: 'approved-provider', policy_version: 'approved-v2' })
})

test('a Task bound to another member clears the private projection and saved pointer', async () => {
  const h = fixture({ send: async options => {
    if (options.path.endsWith('/tasks/' + requestId)) return { data: { request_id: requestId,
      member_id: '99999999-9999-4999-8999-999999999999', task_type: taskType,
      thread_id: threadId, agent_slug: 'health-blood-glucose', request_status: 'dispatched',
      execution_status: 'completed', result: { result_type: 'general_education_answer',
        scope: 'general_education', answer: '不该展示', citations: [] } } }
    return fixtureBase(options)
  } })
  await h.flow.open(memberId, taskType); await h.flow.createEntry(); await h.flow.submit('问题')
  assert.equal(h.flow.getState().result, null)
  assert.equal(h.flow.getState().entry, null)
  assert.equal(h.saved.get(`health-task:${memberId}:${taskType}`), null)
})

test('an older status read cannot replace a newer completed answer', async () => {
  let reads = 0, releaseOld
  const baseTask = { request_id: requestId, member_id: memberId, task_type: taskType,
    thread_id: threadId, agent_slug: 'health-blood-glucose', request_status: 'dispatched' }
  const h = fixture({ send: async options => {
    if (options.path.endsWith('/tasks/' + requestId)) {
      reads++
      if (reads === 2) return await new Promise(resolve => { releaseOld = resolve })
      return { data: reads === 1 ? { ...baseTask, execution_status: 'running', result: null }
        : { ...baseTask, execution_status: 'completed', result: { result_type: 'general_education_answer',
          scope: 'general_education', answer: '当前答复', citations: [] } } }
    }
    return fixtureBase(options)
  } })
  h.storage.setStorageSync(`health-task:${memberId}:${taskType}`, { memberId, taskType,
    entry: { client_request_id: entryId, thread_id: threadId, agent_slug: 'health-blood-glucose' }, requestId })
  await h.flow.open(memberId, taskType)
  const old = h.flow.refresh()
  await new Promise(resolve => setImmediate(resolve))
  await h.flow.refresh()
  releaseOld({ data: { ...baseTask, execution_status: 'running', result: null } })
  await old
  assert.equal(h.flow.getState().result.text, '当前答复')
})
