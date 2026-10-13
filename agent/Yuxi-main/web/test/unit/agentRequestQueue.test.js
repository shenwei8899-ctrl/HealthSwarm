import assert from 'node:assert/strict'
import path from 'node:path'
import { after, before, test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { readFileSync } from 'node:fs'
import { compileScript, parse } from 'vue/compiler-sfc'
import { createPinia, setActivePinia } from 'pinia'
import { reactive, isProxy, ref } from 'vue'

import { createServer } from 'vite'

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
let server
let agentApi
let useAgentRequestQueue
let useAgentRunStream
let dispatchRunEventChunks
let useAgentStreamHandler
let useAgentThreadState
let MessageProcessor
let ErrorHandler
let useUserStore
let getConversationDisplayItems
let groupConversationContinuations

before(async () => {
  const storage = new Map()
  globalThis.localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: (key) => storage.delete(key)
  }
  server = await createServer({ root: webRoot, server: { middlewareMode: true } })
  ;({ agentApi } = await server.ssrLoadModule('/src/apis/index.js'))
  ;({ ErrorHandler } = await server.ssrLoadModule('/src/utils/errorHandler.js'))
  ;({ useUserStore } = await server.ssrLoadModule('/src/stores/user.js'))
  ;({ useAgentRequestQueue } = await server.ssrLoadModule(
    '/src/composables/useAgentRequestQueue.js'
  ))
  ;({ useAgentRunStream, dispatchRunEventChunks } = await server.ssrLoadModule(
    '/src/composables/useAgentRunStream.js'
  ))
  ;({ useAgentStreamHandler } = await server.ssrLoadModule(
    '/src/composables/useAgentStreamHandler.js'
  ))
  ;({ useAgentThreadState } = await server.ssrLoadModule('/src/composables/useAgentThreadState.js'))
  ;({ default: MessageProcessor } = await server.ssrLoadModule('/src/utils/messageProcessor.js'))
  ;({ getConversationDisplayItems } = await server.ssrLoadModule('/src/utils/messageGrouping.js'))
  ;({ groupConversationContinuations } = await server.ssrLoadModule(
    '/src/utils/conversationProcessGrouping.js'
  ))
})

after(async () => {
  await server?.close()
  delete globalThis.localStorage
})

/** 只保留与 Request 恢复有关的线程投影。 */
function recoveryThread() {
  return {
    activeRunId: null,
    isStreaming: false,
    pendingRequestId: null,
    replyLoadingVisible: false,
    queuedRequests: [{ request_id: 'request-recovery', status: 'queued' }],
    requestStreams: {},
    onGoingConv: { msgChunks: {} }
  }
}

/** 构造同请求同线程的数据库状态，不借用相邻 Run。 */
const recoveryRequest = (status = 'dispatched') => ({
  request: {
    request_id: 'request-recovery', thread_id: 'thread-recovery', status,
    dispatched_run_id: status === 'dispatched' ? 'run-recovery' : null
  }
})

/** 等待当前异步帧完成，不推进恢复退避计时器。 */
async function settleRecovery() {
  for (let i = 0; i < 12; i++) await Promise.resolve()
}

for (const failure of ['eof', 'network']) {
  test(`Request ${failure} 后回读同请求的 PG 派发结果，不重新提交`, async (t) => {
    const ts = recoveryThread(), starts = [], reads = []
    t.mock.method(agentApi, 'streamRequestEvents', async () => {
      if (failure === 'network') throw new TypeError('offline')
      return new Response('')
    })
    t.mock.method(agentApi, 'getRequest', async (id) => {
      reads.push(id)
      return recoveryRequest()
    })
    t.mock.method(agentApi, 'createAgentRun', () => assert.fail('恢复不得重新提交正文'))
    const queue = useAgentRequestQueue({
      getThreadState: () => ts,
      resetOnGoingConv: () => {},
      startRunStream: (...args) => starts.push(args)
    })
    await queue.startRequestStream('thread-recovery', 'request-recovery')
    assert.deepEqual(reads, ['request-recovery'])
    assert.deepEqual(starts, [['thread-recovery', 'run-recovery', '0-0', { requestId: 'request-recovery' }]])
    assert.deepEqual(ts.queuedRequests, [])
    assert.equal(ts.requestStreams['request-recovery'], undefined)
  })
}

test('Request 仍排队时退避后重订阅，派发只交接一次', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const ts = recoveryThread(), starts = []
  let subscriptions = 0, reads = 0
  t.mock.method(agentApi, 'streamRequestEvents', async () => {
    subscriptions++
    return new Response(subscriptions === 1 ? '' : 'event: run_created\ndata: {"request_id":"request-recovery","run_id":"run-recovery"}\n\n')
  })
  t.mock.method(agentApi, 'getRequest', async () => { reads++; return recoveryRequest('queued') })
  const queue = useAgentRequestQueue({
    getThreadState: () => ts, resetOnGoingConv: () => {}, startRunStream: (...args) => starts.push(args)
  })
  const pending = queue.startRequestStream('thread-recovery', 'request-recovery')
  await settleRecovery()
  assert.equal(reads, 1)
  t.mock.timers.tick(499)
  await settleRecovery()
  assert.equal(subscriptions, 1)
  t.mock.timers.tick(1)
  await pending
  assert.equal(subscriptions, 2)
  assert.equal(starts.length, 1)
  assert.equal(ts.requestStreams['request-recovery'], undefined)
})

for (const status of ['failed', 'cancelled', 'rejected']) {
  test(`排队请求 ${status} 不清理另一个 active Run`, async (t) => {
    const ts = recoveryThread()
    Object.assign(ts, { activeRunId: 'run-active', isStreaming: true, pendingRequestId: 'request-active', replyLoadingVisible: true })
    ts.onGoingConv.msgChunks = { 'request-active': [{ content: 'current' }], 'request-recovery': [{ content: 'queued' }] }
    t.mock.method(agentApi, 'streamRequestEvents', async () => new Response(`event: ${status}\ndata: {"request_id":"request-recovery"}\n\n`))
    t.mock.method(agentApi, 'getRequest', () => assert.fail('已收到终态不再次恢复'))
    const queue = useAgentRequestQueue({ getThreadState: () => ts })
    await queue.startRequestStream('thread-recovery', 'request-recovery')
    assert.equal(ts.activeRunId, 'run-active')
    assert.equal(ts.isStreaming, true)
    assert.equal(ts.pendingRequestId, 'request-active')
    assert.equal(ts.replyLoadingVisible, true)
    assert.deepEqual(ts.onGoingConv.msgChunks['request-active'], [{ content: 'current' }])
    assert.equal(ts.onGoingConv.msgChunks['request-recovery'], undefined)
  })
}

for (const status of [401, 403, 404, 409, 410]) {
  test(`恢复查询 ${status} 后停止订阅并清除该请求私有投影`, async (t) => {
    t.mock.method(ErrorHandler, 'handleError', () => {})
    const ts = recoveryThread()
    ts.onGoingConv.msgChunks['request-recovery'] = [{ content: 'private queued text' }]
    t.mock.method(agentApi, 'streamRequestEvents', async () => new Response(''))
    t.mock.method(agentApi, 'getRequest', async () => { throw Object.assign(new Error('unavailable'), { status }) })
    const queue = useAgentRequestQueue({ getThreadState: () => ts })
    await queue.startRequestStream('thread-recovery', 'request-recovery')
    assert.deepEqual(ts.queuedRequests, [])
    assert.deepEqual(ts.onGoingConv.msgChunks, {})
    assert.equal(ts.requestStreams['request-recovery'], undefined)
    assert.equal(agentApi.streamRequestEvents.mock.callCount(), 1)
  })
}

for (const field of ['request_id', 'thread_id']) {
  test(`PG 恢复的 ${field} 错绑时不订阅相邻 Run`, async (t) => {
    t.mock.method(ErrorHandler, 'handleError', () => {})
    const ts = recoveryThread(), starts = [], errors = []
    t.mock.method(agentApi, 'streamRequestEvents', async () => new Response(''))
    t.mock.method(agentApi, 'getRequest', async () => {
      const data = recoveryRequest()
      data.request[field] = 'neighbor'
      return data
    })
    const queue = useAgentRequestQueue({ getThreadState: () => ts, resetOnGoingConv: () => {}, startRunStream: (...args) => starts.push(args), onStreamError: (...args) => errors.push(args) })
    await queue.startRequestStream('thread-recovery', 'request-recovery')
    assert.deepEqual(starts, [])
    assert.deepEqual(errors, [['thread-recovery', 'request-recovery', 'error']])
    assert.deepEqual(ts.queuedRequests, [])
    assert.equal(ts.requestStreams['request-recovery'], undefined)
  })
}

test('实际认证 GET 的 403 Error.status 可停止恢复并清除原请求', async (t) => {
  setActivePinia(createPinia())
  const user = useUserStore(), ts = recoveryThread(), requests = []
  user.token = 'synthetic-test-session'
  t.after(() => user.$dispose())
  t.mock.method(console, 'error', () => {})
  const notices = []
  t.mock.method(ErrorHandler, 'handleError', error => notices.push(error))
  t.mock.method(agentApi, 'streamRequestEvents', async () => new Response(''))
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    requests.push([url, options.method, !!options.headers.Authorization])
    return new Response(JSON.stringify({ detail: { code: 'not_found', message: '当前成员不可读取' } }), {
      status: 403, headers: { 'Content-Type': 'application/json' }
    })
  })
  const queue = useAgentRequestQueue({ getThreadState: () => ts })
  await queue.startRequestStream('thread-recovery', 'request-recovery')
  assert.deepEqual(requests, [['/api/agent/requests/request-recovery', 'GET', true]])
  assert.equal(notices[0].status, 403)
  assert.equal(notices[0].response.status, 403)
  assert.deepEqual(ts.queuedRequests, [])
  assert.equal(ts.requestStreams['request-recovery'], undefined)
})

test('连续连接失败只尝试六次，保留原请求并提示手动恢复', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const ts = recoveryThread(), notices = []
  t.mock.method(ErrorHandler, 'handleError', error => notices.push(error.message))
  t.mock.method(agentApi, 'streamRequestEvents', async () => { throw new TypeError('offline') })
  t.mock.method(agentApi, 'getRequest', async () => recoveryRequest('queued'))
  t.mock.method(agentApi, 'createAgentRun', () => assert.fail('不能重提'))
  const queue = useAgentRequestQueue({ getThreadState: () => ts })
  const pending = queue.startRequestStream('thread-recovery', 'request-recovery')
  await settleRecovery()
  for (const delay of [500, 1000, 2000, 4000, 5000]) {
    const calls = agentApi.streamRequestEvents.mock.callCount()
    t.mock.timers.tick(delay - 1)
    await settleRecovery()
    assert.equal(agentApi.streamRequestEvents.mock.callCount(), calls)
    t.mock.timers.tick(1)
    await settleRecovery()
  }
  await pending
  assert.equal(agentApi.streamRequestEvents.mock.callCount(), 6)
  assert.equal(agentApi.getRequest.mock.callCount(), 6)
  assert.deepEqual(ts.queuedRequests, [{ request_id: 'request-recovery', status: 'queued' }])
  assert.equal(ts.requestStreams['request-recovery'], undefined)
  assert.match(notices[0], /重新进入会话恢复原请求/)
  t.mock.timers.tick(100000)
  await settleRecovery()
  assert.equal(agentApi.streamRequestEvents.mock.callCount(), 6)
})

test('成功 queued 帧重置失败计数，继续恢复且不突破退避上限', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const ts = recoveryThread(), starts = []
  let subscriptions = 0
  t.mock.method(agentApi, 'streamRequestEvents', async () => {
    subscriptions++
    return new Response(subscriptions <= 5 ? '' : subscriptions === 6
      ? 'event: queued\ndata: {"position":2}\n\n'
      : 'event: run_created\ndata: {"run_id":"run-recovery"}\n\n')
  })
  t.mock.method(agentApi, 'getRequest', async () => recoveryRequest('queued'))
  t.mock.method(ErrorHandler, 'handleError', error => assert.fail(error.message))
  const queue = useAgentRequestQueue({ getThreadState: () => ts, resetOnGoingConv: () => {}, startRunStream: (...args) => starts.push(args) })
  const pending = queue.startRequestStream('thread-recovery', 'request-recovery')
  await settleRecovery()
  for (const delay of [500, 1000, 2000, 4000, 5000]) {
    t.mock.timers.tick(delay)
    await settleRecovery()
  }
  assert.equal(subscriptions, 6)
  assert.equal(ts.queuedRequests[0].queue_position, 2)
  t.mock.timers.tick(499)
  await settleRecovery()
  assert.equal(subscriptions, 6)
  t.mock.timers.tick(1)
  await pending
  assert.equal(subscriptions, 7)
  assert.equal(starts.length, 1)
})

