import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
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

test('a reference followup can restore the original authorized thread and question',async()=>{
 const referenceType='reference_meal_preview'
 const h=fixture({send:async options=>{
  if(options.path==='/api/health/v1/members')return {data:[{id:memberId,is_owner:true}]}
  if(options.path.endsWith('/readiness'))return {data:{capabilities:{member_id:memberId},entries:[{entry_type:referenceType,status:'available'}]}}
  if(options.path.endsWith('/tasks/'+requestId))return {data:{request_id:requestId,member_id:memberId,task_type:referenceType,thread_id:threadId,agent_slug:'health-meal-planner',request_status:'dispatched',execution_status:'completed',result:{result_type:'needs_input',questions:['早餐需要避开什么食材？']}}}
  throw new Error('unexpected '+options.path)
 }})
 await h.flow.open(memberId,referenceType,{mode:'reference'})
 assert.equal(await h.flow.restoreReferenceRequest(threadId,requestId),true)
 assert.equal(h.flow.getState().entry.thread_id,threadId)
 assert.deepEqual(h.flow.getState().result.questions,['早餐需要避开什么食材？'])
})

function fixtureBase(options) {
  if (options.path === '/api/health/v1/members') return { data: [{ id: memberId, is_owner: true }] }
  if (options.path.endsWith('/readiness')) return { data: { capabilities: { member_id: memberId }, entries: [{ entry_type: taskType, status: 'available' }] } }
  if (options.path.endsWith('/task-entries')) return { data: { member_id: memberId, task_type: taskType,
    client_request_id: entryId, entry_status: 'ready', thread_id: threadId, agent_slug: 'health-blood-glucose', request_submit_url: '/api/agent/runs' } }
  if (options.path === '/api/agent/runs') return { data: { request_id: requestId, thread_id: threadId } }
  throw new Error('unexpected request ' + options.path)
}

test('pausing an uncertain submit retains its request key and late responses cannot overwrite it',async()=>{
 let completePost
 const h=fixture({send:async options=>{
   if(options.path==='/api/agent/runs')return new Promise(resolve=>{completePost=resolve})
   if(options.path.endsWith('/tasks/'+requestId))throw Object.assign(new Error('not found'),{code:404})
   return fixtureBase(options)
 }})
 await h.flow.open(memberId,taskType);await h.flow.createEntry()
 const pending=h.flow.submit('合成问题');h.flow.pause()
 assert.equal(h.flow.getState().requestId,requestId);assert.equal(h.flow.getState().submitUnknown,true);assert.equal(h.flow.getState().canRetry,true)
 completePost({data:{request_id:requestId,thread_id:threadId}});await pending
 assert.equal(h.flow.getState().submitUnknown,true)
 assert.equal(await h.flow.resume(),true);assert.equal(h.flow.getState().requestId,requestId);assert.equal(h.flow.getState().canRetry,true)
 assert.equal(h.calls.filter(c=>c.path==='/api/agent/runs').length,1)
})

test('selected indicator scope is sent unchanged and kept apart from default threads', async () => {
  const selection = { start_date: '2026-10-01', end_date: '2026-10-16', records: [{ record_id: requestId, version: 2 }] }
  const h = fixture()
  await h.flow.open(memberId, taskType, selection)
  await h.flow.createEntry()
  assert.deepEqual(h.calls.find(call => call.path.endsWith('/task-entries')).data.selection, selection)
  assert.equal(h.saved.has(`health-task:${memberId}:${taskType}`), false)
  assert.equal(h.saved.has(`health-task:${memberId}:${taskType}:${JSON.stringify(selection)}`), true)
})

