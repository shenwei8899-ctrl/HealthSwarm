import test from 'node:test'
import assert from 'node:assert/strict'
import { createMealPlanController } from '../src/ui/meal-plan-controller.js'

const member = 'member'
const meals = ['breakfast', 'lunch', 'dinner']
const copy = value => JSON.parse(JSON.stringify(value))
const failure = status => Object.assign(new Error(`合成服务错误${status}`), { status })
const deferred = () => { let resolve, reject; const promise = new Promise((ok, no) => { resolve = ok; reject = no }); return { promise, resolve, reject } }
const recipe = (id = 'recipe') => ({ id, name: `合成菜谱${id}`, yield_grams: '300', cooking_state: '熟', source: '合成来源',
  license: '测试', edition: 'v1', dataset_version: 'public-v1', ingredients: [{ food: { id: 'food', name: '合成原料' }, grams: '300', role: 'food' }] })
const portion = (id = 'recipe') => ({ id: `portion-${id}`, food_id: null, recipe_version_id: id, unit_label: '合成碗', grams_per_unit: '200', source: '合成测量' })
// 独立wire样本不调用投影器或生产计算代码生成oracle。
function snapshot(spec = null) {
  const nutrients = { energy_kcal: '111.25', protein_g: '10', fat_g: '1', carbohydrate_g: null, sodium_mg: '0' }
  return { status: 'draft', scope: 'single_member_recipe_draft', personalized: false,
    plan_date: spec?.plan_date || '2026-10-10', professional_review: 'not_reviewed', notice: '合成计划，仅草稿',
    nutrition: { totals: nutrients, complete: false, estimated: true, calculation_version: 'three-meals-v1' },
    personal_target: { hidden: 'SECRET_HEALTH' }, meals: meals.map(meal_type => ({ meal_type,
      nutrition: { totals: nutrients, complete: false, items: [{ health: 'SECRET_HEALTH' }] },
      dishes: (spec?.meals.find(row => row.meal_type === meal_type)?.dishes || [{ recipe_version_id: 'recipe', grams: '123' }]).map((dish, dish_index) => ({
        dish_index, recipe_version_id: dish.recipe_version_id, name: `服务端${dish.recipe_version_id}`,
        planned_grams: dish.grams ?? (dish.portion_reference_id ? '200' : null), portion_source: dish.grams ? 'planned_estimate' : 'unknown',
        cooking_state: '熟', source: '合成来源', dataset_version: 'v1', nutrition: nutrients,
        ingredients: [{ name: '合成原料', food_id: 'food', role: 'food', planned_grams: null }],
      })),
    })) }
}
function plan(id = 'plan', version = 1, spec = null) { return { plan_id: id, member_id: member, version, updated_at: '2026-10-10', ...snapshot(spec) } }
function detail(id = 'plan', version = 1, spec = null) {
  return { ...plan(id, version, spec), revisions: Array.from({ length: version }, (_, index) => ({
    version: index + 1, reason: index === 0 ? '用户保存餐单草稿' : '合成换菜原因', created_at: '2026-10-10', snapshot: snapshot(spec),
  })) }
}
function setup(overrides = {}, options = {}) {
  let session = { uid: 'uid', username: '合成账号', access_token: 'SECRET_TOKEN' }, listener, serial = 0
  const calls = []
  const client = { sessionRevision: 1, getSession: () => session,
    subscribeSession(callback) { listener = callback; callback(session); return () => { listener = null } },
    listHealthMembers: async () => [{ id: member, is_owner: true, relationship_label: '本人', display_name: '合成本人',
      scopes: ['profile_view', 'profile_edit', 'diet_edit'], profile: 'SECRET_HEALTH' }],
    readProfileLink: async () => ({ member_id: member, source_member_id: 'source', family_id: 'family' }),
    listMealPlans: async id => { calls.push(['list', id]); return { plans: [plan(), plan('second')], truncated: false } },
    readMealPlan: async id => { calls.push(['read', id]); return detail(id) },
    listPublishedRecipes: async query => { calls.push(['recipes', query]); return [recipe(), recipe('other')] },
    listRecipePortions: async id => { calls.push(['portions', id]); return [portion(id)] },
    previewMealPlan: async (id, spec) => { calls.push(['preview', id, copy(spec)]); return { ...snapshot(spec), member_id: id, preview_id: 'preview' } },
    saveMealPlan: async (id, data) => { calls.push(['save', id, copy(data)]); return plan('saved') },
    swapMealPlan: async (id, data) => { calls.push(['swap', id, copy(data)]); return plan(id, 2) },
    ...overrides,
  }
  // 即便客户端存在这些能力，普通业务也不能触碰它们。
  for (const name of ['setConsultationConsent', 'grantMemberScope', 'submitConsultationRequest', 'createMealPlanner']) {
    Object.defineProperty(client, name, { get: () => { assert.fail(`普通餐单访问了${name}`) } })
  }
  const controller = createMealPlanController({ client, newId: () => `00000000-0000-4000-8000-${String(++serial).padStart(12, '0')}`, ...options })
  return { controller, client, calls, serial: () => serial,
    changeSession(next) { session = next; client.sessionRevision += 1; listener?.(next) } }
}
async function draft(context) {
  await context.controller.show(member); context.controller.setDate('2026-10-10')
  for (const meal of meals) await context.controller.setDish(meal, 0, { recipe_version_id: 'recipe' })
}
async function preview(context) { await draft(context); await context.controller.preview() }
async function swap(context) {
  await context.controller.show(member); await context.controller.selectPlan('plan'); context.controller.startSwap('lunch', 0)
  await context.controller.setSwap({ replacement: { recipe_version_id: 'other' }, reason: '合成换菜原因' })
}

