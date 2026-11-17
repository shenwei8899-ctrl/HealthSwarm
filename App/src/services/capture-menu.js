import { dishTitle } from '../utils/meal-presentation.js'

/** 餐单只提供候选菜和准确配方版本，实际份量由用户核对。 */
export function captureMenuDishes(plan, mealType) {
  if (mealType === 'snack') return { dishes: [], notice: '今日餐单暂不包含加餐，请手动填写实际吃过的食物。' }
  if (plan.needs_regeneration?.includes(mealType)) return { dishes: [], notice: '本餐餐单已失效，请先在今日餐单中更新，或手动填写。' }
  const item = plan.meals.find(row => row.meal_type === mealType)
  if (!item?.meal.dishes.length) {
    const generating = plan.pending && !['failed', 'cancelled', 'rejected', 'interrupted', 'completed'].includes(plan.pending.status)
    return { dishes: [], notice: generating ? '本餐餐单正在准备，请稍后重试，或手动填写。' : '还没有本餐食谱，可以直接填写吃过的菜。' }
  }
  const dishes = new Map()
  for (const dish of item.meal.dishes) {
    const name = dishTitle(dish)
    if (!name || name === '菜谱中文译文待补充') throw new Error('本餐菜名尚未就绪，请更新今日餐单或手动填写。')
    const recipe = item.source.kind === 'reference' ? null : dish.recipeVersion || dish.recipe_version_id
    const recipeId = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(recipe || '') ? recipe : null
    const previous = dishes.get(name)
    // 记餐器按菜名选菜，同名不同来源不得继承其中一份配方。
    dishes.set(name, { name, recipe_version_id: previous && previous.recipe_version_id !== recipeId ? null : recipeId,
      grams: null, portion_source: 'unknown', portion_confirmed: false })
  }
  return { dishes: [...dishes.values()], notice: '请勾选实际吃过的菜，再核对本人份量；餐单建议份量不会自动记为摄入。' }
}
