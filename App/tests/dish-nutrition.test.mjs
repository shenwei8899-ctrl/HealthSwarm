import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { computed, ref, watch } from 'vue'
import { DISH_NUTRITION_FIELDS, dishNutritionItems, normalizeDishNutrition } from '../src/utils/dish-nutrition.js'
import { demoDishNutrition } from '../src/utils/dish-nutrition-demo.js'
import { createPlan } from '../src/utils/demo.js'
import { createDishGuide, createCookingGuide, mealFromRoute } from '../src/utils/meal-flow.js'
import { DINNER_FISH_SWAPS, applyMealCustomization } from '../src/utils/meal-customization.js'
import { EXCLUSIVE_PLANS, createDeliveryBatches, getExclusivePlan } from '../src/utils/exclusive-plans.js'
import { createDemoOrder, getOrder } from '../src/utils/orders.js'
import { todayPlan, localDate } from '../src/utils/meal-state.js'

const family = { members: [{ id: 1, age: 30, health: '一般成人' }], defaultDiners: [1], allergies: ['无已知过敏'] }
const metadata = { basis: 'per_100g', foodState: 'cooked_edible', source: 'calculated', sourceReference: 'test-recipe-v1' }
const missingItems = value => dishNutritionItems(value).every(item => item.text === '暂无数据' && !item.available)

function setupStorage() {
  const storage = new Map()
  globalThis.uni = { getStorageSync: key => storage.get(key), setStorageSync: (key, value) => storage.set(key, JSON.parse(JSON.stringify(value))) }
}

test('nutrition distinguishes real zero, missing and invalid values without changing units or basis', () => {
  const value = { ...metadata, energyKcal: 0, proteinG: null, fatG: -1, carbohydrateG: '3.5', fiberG: Number.NaN, sodiumMg: Infinity }
  const items = dishNutritionItems(value)
  assert.equal(items[0].text, '0')
  assert.equal(items[0].unit, 'kcal')
  assert.ok(items.slice(1).every(item => item.text === '暂无数据'))
  assert.equal(dishNutritionItems({ ...metadata, fiberG: 0 })[4].text, '0.0')
  assert.equal(dishNutritionItems({ ...metadata, fiberG: 0.03 })[4].text, '<0.1')
  assert.equal(dishNutritionItems({ ...metadata, sodiumMg: 0.3 })[5].text, '<1')
  assert.ok(missingItems({ ...metadata, basis: 'per_serving', energyKcal: 120 }))
  assert.ok(missingItems({ ...metadata, foodState: 'raw', energyKcal: 120 }))
  assert.ok(missingItems({ energyKcal: 120 }))
  assert.ok(missingItems(null))
})

test('every ordinary, substituted and exclusive-plan dish provides the six-field nutrition object', () => {
  const basePlans = ['早餐', '午餐', '晚餐'].map(meal => createPlan(family, meal))
  const plans = [...basePlans, ...DINNER_FISH_SWAPS.map(swap => applyMealCustomization(basePlans[2], swap))]
  for (const plan of plans) for (const guide of createCookingGuide(plan).dishGuides) {
    assert.equal(dishNutritionItems(guide.nutrition).length, 6)
    assert.equal(guide.nutrition.source, 'demo')
    assert.ok(DISH_NUTRITION_FIELDS.every(({ key }) => Object.hasOwn(guide.nutrition, key)))
  }
  for (const template of EXCLUSIVE_PLANS) for (const batchIndex of [1, 2, 21]) for (const meal of ['早餐', '午餐', '晚餐']) {
    const guide = createCookingGuide(basePlans[2], template, { batchIndex, meal })
    assert.ok(guide.dishGuides.every(dish => DISH_NUTRITION_FIELDS.every(({ key }) => Object.hasOwn(dish.nutrition, key))))
  }
  for (const name of ['清蒸鸡肉', '番茄炖鸡肉', '清炖冬瓜', '番茄冬瓜汤', '小米粥', '清炒上海青']) assert.equal(demoDishNutrition(name).source, 'demo')
  assert.ok(missingItems(createDishGuide({ meal: '晚餐', dishes: [{ name: '新菜品' }] }, '新菜品').nutrition))
})