test('停止订阅会清除退避定时器，不再回读或重连', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  t.mock.method(globalThis, 'clearTimeout')
  const ts = recoveryThread()
  t.mock.method(agentApi, 'streamRequestEvents', async () => new Response(''))
  t.mock.method(agentApi, 'getRequest', async () => recoveryRequest('queued'))
  const queue = useAgentRequestQueue({ getThreadState: () => ts })
  const pending = queue.startRequestStream('thread-recovery', 'request-recovery')
  await settleRecovery()
  const entry = ts.requestStreams['request-recovery']
  assert.notEqual(entry.reconnectTimer, null)
  const timer = entry.reconnectTimer
  queue.stopAllRequestStreams('thread-recovery')
  await pending
  assert.equal(entry.reconnectTimer, null)
  assert.ok(clearTimeout.mock.calls.some(call => call.arguments[0] === timer))
  assert.equal(entry.controller.signal.aborted, true)
  t.mock.timers.tick(100000)
  await settleRecovery()
  assert.equal(agentApi.streamRequestEvents.mock.callCount(), 1)
  assert.equal(agentApi.getRequest.mock.callCount(), 1)
})

for (const stale of ['abort', 'replacement']) {
  test(`${stale} 后迟到的 PG 恢复响应不能启动旧 Run 或清理新投影`, async (t) => {
    const ts = recoveryThread(), late = Promise.withResolvers(), starts = []
    t.mock.method(agentApi, 'streamRequestEvents', async () => new Response(''))
    t.mock.method(agentApi, 'getRequest', () => late.promise)
    const queue = useAgentRequestQueue({ getThreadState: () => ts, resetOnGoingConv: () => {}, startRunStream: (...args) => starts.push(args) })
    const pending = queue.startRequestStream('thread-recovery', 'request-recovery')
    await settleRecovery()
    assert.equal(agentApi.getRequest.mock.callCount(), 1)
    let replacement
    if (stale === 'abort') queue.stopAllRequestStreams('thread-recovery')
    else {
      replacement = { controller: new AbortController() }
      ts.requestStreams['request-recovery'] = replacement
    }
    ts.queuedRequests = [{ request_id: 'new-request', status: 'queued' }]
    late.resolve(recoveryRequest())
    await pending
    assert.deepEqual(ts.queuedRequests, [{ request_id: 'new-request', status: 'queued' }])
    assert.deepEqual(starts, [])
    assert.equal(ts.pendingRequestId, null)
    assert.equal(ts.requestStreams['request-recovery'], replacement)
  })
}

/** 从真实组件编译 AST 取恢复动作，证明实际装配顺序。 */
function chatRecoveryAction(name, deps) {
  const source = readFileSync(new URL('../../src/components/AgentChatComponent.vue', import.meta.url), 'utf8')
  const { descriptor } = parse(source)
  const { scriptSetupAst } = compileScript(descriptor, { id: 'request-recovery-order' })
  const node = scriptSetupAst.find(node => node.type === 'VariableDeclaration' && node.declarations.some(item => item.id.name === name))
  assert.ok(node, name)
  return new Function(...Object.keys(deps), descriptor.scriptSetup.content.slice(node.start, node.end) + `; return ${name}`)(...Object.values(deps))
}

for (const action of ['resumeCurrentRunForVisiblePage', 'selectChat']) {
  test(`${action} 在 Run 流结束前已恢复排队 Request`, async () => {
    const running = Promise.withResolvers(), calls = []
    const deps = {
      currentChatId: { value: 'thread-recovery' }, currentThreadId: { value: 'thread-recovery' },
      currentAgentId: { value: 'health-consultation' }, threadCreationInFlight: { value: false },
      threadSelectionVersion: 0, userStore: { uid: 'synthetic-user', isLoggedIn: true }, initializedThreadId: { value: '' },
      threads: { value: [{ id: 'thread-recovery', agent_id: 'health-consultation' }] }, props: { singleMode: true },
      AgentValidator: { validateAgentIdWithError: () => true }, handleValidationError: assert.fail,
      withConfigNoticeSync: async callback => callback(), setCurrentThreadId: () => {}, syncThreadConfigSnapshot: () => {},
      chatUIStore: {}, fetchThreadMessages: async () => {}, chatThreadsStore: { markThreadViewed: () => {} },
      nextTick: async () => {}, scrollController: { scrollToBottomStaticForce: async () => {} },
      handleAgentStateRefresh: async () => {}, fetchAgentState: async () => {}, fetchThreadAttachments: async () => {}, handleChatError: assert.fail,
      resolveAgentSlugForThread: () => 'health-consultation',
      resumeActiveRunForThread: (_id, options) => { calls.push('run'); return options?.background ? undefined : running.promise },
      resumeQueuedRequests: async () => calls.push('requests'), restorePendingInterruptForThread: () => calls.push('interrupt')
    }
    const pending = chatRecoveryAction(action, deps)('thread-recovery')
    await settleRecovery()
    assert.deepEqual(calls, action === 'selectChat' ? ['run', 'requests', 'interrupt'] : ['run', 'requests'])
    running.resolve()
    await pending
    assert.deepEqual(calls, ['run', 'requests', 'interrupt'])
  })
}

for (const recovery of ['snapshot', 'active', 'active-interrupted', 'open-interrupted']) {
  test(`${recovery} Run 恢复重放保留已并发订阅的 Request`, async (t) => {
    const active = Promise.withResolvers(), requestSignals = []
    const state = useAgentThreadState({ chatState: reactive({ threadStates: {} }), getCurrentThreadId: () => 'thread-recovery' })
    const ts = state.getThreadState('thread-recovery')
    ts.queuedRequests = [{ request_id: 'request-recovery', status: 'queued' }]
    if (recovery === 'snapshot') localStorage.setItem('active_run:thread-recovery', JSON.stringify({ run_id: 'run-active', created_at: Date.now() }))
    if (recovery === 'open-interrupted') {
      ts.activeRunId = 'run-active'
      ts.runStreamAbortController = new AbortController()
    }
    const response = signal => new Response(new ReadableStream({ start(controller) {
      signal.addEventListener('abort', () => controller.error(new DOMException('aborted', 'AbortError')), { once: true })
    } }))
    t.mock.method(agentApi, 'streamRequestEvents', async (_id, { signal }) => { requestSignals.push(signal); return response(signal) })
    t.mock.method(agentApi, 'streamAgentRunEvents', async (_id, _cursor, { signal }) => response(signal))
    t.mock.method(agentApi, 'listThreadQueuedRequests', async () => ({ requests: ts.queuedRequests }))
    t.mock.method(agentApi, recovery === 'snapshot' || recovery === 'open-interrupted' ? 'getAgentRun' : 'getThreadActiveRun', () => active.promise)
    const runStream = useAgentRunStream({
      getThreadState: state.getThreadState, currentAgentId: { value: 'health-consultation' },
      resetOnGoingConv: state.resetOnGoingConv, handleStreamChunk: () => {},
      fetchThreadMessages: async () => {}, fetchAgentState: async () => {}, onScrollToBottom: () => {}
    })
    const queue = useAgentRequestQueue({ getThreadState: state.getThreadState, resetOnGoingConv: state.resetOnGoingConv, startRunStream: runStream.startRunStream })
    const pending = runStream.resumeActiveRunForThread('thread-recovery')
    try {
      await queue.resumeQueuedRequests('thread-recovery', 'health-consultation')
      active.resolve({ run: { id: 'run-active', status: recovery.includes('interrupted') ? 'interrupted' : 'pending' } })
      await settleRecovery()
      assert.equal(ts.activeRunId, 'run-active')
      assert.equal(requestSignals.length, 1)
      assert.equal(requestSignals[0].aborted, false)
      assert.ok(ts.requestStreams['request-recovery'])
    } finally {
      runStream.stopRunStreamSubscription('thread-recovery')
      queue.stopAllRequestStreams('thread-recovery')
      await pending
      localStorage.removeItem('active_run:thread-recovery')
    }
  })
}

for (const recovery of ['snapshot', 'snapshot-steering', 'active', 'open-interrupted']) {
  test(`${recovery} 迟到 Run 恢复查询不能覆盖 Request 刚派发的新 Run`, async (t) => {
    const late = Promise.withResolvers(), streams = []
    const ts = recoveryThread()
    if (recovery.startsWith('snapshot')) localStorage.setItem('active_run:thread-recovery', JSON.stringify({ run_id: 'run-old', created_at: Date.now() }))
    if (recovery === 'open-interrupted') {
      ts.activeRunId = 'run-old'
      ts.runStreamAbortController = new AbortController()
    }
    t.mock.method(agentApi, recovery === 'active' ? 'getThreadActiveRun' : 'getAgentRun', (id) => id === 'run-new'
      ? { run: { id, conversation_thread_id: 'thread-recovery', request_id: 'request-recovery', status: 'pending' } }
      : recovery === 'snapshot-steering'
        ? { run: { id: 'run-old', status: 'running', run_type: 'chat', request_id: 'request-old' } } : late.promise)
    if (recovery === 'snapshot-steering') t.mock.method(agentApi, 'getRequest', () => late.promise)
    t.mock.method(agentApi, 'streamAgentRunEvents', async (id, _cursor, { signal }) => {
      streams.push({ id, signal })
      return new Response(new ReadableStream({ start(controller) {
        signal.addEventListener('abort', () => controller.error(new DOMException('aborted', 'AbortError')), { once: true })
      } }))
    })
    t.mock.method(agentApi, 'streamRequestEvents', async () => new Response('event: run_created\ndata: {"run_id":"run-new"}\n\n'))
    const runStream = useAgentRunStream({
      getThreadState: () => ts, currentAgentId: { value: 'health-consultation' },
      resetOnGoingConv: () => {}, handleStreamChunk: () => {},
      fetchThreadMessages: async () => {}, fetchAgentState: async () => {}, onScrollToBottom: () => {}
    })
    const queue = useAgentRequestQueue({ getThreadState: () => ts, resetOnGoingConv: () => {}, startRunStream: runStream.startRunStream })
    const pending = runStream.resumeActiveRunForThread('thread-recovery')
    try {
      if (recovery === 'snapshot-steering') await settleRecovery()
      await queue.startRequestStream('thread-recovery', 'request-recovery')
      late.resolve(recovery === 'snapshot-steering' ? { request: { source: 'chat' } }
        : { run: { id: 'run-old', status: recovery === 'open-interrupted' ? 'interrupted' : 'pending' } })
      await settleRecovery()
      assert.equal(ts.activeRunId, 'run-new')
      assert.deepEqual(streams.map(stream => stream.id), ['run-new'])
      assert.equal(streams[0].signal.aborted, false)
    } finally {
      runStream.stopRunStreamSubscription('thread-recovery')
      queue.stopAllRequestStreams('thread-recovery')
      await pending
      localStorage.removeItem('active_run:thread-recovery')
    }
  })
}

test('Run 恢复查询返回前线程已清理，新线程对象不接收旧结果', async (t) => {
  const old = recoveryThread(), fresh = recoveryThread(), late = Promise.withResolvers()
  let current = old
  t.mock.method(agentApi, 'getThreadActiveRun', () => late.promise)
  t.mock.method(agentApi, 'streamAgentRunEvents', () => assert.fail('新线程对象不能订阅旧查询结果'))
  const runStream = useAgentRunStream({ getThreadState: () => current, resetOnGoingConv: () => assert.fail('不能清理新线程') })
  const pending = runStream.resumeActiveRunForThread('thread-recovery')
  current = fresh
  late.resolve({ run: { id: 'run-old', status: 'pending' } })
  await pending
  assert.equal(fresh.activeRunId, null)
  assert.equal(old.activeRunId, null)
})

