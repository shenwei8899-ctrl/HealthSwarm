import test from 'node:test'
import assert from 'node:assert/strict'
import { createNutritionClient } from '../src/services/nutrition-client.js'

const SESSION_KEY = 'healthswarm.nutrition.session'
const ACCOUNT_A = { access_token: 'synthetic-token-a', uid: 'synthetic-account-a', username: '合成甲' }
const ACCOUNT_B = { access_token: 'synthetic-token-b', uid: 'synthetic-account-b', username: '合成乙' }
const MEMBER = '371e8f65-d57a-4ff8-8516-d58c17959673'
const PLAN = '8fa35c32-d13b-4db9-8a23-28c9a4e6e637'
const PREVIEW = 'fb7bcb28-fafb-42fd-a73d-e88e71aec4ae'
const RECIPE = 'c9c7b917-fd23-4381-8fd8-e14c09ff4d08'
const PORTION = 'c033dd60-6d44-44e0-b6b6-fcc4a48a06e8'
const REQUEST_KEY = 'a1e1240e-f5cb-43c3-98fa-688c8175dd6d'

/** 网络结果由测试单独交付，直接观察发出的uni.request协议。 */
function harness() {
  const calls = [], values = new Map()
  const client = createNutritionClient({
    request(options) { calls.push(options) },
    storage: {
      getStorageSync: key => structuredClone(values.get(key)),
      setStorageSync: (key, value) => values.set(key, structuredClone(value)),
      removeStorageSync: key => values.delete(key),
    },
  })
  return { client, calls, values }
}

async function signIn(state, account = ACCOUNT_A) {
  const pending = state.client.login(account.uid, 'synthetic-password')
  state.calls.at(-1).success({ statusCode: 200, data: account })
  await pending
}

function threeMeals() {
  return {
    plan_date: '2026-10-10',
    meals: [
      { meal_type: 'breakfast', dishes: [{ recipe_version_id: RECIPE, grams: '125.50' }] },
      { meal_type: 'lunch', dishes: [{ recipe_version_id: RECIPE, grams: null, portion_reference_id: PORTION, portion_count: '1.25' }] },
      { meal_type: 'dinner', dishes: [{ recipe_version_id: RECIPE, grams: 200, portion_reference_id: null, portion_count: null }] },
    ],
  }
}

function swapIntent() {
  return {
    version: 2,
    meal_type: 'lunch',
    dish_index: 0,
    replacement: { recipe_version_id: RECIPE, portion_reference_id: PORTION, portion_count: '1.5' },
    reason: '用户确认更换午餐菜品',
    client_request_id: REQUEST_KEY,
  }
}

test('餐单读取仅调用真实业务GET，查询与路径精确编码并复用当前认证', async () => {
  const state = harness()
  await signIn(state)
  const cases = [
    [() => state.client.listMealPlans(MEMBER), `/api/health/v1/members/${MEMBER}/meal-plans`],
    [() => state.client.readMealPlan(PLAN), `/api/health/v1/meal-plans/${PLAN}`],
    [() => state.client.listPublishedRecipes(), '/api/health/v1/recipes?q='],
    [() => state.client.listPublishedRecipes('番茄 & 米饭/+'), '/api/health/v1/recipes?q=%E7%95%AA%E8%8C%84%20%26%20%E7%B1%B3%E9%A5%AD%2F%2B'],
    [() => state.client.listRecipePortions(RECIPE), `/api/health/v1/portion-references?recipe_version_id=${RECIPE}`],
    [() => state.client.listRecipePortions('recipe/?food_id=foreign'), '/api/health/v1/portion-references?recipe_version_id=recipe%2F%3Ffood_id%3Dforeign'],
    [() => state.client.readMealPlan('plan/../other'), '/api/health/v1/meal-plans/plan%2F..%2Fother'],
  ]
  for (const [invoke, url] of cases) {
    const pending = invoke(), call = state.calls.at(-1)
    assert.equal(call.url, url)
    assert.equal(call.method, 'GET')
    assert.equal(call.timeout, 15000)
    assert.equal(call.data, undefined)
    assert.deepEqual(call.header, { 'Content-Type': 'application/json', Authorization: 'Bearer synthetic-token-a' })
    const response = { authoritative: url, private: 'synthetic only' }
    call.success({ statusCode: 200, data: response })
    assert.deepEqual(await pending, response)
  }
  assert.deepEqual([...state.values.entries()], [[SESSION_KEY, ACCOUNT_A]])
})

