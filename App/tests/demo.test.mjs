import test from 'node:test'
import assert from 'node:assert/strict'
import { createPlan, subtotal, photoEstimate, reviewReasons } from '../src/utils/demo.js'
import { normalizeProfile } from '../src/utils/profile.js'
import { createDeliveryBatches, EXCLUSIVE_PLANS, getExclusivePlan } from '../src/utils/exclusive-plans.js'
import { createMealBundles } from '../src/utils/meal-bundles.js'
import { existsSync } from 'node:fs'
import { createDiabetesCasePlan, createDiabetesCaseProfile } from '../src/utils/health-cases.js'
import { applyMealCustomization, DINNER_FISH_SWAPS, getDishSwapOptions } from '../src/utils/meal-customization.js'
import { createCookingGuide, createDishGuide, mealFromRoute, mealToRoute } from '../src/utils/meal-flow.js'
import { createDemoOrder, getOrder, orderStatus, updateOrder } from '../src/utils/orders.js'

const family = (count = 3) => ({ members: Array.from({ length: count }, (_, id) => ({ id, age: 30, health: '一般成人' })), allergies: ['无已知过敏'] })

test('recommendation cards match shop products, package quantities and total', () => {
  for (const meal of ['早餐', '午餐', '晚餐']) for (const count of [1, 3, 4, 6]) {
    const plan = createPlan(family(count), meal)
    const bundles = createMealBundles(plan)
    assert.equal(bundles.length, 3)
    assert.deepEqual(new Set(bundles.flatMap(b => b.productIds)), new Set(plan.products.map(p => p.id)))
    assert.equal(bundles.reduce((sum, b) => sum + b.priceCents, 0), subtotal(plan.products, plan.products.map(p => p.id)))
    for (const bundle of bundles) {
      assert.equal(bundle.priceCents, subtotal(plan.products, bundle.productIds))
      assert.ok(bundle.spec.length)
      assert.ok(existsSync(new URL('../src' + bundle.image, import.meta.url)))
    }
  }
  assert.equal(createMealBundles(createPlan(family(3)))[0].priceCents, 4860)
})

test('known allergies are excluded before ingredient recommendation', () => {
 const profile=normalizeProfile(family());profile.members[0].allergyStatus='set';profile.members[0].allergies=['鱼类']
 const plan=createPlan(profile)
 assert.equal(plan.blocked.length,0)
 assert.ok(!plan.products.some(p=>p.id===1))
 assert.ok(plan.dishes.some(d=>d.name==='清蒸鸡肉'))
 assert.deepEqual(new Set(createMealBundles(plan).flatMap(b=>b.productIds)),new Set(plan.products.map(p=>p.id)))
})

test('shopping list rounds each package up and subtotal follows selection', () => {
  const plan = createPlan(family(4))
  const fish = plan.products.find(p => p.id === 1)
  assert.equal(fish.need, 600)
  assert.equal(fish.quantity, 2)
  assert.equal(subtotal(plan.products, [1]), 6560)
  assert.equal(subtotal(plan.products, []), 0)
})
test('breakfast has its own ingredient list and covers family size', () => {
  const plan = createPlan(family(2), '早餐')
  assert.equal(plan.products.find(p => p.id === 12).need, 2)
  assert.ok(plan.dishes.some(d => d.name === '原味燕麦粥'))
  assert.ok(!plan.products.some(p => p.id === 1))
})

test('each dish exposes an independent recipe preview and switchable cooking guide', () => {
  for (const meal of ['早餐', '午餐', '晚餐']) {
    const plan = createPlan(family(3), meal)
    const cooking = createCookingGuide(plan)
    assert.equal(cooking.dishGuides.length, plan.dishes.length)
    for (const dish of plan.dishes) {
      const guide = createDishGuide(plan, dish.name)
      assert.equal(guide.name, dish.name)
      assert.ok(guide.image.startsWith('/static/bundles/'))
      assert.ok(guide.minutes > 0)
      assert.ok(guide.ingredients.length)
      assert.ok(guide.steps.length >= 3)
      assert.ok(guide.notes.length)
    }
  }
})
test('daily meal routes and lunch recommendation stay distinct', () => {
  for (const meal of ['早餐', '午餐', '晚餐']) assert.equal(mealFromRoute(mealToRoute(meal)), meal)
  const lunch = createPlan(family(3), '午餐')
  assert.ok(lunch.dishes.some(dish => dish.name === '番茄炒蛋'))
  assert.ok(!lunch.products.some(product => product.id === 1))
  assert.deepEqual(new Set(createMealBundles(lunch).flatMap(bundle => bundle.productIds)), new Set(lunch.products.map(product => product.id)))
})