test('saved-meal chat binds the exact version and retries only thread creation', async () => {
  const selection = { record_id: requestId, source_version: 2 }
  let attempts = 0
  const h = fixture({ send: async options => {
    if (options.path.includes('/diet-logs/page')) return { data: { records:[{ id: requestId, source_version: 2 }],next_offset:null } }
    if (options.path.endsWith('/readiness')) return { data: { capabilities: { member_id: memberId }, entries: [{ entry_type: 'diet_analysis', status: 'available' }] } }
    if (options.path.endsWith('/feedback-conversation')) {
      if (++attempts === 1) throw Object.assign(new Error('timeout'), { code: 'NETWORK_ERROR' })
      return { data: { member_id: memberId, thread_id: threadId, agent_slug: 'health-diet-analyst', feedback_selection: selection } }
    }
    return fixtureBase(options)
  } })
  await h.flow.open(memberId, 'diet_analysis', selection)
  await h.flow.createEntry(); await h.flow.createEntry()
  const writes = h.calls.filter(call => call.method === 'POST')
  assert.equal(writes.length, 2)
  assert.ok(writes.every(call => call.path.endsWith('/feedback-conversation')))
  assert.deepEqual(writes[0].data, { client_request_id: entryId, source_version: 2 })
  assert.deepEqual(writes[0], writes[1])
  assert.equal(h.flow.getState().entry.thread_id, threadId)
})

test('changed meal source cannot create a feedback thread', async () => {
  const h = fixture({ send: async options => {
    if (options.path.includes('/diet-logs/page')) return { data: { records:[{ id: requestId, source_version: 3 }],next_offset:null } }
    if (options.path.endsWith('/readiness')) return { data: { capabilities: { member_id: memberId }, entries: [{ entry_type: 'diet_analysis', status: 'available' }] } }
    return fixtureBase(options)
  } })
  await h.flow.open(memberId, 'diet_analysis', { record_id: requestId, source_version: 2 })
  await h.flow.createEntry()
  assert.equal(h.flow.getState().available, false)
  assert.equal(h.calls.some(call => call.method === 'POST'), false)
})

test('meal feedback displays the verified receipt and rejects a different source', async () => {
  const selection = { record_id: requestId, source_version: 2 }
  let wrongSource = false
  const h = fixture({ send: async options => {
    if (options.path.includes('/diet-logs/page')) return { data: { records:[{ id: requestId, source_version: 2 }],next_offset:null } }
    if (options.path.endsWith('/readiness')) return { data: { capabilities: { member_id: memberId }, entries: [{ entry_type: 'diet_analysis', status: 'available' }] } }
    if (options.path.endsWith('/feedback-conversation')) return { data: { member_id: memberId, thread_id: threadId, agent_slug: 'health-diet-analyst', feedback_selection: selection } }
    if (options.path.endsWith('/tasks/' + requestId)) return { data: { request_id: requestId, member_id: memberId, task_type: 'diet_analysis', thread_id: threadId, agent_slug: 'health-diet-analyst', request_status: 'dispatched', execution_status: 'completed', result: { result_type: 'meal_feedback', data: { status: 'saved', records: [{ ...selection, source_version: wrongSource ? 1 : 2 }], feedback: { diet_log_id: requestId, status: 'active', version: 1, details: { comment: '口味偏咸' } } } } } }
    return fixtureBase(options)
  } })
  await h.flow.open(memberId, 'diet_analysis', selection); await h.flow.createEntry(); await h.flow.submit('记录这餐反馈：口味偏咸')
  assert.match(h.flow.getState().result.text, /口味偏咸/)
  wrongSource = true; await h.flow.refresh()
  assert.equal(h.flow.getState().result, null)
  assert.equal(h.flow.getState().available, false)
})

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

test('concurrent reads of one request share the same verified completion', async () => {
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
  const concurrent = h.flow.refresh()
  assert.equal(reads, 2, 'the open read and one shared refresh are the only HTTP reads')
  releaseOld({ data: { ...baseTask, execution_status: 'completed', result: { result_type: 'general_education_answer',
    scope: 'general_education', answer: '当前答复', citations: [] } } })
  await Promise.all([old, concurrent])
  assert.equal(h.flow.getState().result.text, '当前答复')
})

