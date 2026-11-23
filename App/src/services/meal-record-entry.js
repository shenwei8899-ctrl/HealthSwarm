import { captureMenuDishes } from './capture-menu.js'
import { dishKey } from '../utils/meal-presentation.js'

/** Carry a candidate, never the menu's planned intake or a purchase requirement. */
export function mealRecordEntry(target, dish, cover = '') {
  const kind = target.kind === 'reference' ? 'reference' : 'arrangement'
  const { dishes } = captureMenuDishes({ meals: [{ meal_type: target.mealType,
    source: { kind }, meal: { dishes: [dish] } }] }, target.mealType)
  if (!dishes.length) throw new Error('当前菜品尚不可带入，请手动记餐。')
  return { key: JSON.stringify([target.familyId, target.date, target.sourceId,
    target.version, target.dailyPlanVersion, dishKey(dish)]), dishes, cover,
    sourceContext: { family_id: target.familyId, plan_date: target.date,
      plan_version: target.dailyPlanVersion, meal_type: target.mealType, dish_key: dishKey(dish) } }
}

export function captureUiKey(entryKey = '') {
  return entryKey ? 'cloud-capture-ui:entry:' + entryKey : 'cloud-capture-ui'
}

export function mealTime(value) {
  const n = Date.parse(value)
  return Number.isFinite(n) ? new Date(n + 8 * 3600000).toISOString().slice(11, 16) : '时间未知'
}

export function sortMealRecords(records) {
  return [...records].sort((a, b) => (Date.parse(a.snapshot.meal.eaten_at) || 0) -
    (Date.parse(b.snapshot.meal.eaten_at) || 0) || String(a.id).localeCompare(String(b.id)))
}