test('进入只读取真实本人、关联和普通业务目录；未默认日期份量目标，也不自动保存', async () => {
  const context = setup(); await context.controller.show(member)
  const state = context.controller.getState()
  assert.equal(state.blocked, false); assert.equal(state.draft.plan_date, '')
  assert.equal(state.draft.meals[0].dishes[0].grams, ''); assert.equal(state.currentPlan, null)
  assert.deepEqual(context.calls.map(row => row[0]).sort(), ['list', 'recipes'])
  assert.equal(JSON.stringify(state).includes('SECRET'), false)
  state.draft.meals[0].dishes[0].grams = '444'
  assert.equal(context.controller.getState().draft.meals[0].dishes[0].grams, '')
  context.controller.dispose()
})

test('非本人、owner不匹配、每项入口权限缺失和未关联均在读取餐单前拒绝', async () => {
  const normal = { id: member, is_owner: true, relationship_label: '本人', scopes: ['profile_view', 'profile_edit', 'diet_edit'] }
  const cases = [{ listHealthMembers: async () => [{ ...normal, is_owner: false }] },
    { listHealthMembers: async () => [{ ...normal, relationship_label: '家人' }] },
    ...normal.scopes.map(scope => ({ listHealthMembers: async () => [{ ...normal, scopes: normal.scopes.filter(row => row !== scope) }] })),
    { readProfileLink: async () => ({ member_id: member, family_id: 'family', source_member_id: null }) },
    { readProfileLink: async () => ({ member_id: 'other', family_id: 'family', source_member_id: 'source' }) }]
  for (const overrides of cases) {
    const context = setup(overrides); await context.controller.show(member); await context.controller.preview(); await context.controller.save()
    assert.equal(context.controller.getState().blocked, true); assert.deepEqual(context.calls, []); context.controller.dispose()
  }
})

test('列表截断和家庭unsupported可见但不读取多人快照；个体化单成员只能阅读', async () => {
  const context = setup({ listMealPlans: async () => ({ truncated: true, plans: [
    { ...plan('family'), scope: 'family_recipe_draft', members: { another: { health: 'SECRET_HEALTH' } } },
    { ...plan('personal'), personalized: true },
  ] }), readMealPlan: async id => ({ ...detail(id), personalized: true }) })
  await context.controller.show(member); await context.controller.selectPlan('family')
  assert.equal(context.controller.getState().truncated, true); assert.match(context.controller.getState().notice, /后台/)
  assert.equal(context.controller.getState().currentPlan, null)
  assert.equal(context.calls.some(row => row[0] === 'read'), false)
  assert.equal(JSON.stringify(context.controller.getState()).includes('SECRET'), false)
  await context.controller.selectPlan('personal'); context.controller.startSwap('lunch', 0); await context.controller.confirmSwap()
  assert.equal(context.controller.getState().currentPlan.editable, false); assert.equal(context.controller.getState().swap, null)
  context.controller.dispose()
})

