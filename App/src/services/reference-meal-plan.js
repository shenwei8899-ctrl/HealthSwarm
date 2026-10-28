export function referenceSelection(profile, text, { today, tomorrow, memberId } = {}) {
  if (/后天|后日|下周|下星期|星期[一二三四五六日天]|周[一二三四五六日天]|\d+[月号日/-]/.test(text)) {
    throw new Error('请明确选择今天或明天的餐次，原问题已保留。')
  }
  const selected = memberId ? profile.members.find(m => m.healthMemberId === memberId)
    : profile.members.find(m => m.id === profile.selfMemberId)
  const family = /全家|一家|家人|家庭/.test(text)
  const explicitSelf = /只(给|要|安排).{0,3}我|我一个人|我自己/.test(text)
  const defaults = Array.isArray(profile.defaultDiners) ? profile.defaultDiners : []
  const ids = family ? profile.members.map(m => m.id) : memberId || explicitSelf ? [selected?.id] : defaults.length ? defaults : [selected?.id]
  if (!ids.length || ids.some(id => !id)) throw new Error('请先选择可访问的就餐成员。')
  const chosen = [['breakfast',/早餐|早上/],['lunch',/午餐|中午/],['dinner',/晚餐|晚上|今晚/]].filter(([,pattern])=>pattern.test(text)).map(([meal])=>meal)
  const meals = /三餐|全天|一天/.test(text)||!chosen.length ? ['breakfast','lunch','dinner'] : chosen
  return {mode:'reference',family_id:profile.householdId,plan_date:/明天|明日/.test(text)?tomorrow:today,
    participant_ids:[...new Set(ids)].sort(),meal_types:meals}
}

export function isReferencePlan(value) {
  return value?.scope === 'daily_reference' && value.status === 'reference_ready' &&
    value.professional_status === 'not_reviewed' && value.nutrition_status === 'not_calculated' &&
    typeof value.preview_id === 'string' && Array.isArray(value.meals) && value.meals.length > 0
}
