import { isMockMode } from './config.js'
import { callApiAdapter } from './index.js'
import { storageContext } from './storage.js'
import { confirmedFor, recordsOn } from '../utils/feedback.js'
import { planningMembers, mealContext } from '../utils/meal-context.js'

export async function nutritionFeedback(profile, records, { scope='all',date,meal } = {}) {
  const confirmed=recordsOn(confirmedFor(records,scope),date).filter(record=>record.meal===meal)
  if(!confirmed.length || isMockMode)return null
  const current=storageContext(),ids=confirmed.map(record=>record.id)
  const members=scope==='all'?profile.members:profile.members.filter(member=>String(member.id)===String(scope))
  const result=await callApiAdapter('generateNutritionFeedback',{date,meal,records:confirmed,members:planningMembers(members,profile.viewerAccount),context:mealContext(date).filter(message=>message.memberId===null||members.some(member=>member.id===message.memberId))})
  if(current!==storageContext())throw new Error('账号已切换，请重新查看反馈')
  if(!result?.text?.trim()||!Array.isArray(result.recordIds)||!result.recordIds.length||result.recordIds.some(id=>!ids.includes(id)))throw new Error('反馈依据不完整，请重试')
  return result
}