test('预览逐层白名单保留明确份量文本和零营养缺失语义，不提交伪造健康或模型内容', async () => {
  const state = harness()
  await signIn(state)
  const expected = threeMeals()
  const input = structuredClone(expected)
  Object.assign(input, { member_id: 'foreign', status: 'approved', personalized: true, nutrition: { energy: 0 }, model: { secret: 'ignored' }, purpose: 'meal_plan' })
  for (const meal of input.meals) {
    Object.assign(meal, { members: ['foreign'], nutrition: { totals: { energy: 900 } }, approved: true })
    for (const dish of meal.dishes) Object.assign(dish, { name: '虚构菜名', ingredients: [{ member_id: 'foreign' }], nutrients: { energy: 900 }, rule_version: 99 })
  }
  const pending = state.client.previewMealPlan(MEMBER, input), call = state.calls.at(-1)
  assert.equal(call.url, `/api/health/v1/members/${MEMBER}/meal-plan-previews`)
  assert.equal(call.method, 'POST')
  assert.deepEqual(call.data, expected)
  assert.equal(call.header['Idempotency-Key'], undefined)
  assert.equal(call.header['If-Match'], undefined)
  input.meals[0].dishes[0].grams = '999'
  input.meals[1].dishes.push({ recipe_version_id: 'foreign' })
  assert.deepEqual(call.data, expected)
  const snapshot = { preview_id: PREVIEW, member_id: MEMBER, nutrition: { totals: { energy: null, protein: '0' } } }
  call.success({ statusCode: 201, data: snapshot })
  assert.deepEqual(await pending, snapshot)
})

test('保存只引用预览和原幂等键，换菜只提交DTO并发送带引号原版本', async () => {
  const state = harness()
  await signIn(state)
  const saving = state.client.saveMealPlan(MEMBER, {
    preview_id: PREVIEW, client_request_id: REQUEST_KEY, member_id: 'foreign', nutrition: { energy: 99 }, approved: true,
    requestKey: 'foreign', header: { Authorization: 'foreign', 'If-Match': '"99"' },
  })
  const save = state.calls.at(-1)
  assert.equal(save.url, `/api/health/v1/members/${MEMBER}/meal-plans`)
  assert.equal(save.method, 'POST')
  assert.deepEqual(save.data, { preview_id: PREVIEW, client_request_id: REQUEST_KEY })
  assert.deepEqual(save.header, { 'Content-Type': 'application/json', Authorization: 'Bearer synthetic-token-a', 'Idempotency-Key': REQUEST_KEY })
  save.success({ statusCode: 201, data: { plan_id: PLAN, member_id: MEMBER, version: 1 } })
  assert.equal((await saving).version, 1)

  const expected = swapIntent()
  const input = structuredClone(expected)
  Object.assign(input, { member_id: 'foreign', personalized: true, nutrition: { energy: 1 }, matchVersion: 99, headers: { 'If-Match': '"99"' } })
  Object.assign(input.replacement, { name: '虚构菜名', member_portions: [{ member_id: 'foreign' }], approved: true, nutrition: { energy: 99 } })
  const swapping = state.client.swapMealPlan(PLAN, input), swap = state.calls.at(-1)
  assert.equal(swap.url, `/api/health/v1/meal-plans/${PLAN}/swap`)
  assert.equal(swap.method, 'POST')
  assert.deepEqual(swap.data, expected)
  assert.deepEqual(swap.header, { 'Content-Type': 'application/json', Authorization: 'Bearer synthetic-token-a', 'Idempotency-Key': REQUEST_KEY, 'If-Match': '"2"' })
  input.version = 99
  input.replacement.portion_count = '9'
  assert.deepEqual(swap.data, expected)
  swap.success({ statusCode: 200, data: { plan_id: PLAN, member_id: MEMBER, version: 3 } })
  assert.equal((await swapping).version, 3)
})

