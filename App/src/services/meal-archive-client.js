import { request } from './request.js'
import { getSession } from './session.js'
import { storageContext } from './storage.js'

export function mealArchiveState() {
  return { plans: [], plan: null, nextBefore: null, busy: false, error: '' }
}

/** 日期归档只读；页面隐藏或账号家庭变化后丢弃迟到的响应。 */
export function createMealArchiveClient({ state, send = request, session = getSession, context = storageContext }) {
  let generation = 0
  function discard({ keepList = false } = {}) {
    generation++
    const list = keepList ? { plans: state.plans, nextBefore: state.nextBefore } : {}
    Object.assign(state, mealArchiveState(), list)
  }
  async function read(date, append = false) {
    if (state.busy) return
    const mine = generation, identity = context(), family = session()?.householdId
    const current = () => mine === generation && identity === context()
    state.busy = true; state.error = ''
    if (date) state.plan = null
    try {
      if (!family) throw new Error('请先登录并加入家庭，再查看餐单。')
      const root = `/api/family/${encodeURIComponent(family)}/daily-meal-plans`
      const path = date ? `${root}/${encodeURIComponent(date)}/archive`
        : `${root}?limit=20${append && state.nextBefore ? '&before=' + encodeURIComponent(state.nextBefore) : ''}`
      const { data } = await send({ path })
      if (!current()) return
      const valid = plan => plan?.family_id === family && /^\d{4}-\d{2}-\d{2}$/.test(plan.plan_date || '') &&
        Number.isInteger(plan.version) && plan.version > 0 && Array.isArray(plan.meals) && plan.meals.length > 0 &&
        plan.meals.every(meal => ['breakfast','lunch','dinner'].includes(meal.meal_type) && Array.isArray(meal.dishes))
      if (date) {
        if (!valid(data) || data.plan_date !== date) throw new Error('餐单日期或家庭无法核对，请重新读取。')
        state.plan = data
      } else {
        if (!Array.isArray(data?.plans) || !data.plans.every(valid) ||
            data.next_before != null && !/^\d{4}-\d{2}-\d{2}$/.test(data.next_before)) throw new Error('餐单列表返回不完整，请重新读取。')
        state.plans = append ? [...new Map([...state.plans, ...data.plans].map(plan => [plan.plan_date, plan])).values()] : data.plans
        state.nextBefore = data.next_before ?? null
      }
    } catch (error) {
      if (!current()) return
      if ([401,403,404,410].includes(Number(error.code))) { state.plan = null; state.plans = []; state.nextBefore = null }
      state.error = error.message || '餐单暂时无法读取，请重试。'
    } finally {
      if (current()) state.busy = false
      else if (mine === generation) discard()
    }
  }
  return { discard, list: (append = false) => read(null, append), detail: date => read(date) }
}
