import {request} from './request.js'
import {getSession} from './session.js'
import {scopedStorage} from './storage.js'
import {cloudProfileInput} from './cloud-profile.js'
import {newHealthRequestId} from './health-task-flow.js'

export function preparationRoot() {
  const id=getSession()?.householdId
  if(!id)throw new Error('请先登录并选择当前家庭。')
  return '/api/family/'+encodeURIComponent(id)+'/onboarding-preparations'
}

export function queueOnboardingPreparation(profile) {
  const session=getSession()
  if(!session?.token)throw Object.assign(new Error('登录状态已失效，填写内容已保留，请重新登录后继续。'),{code:401})
  if(profile.householdId!==session.householdId)throw Object.assign(new Error('家庭已变化，请重新读取档案。'),{code:'SESSION_CHANGED'})
  const previous=scopedStorage.getStorageSync('onboarding-preparation-pending')
  if(previous)throw Object.assign(new Error('上次准备的提交结果尚未确认，请先继续原准备。'),{code:'PREPARATION_PENDING'})
  const config=profile.healthConfiguration||{}
  const processing_consents=['consultation','meal_plan'].filter(p=>config[p]?.available&&config[p].processor&&config.policy_version).map(p=>({purpose:p,processor:config[p].processor,policy_version:config.policy_version}))
  const body={...cloudProfileInput(profile,newHealthRequestId()),processing_consents}
  scopedStorage.setStorageSync('onboarding-preparation-pending',body)
  return body
}

export async function readCurrentPreparation() {
  return (await request({path:preparationRoot()+'/current'})).data
}

export function preparationRoute(value) {
  return '/pages/onboarding/preparing'+(value?.id?'?id='+encodeURIComponent(value.id):'')
}
