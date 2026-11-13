// Only explicit, currently readable profile fields participate in recommendations.
const diseases = {
  高血压: 'hypertension', 糖尿病: 'diabetes', 高血脂: 'lipids',
  '高尿酸／痛风': 'purines', '高尿酸或痛风': 'purines', 肾脏疾病: 'kidney',
}
const goals = {
  控压: 'salt', 控糖: 'sugar', 控脂: 'fat', 低嘌呤: 'low-purine',
  减脂: 'weight', 增肌: 'muscle', 补充蛋白质: 'protein', 补蛋白: 'protein',
  饮食均衡: 'balanced', 吃得均衡: 'balanced', 改善蔬菜摄入: 'vegetables',
}
const tastes = { 少盐: 'salt', 清淡: 'light', 少油: 'fat' }
const list = value => Array.isArray(value) ? value.filter(v => typeof v === 'string') : []
const lookup = (mapping, value) => Object.hasOwn(mapping, value) ? mapping[value] : undefined

export function chatPromptTopics(profile) {
  const topics = new Map()
  function add(id, member, field, value, priority) {
    if (!id) return
    if (!topics.has(id)) topics.set(id, { id, priority, sources: [] })
    const topic = topics.get(id)
    topic.priority = Math.max(topic.priority, priority)
    topic.sources.push({ memberId: String(member.id ?? ''), name: member.relation === '本人' ? '我' : member.name || member.relation || '家人', field, value })
  }
  for (const member of Array.isArray(profile?.members) ? profile.members : []) {
    if (!member || member.is_active === false) continue
    if (member.healthStatus === 'set') for (const value of list(member.conditions)) {
      const condition = value === '其他' ? (typeof member.otherCondition === 'string' ? member.otherCondition.trim() : '') : value.trim()
      if (condition) add(lookup(diseases, condition) || 'other-condition', member, '基础病', condition, 3)
    }
    for (const value of list(member.goals)) add(lookup(goals, value), member, '饮食目标', value, 2)
    for (const value of list(member.tastePreferences)) add(lookup(tastes, value), member, '口味偏好', value, 1)
    for (const [status, field, topic, label] of [
      ['allergyStatus', 'allergies', 'allergy', '食物过敏'],
      ['intoleranceStatus', 'intolerances', 'intolerance', '食物不耐受'],
      ['avoidanceStatus', 'avoidances', 'avoidance', '饮食忌口'],
    ]) if (member[status] === 'set' && list(member[field]).length) add(topic, member, label, list(member[field]).join('、'), 2)
  }
  // A disease topic already covers its related goal; do not give it two quotas.
  for (const [disease, goal] of [['hypertension', 'salt'], ['diabetes', 'sugar'], ['lipids', 'fat'], ['purines', 'low-purine']]) {
    if (topics.has(disease)) topics.delete(goal)
  }
  return [...topics.values()].map(topic => ({ ...topic, sources: topic.sources.sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b))) }))
    .sort((a, b) => a.id.localeCompare(b.id))
}

export function chatPromptProfileKey(profile) {
  const members = (Array.isArray(profile?.members) ? profile.members : []).filter(m => m && m.is_active !== false)
  return JSON.stringify({ members: members.map(m => String(m.id ?? '')).sort(), topics: chatPromptTopics(profile) })
}
