import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const source = (
  await readFile(new URL('../src/apis/health_vision_api.js', import.meta.url), 'utf8')
)
  .replace(/^import.*\r?\n/gm, '')
  .replace('export const healthVisionApi', 'const healthVisionApi')

function api() {
  const calls = []
  const post = async (...args) => {
    calls.push(args)
    return { persisted: true }
  }
  const wrapper = new Function(
    'apiGet',
    'apiPost',
    'apiPut',
    'apiDelete',
    'apiRequest',
    'buildQuery',
    `${source}\nreturn healthVisionApi`
  )(
    () => {},
    post,
    () => {},
    () => {},
    () => {},
    () => ''
  )
  return { wrapper, calls }
}

const selection = {
  plan_id: 'plan-a',
  version: 3,
  rule_code: 'approved-basic',
  rule_version: 7,
  profile_version: 2
}

test('安全配餐会话绑定成员和完整来源，使用固定创建幂等键', async () => {
  const { wrapper, calls } = api()
  const body = { ...selection, client_request_id: 'binding-key' }
  assert.deepEqual(await wrapper.createSafeMealPlanner('member-a', body), { persisted: true })
  assert.deepEqual(calls, [
    [
      '/api/health/v1/members/member-a/safe-meal-plan-conversations',
      body,
      { headers: { 'Idempotency-Key': 'binding-key' } }
    ]
  ])
})

test('安全换菜确认调用业务Owner，版本条件和幂等键进入HTTP头', async () => {
  const { wrapper, calls } = api()
  const body = {
    version: 3,
    rule_code: 'approved-basic',
    rule_version: 7,
    profile_version: 2,
    meal_type: 'lunch',
    dish_index: 0,
    recipe_version_id: 'replacement-a',
    client_request_id: 'swap-key'
  }
  await wrapper.safeSwapMealPlan('plan-a', body)
  assert.deepEqual(calls, [
    [
      '/api/health/v1/meal-plans/plan-a/safe-swap',
      body,
      { headers: { 'Idempotency-Key': 'swap-key', 'If-Match': '"3"' } }
    ]
  ])
  assert.equal(Object.hasOwn(body, 'preview_id'), false)
})

test('整份重生成确认仅提交业务预览摘要，沿用版本和幂等契约', async () => {
  const { wrapper, calls } = api()
  const body = {
    version: 3,
    rule_code: 'approved-basic',
    rule_version: 7,
    profile_version: 2,
    preview_hash: 'owner-preview-hash',
    client_request_id: 'regenerate-key'
  }
  await wrapper.safeRegenerateMealPlan('plan-a', body)
  assert.deepEqual(calls, [
    [
      '/api/health/v1/meal-plans/plan-a/safe-regenerate',
      body,
      { headers: { 'Idempotency-Key': 'regenerate-key', 'If-Match': '"3"' } }
    ]
  ])
})