for (const recovery of ['queued', 'eof', 'late']) {
  test(`Vue reactive 线程的 ${recovery} Request 订阅使用真实代理 owner`, async (t) => {
    const state = useAgentThreadState({ chatState: reactive({ threadStates: {} }), getCurrentThreadId: () => 'thread-recovery' })
    const ts = state.getThreadState('thread-recovery'), starts = [], late = Promise.withResolvers()
    ts.queuedRequests = [{ request_id: 'request-recovery', status: 'queued' }]
    let signal
    t.mock.method(agentApi, 'streamRequestEvents', async (_id, options) => {
      signal = options.signal
      if (recovery !== 'queued') return new Response('')
      return new Response(new ReadableStream({ start(controller) {
        controller.enqueue(new TextEncoder().encode('event: queued\ndata: {"request_id":"request-recovery","position":2}\n\n'))
        signal.addEventListener('abort', () => controller.error(new DOMException('aborted', 'AbortError')), { once: true })
      } }))
    })
    t.mock.method(agentApi, 'getRequest', () => recovery === 'late' ? late.promise : recoveryRequest())
    const queue = useAgentRequestQueue({ getThreadState: state.getThreadState, resetOnGoingConv: state.resetOnGoingConv, startRunStream: (...args) => starts.push(args) })
    const pending = queue.startRequestStream('thread-recovery', 'request-recovery')
    try {
      await settleRecovery()
      assert.equal(isProxy(ts), true)
      assert.equal(agentApi.streamRequestEvents.mock.callCount(), 1)
      if (recovery === 'queued') {
        assert.equal(isProxy(ts.requestStreams['request-recovery']), true)
        assert.equal(ts.queuedRequests[0].queue_position, 2)
        assert.equal(signal.aborted, false)
      } else if (recovery === 'eof') {
        await pending
        assert.equal(agentApi.getRequest.mock.callCount(), 1)
        assert.deepEqual(starts, [['thread-recovery', 'run-recovery', '0-0', { requestId: 'request-recovery' }]])
        assert.equal(ts.pendingRequestId, 'request-recovery')
      } else {
        assert.equal(agentApi.getRequest.mock.callCount(), 1)
        queue.stopAllRequestStreams('thread-recovery')
        ts.queuedRequests = [{ request_id: 'new-request', status: 'queued' }]
        late.resolve(recoveryRequest())
        await pending
        assert.deepEqual(starts, [])
        assert.deepEqual(ts.queuedRequests, [{ request_id: 'new-request', status: 'queued' }])
      }
    } finally {
      queue.stopAllRequestStreams('thread-recovery')
      late.resolve(recoveryRequest())
      await pending
    }
  })
}

for (const connection of ['live', 'stopped']) {
  test(`同 Run ${connection} 重复交接保持游标与已消费正文`, async (t) => {
    const state = useAgentThreadState({ chatState: reactive({ threadStates: {} }), getCurrentThreadId: () => 'thread-review' })
    const ts = state.getThreadState('thread-review'), streams = [], running = []
    ts.queuedRequests = [{ request_id: 'request-review', status: 'queued' }]
    t.mock.method(agentApi, 'streamRequestEvents', async () => new Response('event: run_created\ndata: {"request_id":"request-review","run_id":"run-review"}\n\n'))
    t.mock.method(agentApi, 'streamAgentRunEvents', async (id, cursor, { signal }) => {
      streams.push({ id, cursor, signal })
      return new Response(new ReadableStream({ start(controller) {
        controller.enqueue(new TextEncoder().encode('id: 1-1\nevent: chunk\ndata: {"run_id":"run-review","request_id":"request-review","thread_id":"thread-review","payload":{"chunk":{"status":"loading","stream_event":{"type":"message_delta","message_id":"message-review","content":"hello"}}}}\n\n'))
        signal.addEventListener('abort', () => controller.error(new DOMException('aborted', 'AbortError')), { once: true })
      } }))
    })
    const handler = useAgentStreamHandler({ getThreadState: state.getThreadState })
    const runStream = useAgentRunStream({
      getThreadState: state.getThreadState, currentAgentId: { value: 'health-consultation' },
      resetOnGoingConv: state.resetOnGoingConv, handleStreamChunk: handler.handleStreamChunk,
      fetchThreadMessages: async () => {}, fetchAgentState: async () => {}, onScrollToBottom: () => {}
    })
    const queue = useAgentRequestQueue({
      getThreadState: state.getThreadState, resetOnGoingConv: state.resetOnGoingConv,
      startRunStream: (...args) => { const pending = runStream.startRunStream(...args); running.push(pending); return pending }
    })
    const pending = queue.startRequestStream('thread-review', 'request-review')
    try {
      await settleRecovery()
      assert.equal(isProxy(ts), true)
      assert.equal(agentApi.streamRequestEvents.mock.callCount(), 1)
      assert.deepEqual(streams.map(({ id, cursor }) => [id, cursor]), [['run-review', '0-0']])
      assert.deepEqual(ts.onGoingConv.msgChunks['message-review'].map(chunk => chunk.content), ['hello'])
      assert.equal(ts.runLastSeq, '1-1')
      const owner = ts.runStreamAbortController
      if (connection === 'stopped') {
        runStream.stopRunStreamSubscription('thread-review')
        await running[0]
        assert.equal(ts.runStreamAbortController, null)
      }
      await pending
      ts.queuedRequests = [{ request_id: 'request-review', status: 'queued' }]
      await queue.startRequestStream('thread-review', 'request-review')
      await settleRecovery()
      assert.equal(agentApi.streamRequestEvents.mock.callCount(), 2)
      assert.deepEqual(ts.onGoingConv.msgChunks['message-review'].map(chunk => chunk.content), ['hello'])
      assert.equal(ts.activeRunId, 'run-review')
      assert.equal(ts.runLastSeq, '1-1')
      assert.deepEqual(ts.queuedRequests, [])
      if (connection === 'live') {
        assert.equal(streams.length, 1)
        assert.equal(ts.runStreamAbortController, owner)
        assert.equal(streams[0].signal.aborted, false)
      } else {
        assert.deepEqual(streams.map(({ id, cursor }) => [id, cursor]), [['run-review', '0-0'], ['run-review', '1-1']])
        assert.equal(streams[1].signal.aborted, false)
      }
    } finally {
      await pending
      queue.stopAllRequestStreams('thread-review')
      runStream.stopRunStreamSubscription('thread-review')
      await Promise.all(running)
      localStorage.removeItem('active_run:thread-review')
    }
  })
}

for (const recovery of ['known', 'parallel-empty']) {
  test(`${recovery} 两 Request 的迟到旧队列快照不能复活旧 Run 或重复当前正文`, async (t) => {
    const state = useAgentThreadState({ chatState: reactive({ threadStates: {} }), getCurrentThreadId: () => 'thread-review' })
    const ts = state.getThreadState('thread-review'), initial = Promise.withResolvers(), stale = Promise.withResolvers(), second = Promise.withResolvers()
    const requests = [{ request_id: 'request-one', status: 'queued' }, { request_id: 'request-two', status: 'queued' }]
    const streams = [], running = [], resumes = []
    let queueReads = 0
    ts.queuedRequests = recovery === 'known' ? requests : []
    t.mock.method(agentApi, 'listThreadQueuedRequests', () => {
      queueReads++
      return recovery === 'parallel-empty' && queueReads === 1 ? initial.promise : stale.promise
    })
    t.mock.method(agentApi, 'streamRequestEvents', async (requestId) => {
      if (requestId === 'request-two') await second.promise
      return new Response(`event: run_created\ndata: ${JSON.stringify({ request_id: requestId, run_id: requestId === 'request-one' ? 'run-one' : 'run-two' })}\n\n`)
    })
    t.mock.method(agentApi, 'streamAgentRunEvents', async (id, cursor, { signal }) => {
      streams.push({ id, cursor, signal })
      return new Response(new ReadableStream({ start(controller) {
        const frame = id === 'run-one'
          ? 'id: 1-2\nevent: end\ndata: {"run_id":"run-one","payload":{"status":"completed"}}\n\n'
          : 'id: 1-1\nevent: chunk\ndata: {"run_id":"run-two","request_id":"request-two","thread_id":"thread-review","payload":{"chunk":{"status":"loading","stream_event":{"type":"message_delta","message_id":"message-two","content":"hello"}}}}\n\n'
        controller.enqueue(new TextEncoder().encode(frame))
        signal.addEventListener('abort', () => controller.error(new DOMException('aborted', 'AbortError')), { once: true })
      } }))
    })
    const handler = useAgentStreamHandler({ getThreadState: state.getThreadState })
    const runStream = useAgentRunStream({
      getThreadState: state.getThreadState, currentAgentId: { value: 'health-consultation' },
      resetOnGoingConv: state.resetOnGoingConv, handleStreamChunk: handler.handleStreamChunk,
      fetchThreadMessages: async () => {}, fetchAgentState: async () => {}, onScrollToBottom: () => {}
    })
    const queue = useAgentRequestQueue({
      getThreadState: state.getThreadState, resetOnGoingConv: state.resetOnGoingConv,
      startRunStream: (...args) => { const pending = runStream.startRunStream(...args); running.push(pending); return pending }
    })
    resumes.push(queue.resumeQueuedRequests('thread-review', 'health-consultation'))
    if (recovery === 'parallel-empty') {
      resumes.push(queue.resumeQueuedRequests('thread-review', 'health-consultation'))
      initial.resolve({ requests })
      await resumes[0]
    }
    try {
      await settleRecovery()
      assert.equal(isProxy(ts), true)
      assert.equal(queueReads, recovery === 'known' ? 1 : 2)
      assert.equal(ts.activeRunId, null)
      assert.deepEqual(streams.map(({ id, cursor }) => [id, cursor]), [['run-one', '0-0']])
      second.resolve()
      await settleRecovery()
      assert.equal(ts.activeRunId, 'run-two')
      assert.deepEqual(ts.onGoingConv.msgChunks['message-two'].map(chunk => chunk.content), ['hello'])
      const owner = ts.runStreamAbortController
      stale.resolve({ requests })
      await Promise.all(resumes)
      await settleRecovery()
      assert.deepEqual(ts.onGoingConv.msgChunks['message-two'].map(chunk => chunk.content), ['hello'])
      assert.deepEqual(streams.map(({ id, cursor }) => [id, cursor]), [['run-one', '0-0'], ['run-two', '0-0']])
      assert.equal(agentApi.streamRequestEvents.mock.callCount(), 2)
      assert.equal(ts.activeRunId, 'run-two')
      assert.equal(ts.runStreamAbortController, owner)
      assert.equal(owner.signal.aborted, false)
      assert.deepEqual(ts.queuedRequests, [])
    } finally {
      initial.resolve({ requests: [] })
      stale.resolve({ requests: [] })
      second.resolve()
      await Promise.all(resumes)
      queue.stopAllRequestStreams('thread-review')
      runStream.stopRunStreamSubscription('thread-review')
      await Promise.all(running)
      localStorage.removeItem('active_run:thread-review')
    }
  })
}

test('队列快照返回前线程对象已替换，不回写旧线程或新线程', async (t) => {
  const chatState = reactive({ threadStates: {} }), list = Promise.withResolvers()
  const state = useAgentThreadState({ chatState, getCurrentThreadId: () => 'thread-review' })
  const old = state.getThreadState('thread-review')
  old.queuedRequests = [{ request_id: 'old-local', status: 'queued' }]
  t.mock.method(agentApi, 'listThreadQueuedRequests', () => list.promise)
  const queue = useAgentRequestQueue({ getThreadState: state.getThreadState })
  const pending = queue.syncQueuedRequests('thread-review', 'health-consultation')
  state.cleanupThreadState('thread-review')
  const fresh = state.getThreadState('thread-review')
  fresh.queuedRequests = [{ request_id: 'new-local', status: 'queued' }]
  list.resolve({ requests: [{ request_id: 'old-server', status: 'queued' }] })
  await pending
  assert.notEqual(old, fresh)
  assert.deepEqual(old.queuedRequests, [{ request_id: 'old-local', status: 'queued' }])
  assert.deepEqual(fresh.queuedRequests, [{ request_id: 'new-local', status: 'queued' }])
})

