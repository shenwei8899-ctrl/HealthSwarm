import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { ref, computed } from 'vue'
import * as Vue from 'vue'
import { renderToString } from 'vue/server-renderer'
import { setImmediate } from 'node:timers/promises'
import { isHealthAgentId } from '../../src/utils/healthVision.js'

const source = readFileSync(
  new URL('../../src/components/AgentChatComponent.vue', import.meta.url),
  'utf8'
)

test('模型选择按当前选择、Conversation、智能体默认的顺序解析', () => {
  const modelBlock = source.slice(
    source.indexOf('const currentModelSpec = computed'),
    source.indexOf('const handleModelSelect')
  )

  for (const expression of [
    'selectedModelByThread',
    'currentThread.value?.metadata?.model_spec',
    'agentDefaultModel.value'
  ])
    assert.ok(modelBlock.includes(expression), expression)

  assert.ok(
    modelBlock.indexOf('selectedModelByThread') <
      modelBlock.indexOf('currentThread.value?.metadata?.model_spec')
  )
  assert.ok(
    modelBlock.indexOf('currentThread.value?.metadata?.model_spec') <
      modelBlock.indexOf('agentDefaultModel.value')
  )
})

test('发送当前展示模型并在请求被接受后同步 Conversation metadata', () => {
  const sendBlock = source.slice(
    source.indexOf('const handleSendMessage'),
    source.indexOf('const handleDirectSteer')
  )

  assert.match(
    sendBlock,
    /const modelSpec = isHealthRole\.value \? null : currentModelSpec\.value \|\| null/
  )
  assert.match(sendBlock, /model_spec: modelSpec/)
  assert.match(sendBlock, /status !== 'rejected' && modelSpec/)
  assert.match(
    sendBlock,
    /thread\.metadata = \{ \.\.\.\(thread\.metadata \|\| \{\}\), model_spec: modelSpec \}/
  )
})

test('健康绑定会话发送 null 由后台选批准模型，不沿用系统默认或旧覆盖', () => {
  const binding = source.slice(
    source.indexOf('const isHealthRole = computed'),
    source.indexOf('const savedToolApprovalMode')
  )
  const currentThread = ref({ agent_id: 'health-consultation' })
  const currentAgentId = ref('default')
  const isHealthConsultation = new Function(
    'computed',
    'currentThread',
    'currentAgentId',
    'isHealthAgentId',
    `${binding}\nreturn isHealthRole`
  )(computed, currentThread, currentAgentId, isHealthAgentId)
  const declaration = source.match(/ {2}const modelSpec = [^\n]+/)[0]
  const requestModel = new Function(
    'isHealthRole',
    'currentModelSpec',
    `${declaration}\nreturn modelSpec`
  )
  const wrongDefault = ref('synthetic-wrong-system/default')
  for (const slug of [
    'health-consultation',
    'health-meal-planner',
    'health-diet-analyst',
    'health-quality'
  ]) {
    currentThread.value = { agent_id: slug }
    assert.equal(requestModel(isHealthConsultation, wrongDefault), null)
  }
  currentThread.value = { agent_id: 'default' }
  assert.equal(requestModel(isHealthConsultation, wrongDefault), wrongDefault.value)
  currentThread.value = null
  currentAgentId.value = 'health-consultation'
  assert.equal(requestModel(isHealthConsultation, wrongDefault), null)
  assert.match(source, /v-if="isHealthRole"[^>]*>[\s\S]*?后台批准模型/)
  assert.match(source, /<ModelSelectorComponent\s+v-else/)
})

test('健康咨询首条消息不调用普通标题模型，固定标题不变；普通聊天仍生成标题', async () => {
  const send = source.slice(
    source.indexOf('const handleSendMessage'),
    source.indexOf('const handleDirectSteer')
  )
  const titleBlock = send.slice(
    send.indexOf('  if (!isHealthRole.value &&'),
    send.indexOf('  const requestId = createClientRequestId()')
  )
  assert.ok(titleBlock.includes('agentApi.generateTitle'), '执行真实首次发送标题路径')
  const titles = [],
    updates = []
  const invoke = new Function(
    'isHealthRole',
    'threadMessages',
    'threadId',
    'text',
    'agentApi',
    'configStore',
    'chatThreadsStore',
    titleBlock
  )
  const args = [
    ref({ 'synthetic-thread': [] }),
    'synthetic-thread',
    'synthetic-health-question',
    {
      generateTitle: async (...args) => {
        titles.push(args)
        return 'synthetic-title'
      }
    },
    { config: { fast_model: 'unapproved-fast/model' } },
    { updateThread: async (...args) => updates.push(args) }
  ]
  invoke(ref(true), ...args)
  await setImmediate()
  assert.deepEqual(titles, [])
  assert.deepEqual(updates, [])
  invoke(ref(false), ...args)
  await setImmediate()
  assert.deepEqual(titles, [['synthetic-health-question', 'unapproved-fast/model']])
  assert.deepEqual(updates, [['synthetic-thread', 'synthetic-title']])
})

test('路由选择即使已预写当前线程也会加载消息', () => {
  const routeSelectionBlock = source.slice(
    source.indexOf('const selectThreadFromRoute'),
    source.indexOf('const handleQuestionSubmit')
  )

  assert.doesNotMatch(
    routeSelectionBlock,
    /if \(currentThreadId\.value === threadId\) \{\s*return true\s*\}/
  )
  assert.match(routeSelectionBlock, /await selectChat\(threadId\)/)
})

test('路由同步和初始化未完成时页面禁用发送，直接调用发送处理也停止', async () => {
  const view = readFileSync(new URL('../../src/views/AgentView.vue', import.meta.url), 'utf8')
  const render = Vue.compile(view.match(/<AgentChatComponent[\s\S]*?>/)[0].replace(/>$/, ' />'))
  const sendBlock = source.slice(
    source.indexOf('const handleSendMessage'),
    source.indexOf('const handleDirectSteer')
  )
  const sendGuard = sendBlock.slice(
    sendBlock.indexOf('  const text'),
    sendBlock.indexOf('  // 发送后进入')
  )
  const invokeSend = new Function(
    'userInput',
    'images',
    'currentAgent',
    'sendCooldownActive',
    'props',
    'isWaitingForUserAction',
    'startSendCooldown',
    `${sendGuard}\nstartSendCooldown()`
  )
  for (const syncing of [false, true]) {
    for (const initialized of [false, true]) {
      let received
      await renderToString(
        Vue.createSSRApp({
          components: {
            AgentChatComponent: {
              props: ['sendDisabled'],
              setup(props) {
                received = props.sendDisabled
                return () => Vue.h('button', { disabled: props.sendDisabled }, '发送')
              }
            }
          },
          data: () => ({
            syncingRouteThread: syncing,
            agentStore: { isInitialized: initialized },
            needsHealthBinding: false,
            routeDraftProjectId: '',
            getRouteThreadId: () => 'health-thread',
            handleThreadChange() {}
          }),
          render
        })
      )
      assert.equal(received, syncing || !initialized)
      let started = false
      invokeSend(
        ref('读取我的血压'),
        [],
        ref({ id: 'health-consultation' }),
        ref(false),
        { sendDisabled: received },
        ref(false),
        () => {
          started = true
        }
      )
      assert.equal(started, !syncing && initialized)
    }
  }
})
