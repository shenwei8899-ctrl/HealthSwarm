const mealNames = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐' }
const dayMs = 86400000

export function archiveDate(value, now = new Date()) {
  const valid = typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
  const date = valid ? new Date(value + 'T00:00:00Z') : null
  if (!date || Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== value) {
    return { title: '日期待核对', caption: '已保存餐单' }
  }
  const today = new Date(now.getTime() + 8 * 3600000).toISOString().slice(0, 10)
  const distance = (new Date(today + 'T00:00:00Z').getTime() - date.getTime()) / dayMs
  const prefix = distance === 0 ? '今天' : distance === 1 ? '昨天' : value.slice(0, 4) + '年'
  return {
    title: `${Number(value.slice(5, 7))}月${Number(value.slice(8, 10))}日`,
    caption: `${prefix} · 周${'日一二三四五六'[date.getUTCDay()]}`,
  }
}

export function archiveMeals(plan) {
  const meals = Array.isArray(plan?.meals) ? plan.meals : []
  return Object.entries(mealNames).map(([type, name]) => {
    const meal = meals.find(row => row.meal_type === type)
    const dishes = (meal?.dishes || []).map(dish => dish.name).filter(Boolean)
    return { type, name, summary: dishes.join(' · ') || '本餐未记录' }
  })
}

export function archiveCard(plan, now) {
  const date = archiveDate(plan.plan_date, now)
  const recorded = new Set((plan.meals || []).map(row => row.meal_type).filter(type => mealNames[type]))
  const count = Object.keys(plan.members || {}).length
  const owner = count > 1 ? `${count}位成员` : '个人餐单'
  return {
    plan, date, title: date.title + (recorded.size === 3 ? '的三餐' : '的餐单'),
    meals: archiveMeals(plan), summary: owner + (recorded.size ? ` · ${recorded.size}餐` : ''),
  }
}

export function plannedGrams(value) {
  return value === null || value === undefined ? '份量未知' : `${value}g`
}