test('paid orders retain the cooking steps selected at checkout', () => {
  const storage = new Map()
  globalThis.uni = { getStorageSync: key => storage.get(key), setStorageSync: (key, value) => storage.set(key, value) }
  try {
    const lunch = createPlan(family(3), '午餐')
    const guide = createCookingGuide(lunch)
    const order = createDemoOrder({ items: lunch.products, totalCents: subtotal(lunch.products, lunch.products.map(product => product.id)), meal: lunch.meal, cookingGuide: guide })
    lunch.steps[0] = '后来修改的做法'
    assert.equal(getOrder(order.id).cookingGuide.steps[0], guide.steps[0])
    assert.equal(updateOrder(order.id, { status: 'delivered' }).status, 'delivered')
    for (const plan of EXCLUSIVE_PLANS) {
      const exclusiveGuide = createCookingGuide(lunch, plan)
      assert.equal(exclusiveGuide.meal, '晚餐')
      assert.ok(exclusiveGuide.steps.length >= 3)
      assert.ok(exclusiveGuide.title.includes(plan.days[0].meals.find(meal => meal.type === '晚餐').name))
      for (let batchIndex = 1; batchIndex <= 21; batchIndex++) for (const meal of ['早餐', '晚餐']) {
        const guide = createCookingGuide(lunch, plan, { batchIndex, meal })
        assert.equal(guide.meal, meal)
        assert.ok(guide.steps.length >= 3)
      }
    }
    const batches = createDeliveryBatches(getExclusivePlan('balanced'), '2026-10-01', 21)
    const planOrder = createDemoOrder({ items: lunch.products, totalCents: 16800, meal: '晚餐', sourcePlanId: 'balanced', deliveryBatches: batches, cookingGuides: batches.map(batch => ({ index: batch.index, guides: batch.meals.map(item => createCookingGuide(lunch, getExclusivePlan('balanced'), { batchIndex: batch.index, meal: item.type })) })) })
    assert.equal(getOrder(planOrder.id).cookingGuides.length, 21)
    const firstReceived = updateOrder(planOrder.id, { status: 'partial', receivedBatchIndices: [1] })
    assert.equal(orderStatus(firstReceived).label, '配送中')
    assert.equal(firstReceived.cookingGuides[1].guides[0].meal, '早餐')
  } finally {
    delete globalThis.uni
  }
})
test('disease self-reports use AI fixture rules while unsupported minors are blocked',()=>{
 const chronic=normalizeProfile(family());chronic.members[0].healthStatus='set';chronic.members[0].conditions=['糖尿病']
 assert.deepEqual(reviewReasons(chronic),[])
 assert.ok(createPlan(chronic).memberNotes[0].notes.length)
 const child=family();child.members[0].age=8;assert.ok(createPlan(child).blocked.length)
})
test('default diners are separate from household members', () => {
  const profile = family(3)
  profile.defaultDiners = [0, 2]
  const plan = createPlan(profile)
  assert.equal(plan.count, 2)
  assert.deepEqual(plan.members.map(member => member.id), [0, 2])
  profile.members[1].health = '糖尿病（需专业确认）'
  assert.deepEqual(reviewReasons(profile), [])
  profile.defaultDiners.push(1)
  assert.deepEqual(reviewReasons(profile), [])
})
test('legacy profiles expose missing health data instead of assuming normal', () => {
  const profile = normalizeProfile({ members: [{ id: 1, name: '成员' }] })
  assert.equal(profile.members[0].health, '未填写')
  assert.deepEqual(profile.defaultDiners, [1])
  assert.deepEqual(reviewReasons(profile), [])
  assert.equal(createPlan(profile).general, true)
})
test('portion and oil change estimates while preserving interval bounds', () => {
  const full = photoEstimate('全部', '中等')
  const half = photoEstimate('半份', '中等')
  assert.equal(half.kcal, full.kcal / 2)
  assert.ok(photoEstimate('全部', '偏多').kcal > full.kcal)
  assert.ok(half.low < half.kcal && half.kcal < half.high)
})
test('exclusive plan cards have detail, products and allergen confirmation data', () => {
  assert.equal(EXCLUSIVE_PLANS.length, 3)
  for (const plan of EXCLUSIVE_PLANS) {
    assert.ok(plan.days.length >= 2)
    assert.ok(plan.products.length >= 3)
    assert.ok(plan.allergens.length >= 2)
    assert.ok(plan.image.startsWith('/static/bundles/'))
  }
  assert.equal(getExclusivePlan('fiber').name, '高纤轻食计划')
})

