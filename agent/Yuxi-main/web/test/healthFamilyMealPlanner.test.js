import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import process from 'node:process'
import * as Vue from 'vue'
import { parse, compileTemplate } from 'vue/compiler-sfc'
import { renderToString } from 'vue/server-renderer'
import { mealLabels, nutrientLabels, nutrientText } from '../src/utils/healthVision.js'

const source = await readFile(
  process.env.HEALTH_FAMILY_PLANNER_TEST_SOURCE ||
    new URL('../src/components/health/HealthFamilyMealPlanner.vue', import.meta.url),
  'utf8'
)
const script = source
  .match(/<script setup>([\s\S]*?)<\/script>/)[1]
  .replace(/^import[\s\S]*?from ['"][^'"]+['"]\s*\n/gm, '')
const clone = (value) => JSON.parse(JSON.stringify(value))
const failure = (status) => Object.assign(new Error('synthetic failure'), { status })
const nutrition = (energy) => ({
  complete: true,
  totals: {
    energy_kcal: String(energy),
    protein_g: '10',
    fat_g: '5',
    carbohydrate_g: '20',
    sodium_mg: '100'
  }
})
const roster = () =>
  ['a', 'b', 'c'].map((id) => ({
    id,
    display_name: { a: '主成员', b: '共餐成员', c: '新增成员' }[id],
    scopes: ['diet_edit', 'profile_view', 'ai_use']
  }))