test('unknown submit survives hide and reopens with the exact original request', async () => {
  let writes = 0
  const h = fixture({ send: async options => {
    if (options.path === '/api/agent/runs') {
      if (++writes === 1) throw Object.assign(new Error('timeout'), { code: 'NETWORK_ERROR' })
      return { data: { request_id: requestId, thread_id: threadId } }
    }
    if (options.path.endsWith('/tasks/' + requestId)) {
      if (writes === 1) throw Object.assign(new Error('absent'), { code: 404 })
      return { data: { request_id: requestId, member_id: memberId, task_type: taskType, thread_id: threadId,
        agent_slug: 'health-blood-glucose', request_status: 'dispatched', execution_status: 'running' } }
    }
    return fixtureBase(options)
  } })
  await h.flow.open(memberId, taskType); await h.flow.createEntry(); await h.flow.submit('冻结的原问题')
  h.flow.hide(); await h.flow.open(memberId, taskType)
  assert.equal(h.flow.getState().canRetry, true)
  await h.flow.submit('', true)
  const submitted = h.calls.filter(row => row.path === '/api/agent/runs')
  assert.deepEqual(submitted[0], submitted[1])
  assert.equal(h.saved.get(`health-task:${memberId}:${taskType}`).pendingQuery, '')
})

test('rejected requests permit an explicit new question and preserve request order', async () => {
  const second = '55555555-5555-4555-8555-555555555555'
  let active = requestId, next = 0
  const h = fixture({ flow: { newId: () => [entryId, requestId, second][next++] }, send: async options => {
    if (options.path === '/api/agent/runs') { active = options.data.meta.request_id; return { data: { request_id: active, thread_id: threadId } } }
    if (options.path.includes('/tasks/')) return { data: { request_id: active, member_id: memberId, task_type: taskType,
      thread_id: threadId, agent_slug: 'health-blood-glucose', execution_status: 'not_dispatched', request_status: 'rejected' } }
    return fixtureBase(options)
  } })
  await h.flow.open(memberId, taskType); await h.flow.createEntry(); await h.flow.submit('第一次'); await h.flow.submit('第二次')
  assert.equal(h.calls.filter(row => row.path === '/api/agent/runs').length, 2)
  assert.deepEqual(h.flow.getState().requests.map(row => row.request_id), [requestId, second])
})

test('delegated feedback follows server permissions while indicators still require self ownership', async () => {
  const selection = { record_id: requestId, source_version: 2 }
  const h = fixture({ send: async options => {
    if (options.path.endsWith('/members')) return { data: [{ id: memberId, is_owner: false, scopes: ['diet_edit', 'ai_use'] }] }
    if (options.path.includes('/diet-logs/page')) return { data: { records:[{ id: requestId, source_version: 2 }],next_offset:null } }
    if (options.path.endsWith('/readiness')) return { data: { capabilities: { member_id: memberId }, entries: [{ entry_type: 'diet_analysis', status: 'available' }] } }
    if (options.path.endsWith('/feedback-conversation')) return { data: { member_id: memberId, thread_id: threadId, agent_slug: 'health-diet-analyst', feedback_selection: selection } }
    return fixtureBase(options)
  } })
  await h.flow.open(memberId, 'diet_analysis', selection); await h.flow.createEntry()
  assert.equal(h.flow.getState().entry.thread_id, threadId)
  await h.flow.open(memberId, taskType)
  assert.equal(h.flow.getState().available, false)
})

test('run event cursors resume and private stream errors erase task projections', async () => {
  const runId = '66666666-6666-4666-8666-666666666666', subscriptions = []
  const h = fixture({ flow: { subscribe: options => { subscriptions.push(options); return () => {} } }, send: async options => {
    if (options.path.includes('/tasks/')) return { data: { request_id: requestId, member_id: memberId, task_type: taskType,
      thread_id: threadId, agent_slug: 'health-blood-glucose', request_status: 'dispatched', execution_status: 'running', run_id: runId } }
    return fixtureBase(options)
  } })
  await h.flow.open(memberId, taskType); await h.flow.createEntry(); await h.flow.submit('进度')
  subscriptions.at(-1).onEvent({ id: '123-0', type: 'message', runId })
  assert.equal(h.flow.getState().result, null)
  h.flow.hide(); await h.flow.open(memberId, taskType)
  assert.equal(subscriptions.at(-1).cursor, '123-0')
  subscriptions.at(-1).onError({ code: 403 })
  assert.equal(h.flow.getState().entry, null)
  assert.equal(h.saved.get(`health-task:${memberId}:${taskType}`), null)
})

