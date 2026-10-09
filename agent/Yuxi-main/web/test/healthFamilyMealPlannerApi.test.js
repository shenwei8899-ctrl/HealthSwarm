import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const source = (await readFile(new URL('../src/apis/health_vision_api.js', import.meta.url), 'utf8'))
  .replace(/^import.*\n/gm, '')
  .replace('export const healthVisionApi', 'const healthVisionApi')

function api() {
  const calls = []
  const post = async (...args) => {
    calls.push(args)
    return { persisted: true }
  }
  const wrapper = new Function(
    'apiGet', 'apiPost', 'apiPut', 'apiDelete', 'apiRequest', 'buildQuery',
    `${source}\nreturn healthVisionApi`
  )(() => {}, post, () => {}, () => {}, () => {}, () => '')
  return { wrapper, calls }
}

const sources = {
  version: 3,
  rule_code: 'approved-family',
  rule_version: 7,
  profile_versions: { 'member-a': 2, 'member-b': 4 }
}

test('家庭线程传全部成员来源及固定创建幂等键', async () => {
  const { wrapper, calls } = api()
  const body = { ...sources, plan_id: 'plan-a', client_request_id: 'family-binding' }
  assert.deepEqual(await wrapper.createFamilyMealPlanner('member-a', body), { persisted: true })
  assert.deepEqual(calls, [[
    '/api/health/v1/members/member-a/family-meal-planner', body,
    { headers: { 'Idempotency-Key': 'family-binding' } }
  ]])
})

for (const [method, path, details] of [
  ['familySafeSwapMealPlan', 'family-safe-swap', {
    meal_type: 'lunch', dish_index: 2, recipe_version_id: 'approved-replacement'
  }],
  ['familySafeRegenerateMealPlan', 'family-safe-regenerate', { preview_hash: 'original-hash' }],
  ['familyParticipationMealPlan', 'family-participation', {
    preview_hash: 'allocations-hash', reason: '本人早餐增加至55克',
    allocations: [{ meal_type: 'breakfast', participant_ids: ['member-a'],
      dishes: [{ dish_index: 2, member_portions: [{ member_id: 'member-a', grams: '55' }] }] }]
  }]
]) {
  test(`${path}确认原样传递服务预览来源和分配，使用条件版本与原幂等键`, async () => {
    const { wrapper, calls } = api()
    const body = { ...sources, ...details, client_request_id: 'original-confirmation' }
    await wrapper[method]('plan-a', body)
    await wrapper[method]('plan-a', body)
    assert.deepEqual(calls, Array.from({ length: 2 }, () => [
      `/api/health/v1/meal-plans/plan-a/${path}`, body,
      { headers: { 'Idempotency-Key': 'original-confirmation', 'If-Match': '"3"' } }
    ]))
    assert.equal(calls[0][1], body)
  })
}
