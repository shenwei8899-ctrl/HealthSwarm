import { request } from './request.js'

export async function readDailyMealPlan(familyId, date, send = request) {
  const { data } = await send({ path: `/api/family/${encodeURIComponent(familyId)}/daily-meal-plans/${encodeURIComponent(date)}` })
  if (!data || data.date !== date || !['ready', 'absent'].includes(data.status) ||
      !Number.isInteger(data.version) || data.version < 0 || !Array.isArray(data.meals) ||
      (data.status === 'ready' && !data.meals.length) || (data.status === 'absent' && data.meals.length)) {
    throw new Error('今日饮食计划返回不完整，请重新读取。')
  }
  const types = data.meals.map(item => item.meal_type)
  if (types.some(type => !['breakfast', 'lunch', 'dinner'].includes(type)) || new Set(types).size !== types.length ||
      data.meals.some(item => !item.source?.id || !item.meal || !Array.isArray(item.meal.dishes))) {
    throw new Error('今日饮食计划的餐次来源无法核对。')
  }
  return data
}

export function mealQuestionAction(text) {
  const value = String(text || '').trim()
  if (/换(?:个|一个)?话题|换个问题/.test(value)) return 'consultation'
  if (/(换|替换|调整|改成|改为|重新安排)/.test(value) && /(餐|菜|吃)/.test(value)) return 'change'
  if (/(查看|看看|看一下|看下|查一下)/.test(value) && /(餐单|菜单|饮食计划|今日安排)/.test(value)) return 'view'
  if (/安排.*(餐|吃)|吃什么|明天早餐|今晚.*吃|三餐|餐单|菜单|推荐.*(菜|食谱)/.test(value)) return 'generate'
  return 'consultation'
}
