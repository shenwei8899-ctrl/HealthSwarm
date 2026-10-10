import test from 'node:test'
import assert from 'node:assert/strict'
import { mealPlanMember, mealPlanLink, mealPlanList, mealPlanSnapshot, mealPlanPreview, mealPlanDetail,
  mealPlanResult, publishedRecipes, recipePortions } from '../src/ui/meal-plan-projection.js'

const values = { energy_kcal: '123.45', protein_g: '8.20', fat_g: '1.10', carbohydrate_g: null, sodium_mg: '0' }
// 独立手写wire oracle；值故意不满足可在客户端推导的配方比例。
function snapshot() {
  return { status: 'draft', scope: 'single_member_recipe_draft', personalized: false, plan_date: '2026-10-10',
    nutrition: { totals: { ...values }, complete: false, estimated: true, calculation_version: 'three-meals-v1', private_trace: 'SECRET' },
    professional_review: 'not_reviewed', adoption_available: false, purchase_available: false,
    full_health_profile_available: false, confirmed_profile_version: 4, personal_target: { private_health: 'SECRET' },
    notice: '计划份量，待核对', meals: ['breakfast', 'lunch', 'dinner'].map(meal_type => ({ meal_type,
      nutrition: { totals: { ...values }, complete: false, items: [{ raw_health: 'SECRET' }], sources: [{ private_uid: 'SECRET' }] },
      dishes: [{ dish_index: 0, recipe_version_id: 'published-version', name: '合成公开菜名', planned_grams: null,
        portion_source: 'unknown', cooking_state: '熟', source: '合成数据', dataset_version: 'public-v1', license: '测试', edition: 'v1',
        nutrition: { ...values }, private_recipe_data: 'SECRET', ingredients: [
          { name: '合成原料', food_id: 'food-version', role: 'food', planned_grams: '0', private_health: 'SECRET' },
        ] }],
    })) }
}
function plan(id = 'plan', version = 1) { return { plan_id: id, member_id: 'member', version, updated_at: '2026-10-10T10:00:00Z', ...snapshot() } }
const clone = value => JSON.parse(JSON.stringify(value))

test('白名单保留三餐具体菜名原料与服务器数值，null和零互异，不读健康来源和内部记录', () => {
  const result = mealPlanSnapshot(snapshot())
  assert.deepEqual(result.meals.map(row => row.meal_type), ['breakfast', 'lunch', 'dinner'])
  assert.equal(result.meals[0].dishes[0].name, '合成公开菜名')
  assert.equal(result.meals[0].dishes[0].planned_grams, null)
  assert.equal(result.meals[0].dishes[0].ingredients[0].planned_grams, '0')
  assert.equal(result.nutrition.totals.sodium_mg, '0')
  assert.equal(result.nutrition.totals.carbohydrate_g, null)
  assert.equal(result.meals[0].dishes[0].nutrition.energy_kcal, '123.45')
  assert.equal(JSON.stringify(result).includes('SECRET'), false)
  assert.equal(Object.hasOwn(result, 'personal_target'), false)
  assert.equal(result.editable, true)
})

test('缺失营养字段保留null，数值零和文本零保留原值；非法营养不能伪装为未知', () => {
  const input = snapshot(); input.nutrition.totals = { energy_kcal: 0, protein_g: '0' }
  assert.deepEqual(mealPlanSnapshot(input).nutrition.totals,
    { energy_kcal: 0, protein_g: '0', fat_g: null, carbohydrate_g: null, sodium_mg: null })
  for (const wrong of ['', 'not-a-number', -1, Infinity, true, {}, ' 0']) {
    const broken = snapshot(); broken.nutrition.totals.energy_kcal = wrong
    assert.throws(() => mealPlanSnapshot(broken), { code: 'protocol_mismatch' })
  }
})

test('本人入口须匹配owner、本人标签与profile_view/profile_edit/diet_edit，并绑定真实家庭关联', () => {
  const owner = { id: 'member', display_name: '合成本人', is_owner: true, relationship_label: '本人',
    scopes: ['profile_view', 'profile_edit', 'diet_edit'], full_health: 'SECRET' }
  assert.deepEqual(mealPlanMember([owner], 'member'), { id: 'member', display_name: '合成本人', scopes: owner.scopes })
  for (const patch of [{ is_owner: false }, { relationship_label: '家人' }, { id: 'another' },
    ...owner.scopes.map(scope => ({ scopes: owner.scopes.filter(value => value !== scope) }))]) {
    assert.throws(() => mealPlanMember([{ ...owner, ...patch }], 'member'), { code: 'protocol_mismatch' })
  }
  assert.deepEqual(mealPlanLink({ member_id: 'member', family_id: 'family', source_member_id: 'source', health: 'SECRET' }, 'member'),
    { member_id: 'member', family_id: 'family', source_member_id: 'source' })
  for (const patch of [{ member_id: 'other' }, { family_id: null }, { source_member_id: '' }]) {
    assert.throws(() => mealPlanLink({ member_id: 'member', family_id: 'family', source_member_id: 'source', ...patch }, 'member'),
      { code: 'protocol_mismatch' })
  }
})

