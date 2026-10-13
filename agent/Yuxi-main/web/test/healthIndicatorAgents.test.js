import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { setImmediate } from 'node:timers/promises'
import * as Vue from 'vue'
import { parse, compileTemplate } from 'vue/compiler-sfc'

const source = await readFile(
  new URL('../src/components/health/HealthIndicatorAgents.vue', import.meta.url),
  'utf8'
)
const { descriptor } = parse(source)
const script = descriptor.scriptSetup.content.replace(/^import[^\n]+\n/gm, '')
const compiled = compileTemplate({
  source: descriptor.template.content,
  filename: 'HealthIndicatorAgents.vue',
  id: 'indicator-agents-test',
  compilerOptions: { mode: 'function' }
})
assert.deepEqual(compiled.errors, [])
const render = new Function('Vue', compiled.code)({ ...Vue, resolveComponent: (name) => name })
const tasks = ['blood_glucose_review', 'blood_lipids_review', 'blood_pressure_review']
const slugs = ['health-blood-glucose', 'health-blood-lipids', 'health-blood-pressure']
const names = ['血糖记录助手', '血脂记录助手', '血压记录助手']
const clone = (value) => JSON.parse(JSON.stringify(value))
const settle = async () => {
  await Vue.nextTick()
  await setImmediate()
}

/** 实际组件脚本和模板提供入口状态，独立请求事实作为断言依据。 */
function panel(overrides = {}) {
  const props = Vue.reactive({
    memberId: 'member-a',
    scopes: ['ai_use', 'profile_view'],
    configuration: {
      policy_version: 'synthetic-policy',
      consultation: { available: true, processor: 'synthetic-processor' }
    },
    disabled: false
  })
  const userStore = Vue.reactive({ uid: 'actor-a' })
  const calls = []
  const api = {
    agentRunSubmitUrl: '/api/agent/runs',
    memberCapabilities: async (id) => {
      calls.push(['capabilities', id])
      return {
        member_id: id,
        tasks: tasks.map((task_type) => ({
          task_type,
          status: 'unavailable',
          reason_code: 'consent_required'
        }))
      }
    },
    consent: async (id, data) => calls.push(['consent', id, clone(data)]),
    createTaskEntry: async (id, data) => {
      calls.push(['entry', id, clone(data)])
      return {
        ...data,
        member_id: id,
        entry_status: 'ready',
        agent_slug: slugs[tasks.indexOf(data.task_type)],
        thread_id: `thread-${data.task_type}`,
        request_submit_url: '/api/agent/runs'
      }
    },
    ...overrides
  }
  let cleanup
  const effect = Vue.effectScope()
  const state = effect.run(() =>
    new Function(
      'computed',
      'ref',
      'watch',
      'onBeforeUnmount',
      'defineProps',
      'useRouter',
      'useUserStore',
      'api',
      `${script}\nreturn { roles, selectedTask, consent, working, loading, capabilities, error, attempt, role, service, canRead, canUse, canEnter, reason, enter, refreshCapabilities }`
    )(
      Vue.computed,
      Vue.ref,
      Vue.watch,
      (fn) => {
        cleanup = fn
      },
      () => props,
      () => ({ push: async (route) => calls.push(['navigate', route]) }),
      () => userStore,
      api
    )
  )
  return {
    ...state,
    props,
    userStore,
    calls,
    template: () => render(Vue.proxyRefs({ ...props, ...state }), []),
    dispose: () => {
      cleanup()
      effect.stop()
    }
  }
}

/** 遍历编译后的真实节点和默认插槽。 */
function nodes(node, type) {
  if (!node || typeof node !== 'object') return []
  const children = Array.isArray(node.children)
    ? node.children
    : typeof node.children?.default === 'function'
      ? node.children.default()
      : []
  return [...(node.type === type ? [node] : []), ...children.flatMap((child) => nodes(child, type))]
}

