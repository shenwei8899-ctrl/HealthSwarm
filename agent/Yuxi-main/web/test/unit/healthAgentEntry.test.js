import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { computed, ref } from 'vue'
import { isHealthAgentId } from '../../src/utils/healthVision.js'

const source = readFileSync(new URL('../../src/views/AgentView.vue', import.meta.url), 'utf8')

test('已有健康线程可发送；切到空白新对话后必须重新选择健康成员', () => {
  const block = source.slice(
    source.indexOf('const needsHealthBinding ='),
    source.indexOf('const syncSelectedThreadFromRoute =')
  )
  const thread = ref('bound-health-thread')
  const selectedAgentId = ref('health-consultation')
  const binding = new Function(
    'computed',
    'getRouteThreadId',
    'isHealthAgentId',
    'selectedAgentId',
    `${block}\nreturn needsHealthBinding`
  )(computed, () => thread.value, isHealthAgentId, selectedAgentId)
  assert.equal(binding.value, false)
  thread.value = ''
  selectedAgentId.value = 'health-quality'
  assert.equal(binding.value, true)
  selectedAgentId.value = 'default-chatbot'
  assert.equal(binding.value, false)
  assert.match(
    source,
    /:send-disabled="syncingRouteThread \|\| !agentStore.isInitialized \|\| needsHealthBinding"/
  )
  assert.match(source, /v-if="needsHealthBinding"[\s\S]*?选择健康成员/)
})

test('普通智能体选择把所有健康角色引导到成员入口，普通角色仍直接选择', async () => {
  const block = source.slice(
    source.indexOf('const handleAgentSwitch ='),
    source.indexOf('const handleAgentSaved =')
  )
  for (const id of [
    'health-consultation',
    'health-meal-planner',
    'health-diet-analyst',
    'health-quality',
    'default-chatbot'
  ]) {
    const selected = [],
      routes = []
    const factory = new Function(
      'selectedAgentId',
      'message',
      'agentStore',
      'agentDropdownOpen',
      'isHealthAgentId',
      'router',
      `${block}\nreturn handleAgentSwitch`
    )
    const select = factory(
      ref('previous'),
      { info() {}, error() {} },
      { selectAgent: async (id) => selected.push(id) },
      ref(true),
      isHealthAgentId,
      { push: async (route) => routes.push(route) }
    )
    await select(id, false, false)
    if (isHealthAgentId(id)) {
      assert.deepEqual(selected, [])
      assert.deepEqual(routes, [{ name: 'HealthVision' }])
    } else {
      assert.deepEqual(selected, [id])
      assert.deepEqual(routes, [])
    }
  }
})

test('健康角色路由查询不能创建草稿，跳转后清理不能覆盖目标路由', async () => {
  const block = source.slice(
    source.indexOf('const consumeRouteAgentSelection ='),
    source.indexOf('watch(\n')
  )
  for (const id of [
    'health-consultation',
    'health-meal-planner',
    'health-diet-analyst',
    'health-quality',
    'default-chatbot'
  ]) {
    const calls = []
    const route = { query: { agent_id: id } }
    const factory = new Function(
      'getRouteAgentId',
      'getRouteThreadId',
      'agentStore',
      'nextTick',
      'chatComponentRef',
      'isHealthAgentId',
      'message',
      'router',
      'route',
      'handleChatError',
      `${block}\nreturn consumeRouteAgentSelection`
    )
    const select = factory(
      () => route.query.agent_id || '',
      () => '',
      { isInitialized: true, selectAgent: async (id) => calls.push(['select', id]) },
      async () => {},
      ref({
        selectThreadFromRoute: async () => {
          calls.push(['draft'])
          return true
        }
      }),
      isHealthAgentId,
      { info() {} },
      {
        push: async (target) => {
          calls.push(['push', target])
          route.query = {}
        },
        replace: async (target) => calls.push(['replace', target])
      },
      route,
      () => {}
    )
    await select()
    if (isHealthAgentId(id)) assert.deepEqual(calls, [['push', { name: 'HealthVision' }]])
    else
      assert.deepEqual(calls, [
        ['draft'],
        ['select', id],
        ['replace', { name: 'AgentComp', query: {} }]
      ])
  }
})
