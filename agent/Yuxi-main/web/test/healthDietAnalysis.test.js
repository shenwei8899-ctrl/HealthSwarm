import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { setImmediate } from 'node:timers'
import * as Vue from 'vue'
import { parse, compileTemplate } from 'vue/compiler-sfc'
import { mealLabels } from '../src/utils/healthVision.js'

const source = await readFile(
  new URL('../src/components/health/HealthDietAnalysis.vue', import.meta.url),
  'utf8'
)
const { descriptor } = parse(source)
const script = descriptor.scriptSetup.content.replace(/^import[^\n]+\n/gm, '')
const compiled = compileTemplate({
  source: descriptor.template.content,
  filename: 'HealthDietAnalysis.vue',
  id: 'diet-analysis-test',
  compilerOptions: { mode: 'function' }
})
assert.deepEqual(compiled.errors, [])
const render = new Function('Vue', compiled.code)({ ...Vue, resolveComponent: (name) => name })
const clone = (value) => JSON.parse(JSON.stringify(value))

const record = {
  id: 'meal-a',
  source_version: 3,
  snapshot: {
    meal: {
      meal_type: 'lunch',
      eaten_at: '2026-10-09T04:00:00Z',
      items: [{ name: '合成炒鸡蛋' }, { name: '不应显示', excluded: true }]
    }
  }
}

/** 执行真实 SFC 状态及编译模板事件，记录用户可观察的请求与导航。 */
function panel(overrides = {}, customScript = script) {
  const props = Vue.reactive({
    memberId: 'member-a',
    scopes: ['diet_edit', 'ai_use'],
    configuration: {
      policy_version: 'synthetic-policy',
      diet_analysis: { available: true, processor: 'synthetic:analyst' }
    },
    records: [structuredClone(record)],
    record: null,
    feedback: false,
    disabled: false
  })
  const userStore = Vue.reactive({ uid: 'actor-a' })
  const calls = []
  const api = {
    dietPeriodAnalysis: async (id, selection) => {
      calls.push(['period', id, clone(selection)])
      return {
        result_type: 'diet_analysis',
        member_id: id,
        window: { ...selection, timezone: 'Asia/Shanghai' }
      }
    },
    dietAnalysis: async (id, selection) => {
      calls.push(['meal', id, clone(selection)])
      return { result_type: 'diet_analysis', member_id: id, records: [selection] }
    },
    consent: async (id, data) => calls.push(['consent', id, clone(data)]),
    createDietAnalyst: async (id, data) => {
      calls.push(['binding', id, clone(data)])
      return {
        member_id: id,
        thread_id: 'thread-a',
        agent_slug: 'health-diet-analyst',
        feedback_selection: null
      }
    },
    createFeedbackConversation: async (id, data) => {
      calls.push(['feedback-binding', id, clone(data)])
      return {
        member_id: 'member-a',
        thread_id: 'feedback-thread',
        agent_slug: 'health-diet-analyst',
        feedback_selection: { record_id: id, source_version: data.source_version }
      }
    },
    ...overrides.api
  }
  const agentApi = {
    createAgentRun: async (data) => {
      calls.push(['run', clone(data)])
      return { status: 'queued' }
    },
    ...overrides.agentApi
  }
  const router = { push: async (data) => calls.push(['navigate', data]), ...overrides.router }
  let cleanup
  const effect = Vue.effectScope()
  const state = effect.run(() =>
    new Function(
      'computed',
      'ref',
      'watch',
      'onBeforeUnmount',
      'defineProps',
      'defineEmits',
      'useRouter',
      'useUserStore',
      'api',
      'agentApi',
      'mealLabels',
      `${customScript}\nreturn { scope, periodDays, endDate, recordId, comment, consent, working, error, attempt, service, modelName, canRead, canUse, validRecord, canEnter, selectedRecord, recordOptions, beijingToday, recordLabel, enter, openConversation }`
    )(
      Vue.computed,
      Vue.ref,
      Vue.watch,
      (fn) => {
        cleanup = fn
      },
      () => props,
      () => () => {},
      () => router,
      () => userStore,
      api,
      agentApi,
      mealLabels
    )
  )
  return {
    ...state,
    props,
    calls,
    userStore,
    template: () => render(Vue.proxyRefs({ ...props, ...state }), []),
    dispose: () => {
      cleanup()
      effect.stop()
    }
  }
}

