const mealTypes = ['breakfast', 'lunch', 'dinner']
const active = status => ['queued', 'dispatched', 'pending', 'running', 'cancel_requested'].includes(status)

export function todayMealPlanPresentation(state, generating = false) {
  // 只折叠纯状态；授权、问题和候选确认仍交给原来的操作区。
  const prompt = !!state.consentOption || ['consent', 'answer', 'candidates'].includes(state.action) ||
    ['needs_input', 'reference_candidates'].includes(state.pending?.status)
  const normal = {kind: '', label: '', retry: false, showNotice: !!state.plan && (!!state.notice || prompt)}
  if (!state.plan || prompt) return normal

  const roster = state.plan.roster || {}
  const updating = generating || mealTypes.some(type => roster[type]?.status === 'pending') || active(state.pending?.status)
  const failed = state.generationFailed || !generating && mealTypes.some(type => roster[type]?.status === 'failed')
  if (failed) return {
    kind: 'failed', label: '未完成', showNotice: false,
    retry: !updating && ['refresh', 'regenerate'].includes(state.action),
  }
  if (updating) return {kind: 'updating', label: '更新中', retry: false, showNotice: false}
  return normal
}