for (const local of ['sending-push', 'accepted-replacement']) {
  test(`队列读取期间 ${local} 新本地请求保持原有合并语义`, async (t) => {
    const state = useAgentThreadState({ chatState: reactive({ threadStates: {} }), getCurrentThreadId: () => 'thread-review' })
    const ts = state.getThreadState('thread-review'), list = Promise.withResolvers()
    t.mock.method(agentApi, 'listThreadQueuedRequests', () => list.promise)
    const queue = useAgentRequestQueue({ getThreadState: state.getThreadState })
    const pending = queue.syncQueuedRequests('thread-review', 'health-consultation')
    const localRequest = { request_id: 'new-local', status: local === 'sending-push' ? 'sending' : 'queued' }
    if (local === 'sending-push') ts.queuedRequests.push(localRequest)
    else ts.queuedRequests = [localRequest]
    list.resolve({ requests: [{ request_id: 'server-queued', status: 'queued' }] })
    await pending
    assert.deepEqual(ts.queuedRequests, local === 'sending-push'
      ? [{ request_id: 'server-queued', status: 'queued' }, localRequest]
      : [localRequest])
  })
}

for (const outcome of ['eof-completed', 'eof-failed', 'eof-cancelled', 'eof-interrupted', 'sse-completed', 'sse-interrupted', 'pending', 'running', 'finalized', 'reconnected', 'owner', 'abort', 'replacement', 'thread-replaced', 'id', 'thread', 'request', 'reject', 'transient', 'exhausted', 'sse-transient', 'sse-exhausted', 'network']) {
  test(`跨 Run ${outcome} 派发查询保持实际 consumer 的当前 owner 与正文`, async (t) => {
    const recovers = ['transient', 'sse-transient', 'network'].includes(outcome)
    const exhausts = ['exhausted', 'sse-exhausted'].includes(outcome)
    if (recovers || exhausts) t.mock.timers.enable({ apis: ['setTimeout'] })
    const state = useAgentThreadState({ chatState: reactive({ threadStates: {} }), getCurrentThreadId: () => 'thread-review' })
    let ts = state.getThreadState('thread-review'), eventController, replacement
    let oldSubscriptions = 0
    const requestRead = Promise.withResolvers(), runRead = Promise.withResolvers(), running = [], streams = [], reads = [], notices = [], errors = []
    ts.queuedRequests = [{ request_id: 'request-old', status: 'queued' }, { request_id: 'request-new', status: 'queued' }]
    t.mock.method(ErrorHandler, 'handleError', error => notices.push(error))
    t.mock.method(agentApi, 'getRequest', () => requestRead.promise)
    t.mock.method(agentApi, 'getAgentRun', async (id) => {
      reads.push(id)
      if (id === 'run-old' && reads.length > 1 && recovers) return { run: { id, conversation_thread_id: 'thread-review', request_id: 'request-old', status: 'running' } }
      if (id === 'run-old' && reads.length > 1 && exhausts) throw Object.assign(new Error('临时候选查询故障'), { status: 500 })
      return id === 'run-old' ? runRead.promise : { run: { id, conversation_thread_id: 'thread-review', request_id: 'request-third', status: 'pending' } }
    })
    t.mock.method(agentApi, 'streamRequestEvents', async (id, { signal }) => {
      if (id === 'request-old') {
        oldSubscriptions++
        if (!outcome.startsWith('sse-')) return new Response('')
        if (oldSubscriptions > 1) return new Response('event: run_created\ndata: {"request_id":"request-old","run_id":"run-old"}\n\n')
        return new Response(new ReadableStream({ start(controller) {
          eventController = controller
          signal.addEventListener('abort', () => controller.error(new DOMException('aborted', 'AbortError')), { once: true })
        } }))
      }
      return new Response(`event: run_created\ndata: ${JSON.stringify({ request_id: id, run_id: id === 'request-new' ? 'run-new' : 'run-third' })}\n\n`)
    })
    t.mock.method(agentApi, 'streamAgentRunEvents', async (id, cursor, { signal }) => {
      const stream = { id, cursor, signal }
      streams.push(stream)
      return new Response(new ReadableStream({ start(controller) {
        stream.controller = controller
        const frame = id === 'run-old' && !['pending', 'running', 'finalized', 'reconnected'].includes(outcome) && !recovers
          ? 'id: 1-2\nevent: end\ndata: {"run_id":"run-old","payload":{"status":"completed"}}\n\n'
          : `id: 1-1\nevent: chunk\ndata: ${JSON.stringify({ run_id: id, request_id: id.replace('run-', 'request-'), thread_id: 'thread-review', payload: { chunk: { status: 'loading', stream_event: { type: 'message_delta', message_id: id.replace('run-', 'message-'), content: id.replace('run-', 'hello-') } } } })}\n\n`
        controller.enqueue(new TextEncoder().encode(frame))
        signal.addEventListener('abort', () => controller.error(new DOMException('aborted', 'AbortError')), { once: true })
      } }))
    })
    const handler = useAgentStreamHandler({ getThreadState: state.getThreadState })
    const runStream = useAgentRunStream({
      getThreadState: state.getThreadState, currentAgentId: { value: 'health-consultation' },
      resetOnGoingConv: state.resetOnGoingConv, handleStreamChunk: handler.handleStreamChunk,
      fetchThreadMessages: async () => {}, fetchAgentState: async () => {}, onScrollToBottom: () => {}
    })
    const queue = useAgentRequestQueue({
      getThreadState: state.getThreadState, resetOnGoingConv: state.resetOnGoingConv,
      startRunStream: (...args) => { const pending = runStream.startRunStream(...args); running.push(pending); return pending },
      onStreamError: (...args) => errors.push(args)
    })
    const oldRequest = queue.startRequestStream('thread-review', 'request-old')
    try {
      await settleRecovery()
      await queue.startRequestStream('thread-review', 'request-new')
      await settleRecovery()
      const originalOwner = ts.runStreamAbortController
      assert.equal(ts.activeRunId, 'run-new')
      assert.deepEqual(ts.onGoingConv.msgChunks['message-new'].map(chunk => chunk.content), ['hello-new'])
      if (outcome.startsWith('sse-')) {
        eventController.enqueue(new TextEncoder().encode('event: run_created\ndata: {"request_id":"request-old","run_id":"run-old"}\n\n'))
        eventController.close()
      }
      else requestRead.resolve({ request: { request_id: 'request-old', thread_id: 'thread-review', status: 'dispatched', dispatched_run_id: 'run-old' } })
      await settleRecovery()
      assert.equal(ts.activeRunId, 'run-new')
      assert.equal(ts.pendingRequestId, 'request-new')
      assert.equal(ts.runStreamAbortController, originalOwner)
      assert.deepEqual(reads, ['run-old'])
      if (outcome === 'finalized') {
        streams[0].controller.enqueue(new TextEncoder().encode('id: 1-2\nevent: end\ndata: {"run_id":"run-new","payload":{"status":"completed"}}\n\n'))
        await settleRecovery()
        assert.equal(ts.activeRunId, null)
      } else if (outcome === 'reconnected') {
        running.push(runStream.startRunStream('thread-review', 'run-new', '1-1'))
        await settleRecovery()
        assert.equal(ts.activeRunId, 'run-new')
        assert.notEqual(ts.runStreamAbortController, originalOwner)
      } else if (outcome === 'owner' || outcome === 'thread-replaced') {
        if (outcome === 'thread-replaced') {
          state.cleanupThreadState('thread-review')
          ts = state.getThreadState('thread-review')
        }
        await queue.startRequestStream('thread-review', 'request-third')
        await settleRecovery()
        assert.equal(ts.activeRunId, 'run-third')
      } else if (outcome === 'abort') queue.stopAllRequestStreams('thread-review')
      else if (outcome === 'replacement') {
        ts.requestStreams['request-old'] = { controller: new AbortController() }
        replacement = ts.requestStreams['request-old']
      }
      const fact = { run: { id: 'run-old', conversation_thread_id: 'thread-review', request_id: 'request-old', status: outcome.includes('-') ? outcome.split('-').at(-1) : outcome === 'running' ? 'running' : 'pending' } }
      if (outcome === 'id') fact.run.id = 'neighbor-run'
      if (outcome === 'thread') fact.run.conversation_thread_id = 'neighbor-thread'
      if (outcome === 'request') fact.run.request_id = 'neighbor-request'
      if (outcome === 'network') runRead.reject(new TypeError('候选运行查询断网'))
      else if (recovers || exhausts) runRead.reject(Object.assign(new Error('临时候选查询故障'), { status: 500 }))
      else if (outcome === 'reject') runRead.reject(Object.assign(new Error('候选 Run 不可读取'), { status: 403 }))
      else runRead.resolve(fact)
      if (recovers || exhausts) {
        await settleRecovery()
        assert.equal(ts.queuedRequests.some(request => request.request_id === 'request-old'), true)
        assert.equal(ts.requestStreams['request-old'].status, 'queued')
        assert.deepEqual(errors, [])
        assert.deepEqual(notices, [])
        for (const delay of recovers ? [500] : [500, 1000, 2000, 4000, 5000]) {
          t.mock.timers.tick(delay)
          await settleRecovery()
        }
        assert.equal(reads.filter(id => id === 'run-old').length, recovers ? 2 : 6)
      }
      await oldRequest
      await settleRecovery()
      const accepts = ['pending', 'running', 'finalized', 'reconnected'].includes(outcome) || recovers
      const active = accepts ? 'run-old' : ['owner', 'thread-replaced'].includes(outcome) ? 'run-third' : 'run-new'
      assert.equal(ts.activeRunId, active)
      assert.equal(ts.isStreaming, true)
      assert.equal(ts.pendingRequestId, active.replace('run-', 'request-'))
      assert.deepEqual(ts.onGoingConv.msgChunks[active.replace('run-', 'message-')].map(chunk => chunk.content), [active.replace('run-', 'hello-')])
      assert.deepEqual(streams.map(stream => stream.id), outcome === 'reconnected' ? ['run-new', 'run-new', 'run-old'] : accepts ? ['run-new', 'run-old'] : ['owner', 'thread-replaced'].includes(outcome) ? ['run-new', 'run-third'] : ['run-new'])
      assert.equal(streams.at(-1).signal.aborted, false)
      assert.equal(ts.requestStreams['request-old'], replacement)
      assert.deepEqual(errors, ['id', 'thread', 'request', 'reject'].includes(outcome) ? [['thread-review', 'request-old', 'error']] : [])
      assert.equal(notices.length, ['id', 'thread', 'request', 'reject'].includes(outcome) || exhausts ? 1 : 0)
      if (outcome === 'reject') assert.equal(notices[0].status, 403)
      if (exhausts) {
        assert.match(notices[0].message, /重新进入会话恢复原请求/)
        assert.equal(agentApi.streamRequestEvents.mock.callCount(), 7)
        assert.equal(agentApi.getRequest.mock.callCount(), outcome.startsWith('sse-') ? 0 : 6)
        assert.deepEqual(ts.queuedRequests, [{ request_id: 'request-old', status: 'queued' }])
        t.mock.timers.tick(100000)
        await settleRecovery()
        assert.equal(reads.filter(id => id === 'run-old').length, 6)
      }
    } finally {
      requestRead.resolve({ request: { request_id: 'request-old', thread_id: 'thread-review', status: 'cancelled' } })
      runRead.resolve({ run: { id: 'run-old', conversation_thread_id: 'thread-review', request_id: 'request-old', status: 'completed' } })
      queue.stopAllRequestStreams('thread-review')
      runStream.stopRunStreamSubscription('thread-review')
      await oldRequest
      await Promise.all(running)
      localStorage.removeItem('active_run:thread-review')
    }
  })
}

