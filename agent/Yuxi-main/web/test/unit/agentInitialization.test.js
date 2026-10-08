import assert from 'node:assert/strict'
import { setImmediate } from 'node:timers/promises'
import test from 'node:test'
import { message } from 'ant-design-vue'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { createServer } from 'vite'

test('并发初始化等待默认详情，随后选择成员智能体不会被默认覆盖', async (t) => {
  const { store, agentApi, calls } = await loadAgentStore(t)
  const defaultDetail = deferred()
  const detailStarted = deferred()
  t.mock.method(agentApi, 'getAgentDetail', async (id) => {
    calls.details.push(id)
    if (id === 'default-chatbot') {
      detailStarted.resolve()
      await defaultDetail.promise
    }
    return { agent: agentDetail(id) }
  })

  const mountedInitialization = store.initialize()
  await detailStarted.promise
  let routeInitializationCompleted = false
  const routeSelection = (async () => {
    await store.initialize()
    routeInitializationCompleted = true
    await store.selectAgent('health-consultation')
  })()
  await setImmediate()
  const resumedBeforeDefaultDetail = routeInitializationCompleted
  defaultDetail.resolve()
  await Promise.all([mountedInitialization, routeSelection])

  assert.deepEqual(
    { resumedBeforeDefaultDetail, selectedAgentId: store.selectedAgentId },
    { resumedBeforeDefaultDetail: false, selectedAgentId: 'health-consultation' }
  )
  assert.equal(store.isInitialized, true)
  assert.equal(store.agentConfig.model, 'health-consultation-model')
  assert.deepEqual(calls, {
    agents: 1,
    databases: 1,
    tools: 1,
    details: ['default-chatbot', 'health-consultation']
  })
  await store.initialize()
  assert.equal(calls.agents, 1)
  assert.equal(store.selectedAgentId, 'health-consultation')
})

test('初始化失败后共享等待结束，下一次调用重新加载并成功选择', async (t) => {
  const { store, agentApi, calls } = await loadAgentStore(t)
  const failedDetail = deferred()
  const detailStarted = deferred()
  t.mock.method(agentApi, 'getAgentDetail', async (id) => {
    calls.details.push(id)
    if (calls.details.length === 1) {
      detailStarted.resolve()
      await failedDetail.promise
    }
    return { agent: agentDetail(id) }
  })

  const first = store.initialize()
  await detailStarted.promise
  let secondCompleted = false
  const second = store.initialize().then(() => {
    secondCompleted = true
  })
  await setImmediate()
  const completedBeforeFailure = secondCompleted
  failedDetail.reject(new Error('synthetic initialization failure'))
  await Promise.all([first, second])
  assert.equal(completedBeforeFailure, false)
  assert.equal(store.isInitialized, false)
  assert.equal(store.error, 'synthetic initialization failure')
  assert.equal(calls.agents, 1)

  await store.initialize()
  assert.equal(store.isInitialized, true)
  assert.equal(store.error, null)
  assert.equal(store.selectedAgentId, 'default-chatbot')
  assert.deepEqual(calls, {
    agents: 2,
    databases: 2,
    tools: 2,
    details: ['default-chatbot', 'default-chatbot']
  })
})

test('reset 后启动独立初始化，旧失败的清理不释放新等待', async (t) => {
  const { store, agentApi, calls } = await loadAgentStore(t)
  const oldAgents = deferred()
  const newAgents = deferred()
  t.mock.method(agentApi, 'getAgents', async () => {
    calls.agents += 1
    await (calls.agents === 1 ? oldAgents.promise : newAgents.promise)
    return { agents: agentList() }
  })

  const oldInitialization = store.initialize()
  store.reset()
  const newInitialization = store.initialize()
  assert.equal(calls.agents, 2)
  oldAgents.reject(new Error('synthetic previous account failure'))
  await oldInitialization

  let joinedInitializationCompleted = false
  const joinedInitialization = store.initialize().then(() => {
    joinedInitializationCompleted = true
  })
  await setImmediate()
  const completedBeforeNewAgents = joinedInitializationCompleted
  newAgents.resolve()
  await Promise.all([newInitialization, joinedInitialization])
  assert.equal(completedBeforeNewAgents, false)
  assert.equal(store.isInitialized, true)
  assert.equal(store.selectedAgentId, 'default-chatbot')
  assert.deepEqual(calls, {
    agents: 2,
    databases: 2,
    tools: 2,
    details: ['default-chatbot']
  })
})