test('三餐1到10菜明确选目录和份量，未知允许但零输入不当未知；仅服务端数值进入预览', async () => {
  const context = setup(); await draft(context)
  context.controller.removeDish('breakfast', 0); assert.equal(context.controller.getState().draft.meals[0].dishes.length, 1)
  for (let index = 1; index <= 10; index += 1) context.controller.addDish('breakfast')
  assert.equal(context.controller.getState().draft.meals[0].dishes.length, 10)
  for (let index = 9; index > 0; index -= 1) context.controller.removeDish('breakfast', index)
  await context.controller.setDish('lunch', 0, { portion_mode: 'grams', grams: '0' }); await context.controller.preview()
  assert.equal(context.calls.some(row => row[0] === 'preview'), false); assert.match(context.controller.getState().error, /大于0/)
  await context.controller.setDish('lunch', 0, { portion_mode: 'unknown' })
  await context.controller.setDish('dinner', 0, { portion_mode: 'reference', portion_reference_id: 'portion-recipe', portion_count: '1.000' })
  await context.controller.preview()
  const request = context.calls.find(row => row[0] === 'preview')[2]
  assert.deepEqual(request.meals[0].dishes[0], { recipe_version_id: 'recipe' })
  assert.deepEqual(request.meals[2].dishes[0], { recipe_version_id: 'recipe', portion_reference_id: 'portion-recipe', portion_count: '1.000' })
  assert.equal(context.controller.getState().preview.nutrition.totals.sodium_mg, '0')
  assert.equal(context.controller.getState().preview.nutrition.totals.carbohydrate_g, null)
  assert.equal(context.controller.getState().preview.nutrition.totals.energy_kcal, '111.25')
  assert.equal(context.calls.some(row => row[0] === 'save'), false); context.controller.dispose()
})

test('空发布目录显示空态，不能构造演示菜品或发送预览', async () => {
  const context = setup({ listPublishedRecipes: async () => [] }); await context.controller.show(member)
  context.controller.setDate('2026-10-10'); await context.controller.setDish('breakfast', 0, { recipe_version_id: 'unpublished' })
  await context.controller.preview(); assert.deepEqual(context.controller.getState().recipes, [])
  assert.equal(context.calls.some(row => row[0] === 'preview'), false); assert.equal(context.controller.getState().draft.meals[0].dishes[0].recipe_version_id, '')
  context.controller.dispose()
})

test('预览必须属于发出的本人日期、三餐菜谱版本及菜数，串包不能成为可保存回执', async () => {
  const changes = [value => { value.member_id = 'other-member' }, value => { value.plan_date = '2026-10-11' },
    value => { value.meals[0].dishes[0].recipe_version_id = 'other' }, value => { value.meals[0].dishes.push({ ...value.meals[0].dishes[0], dish_index: 1 }) }]
  for (const change of changes) {
    const context = setup({ previewMealPlan: async (id, spec) => {
      const value = { ...snapshot(spec), member_id: id, preview_id: 'wrong-preview' }; change(value); return value
    } })
    await preview(context); await context.controller.save()
    assert.equal(context.controller.getState().blocked, true); assert.equal(context.controller.getState().preview, null)
    assert.equal(context.serial(), 0); context.controller.dispose()
  }
})

test('用户不能将另一个已发布菜谱的份量参考用于当前菜谱，也不能以零数量提交', async () => {
  const context = setup(); await draft(context)
  await context.controller.setDish('lunch', 0, { portion_mode: 'reference', portion_reference_id: 'portion-other', portion_count: '1' })
  await context.controller.preview(); assert.match(context.controller.getState().error, /属于此菜谱版本/)
  await context.controller.setDish('lunch', 0, { portion_reference_id: 'portion-recipe', portion_count: '0' })
  await context.controller.preview(); assert.match(context.controller.getState().error, /大于0/)
  assert.equal(context.calls.some(row => row[0] === 'preview'), false); context.controller.dispose()
})

