import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { setImmediate } from 'node:timers'
import { computed, effectScope, nextTick, reactive, ref, watch } from 'vue'

const source = await readFile(
  new URL('../src/components/health/HealthMealPlans.vue', import.meta.url),
  'utf8'
)
const script = source
  .match(/<script setup>([\s\S]*?)<\/script>/)[1]
  .replace(/^import[\s\S]*?from ['"][^'"]+['"]\s*\n/gm, '')
const snapshot = (extra = {}) => ({
  member_id: 'a',
  status: 'draft',
  preview_id: 'preview-a',
  plan_date: '2026-10-06',
  meals: [],
  ...extra
})

function panel(api = {}, agentApi = {}) {
  const props = reactive({
    memberId: 'a',
    scopes: ['diet_edit', 'report_view', 'ai_use'],
    configuration: {
      policy_version: 'policy-a',
      meal_plan: { available: true, processor: 'approved' }
    }
  })
  const scope = effectScope()
  let cleanup
  const factory = new Function(
    'ref',
    'computed',
    'watch',
    'onMounted',
    'onBeforeUnmount',
    'defineProps',
    'useRouter',
    'api',
    'agentApi',
    `${script}\nreturn { reload, loadRecipes, selectPlan, makePreview, save, openSwap, submitSwap, closeSwap, generate, checkGeneration, stopGeneration, preview, current, historyVersion, saveAttempt, swapAttempt, swap, plans, error, working, polling, generation, generationStatus, consent, date, notes, meals, questions, recipes, recipesError, displayed, canPreview, canGenerate }`
  )
  const state = scope.run(() =>
    factory(
      ref,
      computed,
      watch,
      () => {},
      (fn) => {
        cleanup = fn
      },
      () => props,
      () => ({ push: () => {} }),
      api,
      agentApi
    )
  )
  return {
    props,
    ...state,
    dispose: () => {
      cleanup()
      scope.stop()
    }
  }
}
const empty = { mealPlans: async () => ({ plans: [], truncated: false }) }

test('切换成员和授权立即清空旧数据，迟到列表与预览均丢弃', async () => {
  let finishList, finishPreview
  const state = panel({
    mealPlans: () =>
      new Promise((r) => {
        finishList = r
      }),
    previewMealPlan: () =>
      new Promise((r) => {
        finishPreview = r
      })
  })
  state.meals.value.forEach((meal) => {
    meal.dishes[0].recipe_version_id = 'recipe'
  })
  await nextTick()
  const list = state.reload(),
    preview = state.makePreview()
  state.props.scopes = []
  await nextTick()
  finishList({ plans: [snapshot()], truncated: false })
  finishPreview(snapshot())
  await Promise.all([list, preview])
  assert.deepEqual(state.plans.value, [])
  assert.equal(state.preview.value, null)
  assert.equal(state.canPreview.value, false)
  state.dispose()
})

test('手动预览由服务器计算；改日期或计划量后旧预览失效', async () => {
  let sent
  const state = panel({
    ...empty,
    previewMealPlan: async (member, data) => {
      sent = data
      return snapshot({ nutrition: { totals: { energy_kcal: null } } })
    }
  })
  state.meals.value.forEach((meal) => {
    meal.dishes[0].recipe_version_id = 'recipe'
    meal.dishes[0].grams = null
  })
  await nextTick()
  await state.makePreview()
  assert.equal(sent.meals.length, 3)
  assert.equal('nutrition' in sent, false)
  assert.equal(state.displayed.value.nutrition.totals.energy_kcal, null)
  state.meals.value[0].dishes[0].grams = 150
  await nextTick()
  assert.equal(state.preview.value, null)
  state.dispose()
})

test('保存响应丢失重试原回执与幂等键，回读当前版本及历史', async () => {
  const requests = []
  const state = panel({
    ...empty,
    saveMealPlan: async (member, data) => {
      requests.push(JSON.parse(JSON.stringify(data)))
      if (requests.length === 1) throw Error('response lost')
      return snapshot({ plan_id: 'saved', version: 1 })
    },
    mealPlan: async () =>
      snapshot({ plan_id: 'saved', version: 2, revisions: [{ version: 1 }, { version: 2 }] })
  })
  state.preview.value = snapshot()
  await state.save()
  assert.ok(state.saveAttempt.value)
  await state.save()
  assert.deepEqual(requests[0], requests[1])
  assert.equal(state.current.value.version, 2)
  assert.equal(state.current.value.revisions.length, 2)
  assert.equal(state.preview.value, null)
  state.dispose()
})