const dish = (grams, name = '清蒸鸡肉饭', index = 0) => ({
  dish_index: 0,
  family_dish_index: index,
  recipe_version_id: 'recipe-original',
  name,
  planned_grams: String(grams),
  cooking_state: '熟食',
  source: '合成批准资料',
  dataset_version: 'fixture-v1',
  ingredients: [{ name: '鸡肉', planned_grams: '20' }]
})
const family = (a = 300, b = 60) => ({
  member_id: 'a',
  plan_id: 'plan-a',
  version: 3,
  scope: 'family_recipe_draft',
  plan_date: '2026-10-09',
  nutrition: nutrition(a + b),
  meals: ['breakfast', 'lunch', 'dinner'].map((meal_type) => ({
    meal_type,
    participant_ids: meal_type === 'breakfast' ? ['a', 'b'] : ['a']
  })),
  members: {
    a: {
      member_id: 'a',
      covered_meals: ['breakfast', 'lunch', 'dinner'],
      full_day_covered: true,
      nutrition: nutrition(a),
      meals: ['breakfast', 'lunch', 'dinner'].map((meal_type, index) => ({
        meal_type,
        nutrition: nutrition(100),
        dishes: [dish([50, 100, 150][index])]
      }))
    },
    b: {
      member_id: 'b',
      covered_meals: ['breakfast'],
      full_day_covered: false,
      nutrition: nutrition(b),
      meals: [{ meal_type: 'breakfast', nutrition: nutrition(b), dishes: [dish(60)] }]
    }
  }
})
const selection = () => ({
  plan_id: 'plan-a',
  version: 3,
  rule_code: 'approved-family',
  rule_version: 7,
  profile_versions: { a: 2, b: 4 }
})
function output(operation = 'swap') {
  const snapshot = family(305, 66)
  if (operation === 'participation') snapshot.members.a.meals[0].dishes[0].planned_grams = '55'
  const spec = {
    kind: 'family',
    plan_date: '2026-10-09',
    meals: snapshot.meals.map((meal) => ({
      meal_type: meal.meal_type,
      participant_ids: [...meal.participant_ids],
      dishes: [
        {
          recipe_version_id: 'recipe-original',
          member_portions: meal.participant_ids.map((id) => ({
            member_id: id,
            grams: snapshot.members[id].meals.find((row) => row.meal_type === meal.meal_type)
              .dishes[0].planned_grams,
            portion_reference_id: null,
            portion_count: null
          }))
        }
      ]
    }))
  }
  return {
    preview_id: 'family-receipt',
    scope: 'family_saved_plan',
    member_id: 'a',
    member_ids: ['a', 'b'],
    operation,
    result: {
      status: 'ready',
      reason: null,
      sources: {
        plan: { id: 'plan-a', version: 3 },
        rules: { rule_code: 'approved-family', version: 7, status: 'ready' },
        profiles: { a: { version: 2, status: 'ready' }, b: { version: 4, status: 'ready' } }
      },
      ...(operation === 'swap'
        ? {
            meal_type: 'breakfast',
            dish_index: 0,
            candidates: [
              {
                recipe_version_id: 'recipe-candidate',
                name: '番茄鸡肉饭',
                member_nutrition_differences: { a: { energy_kcal: '5' }, b: { energy_kcal: '6' } },
                plan_snapshot: snapshot,
                plan_spec: spec
              }
            ]
          }
        : { plan_spec: spec, plan_snapshot: snapshot, preview_hash: 'authoritative-preview-hash' })
    }
  }
}
function deferred() {
  let resolve, reject
  const promise = new Promise((done, fail) => {
    resolve = done
    reject = fail
  })
  return { promise, resolve, reject }
}
function panel(options = {}) {
  const props = Vue.reactive({
    memberId: 'a',
    members: roster(),
    configuration: {
      policy_version: 'policy-a',
      meal_plan: { available: true, processor: 'configured-provider' }
    },
    plan: family(),
    disabled: false,
    ...options.props
  })
  const calls = [],
    events = [],
    scope = Vue.effectScope()
  let cleanup, submitted
  const api = {
    professionalProfile: async (id) => {
      calls.push(['profile', id])
      return { status: 'ready', version: { a: 2, b: 4, c: 6 }[id] }
    },
    approvedQualityRules: async (code) => {
      calls.push(['rules', code])
      return { status: 'ready', version: 7 }
    },
    consent: async (id, data) => {
      calls.push(['consent', id, clone(data)])
    },
    createFamilyMealPlanner: async (id, data) => {
      calls.push(['binding', id, clone(data)])
      const family_selection = clone(data)
      delete family_selection.client_request_id
      return {
        member_id: id,
        thread_id: 'family-thread',
        agent_slug: 'health-meal-planner',
        family_selection
      }
    },
    ...Object.fromEntries(
      ['familySafeSwapMealPlan', 'familySafeRegenerateMealPlan', 'familyParticipationMealPlan'].map(
        (method) => [
          method,
          async (id, data) => {
            calls.push([method, id, clone(data)])
            return { ...family(305, 66), version: 4, applied_version: 4 }
          }
        ]
      )
    ),
    ...options.api
  }
  const agentApi = {
    createAgentRun: async (data) => {
      submitted = clone(data)
      calls.push(['run', clone(data)])
    },
    getRequest: async (id) => ({
      request: {
        request_id: id,
        thread_id: 'family-thread',
        status: 'dispatched',
        dispatched_run_id: 'family-run'
      }
    }),
    getAgentRunResult: async (id) => {
      calls.push(['run-read', id])
      return {
        agent_run_id: id,
        request_id: submitted.meta.request_id,
        thread_id: 'family-thread',
        agent_slug: 'health-meal-planner',
        status: 'completed',
        output: JSON.stringify(options.output || output(options.operation))
      }
    },
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
    `${script}\nreturn { ruleCode,operation,slot,notes,extraMembers,consents,profiles,rules,attempt,preview,candidateId,confirmation,working,polling,error,status,questions,originalIds,selectedIds,canUse,busy,slots,allConsented,sourcesReady,canGenerate,selectedCandidate,previewSnapshot,canConfirm,loadSources,generate,poll,confirm,cancel,reset,memberName,reasons }`
  )
  const state = scope.run(() =>
    factory(
      Vue.ref,
      Vue.computed,
      Vue.watch,
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
  state.operation.value = operation
  state.slot.value = 'breakfast:0'
  if (operation === 'participation') state.notes.value = '将主成员早餐份量调整为55克，保留其他份量'
  state.ruleCode.value = 'approved-family'
  await state.loadSources()
  state.consents.value = Object.fromEntries(state.selectedIds.value.map((id) => [id, true]))
  assert.equal(state.canGenerate.value, true)
}

test('所有成员分别核对专业来源、授权与用途同意，不能以入口成员同意代替', async () => {
  const state = panel()
  state.ruleCode.value = '  approved-family  '
  state.slot.value = 'breakfast:0'
  await state.loadSources()
  assert.deepEqual(
    state.calls.map((call) => call.slice(0, 2)),
    [
      ['profile', 'a'],
      ['profile', 'b'],
      ['rules', 'approved-family']
    ]
  )
  state.consents.value = { a: true }
  await state.generate()
  assert.equal(
    state.calls.some(([kind]) => kind === 'binding'),
    false
  )
  state.consents.value.b = true
  await state.generate()
  assert.deepEqual(
    state.calls.filter(([kind]) => kind === 'consent').map((call) => [call[1], call[2].purpose]),
    [
      ['a', 'meal_plan'],
      ['b', 'meal_plan']
    ]
  )
  const binding = state.calls.find(([kind]) => kind === 'binding')[2]
  const { client_request_id, ...actual } = binding
  assert.ok(client_request_id)
  assert.deepEqual(actual, selection())
  assert.equal(
    state.calls.some(([kind]) => kind.startsWith('familySafe')),
    false
  )
  state.dispose()
})

for (const scope of ['diet_edit', 'profile_view', 'ai_use'])
  test(`第二成员缺少${scope}时禁止读取及生成`, async () => {
    const members = roster()
    members[1].scopes = members[1].scopes.filter((item) => item !== scope)
    const state = panel({ props: { members } })
    state.ruleCode.value = 'approved-family'
    state.consents.value = { a: true, b: true }
    await state.loadSources()
    await state.generate()
    assert.equal(state.canUse.value, false)
    assert.deepEqual(state.calls, [])
    state.dispose()
  })
test('共餐菜位使用family_dish_index，个人子集下标不能定位共同菜', async () => {
  const plan = family()
  plan.members.b.meals[0].dishes[0].family_dish_index = 2
  const state = panel({ props: { plan } })
  assert.ok(state.slots.value.some((item) => item.value === 'breakfast:2'))
  assert.equal(
    state.slots.value.some((item) => item.value === 'breakfast:1'),
    false
  )
  state.dispose()
})
test('参与调整拟加入成员须显式选择并独立同意，选择变化清空旧来源', async () => {
  const state = panel()
  await prepare(state, 'participation')
  state.extraMembers.value = ['c']
  assert.deepEqual(state.selectedIds.value, ['a', 'b', 'c'])
  assert.deepEqual(state.profiles.value, {})
  assert.deepEqual(state.consents.value, {})
  await state.loadSources()
  state.consents.value = { a: true, b: true }
  assert.equal(state.canGenerate.value, false)
  state.consents.value.c = true
  assert.equal(state.canGenerate.value, true)
  state.dispose()
})
for (const operation of ['swap', 'regeneration', 'participation'])
  test(`${operation}只生成服务端家庭回执，明确确认才调用正确业务Owner`, async () => {
    const state = panel({ operation })
    await prepare(state, operation)
    await state.generate()
    if (operation === 'swap') state.candidateId.value = 'recipe-candidate'
    assert.equal(state.canConfirm.value, true)
    assert.equal(state.calls.filter(([kind]) => kind.startsWith('family')).length, 0)
    assert.match(
      state.calls.find(([kind]) => kind === 'run')[1].query,
      /主成员（ID:a）.*共餐成员（ID:b）/
    )
    await state.confirm()
    const method = {
      swap: 'familySafeSwapMealPlan',
      regeneration: 'familySafeRegenerateMealPlan',
      participation: 'familyParticipationMealPlan'
    }[operation]
    const saved = state.calls.find(([kind]) => kind === method)
    assert.deepEqual(saved[2].profile_versions, { a: 2, b: 4 })
    assert.equal(saved[2].version, 3)
    assert.equal(state.calls.filter(([kind]) => kind === 'run-read').length, 2)
    if (operation === 'participation') {
      assert.equal(saved[2].allocations[0].dishes[0].member_portions[0].grams, '55')
      assert.equal(saved[2].allocations[0].dishes[0].member_portions[1].grams, '60')
      assert.equal(saved[2].allocations.length, 3)
      assert.equal(Object.hasOwn(saved[2].allocations[0].dishes[0], 'recipe_version_id'), false)
      assert.ok(saved[2].reason)
    }
    assert.equal(state.preview.value, null)
    assert.equal(state.events.find(([kind]) => kind === 'saved')[1].applied_version, 4)
    state.dispose()
  })
test('参与退出者仍属于线程绑定，业务确认只提交实际剩余参与者的档案版本', async () => {
  const result = output('participation')
  delete result.result.plan_snapshot.members.b
  delete result.result.sources.profiles.b
  result.result.plan_spec.meals.forEach((meal) => {
    meal.participant_ids = ['a']
    meal.dishes[0].member_portions = meal.dishes[0].member_portions.filter(
      (person) => person.member_id === 'a'
    )
  })
  const state = panel({ operation: 'participation', output: result })
  await prepare(state, 'participation')
  await state.generate()
  await state.confirm()
  assert.deepEqual(
    state.calls.find(([kind]) => kind === 'familyParticipationMealPlan')[2].profile_versions,
    { a: 2 }
  )
  state.dispose()
})
for (const [label, mutate] of [
  [
    '入口成员',
    (value) => {
      value.member_id = 'b'
    }
  ],
  [
    'Agent角色',
    (value) => {
      value.agent_slug = 'health-consultation'
    }
  ],
  [
    '线程缺失',
    (value) => {
      value.thread_id = null
    }
  ],
  [
    '计划选择',
    (value) => {
      value.family_selection.plan_id = 'other-plan'
    }
  ],
  [
    '档案版本',
    (value) => {
      value.family_selection.profile_versions.b = 99
    }
  ],
  [
    '漏选成员',
    (value) => {
      delete value.family_selection.profile_versions.b
    }
  ]
])
  test(`错家庭绑定${label}不能提交模型请求`, async () => {
    const state = panel({
      api: {
        createFamilyMealPlanner: async () => {
          const binding = {
            member_id: 'a',
            thread_id: 'family-thread',
            agent_slug: 'health-meal-planner',
            family_selection: selection()
          }
          mutate(binding)
          return binding
        }
      }
    })
    await prepare(state)
    await state.generate()
    assert.equal(
      state.calls.some(([kind]) => kind === 'run'),
      false
    )
    assert.equal(state.preview.value, null)
    state.dispose()
  })
for (const field of ['request_id', 'thread_id'])
  test(`错Request ${field}不能读取或展示相邻Run`, async () => {
    const state = panel({
      agent: {
        getRequest: async (id) => ({
          request: {
            request_id: id,
            thread_id: 'family-thread',
            status: 'dispatched',
            dispatched_run_id: 'family-run',
            [field]: 'other-identity'
          }
        })
      }
    })
    await prepare(state)
    await state.generate()
    await state.confirm()
    assert.equal(
      state.calls.some(([kind]) => kind === 'run-read'),
      false
    )
    assert.equal(state.preview.value, null)
    assert.equal(
      state.calls.some(([kind]) => kind.startsWith('familySafe')),
      false
    )
    state.dispose()
  })
for (const field of ['agent_run_id', 'request_id', 'thread_id', 'agent_slug'])
  test(`错Run ${field}不能展示或确认家庭回执`, async () => {
    const state = panel({
      agent: {
        getAgentRunResult: async (id) => ({
          agent_run_id: id,
          request_id: state.attempt.value.request_id,
          thread_id: 'family-thread',
          agent_slug: 'health-meal-planner',
          status: 'completed',
          output: JSON.stringify(output()),
          [field]: 'other-identity'
        })
      }
    })
    await prepare(state)
    await state.generate()
    await state.confirm()
    assert.equal(state.preview.value, null)
    assert.equal(
      state.calls.some(([kind]) => kind.startsWith('familySafe')),
      false
    )
    state.dispose()
  })
for (const [field, wrong] of [
  ['plan_id', 'other-plan'],
  ['member_id', 'b'],
  ['applied_version', 5],
  ['version', 3],
  ['members', null]
])
  test(`错业务确认回执${field}不能宣称保存完成`, async () => {
    const state = panel({
      api: {
        familySafeSwapMealPlan: async () => ({
          ...family(305, 66),
          version: 4,
          applied_version: 4,
          [field]: wrong
        })
      }
    })
    await prepare(state)
    await state.generate()
    state.candidateId.value = 'recipe-candidate'
    await state.confirm()
    assert.equal(
      state.events.some(([kind]) => kind === 'saved'),
      false
    )
    assert.ok(state.confirmation.value)
    assert.match(state.error.value, /未确认/)
    state.dispose()
  })
for (const change of [
  (value) => {
    value.member_ids = ['a']
  },
  (value) => {
    value.member_id = 'b'
  },
  (value) => {
    value.scope = 'single_member_saved_plan'
  },
  (value) => {
    value.operation = 'regeneration'
  },
  (value) => {
    value.result.sources.profiles.b.version = 5
  },
  (value) => {
    delete value.result.sources.profiles.b
  },
  (value) => {
    value.result.sources.plan.id = 'other-plan'
  },
  (value) => {
    value.result.sources.rules.version = 8
  },
  (value) => {
    value.result.dish_index = 1
  },
  (value) => {
    value.result.meal_type = 'dinner'
  }
])
  test(`不接受错成员、范围、来源或菜位的回执 ${change.toString()}`, async () => {
    const value = output()
    change(value)
    const state = panel({ output: value })
    await prepare(state)
    await state.generate()
    assert.equal(state.preview.value, null)
    assert.equal(state.canConfirm.value, false)
    assert.equal(
      state.calls.some(([kind]) => kind.startsWith('familySafe')),
      false
    )
    state.dispose()
  })
for (const status of [403, 404, 409, 410])
  test(`首次确认Run重读${status}拒绝业务写入并清空私有预览`, async () => {
    // 验证实际重读Owner错误，而非单纯UI禁用。
    let readCount = 0
    const fresh = panel({
      agent: {
        getAgentRunResult: async (id) => {
          if (++readCount > 1) throw failure(status)
          return {
            agent_run_id: id,
            request_id: fresh.attempt.value.request_id,
            thread_id: 'family-thread',
            agent_slug: 'health-meal-planner',
            status: 'completed',
            output: JSON.stringify(output())
          }
        }
      }
    })
    await prepare(fresh)
    await fresh.generate()
    fresh.candidateId.value = 'recipe-candidate'
    await fresh.confirm()
    assert.equal(
      fresh.calls.some(([kind]) => kind.startsWith('familySafe')),
      false
    )
    assert.equal(fresh.preview.value, null)
    assert.equal(fresh.events.find(([kind]) => kind === 'invalidated')[2], status)
    fresh.dispose()
  })
for (const invalid of [
  { output: null, error: { type: 'run_not_found' } },
  { output: '' },
  { output: '{invalid-json' },
  { output: 'null' }
]) {
  for (const boundary of ['poll', 'confirm'])
    test(`${boundary}不接受HTTP200错误或无效JSON回执 ${JSON.stringify(invalid)}`, async () => {
      let reads = 0
      const state = panel({
        agent: {
          getAgentRunResult: async (id) => ({
            agent_run_id: id,
            request_id: state.attempt.value?.request_id || state.preview.value.authority.request_id,
            thread_id: 'family-thread',
            agent_slug: 'health-meal-planner',
            status: 'completed',
            ...(boundary === 'poll' || ++reads > 1 ? invalid : { output: JSON.stringify(output()) })
          })
        }
      })
      await prepare(state)
      await state.generate()
      if (boundary === 'confirm') {
        state.candidateId.value = 'recipe-candidate'
        await state.confirm()
      }
      assert.equal(state.preview.value, null)
      assert.equal(state.confirmation.value, null)
      assert.equal(
        state.calls.some(([kind]) => kind.startsWith('familySafe')),
        false
      )
      assert.equal(state.events.find(([kind]) => kind === 'invalidated')[2], 410)
      state.dispose()
    })
}
test('参与调整回执缺完整三餐分配或扩大到未选成员时禁止确认', async () => {
  for (const mutate of [
    (value) => {
      delete value.result.plan_spec
    },
    (value) => {
      value.result.plan_spec.meals[0].dishes[0].member_portions[0].member_id = 'c'
    },
    (value) => {
      value.result.plan_spec.meals.pop()
    }
  ]) {
    const value = output('participation')
    mutate(value)
    const state = panel({ operation: 'participation', output: value })
    await prepare(state, 'participation')
    await state.generate()
    await state.confirm()
    assert.equal(state.preview.value, null)
    assert.equal(
      state.calls.some(([kind]) => kind === 'familyParticipationMealPlan'),
      false
    )
    state.dispose()
  }
})
test('首次确认重读完整回执差异即拒绝，不能只比较preview_id', async () => {
  let reads = 0
  const state = panel({
    agent: {
      getAgentRunResult: async (id) => {
        const value = output()
        if (++reads > 1)
          value.result.candidates[0].member_nutrition_differences.b.energy_kcal = '999'
        return {
          agent_run_id: id,
          request_id: state.attempt.value?.request_id || state.preview.value.authority.request_id,
          thread_id: 'family-thread',
          agent_slug: 'health-meal-planner',
          status: 'completed',
          output: JSON.stringify(value)
        }
      }
    }
  })
  await prepare(state)
  await state.generate()
  state.candidateId.value = 'recipe-candidate'
  await state.confirm()
  assert.equal(
    state.calls.some(([kind]) => kind.startsWith('familySafe')),
    false
  )
  assert.equal(state.preview.value, null)
  state.dispose()
})
test('未知业务写入后保持原包原键恢复，旧Run失效不影响业务幂等恢复', async () => {
  const packets = []
  let posts = 0,
    reads = 0
  const state = panel({
    api: {
      familySafeSwapMealPlan: async (id, data) => {
        packets.push(clone(data))
        if (++posts === 1) throw failure(500)
        return { ...family(305, 66), version: 4, applied_version: 4 }
      }
    },
    agent: {
      getAgentRunResult: async (id) => {
        state.calls.push(['run-read', id])
        if (++reads > 2) throw failure(410)
        return {
          agent_run_id: id,
          request_id: state.attempt.value?.request_id || state.preview.value.authority.request_id,
          thread_id: 'family-thread',
          agent_slug: 'health-meal-planner',
          status: 'completed',
          output: JSON.stringify(output())
        }
      }
    }
  })
  await prepare(state)
  await state.generate()
  state.candidateId.value = 'recipe-candidate'
  await state.confirm()
  const pending = clone(state.confirmation.value)
  assert.equal(state.busy.value, true)
  await state.confirm()
  assert.deepEqual(packets, [pending.data, pending.data])
  assert.equal(state.calls.filter(([kind]) => kind === 'run-read').length, 2)
  assert.equal(state.events.filter(([kind]) => kind === 'saved').length, 1)
  state.dispose()
})
for (const operation of ['swap', 'regeneration', 'participation'])
  test(`${operation}业务POST503丢已提交响应，原包原键恢复且收据只形成一次修订`, async () => {
    const packets = [],
      receipts = new Map()
    let writes = 0,
      reads = 0,
      posts = 0
    const method = {
      swap: 'familySafeSwapMealPlan',
      regeneration: 'familySafeRegenerateMealPlan',
      participation: 'familyParticipationMealPlan'
    }[operation]
    const state = panel({
      operation,
      api: {
        [method]: async (id, data) => {
          packets.push(clone(data))
          const key = `${id}:${data.client_request_id}`
          if (!receipts.has(key)) {
            writes++
            receipts.set(key, {
              body: clone(data),
              result: { ...family(305, 66), version: 4, applied_version: 4 }
            })
          }
          const receipt = receipts.get(key)
          assert.deepEqual(data, receipt.body)
          // 独立业务oracle先形成修订收据，再模拟网关丢失响应；不是503前假设未写入。
          if (++posts === 1) throw failure(503)
          return receipt.result
        }
      },
      agent: {
        getAgentRunResult: async (id) => {
          if (++reads > 2) throw failure(410)
          return {
            agent_run_id: id,
            request_id: state.attempt.value?.request_id || state.preview.value.authority.request_id,
            thread_id: 'family-thread',
            agent_slug: 'health-meal-planner',
            status: 'completed',
            output: JSON.stringify(output(operation))
          }
        }
      }
    })
    await prepare(state, operation)
    await state.generate()
    if (operation === 'swap') state.candidateId.value = 'recipe-candidate'
    await state.confirm()
    assert.equal(writes, 1)
    assert.ok(state.confirmation.value, '503无法证明未提交，必须保留已冻结确认包')
    const pending = clone(state.confirmation.value)
    assert.equal(state.busy.value, true)
    assert.equal(
      state.events.some(([kind]) => kind === 'saved'),
      false
    )
    await state.confirm()
    assert.deepEqual(packets, [pending.data, pending.data])
    assert.equal(writes, 1)
    assert.equal(receipts.size, 1)
    assert.equal(reads, 2)
    assert.equal(state.events.filter(([kind]) => kind === 'saved').length, 1)
    state.dispose()
  })
test('首次Run重读503仍视为依赖未就绪，清除旧预览且不提交业务确认', async () => {
  let reads = 0
  const state = panel({
    agent: {
      getAgentRunResult: async (id) => {
        if (++reads > 1) throw failure(503)
        return {
          agent_run_id: id,
          request_id: state.attempt.value.request_id,
          thread_id: 'family-thread',
          agent_slug: 'health-meal-planner',
          status: 'completed',
          output: JSON.stringify(output())
        }
      }
    }
  })
  await prepare(state)
  await state.generate()
  state.candidateId.value = 'recipe-candidate'
  await state.confirm()
  assert.equal(state.preview.value, null)
  assert.equal(state.confirmation.value, null)
  assert.deepEqual(state.profiles.value, {})
  assert.equal(
    state.calls.some(([kind]) => kind.startsWith('familySafe')),
    false
  )
  assert.match(state.error.value, /未就绪/)
  state.dispose()
})

const invalidators = [
  [
    '入口成员',
    (state) => {
      state.props.memberId = 'b'
    }
  ],
  [
    '计划版本',
    (state) => {
      state.props.plan.version++
    }
  ],
  [
    '计划ID',
    (state) => {
      state.props.plan.plan_id = 'other-plan'
    }
  ],
  [
    '其他成员授权',
    (state) => {
      state.props.members[1].scopes = ['diet_edit']
    }
  ],
  [
    '其他成员移除',
    (state) => {
      state.props.members = state.props.members.filter((row) => row.id !== 'b')
    }
  ],
  [
    '政策',
    (state) => {
      state.props.configuration.policy_version = 'policy-b'
    }
  ],
  [
    '处理方',
    (state) => {
      state.props.configuration.meal_plan.processor = 'other-provider'
    }
  ],
  [
    '模型关闭',
    (state) => {
      state.props.configuration.meal_plan.available = false
    }
  ],
  [
    '同处理方模型变化',
    (state) => {
      state.props.configuration.meal_plan.model = 'provider:other-fixed-model'
    }
  ]
]
for (const [label, invalidate] of invalidators)
  test(`${label}变化隔离迟到全体专业档案响应`, async () => {
    const delayed = deferred()
    const state = panel({
      api: {
        professionalProfile: (id) =>
          id === 'b' ? delayed.promise : Promise.resolve({ status: 'ready', version: 2 })
      }
    })
    state.ruleCode.value = 'approved-family'
    const reading = state.loadSources()
    invalidate(state)
    delayed.resolve({ status: 'ready', version: 4 })
    await reading
    assert.deepEqual(state.profiles.value, {})
    assert.equal(state.preview.value, null)
    assert.equal(state.canGenerate.value, false)
    state.dispose()
  })
for (const boundary of [
  'consent',
  'binding',
  'run',
  'request',
  'result',
  'confirm-result',
  'business-result'
])
  test(`第二成员撤权隔离迟到${boundary}且不向后推进`, async () => {
    const delayed = deferred()
    let entered = false
    const block = (value) => {
      entered = true
      return delayed.promise.then(() => value)
    }
    let requestId
    const overrides = { api: {}, agent: {} }
    if (boundary === 'consent') overrides.api.consent = () => block(undefined)
    if (boundary === 'binding')
      overrides.api.createFamilyMealPlanner = () =>
        block({
          member_id: 'a',
          thread_id: 'family-thread',
          agent_slug: 'health-meal-planner',
          family_selection: selection()
        })
    if (boundary === 'run')
      overrides.agent.createAgentRun = (data) => {
        requestId = data.meta.request_id
        return block(undefined)
      }
    if (boundary === 'request')
      overrides.agent.getRequest = (id) => {
        requestId = id
        return block({
          request: {
            request_id: id,
            thread_id: 'family-thread',
            status: 'dispatched',
            dispatched_run_id: 'family-run'
          }
        })
      }
    if (boundary === 'result')
      overrides.agent.getAgentRunResult = (id) => {
        requestId = state.attempt.value.request_id
        return block({
          agent_run_id: id,
          request_id: requestId,
          thread_id: 'family-thread',
          agent_slug: 'health-meal-planner',
          status: 'completed',
          output: JSON.stringify(output())
        })
      }
    if (boundary === 'confirm-result') {
      let reads = 0
      overrides.agent.getAgentRunResult = (id) => {
        requestId = state.attempt.value?.request_id || state.preview.value.authority.request_id
        const value = {
          agent_run_id: id,
          request_id: requestId,
          thread_id: 'family-thread',
          agent_slug: 'health-meal-planner',
          status: 'completed',
          output: JSON.stringify(output())
        }
        return ++reads === 1 ? Promise.resolve(value) : block(value)
      }
    }
    if (boundary === 'business-result')
      overrides.api.familySafeSwapMealPlan = () =>
        block({ ...family(), version: 4, applied_version: 4 })
    const state = panel(overrides)
    await prepare(state)
    let running
    if (['confirm-result', 'business-result'].includes(boundary)) {
      await state.generate()
      state.candidateId.value = 'recipe-candidate'
      running = state.confirm()
    } else running = state.generate()
    while (!entered) await Vue.nextTick()
    state.props.members[1].scopes = []
    delayed.resolve()
    await running
    assert.equal(state.preview.value, null)
    assert.equal(state.confirmation.value, null)
    assert.equal(state.attempt.value, null)
    assert.equal(
      state.events.some(([kind]) => kind === 'saved'),
      false
    )
    if (boundary === 'confirm-result')
      assert.equal(
        state.calls.some(([kind]) => kind.startsWith('familySafe')),
        false
      )
    state.dispose()
  })
for (const code of [500, 502, 503, 504]) {
  test(`家庭绑定POST${code}按原包原键恢复同一线程`, async () => {
    const packets = [],
      receipts = new Map()
    const state = panel({
      api: {
        createFamilyMealPlanner: async (member, body) => {
          packets.push([member, clone(body)])
          if (!receipts.has(body.client_request_id)) {
            const { client_request_id, ...family_selection } = body
            receipts.set(client_request_id, {
              member_id: member,
              thread_id: 'family-thread',
              agent_slug: 'health-meal-planner',
              family_selection
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

  test(`家庭Request POST/GET、Run GET和取消${code}保留原请求直到恢复`, async () => {
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
              thread_id: 'family-thread',
              status: 'dispatched',
              dispatched_run_id: 'family-run'
            }
          }
        },
        getAgentRunResult: async () => {
          if (++runReads === 1) throw failure(code)
          return {
            agent_run_id: 'family-run',
            request_id: packets[0].meta.request_id,
            thread_id: 'family-thread',
            agent_slug: 'health-meal-planner',
            status: 'completed',
            output: JSON.stringify(output())
          }
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
    assert.equal(state.allConsented.value, true)
    assert.equal(requests.size, 1)
    await state.poll()
    assert.equal(state.attempt.value, null)
    assert.ok(state.preview.value)
    state.dispose()
  })
}

test('家庭健康绑定POST404清除全体专业来源及同意，不保留生成请求', async () => {
  const state = panel({
    api: {
      createFamilyMealPlanner: async () => {
        throw failure(404)
      }
    }
  })
  await prepare(state)
  await state.generate()
  assert.equal(state.attempt.value, null)
  assert.equal(state.preview.value, null)
  assert.deepEqual(clone(state.profiles.value), {})
  assert.equal(state.rules.value, null)
  assert.deepEqual(clone(state.consents.value), {})
  assert.equal(
    state.calls.some(([kind]) => kind === 'run'),
    false
  )
  assert.ok(state.events.some(([event, , code]) => event === 'invalidated' && code === 404))
  state.dispose()
})

test('生成结果未确认后使用相同绑定和request重试，不产生另一轮模型请求', async () => {
  const submissions = []
  let count = 0
  const state = panel({
    agent: {
      createAgentRun: async (data) => {
        submissions.push(clone(data))
        if (++count === 1) throw failure(500)
      },
      getRequest: async () => {
        throw failure(500)
      }
    }
  })
  await prepare(state)
  await state.generate()
  const first = clone(state.attempt.value)
  await state.generate()
  assert.deepEqual(submissions, [submissions[0], submissions[0]])
  assert.equal(state.attempt.value.binding_id, first.binding_id)
  assert.equal(state.calls.filter(([kind]) => kind === 'binding').length, 1)
  state.dispose()
})
test('第二成员取消本轮同意后丢弃迟到Run，不发布预览或保存', async () => {
  const delayed = deferred()
  let entered = false
  const state = panel({
    agent: {
      getAgentRunResult: async (id) => {
        entered = true
        const request_id = state.attempt.value.request_id
        await delayed.promise
        return {
          agent_run_id: id,
          request_id,
          thread_id: 'family-thread',
          agent_slug: 'health-meal-planner',
          status: 'completed',
          output: JSON.stringify(output())
        }
      }
    }
  })
  await prepare(state)
  const generating = state.generate()
  while (!entered) await Vue.nextTick()
  state.consents.value.b = false
  delayed.resolve()
  await generating
  assert.equal(state.preview.value, null)
  assert.equal(state.attempt.value, null)
  assert.equal(
    state.calls.some(([kind]) => kind.startsWith('familySafe')),
    false
  )
  state.dispose()
})
test('无候选及专业规则未就绪保持未保存，明确展示原因', async () => {
  for (const status of ['ready', 'not_ready']) {
    const value = output()
    value.result.status = status
    value.result.candidates = []
    value.result.reason = status === 'ready' ? 'no_eligible_candidates' : 'swap_rules_not_approved'
    const state = panel({ output: value })
    await prepare(state)
    await state.generate()
    await state.confirm()
    assert.equal(state.preview.value.result.reason, value.result.reason)
    assert.equal(state.canConfirm.value, false)
    assert.equal(
      state.calls.some(([kind]) => kind.startsWith('familySafe')),
      false
    )
    state.dispose()
  }
})
test('已派发取消走相同Request与Run，取消未知保持原生成请求可恢复', async () => {
  const state = panel({
    agent: {
      getRequest: async (id) => ({
        request: {
          request_id: id,
          thread_id: 'family-thread',
          status: 'dispatched',
          dispatched_run_id: 'family-run'
        }
      }),
      getAgentRunResult: async () => {
        throw failure(500)
      },
      cancelRequest: async () => {
        throw failure(409)
      },
      cancelAgentRun: async () => {
        throw failure(500)
      }
    }
  })
  await prepare(state)
  await state.generate()
  const id = state.attempt.value.request_id
  await state.cancel()
  assert.equal(state.attempt.value.request_id, id)
  assert.equal(state.preview.value, null)
  assert.match(state.error.value, /未确认/)
  state.dispose()
})

function compileRender(template, filename) {
  const result = compileTemplate({
    source: template,
    filename,
    id: 'family-planner-test',
    compilerOptions: { mode: 'function' }
  })
  assert.deepEqual(result.errors, [])
  return new Function('Vue', result.code)(Vue)
}
test('实际家庭模板展示每人菜名、克数、覆盖、独立同意与明确保存，不把家庭总量标为个人全天', async () => {
  const state = panel()
  await prepare(state)
  await state.generate()
  state.candidateId.value = 'recipe-candidate'
  const snapshotSource = await readFile(
    new URL('../src/components/health/HealthFamilyMealPlanSnapshot.vue', import.meta.url),
    'utf8'
  )
  const snapshotScript = snapshotSource
    .match(/<script setup>([\s\S]*?)<\/script>/)[1]
    .replace(/^import[\s\S]*?from ['"][^'"]+['"]\s*\n/gm, '')
  const app = Vue.createSSRApp({
    render: compileRender(parse(source).descriptor.template.content, 'HealthFamilyMealPlanner.vue'),
    setup: () => ({
      ...state.props,
      ...Object.fromEntries(
        Object.entries(state).map(([key, value]) => [key, Vue.isRef(value) ? value.value : value])
      ),
      mealLabels,
      nutrientLabels,
      nutrientText
    })
  })
  app.component('HealthFamilyMealPlanSnapshot', {
    props: { snapshot: Object, members: Array, ruleChecked: Boolean },
    render: compileRender(
      parse(snapshotSource).descriptor.template.content,
      'HealthFamilyMealPlanSnapshot.vue'
    ),
    setup: (props) => ({
      ...new Function('defineProps', `${snapshotScript}\nreturn { memberName,gramsText }`)(
        () => props
      ),
      mealLabels,
      nutrientLabels,
      nutrientText
    })
  })
  for (const tag of ['AInput', 'AButton', 'ASelect', 'ATextarea', 'ACheckbox', 'ATag'])
    app.component(tag, { setup: (_, context) => () => Vue.h('div', context.slots.default?.()) })
  app.component('AAlert', { props: ['message'], setup: (props) => () => Vue.h('p', props.message) })
  const html = await renderToString(app)
  assert.match(html, /同意为 主成员/)
  assert.match(html, /同意为 共餐成员/)
  assert.match(html, /家庭计划合计（多人）/)
  assert.match(html, /所列餐次计划合计/)
  assert.match(html, /未覆盖三餐，不能作为个人全天结论/)
  assert.match(html, /清蒸鸡肉饭/)
  assert.match(html, /个人计划份量：60 g/)
  assert.match(html, /300 kcal → 305 kcal/)
  assert.match(html, /60 kcal → 66 kcal/)
  assert.match(html, /尚未保存/)
  assert.match(html, /确认保存家庭新版本/)
  assert.match(html, /原批准与采用状态将失效/)
  state.dispose()
})