for (const status of [0, 500, 502, 503, 504]) {
  for (const operation of ['save', 'swap']) {
    test(`${operation}提交后${status}未知时冻结原包原UUID，显式重试只有一次最终业务写入`, async () => {
      const receipts = new Map(), authority = new Map(), posts = []
      let commits = 0, selectedSpec = null
      const post = async (id, body) => {
        posts.push([id, copy(body)])
        if (!receipts.has(body.client_request_id)) {
          commits += 1
          const result = operation === 'save' ? detail('saved', 1, selectedSpec) : detail(id, body.version + 1)
          authority.set(result.plan_id, result); receipts.set(body.client_request_id, { id, body: copy(body), planId: result.plan_id })
          throw failure(status)
        }
        const receipt = receipts.get(body.client_request_id)
        assert.deepEqual([id, body], [receipt.id, receipt.body])
        return copy(authority.get(receipt.planId))
      }
      const context = setup({ saveMealPlan: post, swapMealPlan: post,
        previewMealPlan: async (id, spec) => { selectedSpec = copy(spec); return { ...snapshot(spec), member_id: id, preview_id: 'preview' } },
        readMealPlan: async id => copy(authority.get(id) || detail(id)),
        listMealPlans: async () => ({ plans: authority.size ? [...authority.values()].map(copy) : [plan()], truncated: false }) })
      if (operation === 'save') await preview(context); else await swap(context)
      await (operation === 'save' ? context.controller.save() : context.controller.confirmSwap())
      assert.equal(context.controller.getState().writeUnknown, true); assert.equal(context.serial(), 1); assert.equal(commits, 1)
      const frozen = copy(context.controller.getState().draft), originalSwap = copy(context.controller.getState().swap)
      context.controller.setDate('2027-01-01'); await context.controller.setDish('breakfast', 0, { grams: '999' })
      context.controller.startSwap('dinner', 0); context.controller.setSwap({ reason: '换成另一意图' }); context.controller.cancelSwap()
      await context.controller.selectPlan('plan'); await context.controller.reload(); await context.controller.preview()
      await context.controller.save(); await context.controller.confirmSwap()
      assert.deepEqual(context.controller.getState().draft, frozen); assert.deepEqual(context.controller.getState().swap, originalSwap)
      assert.equal(posts.length, 1); assert.equal(context.serial(), 1)
      await (operation === 'save' ? context.controller.save(true) : context.controller.confirmSwap(true))
      assert.deepEqual(posts[0], posts[1]); assert.equal(commits, 1); assert.equal(receipts.size, 1); assert.equal(context.serial(), 1)
      assert.equal(context.controller.getState().writeUnknown, false); assert.equal(context.controller.getState().readBackPending, false)
      assert.equal(context.controller.getState().currentPlan.plan_id, operation === 'save' ? 'saved' : 'plan')
      assert.equal(context.controller.getState().history.length, operation === 'save' ? 1 : 2)
      await context.controller.save(); await context.controller.confirmSwap()
      assert.equal(posts.length, 2); context.controller.dispose()
    })
  }
}

test('幂等换菜回执可返回较新当前版本，按权威版本回读且不虚构applied_version', async () => {
  let calls = 0
  const context = setup({ swapMealPlan: async () => { if (++calls === 1) throw failure(0); return plan('plan', 3) },
    readMealPlan: async () => detail('plan', calls ? 3 : 1) })
  await swap(context); await context.controller.confirmSwap(); await context.controller.confirmSwap(true)
  assert.equal(context.controller.getState().currentPlan.version, 3)
  assert.equal(Object.hasOwn(context.controller.getState().currentPlan, 'applied_version'), false)
  assert.equal(context.controller.getState().history.length, 3); context.controller.dispose()
})

test('已确认POST后详情5xx冻结新操作，只允许GET读回，不产生第二个餐单或revision', async () => {
  let reads = 0, posts = 0
  const context = setup({ saveMealPlan: async () => { posts += 1; return plan('saved') },
    readMealPlan: async id => { if (++reads === 1) throw failure(503); return detail(id) } })
  await preview(context); await context.controller.save()
  assert.equal(context.controller.getState().writeUnknown, false); assert.equal(context.controller.getState().readBackPending, true)
  assert.match(context.controller.getState().notice, /写入已确认/)
  await context.controller.save(true); await context.controller.save(); context.controller.setDate('2026-12-01')
  assert.equal(posts, 1); assert.equal(context.serial(), 1); assert.equal(context.controller.getState().draft.plan_date, '2026-10-10')
  await context.controller.retryReadBack()
  assert.equal(posts, 1); assert.equal(context.controller.getState().currentPlan.plan_id, 'saved')
  assert.equal(context.controller.getState().readBackPending, false); context.controller.dispose()
})