/** 遍历实际编译模板的节点和组件默认插槽。 */
function nodes(node, type) {
  if (!node || typeof node !== 'object') return []
  const children = Array.isArray(node.children)
    ? node.children
    : typeof node.children?.default === 'function'
      ? node.children.default()
      : []
  return [...(node.type === type ? [node] : []), ...children.flatMap((child) => nodes(child, type))]
}

/** 读取实际渲染的文案，处理默认插槽与文本VNode。 */
function textOf(node) {
  if (typeof node === 'string') return node
  if (!node || typeof node !== 'object') return ''
  if (typeof node.children === 'string') return node.children
  const children = Array.isArray(node.children)
    ? node.children
    : typeof node.children?.default === 'function'
      ? node.children.default()
      : []
  return children.map(textOf).join('')
}

test('同意文案显示批准模型名称及云处理用途，审批请求仍使用完整处理指纹', async () => {
  const state = panel()
  const processor = `synthetic:${'a'.repeat(64)}`
  state.props.configuration.diet_analysis = {
    available: true,
    model: 'synthetic:analyst-fixed',
    processor
  }
  state.props.configuration.model_options = [
    { spec: 'synthetic:analyst-fixed', name: '合成饮食分析模型' }
  ]
  const disclosure = textOf(nodes(state.template(), 'a-checkbox')[0])
  assert.match(disclosure, /云端饮食分析服务.*合成饮食分析模型/)
  assert.match(disclosure, /必要的已确认饮食和餐后反馈/)
  assert.doesNotMatch(disclosure, /[a-f0-9]{64}/)
  state.consent.value = true
  await state.enter()
  assert.equal(state.calls.find(([kind]) => kind === 'consent')[2].processor, processor)
  state.props.configuration.model_options = []
  const unnamed = textOf(nodes(state.template(), 'a-checkbox')[0])
  assert.match(unnamed, /管理员批准的饮食分析服务/)
  assert.doesNotMatch(unnamed, /[a-f0-9]{64}/)
  state.dispose()
})

test('实际模板选择7日、结束日期并独立同意后，预检与绑定先于Run且导航同一线程', async () => {
  const state = panel()
  const [days] = nodes(state.template(), 'a-select')
  days.props['onUpdate:value'](7)
  nodes(state.template(), 'input')[0].props['onUpdate:modelValue']('2026-10-09')
  assert.equal(state.canEnter.value, false)
  nodes(state.template(), 'a-checkbox')[0].props['onUpdate:checked'](true)
  const start = nodes(state.template(), 'a-button')[0]
  assert.equal(start.props.disabled, false)
  await start.props.onClick()
  assert.deepEqual(
    state.calls.map(([kind]) => kind),
    ['period', 'consent', 'binding', 'run', 'navigate']
  )
  assert.deepEqual(state.calls[0], [
    'period',
    'member-a',
    { period_days: 7, end_date: '2026-10-09' }
  ])
  assert.deepEqual(state.calls[1], [
    'consent',
    'member-a',
    {
      purpose: 'diet_analysis',
      accepted: true,
      processor: 'synthetic:analyst',
      policy_version: 'synthetic-policy'
    }
  ])
  const request = state.calls[3][1]
  assert.equal(request.agent_slug, 'health-diet-analyst')
  assert.equal(request.thread_id, 'thread-a')
  assert.equal(
    request.query,
    '请分析截至2026-10-09的7个北京时间自然日的已确认饮食记录：period_days=7，end_date=2026-10-09。缺失和未记录天数保持未知。'
  )
  assert.ok(request.meta.request_id)
  assert.deepEqual(state.calls[4], [
    'navigate',
    { name: 'AgentCompWithThreadId', params: { thread_id: 'thread-a' } }
  ])
  state.dispose()
})

