import { request } from './request.js'
import { getSession } from './session.js'
import { newHealthRequestId } from './health-task-flow.js'
import { dishKey } from '../utils/meal-presentation.js'

export async function addDishToMeal(target, dish, mealType, requestId, send = request) {
  const familyId = target.familyId || getSession().householdId
  const { data } = await send({
    path: '/api/family/' + encodeURIComponent(familyId) + '/daily-meal-plans/' + target.date + '/dishes',
    method: 'POST',
    data: { version: target.dailyPlanVersion, source_meal: target.mealType, meal_type: mealType,
      dish_key: dishKey(dish), client_request_id: requestId || newHealthRequestId() },
  })
  if (data.date !== target.date || !Number.isInteger(data.version) || data.status !== 'ready') throw new Error('餐单保存结果尚未确认，请重新读取。')
  return data
}

export function savedPurchaseScope(target, dishes) {
  return target.dailyPlanVersion == null ? null : { familyId: target.familyId, date: target.date,
    mealType: target.mealType, version: target.dailyPlanVersion, dishKeys: dishes?.map(dishKey) || [] }
}