test('三类助手分别经明确同意、任务入口进入独立角色线程', async () => {
  for (let i = 0; i < tasks.length; i++) {
    const state = panel()
    await settle()
    state.selectedTask.value = tasks[i]
    await state.enter()
    assert.equal(
      state.calls.some(([kind]) => kind === 'consent' || kind === 'entry'),
      false
    )
    assert.deepEqual(
      nodes(state.template(), 'a-select')[0].props.options.map((item) => item.label),
      names
    )
    nodes(state.template(), 'a-checkbox')[0].props['onUpdate:checked'](true)
    const button = nodes(state.template(), 'a-button')[0]
    assert.equal(button.props.disabled, false)
    await button.props.onClick()
    const accepted = state.calls.find(([kind]) => kind === 'consent')
    assert.deepEqual(accepted, [
      'consent',
      'member-a',
      {
        purpose: 'consultation',
        accepted: true,
        processor: 'synthetic-processor',
        policy_version: 'synthetic-policy'
      }
    ])
    const entry = state.calls.find(([kind]) => kind === 'entry')
    assert.equal(entry[1], 'member-a')
    assert.equal(entry[2].task_type, tasks[i])
    assert.match(entry[2].client_request_id, /^[0-9a-f-]{36}$/)
    assert.deepEqual(state.calls.at(-1), [
      'navigate',
      { name: 'AgentCompWithThreadId', params: { thread_id: `thread-${tasks[i]}` } }
    ])
    state.dispose()
  }
})

test('无成员、缺授权、未批准模型或缺角色能力时不发送同意或创建线程', async () => {
  for (const change of [
    (state) => {
      state.props.memberId = ''
    },
    (state) => {
      state.props.scopes = ['profile_view']
    },
    (state) => {
      state.props.scopes = ['ai_use']
    },
    (state) => {
      state.props.configuration.consultation.available = false
    },
    (state) => {
      state.capabilities.value.tasks[0] = {
        task_type: tasks[0],
        status: 'unavailable',
        reason_code: 'agent_unavailable'
      }
    },
    (state) => {
      state.capabilities.value.tasks[0] = {
        task_type: tasks[0],
        status: 'unavailable',
        reason_code: 'self_member_required'
      }
    }
  ]) {
    const state = panel()
    await settle()
    change(state)
    state.consent.value = true
    assert.equal(state.canEnter.value, false)
    await state.enter()
    assert.equal(
      state.calls.some(([kind]) => kind === 'consent' || kind === 'entry'),
      false
    )
    state.dispose()
  }
})

test('网络中断或代理5xx时保留入口幂等键和同意，重试恢复同一线程', async () => {
  for (const status of [undefined, 500, 502, 503, 504]) {
    const sent = []
    const state = panel({
      createTaskEntry: async (id, data) => {
        sent.push(clone(data))
        if (sent.length === 1) throw Object.assign(Error('合成未知响应'), { status })
        return {
          ...data,
          member_id: id,
          entry_status: 'ready',
          agent_slug: slugs[0],
          thread_id: 'recovered-thread',
          request_submit_url: '/api/agent/runs'
        }
      }
    })
    await settle()
    state.consent.value = true
    await state.enter()
    assert.equal(
      state.calls.some(([kind]) => kind === 'navigate'),
      false
    )
    assert.ok(state.error.value)
    assert.equal(state.consent.value, true)
    await state.enter()
    assert.deepEqual(sent[1], sent[0])
    assert.deepEqual(state.calls.at(-1)[1].params, { thread_id: 'recovered-thread' })
    state.dispose()
  }
})

test('未就绪、待补资料及成员任务角色回执不一致都不能导航', async () => {
  for (const patch of [
    { entry_status: 'dependency_not_ready', reason_code: 'runtime_dependency_unavailable' },
    { entry_status: 'needs_input', questions: ['请核对测量时间'] },
    { member_id: 'member-b' },
    { task_type: tasks[1] },
    { client_request_id: 'wrong-id' },
    { agent_slug: slugs[1] },
    { thread_id: null },
    { request_submit_url: '/api/other' }
  ]) {
    const state = panel({
      createTaskEntry: async (id, data) => ({
        ...data,
        member_id: id,
        entry_status: 'ready',
        agent_slug: slugs[0],
        thread_id: 'thread-a',
        request_submit_url: '/api/agent/runs',
        ...patch
      })
    })
    await settle()
    state.consent.value = true
    await state.enter()
    assert.ok(state.error.value, JSON.stringify(patch))
    assert.equal(
      state.calls.some(([kind]) => kind === 'navigate'),
      false
    )
    state.dispose()
  }
})

