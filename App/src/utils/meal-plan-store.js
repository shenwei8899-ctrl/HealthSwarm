import { scopedStorage } from '../services/storage.js'
import { mealContext } from './meal-context.js'
import { memberAge } from './member-age.js'

export const MEAL_RULE_VERSION = 'all-members-v1'
export function mealPlanKey(profile, meal, date, swap = null, messages = []) {
  const selected = new Set(profile.defaultDiners || profile.members.map(member=>member.id))
  return JSON.stringify({
    rules: MEAL_RULE_VERSION, date, meal, swap,
    members: profile.members.filter(member => (profile.defaultDiners || profile.members.map(m=>m.id)).includes(member.id)).map(member => ({ ...member, age: memberAge(member, date).years })),
    goals: profile.goals, tastes: profile.tastes, context: mealContext(date, messages).filter(message=>message.memberId===null||selected.has(message.memberId)),
  })
}

export function readMealResult(date, meal, key) {
  if (typeof uni === 'undefined') return null
  const stored = scopedStorage.getStorageSync('generated-meals-v1')?.[date]?.[meal]
  return stored?.key === key ? stored.plan : null
}

export function writeMealResult(date, meal, key, plan) {
  if (typeof uni === 'undefined') return
  const store = scopedStorage.getStorageSync('generated-meals-v1') || {}
  store[date] ||= {}
  store[date][meal] = { key, plan: JSON.parse(JSON.stringify(plan)) }
  scopedStorage.setStorageSync('generated-meals-v1', store)
}

export function unavailableMeal(members, meal, date) {
  const message = '本餐建议尚未生成，请重试分析'
  return { members, count: members.length, meal, date, dishes: [], products: [], steps: [], memberNotes: [], memberDemands: [], minutes: 0,
    nutrition: null, sourceType: 'api', blocked: [message], issues: [{ type: 'service', message }], safetyText: message }
}
