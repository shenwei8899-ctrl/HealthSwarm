import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import process from 'node:process'
import { computed, effectScope, isRef, nextTick, reactive, ref, watch } from 'vue'
import * as Vue from 'vue'
import { parse, compileTemplate } from 'vue/compiler-sfc'
import { renderToString } from 'vue/server-renderer'
import { mealLabels, nutrientLabels, nutrientText } from '../src/utils/healthVision.js'

const source = await readFile(
  process.env.HEALTH_SAFE_PLANNER_TEST_SOURCE ||
    new URL('../src/components/health/HealthSafeMealPlanner.vue', import.meta.url),
  'utf8'
)
const script = source
  .match(/<script setup>([\s\S]*?)<\/script>/)[1]
  .replace(/^import[\s\S]*?from ['"][^'"]+['"]\s*\n/gm, '')

const nutrition = {
  energy_kcal: '460',
  protein_g: '25',
  fat_g: '12',
  carbohydrate_g: '55',
  sodium_mg: '320'
}
const snapshot = (name = '鸡蛋炒饭', recipe = 'recipe-a') => ({
  member_id: 'member-a',
  plan_id: 'plan-a',
  version: 3,
  status: 'draft',
  plan_date: '2026-10-09',
  nutrition: { complete: true, totals: nutrition },
  meals: [
    {
      meal_type: 'lunch',
      nutrition: { complete: true, totals: nutrition },
      dishes: [
        {
          dish_index: 0,
          name,
          recipe_version_id: recipe,
          planned_grams: '200',
          nutrition,
          ingredients: [
            { name: '鸡蛋', planned_grams: '50', source: '合成资料', dataset_version: 'fixture-1' }
          ]
        }
      ]
    }
  ]
})
const selection = {
  plan_id: 'plan-a',
  version: 3,
  rule_code: 'approved-basic',
  rule_version: 7,
  profile_version: 2
}
const sources = () => ({
  plan: { id: 'plan-a', version: 3, content_hash: 'plan-hash' },
  profiles: { 'member-a': { id: 'profile-a', version: 2, status: 'ready', reason: null } },
  rules: { rule_code: 'approved-basic', version: 7, status: 'ready', reason: null }
})
const output = (operation = 'swap') => ({
  preview_id: 'run-receipt-a',
  scope: 'single_member_saved_plan',
  member_id: 'member-a',
  operation,
  result: {
    status: 'ready',
    reason: null,
    sources: sources(),
    ...(operation === 'swap'
      ? {
          meal_type: 'lunch',
          dish_index: 0,
          candidates: [
            {
              recipe_version_id: 'replacement-a',
              name: '番茄鸡蛋饭',
              planned_grams: '200',
              nutrition_difference: { ...nutrition, energy_kcal: '-15', protein_g: '2' },
              plan_snapshot: {
                ...snapshot('番茄鸡蛋饭', 'replacement-a'),
                nutrition: { complete: true, totals: { ...nutrition, energy_kcal: '445' } }
              },
              safety_check: { status: 'passed' }
            }
          ]
        }
      : {
          plan_snapshot: snapshot('清蒸鱼饭', 'replacement-b'),
          preview_hash: 'owner-preview-hash',
          safety_check: { status: 'passed' }
        })
  }
})
const deferred = () => {
  let resolve, reject
  const promise = new Promise((finish, fail) => {
    resolve = finish
    reject = fail
  })
  return { promise, resolve, reject }
}
const failure = (status) => Object.assign(new Error('synthetic failure'), { status })
const clone = (value) => JSON.parse(JSON.stringify(value))

/** 执行实际组件脚本与watcher，API stub只提供独立业务结果。 */
function panel(options = {}) {
  const props = reactive({
    memberId: 'member-a',
    scopes: ['diet_edit', 'profile_view', 'ai_use'],
    configuration: {
      policy_version: 'policy-a',
      meal_plan: { available: true, processor: 'approved-provider' }
    },
    plan: snapshot(),
    disabled: false,
    ...options.props
  })
  const calls = [],
    events = []
  const scope = effectScope()
  let cleanup, submitted
  const api = {
    professionalProfile: async (member) => {
      calls.push(['profile', member])
      return { status: 'ready', version: 2 }
    },
    approvedQualityRules: async (code) => {
      calls.push(['rules', code])
      return { status: 'ready', version: 7 }
    },
    consent: async (...args) => {
      calls.push(['consent', ...args])
    },
    createSafeMealPlanner: async (member, body) => {
      calls.push(['binding', member, clone(body)])
      const safe_selection = { ...body }
      delete safe_selection.client_request_id
      return {
        member_id: member,
        thread_id: 'thread-a',
        agent_slug: 'health-meal-planner',
        safe_selection
      }
    },
    safeSwapMealPlan: async (id, body) => {
      calls.push(['safe-swap', id, clone(body)])
      return { ...snapshot(), version: 4, applied_version: 4 }
    },
    safeRegenerateMealPlan: async (id, body) => {
      calls.push(['safe-regenerate', id, clone(body)])
      return { ...snapshot('清蒸鱼饭'), version: 4, applied_version: 4 }
    },
    saveMealPlan: async () => {
      assert.fail('安全确认不能走基础保存接口')
    },
    ...options.api
  }
  const agentApi = {
    createAgentRun: async (body) => {
      submitted = clone(body)
      calls.push(['run', submitted])
    },
    getRequest: async (id) => ({
      request: {
        request_id: id,
        thread_id: 'thread-a',
        status: 'dispatched',
        dispatched_run_id: 'run-a'
      }
    }),
    getAgentRunResult: async (id) => ({
      agent_run_id: id,
      thread_id: 'thread-a',
      request_id: submitted.meta.request_id,
      agent_slug: 'health-meal-planner',
      status: 'completed',
      output: JSON.stringify(options.output || output())
    }),
    cancelRequest: async (id) => {
      calls.push(['cancel-request', id])
    },
    cancelAgentRun: async (id) => {
      calls.push(['cancel-run', id])
    },
    ...options.agent
  }
  const factory = new Function(
    'ref',
    'computed',
    'watch',
    'onBeforeUnmount',
    'defineProps',
    'defineEmits',
    'api',
    'agentApi',
    'mealLabels',
    'nutrientLabels',
    'nutrientText',
    `${script}\nreturn { ruleCode,consent,operation,slot,notes,profile,rules,attempt,preview,candidateId,confirmation,working,polling,error,status,questions,canUse,canGenerate,canConfirm,selectedCandidate,previewSnapshot,loadSources,generate,poll,confirm,cancel,reset,busy,slots,reasons }`
  )
  const state = scope.run(() =>
    factory(
      ref,
      computed,
      watch,
      (fn) => {
        cleanup = fn
      },
      () => props,
      () =>
        (...args) =>
          events.push(args),
      api,
      agentApi,
      mealLabels,
      nutrientLabels,
      nutrientText
    )
  )
  return {
    ...state,
    props,
    calls,
    events,
    dispose: () => {
      cleanup()
      scope.stop()
    }
  }
}

