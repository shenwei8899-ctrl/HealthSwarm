// 推荐只使用时间与通用话题，不根据家庭成员信息推断疾病。
export const CHAT_PROMPT_POOL = Object.freeze([
  { id: 'breakfast-today', text: '帮我安排今天早餐', action: 'reference_meal_preview', hours: [5, 10] },
  { id: 'breakfast-tomorrow', text: '给我安排明天早餐', action: 'reference_meal_preview', hours: [17, 24] },
  { id: 'lunch-today', text: '今天午餐吃什么？', action: 'reference_meal_preview', hours: [5, 14] },
  { id: 'dinner-today', text: '今晚全家吃什么？', action: 'reference_meal_preview', hours: [10, 24] },
  { id: 'meals-tomorrow', text: '帮我安排明天三餐', action: 'reference_meal_preview' },
  { id: 'family-tomorrow', text: '安排明天全家三餐', action: 'reference_meal_preview' },
  { id: 'vegetables', text: '蔬菜怎么做更好吃？', action: 'consultation' },
  { id: 'egg-tomato', text: '鸡蛋番茄怎么搭配？', action: 'consultation' },
  { id: 'quick-breakfast', text: '早餐怎样省时准备？', action: 'consultation' },
  { id: 'office-lunch', text: '上班带饭怎么搭配？', action: 'consultation' },
  { id: 'takeaway', text: '点外卖怎么选蔬菜？', action: 'consultation' },
  { id: 'whole-grains', text: '粗粮怎样搭配主食？', action: 'consultation' },
  { id: 'protein', text: '日常蛋白质怎么选？', action: 'consultation' },
  { id: 'less-salt', text: '少盐怎样也有味道？', action: 'consultation' },
  { id: 'snacks', text: '下午加餐可以选啥？', action: 'consultation' },
  { id: 'fruit', text: '水果适合怎么安排？', action: 'consultation' },
  { id: 'shopping', text: '买菜怎样减少浪费？', action: 'consultation' },
  { id: 'storage', text: '蔬菜怎样保存更好？', action: 'consultation' },
  { id: 'label', text: '食品营养标签怎么看？', action: 'consultation' },
  { id: 'eat-out', text: '在外聚餐怎么搭配？', action: 'consultation' },
  { id: 'regular-meals', text: '忙起来怎么规律吃饭？', action: 'consultation' },
  { id: 'leftovers', text: '剩饭剩菜怎么保存？', action: 'consultation' },
  { id: 'records', text: '看看我的饮食记录', action: 'open_records' },
  { id: 'recent-records', text: '查看最近的饮食记录', action: 'open_records' },
])

/** 抽取四条不同问题，候选充足时整组避开上一组。 */
export function selectChatPrompts({ previousIds = [], hour = new Date().getHours(), random = Math.random } = {}) {
  const previous = new Set(Array.isArray(previousIds) ? previousIds : [])
  const candidates = CHAT_PROMPT_POOL.filter(p => !p.hours || (hour >= p.hours[0] && hour < p.hours[1]))
  const fresh = candidates.filter(p => !previous.has(p.id))
  const pool = [...(fresh.length >= 4 ? fresh : candidates)]
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1))
    ;[pool[i], pool[j]] = [pool[j], pool[i]]
  }
  const selected = []
  // 两种“查看记录”文案指向同一功能，每组最多出现一次。
  for (const prompt of pool) {
    if (prompt.action === 'open_records' && selected.some(p => p.action === 'open_records')) continue
    selected.push(prompt)
    if (selected.length === 4) break
  }
  return selected
}
