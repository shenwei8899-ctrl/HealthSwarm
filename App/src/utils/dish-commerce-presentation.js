import { recipeDisplay } from './meal-presentation.js'

export function mealPairingText(data, fallback = '餐单已更新。') {
  return typeof data?.pairing_summary === 'string' && data.pairing_summary.trim()
    ? data.pairing_summary.trim() : fallback
}

export function recipeTime(dish) {
  return Number.isInteger(dish?.cooking_minutes) && dish.cooking_minutes > 0
    ? `约 ${dish.cooking_minutes} 分钟 · 含备菜` : '制作时间待补充'
}

export function plainNutrition(value) {
  return typeof value === 'string' ? value.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').trim() : ''
}

export function ingredientCopy(item) {
  if (typeof item === 'string') return item
  if (!item || typeof item !== 'object') return ''
  const grams = item.planned_grams
  return [item.name, grams !== null && grams !== undefined && grams !== '' && Number.isFinite(Number(grams)) && Number(grams) >= 0 ? `${grams}g` : ''].filter(Boolean).join(' ')
}

export function recipeIngredients(dish) {
  const original = Array.isArray(dish?.ingredients) ? dish.ingredients : []
  const display = recipeDisplay(dish)
  const products = Array.isArray(dish?.ingredient_products) ? dish.ingredient_products : []
  return original.map((quote, index) => {
    // Bind only an exact recipe ingredient; never infer a SKU from a similar name.
    const product = typeof quote === 'string' ? products.find(p => p && Array.isArray(p.ingredient_refs) && p.ingredient_refs.includes(quote)) : null
    const label = ingredientCopy(display.ingredients?.[index] ?? quote)
    return { key: index, name: product?.product_name || label, image: typeof product?.image_url === 'string' ? product.image_url : '',
      skuId: product?.sku_id ?? '', amount: label }
  })
}

export function recipeNutrition(dish) {
  const products = Array.isArray(dish?.ingredient_products) ? dish.ingredient_products : []
  const highlights = Array.isArray(dish?.nutrition_highlights) ? dish.nutrition_highlights : []
  const ingredients = Array.isArray(dish?.ingredients) ? dish.ingredients : []
  return highlights.flatMap(item => {
    if (!item || item.sku_id == null) return []
    const product = products.find(p => p?.sku_id != null && String(p.sku_id) === String(item.sku_id) &&
      Array.isArray(p.ingredient_refs) && p.ingredient_refs.some(ref => typeof ref === 'string' && ingredients.includes(ref)))
    const quote = plainNutrition(item.quote)
    return product && quote ? [{ name: product.product_name || '', skuId: product.sku_id, quote }] : []
  })
}