test('审批前后的工具和思考跨关联 Run 连续展示，正文仍独立', () => {
  const runs = [
    { run_id: 'first', status: 'interrupted', timing: { created_at: '2026-09-16T00:00:00Z' } },
    {
      run_id: 'resume',
      run_type: 'resume',
      created_by_run_id: 'first',
      status: 'completed',
      timing: { created_at: '2026-09-16T00:01:00Z' }
    }
  ]
  const history = [
    { id: 'human', run_id: 'first', type: 'human', content: '完成任务' },
    { id: 'm1', run_id: 'first', type: 'ai', tool_calls: [{ id: 't1', name: 'ls', args: {} }] },
    {
      id: 'm2',
      run_id: 'first',
      type: 'ai',
      reasoning_content: 'thinking1',
      tool_calls: [
        { id: 't2', name: 'read_file', args: {} },
        { id: 't3', name: 'ask_user_question', args: {}, status: 'success' }
      ]
    },
    {
      id: 'answer',
      run_id: 'resume',
      type: 'human',
      content: '同意',
      extra_metadata: { source: 'ask_user_question_resume' }
    },
    {
      id: 'm3',
      run_id: 'resume',
      type: 'ai',
      reasoning_content: 'thinking2',
      tool_calls: [{ id: 't4', name: 'ls', args: {} }]
    },
    { id: 'm4', run_id: 'resume', type: 'ai', content: '最终回答' }
  ]
  const runGroups = MessageProcessor.convertServerHistoryToMessages(history, runs)
  const groups = groupConversationContinuations(runGroups)
  assert.equal(groups.length, 1)
  const items = getConversationDisplayItems(groups[0])
  assert.deepEqual(
    items.map((item) => item.type),
    ['message', 'tool-group', 'message']
  )
  assert.deepEqual(
    items[1].entries.map((entry) => (entry.type === 'tool' ? entry.toolCall.id : entry.content)),
    ['t1', 'thinking1', 't2', 't3', 'thinking2', 't4']
  )
  assert.equal(items[2].message.content, '最终回答')
  assert.equal(runGroups.length, 2)
  const streaming = groupConversationContinuations([
    runGroups[0],
    { ...runGroups[1], status: 'streaming', messages: runGroups[1].messages.slice(0, 1) }
  ])
  assert.equal(streaming[0].status, 'streaming')
  assert.equal(getConversationDisplayItems(streaming[0])[1].key, items[1].key)
})

test('thinking 与相邻工具按顺序合并，正文和错误仍独立显示', () => {
  const messages = [
    { id: 'a1', type: 'ai', reasoning_content: '先检查', tool_calls: [{ id: 't1', name: 'ls', args: {} }] },
    { id: 'a2', type: 'ai', reasoning_content: '再确认', tool_calls: [{ id: 't2', name: 'read_file', args: {} }] },
    { id: 'a3', type: 'ai', reasoning_content: '得到结论', content: '最终回答' }
  ]
  const items = getConversationDisplayItems({ messages })
  assert.deepEqual(items.map((item) => item.type), ['tool-group', 'message'])
  assert.deepEqual(items[0].entries.map((entry) => entry.type), ['reasoning', 'tool', 'reasoning', 'tool', 'reasoning'])
  assert.deepEqual(items[0].entries.filter((entry) => entry.type === 'reasoning').map((entry) => entry.content), ['先检查', '再确认', '得到结论'])
  assert.equal(items[0].toolCalls.length, 2)
  assert.equal(items[1].message.content, '最终回答')
  assert.equal(items[1].message.reasoning_content, '')
  assert.equal(messages[2].reasoning_content, '得到结论')

  const thinkingOnly = getConversationDisplayItems({ messages: [{ id: 'a', type: 'ai', reasoning_content: '思考中' }] })
  assert.equal(thinkingOnly.length, 1)
  assert.equal(thinkingOnly[0].type, 'tool-group')
  assert.equal(thinkingOnly[0].entries[0].content, '思考中')
  assert.deepEqual(thinkingOnly[0].toolCalls, [])
  assert.deepEqual(getConversationDisplayItems({ messages: [{ type: 'ai', content: '' }] }), [])

  const failed = getConversationDisplayItems({ messages: [{ type: 'ai', reasoning_content: '检查中断', error_type: 'interrupted' }] })
  assert.deepEqual(failed.map((item) => item.type), ['tool-group', 'message'])
  assert.equal(failed[1].message.error_type, 'interrupted')
})

test('同一消息的 thinking、正文和工具分段使用不同的稳定 key', () => {
  const message = { id: 'mixed', type: 'ai', reasoning_content: '计划', content: '先查文件', tool_calls: [{ id: 't1', name: 'ls', args: {} }] }
  const items = getConversationDisplayItems({ messages: [message] })
  assert.deepEqual(items.map((item) => item.type), ['tool-group', 'message', 'tool-group'])
  assert.equal(new Set(items.map((item) => item.key)).size, 3)
  assert.equal(items[0].entries[0].content, '计划')
  assert.equal(items[2].entries[0].toolCall.id, 't1')
  const updated = getConversationDisplayItems({ messages: [{ ...message, content: '先查文件，再整理' }] })
  assert.deepEqual(updated.map((item) => item.key), items.map((item) => item.key))
})

test('当前工具语义流首块即显示，完整快照覆盖分片并关联同 Run 结果', () => {
  const threadState = { onGoingConv: { msgChunks: {} } }
  const { handleStreamChunk } = useAgentStreamHandler({ getThreadState: () => threadState })
  const send = (stream_event) =>
    handleStreamChunk({ status: 'loading', run_id: 'run-tools', stream_event }, 'thread-tools')
  const messages = () =>
    MessageProcessor.convertToolResultToMessages(
      Object.values(threadState.onGoingConv.msgChunks).map(MessageProcessor.mergeMessageChunk)
    ).filter((msg) => msg.type !== 'tool')
  send({
    type: 'tool_call_delta',
    message_id: 'model-tools',
    tool_call_id: 'call-1',
    name: 'read_file',
    index: 0,
    args_delta: '{"path":'
  })
  let items = getConversationDisplayItems({ messages: messages() })
  assert.equal(items.length, 1)
  assert.equal(items[0].type, 'tool-group')
  assert.equal(items[0].toolCalls[0].name, 'read_file')
  send({ type: 'tool_call_delta', message_id: 'model-tools', index: 0, args_delta: '"/notes.md"}' })
  send({
    type: 'tool_call',
    message_id: 'model-tools',
    tool_call_id: 'call-1',
    name: 'read_file',
    index: 0,
    args: { path: '/notes.md' }
  })
  send({
    type: 'tool_call',
    message_id: 'model-tools',
    tool_call_id: 'call-2',
    name: 'ls',
    index: 1,
    args: { path: '/' }
  })
  handleStreamChunk(
    {
      status: 'stream_event',
      run_id: 'run-tools',
      event: {
        method: 'tools',
        data: {
          event: 'tool-finished',
          tool_call_id: 'call-1',
          output: { type: 'tool', tool_call_id: 'call-1', content: 'notes', status: 'success' }
        }
      }
    },
    'thread-tools'
  )
  const toolCalls = messages()[0].tool_calls
  assert.equal(toolCalls.length, 2)
  assert.deepEqual(JSON.parse(toolCalls[0].args), { path: '/notes.md' })
  assert.equal(toolCalls[0].tool_call_result.content, 'notes')
  assert.equal(toolCalls[0].tool_call_result.run_id, 'run-tools')
  assert.equal(toolCalls[1].tool_call_result, null)
})

test('只有单个完整工具事件且无正文时仍显示工具，旧 loading msg 不再消费', () => {
  const threadState = { onGoingConv: { msgChunks: {} } }
  const { handleStreamChunk } = useAgentStreamHandler({ getThreadState: () => threadState })
  handleStreamChunk(
    { status: 'loading', msg: { id: 'legacy', type: 'ai', content: 'old' } },
    'thread-tools'
  )
  assert.deepEqual(threadState.onGoingConv.msgChunks, {})
  handleStreamChunk(
    {
      status: 'loading',
      run_id: 'run-tools',
      stream_event: {
        type: 'tool_call',
        message_id: 'only-tool',
        tool_call_id: 'call-1',
        name: 'ls',
        args: {}
      }
    },
    'thread-tools'
  )
  const message = MessageProcessor.mergeMessageChunk(threadState.onGoingConv.msgChunks['only-tool'])
  assert.equal(getConversationDisplayItems({ messages: [message] })[0].toolCalls[0].name, 'ls')
})

test('重复工具 ID 的结果不能跨 Run 绑定', () => {
  const [message] = MessageProcessor.convertToolResultToMessages([
    { type: 'ai', run_id: 'new-run', tool_calls: [{ id: 'same-call', name: 'ls', args: {} }] },
    { type: 'tool', run_id: 'old-run', tool_call_id: 'same-call', content: 'old result' }
  ])
  assert.equal(message.tool_calls[0].tool_call_result, null)
})

/** 集中 Run SSE 测试的固定依赖，只暴露各用例关心的行为。 */
const createRunStream = ({ threadState, handleStreamChunk, resetOnGoingConv }) =>
  useAgentRunStream({
    getThreadState: () => threadState,
    currentAgentId: { value: 'agent-1' },
    handleStreamChunk,
    fetchThreadMessages: async () => {},
    fetchAgentState: () => {},
    resetOnGoingConv,
    onScrollToBottom: () => {},
    streamSmoother: { flushThread: () => {} }
  })

test('Run envelope 归一化同时保留批量与单 chunk 形状及线程上下文', () => {
  const batchData = {
    request_id: 'request-1',
    run_id: 'run-1',
    payload: { items: [{ status: 'loading', id: 'message-1' }] }
  }
  const singleData = {
    request_id: 'request-2',
    payload: {
      chunk: {
        status: 'loading',
        id: 'message-2',
        metadata: { thread_id: 'child-thread' }
      }
    }
  }

  const dispatched = []
  dispatchRunEventChunks({
    data: batchData,
    runId: 'run-fallback',
    fallbackThreadId: 'parent-thread',
    streamRunId: 'run-1',
    streamThreadId: 'parent-thread',
    onChunk: (chunk, threadId) => dispatched.push({ chunk, threadId })
  })
  dispatchRunEventChunks({
    data: singleData,
    runId: 'run-fallback',
    fallbackThreadId: 'parent-thread',
    onChunk: (chunk, threadId) => dispatched.push({ chunk, threadId })
  })

  assert.deepEqual(dispatched, [
    {
      chunk: {
        status: 'loading',
        id: 'message-1',
        request_id: 'request-1',
        run_id: 'run-1',
        thread_id: 'parent-thread',
        stream_run_id: 'run-1',
        stream_thread_id: 'parent-thread'
      },
      threadId: 'parent-thread'
    },
    {
      chunk: {
        status: 'loading',
        id: 'message-2',
        metadata: { thread_id: 'child-thread' },
        request_id: 'request-2',
        run_id: 'run-fallback',
        thread_id: 'child-thread'
      },
      threadId: 'child-thread'
    }
  ])
})

test('agent_state SSE 使在途状态请求失效', () => {
  const threadState = {
    agentState: null,
    agentStateRequestVersion: 4,
    onGoingConv: { msgChunks: {} }
  }
  const { handleStreamChunk } = useAgentStreamHandler({
    getThreadState: () => threadState,
    processApprovalInStream: () => false,
    currentAgentId: { value: 'agent-1' },
    supportsFiles: { value: false }
  })
  const agentState = { token_usage: { measured_at: '2026-08-09T00:00:00Z' } }

  handleStreamChunk({ status: 'agent_state', agent_state: agentState }, 'thread-1')

  assert.deepEqual(threadState.agentState, agentState)
  assert.equal(threadState.agentStateRequestVersion, 5)
})

test('Run init 将权威 run_id 绑定到实时 User Message', () => {
  const threadState = {
    pendingRequestId: 'request-1',
    replyLoadingVisible: false,
    contextCompressing: false,
    onGoingConv: {
      msgChunks: {
        'request-1': [
          { id: 'request-1', type: 'human', content: '快排', created_at: '2026-09-05T06:32:00Z' }
        ]
      }
    }
  }
  const { handleStreamChunk } = useAgentStreamHandler({
    getThreadState: () => threadState,
    processApprovalInStream: () => false,
    currentAgentId: { value: 'agent-1' },
    supportsFiles: { value: false }
  })

  handleStreamChunk(
    {
      status: 'init',
      run_id: 'stale-body-run',
      stream_run_id: 'run-1',
      stream_thread_id: 'thread-1',
      request_id: 'request-1',
      msg: { type: 'human', content: '快排' }
    },
    'thread-1'
  )

  const [message] = threadState.onGoingConv.msgChunks['request-1']
  assert.equal(message.created_at, '2026-09-05T06:32:00Z')
  assert.equal(message.run_id, 'run-1')
  assert.equal(message.extra_metadata.run_id, 'run-1')
  assert.equal(message.extra_metadata.request_id, 'request-1')
})