test('已确认换菜后列表5xx只能GET恢复，下一次明确操作才生成新的UUID', async () => {
  let version = 1, lists = 0
  const posts = []
  const context = setup({ swapMealPlan: async (id, body) => { posts.push([id, copy(body)]); version += 1; return plan(id, version) },
    readMealPlan: async id => detail(id, version), listMealPlans: async () => {
      if (++lists === 2) throw failure(502)
      return { plans: [plan('plan', version)], truncated: false }
    } })
  await swap(context); await context.controller.confirmSwap()
  assert.equal(version, 2); assert.equal(context.controller.getState().readBackPending, true)
  await context.controller.confirmSwap(true); await context.controller.confirmSwap()
  assert.equal(posts.length, 1); await context.controller.retryReadBack(); assert.equal(posts.length, 1)
  context.controller.startSwap('breakfast', 0)
  await context.controller.setSwap({ replacement: { recipe_version_id: 'recipe' }, reason: '下一次明确选择' })
  await context.controller.confirmSwap()
  assert.equal(version, 3); assert.equal(posts.length, 2); assert.equal(context.serial(), 2)
  assert.notEqual(posts[0][1].client_request_id, posts[1][1].client_request_id)
  assert.equal(posts[1][1].version, 2); assert.equal(context.controller.getState().currentPlan.version, 3)
  context.controller.dispose()
})

test('409废弃原预览和待确认请求，要求重新读取并明确重选，旧操作不能新键重发', async () => {
  let posts = 0
  const context = setup({ swapMealPlan: async () => { posts += 1; throw failure(409) } })
  await swap(context); await context.controller.confirmSwap()
  assert.equal(context.controller.getState().needsReload, true); assert.equal(context.controller.getState().swap, null)
  assert.equal(context.controller.getState().currentPlan, null); assert.equal(context.controller.getState().preview, null)
  context.controller.startSwap('lunch', 0); await context.controller.confirmSwap(true); await context.controller.confirmSwap()
  assert.equal(posts, 1); assert.equal(context.serial(), 1)
  await context.controller.reload(); assert.equal(context.controller.getState().needsReload, false)
  assert.equal(context.controller.getState().currentPlan, null)
  await context.controller.selectPlan('plan'); context.controller.startSwap('lunch', 0)
  await context.controller.setSwap({ replacement: { recipe_version_id: 'other' }, reason: '明确重新换菜' })
  await context.controller.confirmSwap(); assert.equal(posts, 2); assert.equal(context.serial(), 2); context.controller.dispose()
})

test('历史快照独立只读，不替换当前版，不允许以历史版本开始换菜', async () => {
  const context = setup({ readMealPlan: async id => { const result = detail(id, 2); result.revisions[0].snapshot.meals[0].dishes[0].name = '旧版菜名'; return result } })
  await context.controller.show(member); await context.controller.selectPlan('plan'); context.controller.showHistory(1)
  assert.equal(context.controller.getState().currentPlan.version, 2)
  assert.equal(context.controller.getState().historySnapshot.meals[0].dishes[0].name, '旧版菜名')
  context.controller.startSwap('breakfast', 0); await context.controller.confirmSwap(); assert.equal(context.controller.getState().swap, null)
  context.controller.showHistory(null); context.controller.startSwap('breakfast', 0)
  assert.equal(context.controller.getState().swap.dish_index, 0); context.controller.dispose()
})

test('详情选择序号拒绝迟到旧正文，餐单ID错位立即清除全部私有状态', async () => {
  const old = deferred(), fresh = deferred()
  const context = setup({ readMealPlan: id => id === 'plan' ? old.promise : fresh.promise })
  await context.controller.show(member)
  const first = context.controller.selectPlan('plan'), second = context.controller.selectPlan('second')
  fresh.resolve(detail('second')); await second; old.resolve(detail('plan')); await first
  assert.equal(context.controller.getState().currentPlan.plan_id, 'second')
  const broken = setup({ readMealPlan: async () => detail('wrong-id') }); await broken.controller.show(member); await broken.controller.selectPlan('plan')
  assert.equal(broken.controller.getState().blocked, true); assert.equal(broken.controller.getState().currentPlan, null)
  assert.deepEqual(broken.controller.getState().plans, []); assert.equal(JSON.stringify(broken.controller.getState()).includes('SECRET'), false)
  context.controller.dispose(); broken.controller.dispose()
})

