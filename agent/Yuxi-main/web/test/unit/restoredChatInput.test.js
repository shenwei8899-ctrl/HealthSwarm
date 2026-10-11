import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import process from 'node:process'
import { before, after, test } from 'node:test'
import { setImmediate } from 'node:timers/promises'
import { computed, reactive, ref, nextTick } from 'vue'
import { createServer } from 'vite'

/** 负控在内存中恢复目标缺陷，不改运行页面或源码文件。 */
function negativeControl(source, owner) {
  source = source.replaceAll('\r\n', '\n')
  const mutation = process.env.RESTORE_INPUT_NEGATIVE_CONTROL
  if (owner === 'component') {
    const replacements = {
      'wait-stream': ['background: true, isCurrent:', 'background: false, isCurrent:'],
      'component-generation': ['selectionVersion === threadSelectionVersion && ', ''],
      'config-selection': [
        'await agentStore.fetchAgentDetail(targetChat.agent_id)\n        if (!isCurrentSelection()) return',
        'await agentStore.fetchAgentDetail(targetChat.agent_id)'
      ],
      'state-publication': ['      !isCurrent() ||\n      !selectionIsCurrent() ||', ''],
      'strict-state-read': ['required || failOnError', 'required'],
      'strict-attachment-read': ['if (required) throw error', ''],
      'readiness-guard': [
        '    (currentChatId.value && initializedThreadId.value !== currentChatId.value) ||',
        ''
      ],
      'current-send-binding': ['agent_slug: agentSlug', 'agent_slug: currentAgentId.value'],
      'current-health-binding': ['if (!healthRole &&', 'if (!isHealthRole.value &&'],
      'create-ready': ['    initializedThreadId.value = thread.id', ''],
      'unmount-selection': ['  threadSelectionVersion += 1', '']
    }
    if (mutation === 'history-publication' || mutation === 'attachment-publication') {
      const start = source.indexOf(
        mutation === 'history-publication'
          ? 'const fetchThreadMessages ='
          : 'const fetchThreadAttachments ='
      )
      return (
        source.slice(0, start) +
        source
          .slice(start)
          .replace(
            mutation === 'history-publication'
              ? '    if (!isCurrent() || !selectionIsCurrent()) return false'
              : '    if (!isCurrent() || !selectionIsCurrent()) return',
            ''
          )
      )
    }
    if (replacements[mutation]) return source.replaceAll(...replacements[mutation])
  }
  if (owner === 'view' && process.env.RESTORE_INPUT_NEGATIVE_CONTROL === 'route-generation') {
    return source
      .replaceAll('    if (!isCurrentSync()) return', '')
      .replace(
        'if (isCurrentSync()) syncingRouteThread.value = false',
        'syncingRouteThread.value = false'
      )
  }
  if (owner === 'run') {
    if (mutation === 'stream-ownership')
      return source
        .replace('!runController.signal.aborted &&', 'true &&')
        .replace(
          '      getThreadState(threadId) === ts &&\n      ts.runStreamAbortController === runController &&\n      options.isCurrent?.() !== false',
          '      true'
        )
    if (mutation === 'reconnect-selection')
      return source
        .replaceAll('options.isCurrent?.() === false', 'false')
        .replaceAll('options.isCurrent?.() !== false', 'true')
    if (mutation === 'terminal-refresh-current')
      return source.replace('published === false || !isCurrent()', '!isCurrent()')
    if (mutation === 'run-recovery-current') return source.replace('      isCurrent() &&', '')
    if (mutation === 'strict-active-read')
      return source
        .replaceAll('        if (background) throw e', '')
        .replaceAll('      if (background) throw e', '')
  }
  if (owner === 'queue') {
    if (mutation === 'queue-recovery-current')
      return source.replaceAll('!isCurrent() || ', '').replace('    if (!isCurrent()) return', '')
    if (mutation === 'strict-queue-read') return source.replace('      if (required) throw e', '')
  }
  return source
}