test('缺少 SSE request_id 时不把 Run 关联到本地 pending User', () => {
  const threadState = {
    pendingRequestId: 'request-old',
    replyLoadingVisible: false,
    contextCompressing: false,
    onGoingConv: { msgChunks: {} }
  }
  const { handleStreamChunk } = useAgentStreamHandler({
    getThreadState: () => threadState,
    processApprovalInStream: () => false,
    currentAgentId: { value: 'agent-1' },
    supportsFiles: { value: false }
  })

  handleStreamChunk(
    {
      status: 'init',
      run_id: 'run-new',
      msg: {
        type: 'human',
        content: '旧请求',
        run_id: 'run-from-msg',
        extra_metadata: { run_id: 'run-from-msg' }
      }
    },
    'thread-1'
  )

  const [message] = threadState.onGoingConv.msgChunks['request-old']
  assert.equal(message.run_id, undefined)
  assert.equal(message.extra_metadata.run_id, undefined)
})

test('子线程 init 不继承父订阅 Run 关联', () => {
  const threadState = {
    pendingRequestId: 'request-child',
    replyLoadingVisible: false,
    contextCompressing: false,
    onGoingConv: { msgChunks: {} }
  }
  const { handleStreamChunk } = useAgentStreamHandler({
    getThreadState: () => threadState,
    processApprovalInStream: () => false,
    currentAgentId: { value: 'agent-1' },
    supportsFiles: { value: false }
  })

  handleStreamChunk(
    {
      status: 'init',
      request_id: 'request-child',
      stream_run_id: 'parent-run',
      stream_thread_id: 'parent-thread',
      msg: { type: 'human', content: '子线程输入' }
    },
    'child-thread'
  )

  const [message] = threadState.onGoingConv.msgChunks['request-child']
  assert.equal(message.run_id, undefined)
})

test('恢复队列在同步后重新读取线程状态并启动当前请求流', async () => {
  const staleThreadState = {
    queuedRequests: [{ request_id: 'request-stale', status: 'queued' }],
    requestStreams: {}
  }
  const latestThreadState = {
    queuedRequests: [{ request_id: 'request-latest', status: 'running' }],
    requestStreams: {}
  }
  let currentThreadState = staleThreadState
  const calls = []
  const originalListThreadQueuedRequests = agentApi.listThreadQueuedRequests
  const originalStreamRequestEvents = agentApi.streamRequestEvents
  agentApi.listThreadQueuedRequests = async (...args) => {
    calls.push(['sync', ...args])
    currentThreadState = latestThreadState
    return {
      requests: [{ request_id: 'request-from-sync', status: 'queued' }],
      queue: { status: 'running' }
    }
  }
  agentApi.streamRequestEvents = async (requestId) =>
    new Response(`event: run_created\ndata: {"run_id":"run-for-${requestId}"}\n\n`, {
      headers: { 'Content-Type': 'text/event-stream' }
    })

  try {
    const streamStarts = []
    const queue = useAgentRequestQueue({
      getThreadState: () => currentThreadState,
      resetOnGoingConv: () => {},
      startRunStream: (...args) => streamStarts.push(args),
      onStreamError: () => {}
    })

    await queue.resumeQueuedRequests('thread-1', 'agent-1')
    await new Promise((resolve) => setTimeout(resolve, 0))

    assert.deepEqual(calls, [['sync', 'thread-1', 'agent-1']])
    assert.deepEqual(streamStarts, [
      ['thread-1', 'run-for-request-latest', '0-0', { requestId: 'request-latest' }]
    ])
    // 迟到同步不再回写已被替换的线程，恢复动作仍订阅当前线程的队列。
    assert.deepEqual(staleThreadState.queuedRequests, [
      { request_id: 'request-stale', status: 'queued' }
    ])
    assert.deepEqual(latestThreadState.queuedRequests, [])
    assert.equal(latestThreadState.requestStreams['request-latest'], undefined)
  } finally {
    agentApi.listThreadQueuedRequests = originalListThreadQueuedRequests
    agentApi.streamRequestEvents = originalStreamRequestEvents
  }
})

test('run_created 立即完成状态交接并订阅新 Run SSE', async () => {
  const threadState = {
    queuedRequests: [{ request_id: 'request-1', status: 'queued' }],
    requestStreams: {},
    onGoingConv: {
      msgChunks: {
        old: [],
        'request-1': [{ type: 'human', content: '待执行', request_id: 'request-1' }]
      }
    },
    pendingRequestId: null
  }
  const calls = []
  const originalStreamRequestEvents = agentApi.streamRequestEvents
  agentApi.streamRequestEvents = async () =>
    new Response('event: run_created\ndata: {"run_id":"run-2"}\n\n', {
      headers: { 'Content-Type': 'text/event-stream' }
    })

  try {
    const queue = useAgentRequestQueue({
      getThreadState: () => threadState,
      resetOnGoingConv: (threadId, options) => {
        calls.push(['reset', threadId, options])
        threadState.onGoingConv = { msgChunks: {} }
      },
      startRunStream: (...args) => {
        calls.push(['start', ...args])
      },
      onStreamError: () => {}
    })

    await queue.startRequestStream('thread-1', 'request-1')

    assert.deepEqual(calls, [
      ['reset', 'thread-1', { preserveRequestStreams: true }],
      ['start', 'thread-1', 'run-2', '0-0', { requestId: 'request-1' }]
    ])
    assert.equal(threadState.onGoingConv.msgChunks['request-1'][0].content, '待执行')
    assert.equal(threadState.onGoingConv.msgChunks.old, undefined)
    assert.equal(threadState.pendingRequestId, 'request-1')
    assert.deepEqual(threadState.queuedRequests, [])
  } finally {
    agentApi.streamRequestEvents = originalStreamRequestEvents
  }
})

test('run_created 先到达时保留旧 Run 已渲染的内容', async (t) => {
  t.mock.method(agentApi, 'getAgentRun', async (id) => ({ run: { id, conversation_thread_id: 'thread-1', request_id: 'request-2', status: 'pending' } }))
  const oldMessages = { 'old-message': [{ id: 'old-message', content: '旧回复' }] }
  const threadState = {
    activeRunId: 'run-1',
    queuedRequests: [{ request_id: 'request-2', status: 'queued' }],
    requestStreams: {},
    onGoingConv: { msgChunks: oldMessages },
    pendingRequestId: null
  }
  const calls = []
  const originalStreamRequestEvents = agentApi.streamRequestEvents
  agentApi.streamRequestEvents = async () =>
    new Response('event: run_created\ndata: {"run_id":"run-2"}\n\n', {
      headers: { 'Content-Type': 'text/event-stream' }
    })

  try {
    const queue = useAgentRequestQueue({
      getThreadState: () => threadState,
      resetOnGoingConv: () => calls.push(['reset']),
      startRunStream: (...args) => calls.push(['start', ...args]),
      onStreamError: () => {}
    })

    await queue.startRequestStream('thread-1', 'request-2')

    assert.deepEqual(calls, [['start', 'thread-1', 'run-2', '0-0', { requestId: 'request-2' }]])
    assert.equal(threadState.onGoingConv.msgChunks, oldMessages)
    assert.equal(threadState.pendingRequestId, 'request-2')
  } finally {
    agentApi.streamRequestEvents = originalStreamRequestEvents
  }
})

test('replacement Run SSE 的增量 chunk 会连续进入前端渲染处理', async (t) => {
  t.mock.method(agentApi, 'getAgentRun', async (id) => ({ run: { id, conversation_thread_id: 'thread-1', request_id: 'request-2', status: 'pending' } }))
  const oldMessages = { 'old-message': [{ id: 'old-message', content: '旧回复' }] }
  const threadState = {
    activeRunId: 'run-1',
    activeRunSteerable: true,
    queuedRequests: [{ request_id: 'request-2', status: 'queued' }],
    requestStreams: {},
    runLastSeq: '0-0',
    runStreamAbortController: null,
    replyLoadingVisible: true,
    pendingRequestId: 'request-1',
    pendingInterrupt: null,
    onGoingConv: { msgChunks: oldMessages }
  }
  const originalStreamRequestEvents = agentApi.streamRequestEvents
  const originalStreamAgentRunEvents = agentApi.streamAgentRunEvents
  const textEncoder = new TextEncoder()
  let runStreamController
  let replacementRun
  let firstLoadingChunk
  let loadingChunkCount = 0
  let resolveFirstChunk
  let resolveSecondChunk
  const firstChunkProcessed = new Promise((resolve) => {
    resolveFirstChunk = resolve
  })
  const secondChunkProcessed = new Promise((resolve) => {
    resolveSecondChunk = resolve
  })

  agentApi.streamRequestEvents = async () =>
    new Response('event: run_created\ndata: {"run_id":"run-2"}\n\n', {
      headers: { 'Content-Type': 'text/event-stream' }
    })
  agentApi.streamAgentRunEvents = async () =>
    new Response(
      new ReadableStream({
        start(controller) {
          runStreamController = controller
        }
      }),
      { headers: { 'Content-Type': 'text/event-stream' } }
    )

  try {
    const { handleStreamChunk } = useAgentStreamHandler({
      getThreadState: () => threadState,
      processApprovalInStream: () => false,
      currentAgentId: { value: 'agent-1' },
      supportsFiles: { value: false }
    })
    const runStream = createRunStream({
      threadState,
      handleStreamChunk: (chunk, threadId) => {
        const shouldStop = handleStreamChunk(chunk, threadId)
        if (chunk.status === 'loading') {
          loadingChunkCount += 1
          if (loadingChunkCount === 1) {
            firstLoadingChunk = chunk
            resolveFirstChunk()
          }
          if (loadingChunkCount === 2) resolveSecondChunk()
        }
        return shouldStop
      },
      resetOnGoingConv: () => {}
    })
    const queue = useAgentRequestQueue({
      getThreadState: () => threadState,
      resetOnGoingConv: () => {},
      startRunStream: (...args) => {
        replacementRun = runStream.startRunStream(...args)
        return replacementRun
      },
      onStreamError: () => {}
    })

    await queue.startRequestStream('thread-1', 'request-2')

    runStreamController.enqueue(
      textEncoder.encode(
        'id: 1-0\nevent: custom\ndata: {"run_id":"run-2","request_id":"request-2","payload":{"chunk":{"status":"loading","run_id":"run-2","request_id":"request-2","stream_event":{"type":"message_delta","message_id":"assistant-2","content":"流式"}}}}\n\n'
      )
    )
    await firstChunkProcessed
    assert.deepEqual(
      threadState.onGoingConv.msgChunks['assistant-2'].map((chunk) => chunk.content),
      ['流式']
    )
    assert.equal(firstLoadingChunk.stream_run_id, 'run-2')
    assert.equal(firstLoadingChunk.stream_thread_id, 'thread-1')

    runStreamController.enqueue(
      textEncoder.encode(
        'id: 2-0\nevent: custom\ndata: {"run_id":"run-2","request_id":"request-2","payload":{"chunk":{"status":"loading","run_id":"run-2","request_id":"request-2","stream_event":{"type":"message_delta","message_id":"assistant-2","content":"渲染"}}}}\n\n'
      )
    )
    await secondChunkProcessed
    assert.deepEqual(
      threadState.onGoingConv.msgChunks['assistant-2'].map((chunk) => chunk.content),
      ['流式', '渲染']
    )

    runStreamController.enqueue(
      textEncoder.encode(
        'id: 3-0\nevent: end\ndata: {"run_id":"run-2","payload":{"status":"completed"}}\n\n'
      )
    )
    runStreamController.close()
    await replacementRun

    assert.deepEqual(threadState.onGoingConv.msgChunks['old-message'], [
      { id: 'old-message', content: '旧回复' }
    ])
    assert.equal(threadState.runLastSeq, '3-0')
  } finally {
    agentApi.streamRequestEvents = originalStreamRequestEvents
    agentApi.streamAgentRunEvents = originalStreamAgentRunEvents
  }
})