test('同意或入口响应期间成员、任务、授权、操作者、模型政策变化或卸载撤销迟到导航', async () => {
  for (const stage of ['consent', 'createTaskEntry']) {
    for (const change of [
      (state) => {
        state.props.memberId = 'member-b'
      },
      (state) => {
        state.selectedTask.value = tasks[1]
      },
      (state) => {
        state.props.scopes = []
      },
      (state) => {
        state.userStore.uid = 'actor-b'
      },
      (state) => {
        state.props.configuration.policy_version = 'policy-b'
      },
      (state) => {
        state.props.configuration.consultation.model = 'model-b'
      },
      (state) => {
        state.dispose()
      }
    ]) {
      let release
      const state = panel({
        [stage]: (id, data) =>
          new Promise((resolve) => {
            release = () =>
              resolve({
                ...data,
                member_id: id,
                entry_status: 'ready',
                agent_slug: slugs[0],
                thread_id: 'late-thread',
                request_submit_url: '/api/agent/runs'
              })
          })
      })
      await settle()
      state.consent.value = true
      const pending = state.enter()
      await settle()
      change(state)
      release()
      await pending
      assert.equal(
        state.calls.some(([kind]) => kind === 'entry' || kind === 'navigate'),
        false
      )
      assert.equal(state.consent.value, false)
      state.dispose()
    }
  }
})

test('能力读取失败保持错误且禁用提交，重新读取后按真实能力恢复', async () => {
  let fail = true
  const state = panel({
    memberCapabilities: async (id) => {
      if (fail) throw Error('合成读取失败')
      return { member_id: id, tasks: [{ task_type: tasks[0], status: 'available' }] }
    }
  })
  assert.equal(state.loading.value, true)
  await settle()
  assert.equal(state.canUse.value, false)
  assert.equal(
    nodes(state.template(), 'a-alert').some((node) => node.props.message === '合成读取失败'),
    true
  )
  fail = false
  await state.refreshCapabilities()
  assert.equal(state.error.value, '')
  assert.equal(state.canUse.value, true)
  state.dispose()
})

test('指标页签装配当前成员、授权、配置及成员切换销毁边界', async () => {
  const view = await readFile(new URL('../src/views/HealthVisionView.vue', import.meta.url), 'utf8')
  const block = view.slice(view.indexOf('const tabs ='), view.indexOf('const editable ='))
  const tabs = new Function('computed', 'userStore', `${block}\nreturn tabs`)(Vue.computed, {
    isAdmin: false
  })
  assert.ok(tabs.value.some((item) => item.key === 'indicators' && item.label === '指标助手'))
  const fragment = view
    .match(/<HealthIndicatorAgents[\s\S]*?\/>/)[0]
    .replace(/\s+v-else-if="[^"]*"/, '')
  const compiled = compileTemplate({
    source: fragment,
    filename: 'HealthVisionView.vue',
    id: 'indicator-entry-test',
    compilerOptions: { mode: 'function' }
  })
  assert.deepEqual(compiled.errors, [])
  const renderEntry = new Function('Vue', compiled.code)({
    ...Vue,
    resolveComponent: (name) => name
  })
  const context = {
    memberId: 'member-a',
    member: { scopes: ['ai_use', 'report_view', 'diet_edit'] },
    config: { consultation: { available: true } },
    busy: false,
    confirming: false
  }
  const vnode = renderEntry(context, [])
  assert.equal(vnode.props['member-id'], 'member-a')
  assert.equal(vnode.props.configuration, context.config)
  assert.equal(vnode.props.scopes, context.member.scopes)
  context.memberId = 'member-b'
  context.member = { scopes: [] }
  const changed = renderEntry(context, [])
  assert.equal(changed.props['member-id'], 'member-b')
  assert.deepEqual(changed.props.scopes, [])
  assert.notEqual(changed.key, vnode.key)
})

test('任务入口和成员能力经既有认证API封装，保留请求幂等键', async () => {
  const apiSource = (
    await readFile(new URL('../src/apis/health_vision_api.js', import.meta.url), 'utf8')
  )
    .replace(/^import.*\r?\n/gm, '')
    .replace('export const healthVisionApi', 'const healthVisionApi')
  const calls = []
  const api = new Function(
    'apiGet',
    'apiPost',
    'apiPut',
    'apiDelete',
    'apiRequest',
    'buildQuery',
    `${apiSource}\nreturn healthVisionApi`
  )(
    async (...args) => calls.push(['get', ...args]),
    async (...args) => calls.push(['post', ...args]),
    () => {},
    () => {},
    () => {},
    () => ''
  )
  await api.memberCapabilities('member-a')
  await api.createTaskEntry('member-a', {
    task_type: 'blood_glucose_review',
    client_request_id: 'request-a'
  })
  assert.deepEqual(calls, [
    ['get', '/api/health/v1/members/member-a/capabilities'],
    [
      'post',
      '/api/health/v1/members/member-a/task-entries',
      { task_type: 'blood_glucose_review', client_request_id: 'request-a' },
      { headers: { 'Idempotency-Key': 'request-a' } }
    ]
  ])
})
