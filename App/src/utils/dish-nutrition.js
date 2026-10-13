// Recipe-level nutrition. Values describe 100 g of cooked edible food, not a
// purchased package, raw ingredient weight, the entire meal or personal intake.
export const DISH_NUTRITION_FIELDS = Object.freeze([
  { key: 'energyKcal', label: '能量', unit: 'kcal', decimals: 0 },
  { key: 'proteinG', label: '蛋白质', unit: 'g', decimals: 1 },
  { key: 'fatG', label: '脂肪', unit: 'g', decimals: 1 },
  { key: 'carbohydrateG', label: '碳水化合物', unit: 'g', decimals: 1 },
  { key: 'fiberG', label: '膳食纤维', unit: 'g', decimals: 1 },
  { key: 'sodiumMg', label: '钠', unit: 'mg', decimals: 0 },
])

const sources = ['demo', 'calculated', 'measured']

export function normalizeDishNutrition(value) {
  const usable = value?.basis === 'per_100g' && value?.foodState === 'cooked_edible' && sources.includes(value?.source)
  const result = {
    basis: 'per_100g', foodState: 'cooked_edible',
    source: usable ? value.source : 'unavailable',
    sourceReference: usable && typeof value.sourceReference === 'string' ? value.sourceReference : null,
  }
  for (const { key } of DISH_NUTRITION_FIELDS) {
    const number = usable ? value[key] : null
    result[key] = typeof number === 'number' && Number.isFinite(number) && number >= 0 ? number : null
  }
  return result
}

export function dishNutritionItems(value) {
  const nutrition = normalizeDishNutrition(value)
  return DISH_NUTRITION_FIELDS.map(field => {
    const number = nutrition[field.key]
    const minimum = 10 ** -field.decimals
    return {
      ...field, available: number !== null,
      text: number === null ? '暂无数据' : number > 0 && number < minimum ? `<${minimum}` : number.toFixed(field.decimals),
    }
  })
}