test('旧 Run 的延迟 AbortError 不覆盖新 Run 状态', async () => {
  const threadState = {
    activeRunId: null,
    activeRunSteerable: false,
    runLastSeq: '0-0',
    runStreamAbortController: null,
    replyLoadingVisible: false,
    pendingRequestId: null,
    onGoingConv: { msgChunks: {} }
  }
  const streamControllers = new Map()
  const originalStreamAgentRunEvents = agentApi.streamAgentRunEvents
  agentApi.streamAgentRunEvents = async (runId, _afterSeq, { signal }) =>
    new Response(
      new ReadableStream({
        start(controller) {
          streamControllers.set(runId, controller)
          signal.addEventListener('abort', () => {
            const delay = runId === 'run-1' ? 10 : 0
            setTimeout(() => controller.error(new DOMException('aborted', 'AbortError')), delay)
          })
          if (runId === 'run-2') {
            controller.enqueue(
              new TextEncoder().encode(
                'event: custom\ndata: {"run_id":"run-2","request_id":"request-2","payload":{"chunk":{"status":"init","msg":{"type":"human","content":"new"}}}}\n\n'
              )
            )
          }
        }
      }),
      { headers: { 'Content-Type': 'text/event-stream' } }
    )

  const runStream = createRunStream({
    threadState,
    handleStreamChunk: (chunk) => {
      if (chunk.status !== 'init') return
      threadState.pendingRequestId = chunk.request_id
      threadState.replyLoadingVisible = true
    },
    resetOnGoingConv: () => {}
  })

  try {
    const oldRun = runStream.startRunStream('thread-1', 'run-1')
    await new Promise((resolve) => setTimeout(resolve, 0))
    const newRun = runStream.startRunStream('thread-1', 'run-2')
    await new Promise((resolve) => setTimeout(resolve, 20))

    assert.equal(threadState.activeRunId, 'run-2')
    assert.equal(threadState.pendingRequestId, 'request-2')
    assert.equal(threadState.replyLoadingVisible, true)

    threadState.runStreamAbortController.abort()
    await Promise.allSettled([oldRun, newRun])
  } finally {
    agentApi.streamAgentRunEvents = originalStreamAgentRunEvents
  }
})

test('旧 Run 终态清理保留排队 Request SSE', async () => {
  const threadState = {
    activeRunId: null,
    activeRunSteerable: false,
    runLastSeq: '0-0',
    runStreamAbortController: null,
    replyLoadingVisible: false,
    pendingRequestId: null,
    pendingInterrupt: null,
    requestStreams: { 'request-2': { controller: new AbortController() } }
  }
  const resetCalls = []
  const originalStreamAgentRunEvents = agentApi.streamAgentRunEvents
  agentApi.streamAgentRunEvents = async () =>
    new Response('event: end\ndata: {"run_id":"run-1","payload":{"status":"completed"}}\n\n', {
      headers: { 'Content-Type': 'text/event-stream' }
    })

  try {
    const runStream = createRunStream({
      threadState,
      handleStreamChunk: () => {},
      resetOnGoingConv: (_threadId, options) => resetCalls.push(options)
    })

    await runStream.startRunStream('thread-1', 'run-1')
    await new Promise((resolve) => setTimeout(resolve, 0))

    assert.deepEqual(resetCalls, [{ preserveRequestStreams: true }])
    assert.equal(threadState.requestStreams['request-2'].controller.signal.aborted, false)
  } finally {
    agentApi.streamAgentRunEvents = originalStreamAgentRunEvents
  }
})

for (const reuseCursor of [false, true]) {
  test(`数据库补发 end ${reuseCursor ? '复用游标会被丢弃（缺陷对照）' : '无游标时直接结束生成'}`, async () => {
    const threadState = {
      activeRunId: null,
      runLastSeq: '0-0',
      runStreamAbortController: null,
      replyLoadingVisible: true,
      onGoingConv: { msgChunks: {} }
    }
    const originalStream = agentApi.streamAgentRunEvents
    const originalGetRun = agentApi.getAgentRun
    let statusReads = 0
    const chunks = []
    const message =
      'event: messages\nid: 1700000000002-0\ndata: {"payload":{"chunk":{"content":"final"}}}\n\n'
    const end = `event: end\n${reuseCursor ? 'id: 1700000000002-0\n' : ''}data: {"payload":{"status":"completed"}}\n\n`
    agentApi.streamAgentRunEvents = async () => new Response(message + message + end)
    agentApi.getAgentRun = async () => {
      statusReads += 1
      return { run: { id: 'run-fallback', status: 'completed' } }
    }
    try {
      const stream = createRunStream({
        threadState,
        handleStreamChunk: (chunk) => chunks.push(chunk),
        resetOnGoingConv: () => {}
      })
      await stream.startRunStream('thread-fallback', 'run-fallback')
      assert.equal(statusReads, reuseCursor ? 1 : 0)
      assert.equal(chunks.length, 1)
      assert.equal(chunks[0].content, 'final')
      assert.equal(threadState.activeRunId, null)
      assert.equal(threadState.isStreaming, false)
      assert.equal(threadState.replyLoadingVisible, false)
      assert.equal(localStorage.getItem('active_run:thread-fallback'), null)
    } finally {
      agentApi.streamAgentRunEvents = originalStream
      agentApi.getAgentRun = originalGetRun
    }
  })
}

test('自然断流后从 PG 终态复用统一清理并刷新历史', async () => {
  const threadState = {
    activeRunId: null,
    activeRunSteerable: true,
    runLastSeq: '0-0',
    runStreamAbortController: null,
    replyLoadingVisible: true,
    pendingRequestId: 'request-1',
    pendingInterrupt: null,
    onGoingConv: { msgChunks: { 'message-1': [{ content: '实时内容' }] } }
  }
  const refreshed = []
  const notifications = []
  const resetCalls = []
  const originalStreamAgentRunEvents = agentApi.streamAgentRunEvents
  const originalGetAgentRun = agentApi.getAgentRun
  agentApi.streamAgentRunEvents = async () =>
    new Response('', { headers: { 'Content-Type': 'text/event-stream' } })
  agentApi.getAgentRun = async () => ({
    run: { id: 'run-1', status: 'completed' }
  })

  try {
    const runStream = useAgentRunStream({
      getThreadState: () => threadState,
      currentAgentId: { value: 'agent-1' },
      handleStreamChunk: () => {},
      fetchThreadMessages: async () => refreshed.push('history'),
      fetchAgentState: async () => refreshed.push('state'),
      resetOnGoingConv: (_threadId, options) => resetCalls.push(options),
      onScrollToBottom: () => {},
      streamSmoother: { flushThread: () => {} },
      onTerminalDetected: (payload) => notifications.push(payload)
    })

    await runStream.startRunStream('thread-1', 'run-1')
    await new Promise((resolve) => setTimeout(resolve, 0))

    assert.equal(threadState.activeRunId, null)
    assert.equal(threadState.isStreaming, false)
    assert.equal(threadState.replyLoadingVisible, false)
    assert.deepEqual(resetCalls, [{ preserveRequestStreams: true }])
    assert.deepEqual(refreshed, ['history', 'state'])
    assert.deepEqual(
      notifications.map(({ runId }) => runId),
      ['run-1']
    )
  } finally {
    agentApi.streamAgentRunEvents = originalStreamAgentRunEvents
    agentApi.getAgentRun = originalGetAgentRun
  }
})

test('自然断流遇到仍持有的 pending interrupt 时保留 Run 快照', async () => {
  const threadId = 'thread-with-pending-interrupt'
  const threadState = {
    activeRunId: null,
    activeRunSteerable: true,
    runLastSeq: '5-0',
    runStreamAbortController: null,
    replyLoadingVisible: true,
    pendingRequestId: 'request-1',
    pendingInterrupt: { interruptedRunId: 'run-1', questions: [{ question: '继续吗？' }] },
    onGoingConv: { msgChunks: {} }
  }
  const interrupts = []
  const originalStreamAgentRunEvents = agentApi.streamAgentRunEvents
  const originalGetAgentRun = agentApi.getAgentRun
  agentApi.streamAgentRunEvents = async () =>
    new Response('', { headers: { 'Content-Type': 'text/event-stream' } })
  agentApi.getAgentRun = async () => ({ run: { id: 'run-1', status: 'interrupted' } })

  try {
    const runStream = useAgentRunStream({
      getThreadState: () => threadState,
      currentAgentId: { value: 'agent-1' },
      handleStreamChunk: () => {},
      fetchThreadMessages: async () => {},
      fetchAgentState: async () => {},
      resetOnGoingConv: () => {},
      onScrollToBottom: () => {},
      streamSmoother: { flushThread: () => {} },
      onInterruptDetected: ({ runId }) => interrupts.push(runId)
    })

    await runStream.startRunStream(threadId, 'run-1')

    assert.equal(threadState.activeRunId, 'run-1')
    assert.equal(threadState.isStreaming, false)
    assert.deepEqual(interrupts, ['run-1'])
    assert.equal(JSON.parse(localStorage.getItem(`active_run:${threadId}`)).run_id, 'run-1')
  } finally {
    agentApi.streamAgentRunEvents = originalStreamAgentRunEvents
    agentApi.getAgentRun = originalGetAgentRun
    localStorage.removeItem(`active_run:${threadId}`)
  }
})

test('恢复时没有 active Run 也走统一终态清理', async () => {
  const threadId = 'thread-without-active-run'
  const threadState = {
    activeRunId: 'run-old',
    activeRunSteerable: false,
    runLastSeq: '22-0',
    runStreamAbortController: null,
    isStreaming: true,
    replyLoadingVisible: true,
    pendingRequestId: 'request-old',
    pendingInterrupt: { interruptedRunId: 'run-old' },
    onGoingConv: { msgChunks: {} }
  }
  const refreshed = []
  const notifications = []
  const originalGetThreadActiveRun = agentApi.getThreadActiveRun
  agentApi.getThreadActiveRun = async () => ({ run: null })
  localStorage.removeItem(`active_run:${threadId}`)

  try {
    const runStream = useAgentRunStream({
      getThreadState: () => threadState,
      currentAgentId: { value: 'agent-1' },
      handleStreamChunk: () => {},
      fetchThreadMessages: async () => refreshed.push('history'),
      fetchAgentState: async () => refreshed.push('state'),
      resetOnGoingConv: () => {},
      onScrollToBottom: () => {},
      streamSmoother: { flushThread: () => {} },
      onTerminalDetected: (payload) => notifications.push(payload)
    })

    await runStream.resumeActiveRunForThread(threadId)
    await new Promise((resolve) => setTimeout(resolve, 0))

    assert.equal(threadState.activeRunId, null)
    assert.equal(threadState.isStreaming, false)
    assert.equal(threadState.runLastSeq, '0-0')
    assert.equal(threadState.pendingInterrupt, null)
    assert.deepEqual(refreshed, ['history', 'state'])
    assert.deepEqual(
      notifications.map(({ runId }) => runId),
      [null]
    )
  } finally {
    agentApi.getThreadActiveRun = originalGetThreadActiveRun
    localStorage.removeItem(`active_run:${threadId}`)
  }
})

test('恢复期间出现的新 Run 不会被旧的空闲查询结果清理', async () => {
  const threadId = 'thread-with-new-run'
  const threadState = {
    activeRunId: 'run-old',
    activeRunSteerable: true,
    runLastSeq: '22-0',
    runStreamAbortController: null,
    isStreaming: true,
    replyLoadingVisible: true,
    pendingRequestId: 'request-new',
    pendingInterrupt: null,
    onGoingConv: { msgChunks: {} }
  }
  const refreshed = []
  const originalGetThreadActiveRun = agentApi.getThreadActiveRun
  agentApi.getThreadActiveRun = async () => {
    threadState.activeRunId = 'run-new'
    return { run: null }
  }
  localStorage.removeItem(`active_run:${threadId}`)

  try {
    const runStream = useAgentRunStream({
      getThreadState: () => threadState,
      currentAgentId: { value: 'agent-1' },
      handleStreamChunk: () => {},
      fetchThreadMessages: async () => refreshed.push('history'),
      fetchAgentState: async () => refreshed.push('state'),
      resetOnGoingConv: () => {},
      onScrollToBottom: () => {},
      streamSmoother: { flushThread: () => {} }
    })

    await runStream.resumeActiveRunForThread(threadId)

    assert.equal(threadState.activeRunId, 'run-new')
    assert.equal(threadState.isStreaming, true)
    assert.deepEqual(refreshed, [])
  } finally {
    agentApi.getThreadActiveRun = originalGetThreadActiveRun
    localStorage.removeItem(`active_run:${threadId}`)
  }
})

