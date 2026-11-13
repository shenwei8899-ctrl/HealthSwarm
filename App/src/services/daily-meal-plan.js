import { request } from './request.js'
import { storageContext } from './storage.js'

const pendingByTransport = new WeakMap()

export function isCandidateMealPending(pending,familyId,date) {
  const text = value => typeof value === 'string' && value.trim().length > 0
  const selection = pending?.selection
  return pending?.status === 'reference_candidates' && text(pending.member_id) && text(pending.request_id) && text(pending.thread_id) &&
    selection?.mode === 'reference' && selection.family_id === familyId && selection.plan_date === date &&
    Array.isArray(selection.participant_ids) && selection.participant_ids.length > 0 && selection.participant_ids.every(text) &&
    new Set(selection.participant_ids).size === selection.participant_ids.length &&
    Array.isArray(selection.meal_types) && selection.meal_types.length > 0 &&
    selection.meal_types.every(type => ['breakfast','lunch','dinner'].includes(type)) && new Set(selection.meal_types).size === selection.meal_types.length
}

export function readDailyMealPlan(familyId, date, send = request, { fresh = false, scope } = {}) {
  const key = JSON.stringify([scope ?? (typeof uni === 'undefined' ? '' : storageContext()), familyId, date])
  let pending = pendingByTransport.get(send)
  if (!pending) {
    pending = new Map()
    pendingByTransport.set(send, pending)
  }
  const previous = pending.get(key)
  if (previous && !fresh) return previous.promise

  const entry = {}
  entry.promise = fetchDailyMealPlan(familyId, date, send).then(
    plan => entry.successor || plan,
    error => {
      if (entry.successor) return entry.successor
      throw error
    },
  ).finally(() => {
    if (pending.get(key) === entry) pending.delete(key)
  })
  if (previous) previous.successor = entry.promise
  pending.set(key, entry)
  return entry.promise
}

async function fetchDailyMealPlan(familyId, date, send) {
  const { data } = await send({ path: `/api/family/${encodeURIComponent(familyId)}/daily-meal-plans/${encodeURIComponent(date)}` })
  if (!data || data.date !== date || !['ready', 'absent', 'needs_regeneration'].includes(data.status) ||
      !Number.isInteger(data.version) || data.version < 0 || !Array.isArray(data.meals) ||
      (data.status === 'ready' && !data.meals.length) || (data.status !== 'ready' && data.meals.length) ||
      (data.needs_regeneration != null && (!Array.isArray(data.needs_regeneration) || data.needs_regeneration.some(t=>!['breakfast','lunch','dinner'].includes(t))))) {
    throw new Error('今日餐单返回不完整，请重新读取。')
  }
  const types = data.meals.map(item => item.meal_type)
  if (types.some(type => !['breakfast', 'lunch', 'dinner'].includes(type)) || new Set(types).size !== types.length ||
      data.meals.some(item => !item.source?.id || !item.meal || !Array.isArray(item.meal.dishes))) {
    throw new Error('今日餐单的餐次来源无法核对。')
  }
  if (data.pending?.status === 'reference_candidates' && !isCandidateMealPending(data.pending,familyId,date)) {
    throw new Error('待核对候选的请求资料不完整，请重新读取。')
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