test('未登录时七个餐单操作均拒绝发出业务请求', async () => {
  const state = harness()
  const calls = [
    () => state.client.listMealPlans(MEMBER),
    () => state.client.readMealPlan(PLAN),
    () => state.client.listPublishedRecipes('合成菜谱'),
    () => state.client.listRecipePortions(RECIPE),
    () => state.client.previewMealPlan(MEMBER, threeMeals()),
    () => state.client.saveMealPlan(MEMBER, { preview_id: PREVIEW, client_request_id: REQUEST_KEY }),
    () => state.client.swapMealPlan(PLAN, swapIntent()),
  ]
  for (const invoke of calls) await assert.rejects(invoke(), { status: 401, code: 'login_required' })
  assert.equal(state.calls.length, 0)
})

test('菜谱查询、非法三餐、嵌套伪造份量与非法换菜版本在发送前明确失败', async () => {
  const state = harness()
  await signIn(state)
  const before = state.calls.length
  for (const query of [{ q: '任意对象' }, 'x'.repeat(121)]) {
    await assert.rejects(state.client.listPublishedRecipes(query), { status: 422, code: 'invalid_recipe_query' })
  }
  const specs = [
    { plan_date: '2026-10-10', meals: [] },
    { ...threeMeals(), plan_date: { member_id: 'foreign' } },
    { ...threeMeals(), meals: [{ meal_type: 'breakfast', dishes: [] }, ...threeMeals().meals.slice(1)] },
  ]
  const duplicate = threeMeals()
  duplicate.meals[2].meal_type = 'breakfast'
  specs.push(duplicate)
  for (const grams of [{ health_profile: 'foreign' }, [], false, '', 0, -1, Infinity]) {
    const spec = threeMeals()
    spec.meals[0].dishes[0].grams = grams
    specs.push(spec)
  }
  const referenceConflict = threeMeals()
  referenceConflict.meals[0].dishes[0].portion_reference_id = PORTION
  referenceConflict.meals[0].dishes[0].portion_count = '1'
  specs.push(referenceConflict)
  const countWithoutReference = threeMeals()
  countWithoutReference.meals[0].dishes[0].portion_count = '1'
  specs.push(countWithoutReference)
  for (const spec of specs) {
    await assert.rejects(async () => state.client.previewMealPlan(MEMBER, spec), { status: 422, code: 'invalid_meal_plan_input' })
  }
  for (const change of [{ version: '2' }, { version: 0 }, { version: 1.5 }, { version: Number.MAX_SAFE_INTEGER + 1 }, { dish_index: -1 }, { dish_index: 10 }, { dish_index: '0' }, { reason: '' }, { reason: 'x'.repeat(501) }, { meal_type: 'snack' }]) {
    await assert.rejects(async () => state.client.swapMealPlan(PLAN, { ...swapIntent(), ...change }), { status: 422, code: 'invalid_meal_plan_input' })
  }
  await assert.rejects(async () => state.client.saveMealPlan(MEMBER, { preview_id: PREVIEW }), { status: 422 })
  await assert.rejects(async () => state.client.listRecipePortions({ recipe_version_id: RECIPE, food_id: 'foreign' }), { status: 422 })
  assert.equal(state.calls.length, before)
})

test('DTO允许未知计划份量留空，响应保留服务端不完整状态而不填零', async () => {
  const state = harness()
  await signIn(state)
  const spec = threeMeals()
  spec.meals[0].dishes[0] = { recipe_version_id: RECIPE }
  const pending = state.client.previewMealPlan(MEMBER, spec), call = state.calls.at(-1)
  assert.deepEqual(call.data.meals[0].dishes[0], { recipe_version_id: RECIPE })
  call.success({ statusCode: 201, data: { preview_id: PREVIEW, nutrition: { complete: false, totals: { energy: null } } } })
  assert.deepEqual(await pending, { preview_id: PREVIEW, nutrition: { complete: false, totals: { energy: null } } })
})