const component = negativeControl(
  readFileSync(new URL('../../src/components/AgentChatComponent.vue', import.meta.url), 'utf8'),
  'component'
)
const view = negativeControl(
  readFileSync(new URL('../../src/views/AgentView.vue', import.meta.url), 'utf8'),
  'view'
)
let server,
  agentApi,
  threadApi,
  ErrorHandler,
  useAgentRunStream,
  useAgentRequestQueue,
  useAgentThreadState

before(async () => {
  const storage = new Map()
  globalThis.localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key)
  }
  server = await createServer({
    server: { middlewareMode: true, hmr: false },
    optimizeDeps: { noDiscovery: true, include: [] },
    plugins: [
      {
        name: 'restore-input-negative-control',
        enforce: 'pre',
        transform(code, id) {
          if (id.endsWith('/useAgentRunStream.js')) return negativeControl(code, 'run')
          if (id.endsWith('/useAgentRequestQueue.js')) return negativeControl(code, 'queue')
        }
      }
    ]
  })
  ;({ agentApi, threadApi } = await server.ssrLoadModule('/src/apis/index.js'))
  ;({ ErrorHandler } = await server.ssrLoadModule('/src/utils/errorHandler.js'))
  ;({ useAgentRunStream } = await server.ssrLoadModule('/src/composables/useAgentRunStream.js'))
  ;({ useAgentRequestQueue } = await server.ssrLoadModule(
    '/src/composables/useAgentRequestQueue.js'
  ))
  ;({ useAgentThreadState } = await server.ssrLoadModule('/src/composables/useAgentThreadState.js'))
})

after(async () => {
  await server?.close()
  delete globalThis.localStorage
})

