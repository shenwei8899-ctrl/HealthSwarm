import { callApiAdapter } from './index.js'
import { isMockMode } from './config.js'
import { storageContext } from './storage.js'
import { createPlan, getMealMembers } from '../utils/demo.js'
import { getProfile } from '../utils/profile.js'
import { applyMealCustomization, getMealSwap } from '../utils/meal-customization.js'
import { mealProfile, todayPlan, localDate, activePlanOrder } from '../utils/meal-state.js'
import { mealContext, planningMembers } from '../utils/meal-context.js'
import { memberAge } from '../utils/member-age.js'
import { normalizeMealResult } from '../utils/meal-result.js'
import { mealPlanKey, readMealResult, writeMealResult, MEAL_RULE_VERSION } from '../utils/meal-plan-store.js'

const pending = new Map()
const latest = new Map()
export async function ensureMealPlan(profile, meal, { date = localDate(), force = false, mode = isMockMode ? 'mock' : 'api' } = {}) {
  const scoped = mealProfile(profile, meal, date), swap = getMealSwap(meal)
  const key = mealPlanKey(scoped, meal, date, swap)
  const currentScope = storageContext(), taskKey = currentScope + ':' + mode + ':' + key
  const slot=currentScope+':'+date+':'+meal
  const cached = readMealResult(date, meal, key)
  if (!force && cached?.sourceType === (mode === 'mock' ? 'demo' : 'api')) return todayPlan(profile, meal, date)
  if (pending.has(taskKey)) return pending.get(taskKey)
  latest.set(slot,taskKey)
  const liveKey=mealPlanKey(mealProfile(getProfile(),meal,date),meal,date,swap)
  const task = (async () => {
    const members = planningMembers(getMealMembers(scoped), profile.viewerAccount).map(member => ({ ...member, age: memberAge(member, date).years, ageMonths: memberAge(member, date).months }))
    const input = { clientRequestId: 'meal-' + Date.now() + '-' + Math.random().toString(36).slice(2), ruleVersion: MEAL_RULE_VERSION, date, meal, members,
      goals: profile.goals || [], tastes: profile.tastes || [], context: mealContext(date).filter(message=>message.memberId===null||members.some(member=>member.id===message.memberId)), swap,
      // Re-evaluate eating advice against purchased recipes, preserving fulfillment.
      paidOrder: activePlanOrder(date) ? { id: activePlanOrder(date).id, cookingGuides: activePlanOrder(date).cookingGuides } : null }
    let plan
    if (mode === 'mock') plan = applyMealCustomization(createPlan(scoped, meal, date), swap)
    else plan = normalizeMealResult(await callApiAdapter('generateMealPlan', input), input)
    if (currentScope !== storageContext() || latest.get(slot)!==taskKey || liveKey!==mealPlanKey(mealProfile(getProfile(),meal,date),meal,date,getMealSwap(meal)) || key !== mealPlanKey(mealProfile(profile, meal, date), meal, date, getMealSwap(meal))) throw Object.assign(new Error('本餐依据已变化，请重新分析'), { code: 'STALE_MEAL_REQUEST' })
    writeMealResult(date, meal, key, plan)
    return todayPlan(profile, meal, date)
  })()
  pending.set(taskKey, task)
  try { return await task } finally { pending.delete(taskKey) }
}
