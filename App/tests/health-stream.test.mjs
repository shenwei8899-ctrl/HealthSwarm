import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createHealthEventParser, subscribeHealthEvents } from '../src/services/health-events.js'
import { createHealthTaskFlow } from '../src/services/health-task-flow.js'

const memberId = '11111111-1111-4111-8111-111111111111'
const entryId = '22222222-2222-4222-8222-222222222222'
const requestId = '33333333-3333-4333-8333-333333333333'
const threadId = '44444444-4444-4444-8444-444444444444'
const runId = '55555555-5555-4555-8555-555555555555'
const tick = () => new Promise(resolve => setImmediate(resolve))
const delta = (content, offset = 0, id = '10-0', extra = {}) => ({ id, type: 'custom', runId, requestId, threadId,
  phase: 'streaming', messageId: 'answer-1', offset, content, ...extra })
function fixture() {
  let account = { accountId: '17', token: 'test-session' }, revision = '1', status = 'running', reads = 0, readError = null
  const subscriptions = [], timers = [], saved = new Map(), snapshots = []
  const storage = { getStorageSync: key => saved.get(key), setStorageSync: (key, value) => saved.set(key, structuredClone(value)) }
  const flow = createHealthTaskFlow({ session: () => account, revision: () => revision, storage,
    onChange: value => snapshots.push(value), newId: (() => { const ids = [entryId, requestId]; return () => ids.shift() })(),
    schedule: fn => { const handle = { fn }; timers.push(handle); return handle }, cancel: handle => { handle.cancelled = true },
    subscribe: options => { const subscription = { ...options, closed: false }; subscriptions.push(subscription); return () => { subscription.closed = true } },
    send: async options => {
      if (options.path.endsWith('/members')) return { data: [{ id: memberId, is_owner: true }] }
      if (options.path.endsWith('/readiness')) return { data: { capabilities: { member_id: memberId }, entries: [{ entry_type: 'consultation', status: 'available' }] } }
      if (options.path.endsWith('/task-entries')) return { data: { member_id: memberId, task_type: 'consultation', client_request_id: entryId,
        entry_status: 'ready', thread_id: threadId, agent_slug: 'health-consultation', request_submit_url: '/api/agent/runs' } }
      if (options.path === '/api/agent/runs') return { data: { request_id: requestId, thread_id: threadId } }
      if (options.path.endsWith('/cancel')) { status = 'cancelled'; return { data: { status } } }
      if (options.path.includes('/tasks/')) {
        reads++
        if (readError) { const error = readError; readError = null; throw error }
        return { data: { request_id: requestId, member_id: memberId, task_type: 'consultation', thread_id: threadId,
          agent_slug: 'health-consultation', run_id: runId, request_status: 'dispatched', execution_status: status,
          result: status === 'completed' ? { result_type: 'general_education_answer', scope: 'general_education', answer: '正式结果', citations: [] }
            : status === 'failed' ? { result_type: 'error', code: 'output_persistence_error', retryable: false } : null } }
      }
      throw new Error('Unexpected path ' + options.path)
    } })
  return { flow, subscriptions, saved, snapshots,
    setStatus: value => { status = value }, reads: () => reads, failNextRead: error => { readError = error },
    switchAccount: () => { account = { accountId: '18', token: 'other' }; revision = '2' },
    poll: async () => { const handle = timers.find(row => !row.cancelled && !row.used); assert.ok(handle); handle.used = true; handle.fn(); await tick() } }
}
async function start(h) { await h.flow.open(memberId, 'consultation'); await h.flow.createEntry(); await h.flow.submit('今天怎样吃？') }

test('SSE parses fragmented Chinese public deltas and progress while filtering raw model/reasoning text', () => {
  const events = [], parse = createHealthEventParser(event => events.push(event))
  const frame = (id, event, data) => `id: ${id}\r\nevent: ${event}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`
  const raw = new TextEncoder().encode(frame('10-0', 'custom', { run_id: runId, request_id: requestId, thread_id: threadId,
    payload: { name: 'yuxi.health_answer_delta', chunk: { content: '早餐建议。', offset: 0, message_id: 'answer-1', reasoning_content: '不可显示' } } }) +
    frame('11-0', 'messages', { run_id: runId, payload: { chunk: { stream_event: { type: 'message_delta', content: '原始模型不可显示' } } } }) +
    frame('12-0', 'custom', { run_id: runId, payload: { name: 'yuxi.health_progress', chunk: { phase: 'validating', message: '自由文案不可显示' } } }))
  for (let i = 0; i < raw.length; i += 2) parse(raw.slice(i, i + 2).buffer)
  assert.equal(events[0].content, '早餐建议。')
  assert.equal(events[0].offset, 0)
  assert.equal(events[0].messageId, 'answer-1')
  assert.equal(events[2].phase, 'validating')
  assert.equal(JSON.stringify(events).includes('不可显示'), false)
})