async function prepare(state, operation = 'swap') {
  state.ruleCode.value = 'approved-basic'
  state.slot.value = 'lunch:0'
  state.operation.value = operation
  await state.loadSources()
  state.consent.value = true
  assert.equal(state.canGenerate.value, true)
}

test('专业来源与处理同意未齐时不能生成，批准规则代码按用户输入核对', async () => {
  const state = panel()
  assert.equal(state.canGenerate.value, false)
  state.ruleCode.value = '  approved-basic  '
  state.slot.value = 'lunch:0'
  await state.loadSources()
  assert.deepEqual(state.calls, [
    ['profile', 'member-a'],
    ['rules', 'approved-basic']
  ])
  assert.equal(state.canGenerate.value, false)
  await state.generate()
  assert.equal(
    state.calls.some(([kind]) => kind === 'binding'),
    false
  )
  state.consent.value = true
  assert.equal(state.canGenerate.value, true)
  state.dispose()
})

test('缺少专业档案查看授权、跨成员或家庭餐单均不能调用单成员入口', async () => {
  for (const props of [
    { scopes: ['diet_edit', 'ai_use'] },
    { memberId: 'member-b' },
    { plan: { ...snapshot(), kind: 'family_meal_plan' } }
  ]) {
    const state = panel({ props })
    state.ruleCode.value = 'approved-basic'
    state.consent.value = true
    assert.equal(state.canUse.value, false)
    await state.loadSources()
    await state.generate()
    assert.deepEqual(state.calls, [])
    state.dispose()
  }
})

test('AI换菜冻结完整来源和用户菜位，模型运行只创建预览', async () => {
  const state = panel()
  await prepare(state)
  await state.generate()
  const binding = state.calls.find(([kind]) => kind === 'binding')
  assert.deepEqual(binding.slice(1, 2), ['member-a'])
  assert.deepEqual(
    Object.fromEntries(Object.entries(binding[2]).filter(([key]) => key !== 'client_request_id')),
    selection
  )
  const run = state.calls.find(([kind]) => kind === 'run')[1]
  assert.equal(run.thread_id, 'thread-a')
  assert.match(run.query, /午餐第1道菜/)
  assert.deepEqual(state.preview.value.selection, selection)
  assert.equal(state.attempt.value, null)
  assert.equal(state.canConfirm.value, false)
  assert.equal(
    state.calls.some(([kind]) => kind.startsWith('safe-')),
    false
  )
  state.candidateId.value = 'replacement-a'
  assert.equal(state.canConfirm.value, true)
  state.dispose()
})

test('创建会话返回错来源时停止派发，不能使用已有错位线程', async () => {
  const state = panel({
    api: {
      createSafeMealPlanner: async () => ({
        thread_id: 'foreign-thread',
        member_id: 'member-a',
        agent_slug: 'health-meal-planner',
        safe_selection: { ...selection, profile_version: 99 }
      })
    }
  })
  await prepare(state)
  await state.generate()
  assert.equal(
    state.calls.some(([kind]) => kind === 'run'),
    false
  )
  assert.equal(state.preview.value, null)
  assert.match(state.error.value, /未确认/)
  state.dispose()
})

for (const [name, change] of [
  [
    '餐单ID',
    (p) => {
      p.result.sources.plan.id = 'foreign-plan'
    }
  ],
  [
    '餐单版本',
    (p) => {
      p.result.sources.plan.version = 4
    }
  ],
  [
    '档案版本',
    (p) => {
      p.result.sources.profiles['member-a'].version = 3
    }
  ],
  [
    '额外成员来源',
    (p) => {
      p.result.sources.profiles['member-b'] = { version: 2 }
    }
  ],
  [
    '规则代码',
    (p) => {
      p.result.sources.rules.rule_code = 'other-rule'
    }
  ],
  [
    '规则版本',
    (p) => {
      p.result.sources.rules.version = 8
    }
  ],
  [
    '档案未就绪',
    (p) => {
      p.result.sources.profiles['member-a'].status = 'not_ready'
    }
  ],
  [
    '规则未就绪',
    (p) => {
      p.result.sources.rules.status = 'not_ready'
    }
  ],
  [
    '错误操作',
    (p) => {
      p.operation = 'regeneration'
    }
  ],
  [
    '错误餐次',
    (p) => {
      p.result.meal_type = 'dinner'
    }
  ],
  [
    '错误菜位',
    (p) => {
      p.result.dish_index = 1
    }
  ],
  [
    '输出成员',
    (p) => {
      p.member_id = 'member-b'
    }
  ],
  [
    '输出范围',
    (p) => {
      p.scope = 'family'
    }
  ]
]) {
  test(`拒绝${name}错位的终态预览，无法确认业务写入`, async () => {
    const wrong = output()
    change(wrong)
    const state = panel({ output: wrong })
    await prepare(state)
    await state.generate()
    assert.equal(state.preview.value, null)
    assert.equal(state.canConfirm.value, false)
    await state.confirm()
    assert.equal(
      state.calls.some(([kind]) => kind.startsWith('safe-')),
      false
    )
    state.dispose()
  })
}