/** 用实际选择方法和恢复 composable 装配合成会话，长流保持打开。 */
function chat(t, { source = component, active = true, realTerminalRefresh = false } = {}) {
  const currentThreadId = ref(null),
    currentAgentId = ref('default')
  const threads = ref([
    { id: 'a', agent_id: 'health-consultation', metadata: { health_member_id: 'member-a' } },
    { id: 'b', agent_id: 'health-diet-analyst', metadata: { health_member_id: 'member-b' } }
  ])
  const userStore = reactive({ uid: 'synthetic-user', isLoggedIn: true })
  const chatUIStore = reactive({ isLoadingMessages: false })
  const threadMessages = ref({}),
    threadRuns = ref({}),
    threadAttachmentsMap = ref({})
  let refreshMessages = async () => {},
    refreshState = async () => {}
  const notifications = []
  const errors = [],
    streams = [],
    requestStreams = [],
    chunks = [],
    details = new Map(),
    viewed = []
  const state = useAgentThreadState({
    chatState: reactive({ threadStates: {} }),
    getCurrentThreadId: () => currentThreadId.value
  })
  const handleChatError = (error) => errors.push(error.message)
  const run = useAgentRunStream({
    ...state,
    currentAgentId,
    handleStreamChunk: (chunk) => chunks.push(chunk),
    fetchThreadMessages: (...args) => refreshMessages(...args),
    fetchAgentState: (...args) => refreshState(...args),
    onTerminalDetected: () => notifications.push('terminal'),
    onInterruptDetected: () => notifications.push('interrupt'),
    onScrollToBottom: () => {},
    streamSmoother: { flushThread() {} }
  })
  const queue = useAgentRequestQueue({ ...state, startRunStream: run.startRunStream })
  t.mock.method(agentApi, 'getAgentHistory', async (id) => ({
    history: [{ content: `history-${id}` }],
    runs: [],
    thread: threads.value.find((thread) => thread.id === id)
  }))
  t.mock.method(agentApi, 'getThreadActiveRun', async (id) => ({
    run: active ? { id: `run-${id}`, status: 'running' } : null
  }))
  t.mock.method(agentApi, 'getAgentRun', async (id) => ({ run: { id, status: 'running' } }))
  t.mock.method(agentApi, 'listThreadQueuedRequests', async () => ({ requests: [] }))
  t.mock.method(agentApi, 'getAgentState', async () => ({ agent_state: {}, interrupt: null }))
  t.mock.method(threadApi, 'getThreadAttachments', async () => ({ attachments: [] }))
  t.mock.method(agentApi, 'streamAgentRunEvents', async (id, _seq, { signal }) => {
    streams.push(id)
    return new Response(
      new ReadableStream({
        start(controller) {
          signal.addEventListener('abort', () => controller.close(), { once: true })
        }
      })
    )
  })
  t.mock.method(agentApi, 'streamRequestEvents', async (id, { signal }) => {
    requestStreams.push(id)
    return new Response(
      new ReadableStream({
        start(controller) {
          signal.addEventListener('abort', () => controller.close(), { once: true })
        }
      })
    )
  })
  const agentStore = {
    isInitialized: true,
    async fetchAgentDetail(id) {
      details.set(id, {})
      return details.get(id)
    },
    async selectAgent(id) {
      if (!details.has(id)) await this.fetchAgentDetail(id)
      currentAgentId.value = id
    }
  }
  const chatThreadsStore = { upsertThread() {}, markThreadViewed: async (id) => viewed.push(id) }
  const environment = {
    ref,
    nextTick,
    agentApi,
    threadApi,
    userStore,
    agentStore,
    chatUIStore,
    chatThreadsStore,
    threads,
    currentAgentId,
    currentThreadId,
    threadMessages,
    threadRuns,
    threadAttachmentsMap,
    currentChatId: computed(() => currentThreadId.value),
    extractPendingInterrupt: () => null,
    threadCreationInFlight: ref(false),
    props: { singleMode: false },
    message: { info() {} },
    AgentValidator: { validateAgentIdWithError: () => true },
    handleValidationError: assert.fail,
    handleChatError,
    withConfigNoticeSync: async (task) => task(),
    setCurrentThreadId: (id) => {
      currentThreadId.value = id
    },
    resetAgentPanelState() {},
    syncThreadConfigSnapshot() {},
    ...state,
    ...run,
    ...queue,
    resolveAgentSlugForThread: (id) => threads.value.find((thread) => thread.id === id)?.agent_id,
    scrollController: { scrollToBottomStaticForce: async () => {} },
    handleAgentStateRefresh: async () => {},
    restorePendingInterruptForThread() {},
    initAll: async () => {},
    loadChatsList: async () => {},
    initializedThreadId: ref('')
  }
  const history = source.slice(
    source.indexOf('const fetchThreadMessages ='),
    source.indexOf('// 把草稿线程')
  )
  const capture = source.slice(
    source.indexOf('const captureThreadSelection ='),
    source.indexOf('// ==================== LOCAL CHAT')
  )
  const attachments = source.slice(
    source.indexOf('const fetchThreadAttachments ='),
    source.indexOf('const handleArtifactSaved =')
  )
  const agentState = source.slice(
    source.indexOf('const fetchAgentState ='),
    source.indexOf('const createActiveThread =')
  )
  const selection = source.slice(
    source.indexOf('const selectChat ='),
    source.indexOf('const handleSendMessage =')
  )
  const unmount = source.slice(
    source.indexOf('onUnmounted(() => {') + 'onUnmounted(() => {'.length,
    source.indexOf(
      '  stopReplyElapsedTimer({ reset: true })',
      source.indexOf('onUnmounted(() => {')
    )
  )
  const methods = new Function(
    ...Object.keys(environment),
    `let threadSelectionVersion = 0;\n${capture}\n${history}\n${attachments}\n${agentState}\n${selection}\nreturn { selectChat, selectThreadFromRoute, fetchThreadMessages, fetchAgentState, fetchThreadAttachments, unmount: () => {${unmount}} }`
  )(...Object.values(environment))
  if (realTerminalRefresh) {
    refreshMessages = methods.fetchThreadMessages
    refreshState = methods.fetchAgentState
  }
  t.after(async () => {
    for (const id of ['a', 'b']) {
      run.stopRunStreamSubscription(id)
      queue.stopAllRequestStreams(id)
      localStorage.removeItem(`active_run:${id}`)
    }
    await setImmediate()
  })
  return {
    ...environment,
    ...methods,
    streams,
    requestStreams,
    chunks,
    errors,
    details,
    viewed,
    notifications
  }
}