test('旧详情晚到403清除新详情，废弃epoch后其他并发目录结果不能回填', async () => {
  const denied = deferred(), catalog = deferred()
  const context = setup({ readMealPlan: id => id === 'plan' ? denied.promise : Promise.resolve(detail(id)),
    listPublishedRecipes: query => query ? catalog.promise : Promise.resolve([recipe()]) })
  await context.controller.show(member); const old = context.controller.selectPlan('plan')
  await context.controller.selectPlan('second'); const search = context.controller.searchRecipes('并发')
  denied.reject(failure(403)); await old; catalog.resolve([recipe('late')]); await search
  assert.equal(context.controller.getState().blocked, true); assert.deepEqual(context.controller.getState().recipes, [])
  assert.equal(context.controller.getState().currentPlan, null); assert.equal(context.controller.getState().member, null)
  context.controller.dispose()
})

test('账号切换或页面隐藏同步清除草稿与未知意图，迟到POST和GET不能回填', async () => {
  for (const mode of ['hide', 'account']) {
    const post = deferred(), context = setup({ saveMealPlan: () => post.promise }); await preview(context)
    const saving = context.controller.save()
    if (mode === 'hide') context.controller.hide(); else context.changeSession({ uid: 'other-uid', username: '另一个合成账号' })
    assert.equal(context.controller.getState().preview, null); assert.equal(context.controller.getState().writeUnknown, false)
    post.resolve(plan('saved')); await saving
    assert.equal(context.controller.getState().currentPlan, null); assert.equal(context.calls.some(row => row[0] === 'read'), false)
    assert.equal(context.controller.getState().draft.plan_date, ''); context.controller.dispose()
  }
  const read = deferred(), context = setup({ readMealPlan: () => read.promise }); await context.controller.show(member)
  const reading = context.controller.selectPlan('plan'); context.changeSession(null); read.resolve(detail()); await reading
  assert.equal(context.controller.getState().currentPlan, null); assert.equal(context.controller.getState().member, null); context.controller.dispose()
})

test('目录与预览拒迟到旧选择，公共份量按菜谱版本缓存并拒绝跨菜谱使用', async () => {
  const oldQuery = deferred(), newQuery = deferred(), firstPortion = deferred(), secondPortion = deferred(), delayedPreview = deferred()
  const context = setup({ listPublishedRecipes: query => query === 'old' ? oldQuery.promise : query === 'new' ? newQuery.promise : Promise.resolve([recipe(), recipe('other')]),
    listRecipePortions: id => id === 'recipe' ? firstPortion.promise : secondPortion.promise,
    previewMealPlan: () => delayedPreview.promise })
  await context.controller.show(member)
  const old = context.controller.searchRecipes('old'), fresh = context.controller.searchRecipes('new')
  newQuery.resolve([recipe(), recipe('other')]); await fresh; oldQuery.resolve([recipe('stale')]); await old
  assert.equal(context.controller.getState().recipes.some(row => row.id === 'stale'), false)
  const first = context.controller.setDish('breakfast', 0, { recipe_version_id: 'recipe' })
  const second = context.controller.setDish('breakfast', 0, { recipe_version_id: 'other' })
  secondPortion.resolve([portion('other')]); await second; firstPortion.resolve([portion('recipe')]); await first
  assert.equal(context.controller.getState().portions.recipe[0].recipe_version_id, 'recipe')
  assert.equal(context.controller.getState().portions.other[0].recipe_version_id, 'other')
  assert.equal(context.controller.getState().draft.meals[0].dishes[0].recipe_version_id, 'other')
  assert.equal(context.controller.getState().draft.meals[0].dishes[0].portion_reference_id, '')
  context.controller.setDate('2026-10-10')
  await context.controller.setDish('lunch', 0, { recipe_version_id: 'other' }); await context.controller.setDish('dinner', 0, { recipe_version_id: 'other' })
  const rendering = context.controller.preview(); const original = copy(context.controller.getState().draft)
  context.controller.setDate('2026-10-11'); delayedPreview.resolve({ ...snapshot(original), member_id: member, preview_id: 'preview' }); await rendering
  assert.equal(context.controller.getState().preview, null); assert.equal(context.controller.getState().draft.plan_date, '2026-10-11')
  context.controller.dispose()
  const broken = setup({ listRecipePortions: async () => [portion('wrong-version')] }); await broken.controller.show(member)
  await broken.controller.setDish('breakfast', 0, { recipe_version_id: 'recipe' })
  assert.equal(broken.controller.getState().blocked, true); assert.deepEqual(broken.controller.getState().portions, {}); broken.controller.dispose()
})