test('exclusive plan delivery schedule contains 21 consecutive batches', () => {
  const batches = createDeliveryBatches(getExclusivePlan('balanced'), '2026-10-01', 21)
  assert.equal(batches.length, 21)
  assert.equal(batches[0].date, '2026-10-01')
  assert.equal(batches[20].date, '2026-10-21')
  assert.ok(batches.every(batch => batch.dishes.length >= 2))
  assert.ok(batches.every(batch => batch.meals.some(meal => meal.type === '早餐') && batch.meals.some(meal => meal.type === '晚餐')))
})

test('single-dish swap preserves the rest of the menu and synchronizes the ingredient bundle', () => {
  const base = createPlan(family(3), '晚餐')
  const option = DINNER_FISH_SWAPS.find(item => item.id === 'tomato-fish')
  const swapped = applyMealCustomization(base, { id: option.id, sourceDish: option.sourceDish, reason: '口味不喜欢' })
  assert.equal(getDishSwapOptions('晚餐', '清蒸鲈鱼').length, 3)
  assert.ok(swapped.dishes.some(dish => dish.name === '番茄炖鲈鱼'))
  assert.ok(swapped.dishes.some(dish => dish.name === '香菇青菜'))
  assert.deepEqual(swapped.products.map(product => product.id), base.products.map(product => product.id))
  assert.ok(swapped.steps[1].includes('番茄'))
  assert.equal(createMealBundles(swapped)[0].name, '番茄炖鲈鱼鲜蔬包')
})

test('ingredient-changing swap removes fish and adds shrimp without mutating the base plan', () => {
  const base = createPlan(family(3), '晚餐')
  const swapped = applyMealCustomization(base, { id: 'shrimp-tofu', sourceDish: '清蒸鲈鱼', reason: '家里没有这些食材' })
  assert.ok(base.products.some(product => product.id === 1))
  assert.ok(!swapped.products.some(product => product.id === 1))
  assert.ok(swapped.products.some(product => product.id === 7))
  assert.ok(createMealBundles(swapped)[0].productIds.includes(7))
})

test('diabetes dinner case keeps missing safety data visible and uses the controlled demo plan', () => {
  const profile = createDiabetesCaseProfile()
  const father = profile.members.find(member => member.name === '爸爸')
  assert.equal(profile.members.length, 3)
  assert.equal(father.health, '2型糖尿病（自报）')
  assert.equal(father.hypoglycemiaRisk, '不确定')
  assert.equal(father.kidneyCondition, '未填写')
  assert.equal(father.clinicianGuidance, '')
  assert.equal(createPlan(profile).blocked.length,0, 'diseases are not blanket manual-review blockers')
  const controlledPlan = createDiabetesCasePlan(profile)
  assert.deepEqual(controlledPlan.blocked, [])
  assert.equal(controlledPlan.count, 3)
  assert.ok(controlledPlan.dishes.some(dish => dish.name === '清蒸鲈鱼'))
  assert.ok(createMealBundles(controlledPlan).length)
})

test('structured diabetes profiles are adapted without manual review',()=>{
 const p=normalizeProfile(family(3));p.members[1].healthStatus='set';p.members[1].conditions=['糖尿病']
 const plan=createPlan(p);assert.equal(plan.blocked.length,0);assert.ok(plan.memberNotes[1].portion.includes('主食'));assert.ok(createMealBundles(plan).length)
})