test('explicit recipe nutrition overrides demo values, including authoritative missing data', () => {
  const value = { ...metadata, energyKcal: 200, proteinG: 0, sodiumMg: 80 }
  const plan = { meal: '晚餐', dishes: [{ name: '清蒸鲈鱼', nutrition: value }] }
  const guide = createDishGuide(plan, '清蒸鲈鱼')
  assert.equal(guide.nutrition.energyKcal, 200)
  assert.equal(guide.nutrition.proteinG, 0)
  assert.equal(guide.nutrition.fatG, null)
  assert.equal(guide.nutrition.source, 'calculated')
  value.energyKcal = 500
  assert.equal(guide.nutrition.energyKcal, 200)
  plan.dishes[0].nutrition = null
  assert.ok(missingItems(createDishGuide(plan, '清蒸鲈鱼').nutrition))

  const dinner = createPlan(family, '晚餐')
  dinner.dishes[0].nutrition = { ...metadata, energyKcal: 500 }
  const changed = applyMealCustomization(dinner, DINNER_FISH_SWAPS[1])
  assert.equal(createDishGuide(changed, '香煎鲈鱼').nutrition.energyKcal, 150)
  assert.equal(dinner.dishes[0].nutrition.energyKcal, 500)
})

test('ordinary and 21-batch orders persist recipe nutrition without changing existing snapshots', () => {
  setupStorage()
  const plan = createPlan(family, '晚餐')
  const guide = createCookingGuide(plan)
  const original = JSON.parse(JSON.stringify(guide.dishGuides[0].nutrition))
  const order = createDemoOrder({ items: [], totalCents: 100, meal: '晚餐', cookingGuide: guide })
  guide.dishGuides[0].nutrition.energyKcal = 999
  assert.deepEqual(getOrder(order.id).cookingGuide.dishGuides[0].nutrition, original)

  const template = getExclusivePlan('balanced')
  const batches = createDeliveryBatches(template, localDate(), 21)
  const cookingGuides = batches.map(batch => ({ index: batch.index, guides: batch.meals.map(item => createCookingGuide(plan, template, { batchIndex: batch.index, meal: item.type })) }))
  const paid = createDemoOrder({ items: [], totalCents: 100, meal: '晚餐', sourcePlanId: 'balanced', deliveryBatches: batches, cookingGuides })
  const snapshot = JSON.stringify(getOrder(paid.id))
  const today = todayPlan(family, '晚餐')
  assert.deepEqual(today.dishes[0].nutrition, today.snapshot.dishGuides[0].nutrition)
  assert.deepEqual(createDishGuide(today, today.dishes[0].name).nutrition, normalizeDishNutrition(today.snapshot.dishGuides[0].nutrition))
  cookingGuides[0].guides[0].dishGuides[0].nutrition.energyKcal = 777
  assert.equal(JSON.stringify(getOrder(paid.id)), snapshot)

  // Older paid recipes retain unavailable nutrition rather than borrowing a new fixture.
  const legacy = { ...today, dishes: [{ ...today.dishes[0], nutrition: null }] }
  assert.ok(missingItems(createDishGuide(legacy, legacy.dishes[0].name).nutrition))
})

test('switching dishes in a received order switches the displayed nutrition and handles old recipes', () => {
  setupStorage()
  const cookingGuide = createCookingGuide(createPlan(family, '晚餐'))
  delete cookingGuide.dishGuides[1].nutrition
  const created = createDemoOrder({ items: [], totalCents: 100, meal: '晚餐', cookingGuide })
  const deps = { computed, ref, watch, getOrder, getProfile: () => family, createPlan, createCookingGuide, getExclusivePlan, mealFromRoute,
    onLoad: callback => callback({ id: created.id, meal: 'dinner' }), onShow: callback => callback() }
  const script = readFileSync(new URL('../src/pages/cook/index.vue', import.meta.url), 'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  const page = new Function('deps', `const {${Object.keys(deps).join(',')}} = deps;\n${script}\nreturn { activeDish, activeDishName }`)(deps)
  assert.equal(page.activeDish.value.nutrition.energyKcal, 120)
  page.activeDishName.value = cookingGuide.dishGuides[2].name
  assert.equal(page.activeDish.value.nutrition.energyKcal, cookingGuide.dishGuides[2].nutrition.energyKcal)
  page.activeDishName.value = cookingGuide.dishGuides[1].name
  assert.ok(missingItems(page.activeDish.value.nutrition))
})
