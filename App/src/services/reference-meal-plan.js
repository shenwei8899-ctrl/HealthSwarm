export function referenceSelection(profile, text, { today, tomorrow, memberId, previous } = {}) {
  if (/后天|后日|下周|下星期|星期[一二三四五六日天]|周[一二三四五六日天]|\d+[月号日/-]/.test(text)) {
    throw new Error('请明确选择今天或明天的餐次，原问题已保留。')
  }
  const selected = memberId ? profile.members.find(m => m.healthMemberId === memberId)
    : profile.members.find(m => m.id === profile.selfMemberId)
  if (previous && (previous.family_id !== profile.householdId || !Array.isArray(previous.participant_ids) ||
    !Array.isArray(previous.meal_types) || previous.participant_ids.some(id => !profile.members.some(m => m.id === id)))) {
    throw new Error('餐单成员资料已变化，请重新选择就餐成员。')
  }
  const family = /全家|一家|家人|家庭|我们/.test(text)
  const self = /为我|给我|帮我|本人|自己|一个人|一人|只(?:有|给)?我/.test(text)
  const ids = family ? profile.members.map(m => m.id) : previous && !self ? previous.participant_ids : [selected?.id]
  if (!ids.length || ids.some(id => !id)) throw new Error('请先选择可访问的就餐成员。')
  const chosen = [['breakfast',/早餐|早饭|早上|今早|明早/],['lunch',/午餐|午饭|中午/],['dinner',/晚餐|晚饭|晚上|今晚|明晚/]].filter(([,pattern])=>pattern.test(text)).map(([meal])=>meal)
  const meals = /三餐|全天|一天/.test(text) ? ['breakfast','lunch','dinner']
    : previous && chosen.every(meal => previous.meal_types.includes(meal)) ? previous.meal_types
    : chosen.length ? chosen : ['breakfast','lunch','dinner']
  const date = /明天|明日|明早|明晚/.test(text) ? tomorrow : /今天|今日|今早|今晚/.test(text) ? today : previous?.plan_date || today
  return {mode:'reference',family_id:profile.householdId,plan_date:date,
    participant_ids:[...new Set(ids)].sort(),meal_types:meals}
}

export function isReferencePlan(value) {
  return value?.scope === 'daily_reference' && value.status === 'reference_ready' &&
    value.professional_status === 'not_reviewed' && value.nutrition_status === 'not_calculated' &&
    typeof value.preview_id === 'string' && Array.isArray(value.meals) && value.meals.length > 0
}