test('1、7、30日均走当前自然日预检，未来日期及其他窗口不能提交', async () => {
  for (const days of [1, 7, 30]) {
    const state = panel()
    state.periodDays.value = days
    state.endDate.value = '2026-10-09'
    state.consent.value = true
    await state.enter()
    assert.deepEqual(state.calls[0][2], { period_days: days, end_date: '2026-10-09' })
    state.dispose()
  }
  for (const change of [
    (state) => {
      state.periodDays.value = 2
    },
    (state) => {
      state.endDate.value = '9999-12-31'
    },
    (state) => {
      state.endDate.value = ''
    }
  ]) {
    const state = panel()
    change(state)
    state.consent.value = true
    await state.enter()
    assert.deepEqual(state.calls, [])
    state.dispose()
  }
})

test('实际餐次选择展示菜名，source_version为3并只预检该餐', async () => {
  const state = panel()
  nodes(state.template(), 'a-radio-group')[0].props['onUpdate:value']('meal')
  const selector = nodes(state.template(), 'a-select')[0]
  assert.match(selector.props.options[0].label, /午餐.*合成炒鸡蛋/)
  assert.doesNotMatch(selector.props.options[0].label, /不应显示/)
  selector.props['onUpdate:value']('meal-a')
  state.consent.value = true
  await state.enter()
  assert.deepEqual(state.calls[0], ['meal', 'member-a', { record_id: 'meal-a', source_version: 3 }])
  assert.equal(
    state.calls[3][1].query,
    '请分析已确认餐次：record_id=meal-a，source_version=3。请沿用该确认记录的营养计算事实。'
  )
  state.dispose()
})

test('缺确认版本、空餐次和无授权状态显示原因且不能猜版本或调用模型', async () => {
  for (const change of [
    (state) => {
      state.props.records[0].source_version = undefined
      state.scope.value = 'meal'
      state.recordId.value = 'meal-a'
    },
    (state) => {
      state.props.records = []
      state.scope.value = 'meal'
    },
    (state) => {
      state.props.scopes = ['ai_use']
    },
    (state) => {
      state.props.scopes = ['diet_edit']
    },
    (state) => {
      state.props.configuration.diet_analysis.available = false
    },
    (state) => {
      state.props.disabled = true
    }
  ]) {
    const state = panel()
    change(state)
    state.consent.value = true
    await state.enter()
    assert.deepEqual(state.calls, [])
    assert.equal(state.canEnter.value, false)
    state.dispose()
  }
  const empty = panel()
  empty.props.records = []
  empty.scope.value = 'meal'
  assert.match(nodes(empty.template(), 'a-empty')[0].props.description, /人工录入并确认/)
  empty.dispose()
  const unavailable = panel()
  unavailable.props.configuration.diet_analysis = { available: false, reason: '费用限额未批准' }
  assert.match(nodes(unavailable.template(), 'a-alert')[0].props.message, /费用限额未批准/)
  unavailable.dispose()
})

test('选餐反馈严格绑定确认版本并提交用户原文，保留人工反馈入口外的专属会话', async () => {
  const state = panel()
  state.props.feedback = true
  state.props.record = structuredClone(record)
  const input = nodes(state.template(), 'a-textarea')[0]
  assert.equal(input.props.maxlength, 493)
  input.props['onUpdate:value']('吃完程度：一半；口味：偏咸；自述：饭量比较大')
  state.consent.value = true
  await nodes(state.template(), 'a-button')[0].props.onClick()
  assert.deepEqual(
    state.calls.map(([kind]) => kind),
    ['consent', 'feedback-binding', 'run', 'navigate']
  )
  assert.equal(state.calls[1][1], 'meal-a')
  assert.equal(state.calls[1][2].source_version, 3)
  assert.ok(state.calls[1][2].client_request_id)
  assert.equal(
    state.calls[2][1].query,
    '记录这餐反馈：吃完程度：一半；口味：偏咸；自述：饭量比较大'
  )
  assert.equal(state.calls[2][1].thread_id, 'feedback-thread')
  state.dispose()
})