test('public deltas appear before task completion, deduplicate replay and yield to the formal business result', async () => {
  const h = fixture(); await start(h)
  const stream = h.subscriptions.at(-1), reads = h.reads()
  stream.onEvent(delta('早餐建议。'))
  assert.equal(h.flow.getState().streamText, '早餐建议。')
  assert.equal(h.flow.getState().result, null)
  assert.equal(h.reads(), reads, 'delivery must not wait for a final task read')
  stream.onEvent(delta('早餐建议。'))
  stream.onEvent(delta('早餐建议。', 0, '10-1'))
  stream.onEvent(delta('适量搭配。', 5, '11-0'))
  assert.equal(h.flow.getState().streamText, '早餐建议。适量搭配。')
  assert.equal(JSON.stringify([...h.saved.values()]).includes('早餐建议'), false)
  h.setStatus('completed'); stream.onEvent({ type: 'end', requestId, runId, threadId }); await tick()
  assert.equal(h.flow.getState().result.text, '正式结果')
  assert.equal(h.flow.getState().streamText, '')
  assert.equal(stream.closed, true)
})

test('disconnect resumes from the latest cursor, ignores old connection callbacks and preserves received text', async () => {
  const h = fixture(); await start(h)
  const first = h.subscriptions.at(-1)
  first.onEvent(delta('先收到。')); first.onError(new Error('断网'))
  assert.equal(h.flow.getState().streamPhase, 'reconnecting')
  first.onEvent(delta('断流后的迟到内容', 4, '11-0'))
  assert.equal(h.flow.getState().streamText, '先收到。')
  await h.poll()
  const second = h.subscriptions.at(-1)
  assert.notEqual(second, first)
  assert.equal(second.cursor, '10-0')
  first.onEvent(delta('旧连接不应出现', 4, '11-0'))
  second.onEvent(delta('继续。', 4, '12-0'))
  assert.equal(h.flow.getState().streamText, '先收到。继续。')
})

test('a temporary task-read failure keeps polling the accepted request and recovers the same stream', async () => {
  const h = fixture(); await start(h)
  const first = h.subscriptions.at(-1)
  first.onEvent(delta('已收到。')); first.onError(new Error('断网'))
  h.failNextRead(Object.assign(new Error('暂时断网'), { code: 'NETWORK_ERROR' }))
  await h.poll()
  assert.equal(h.flow.getState().streamText, '已收到。')
  assert.equal(h.flow.getState().streamPhase, 'reconnecting')
  await h.poll()
  assert.equal(h.subscriptions.at(-1).cursor, '10-0')
  h.subscriptions.at(-1).onEvent(delta('恢复。', 4, '11-0'))
  assert.equal(h.flow.getState().streamText, '已收到。恢复。')
})

test('a missing offset replays from zero and a new message ID resets the previous model message', async () => {
  const h = fixture(); await start(h)
  const first = h.subscriptions.at(-1)
  first.onEvent(delta('首段。'))
  first.onEvent(delta('缺段后的文本', 99, '11-0'))
  assert.equal(h.flow.getState().streamText, '')
  assert.equal(first.closed, true)
  await h.poll()
  const second = h.subscriptions.at(-1)
  assert.equal(second.cursor, '0-0')
  second.onEvent(delta('首段。')); second.onEvent(delta('下段。', 3, '12-0'))
  second.onEvent(delta('新答复。', 0, '13-0', { messageId: 'answer-2' }))
  assert.equal(h.flow.getState().streamText, '新答复。')
})

test('stream offsets count Unicode characters consistently with Python when an answer includes emoji', async () => {
  const h = fixture(); await start(h)
  const stream = h.subscriptions.at(-1)
  stream.onEvent(delta('🥗早餐。'))
  stream.onEvent(delta('午餐。', 4, '11-0'))
  assert.equal(h.flow.getState().streamText, '🥗早餐。午餐。')
  assert.equal(h.flow.getState().streamOffset, 7)
})

