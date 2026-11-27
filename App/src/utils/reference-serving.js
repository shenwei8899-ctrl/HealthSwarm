import { DISH_NUTRITION_FIELDS } from './dish-nutrition.js'

export function referenceNutritionItems(dish) {
  const total = dish?.nutrition_total
  const values = total?.basis === 'whole_dish' && total.quantity_basis === 'source_recipe' ? total : null
  return DISH_NUTRITION_FIELDS.map(field => {
    const value = values?.[field.key]
    const valid = typeof value === 'number' && Number.isFinite(value) && value >= 0
    const minimum = 10 ** -field.decimals
    return { ...field, available: valid, text: !valid ? '暂未核算' : value > 0 && value < minimum ? `<${minimum}` : value.toFixed(field.decimals) }
  })
}