test('cancel sends the running Run ID and a new queued question can be selected independently', async () => {
  const runId = '66666666-6666-4666-8666-666666666666', second = '55555555-5555-4555-8555-555555555555'
  let active = requestId, next = 0
  const h = fixture({ flow: { newId: () => [entryId, requestId, second][next++] }, send: async options => {
    if (options.path === '/api/agent/runs') { active = options.data.meta.request_id; return { data: { request_id: active, thread_id: threadId } } }
    if (options.path.endsWith('/cancel')) return { data: { status: 'cancel_requested' } }
    if (options.path.includes('/tasks/')) return { data: { request_id: options.path.split('/').at(-1), member_id: memberId, task_type: taskType,
      thread_id: threadId, agent_slug: 'health-blood-glucose', request_status: 'dispatched', execution_status: 'running', run_id: runId } }
    return fixtureBase(options)
  } })
  await h.flow.open(memberId, taskType); await h.flow.createEntry(); await h.flow.submit('原问题'); await h.flow.submit('追加问题')
  await h.flow.selectRequest(requestId); await h.flow.cancelRequest()
  assert.ok(h.calls.some(row => row.path === `/api/agent/runs/${runId}/cancel`))
  assert.equal(h.flow.getState().requestId, requestId)
  assert.deepEqual(h.flow.getState().requests.map(row => row.request_id), [requestId, second])
})


for(const code of ['budget_price_unavailable','budget_exceeded'])test(`terminal ${code} stops polling and keeps structured failure`,async()=>{
 const h=fixture({send:async options=>options.path.endsWith('/tasks/'+requestId)?{data:{request_id:requestId,member_id:memberId,task_type:taskType,thread_id:threadId,agent_slug:'health-blood-glucose',request_status:'dispatched',execution_status:'failed',result:{result_type:'error',code,retryable:false}}}:fixtureBase(options)})
 await h.flow.open(memberId,taskType);await h.flow.createEntry();await h.flow.submit('你好')
 assert.deepEqual(h.flow.getState().result,{type:'error',code,retryable:false});assert.equal(h.flow.getState().status,'failed')
 assert.equal(h.scheduled.length,0)
})

test('minified task entry keeps its task dictionary outside WeChat async local bindings', async () => {
  const compiler = createRequire(import.meta.resolve('vite'))
  const { rollup } = compiler('rollup'), { minify } = compiler('terser'), { parse } = compiler('@babel/parser')
  const source = readFileSync(new URL('../src/services/health-task-flow.js', import.meta.url), 'utf8')
  const bundle = await rollup({ input: 'task-entry', external: id => id !== 'task-entry', plugins: [{
    name: 'task-entry-source', resolveId: id => id === 'task-entry' ? id : null,
    load: id => id === 'task-entry' ? source : null,
  }] })
  try {
    const generated = await bundle.generate({ format: 'cjs', generatedCode: { constBindings: true } })
    const compressed = await minify(generated.output[0].code, { module: true })
    const ast = parse(compressed.code, { sourceType: 'script' })
    const isFunction = node => /Function/.test(node.type)
    const walk = (node, visit, parents = []) => {
      if (!node || typeof node !== 'object') return
      if (visit(node, parents) === false) return
      for (const value of Object.values(node)) {
        if (Array.isArray(value)) value.forEach(child => walk(child, visit, [...parents, node]))
        else if (value && typeof value === 'object') walk(value, visit, [...parents, node])
      }
    }
    let entry, dictionary
    walk(ast, (node, parents) => {
      if (node.type === 'CallExpression' && node.callee.type === 'MemberExpression' && node.callee.property.name === 'call' &&
          node.callee.object.type === 'MemberExpression' && node.callee.object.property.name === 'hasOwnProperty') {
        entry = parents.findLast(isFunction); dictionary = node.arguments[0].name
      }
    })
    assert.ok(entry && dictionary, 'the real task-type validation must remain in the compiled entry')
    const locals = []
    walk(entry.body, node => {
      if (isFunction(node)) return false
      if (node.type === 'VariableDeclarator') walk(node.id, binding => { if (binding.type === 'Identifier') locals.push(binding.name) })
    })
    assert.equal(locals.includes(dictionary), false,
      'WeChat regenerator hoists block locals; they must not shadow the task dictionary used before the first await')
  } finally { await bundle.close() }
})

