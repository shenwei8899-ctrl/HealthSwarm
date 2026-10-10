export const MEAL_TYPES = ['breakfast', 'lunch', 'dinner']
export const MEAL_SCOPES = ['profile_view', 'profile_edit', 'diet_edit']
export const NUTRIENT_LABELS = {
  energy_kcal: ['能量', 'kcal'], protein_g: ['蛋白质', 'g'], fat_g: ['脂肪', 'g'],
  carbohydrate_g: ['碳水化合物', 'g'], sodium_mg: ['钠', 'mg'],
}

function invalid(message) { return Object.assign(new Error(message), { code: 'protocol_mismatch' }) }
const text = value => typeof value === 'string' ? value : ''
function required(value, label) {
  if (typeof value !== 'string' || !value) throw invalid(`服务未返回可核对的${label}`)
  return value
}
function version(value) {
  if (!Number.isSafeInteger(value) || value < 1) throw invalid('餐单版本无效，请重新读取')
  return value
}
/** 服务端未知量保留为空，已知零值保留原值；客户端不进行营养计算。 */
function quantity(value) {
  if (value === null || value === undefined) return null
  if (!['string', 'number'].includes(typeof value)
    || (typeof value === 'string' && !/^\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(value))
    || !Number.isFinite(Number(value)) || Number(value) < 0) throw invalid('服务返回的营养或份量数值无效')
  return value
}
function nutrients(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw invalid('服务未返回营养数值结构')
  return Object.fromEntries(Object.keys(NUTRIENT_LABELS).map(key => [key, quantity(value[key])]))
}
function nutrition(value) {
  if (!value || typeof value.complete !== 'boolean') throw invalid('服务未返回营养完整性状态')
  return { totals: nutrients(value.totals), complete: value.complete, estimated: value.estimated === true,
    calculation_version: text(value.calculation_version) }
}

/** 本人身份与入口权限只改善体验，最终授权仍由业务服务校验。 */
export function mealPlanMember(rows, memberId) {
  const row = (Array.isArray(rows) ? rows : []).find(item => item?.id === memberId)
  if (!row || row.is_owner !== true || row.relationship_label !== '本人'
    || !Array.isArray(row.scopes) || !MEAL_SCOPES.every(scope => row.scopes.includes(scope))) {
    throw invalid('当前账号没有此本人成员的档案与饮食权限，请返回核对')
  }
  return { id: memberId, display_name: text(row.display_name) || '本人', scopes: [...MEAL_SCOPES] }
}

export function mealPlanLink(value, memberId) {
  if (value?.member_id !== memberId || !value.family_id || !value.source_member_id) {
    throw invalid('尚未核对真实本人关联，请返回本人成员接入页')
  }
  return { member_id: memberId, family_id: required(value.family_id, '家庭关联'),
    source_member_id: required(value.source_member_id, '家庭成员关联') }
}

/** 列表只保留索引；家庭多人快照和健康来源不会进入小程序内存。 */
export function mealPlanSummary(value, memberId) {
  if (value?.member_id !== memberId) throw invalid('餐单与当前本人成员不一致')
  const supported = value.scope === 'single_member_recipe_draft' && !Object.hasOwn(value, 'members')
  if (supported && typeof value.personalized !== 'boolean') throw invalid('服务未返回餐单个体适配边界')
  return { plan_id: required(value.plan_id, '餐单标识'), member_id: memberId, version: version(value.version),
    plan_date: required(value.plan_date, '计划日期'), updated_at: text(value.updated_at), supported,
    personalized: supported ? value.personalized : null, editable: supported && value.personalized === false,
    notice: supported ? '' : '家庭或其他餐单类型请在后台查看；此页面仅支持本人单成员餐单。' }
}

export function mealPlanList(value, memberId) {
  if (!Array.isArray(value?.plans) || typeof value.truncated !== 'boolean') throw invalid('服务未返回餐单列表与截断状态')
  const plans = value.plans.map(row => mealPlanSummary(row, memberId))
  if (new Set(plans.map(row => row.plan_id)).size !== plans.length) throw invalid('餐单列表存在重复标识')
  return { plans, truncated: value.truncated }
}

