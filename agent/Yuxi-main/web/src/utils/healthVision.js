/** 生成未识别、无虚构证据的人工报告字段。 */
export function newReportField() {
  return {
    field_id: crypto.randomUUID(),
    name: '',
    observation_code: 'unknown',
    value_raw: '',
    value_numeric: null,
    unit_raw: '',
    reference_raw: '',
    observed_at: null,
    fasting: 'unknown',
    source: 'manual',
    evidence: null,
    review_flags: [],
    excluded: false
  }
}

/** 克数和分食比例必须由用户明确填写，不能默认估重。 */
export function newMealItem() {
  return {
    item_id: crypto.randomUUID(),
    name: '',
    candidates: [],
    cooking_method: '未知',
    visible_ingredients: [],
    locations: [],
    uncertainties: [],
    food_id: null,
    recipe_version_id: null,
    grams: null,
    portion_reference_id: null,
    portion_count: null,
    share_ratio: null,
    portion_source: 'unknown',
    adjustments: [],
    excluded: false
  }
}

/** 数字显示保留未知值；未知不是零。 */
export function nutrientText(value, unit) {
  return value === null || value === undefined ? '未知' : `${value} ${unit}`
}

/** 避免依赖客户端隐式时区。 */
export function localDateTime() {
  const date = new Date()
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

export const nutrientLabels = {
  energy_kcal: ['能量', 'kcal'],
  protein_g: ['蛋白质', 'g'],
  fat_g: ['脂肪', 'g'],
  carbohydrate_g: ['碳水化合物', 'g'],
  sodium_mg: ['钠', 'mg']
}
export const mealLabels = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐' }

/** 健康角色由成员业务入口绑定，聊天页统一使用后台审批模型。 */
export function isHealthAgentId(id) {
  return [
    'health-consultation',
    'health-meal-planner',
    'health-diet-analyst',
    'health-quality'
  ].includes(id)
}