for (const [name, field, value] of [
  ['Run ID', 'agent_run_id', 'foreign-run'],
  ['Request ID', 'request_id', 'foreign-request'],
  ['线程', 'thread_id', 'foreign-thread'],
  ['角色', 'agent_slug', 'health-consultation']
]) {
  test(`拒绝${name}错位的Run终态，不能从相邻运行猜测结果`, async () => {
    let requestId
    const state = panel({
      agent: {
        createAgentRun: async (body) => {
          requestId = body.meta.request_id
        },
        getAgentRunResult: async () => ({
          agent_run_id: 'run-a',
          thread_id: 'thread-a',
          request_id: requestId,
          agent_slug: 'health-meal-planner',
          status: 'completed',
          output: JSON.stringify(output()),
          [field]: value
        })
      }
    })
    await prepare(state)
    await state.generate()
    assert.equal(state.preview.value, null)
    assert.equal(state.canConfirm.value, false)
    state.dispose()
  })
}

test('Request线程错位时不读取其Run，清晰保留恢复操作', async () => {
  let readRun = 0
  const state = panel({
    agent: {
      getRequest: async (id) => ({
        request: {
          request_id: id,
          thread_id: 'foreign-thread',
          status: 'dispatched',
          dispatched_run_id: 'foreign-run'
        }
      }),
      getAgentRunResult: async () => {
        readRun++
        return {}
      }
    }
  })
  await prepare(state)
  await state.generate()
  assert.equal(readRun, 0)
  assert.equal(state.preview.value, null)
  assert.ok(state.attempt.value)
  state.dispose()
})

test('Request ID错位时不读取其Run，不能接收其他请求的业务结果', async () => {
  let readRun = 0
  const state = panel({
    agent: {
      getRequest: async () => ({
        request: {
          request_id: 'foreign-request',
          thread_id: 'thread-a',
          status: 'dispatched',
          dispatched_run_id: 'foreign-run'
        }
      }),
      getAgentRunResult: async () => {
        readRun++
        return {}
      }
    }
  })
  await prepare(state)
  await state.generate()
  assert.equal(readRun, 0)
  assert.equal(state.preview.value, null)
  state.dispose()
})

for (const [name, alter] of [
  [
    '成员',
    (p) => {
      p.memberId = 'member-b'
    }
  ],
  [
    '餐单版本',
    (p) => {
      p.plan.version = 4
    }
  ],
  [
    '授权',
    (p) => {
      p.scopes = ['diet_edit']
    }
  ],
  [
    '处理政策',
    (p) => {
      p.configuration.policy_version = 'policy-b'
    }
  ]
]) {
  test(`${name}变化立即清理私有预览并丢弃迟到专业来源`, async () => {
    const late = deferred()
    const state = panel({ api: { professionalProfile: () => late.promise } })
    state.ruleCode.value = 'approved-basic'
    const pending = state.loadSources()
    alter(state.props)
    late.resolve({ status: 'ready', version: 2 })
    await pending
    await nextTick()
    assert.equal(state.profile.value, null)
    assert.equal(state.rules.value, null)
    assert.equal(state.preview.value, null)
    assert.equal(state.consent.value, false)
    assert.equal(state.working.value, false)
    state.dispose()
  })
}

test('成员变化后的迟到Run不能回填旧成员结果', async () => {
  const late = deferred()
  const state = panel({ agent: { getAgentRunResult: () => late.promise } })
  await prepare(state)
  const pending = state.generate()
  while (!state.polling.value) await nextTick()
  state.props.memberId = 'member-b'
  late.resolve({
    agent_run_id: 'run-a',
    thread_id: 'thread-a',
    request_id: 'obsolete',
    agent_slug: 'health-meal-planner',
    status: 'completed',
    output: JSON.stringify(output())
  })
  await pending
  assert.equal(state.preview.value, null)
  assert.equal(state.attempt.value, null)
  assert.equal(state.polling.value, false)
  assert.equal(state.profile.value, null)
  state.dispose()
})

test('ready但没有候选时明确未就绪，不能提交确认', async () => {
  const empty = output()
  empty.result.candidates = []
  empty.result.reason = 'no_eligible_candidates'
  const state = panel({ output: empty })
  await prepare(state)
  await state.generate()
  assert.equal(state.preview.value.result.status, 'ready')
  assert.equal(state.previewSnapshot.value, null)
  assert.equal(state.canConfirm.value, false)
  await state.confirm()
  assert.equal(
    state.calls.some(([kind]) => kind.startsWith('safe-')),
    false
  )
  assert.match(state.reasons.no_eligible_candidates, /没有合格换菜候选/)
  state.dispose()
})

