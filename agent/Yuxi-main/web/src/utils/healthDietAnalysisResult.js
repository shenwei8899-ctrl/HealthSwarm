const nutrientCodes = ['energy_kcal', 'protein_g', 'fat_g', 'carbohydrate_g', 'sodium_mg']
const count = (value) => Number.isInteger(value) && value >= 0
const fact = (value) =>
  value === null ||
  (typeof value === 'number' && Number.isFinite(value)) ||
  (typeof value === 'string' && /^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(value))

/** 只识别同一已完成Run的持久化饮食分析或反馈正文。 */
export function publishedDietAnalysisResult(message, run, agentSlug, isProcessing = false) {
  if (
    agentSlug !== 'health-diet-analyst' ||
    isProcessing ||
    message?.type !== 'ai' ||
    message.message_type !== 'text' ||
    !Number.isInteger(message.id) ||
    message.id < 1 ||
    !message.run_id ||
    run?.run_id !== message.run_id ||
    run.status !== 'completed' ||
    !message.request_id ||
    run.request_id !== message.request_id ||
    message.error_type ||
    message.extra_metadata?.error_type ||
    message.isStoppedByUser ||
    typeof message.content !== 'string'
  )
    return null
  let result
  try {
    result = JSON.parse(message.content)
  } catch {
    return null
  }
  if (!result || typeof result !== 'object' || Array.isArray(result)) return null
  if (!['diet_analysis', 'meal_feedback'].includes(result.result_type)) return null
  // 显式目标绑定保留原完整投影，事实卡片尚不承载当前目标。
  if (Object.hasOwn(result, 'current_personal_targets')) return null
  const feedback = result.result_type === 'meal_feedback'
  if (
    feedback
      ? result.scope !== 'single_meal_feedback' || result.nutrition_recalculated !== false
      : !['confirmed_period', 'confirmed_single_meal'].includes(result.scope)
  )
    return null
  if (result.status === 'needs_input') {
    return Array.isArray(result.questions) &&
      result.questions.length > 0 &&
      result.questions.every((question) => typeof question === 'string' && question.trim())
      ? result
      : null
  }
  if (feedback) {
    return result.status === 'saved' &&
      result.feedback?.status === 'active' &&
      Number.isInteger(result.feedback.version) &&
      result.feedback.version > 0 &&
      result.feedback.details &&
      typeof result.feedback.details === 'object' &&
      !Array.isArray(result.feedback.details) &&
      typeof result.feedback.details.consumption === 'string' &&
      typeof result.feedback.details.comment === 'string' &&
      Array.isArray(result.feedback.details.tags) &&
      result.feedback.details.tags.every((tag) => typeof tag === 'string')
      ? result
      : null
  }
  if (
    result.status !== 'completed' ||
    !result.nutrition?.totals ||
    typeof result.nutrition.totals !== 'object' ||
    Array.isArray(result.nutrition.totals) ||
    !result.coverage ||
    typeof result.coverage !== 'object' ||
    Array.isArray(result.coverage)
  )
    return null
  if (result.scope === 'confirmed_period') {
    return [1, 7, 30].includes(result.window?.period_days) &&
      result.window.timezone === 'Asia/Shanghai' &&
      typeof result.window.start_date === 'string' &&
      typeof result.window.end_date === 'string' &&
      ['days_with_records', 'record_count', 'excluded_invalidated_records'].every((code) =>
        count(result.coverage[code])
      ) &&
      nutrientCodes.every((code) => {
        const value = result.nutrition.totals[code]
        return (
          value &&
          fact(value.recorded_total) &&
          fact(value.known_sum) &&
          count(value.known_records) &&
          count(value.missing_records)
        )
      })
      ? result
      : null
  }
  return Array.isArray(result.items) &&
    result.items.every((item) => item && typeof item.name === 'string' && fact(item.eaten_grams)) &&
    ['recorded_items', 'calculated_items', 'known_nutrients', 'supported_nutrients'].every((code) =>
      count(result.coverage[code])
    ) &&
    nutrientCodes.every((code) => fact(result.nutrition.totals[code]))
    ? result
    : null
}