/** 实际页面同步方法拥有发送锁，子组件初始化返回后才解锁。 */
function page(selectThreadFromRoute, source = view) {
  const route = reactive({ params: { thread_id: 'a' } }),
    syncingRouteThread = ref(false)
  const replaces = []
  const environment = {
    chatComponentRef: ref({ selectThreadFromRoute }),
    route,
    syncingRouteThread,
    getRouteThreadId: () => route.params.thread_id,
    agentStore: { isInitialized: true },
    router: { replace: async (target) => replaces.push(target) },
    handleChatError: assert.fail
  }
  const block = source.slice(
    source.indexOf('const syncSelectedThreadFromRoute ='),
    source.indexOf('const consumeRouteAgentSelection =')
  )
  const sync = new Function(
    ...Object.keys(environment),
    `let routeThreadSyncVersion = 0;\n${block}\nreturn syncSelectedThreadFromRoute`
  )(...Object.values(environment))
  return { route, syncingRouteThread, replaces, sync }
}

test('活跃 Run 初始恢复完成后解锁，流保持运行且成员绑定未变', async (t) => {
  const c = chat(t),
    p = page(c.selectThreadFromRoute)
  let settled = false
  const selection = p.sync().then(() => {
    settled = true
  })
  await setImmediate()
  const observed = {
    settled,
    disabled: p.syncingRouteThread.value,
    run: c.getThreadState('a').activeRunId
  }
  c.stopRunStreamSubscription('a')
  await selection
  assert.deepEqual(observed, { settled: true, disabled: false, run: 'run-a' })
  assert.deepEqual(c.streams, ['run-a'])
  assert.equal(c.currentAgentId.value, 'health-consultation')
  assert.equal(c.threads.value[0].metadata.health_member_id, 'member-a')
  assert.equal(c.threadMessages.value.a[0].content, 'history-a')
})

test('既有默认恢复仍等待持续 Run 流，停止订阅后返回', async (t) => {
  const c = chat(t)
  let settled = false
  const pending = c.resumeActiveRunForThread('a').then(() => {
    settled = true
  })
  await setImmediate()
  assert.equal(c.getThreadState('a').activeRunId, 'run-a')
  assert.equal(settled, false)
  c.stopRunStreamSubscription('a')
  await pending
  assert.equal(settled, true)
})

for (const stage of ['detail', 'history', 'state', 'attachments', 'active-run', 'queue']) {
  test(`初始 ${stage} 未确认时保持发送锁，读完后解锁`, async (t) => {
    const c = chat(t),
      p = page(c.selectThreadFromRoute),
      gate = Promise.withResolvers()
    const target =
      stage === 'detail' ? c.agentStore : stage === 'attachments' ? threadApi : agentApi
    const method = {
      detail: 'fetchAgentDetail',
      history: 'getAgentHistory',
      state: 'getAgentState',
      attachments: 'getThreadAttachments',
      'active-run': 'getThreadActiveRun',
      queue: 'listThreadQueuedRequests'
    }[stage]
    const original = target[method].bind(target)
    t.mock.method(target, method, async (...args) => {
      await gate.promise
      return original(...args)
    })
    const selection = p.sync()
    await setImmediate()
    assert.equal(p.syncingRouteThread.value, true)
    assert.equal(c.initializedThreadId.value, '')
    gate.resolve()
    await selection
    assert.equal(p.syncingRouteThread.value, false)
    assert.equal(c.initializedThreadId.value, 'a')
  })
}