test('空反馈和无用途同意不能创建反馈线程；换餐清除旧餐自述', async () => {
  const state = panel()
  state.props.feedback = true
  state.props.record = structuredClone(record)
  state.consent.value = true
  await state.enter()
  assert.deepEqual(state.calls, [])
  state.comment.value = '旧餐自述'
  state.consent.value = false
  await state.enter()
  assert.deepEqual(state.calls, [])
  state.props.record = { ...record, id: 'meal-b' }
  assert.equal(state.comment.value, '')
  assert.equal(state.consent.value, false)
  state.dispose()
})

test('跨成员、角色及反馈来源不一致的服务绑定不能创建Run', async () => {
  for (const binding of [
    { member_id: 'member-b', agent_slug: 'health-diet-analyst', thread_id: 'thread-a' },
    { member_id: 'member-a', agent_slug: 'health-consultation', thread_id: 'thread-a' },
    { member_id: 'member-a', agent_slug: 'health-diet-analyst', thread_id: '' },
    {
      member_id: 'member-a',
      agent_slug: 'health-diet-analyst',
      thread_id: 'thread-a',
      feedback_selection: { record_id: 'meal-a', source_version: 3 }
    }
  ]) {
    const state = panel({ api: { createDietAnalyst: async () => binding } })
    state.consent.value = true
    await state.enter()
    assert.equal(
      state.calls.some(([kind]) => kind === 'run'),
      false
    )
    assert.match(state.error.value, /尚未确认/)
    state.dispose()
  }
  for (const selected of [
    { record_id: 'meal-b', source_version: 3 },
    { record_id: 'meal-a', source_version: 1 },
    null
  ]) {
    const state = panel({
      api: {
        createFeedbackConversation: async () => ({
          member_id: 'member-a',
          agent_slug: 'health-diet-analyst',
          thread_id: 'thread-a',
          feedback_selection: selected
        })
      }
    })
    state.props.feedback = true
    state.props.record = structuredClone(record)
    state.comment.value = '这餐偏咸'
    state.consent.value = true
    await state.enter()
    assert.equal(
      state.calls.some(([kind]) => kind === 'run'),
      false
    )
    state.dispose()
  }
})

test('无模型预检的成员、版本和窗口不匹配时不提交外发同意或线程', async () => {
  for (const result of [
    {
      member_id: 'member-b',
      result_type: 'diet_analysis',
      window: { period_days: 1, end_date: '2026-10-09', timezone: 'Asia/Shanghai' }
    },
    {
      member_id: 'member-a',
      result_type: 'diet_analysis',
      window: { period_days: 7, end_date: '2026-10-09', timezone: 'Asia/Shanghai' }
    },
    {
      member_id: 'member-a',
      result_type: 'diet_analysis',
      window: { period_days: 1, end_date: '2026-10-08', timezone: 'Asia/Shanghai' }
    },
    {
      member_id: 'member-a',
      result_type: 'diet_analysis',
      window: { period_days: 1, end_date: '2026-10-09', timezone: 'UTC' }
    }
  ]) {
    const state = panel({ api: { dietPeriodAnalysis: async () => result } })
    state.endDate.value = '2026-10-09'
    state.consent.value = true
    await state.enter()
    assert.deepEqual(state.calls, [])
    state.dispose()
  }
  for (const selection of [
    { record_id: 'meal-b', source_version: 3 },
    { record_id: 'meal-a', source_version: 1 }
  ]) {
    const state = panel({
      api: {
        dietAnalysis: async () => ({
          member_id: 'member-a',
          result_type: 'diet_analysis',
          records: [selection]
        })
      }
    })
    state.scope.value = 'meal'
    state.recordId.value = 'meal-a'
    state.consent.value = true
    await state.enter()
    assert.deepEqual(state.calls, [])
    state.dispose()
  }
})

