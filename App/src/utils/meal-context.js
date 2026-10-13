import { scopedStorage } from '../services/storage.js'
import { memberAge } from './member-age.js'

const relevant = /怀孕|孕期|哺乳|产后|喂养|辅食|吞咽|食欲|过敏|不耐受|忌口|医嘱|医生|糖尿病|血压|血脂|肾脏|痛风|不吃|不能吃|孩子.*岁|宝宝.*月/

export function mealContext(date, extraMessages = []) {
  const saved = typeof uni === 'undefined' ? [] : scopedStorage.getStorageSync('chat-' + date) || []
  const refs = typeof uni === 'undefined' ? [] : scopedStorage.getStorageSync('meal-context-refs-v1')?.[date] || []
  const inherited = refs.flatMap(ref => (scopedStorage.getStorageSync('chat-' + ref.date) || []).filter(message => message.id === ref.id).map(message => ({ ...message, sourceDate:ref.date })))
  const unique = new Map()
  for (const message of [...inherited, ...saved, ...extraMessages]) {
    if (message.role !== 'user' || !relevant.test(message.text || '') || message.withdrawn) continue
    const id = message.id || `${date}:${message.text}`
    unique.set(id, { id, text: message.text, date: message.sourceDate || date, memberId:message.memberId ?? null, createdAt: message.createdAt || null })
  }
  // Current-day statements retain their order so corrections remain visible.
  return [...unique.values()]
}

export function linkMealContext(targetDate, sourceDate) {
  if(targetDate===sourceDate || typeof uni==='undefined')return
  const store=scopedStorage.getStorageSync('meal-context-refs-v1')||{}
  store[targetDate]=mealContext(sourceDate).map(message=>({id:message.id,date:message.date}))
  scopedStorage.setStorageSync('meal-context-refs-v1',store)
}

export function planningMembers(members, viewer = 'creator') {
  return members.map(member => ({
    ...member,
    reports: (member.reports || []).filter(report => ['done', '已核对'].includes(report.status) && (member.claimedBy === viewer || report.shared === true)),
  }))
}

export const hasMealContext = message => relevant.test(message || '')

export function contextMember(profile, text) {
  const named = profile.members.filter(member => member.name !== '我' && (text.includes(member.name) || (member.relation && !['本人','家人'].includes(member.relation) && text.includes(member.relation))))
  if (named.length === 1) return named[0].id
  if (named.length > 1) return null
  if (/^我(?!妈|爸|家|女儿|儿子|孩子|宝宝)/.test(text)) return (profile.members.find(member => member.claimedBy === (profile.viewerAccount || 'creator')) || profile.members.find(member => member.relation === '本人'))?.id ?? null
  const children = profile.members.filter(member => { const age=memberAge(member).years;return age !== null && age < 18 })
  if (/孩子|宝宝/.test(text) && children.length === 1) return children[0].id
  return null
}