function recoveringTask({pollLimit=2,loseSubmit=false}={}) {
  const timers=new Map(),listeners=new Set(),delays=[],emitted=[]
  let sequence=0,answer=false,failure=null
  const taskData=()=>({request_id:requestId,member_id:memberId,task_type:taskType,
    thread_id:threadId,agent_slug:'health-blood-glucose',request_status:'dispatched',
    execution_status:answer?'completed':'running',result:answer?{
      result_type:'general_education_answer',scope:'general_education',answer:'合成回复',citations:[]}:null})
  const h=fixture({flow:{pollLimit,subscribe:()=>()=>{},onChange:s=>emitted.push(s),
    schedule:(fn,ms)=>{const key=++sequence;timers.set(key,fn);delays.push(ms);return key},
    cancel:key=>timers.delete(key),watchNetwork:fn=>{listeners.add(fn);return ()=>listeners.delete(fn)}},
    send:async options=>{
      if(options.path.includes('/tasks/')) {
        if(failure)throw Object.assign(new Error('synthetic read failure'),{code:failure})
        return {data:taskData()}
      }
      if(loseSubmit&&options.path==='/api/agent/runs')throw Object.assign(new Error('synthetic lost response'),{code:'NETWORK_ERROR'})
      return fixtureBase(options)
    }})
  return {...h,timers,listeners,delays,emitted,
    async start(){await h.flow.open(memberId,taskType);await h.flow.createEntry();await h.flow.submit('合成问题')},
    async tick(){const [key,fn]=timers.entries().next().value;timers.delete(key);fn();await new Promise(r=>setImmediate(r))},
    async online(){for(const fn of [...listeners])fn();await new Promise(r=>setImmediate(r))},
    fail(code){failure=code},complete(){answer=true;failure=null}}
}

test('long tasks continue at a capped lower frequency and clear waiting notices on completion',async()=>{
  const h=recoveringTask();await h.start()
  for(let i=0;i<8;i++)await h.tick()
  assert.equal(h.timers.size,1);assert.equal(h.listeners.size,1)
  assert.ok(h.delays.at(-1)>2000);assert.ok(h.delays.every(ms=>ms<=30000))
  assert.match(h.flow.getState().notice,/自动获取/)
  h.complete();await h.tick()
  assert.equal(h.flow.getState().result.text,'合成回复')
  assert.equal(h.flow.getState().notice,'');assert.equal(h.flow.getState().error,'')
  assert.equal(h.timers.size,0);assert.equal(h.listeners.size,0)
  assert.equal(h.calls.filter(c=>c.path==='/api/agent/runs').length,1)
  assert.equal(h.emitted.at(-1).notice,'');h.flow.hide()
})

for(const code of ['NETWORK_ERROR',503])test(`temporary ${code} read failures back off and recover the original task without resubmitting`,async()=>{
  const h=recoveringTask({pollLimit:100});await h.start();h.fail(code)
  await h.tick();const first=h.delays.at(-1);await h.tick()
  assert.ok(first>2000);assert.ok(h.delays.at(-1)>first)
  assert.equal(h.timers.size,1);assert.match(h.flow.getState().error,/自动重试/)
  h.complete();await h.tick()
  assert.equal(h.flow.getState().requestId,requestId)
  assert.equal(h.flow.getState().result.text,'合成回复');assert.equal(h.flow.getState().error,'')
  assert.equal(h.calls.filter(c=>c.path==='/api/agent/runs').length,1);h.flow.hide()
})