test('同步队列保留尚未收到接入响应的发送项，并以服务端已接收请求去重', async () => {
  const threadState = {
    queuedRequests: [
      { request_id: 'sending', status: 'sending', content: '正在提交' },
      { request_id: 'accepted', status: 'sending', content: '已接收' }
    ]
  }
  const original = agentApi.listThreadQueuedRequests
  agentApi.listThreadQueuedRequests = async () => ({
    requests: [{ request_id: 'accepted', status: 'queued' }]
  })
  try {
    const queue = useAgentRequestQueue({ getThreadState: () => threadState })
    await queue.syncQueuedRequests('thread-1', 'agent-1')
    assert.deepEqual(
      threadState.queuedRequests.map(({ request_id, status }) => [request_id, status]),
      [
        ['accepted', 'queued'],
        ['sending', 'sending']
      ]
    )
  } finally {
    agentApi.listThreadQueuedRequests = original
  }
})

test('接入未完成的发送项只展示，不订阅或取消尚未持久化的 Request', async () => {
  const threadState = { queuedRequests: [{ request_id: 'sending', status: 'sending' }] }
  const originals = [
    agentApi.listThreadQueuedRequests,
    agentApi.streamRequestEvents,
    agentApi.cancelRequest
  ]
  const unexpected = []
  agentApi.listThreadQueuedRequests = async () => ({ requests: [] })
  agentApi.streamRequestEvents = async () => {
    unexpected.push('stream')
    throw new Error('请求尚未入库')
  }
  agentApi.cancelRequest = async () => {
    unexpected.push('cancel')
    throw new Error('请求尚未入库')
  }
  try {
    const queue = useAgentRequestQueue({ getThreadState: () => threadState })
    await queue.resumeQueuedRequests('thread-1', 'agent-1')
    assert.equal(await queue.cancelRequest('thread-1', 'sending'), false)
    assert.deepEqual(unexpected, [])
    assert.deepEqual(threadState.queuedRequests, [{ request_id: 'sending', status: 'sending' }])
  } finally {
    ;[agentApi.listThreadQueuedRequests, agentApi.streamRequestEvents, agentApi.cancelRequest] =
      originals
  }
})

for (const images of [['A'], ['A', 'B']]) {
  test(`排队消息经过同步、派发和 init 后保留 ${images.length} 张图片及附件`, async () => {
    const message = {
      id: 'request-images',
      type: 'human',
      request_id: 'request-images',
      content: '比较图片',
      image_contents: images,
      image_content: images[0],
      message_type: 'multimodal_image',
      extra_metadata: { attachments: [{ file_id: 'attachment-1' }] }
    }
    const threadState = {
      queuedRequests: [{ request_id: 'request-images', status: 'sending', message }],
      requestStreams: {},
      onGoingConv: { msgChunks: {} }
    }
    const originals = [agentApi.listThreadQueuedRequests, agentApi.streamRequestEvents]
    agentApi.listThreadQueuedRequests = async () => ({
      requests: [{ request_id: 'request-images', status: 'queued', content: '比较图片', queue_position: 2 }]
    })
    agentApi.streamRequestEvents = async () =>
      new Response('event: run_created\ndata: {"run_id":"run-images"}\n\n')
    try {
      const queue = useAgentRequestQueue({
        getThreadState: () => threadState,
        resetOnGoingConv: () => { threadState.onGoingConv = { msgChunks: {} } },
        startRunStream: () => {}
      })
      await queue.syncQueuedRequests('thread-images', 'agent-1')
      assert.equal(threadState.queuedRequests[0].status, 'queued')
      assert.equal(threadState.queuedRequests[0].queue_position, 2)
      await queue.startRequestStream('thread-images', 'request-images')
      const [dispatched] = threadState.onGoingConv.msgChunks['request-images']
      assert.deepEqual(dispatched.image_contents, images)
      assert.deepEqual(dispatched.extra_metadata.attachments, [{ file_id: 'attachment-1' }])
      assert.deepEqual(threadState.queuedRequests, [])
      const { handleStreamChunk } = useAgentStreamHandler({ getThreadState: () => threadState })
      handleStreamChunk({
        status: 'init', request_id: 'request-images',
        msg: { id: 'persisted-id', type: 'human', content: '比较图片' }
      }, 'thread-images')
      const [initialized] = threadState.onGoingConv.msgChunks['request-images']
      assert.equal(initialized.id, 'persisted-id')
      assert.deepEqual(initialized.image_contents, images)
    } finally {
      ;[agentApi.listThreadQueuedRequests, agentApi.streamRequestEvents] = originals
    }
  })
}

test('取消排队请求释放其本地用户消息，不影响其他请求', async () => {
  const threadState = {
    queuedRequests: [
      { request_id: 'cancelled', status: 'queued', message: { image_contents: ['A'] } },
      { request_id: 'remaining', status: 'queued', message: { image_contents: ['B'] } }
    ],
    requestStreams: {},
    onGoingConv: { msgChunks: {} }
  }
  const original = agentApi.cancelRequest
  agentApi.cancelRequest = async () => ({})
  try {
    const queue = useAgentRequestQueue({ getThreadState: () => threadState })
    assert.equal(await queue.cancelRequest('thread-1', 'cancelled'), true)
    assert.deepEqual(threadState.queuedRequests.map((request) => request.message.image_contents), [['B']])
  } finally {
    agentApi.cancelRequest = original
  }
})

for (const action of ['resumeQueuedRequests', 'continueQueue', 'steerRequest']) {
  test(`${action} 在派发后的空快照到达时保留请求消息直到 run_created`, async () => {
    const message = { type: 'human', content: '图片', image_contents: ['A', 'B'] }
    const threadState = {
      queuedRequests: [{ request_id: 'images', status: 'queued', message }],
      requestStreams: {}, onGoingConv: { msgChunks: {} }
    }
    const originals = [agentApi.listThreadQueuedRequests, agentApi.streamRequestEvents,
      agentApi.continueThreadQueue, agentApi.steerRequest]
    let controller
    const dispatched = Promise.withResolvers()
    agentApi.listThreadQueuedRequests = async () => ({ requests: [] })
    agentApi.streamRequestEvents = async () => new Response(new ReadableStream({
      start(value) { controller = value }
    }))
    agentApi.continueThreadQueue = async () => ({ request_id: 'images' })
    agentApi.steerRequest = async () => ({})
    try {
      const queue = useAgentRequestQueue({
        getThreadState: () => threadState,
        resetOnGoingConv: () => { threadState.onGoingConv = { msgChunks: {} } },
        startRunStream: () => dispatched.resolve()
      })
      await queue[action]('thread', 'agent', 'images')
      assert.deepEqual(threadState.queuedRequests, [])
      assert.ok(controller, '同步前必须订阅已接入的本地请求')
      controller.enqueue(new TextEncoder().encode('event: run_created\ndata: {"run_id":"run-images"}\n\n'))
      controller.close()
      await dispatched.promise
      assert.deepEqual(threadState.onGoingConv.msgChunks.images[0].image_contents, ['A', 'B'])
      assert.equal(threadState.requestStreams.images, undefined)
    } finally {
      ;[agentApi.listThreadQueuedRequests, agentApi.streamRequestEvents,
        agentApi.continueThreadQueue, agentApi.steerRequest] = originals
    }
  })
}

for (const agentId of [
  'health-consultation',
  'health-blood-glucose',
  'health-blood-lipids',
  'health-blood-pressure'
]) {
  for (const terminal of ['end', 'eof', 'failed']) {
    test(`健康校验后发布 ${agentId} ${terminal} 无正文流仍等待并从历史取得最终结果`, { timeout: 10000 }, async (t) => {
      const threadId = `validated-${agentId}-${terminal}`
      const runId = `run-${threadId}`
      const requestId = `request-${threadId}`
      const state = useAgentThreadState({
        chatState: { threadStates: {} },
        getCurrentThreadId: () => threadId
      })
      const ts = state.getThreadState(threadId)
      const userMessage = { id: requestId, type: 'human', content: '回顾我的记录' }
      ts.onGoingConv.msgChunks[requestId] = [userMessage]
      const finalMessage = {
        id: `output-${threadId}`,
        type: 'ai',
        content: '已核对来源的记录回顾',
        run_id: runId
      }
      let controller
      let committed = false
      const history = []
      const reads = []
      const refreshed = Promise.withResolvers()
      const enqueue = (event, payload, seq) => controller.enqueue(new TextEncoder().encode(
        `id: ${seq}\nevent: ${event}\ndata: ${JSON.stringify({
          run_id: runId, request_id: requestId, thread_id: threadId, payload
        })}\n\n`
      ))
      t.mock.method(agentApi, 'streamAgentRunEvents', async (_runId, _cursor, { signal }) => new Response(new ReadableStream({
        start(value) {
          controller = value
          signal.addEventListener('abort', () => controller.error(new DOMException('aborted', 'AbortError')), { once: true })
          enqueue('custom', { name: 'yuxi.init', chunk: { status: 'init' } }, '1-0')
          enqueue('custom', {
            name: 'yuxi.health_progress',
            chunk: { status: 'health_progress', phase: 'running', message: '正在回顾记录与审核知识' }
          }, '1-1')
        }
      })))
      t.mock.method(agentApi, 'createAgentRun', () => assert.fail('终态恢复不得重新提交请求'))
      t.mock.method(agentApi, 'getAgentRun', async (id) => {
        assert.equal(id, runId)
        assert.equal(committed, true)
        return { run: { id, status: 'completed' } }
      })
      const handler = useAgentStreamHandler({ getThreadState: state.getThreadState, currentAgentId: ref(agentId) })
      const runStream = useAgentRunStream({
        getThreadState: state.getThreadState,
        currentAgentId: ref(agentId),
        handleStreamChunk: handler.handleStreamChunk,
        fetchThreadMessages: async ({ agentId: selectedAgentId, threadId: selectedThreadId }) => {
          assert.equal(committed, true, '仅终态后回读权威历史')
          assert.equal(selectedAgentId, agentId)
          assert.equal(selectedThreadId, threadId)
          reads.push(selectedThreadId)
          history.push(userMessage, ...(terminal === 'failed' ? [] : [finalMessage]))
          return true
        },
        fetchAgentState: async () => {},
        resetOnGoingConv: state.resetOnGoingConv,
        onScrollToBottom: () => {},
        onTerminalDetected: () => refreshed.resolve()
      })
      const pending = runStream.startRunStream(threadId, runId)
      try {
        await settleRecovery()
        assert.equal(ts.replyLoadingVisible, true)
        assert.equal(ts.isStreaming, true)
        assert.equal(ts.activeRunId, runId)
        assert.deepEqual(Object.values(ts.onGoingConv.msgChunks).flat().map((message) => message.type), ['human'])
        assert.deepEqual(history, [])
        assert.deepEqual(reads, [])

        enqueue('custom', {
          name: 'yuxi.health_progress',
          chunk: { status: 'health_progress', phase: 'validating', message: '正在校验答复来源与引用' }
        }, '1-2')
        await settleRecovery()
        assert.equal(ts.replyLoadingVisible, true)
        assert.deepEqual(Object.values(ts.onGoingConv.msgChunks).flat().map((message) => message.type), ['human'])

        committed = true
        if (terminal !== 'eof') {
          enqueue('end', {
            status: terminal === 'failed' ? 'failed' : 'completed'
          }, '1-3')
        }
        controller.close()
        await pending
        await refreshed.promise
        assert.equal(ts.replyLoadingVisible, false)
        assert.equal(ts.isStreaming, false)
        assert.equal(ts.activeRunId, null)
        assert.deepEqual(ts.onGoingConv.msgChunks, {})
        assert.deepEqual(reads, [threadId])
        assert.deepEqual(history.filter((message) => message.type === 'ai'), terminal === 'failed' ? [] : [finalMessage])
        assert.equal(agentApi.getAgentRun.mock.callCount(), terminal === 'eof' ? 1 : 0)
        assert.equal(localStorage.getItem(`active_run:${threadId}`), null)
      } finally {
        runStream.stopRunStreamSubscription(threadId)
        await pending
        localStorage.removeItem(`active_run:${threadId}`)
      }
    })
  }
}