for (const stage of ['history', 'state', 'attachments', 'active-run', 'queue']) {
  test(`初始 ${stage} 失败明确拒绝当前线程就绪`, async (t) => {
    const c = chat(t)
    const target = stage === 'attachments' ? threadApi : agentApi
    const method = {
      history: 'getAgentHistory',
      state: 'getAgentState',
      attachments: 'getThreadAttachments',
      'active-run': 'getThreadActiveRun',
      queue: 'listThreadQueuedRequests'
    }[stage]
    t.mock.method(target, method, async () => {
      throw new Error(`synthetic-${stage}-unavailable`)
    })
    assert.equal(await c.selectThreadFromRoute('a'), false)
    assert.equal(c.initializedThreadId.value, '')
    assert.ok(c.errors.includes(`synthetic-${stage}-unavailable`))
  })
}

test('A→B→A 时旧历史迟到不覆盖当前 A，也不重新恢复旧选择', async (t) => {
  const c = chat(t),
    late = Promise.withResolvers(),
    started = Promise.withResolvers()
  let reads = 0
  t.mock.method(agentApi, 'getAgentHistory', async (id) => {
    if (id === 'a' && ++reads === 1) {
      started.resolve()
      await late.promise
      return { history: [{ content: 'stale-a' }], runs: [] }
    }
    return { history: [{ content: `fresh-${id}` }], runs: [] }
  })
  const old = c.selectThreadFromRoute('a')
  await started.promise
  await c.selectThreadFromRoute('b')
  await c.selectThreadFromRoute('a')
  late.resolve()
  assert.equal(await old, null)
  assert.equal(c.threadMessages.value.a[0].content, 'fresh-a')
  assert.equal(c.currentAgentId.value, 'health-consultation')
  assert.deepEqual(c.streams, ['run-b', 'run-a'])
})

test('旧 Agent 详情迟到不覆盖新会话的成员角色和配置', async (t) => {
  const c = chat(t),
    late = Promise.withResolvers(),
    started = Promise.withResolvers()
  const original = c.agentStore.fetchAgentDetail.bind(c.agentStore)
  t.mock.method(c.agentStore, 'fetchAgentDetail', async (id) => {
    if (id === 'health-consultation') {
      started.resolve()
      await late.promise
    }
    return original(id)
  })
  const old = c.selectThreadFromRoute('a')
  await started.promise
  await c.selectThreadFromRoute('b')
  late.resolve()
  assert.equal(await old, null)
  assert.equal(c.currentAgentId.value, 'health-diet-analyst')
  assert.equal(c.currentThreadId.value, 'b')
  assert.deepEqual(c.streams, ['run-b'])
})

test('旧 route Promise 不提前释放新 route 的发送锁或跳转', async () => {
  const first = Promise.withResolvers(),
    second = Promise.withResolvers()
  const p = page((id) => (id === 'a' ? first.promise : second.promise))
  const old = p.sync()
  p.route.params.thread_id = 'b'
  const current = p.sync()
  first.resolve(false)
  await old
  assert.equal(p.syncingRouteThread.value, true)
  assert.deepEqual(p.replaces, [])
  second.resolve(true)
  await current
  assert.equal(p.syncingRouteThread.value, false)
})