test('换菜网络重试冻结菜谱、理由和版本；409移除旧详情直到重新读取', async () => {
  const requests = []
  const state = panel({
    ...empty,
    recipes: async () => [],
    swapMealPlan: async (id, data) => {
      requests.push(JSON.parse(JSON.stringify(data)))
      if (requests.length === 1) throw Error('response lost')
      throw Object.assign(Error('conflict'), { status: 409 })
    }
  })
  state.current.value = snapshot({ plan_id: 'saved', version: 4 })
  state.openSwap('lunch', { dish_index: 0, name: '旧菜' })
  state.swap.value.replacement.recipe_version_id = 'new-recipe'
  state.swap.value.reason = '换口味'
  await state.submitSwap()
  state.swap.value.reason = '不应覆盖原请求'
  await state.submitSwap()
  assert.deepEqual(requests[0], requests[1])
  assert.equal(requests[0].version, 4)
  assert.equal(state.current.value, null)
  assert.match(state.error.value, /版本/)
  state.dispose()
})

test('历史选择显示旧快照；乱序详情不能覆盖当前选择', async () => {
  let finish
  const state = panel({
    mealPlan: () =>
      new Promise((r) => {
        finish = r
      }),
    ...empty
  })
  const read = state.selectPlan('saved')
  state.props.memberId = 'b'
  await nextTick()
  finish(snapshot({ plan_id: 'saved', version: 3 }))
  await read
  assert.equal(state.current.value, null)
  state.current.value = snapshot({ version: 2 })
  state.historyVersion.value = { version: 1, snapshot: snapshot({ plan_date: '2026-10-01' }) }
  assert.equal(state.displayed.value.plan_date, '2026-10-01')
  state.dispose()
})

test('生成绑定响应迟到不能向旧成员提交 Run', async () => {
  let finish,
    count = 0
  const state = panel(
    {
      ...empty,
      consent: async () => {},
      createMealPlanner: () =>
        new Promise((r) => {
          finish = r
        })
    },
    {
      createAgentRun: async () => {
        count++
      }
    }
  )
  state.consent.value = true
  const run = state.generate()
  await new Promise((r) => setImmediate(r))
  state.props.memberId = 'b'
  await nextTick()
  finish({ member_id: 'a', agent_slug: 'health-meal-planner', thread_id: 'old' })
  await run
  assert.equal(count, 0)
  assert.equal(state.generation.value, null)
  state.dispose()
})

test('生成提交响应未知可重试原正文，完成结果只认同 Run 回执', async () => {
  const submitted = [],
    consents = []
  const state = panel(
    {
      ...empty,
      consent: async (id, data) => {
        consents.push(data)
      },
      createMealPlanner: async () => ({
        member_id: 'a',
        agent_slug: 'health-meal-planner',
        thread_id: 'bound'
      })
    },
    {
      createAgentRun: async (data) => {
        submitted.push(JSON.parse(JSON.stringify(data)))
        if (submitted.length === 1) throw Error('lost')
      },
      getRequest: async (id) => ({
        request: { request_id: id, thread_id: 'bound', dispatched_run_id: 'run-a' }
      }),
      getAgentRunResult: async () => ({
        status: 'completed',
        agent_slug: 'health-meal-planner',
        thread_id: 'bound',
        agent_run_id: 'run-a',
        request_id: submitted[0].meta.request_id,
        output: JSON.stringify(snapshot())
      })
    }
  )
  state.consent.value = true
  state.notes.value = '清淡'
  await state.generate()
  state.notes.value = '不应改写原请求'
  await state.generate()
  assert.deepEqual(submitted[0], submitted[1])
  assert.equal(consents[0].purpose, 'meal_plan')
  assert.equal(state.preview.value.preview_id, 'preview-a')
  assert.equal(state.generation.value, null)
  assert.equal(state.saveAttempt.value, null)
  state.dispose()
})

test('未完成、跨 Run 和其他成员结果不能发布为页面餐单', async () => {
  for (const mode of ['pending', 'foreign-run', 'foreign-member']) {
    const state = panel(empty, {
      getRequest: async () => ({
        request: { request_id: 'request', thread_id: 'bound', dispatched_run_id: 'run-a' }
      }),
      getAgentRunResult: async () => ({
        status: mode === 'pending' ? 'running' : 'completed',
        agent_slug: 'health-meal-planner',
        thread_id: 'bound',
        agent_run_id: mode === 'foreign-run' ? 'other' : 'run-a',
        request_id: 'request',
        output: JSON.stringify(snapshot({ member_id: mode === 'foreign-member' ? 'b' : 'a' }))
      })
    })
    state.generation.value = { request_id: 'request', thread_id: 'bound' }
    await state.checkGeneration()
    assert.equal(state.preview.value, null)
    state.dispose()
  }
})

