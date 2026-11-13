import { chatPromptTopics } from './chat-prompt-profile.js'
import { PERSONALIZED_CHAT_PROMPT_POOL } from '../data/chat-prompts.js'
export { PERSONALIZED_CHAT_PROMPT_POOL } from '../data/chat-prompts.js'

// The general pool also supplies the instant, network-independent first render.
export const CHAT_PROMPT_POOL = Object.freeze([
  { id: 'breakfast-today', text: '帮我安排今天早餐', action: 'reference_meal_preview', hours: [5, 10] },
  { id: 'breakfast-tomorrow', text: '给我安排明天早餐', action: 'reference_meal_preview', hours: [17, 24] },
  { id: 'lunch-today', text: '今天午餐吃什么？', action: 'reference_meal_preview', hours: [5, 14] },
  { id: 'dinner-today', text: '今晚全家吃什么？', action: 'reference_meal_preview', hours: [10, 24] },
  { id: 'meals-tomorrow', text: '帮我安排明天三餐', action: 'reference_meal_preview' },
  { id: 'family-tomorrow', text: '安排明天全家三餐', action: 'reference_meal_preview' },
  { id: 'vegetables', text: '蔬菜怎么做好吃？', action: 'consultation' },
  { id: 'egg-tomato', text: '番茄鸡蛋怎么搭？', action: 'consultation' },
  { id: 'quick-breakfast', text: '早餐怎么省时？', action: 'consultation' },
  { id: 'office-lunch', text: '带饭怎么搭配？', action: 'consultation' },
  { id: 'takeaway', text: '外卖怎么加蔬菜？', action: 'consultation' },
  { id: 'whole-grains', text: '粗粮主食怎么搭？', action: 'consultation' },
  { id: 'protein', text: '吃什么补蛋白？', action: 'consultation' },
  { id: 'less-salt', text: '少盐也能好吃吗？', action: 'consultation' },
  { id: 'snacks', text: '下午加餐吃啥？', action: 'consultation' },
  { id: 'fruit', text: '水果啥时候吃？', action: 'consultation' },
  { id: 'shopping', text: '怎么买菜不浪费？', action: 'consultation' },
  { id: 'storage', text: '蔬菜怎么保存？', action: 'consultation' },
  { id: 'label', text: '营养标签怎么看？', action: 'consultation' },
  { id: 'eat-out', text: '聚餐怎么点菜？', action: 'consultation' },
  { id: 'regular-meals', text: '忙时怎么按点吃？', action: 'consultation' },
  { id: 'leftovers', text: '剩菜怎么保存？', action: 'consultation' },
  { id: 'records', text: '看看饮食记录', action: 'open_records' },
  { id: 'recent-records', text: '看看最近吃了啥', action: 'open_records' },
])

function shuffled(values, random) {
  const pool = [...values]
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1))
    ;[pool[i], pool[j]] = [pool[j], pool[i]]
  }
  return pool
}

function generalCategory(prompt) {
  if (prompt.action === 'open_records') return 'records'
  if (prompt.id.includes('breakfast')) return 'breakfast'
  if (prompt.action === 'reference_meal_preview') return 'meal-plan'
  return ({ 'egg-tomato': 'vegetables', leftovers: 'storage' })[prompt.id] || prompt.id
}

/** Match the whole readable household; shuffle within relevant topics, not across all questions. */
export function selectChatPrompts({ profile, previousIds = [], hour = new Date().getHours(), random = Math.random } = {}) {
  const previous = new Set(Array.isArray(previousIds) ? previousIds.filter(id => typeof id === 'string') : [])
  const topics = shuffled(chatPromptTopics(profile), random)
  const general = shuffled(CHAT_PROMPT_POOL.filter(p => (!p.hours || hour >= p.hours[0] && hour < p.hours[1]) &&
    (!profile?.members || profile.members.length > 1 || !['dinner-today', 'family-tomorrow'].includes(p.id))), random)
  const selected = []
  const categories = new Set(), counts = new Map(), forms = new Map()
  const candidates = shuffled(PERSONALIZED_CHAT_PROMPT_POOL, random)
  for (let slot = 0; slot < 3 && topics.length; slot++) {
    // Cover different needs first; rotate equally ranked topics across successive groups.
    topics.sort((a, b) => (counts.get(a.id) || 0) - (counts.get(b.id) || 0) || b.priority - a.priority ||
      [...previous].filter(id => id.startsWith(a.id + ':')).length - [...previous].filter(id => id.startsWith(b.id + ':')).length)
    for (const topic of topics) {
      const usable = candidates.filter(p => p.topic === topic.id && !categories.has(p.category) &&
        (forms.get(p.form) || 0) < 2 && !selected.some(s => s.id === p.id || s.text === p.text))
      const prompt = usable.find(p => !previous.has(p.id)) || usable[0]
      if (!prompt) continue
      selected.push(prompt)
      categories.add(prompt.category); counts.set(topic.id, (counts.get(topic.id) || 0) + 1)
      forms.set(prompt.form, (forms.get(prompt.form) || 0) + 1)
      break
    }
  }
  // Previous questions may return only if fresh, distinct categories cannot fill the group.
  for (const freshOnly of [true, false]) for (const prompt of general) {
    if (selected.length === 4) return selected
    const category = generalCategory(prompt)
    if (categories.has(category) || selected.some(p => p.text === prompt.text) || freshOnly && previous.has(prompt.id)) continue
    selected.push(prompt); categories.add(category)
  }
  return selected
}