test('needs_input只展示追问，不将其当成可保存预览', async () => {
  const state = panel({
    output: {
      scope: 'single_member_saved_plan',
      member_id: 'member-a',
      status: 'needs_input',
      questions: ['请补充午餐要求', { bad: true }]
    }
  })
  await prepare(state)
  await state.generate()
  assert.deepEqual(state.questions.value, ['请补充午餐要求'])
  assert.equal(state.preview.value, null)
  assert.equal(state.attempt.value, null)
  assert.equal(state.canConfirm.value, false)
  state.dispose()
})

test('确认保存新版本使用安全换菜Owner，明确提示重新专业审核', async () => {
  const state = panel()
  await prepare(state)
  await state.generate()
  state.candidateId.value = 'replacement-a'
  await state.confirm()
  const saved = state.calls.find(([kind]) => kind === 'safe-swap')
  assert.equal(saved[1], 'plan-a')
  const { client_request_id, ...data } = saved[2]
  assert.ok(client_request_id)
  assert.deepEqual(data, {
    version: 3,
    rule_code: 'approved-basic',
    rule_version: 7,
    profile_version: 2,
    meal_type: 'lunch',
    dish_index: 0,
    recipe_version_id: 'replacement-a'
  })
  assert.equal(state.preview.value, null)
  assert.equal(state.confirmation.value, null)
  assert.equal(state.events.find(([event]) => event === 'saved')[1].applied_version, 4)
  assert.match(state.status.value, /版本 4.*重新.*专业审核/)
  state.dispose()
})

const completeRun = (requestId, payload = output()) => ({
  agent_run_id: 'run-a',
  request_id: requestId,
  thread_id: 'thread-a',
  agent_slug: 'health-meal-planner',
  status: 'completed',
  output: JSON.stringify(payload)
})

for (const [name, mutate] of [
  [
    'AI授权403',
    () => {
      throw failure(403)
    }
  ],
  [
    'AI回执失效410',
    () => {
      throw failure(410)
    }
  ],
  [
    'Run ID',
    (run) => {
      run.agent_run_id = 'foreign-run'
    }
  ],
  [
    'Request ID',
    (run) => {
      run.request_id = 'foreign-request'
    }
  ],
  [
    '线程',
    (run) => {
      run.thread_id = 'foreign-thread'
    }
  ],
  [
    '角色',
    (run) => {
      run.agent_slug = 'health-consultation'
    }
  ],
  [
    '非终态',
    (run) => {
      run.status = 'running'
    }
  ],
  [
    '预览收据',
    (run) => {
      const value = JSON.parse(run.output)
      value.preview_id = 'other-receipt'
      run.output = JSON.stringify(value)
    }
  ],
  [
    '输出范围',
    (run) => {
      const value = JSON.parse(run.output)
      value.scope = 'family'
      run.output = JSON.stringify(value)
    }
  ],
  [
    '输出成员',
    (run) => {
      const value = JSON.parse(run.output)
      value.member_id = 'member-b'
      run.output = JSON.stringify(value)
    }
  ],
  [
    '输出操作',
    (run) => {
      const value = JSON.parse(run.output)
      value.operation = 'regeneration'
      run.output = JSON.stringify(value)
    }
  ],
  [
    '完整业务结果',
    (run) => {
      const value = JSON.parse(run.output)
      value.result.candidates[0].planned_grams = '250'
      run.output = JSON.stringify(value)
    }
  ]
]) {
  test(`首次确认前AI回执${name}变化，即使普通安全换菜仍有权限也不能写入`, async () => {
    let requestId,
      reads = 0,
      writes = 0
    const state = panel({
      api: {
        safeSwapMealPlan: async () => {
          writes++
          return { ...snapshot(), applied_version: 4, version: 4 }
        }
      },
      agent: {
        createAgentRun: async (body) => {
          requestId = body.meta.request_id
        },
        getAgentRunResult: async () => {
          reads++
          const run = completeRun(requestId)
          if (reads > 1) mutate(run)
          return run
        }
      }
    })
    await prepare(state)
    await state.generate()
    assert.deepEqual(clone(state.preview.value.authority), {
      run_id: 'run-a',
      request_id: requestId,
      thread_id: 'thread-a'
    })
    state.candidateId.value = 'replacement-a'
    assert.equal(state.canConfirm.value, true)
    await state.confirm()
    assert.equal(writes, 0, '普通业务接口权限不能替代当前AI预览权限')
    assert.equal(reads, 2, '首次确认必须重读所属AI运行')
    assert.equal(state.confirmation.value, null)
    assert.equal(state.preview.value, null)
    assert.ok(state.events.some(([event]) => event === 'invalidated'))
    state.dispose()
  })
}

test('首次确认重新读取AI回执期间切换成员，迟到结果不能触发安全写入', async () => {
  const late = deferred()
  let requestId,
    reads = 0,
    writes = 0
  const state = panel({
    api: {
      safeSwapMealPlan: async () => {
        writes++
        return { ...snapshot(), applied_version: 4, version: 4 }
      }
    },
    agent: {
      createAgentRun: async (body) => {
        requestId = body.meta.request_id
      },
      getAgentRunResult: async () => {
        reads++
        return reads === 1 ? completeRun(requestId) : late.promise
      }
    }
  })
  await prepare(state)
  await state.generate()
  state.candidateId.value = 'replacement-a'
  const pending = state.confirm()
  assert.equal(state.working.value, true)
  assert.equal(state.confirmation.value, null)
  state.props.memberId = 'member-b'
  late.resolve(completeRun(requestId))
  await pending
  assert.equal(writes, 0)
  assert.equal(state.preview.value, null)
  assert.equal(state.confirmation.value, null)
  assert.equal(state.working.value, false)
  state.dispose()
})

