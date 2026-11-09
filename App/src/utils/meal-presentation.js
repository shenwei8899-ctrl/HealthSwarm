export const mealTypes = ['breakfast', 'lunch', 'dinner']
export const mealLabels = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐' }

export function canPurchaseAllMeals(plan, visibleTypes = mealTypes) {
  if (plan?.status !== 'ready' || !mealTypes.every(type => visibleTypes.includes(type) &&
      plan.meals?.some(item => item.meal_type === type && Array.isArray(item.meal?.dishes) && item.meal.dishes.length))) return false
  return mealTypes.every(type => plan.meals.some(item => item.meal_type===type && item.purchase_ready!==false &&
    (plan.purchase_options || []).some(option => !option.gaps?.some(g=>g.reason!=='not_sold') &&
      option.kind === item.source?.kind && option.id === item.source?.id && option.meal_types?.includes(type))))
}

export function dishTitle(dish) {
  const name = String(dish?.display_zh?.name || dish?.display_name || dish?.name || dish?.recipe_name || '').trim()
  const parts = name.split(/\s*[|｜]\s*/)
  return parts.find(part => /[\u3400-\u9fff]/.test(part)) || (dish?.file_id && dish?.chunk_id ? '菜谱中文译文待补充' : name)
}

export function recipeDisplay(dish) {
  if (!dish) return { ingredients: [], steps: [] }
  const zh = dish.display_zh
  const valid = zh && zh.ingredients?.length === dish.ingredients?.length && zh.steps?.length === dish.steps?.length
  if (valid) return { ...dish, ...zh, name: dishTitle(dish) }
  if (!dish.file_id || !dish.chunk_id) return dish
  const text = value => typeof value === 'string' && /[a-z]{2,}/i.test(value.replace(/\b(?:kg|mg|ml|kcal|kj|cm|mm)\b/ig, '')) ? '中文译文暂未就绪' : value
  return { ...dish, name: dishTitle(dish), ingredients: (dish.ingredients || []).map(text), steps: (dish.steps || []).map(text),
    portion_quote: text(dish.portion_quote), nutrition_quote: text(dish.nutrition_quote) }
}

export function ingredientLabels(dishes = []) {
  return Object.fromEntries(dishes.flatMap(dish => (dish.ingredients || []).filter(i => typeof i === 'string')
    .map((original, index) => [original, recipeDisplay(dish).ingredients[index]])))
}

export function referenceIngredientLabel(labels, original) {
  return labels?.[original] || (/[a-z]{2,}/i.test(original || '') ? '食材中文译文待补充' : original)
}

export function referenceGapDetail(gap) {
  if (!/[a-z]{2,}/i.test(gap.detail || '')) return gap.detail
  return {no_match:'商城商品名中暂未找到对应食材。',needs_confirmation:'请核对具体品种、形态和用量。',
    not_sold:'此项无需在商城购买，请自行准备。',catalog_unavailable:'商品目录暂时无法读取，请稍后核对。'}[gap.reason] || '采购资料待核对。'
}

export function dishKey(dish) {
  return String(dish?.dish_key || dish?.id || dish?.recipe_ref || [dish?.file_id, dish?.chunk_id, dish?.name].filter(Boolean).join(':'))
}

export function mealNutrition(meal) {
  const values = meal?.nutrition || {}
  return [['kcal', '能量', '千卡'], ['protein', '蛋白质', '克']]
    .filter(([key]) => Number.isFinite(values[key]) && values[key] >= 0)
    .map(([key, label, unit]) => ({ key, label, unit, value: Math.round(values[key] * 10) / 10 }))
}

export function dishPortion(meal, dish) {
  const rows = (meal?.memberNotes || []).flatMap(member => (member.dishes || []).filter(row => String(row.dishId) === dishKey(dish)))
  if (rows.length && rows.every(row => Number.isFinite(row.grams))) return '本餐安排 ' + Math.round(rows.reduce((sum, row) => sum + row.grams, 0)) + ' 克'
  return recipeDisplay(dish)?.portion_quote || ''
}