test('有界列表索引不保存快照，家庭项只显示unsupported；单成员个体化可读但不可普通换菜', () => {
  const family = { ...plan('family'), scope: 'family_recipe_draft', members: { someone: { medical: 'SECRET' } } }
  const personalized = { ...plan('personal'), personalized: true }
  const result = mealPlanList({ plans: [plan(), family, personalized], truncated: true }, 'member')
  assert.equal(result.truncated, true)
  assert.equal(result.plans[1].supported, false)
  assert.equal(result.plans[1].editable, false)
  assert.equal(JSON.stringify(result).includes('SECRET'), false)
  assert.equal(Object.hasOwn(result.plans[0], 'meals'), false)
  assert.equal(mealPlanResult(personalized, 'member', 'personal').editable, false)
  assert.throws(() => mealPlanSnapshot(family), { code: 'protocol_mismatch' })
  assert.throws(() => mealPlanList({ plans: [{ ...plan(), member_id: 'other' }], truncated: false }, 'member'), { code: 'protocol_mismatch' })
  assert.throws(() => mealPlanList({ plans: [plan(), plan()], truncated: false }, 'member'), { code: 'protocol_mismatch' })
})

test('详情与预览精确绑定成员餐单，修订独立只读，拒绝无当前版历史与错误菜品位置', () => {
  const input = { ...plan('plan', 2), revisions: [
    { version: 1, reason: '原版', created_at: '2026-10-09', snapshot: snapshot() },
    { version: 2, reason: '换菜', created_at: '2026-10-10', snapshot: snapshot() },
  ] }
  const result = mealPlanDetail(input, 'member', 'plan')
  assert.equal(result.plan.version, 2); assert.equal(result.history[0].version, 1)
  assert.equal(result.history[0].snapshot.editable, false)
  assert.equal(result.plan.editable, true)
  assert.throws(() => mealPlanDetail(input, 'member', 'another-plan'), { code: 'protocol_mismatch' })
  assert.throws(() => mealPlanDetail({ ...input, revisions: input.revisions.slice(0, 1) }, 'member', 'plan'), { code: 'protocol_mismatch' })
  assert.throws(() => mealPlanDetail({ ...input, revisions: [input.revisions[0], input.revisions[0]] }, 'member', 'plan'), { code: 'protocol_mismatch' })
  const shifted = clone(input); shifted.meals[0].dishes[0].dish_index = 1
  assert.throws(() => mealPlanDetail(shifted, 'member', 'plan'), { code: 'protocol_mismatch' })
  assert.equal(mealPlanPreview({ ...snapshot(), member_id: 'member', preview_id: 'preview' }, 'member').preview_id, 'preview')
  assert.throws(() => mealPlanPreview({ ...snapshot(), member_id: 'other', preview_id: 'preview' }, 'member'), { code: 'protocol_mismatch' })
  assert.throws(() => mealPlanPreview({ ...snapshot(), personalized: true, member_id: 'member', preview_id: 'preview' }, 'member'), { code: 'protocol_mismatch' })
})

test('发布菜谱与份量只保留公开字段；跨版本参考、食品参考和重复版本被拒绝', () => {
  const recipe = { id: 'published-version', name: '合成公开菜名', yield_grams: '300', source: '合成来源',
    ingredients: [{ food: { id: 'food', name: '原料', health: 'SECRET' }, grams: '300', role: 'food' }],
    published_by: 'SECRET', nutrients: values }
  assert.deepEqual(publishedRecipes([]), [])
  assert.equal(JSON.stringify(publishedRecipes([recipe])).includes('SECRET'), false)
  const portion = { id: 'reference', recipe_version_id: 'published-version', food_id: null, unit_label: '合成碗',
    grams_per_unit: '200', applicable_scope: '合成测试', source: '合成来源', published_by: 'SECRET' }
  assert.equal(recipePortions([portion], 'published-version')[0].unit_label, '合成碗')
  assert.equal(JSON.stringify(recipePortions([portion], 'published-version')).includes('SECRET'), false)
  assert.throws(() => recipePortions([{ ...portion, recipe_version_id: 'other' }], 'published-version'), { code: 'protocol_mismatch' })
  assert.throws(() => recipePortions([{ ...portion, food_id: 'food' }], 'published-version'), { code: 'protocol_mismatch' })
  assert.throws(() => recipePortions([{ ...portion, grams_per_unit: '0' }], 'published-version'), { code: 'protocol_mismatch' })
  assert.throws(() => publishedRecipes([recipe, recipe]), { code: 'protocol_mismatch' })
})