for (const kind of ['run', 'queue', 'history', 'state', 'attachments']) {
  test(`${kind} 迟到初始化在账号变化后不发布或订阅`, async (t) => {
    const c = chat(t),
      late = Promise.withResolvers(),
      started = Promise.withResolvers()
    const target = kind === 'attachments' ? threadApi : agentApi
    const method = {
      run: 'getThreadActiveRun',
      queue: 'listThreadQueuedRequests',
      history: 'getAgentHistory',
      state: 'getAgentState',
      attachments: 'getThreadAttachments'
    }[kind]
    const original =
      kind === 'queue'
        ? async () => ({ requests: [{ request_id: 'late-queue', status: 'queued' }] })
        : target[method].bind(target)
    t.mock.method(target, method, async (...args) => {
      started.resolve()
      await late.promise
      return original(...args)
    })
    const old = c.selectThreadFromRoute('a')
    await started.promise
    c.userStore.uid = 'another-synthetic-user'
    late.resolve()
    assert.equal(await old, null)
    assert.equal(c.initializedThreadId.value, '')
    if (kind === 'run') assert.deepEqual(c.streams, [])
    if (kind === 'history') assert.equal(c.threadMessages.value.a, undefined)
    if (kind === 'state') assert.equal(c.getThreadState('a').agentState, null)
    if (kind === 'attachments') assert.equal(c.threadAttachmentsMap.value.a, undefined)
    if (kind === 'queue') {
      assert.deepEqual(c.getThreadState('a').queuedRequests, [])
      assert.deepEqual(c.requestStreams, [])
    }
  })
}

test('组件销毁后在途初始化不发布历史或启动订阅', async (t) => {
  const c = chat(t),
    late = Promise.withResolvers(),
    started = Promise.withResolvers()
  t.mock.method(agentApi, 'getAgentHistory', async () => {
    started.resolve()
    await late.promise
    return { history: [{ content: 'after-unmount' }], runs: [] }
  })
  const selection = c.selectThreadFromRoute('a')
  await started.promise
  c.unmount()
  late.resolve()
  assert.equal(await selection, null)
  assert.equal(c.threadMessages.value.a, undefined)
  assert.deepEqual(c.streams, [])
})

/** 执行组件发送入口，模拟 nextTick 期间切换角色。 */
function sender(c, source = component) {
  const context = {
    ...c,
    userInput: ref('追加问题'),
    images: [],
    currentAgent: ref({ id: 'health-consultation' }),
    sendCooldownActive: ref(false),
    props: { sendDisabled: false },
    isWaitingForUserAction: ref(false),
    currentChatId: c.currentThreadId,
    currentPendingThreadAttachments: ref([{ file_id: 'attachment-a' }]),
    isHealthRole: computed(() =>
      c.threads.value
        .find((thread) => thread.id === c.currentThreadId.value)
        ?.agent_id.startsWith('health-')
    ),
    currentModelSpec: ref('ignored-health-model'),
    currentToolApprovalMode: ref('auto'),
    startSendCooldown() {
      context.sendCooldownActive.value = true
    },
    nextTick: async () => {
      c.currentAgentId.value = 'ordinary'
      c.currentThreadId.value = 'b'
    },
    scrollController: { scrollToBottom() {} },
    approvalState: {},
    hideApprovalState() {},
    createClientRequestId: () => 'followup',
    markAttachmentsRequestId: () => null,
    buildOptimisticHumanMessage: ({ text }) => ({ content: text }),
    rollbackAttachments() {},
    isRunInterruptedConflict: () => false,
    resumeQueuedRequests: async () => {},
    agentInputAreaRef: ref(null),
    configStore: { config: { fast_model: 'synthetic-fast-model' } }
  }
  const block = source.slice(
    source.indexOf('const handleSendMessage ='),
    source.indexOf('const handleDirectSteer =')
  )
  const send = new Function(...Object.keys(context), `${block}\nreturn handleSendMessage`)(
    ...Object.values(context)
  )
  return { send, context }
}

test('初始化未就绪直接发送也拒绝，就绪后重复点击仅接入一次同线程请求', async (t) => {
  const c = chat(t),
    requests = [],
    titles = []
  c.threads.value[1].agent_id = 'ordinary'
  c.currentThreadId.value = 'a'
  const s = sender(c)
  t.mock.method(agentApi, 'createAgentRun', async (request) => {
    requests.push(request)
    return { status: 'queued' }
  })
  t.mock.method(agentApi, 'generateTitle', async (...args) => {
    titles.push(args)
    return ''
  })
  await s.send()
  assert.deepEqual(requests, [])
  await c.selectThreadFromRoute('a')
  c.threadMessages.value.a = []
  s.context.userInput.value = '追加问题'
  await Promise.all([s.send(), s.send()])
  assert.equal(requests.length, 1)
  assert.deepEqual(
    [
      requests[0].thread_id,
      requests[0].agent_slug,
      requests[0].queue_policy,
      requests[0].model_spec
    ],
    ['a', 'health-consultation', 'enqueue', null]
  )
  assert.deepEqual(requests[0].meta.attachment_file_ids, ['attachment-a'])
  assert.equal(c.getThreadState('a').activeRunId, 'run-a')
  assert.deepEqual(titles, [])
})