test('首次确认前AI回执读取断线不冻结确认包，可重新核验后提交一次', async () => {
  let requestId,
    reads = 0,
    writes = 0
  const state = panel({
    api: {
      safeSwapMealPlan: async () => {
        writes++
        return { ...snapshot(), applied_version: 4, version: 4 }
      }
    },
    agent: {
      createAgentRun: async (body) => {
        requestId = body.meta.request_id
      },
      getAgentRunResult: async () => {
        reads++
        if (reads === 2) throw new Error('revalidation offline')
        return completeRun(requestId)
      }
    }
  })
  await prepare(state)
  await state.generate()
  state.candidateId.value = 'replacement-a'
  await state.confirm()
  assert.equal(writes, 0)
  assert.equal(state.confirmation.value, null)
  assert.ok(state.preview.value)
  assert.equal(state.canConfirm.value, true)
  await state.confirm()
  assert.equal(reads, 3)
  assert.equal(writes, 1)
  assert.ok(state.events.some(([event]) => event === 'saved'))
  state.dispose()
})

test('业务已提交但响应丢失时按原幂等包恢复，不再读取因保存失效的旧AI回执', async () => {
  let requestId,
    reads = 0,
    persistedVersion = 3
  const packets = []
  const state = panel({
    api: {
      safeSwapMealPlan: async (id, body) => {
        packets.push([id, clone(body)])
        if (packets.length === 1) {
          persistedVersion = 4
          throw new Error('response lost after actual commit')
        }
        assert.deepEqual(packets[1], packets[0])
        return { ...snapshot(), version: persistedVersion, applied_version: 4 }
      }
    },
    agent: {
      createAgentRun: async (body) => {
        requestId = body.meta.request_id
      },
      getAgentRunResult: async () => {
        reads++
        if (persistedVersion > 3) throw failure(410)
        return completeRun(requestId)
      }
    }
  })
  await prepare(state)
  await state.generate()
  state.candidateId.value = 'replacement-a'
  await state.confirm()
  assert.equal(persistedVersion, 4)
  assert.equal(reads, 2)
  assert.ok(state.confirmation.value)
  state.candidateId.value = 'foreign-candidate'
  await state.confirm()
  assert.ok(
    state.events.some(([event]) => event === 'saved'),
    '已提交的业务结果应按原幂等键恢复为保存成功'
  )
  assert.equal(reads, 2, '业务幂等恢复不能依赖已因保存而失效的旧Run')
  assert.equal(packets.length, 2)
  assert.deepEqual(packets[1], packets[0])
  assert.equal(state.confirmation.value, null)
  assert.equal(state.events.find(([event]) => event === 'saved')[1].applied_version, 4)
  state.dispose()
})

for (const [name, fields] of [
  ['餐单', { plan_id: 'foreign-plan' }],
  ['成员', { member_id: 'member-b' }],
  ['应用版本', { applied_version: 5, version: 5 }],
  ['当前版本', { applied_version: 4, version: 3 }]
]) {
  test(`确认回读${name}错位不能宣告保存成功，保留原确认键等待恢复`, async () => {
    const state = panel({
      api: {
        safeSwapMealPlan: async () => ({ ...snapshot(), applied_version: 4, version: 4, ...fields })
      }
    })
    await prepare(state)
    await state.generate()
    state.candidateId.value = 'replacement-a'
    await state.confirm()
    assert.ok(state.confirmation.value)
    assert.ok(state.preview.value)
    assert.equal(
      state.events.some(([event]) => event === 'saved'),
      false
    )
    assert.match(state.error.value, /未确认/)
    state.dispose()
  })
}

test('整餐重生成仅在确认后提交Owner预览摘要，不使用Agent收据保存', async () => {
  const state = panel({ output: output('regeneration') })
  await prepare(state, 'regeneration')
  await state.generate()
  assert.equal(state.canConfirm.value, true)
  assert.equal(
    state.calls.some(([kind]) => kind.startsWith('safe-')),
    false
  )
  await state.confirm()
  const saved = state.calls.find(([kind]) => kind === 'safe-regenerate')
  assert.equal(saved[1], 'plan-a')
  assert.equal(saved[2].preview_hash, 'owner-preview-hash')
  assert.equal(Object.hasOwn(saved[2], 'preview_id'), false)
  assert.equal(Object.hasOwn(saved[2], 'recipe_version_id'), false)
  assert.equal(state.events.find(([event]) => event === 'saved')[1].version, 4)
  state.dispose()
})