test('failure, cancellation, leaving and account changes never retain or append stale private preview', async () => {
  for (const action of ['failure', 'cancel', 'hide', 'account', 'permission']) {
    const h = fixture(); await start(h)
    const stream = h.subscriptions.at(-1); stream.onEvent(delta('临时内容。'))
    if (action === 'failure') { h.setStatus('failed'); await h.flow.refresh() }
    if (action === 'cancel') await h.flow.cancelRequest()
    if (action === 'hide') h.flow.hide()
    if (action === 'account') { h.switchAccount(); h.flow.hide() }
    if (action === 'permission') stream.onError({ code: 403 })
    stream.onEvent(delta('迟到内容', 5, '99-0'))
    assert.equal(h.flow.getState().streamText, '', action)
    assert.equal(stream.closed, true, action)
  }
})

test('a public validation error clears the preview immediately before the task read completes', async () => {
  const h = fixture(); await start(h)
  const stream = h.subscriptions.at(-1); stream.onEvent(delta('临时内容。'))
  stream.onEvent({ type: 'error', requestId, runId, threadId })
  assert.equal(h.flow.getState().streamText, '')
  await tick()
})

test('mismatched request/run/thread identities cannot publish text', async () => {
  const h = fixture(); await start(h)
  const stream = h.subscriptions.at(-1)
  for (const field of ['requestId', 'runId', 'threadId']) stream.onEvent(delta('不应出现。', 0, '10-0', { [field]: 'other' }))
  stream.onEvent(delta('不应出现。', 0, '10-0', { requestId: undefined }))
  assert.equal(h.flow.getState().streamText, '')
})

test('H5 response reader publishes the first public frame while the HTTP response remains open', async () => {
  const original = { window: globalThis.window, uni: globalThis.uni, fetch: globalThis.fetch }
  const values = new Map([['fn-session-v2:mock', { accountId: '17', token: 'synthetic', clientRevision: 'one' }]])
  let controller, aborted = false
  globalThis.window = {}
  globalThis.uni = { getStorageSync: key => values.get(key) }
  globalThis.fetch = async (_url, options) => {
    options.signal.addEventListener('abort', () => { aborted = true })
    return { ok: true, body: new ReadableStream({ start(value) { controller = value } }) }
  }
  try {
    const events = []
    const close = subscribeHealthEvents({ requestId, runId, onEvent: value => events.push(value) })
    await tick()
    controller.enqueue(new TextEncoder().encode(`id: 1-0\nevent: custom\ndata: ${JSON.stringify({ run_id: runId, request_id: requestId, thread_id: threadId,
      payload: { name: 'yuxi.health_answer_delta', chunk: { content: '首个句子。', offset: 0, message_id: 'answer-1' } } })}\n\n`))
    await tick()
    assert.equal(events[0].content, '首个句子。')
    close(); assert.equal(aborted, true)
    controller.close(); await tick()
  } finally {
    for (const [key, value] of Object.entries(original)) { if (value === undefined) delete globalThis[key]; else globalThis[key] = value }
  }
})

test('WeChat chunk adapter delivers public Chinese frames before request success and ignores switched-session chunks', () => {
  let options, receive, aborted = false, revision = 'one'
  const native = { request(value) { options = value; return { onChunkReceived(callback) { receive = callback }, abort() { aborted = true } } } }
  // 与组件测试相同的依赖注入方式：执行真实适配器源码，仅替换平台和配置入口。
  const source = readFileSync(new URL('../src/services/health-events.js', import.meta.url), 'utf8')
    .replace(/^import .*$/gm, '').replace(/^export /gm, '')
  const subscribe = new Function('uni', 'window', 'fetch', 'apiBaseUrl', 'allowLocalHealthApi', 'getSession', 'sessionRevision',
    source + ';return subscribeHealthEvents')(native, undefined, undefined, 'https://nutrition.example', false,
    () => ({ token: 'synthetic' }), () => revision)
  const events = [], close = subscribe({ requestId, runId, cursor: '9-0', onEvent: event => events.push(event) })
  assert.equal(options.enableChunked, true)
  assert.equal(options.responseType, 'arraybuffer')
  assert.equal(options.header.Authorization, 'Bearer synthetic')
  assert.match(options.url, /after_seq=9-0/)
  const bytes = new TextEncoder().encode(`id: 10-0\nevent: custom\ndata: ${JSON.stringify({ run_id: runId, request_id: requestId, thread_id: threadId,
    payload: { name: 'yuxi.health_answer_delta', chunk: { content: '微信实时首段。', offset: 0, message_id: 'answer-1' } } })}\n\n`)
  for (let i = 0; i < bytes.length; i += 3) receive({ data: bytes.slice(i, i + 3).buffer })
  assert.equal(events[0].content, '微信实时首段。', 'request success has not fired yet')
  revision = 'two'; receive({ data: bytes.buffer })
  assert.equal(events.length, 1)
  close(); assert.equal(aborted, true)
})
