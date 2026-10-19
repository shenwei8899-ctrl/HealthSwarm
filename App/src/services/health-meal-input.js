/** 空白保持未知；服务端继续拥有营养与来源校验。 */
export function mealInput(value) {
  const meal = JSON.parse(JSON.stringify(value))
  for (const item of meal.items) {
    for (const field of ['grams', 'share_ratio', 'portion_count']) {
      if (item[field] === '' || item[field] === undefined) item[field] = null
    }
  }
  return meal
}