test('同 Run 重订阅后旧流迟到正文和终态均丢弃', async (t) => {
  const c = chat(t),
    oldOpened = Promise.withResolvers()
  let oldController,
    reads = 0
  const normal = agentApi.streamAgentRunEvents.bind(agentApi)
  t.mock.method(agentApi, 'streamAgentRunEvents', (...args) => {
    if (++reads > 1) return normal(...args)
    return new Response(
      new ReadableStream({
        start(controller) {
          oldController = controller
          oldOpened.resolve()
        }
      })
    )
  })
  const old = c.startRunStream('a', 'run-shared')
  await oldOpened.promise
  const current = c.startRunStream('a', 'run-shared')
  oldController.enqueue(
    new TextEncoder().encode(
      'event: messages\ndata: {"payload":{"chunk":{"content":"stale"}}}\n\nevent: end\ndata: {"payload":{"status":"completed"}}\n\n'
    )
  )
  oldController.close()
  await old
  assert.deepEqual(c.chunks, [])
  assert.equal(c.getThreadState('a').activeRunId, 'run-shared')
  c.stopRunStreamSubscription('a')
  await current
})

test('同 Run 旧连接迟到网络错误不弹错，也不重连', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const c = chat(t),
    late = Promise.withResolvers(),
    errors = []
  let reads = 0
  const normal = agentApi.streamAgentRunEvents.bind(agentApi)
  t.mock.method(agentApi, 'streamAgentRunEvents', (...args) =>
    ++reads === 1 ? late.promise : normal(...args)
  )
  t.mock.method(ErrorHandler, 'handleError', (error) => errors.push(error.message))
  t.mock.method(console, 'error', () => {})
  const old = c.startRunStream('a', 'run-shared')
  const current = c.startRunStream('a', 'run-shared')
  late.reject(new Error('stale-network'))
  await old
  assert.deepEqual(errors, [])
  c.stopRunStreamSubscription('a')
  await current
  t.mock.timers.tick(500)
  await setImmediate()
  assert.equal(reads, 2)
})

for (const source of ['eof', 'watchdog']) {
  test(`${source} 旧 PG 终态读迟到不结束同 Run 的新订阅`, async (t) => {
    if (source === 'watchdog') t.mock.timers.enable({ apis: ['setInterval', 'Date'], now: 0 })
    const c = chat(t),
      late = Promise.withResolvers(),
      started = Promise.withResolvers()
    let reads = 0
    const normal = agentApi.streamAgentRunEvents.bind(agentApi)
    if (source === 'eof')
      t.mock.method(agentApi, 'streamAgentRunEvents', (...args) =>
        ++reads === 1 ? new Response('') : normal(...args)
      )
    t.mock.method(agentApi, 'getAgentRun', async () => {
      started.resolve()
      return late.promise
    })
    const old = c.startRunStream('a', 'run-shared')
    if (source === 'watchdog') {
      await setImmediate()
      t.mock.timers.tick(60000)
    }
    await started.promise
    const current = c.startRunStream('a', 'run-shared')
    late.resolve({ run: { id: 'run-shared', status: 'completed' } })
    await setImmediate()
    assert.equal(c.getThreadState('a').activeRunId, 'run-shared')
    assert.equal(c.getThreadState('a').runStreamAbortController.signal.aborted, false)
    c.stopRunStreamSubscription('a')
    await Promise.all([old, current])
  })
}