test('connectivity restoration reads immediately and removes the pending delayed read',async()=>{
  const h=recoveringTask();await h.start();h.fail('NETWORK_ERROR');await h.tick()
  const before=h.calls.length;h.complete();await h.online()
  assert.equal(h.calls.length,before+1);assert.equal(h.calls.at(-1).method,undefined)
  assert.equal(h.flow.getState().result.text,'合成回复')
  assert.equal(h.timers.size,0);assert.equal(h.listeners.size,0);h.flow.hide()
})

test('an accepted submit stays pending when its first result read fails and recovers without another submit',async()=>{
  const h=recoveringTask();h.fail(503);await h.start()
  assert.equal(h.flow.getState().submitUnknown,false)
  assert.equal(h.flow.getState().status,'queued');assert.equal(h.timers.size,1)
  h.complete();await h.tick()
  assert.equal(h.flow.getState().result.text,'合成回复')
  assert.equal(h.calls.filter(c=>c.path==='/api/agent/runs').length,1);h.flow.hide()
})

test('lost submit responses are confirmed automatically with the same request key and preserve explicit retry until confirmed',async()=>{
  const h=recoveringTask({loseSubmit:true});await h.start();h.fail(404)
  assert.equal(h.flow.getState().canRetry,true);assert.equal(h.timers.size,1)
  await h.tick();assert.equal(h.flow.getState().canRetry,true)
  assert.equal(h.flow.getState().requestId,requestId);assert.equal(h.timers.size,1)
  h.complete();await h.tick()
  assert.equal(h.flow.getState().canRetry,false);assert.equal(h.flow.getState().result.text,'合成回复')
  assert.equal(h.saved.get(`health-task:${memberId}:${taskType}`).pendingQuery,'')
  assert.equal(h.calls.filter(c=>c.path==='/api/agent/runs').length,1);h.flow.hide()
})

for(const code of [401,403,404,409,410,'TASK_MISMATCH'])test(`read failure ${code} stops recovery and clears inaccessible task state`,async()=>{
  const h=recoveringTask();await h.start();h.fail(code);await h.tick()
  assert.equal(h.flow.getState().requestId,'');assert.equal(h.flow.getState().result,null)
  assert.equal(h.timers.size,0);assert.equal(h.listeners.size,0);h.flow.hide()
})

for(const action of ['pause','hide','account'])test(`${action} prevents stale recovery callbacks from reading the previous task`,async()=>{
  const h=recoveringTask();await h.start()
  const timer=[...h.timers.values()][0],online=[...h.listeners][0]
  if(action==='account')h.setAccount({accountId:'other',token:'synthetic-other'})
  else h.flow[action]()
  const before=h.calls.length;timer();online();await new Promise(r=>setImmediate(r))
  assert.equal(h.calls.length,before)
  if(action!=='account'){assert.equal(h.timers.size,0);assert.equal(h.listeners.size,0)}
  h.flow.hide()
})

for(const code of ['NETWORK_ERROR',503])test(`unknown submission survives a transient ${code} task read and recovers automatically without another POST`,async()=>{
 const h=recoveringTask({loseSubmit:true});h.fail(code);await h.start()
 assert.equal(h.flow.getState().submitUnknown,true);assert.equal(h.timers.size,1)
 await h.tick()
 assert.equal(h.flow.getState().submitUnknown,true);assert.equal(h.timers.size,1)
 h.complete();await h.tick()
 assert.equal(h.flow.getState().submitUnknown,false)
 assert.equal(h.flow.getState().requestId,requestId)
 assert.equal(h.flow.getState().result.text,'合成回复')
 assert.equal(h.calls.filter(c=>c.path==='/api/agent/runs').length,1)
 assert.equal(h.timers.size,0);assert.equal(h.listeners.size,0);h.flow.hide()
})
