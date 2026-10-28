/** 通过既有持久化配餐链路处理聊天请求，不接受模型生成的替代菜单。 */
export async function loadChatMealPlan(intent, { client, state, profile, isCurrent = () => true, retry = false }) {
  if (!intent || !isCurrent()) return null
  if (intent.unsupportedDate) throw new Error('请明确选择今天或明天的餐单；多日安排请使用 AI 专属计划。')
  if (intent.requiresProfileReview) throw new Error('请先在家庭档案中核对并保存这次提到的健康情况、过敏、忌口或医嘱，确认后发送“按档案为我配餐”。')
  const ids = intent.audience === 'self' ? [profile.selfMemberId] : intent.audience === 'family' ? profile.defaultDiners : null
  if (intent.audience !== 'default' && (!Array.isArray(ids) || !ids.length || ids.some(id => !id || !profile.members.some(member => member.id === id)))) {
    throw new Error(intent.audience === 'self' ? '请先在家庭档案中确认本人资料，再为你配餐。' : '请先在家庭档案中选择默认就餐成员。')
  }

  await client.load(intent.date, retry)
  if (!isCurrent() || state.phase !== 'ready' || state.error || !state.arrangement) return null
  if (!ids) return state.arrangement
  for (const type of intent.meals) {
    const meal = state.arrangement.meals.find(row => row.type === type)
    if (!meal) throw new Error('本餐结果不完整，请重新读取。')
    const actual = meal.members.map(member => member.id).sort()
    if (JSON.stringify(actual) === JSON.stringify([...ids].sort())) continue
    if (!isCurrent()) return null
    // 明确的“为我配餐”只调整请求的餐次，权限、营养和版本仍由服务端验证。
    await client.changeMembers(type, ids)
    if (!isCurrent() || state.phase !== 'ready' || state.error || !state.arrangement) return null
    const saved = state.arrangement.meals.find(row => row.type === type)?.members.map(member => member.id).sort()
    if (JSON.stringify(saved) !== JSON.stringify([...ids].sort())) throw new Error('本餐就餐成员尚未确认，请重新读取安排后再试。')
  }
  return state.arrangement
}