for (const operation of ['swap', 'regeneration']) {
  for (const code of [500, 502, 503, 504]) {
    test(`${operation}确认写入后${code}保留原包，重试只形成一次业务修订`, async () => {
      const receipts = new Map(),
        packets = []
      let requestId,
        reads = 0,
        version = 3
      const method = operation === 'swap' ? 'safeSwapMealPlan' : 'safeRegenerateMealPlan'
      const state = panel({
        output: output(operation),
        api: {
          [method]: async (id, body) => {
            packets.push([id, clone(body)])
            if (!receipts.has(body.client_request_id)) {
              assert.equal(id, 'plan-a')
              assert.equal(body.version, 3)
              assert.equal(body.profile_version, 2)
              assert.equal(body.rule_version, 7)
              if (operation === 'swap') assert.equal(body.recipe_version_id, 'replacement-a')
              else assert.equal(body.preview_hash, 'owner-preview-hash')
              receipts.set(body.client_request_id, {
                ...snapshot(),
                version: ++version,
                applied_version: version
              })
              throw failure(code)
            }
            return receipts.get(body.client_request_id)
          }
        },
        agent: {
          createAgentRun: async (body) => {
            requestId = body.meta.request_id
          },
          getAgentRunResult: async () => {
            reads++
            if (version !== 3) throw failure(410)
            return { ...completeRun(requestId), output: JSON.stringify(output(operation)) }
          }
        }
      })
      await prepare(state, operation)
      await state.generate()
      if (operation === 'swap') state.candidateId.value = 'replacement-a'
      await state.confirm()
      assert.equal(version, 4, '第一次业务调用已经保存')
      assert.ok(state.preview.value)
      assert.ok(state.confirmation.value)
      assert.equal(
        state.events.some(([event]) => event === 'saved'),
        false
      )
      assert.match(state.error.value, /未收到.*原确认/)
      state.candidateId.value = 'foreign-candidate'
      await state.confirm()
      assert.deepEqual(packets[1], packets[0])
      assert.equal(receipts.size, 1)
      assert.equal(version, 4)
      assert.equal(reads, 2, '恢复幂等收据不能再次读取已失效Run')
      assert.equal(state.events.find(([event]) => event === 'saved')[1].applied_version, 4)
      assert.equal(state.confirmation.value, null)
      state.dispose()
    })
  }
}

test('首次确认Run重读503清除旧预览，未发送业务POST也未冻结确认包', async () => {
  let requestId,
    reads = 0,
    writes = 0
  const state = panel({
    api: {
      safeSwapMealPlan: async () => {
        writes++
        return { ...snapshot(), version: 4, applied_version: 4 }
      }
    },
    agent: {
      createAgentRun: async (body) => {
        requestId = body.meta.request_id
      },
      getAgentRunResult: async () => {
        if (++reads === 2) throw failure(503)
        return completeRun(requestId)
      }
    }
  })
  await prepare(state)
  await state.generate()
  state.candidateId.value = 'replacement-a'
  await state.confirm()
  assert.equal(writes, 0)
  assert.equal(state.preview.value, null)
  assert.equal(state.confirmation.value, null)
  assert.match(state.error.value, /未就绪/)
  state.dispose()
})

for (const code of [500, 502, 503, 504]) {
  test(`绑定POST${code}原键恢复同一线程并提交同一生成请求`, async () => {
    const packets = [],
      receipts = new Map()
    const state = panel({
      api: {
        createSafeMealPlanner: async (member, body) => {
          packets.push([member, clone(body)])
          if (!receipts.has(body.client_request_id)) {
            const { client_request_id, ...safe_selection } = body
            receipts.set(client_request_id, {
              member_id: member,
              thread_id: 'thread-a',
              agent_slug: 'health-meal-planner',
              safe_selection
            })
            throw failure(code)
          }
          return receipts.get(body.client_request_id)
        }
      }
    })
    await prepare(state)
    await state.generate()
    const original = clone(state.attempt.value)
    assert.equal(state.calls.filter(([kind]) => kind === 'run').length, 0)
    await state.generate()
    assert.deepEqual(packets[1], packets[0])
    assert.equal(receipts.size, 1)
    assert.equal(
      state.calls.find(([kind]) => kind === 'run')[1].meta.request_id,
      original.request_id
    )
    assert.ok(state.preview.value)
    state.dispose()
  })

  test(`Request POST/GET、Run GET和取消${code}均保留同一生成请求直到恢复`, async () => {
    const packets = [],
      requests = new Set()
    let requestReads = 0,
      runReads = 0
    const state = panel({
      agent: {
        createAgentRun: async (body) => {
          packets.push(clone(body))
          requests.add(body.meta.request_id)
          if (packets.length === 1) throw failure(code)
        },
        getRequest: async (id) => {
          if (++requestReads === 1) throw failure(code)
          return {
            request: {
              request_id: id,
              thread_id: 'thread-a',
              status: 'dispatched',
              dispatched_run_id: 'run-a'
            }
          }
        },
        getAgentRunResult: async () => {
          if (++runReads === 1) throw failure(code)
          return completeRun(packets[0].meta.request_id)
        },
        cancelRequest: async () => {
          throw failure(code)
        }
      }
    })
    await prepare(state)
    await state.generate()
    const original = clone(state.attempt.value)
    await state.generate()
    assert.deepEqual(packets[1], packets[0])
    assert.deepEqual(clone(state.attempt.value), original)
    await state.poll()
    assert.deepEqual(clone(state.attempt.value), original)
    await state.cancel()
    assert.deepEqual(clone(state.attempt.value), original)
    assert.equal(state.consent.value, true)
    assert.equal(requests.size, 1)
    await state.poll()
    assert.equal(state.attempt.value, null)
    assert.ok(state.preview.value)
    state.dispose()
  })
}

test('健康绑定POST404清除私有来源及同意，不按Agent Request尚未确认处理', async () => {
  const state = panel({
    api: {
      createSafeMealPlanner: async () => {
        throw failure(404)
      }
    }
  })
  await prepare(state)
  await state.generate()
  assert.equal(state.attempt.value, null)
  assert.equal(state.preview.value, null)
  assert.equal(state.profile.value, null)
  assert.equal(state.rules.value, null)
  assert.equal(state.consent.value, false)
  assert.equal(
    state.calls.some(([kind]) => kind === 'run'),
    false
  )
  assert.ok(state.events.some(([event, , code]) => event === 'invalidated' && code === 404))
  state.dispose()
})

