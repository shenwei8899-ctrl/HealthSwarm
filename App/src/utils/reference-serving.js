import { DISH_NUTRITION_FIELDS, normalizeDishNutrition } from './dish-nutrition.js'

export function referenceNutritionOptions(dish) {
  return [{ key: 'per100', label: '每100克', values: normalizeDishNutrition(dish?.nutrition) },
    { key: 'whole', label: '整道菜', values: dish?.nutrition_total?.basis === 'whole_dish' ? dish.nutrition_total : null },
    ...(dish?.member_servings || []).map(person => ({ key: person.member_id, label: person.name,
      values: person.nutrition?.basis === 'per_serving' ? person.nutrition : null }))]
}

export function referenceNutritionItems(option) {
  return DISH_NUTRITION_FIELDS.map(field => {
    const value = option?.values?.[field.key]
    const valid = typeof value === 'number' && Number.isFinite(value) && value >= 0
    const minimum = 10 ** -field.decimals
    return { ...field, available: valid, text: !valid ? '暂未核算' : value > 0 && value < minimum ? `<${minimum}` : value.toFixed(field.decimals) }
  })
}
