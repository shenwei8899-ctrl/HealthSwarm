import { request } from './request.js'

const path = familyId => '/api/family/' + encodeURIComponent(familyId) + '/weekly-meal-plans'

export async function startWeeklyMealPlan(familyId, values) {
  const { data } = await request({path:path(familyId),method:'POST',headers:{'Idempotency-Key':values.client_request_id},data:values,timeout:30000})
  return data
}

export async function readWeeklyMealPlan(familyId, threadId, groupId) {
  const { data } = await request({path:path(familyId)+'/'+encodeURIComponent(groupId)+'?thread_id='+encodeURIComponent(threadId),timeout:30000})
  return data
}

export async function readWeeklyMealDay(familyId, threadId, groupId, date) {
  const { data } = await request({path:path(familyId)+'/'+encodeURIComponent(groupId)+'/days/'+encodeURIComponent(date)+'?thread_id='+encodeURIComponent(threadId),timeout:30000})
  return data
}

export async function listWeeklyMealPlans(familyId, threadId) {
  const { data } = await request({path:path(familyId)+'?thread_id='+encodeURIComponent(threadId),timeout:30000})
  return data.items || []
}

export async function retryWeeklyMealPlan(familyId, threadId, groupId) {
  const { data } = await request({path:path(familyId)+'/'+encodeURIComponent(groupId)+'/retry?thread_id='+encodeURIComponent(threadId),method:'POST',timeout:30000})
  return data
}