test('两个菜位并发读取同一菜谱参考，其中一位改选不丢另一位目录；旧请求不能覆盖新目录', async () => {
  const first = deferred(), second = deferred()
  let recipeReads = 0
  const context = setup({ listRecipePortions: id => id === 'recipe'
    ? (++recipeReads === 1 ? first.promise : second.promise) : Promise.resolve([portion('other')]) })
  await context.controller.show(member); context.controller.setDate('2026-10-10')
  const breakfast = context.controller.setDish('breakfast', 0, { recipe_version_id: 'recipe' })
  const lunchFirst = context.controller.setDish('lunch', 0, { recipe_version_id: 'recipe' })
  await context.controller.setDish('lunch', 0, { recipe_version_id: 'other' })
  second.resolve([portion('recipe')]); await lunchFirst
  assert.equal(context.controller.getState().portions.recipe?.[0]?.id, 'portion-recipe')
  first.resolve([{ ...portion('recipe'), id: 'late-old-reference' }]); await breakfast
  assert.equal(context.controller.getState().portions.recipe?.[0]?.id, 'portion-recipe')
  await context.controller.setDish('breakfast', 0, { portion_mode: 'reference', portion_reference_id: 'portion-recipe', portion_count: '1' })
  await context.controller.setDish('dinner', 0, { recipe_version_id: 'other' })
  await context.controller.preview()
  const request = context.calls.find(row => row[0] === 'preview')[2]
  assert.deepEqual(request.meals[0].dishes[0], { recipe_version_id: 'recipe', portion_reference_id: 'portion-recipe', portion_count: '1' })
  assert.equal(context.controller.getState().preview.meals[0].dishes[0].recipe_version_id, 'recipe')
  await context.controller.setDish('lunch', 0, { portion_mode: 'reference', portion_reference_id: 'portion-recipe', portion_count: '1' })
  await context.controller.preview()
  assert.match(context.controller.getState().error, /属于此菜谱版本/)
  assert.equal(context.calls.filter(row => row[0] === 'preview').length, 1)
  context.controller.dispose()
})

test('隐藏或切号废弃公共份量页epoch，旧参考请求不能重新填入目录', async () => {
  for (const mode of ['hide', 'account', 'revoked']) {
    const waiting = deferred(), context = setup({ listRecipePortions: () => waiting.promise,
      readMealPlan: async () => { throw failure(403) } })
    await context.controller.show(member)
    const reading = context.controller.setDish('breakfast', 0, { recipe_version_id: 'recipe' })
    if (mode === 'hide') context.controller.hide()
    else if (mode === 'account') context.changeSession({ uid: 'other-uid', username: '另一合成账号' })
    else await context.controller.selectPlan('plan')
    waiting.resolve([portion('recipe')]); await reading
    assert.deepEqual(context.controller.getState().portions, {}); assert.equal(context.controller.getState().member, null)
    context.controller.dispose()
  }
})

for (const status of [403, 404, 410]) {
  test(`${status}清空已保存正文、预览与内存写意图，不能重发`, async () => {
    const context = setup({ saveMealPlan: async () => { throw failure(status) } }); await preview(context)
    await context.controller.save(); await context.controller.save(true)
    assert.equal(context.controller.getState().blocked, true); assert.equal(context.controller.getState().preview, null)
    assert.deepEqual(context.controller.getState().history, []); assert.equal(context.controller.getState().member, null)
    assert.equal(context.serial(), 1); context.controller.dispose()
  })
}