test('未绑定的健康角色偏好不成为默认选择，已绑定线程仍可显式选择', async (t) => {
  const { store, calls } = await loadAgentStore(t)
  store.selectedAgentId = 'health-consultation'
  await Promise.all([store.initialize(), store.initialize()])
  assert.equal(store.selectedAgentId, 'default-chatbot')
  assert.equal(store.agentConfig.model, 'default-chatbot-model')
  assert.deepEqual(store.originalAgentConfig, store.agentConfig)
  assert.deepEqual(calls, {
    agents: 1,
    databases: 1,
    tools: 1,
    details: ['default-chatbot']
  })
  await store.selectAgent('health-consultation')
  assert.equal(store.selectedAgentId, 'health-consultation')
  assert.equal(store.agentConfig.model, 'health-consultation-model')
})

/** 用真实 Vite 模块和 Pinia 加载 store，仅替换外部请求边界。 */
async function loadAgentStore(t) {
  const previousStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: { getItem: () => null, setItem() {}, removeItem() {} }
  })
  const server = await createServer({
    server: { middlewareMode: true, hmr: false },
    // 自动重优化会重载模块图，使 store 持有的 API 与随后设置 mock 的对象分离。
    optimizeDeps: { noDiscovery: true, include: [] },
    ssr: { optimizeDeps: { noDiscovery: true, include: [] } },
    appType: 'custom'
  })
  const pinia = createPinia()
  setActivePinia(pinia)
  t.after(async () => {
    disposePinia(pinia)
    await server.close()
    if (previousStorage) Object.defineProperty(globalThis, 'localStorage', previousStorage)
    else delete globalThis.localStorage
  })
  const { agentApi, databaseApi, toolApi } = await server.ssrLoadModule('/src/apis/index.js')
  t.mock.method(message, 'error', () => {})
  t.mock.method(console, 'error', () => {})
  const calls = { agents: 0, databases: 0, tools: 0, details: [] }
  t.mock.method(agentApi, 'getAgents', async () => {
    calls.agents += 1
    return { agents: agentList() }
  })
  t.mock.method(databaseApi, 'getAccessibleDatabases', async () => {
    calls.databases += 1
    return { databases: [] }
  })
  t.mock.method(toolApi, 'getTools', async () => {
    calls.tools += 1
    return { data: [] }
  })
  t.mock.method(agentApi, 'getAgentDetail', async (id) => {
    calls.details.push(id)
    return { agent: agentDetail(id) }
  })
  const { useAgentStore } = await server.ssrLoadModule('/src/stores/agent.js')
  const loadedApis = await server.ssrLoadModule('/src/apis/index.js')
  assert.strictEqual(loadedApis.agentApi, agentApi)
  assert.strictEqual(loadedApis.databaseApi, databaseApi)
  assert.strictEqual(loadedApis.toolApi, toolApi)
  return { store: useAgentStore(), agentApi, calls }
}

/** 提供独立身份与默认选项，重现真实线程选择的两种智能体。 */
function agentList() {
  return [
    { id: 'default-chatbot', name: '智能助手', is_builtin: true },
    { id: 'health-consultation', name: '家庭营养师' }
  ]
}

/** 返回带独立模型配置的详情，以检查最终选择及配置一致性。 */
function agentDetail(id) {
  return {
    ...agentList().find((agent) => agent.id === id),
    config_json: { context: { model: `${id}-model` } }
  }
}

/** 用可控请求完成点验证等待次序，不依赖固定延时。 */
function deferred() {
  let resolve
  let reject
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}