test('成员、账号、窗口、记录或用途政策变化立即拒绝迟到的预检和绑定', async () => {
  for (const change of [
    (state) => {
      state.props.memberId = 'member-b'
    },
    (state) => {
      state.userStore.uid = 'actor-b'
    },
    (state) => {
      state.periodDays.value = 7
    },
    (state) => {
      state.endDate.value = '2026-10-08'
    },
    (state) => {
      state.props.records[0].source_version = 4
    },
    (state) => {
      state.props.configuration.policy_version = 'changed-policy'
    },
    (state) => {
      state.props.configuration.diet_analysis.processor = 'changed-provider-fingerprint'
    },
    (state) => {
      state.props.scopes = []
    }
  ]) {
    let finish
    const state = panel({
      api: {
        dietPeriodAnalysis: (id, selection) =>
          new Promise((resolve) => {
            finish = () =>
              resolve({
                member_id: id,
                result_type: 'diet_analysis',
                window: { ...selection, timezone: 'Asia/Shanghai' }
              })
          })
      }
    })
    state.endDate.value = '2026-10-09'
    state.consent.value = true
    const running = state.enter()
    change(state)
    finish()
    await running
    assert.deepEqual(state.calls, [])
    assert.equal(state.consent.value, false)
    assert.equal(state.attempt.value, null)
    state.dispose()
  }
  let finish
  const state = panel({
    api: {
      createDietAnalyst: () =>
        new Promise((resolve) => {
          finish = resolve
        })
    }
  })
  state.consent.value = true
  const running = state.enter()
  await new Promise((resolve) => setImmediate(resolve))
  state.props.memberId = 'member-b'
  finish({ member_id: 'member-a', agent_slug: 'health-diet-analyst', thread_id: 'old-thread' })
  await running
  assert.equal(
    state.calls.some(([kind]) => ['run', 'navigate'].includes(kind)),
    false
  )
  state.dispose()
})

test('未知Run响应可重试同一原文、线程和请求键，实际模板保留恢复入口', async () => {
  const submitted = []
  const state = panel({
    agentApi: {
      createAgentRun: async (data) => {
        submitted.push(clone(data))
        if (submitted.length === 1) throw Error('synthetic network failure')
      }
    }
  })
  state.endDate.value = '2026-10-09'
  state.consent.value = true
  await state.enter()
  const buttons = nodes(state.template(), 'a-button')
  assert.equal(buttons.length, 2)
  assert.equal(buttons[1].props.disabled, false)
  assert.match(state.error.value, /原请求/)
  await buttons[0].props.onClick()
  assert.deepEqual(submitted[0], submitted[1])
  assert.equal(state.calls.filter(([kind]) => kind === 'binding').length, 1)
  assert.equal(state.calls.filter(([kind]) => kind === 'navigate').length, 1)
  state.dispose()
})

test('确定的版本、授权和服务失败需重新同意，卸载后请求不再导航', async () => {
  for (const status of [401, 403, 404, 409, 410, 422, 503]) {
    const state = panel({
      api: {
        createDietAnalyst: async () => {
          throw Object.assign(Error('合成错误'), { status })
        }
      }
    })
    state.consent.value = true
    await state.enter()
    assert.equal(state.attempt.value, null)
    assert.equal(state.consent.value, false)
    assert.equal(state.working.value, false)
    assert.ok(state.error.value)
    state.dispose()
  }
  let finish
  const state = panel({
    agentApi: {
      createAgentRun: () =>
        new Promise((resolve) => {
          finish = resolve
        })
    }
  })
  state.consent.value = true
  const running = state.enter()
  await new Promise((resolve) => setImmediate(resolve))
  state.dispose()
  finish({ status: 'queued' })
  await running
  assert.equal(
    state.calls.some(([kind]) => kind === 'navigate'),
    false
  )
})

test('负控移除 epoch 核对后，旧窗口响应会错误提交同意和Run，独立oracle可反证', async () => {
  const defective = script.replace('epoch === ticket && canUse.value', 'canUse.value')
  assert.notEqual(defective, script)
  let finish
  const state = panel(
    {
      api: {
        dietPeriodAnalysis: (id, selection) =>
          new Promise((resolve) => {
            finish = () =>
              resolve({
                member_id: id,
                result_type: 'diet_analysis',
                window: { ...selection, timezone: 'Asia/Shanghai' }
              })
          })
      }
    },
    defective
  )
  state.endDate.value = '2026-10-09'
  state.consent.value = true
  const running = state.enter()
  state.periodDays.value = 7
  finish()
  await running
  assert.throws(
    () =>
      assert.equal(
        state.calls.some(([kind]) => kind === 'run'),
        false
      ),
    /true !== false/
  )
  state.dispose()
})