test('网络和5xx未知写入不自动重发，显式恢复仍使用原正文、幂等键和原版本', async () => {
  const state = harness()
  await signIn(state)
  const intents = [
    [() => state.client.saveMealPlan(MEMBER, { preview_id: PREVIEW, client_request_id: REQUEST_KEY }), { preview_id: PREVIEW, client_request_id: REQUEST_KEY }, undefined],
    [() => state.client.swapMealPlan(PLAN, swapIntent()), swapIntent(), '"2"'],
  ]
  for (const [invoke, data, version] of intents) {
    for (const status of [0, 500, 503]) {
      const count = state.calls.length
      const pending = invoke(), failed = state.calls.at(-1)
      if (status === 0) failed.fail({ errMsg: 'synthetic response lost after commit' })
      else failed.success({ statusCode: status, data: { code: 'synthetic_unavailable', message: '合成未知写入结果' } })
      await assert.rejects(pending, { status, code: status === 0 ? 'network_error' : 'synthetic_unavailable' })
      assert.equal(state.calls.length, count + 1)
      assert.deepEqual(state.client.getSession(), ACCOUNT_A)
      const retry = invoke(), restored = state.calls.at(-1)
      assert.deepEqual(restored.data, data)
      assert.deepEqual(restored.data, failed.data)
      assert.equal(restored.header['Idempotency-Key'], REQUEST_KEY)
      assert.equal(restored.header['If-Match'], version)
      restored.success({ statusCode: 200, data: { plan_id: PLAN, version: 3 } })
      assert.deepEqual(await retry, { plan_id: PLAN, version: 3 })
      assert.equal(state.calls.length, count + 2)
    }
  }
})

test('当前401清理会话且不重试保存，拒权、来源失效与冲突保留实际业务错误', async () => {
  const state = harness()
  await signIn(state)
  for (const [status, code] of [[403, 'diet_edit_required'], [404, 'not_found'], [409, 'version_conflict'], [410, 'source_invalidated']]) {
    const count = state.calls.length
    const pending = state.client.swapMealPlan(PLAN, swapIntent())
    state.calls.at(-1).success({ statusCode: status, data: { code, message: '合成业务拒绝' } })
    await assert.rejects(pending, { status, code, message: '合成业务拒绝' })
    assert.equal(state.calls.length, count + 1)
    assert.deepEqual(state.client.getSession(), ACCOUNT_A)
  }
  const count = state.calls.length
  const pending = state.client.saveMealPlan(MEMBER, { preview_id: PREVIEW, client_request_id: REQUEST_KEY })
  state.calls.at(-1).success({ statusCode: 401, data: { code: 'token_expired', message: '合成会话过期' } })
  await assert.rejects(pending, { status: 401, code: 'token_expired' })
  assert.equal(state.calls.length, count + 1)
  assert.equal(state.client.getSession(), null)
  assert.equal(state.values.has(SESSION_KEY), false)
  await assert.rejects(state.client.readMealPlan(PLAN), { code: 'login_required' })
  assert.equal(state.calls.length, count + 1)
})

test('所有餐单响应受会话版本隔离，旧成功、401、500和网络失败不能影响新账号', async () => {
  for (const outcome of [200, 401, 500, 0]) {
    const state = harness()
    await signIn(state)
    const pending = [
      state.client.listMealPlans(MEMBER),
      state.client.readMealPlan(PLAN),
      state.client.listPublishedRecipes(),
      state.client.listRecipePortions(RECIPE),
      state.client.previewMealPlan(MEMBER, threeMeals()),
      state.client.saveMealPlan(MEMBER, { preview_id: PREVIEW, client_request_id: REQUEST_KEY }),
      state.client.swapMealPlan(PLAN, swapIntent()),
    ]
    const rejected = pending.map(result => assert.rejects(result, { status: 0, code: 'stale_session' }))
    const oldCalls = state.calls.slice(1)
    state.client.logout()
    await signIn(state, ACCOUNT_B)
    for (const call of oldCalls) {
      if (outcome === 0) call.fail({ errMsg: 'synthetic stale transport failure' })
      else call.success({ statusCode: outcome, data: { member_id: MEMBER, private: 'synthetic old body' } })
    }
    await Promise.all(rejected)
    assert.deepEqual(state.client.getSession(), ACCOUNT_B)
    assert.deepEqual([...state.values.entries()], [[SESSION_KEY, ACCOUNT_B]])
    assert.equal(state.calls.length, 9)
  }
})