test('恢复选择失效后已经安排的重连不重开旧 Run', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const c = chat(t),
    streams = []
  let selected = true
  t.mock.method(agentApi, 'streamAgentRunEvents', async (id) => {
    streams.push(id)
    return new Response('')
  })
  await c.startRunStream('a', 'run-shared', '0-0', { isCurrent: () => selected })
  selected = false
  t.mock.timers.tick(500)
  await setImmediate()
  assert.deepEqual(streams, ['run-shared'])
})

for (const scoped of [true, false]) {
  test(`${scoped ? '恢复 Run' : '后续排队 Run'} 终态迟到历史不覆盖重新选中的 A，也不通知旧选择`, async (t) => {
    const c = chat(t, { realTerminalRefresh: true }),
      late = Promise.withResolvers(),
      started = Promise.withResolvers()
    const targetRun = scoped ? 'run-a' : 'run-followup'
    let historyReads = 0,
      oldController,
      pending
    const normal = agentApi.streamAgentRunEvents.bind(agentApi)
    t.mock.method(agentApi, 'streamAgentRunEvents', (...args) => {
      if (args[0] !== targetRun || oldController) return normal(...args)
      return new Response(
        new ReadableStream({
          start(controller) {
            oldController = controller
          }
        })
      )
    })
    t.mock.method(agentApi, 'getAgentHistory', async (id) => {
      if (id === 'a' && ++historyReads === 2) {
        started.resolve()
        await late.promise
        return { history: [{ content: 'stale-terminal-a' }], runs: [] }
      }
      return { history: [{ content: `fresh-${id}` }], runs: [] }
    })
    await c.selectThreadFromRoute('a')
    if (!scoped) pending = c.startRunStream('a', targetRun, '0-0', { requestId: 'queued-followup' })
    oldController.enqueue(
      new TextEncoder().encode('event: end\ndata: {"payload":{"status":"completed"}}\n\n')
    )
    oldController.close()
    await pending
    await started.promise
    await c.selectThreadFromRoute('b')
    await c.selectThreadFromRoute('a')
    late.resolve()
    await setImmediate()
    assert.equal(c.threadMessages.value.a[0].content, 'fresh-a')
    assert.deepEqual(c.notifications, [])
    assert.equal(c.getThreadState('a').activeRunId, 'run-a')
  })
}

test('旧历史读取失败在重新选择后不弹出旧错误', async (t) => {
  const c = chat(t),
    late = Promise.withResolvers(),
    started = Promise.withResolvers()
  t.mock.method(agentApi, 'getAgentHistory', async () => {
    started.resolve()
    await late.promise
    throw new Error('stale-history-failure')
  })
  const old = c.selectThreadFromRoute('a')
  await started.promise
  await c.selectThreadFromRoute('')
  late.resolve()
  assert.equal(await old, null)
  assert.deepEqual(c.errors, [])
})

test('附件或新建入口创建的合法线程立即满足本地就绪守卫', async (t) => {
  const c = chat(t),
    project = ref('project-a'),
    requestId = ref('')
  const context = {
    ...c,
    selectedProjectId: project,
    threadCreationRequestId: requestId,
    AUTO_PROJECT_ID: 'auto',
    createClientRequestId: () => 'create-once',
    createThreadForContext: async () => ({ accepted: true, thread: { id: 'created' } })
  }
  c.chatThreadsStore.setThreadCreationInFlight = (value) => {
    c.threadCreationInFlight.value = value
  }
  const block = component.slice(
    component.indexOf('const createActiveThread ='),
    component.indexOf('const ensureActiveThread =')
  )
  const create = new Function(...Object.keys(context), `${block}\nreturn createActiveThread`)(
    ...Object.values(context)
  )
  assert.equal(await create(), 'created')
  assert.equal(c.currentThreadId.value, 'created')
  assert.equal(c.initializedThreadId.value, 'created')
  assert.equal(c.threadCreationInFlight.value, false)
})