test('配餐师补充问题显示原文，未启用服务禁止调用模型', async () => {
  const state = panel(empty, {
    getRequest: async () => ({
      request: { request_id: 'request', thread_id: 'bound', dispatched_run_id: 'run-a' }
    }),
    getAgentRunResult: async () => ({
      status: 'completed',
      agent_slug: 'health-meal-planner',
      thread_id: 'bound',
      agent_run_id: 'run-a',
      request_id: 'request',
      output: JSON.stringify({ status: 'needs_input', questions: ['请补充用餐意图'] })
    })
  })
  state.generation.value = { request_id: 'request', thread_id: 'bound' }
  await state.checkGeneration()
  assert.deepEqual(state.questions.value, ['请补充用餐意图'])
  assert.equal(state.preview.value, null)
  state.props.configuration.meal_plan.available = false
  assert.equal(state.canGenerate.value, false)
  state.dispose()
})

test('取消响应未知仍保留恢复入口，成功后才能重新生成', async () => {
  let calls = 0
  const state = panel(empty, {
    cancelRequest: async () => {
      if (++calls === 1) throw Error('lost')
      return { status: 'cancel_requested' }
    }
  })
  state.generation.value = { request_id: 'request', thread_id: 'bound' }
  await state.stopGeneration()
  assert.ok(state.generation.value)
  await state.stopGeneration()
  assert.equal(state.generation.value, null)
  state.dispose()
})

test('已经派发的请求取消对应 Run；未知提交尚不存在时不能假定已取消', async () => {
  const cancelled = []
  const state = panel(empty, {
    cancelRequest: async () => {
      throw Object.assign(Error('dispatched'), { status: 409 })
    },
    getRequest: async () => ({ request: { thread_id: 'bound', dispatched_run_id: 'run-a' } }),
    cancelAgentRun: async (id) => {
      cancelled.push(id)
    }
  })
  state.generation.value = { request_id: 'request', thread_id: 'bound' }
  await state.stopGeneration()
  assert.deepEqual(cancelled, ['run-a'])
  assert.equal(state.generation.value, null)
  state.dispose()
  const unknown = panel(empty, {
    cancelRequest: async () => {
      throw Object.assign(Error('not committed'), { status: 404 })
    }
  })
  unknown.generation.value = { request_id: 'request', thread_id: 'bound' }
  await unknown.stopGeneration()
  assert.ok(unknown.generation.value)
  unknown.dispose()
})

test('刷新发现权限撤回，清除此前餐单和历史快照', async () => {
  const state = panel({
    mealPlans: async () => {
      throw Object.assign(Error('revoked'), { status: 403 })
    }
  })
  state.current.value = snapshot({ plan_id: 'saved', version: 1 })
  state.historyVersion.value = { snapshot: snapshot() }
  await state.reload()
  assert.equal(state.current.value, null)
  assert.equal(state.displayed.value, null)
  assert.match(state.error.value, /授权/)
  state.dispose()
})

test('健康 API 在真实方法边界携带餐单幂等与版本头', async () => {
  const text = await readFile(new URL('../src/apis/health_vision_api.js', import.meta.url), 'utf8')
  const calls = []
  const fn =
    (method) =>
    (...args) => {
      calls.push({ method, args })
    }
  const factory = new Function(
    'apiGet',
    'apiPost',
    'apiPut',
    'apiDelete',
    'apiRequest',
    'buildQuery',
    `${text.replace(/^import.*\r?\n/, '').replace('export const', 'const')}\nreturn healthVisionApi`
  )
  const api = factory(fn('GET'), fn('POST'), fn('PUT'), fn('DELETE'), fn('REQUEST'), () => '')
  api.saveMealPlan('member', { preview_id: 'preview', client_request_id: 'key' })
  api.swapMealPlan('plan', { version: 3, client_request_id: 'swap' })
  assert.equal(calls[0].args[0], '/api/health/v1/members/member/meal-plans')
  assert.equal(calls[0].args[2].headers['Idempotency-Key'], 'key')
  assert.equal(calls[1].args[2].headers['If-Match'], '"3"')
  assert.equal(calls[1].args[2].headers['Idempotency-Key'], 'swap')
})