/** 白名单展示实际菜品、原料与服务端数值，不投影病历、模型或审核内部记录。 */
export function mealPlanSnapshot(value) {
  if (value?.scope !== 'single_member_recipe_draft' || Object.hasOwn(value, 'members')
    || value.status !== 'draft' || typeof value.personalized !== 'boolean'
    || !Array.isArray(value.meals) || value.meals.length !== 3) throw invalid('服务未返回可读取的单成员餐单草稿')
  const meals = MEAL_TYPES.map(mealType => {
    const matching = value.meals.filter(meal => meal?.meal_type === mealType)
    if (matching.length !== 1 || !Array.isArray(matching[0].dishes)
      || matching[0].dishes.length < 1 || matching[0].dishes.length > 10) throw invalid('餐单须包含完整且唯一的三餐菜品')
    const meal = matching[0]
    return { meal_type: mealType, nutrition: nutrition(meal.nutrition), dishes: meal.dishes.map((dish, index) => {
      if (dish?.dish_index !== index || !Array.isArray(dish.ingredients)) throw invalid('菜品位置或原料结构无法核对')
      return { dish_index: index, name: required(dish.name, '菜名'),
        recipe_version_id: required(dish.recipe_version_id, '菜谱版本'), planned_grams: quantity(dish.planned_grams),
        portion_source: text(dish.portion_source), cooking_state: text(dish.cooking_state),
        source: text(dish.source), license: text(dish.license), edition: text(dish.edition), dataset_version: text(dish.dataset_version),
        nutrition: nutrients(dish.nutrition), ingredients: dish.ingredients.map(ingredient => ({
          name: required(ingredient?.name, '原料名称'), food_id: required(ingredient.food_id, '原料版本'),
          role: text(ingredient.role), planned_grams: quantity(ingredient.planned_grams),
        })) }
    }) }
  })
  return { status: 'draft', scope: value.scope, personalized: value.personalized,
    editable: value.personalized === false, plan_date: required(value.plan_date, '计划日期'), meals,
    nutrition: nutrition(value.nutrition), professional_review: text(value.professional_review),
    notice: text(value.notice), adoption_available: false, purchase_available: false }
}

export function mealPlanPreview(value, memberId) {
  if (value?.member_id !== memberId || value.personalized !== false) throw invalid('预览与本人普通草稿不一致')
  return { preview_id: required(value.preview_id, '预览标识'), member_id: memberId, ...mealPlanSnapshot(value) }
}

/** 保存与换菜返回当前版本，不假定存在 applied_version 等客户端收据字段。 */
export function mealPlanResult(value, memberId, planId = null) {
  const summary = mealPlanSummary(value, memberId)
  if (!summary.supported || (planId !== null && summary.plan_id !== planId)) throw invalid('返回餐单与选定餐单不一致')
  return { ...summary, ...mealPlanSnapshot(value) }
}

export function mealPlanDetail(value, memberId, planId) {
  const plan = mealPlanResult(value, memberId, planId)
  if (!Array.isArray(value.revisions)) throw invalid('服务未返回餐单修订历史')
  const history = value.revisions.map(row => ({ version: version(row?.version), reason: text(row.reason),
    created_at: text(row.created_at), snapshot: { ...mealPlanSnapshot(row.snapshot), editable: false } }))
  if (new Set(history.map(row => row.version)).size !== history.length
    || history.some(row => row.version > plan.version)
    || !history.some(row => row.version === plan.version)) throw invalid('当前餐单与修订历史无法核对')
  return { plan, history }
}

export function publishedRecipes(value) {
  if (!Array.isArray(value)) throw invalid('服务未返回已发布菜谱目录')
  const rows = value.map(row => ({ id: required(row?.id, '已发布菜谱版本'), name: required(row.name, '菜谱名称'),
    yield_grams: quantity(row.yield_grams), cooking_state: text(row.cooking_state), source: text(row.source),
    license: text(row.license), edition: text(row.edition), dataset_version: text(row.dataset_version),
    ingredients: (Array.isArray(row.ingredients) ? row.ingredients : []).map(ingredient => ({
      name: required(ingredient?.food?.name, '菜谱原料'), role: text(ingredient.role), grams: quantity(ingredient.grams),
    })) }))
  if (new Set(rows.map(row => row.id)).size !== rows.length) throw invalid('发布目录存在重复菜谱版本')
  return rows
}

export function recipePortions(value, recipeVersionId) {
  if (!Array.isArray(value)) throw invalid('服务未返回份量参考目录')
  const rows = value.map(row => {
    if (row?.recipe_version_id !== recipeVersionId || row.food_id) throw invalid('份量参考不属于所选菜谱版本')
    const grams = quantity(row.grams_per_unit)
    if (grams === null || Number(grams) <= 0) throw invalid('发布份量参考克数无效')
    return { id: required(row.id, '份量参考标识'), recipe_version_id: recipeVersionId,
      unit_label: required(row.unit_label, '份量单位'), grams_per_unit: grams, source: text(row.source),
      license: text(row.license), edition: text(row.edition), dataset_version: text(row.dataset_version),
      applicable_scope: text(row.applicable_scope) }
  })
  if (new Set(rows.map(row => row.id)).size !== rows.length) throw invalid('发布目录存在重复份量参考')
  return rows
}