test('未知确认结果重试固定幂等键和原请求，不采纳后来候选修改', async () => {
  const attempts = []
  const state = panel({
    api: {
      safeSwapMealPlan: async (id, body) => {
        attempts.push([id, clone(body)])
        if (attempts.length === 1) throw new Error('connection lost after commit')
        return { ...snapshot(), version: 4, applied_version: 4 }
      }
    }
  })
  await prepare(state)
  await state.generate()
  state.candidateId.value = 'replacement-a'
  await state.confirm()
  assert.ok(state.confirmation.value)
  assert.match(state.error.value, /未确认/)
  state.candidateId.value = 'foreign-candidate'
  await state.confirm()
  assert.deepEqual(attempts[1], attempts[0])
  assert.equal(attempts[1][1].recipe_version_id, 'replacement-a')
  assert.equal(state.confirmation.value, null)
  assert.ok(state.events.some(([event]) => event === 'saved'))
  state.dispose()
})

for (const code of [403, 404, 409, 410]) {
  test(`确认收到${code}时清理旧预览、同意和来源并通知页面刷新`, async () => {
    const state = panel({
      api: {
        safeSwapMealPlan: async () => {
          throw failure(code)
        }
      }
    })
    await prepare(state)
    await state.generate()
    state.candidateId.value = 'replacement-a'
    await state.confirm()
    assert.equal(state.preview.value, null)
    assert.equal(state.confirmation.value, null)
    assert.equal(state.profile.value, null)
    assert.equal(state.rules.value, null)
    assert.equal(state.consent.value, false)
    assert.ok(state.events.some(([event]) => event === 'invalidated'))
    assert.match(state.error.value, [403, 404].includes(code) ? /授权.*清除/ : /旧预览已失效/)
    state.dispose()
  })
}

test('轮询网络中断后可恢复同一Request，非终态不展示输出', async () => {
  let reads = 0,
    requestId
  const state = panel({
    agent: {
      createAgentRun: async (body) => {
        requestId = body.meta.request_id
      },
      getAgentRunResult: async () => {
        reads++
        if (reads === 1) throw new Error('offline')
        return {
          agent_run_id: 'run-a',
          thread_id: 'thread-a',
          request_id: requestId,
          agent_slug: 'health-meal-planner',
          status: reads === 2 ? 'running' : 'completed',
          output: JSON.stringify(output())
        }
      }
    }
  })
  await prepare(state)
  await state.generate()
  const fixedId = state.attempt.value.request_id
  assert.equal(state.preview.value, null)
  await state.poll()
  assert.equal(state.attempt.value.request_id, fixedId)
  assert.equal(state.preview.value, null)
  await state.poll()
  assert.equal(state.preview.value.preview_id, 'run-receipt-a')
  assert.equal(state.attempt.value, null)
  state.dispose()
})

test('Run提交未知以及Request读取取消404保留原请求，后续可恢复同一终态', async () => {
  let requestId,
    reads = 0
  const state = panel({
    agent: {
      createAgentRun: async (body) => {
        requestId = body.meta.request_id
        throw failure(404)
      },
      getRequest: async (id) => {
        reads++
        if (reads === 1) throw failure(404)
        return {
          request: {
            request_id: id,
            thread_id: 'thread-a',
            status: 'dispatched',
            dispatched_run_id: 'run-a'
          }
        }
      },
      cancelRequest: async () => {
        throw failure(404)
      },
      getAgentRunResult: async () => ({
        agent_run_id: 'run-a',
        thread_id: 'thread-a',
        request_id: requestId,
        agent_slug: 'health-meal-planner',
        status: 'completed',
        output: JSON.stringify(output())
      })
    }
  })
  await prepare(state)
  await state.generate()
  assert.ok(state.attempt.value, '提交结果未知时必须保留可恢复的原请求')
  const fixed = clone(state.attempt.value)
  assert.equal(fixed.request_id, requestId)
  await state.poll()
  assert.deepEqual(clone(state.attempt.value), fixed)
  await state.cancel()
  assert.deepEqual(clone(state.attempt.value), fixed)
  assert.equal(state.profile.value.version, 2)
  assert.equal(state.rules.value.version, 7)
  assert.equal(state.consent.value, true)
  assert.equal(
    state.events.some(([event]) => event === 'invalidated'),
    false
  )
  assert.match(state.error.value, /尚未确认/)
  await state.poll()
  assert.equal(state.attempt.value, null)
  assert.equal(state.preview.value.preview_id, 'run-receipt-a')
  state.dispose()
})

test('取消已派发请求先核对Request所属线程，再取消精确Run', async () => {
  const state = panel({
    agent: {
      getAgentRunResult: async () => {
        throw new Error('offline')
      },
      cancelRequest: async () => {
        throw failure(409)
      }
    }
  })
  await prepare(state)
  await state.generate()
  await state.cancel()
  assert.deepEqual(
    state.calls.filter(([kind]) => kind === 'cancel-run'),
    [['cancel-run', 'run-a']]
  )
  assert.equal(state.attempt.value, null)
  assert.equal(state.preview.value, null)
  state.dispose()
})

test('取消恢复发现错位Request不能取消其他线程Run', async () => {
  let phase = 'generate'
  const state = panel({
    agent: {
      getAgentRunResult: async () => {
        throw new Error('offline')
      },
      cancelRequest: async () => {
        phase = 'cancel'
        throw failure(409)
      },
      getRequest: async (id) => ({
        request: {
          request_id: id,
          thread_id: phase === 'cancel' ? 'foreign-thread' : 'thread-a',
          dispatched_run_id: 'run-a',
          status: 'dispatched'
        }
      })
    }
  })
  await prepare(state)
  await state.generate()
  await state.cancel()
  assert.equal(
    state.calls.some(([kind]) => kind === 'cancel-run'),
    false
  )
  assert.ok(state.attempt.value)
  state.dispose()
})

