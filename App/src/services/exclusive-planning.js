import { request } from './request.js'
import { getSession, sessionRevision } from './session.js'
import { scopedStorage } from './storage.js'
import { newHealthRequestId } from './health-task-flow.js'
import { commerce } from './commerce.js'
import { createExclusivePlanFlow } from './exclusive-plan-flow.js'
export { exclusivePlanState, planTiers, planTierNames, planMoney } from './exclusive-plan-flow.js'
// 旧原型仅供演示回归；正式页面不调用这一入口。
export { ensureExclusivePlan } from './exclusive-planning-demo.js'
export async function readExclusivePreview(groupId, tier) {
  const familyId = getSession()?.householdId
  if (!familyId) throw new Error('请先选择家庭')
  const { data } = await request({
    path: '/api/health/v1/families/' + encodeURIComponent(familyId) +
      '/exclusive-plans/' + encodeURIComponent(groupId) + '/tiers/' + encodeURIComponent(tier),
  })
  return data
}
export function createExclusivePlanClient(state) {
  return createExclusivePlanFlow({ state, send: request, commerce, family: () => getSession()?.householdId,
    revision: sessionRevision, storage: scopedStorage, newId: newHealthRequestId })
}