for (const boundary of ['request', 'result']) {
  test(`${boundary}轮询挂起时仍可取消，迟到响应不能恢复预览或生成状态`, async () => {
    const late = deferred()
    let called = false
    const state = panel({
      agent:
        boundary === 'request'
          ? {
              getRequest: () => {
                called = true
                return late.promise
              }
            }
          : {
              getAgentRunResult: () => {
                called = true
                return late.promise
              }
            }
    })
    await prepare(state)
    const pending = state.generate()
    while (!called) await nextTick()
    const requestId = state.attempt.value.request_id
    assert.equal(state.polling.value, true)
    await state.cancel()
    assert.ok(state.calls.some(([kind, id]) => kind === 'cancel-request' && id === requestId))
    assert.equal(state.attempt.value, null)
    assert.equal(state.polling.value, false)
    late.resolve(
      boundary === 'request'
        ? {
            request: {
              request_id: requestId,
              thread_id: 'thread-a',
              status: 'dispatched',
              dispatched_run_id: 'run-a'
            }
          }
        : {
            agent_run_id: 'run-a',
            thread_id: 'thread-a',
            request_id: requestId,
            agent_slug: 'health-meal-planner',
            status: 'completed',
            output: JSON.stringify(output())
          }
    )
    await pending
    assert.equal(state.preview.value, null)
    assert.equal(state.attempt.value, null)
    assert.equal(state.polling.value, false)
    state.dispose()
  })
}

test('取消响应丢失保留原请求和恢复入口，不能假定服务端已停止', async () => {
  const state = panel({
    agent: {
      getAgentRunResult: async () => {
        throw new Error('offline')
      },
      cancelRequest: async () => {
        throw new Error('cancel response lost')
      }
    }
  })
  await prepare(state)
  await state.generate()
  const fixed = state.attempt.value.request_id
  await state.cancel()
  assert.equal(state.attempt.value.request_id, fixed)
  assert.equal(state.preview.value, null)
  assert.equal(state.polling.value, false)
  assert.match(state.error.value, /未确认/)
  state.dispose()
})

test('取消提交尚未确认时，旧轮询结果也不得发布为可确认预览', async () => {
  const run = deferred(),
    cancelled = deferred()
  let called = false
  const state = panel({
    agent: {
      getAgentRunResult: () => {
        called = true
        return run.promise
      },
      cancelRequest: () => cancelled.promise
    }
  })
  await prepare(state)
  const generation = state.generate()
  while (!called) await nextTick()
  const requestId = state.attempt.value.request_id
  const cancelling = state.cancel()
  run.resolve({
    agent_run_id: 'run-a',
    thread_id: 'thread-a',
    request_id: requestId,
    agent_slug: 'health-meal-planner',
    status: 'completed',
    output: JSON.stringify(output())
  })
  await generation
  assert.equal(state.preview.value, null)
  assert.equal(state.canConfirm.value, false)
  cancelled.resolve()
  await cancelling
  assert.equal(state.attempt.value, null)
  assert.equal(state.preview.value, null)
  state.dispose()
})

function compileRender(template, filename) {
  const compiled = compileTemplate({
    source: template,
    filename,
    id: 'safe-planner-test',
    compilerOptions: { mode: 'function' }
  })
  assert.deepEqual(compiled.errors, [])
  return new Function('Vue', compiled.code)(Vue)
}

test('实际模板展示具体菜名、份量、营养差值及未保存和重新审核说明', async () => {
  const state = panel()
  await prepare(state)
  await state.generate()
  state.candidateId.value = 'replacement-a'
  const snapshotSource = await readFile(
    new URL('../src/components/health/HealthMealPlanSnapshot.vue', import.meta.url),
    'utf8'
  )
  const snapshotScript = snapshotSource
    .match(/<script setup>([\s\S]*?)<\/script>/)[1]
    .replace(/^import[\s\S]*?from ['"][^'"]+['"]\s*\n/gm, '')
  const { gramsText } = new Function(
    'defineProps',
    'defineEmits',
    `${snapshotScript}\nreturn { gramsText }`
  )(
    () => {},
    () => {}
  )
  const app = Vue.createSSRApp({
    render: compileRender(parse(source).descriptor.template.content, 'HealthSafeMealPlanner.vue'),
    setup: () => ({
      ...state.props,
      ...Object.fromEntries(
        Object.entries(state).map(([key, value]) => [key, isRef(value) ? value.value : value])
      ),
      mealLabels,
      nutrientLabels,
      nutrientText
    })
  })
  app.component('HealthMealPlanSnapshot', {
    props: { snapshot: Object, ruleChecked: Boolean, editable: Boolean },
    render: compileRender(
      parse(snapshotSource).descriptor.template.content,
      'HealthMealPlanSnapshot.vue'
    ),
    setup: () => ({ mealLabels, nutrientLabels, nutrientText, gramsText })
  })
  for (const tag of ['AInput', 'AButton', 'ASelect', 'ATextarea', 'ACheckbox', 'ATag']) {
    app.component(tag, { setup: (_, context) => () => Vue.h('div', context.slots.default?.()) })
  }
  app.component('AAlert', { props: ['message'], setup: (props) => () => Vue.h('p', props.message) })
  const html = await renderToString(app)
  assert.match(html, /番茄鸡蛋饭/)
  assert.match(html, /200.*g/)
  assert.match(html, /能量：-15 kcal/)
  assert.match(html, /460 kcal → 445 kcal/)
  assert.match(html, /尚未保存/)
  assert.match(html, /尚未形成专业审核决定/)
  assert.match(html, /原批准与采用状态将失效/)
  state.dispose()
})
