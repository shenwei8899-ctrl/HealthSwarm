export const mealNames = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐' }
export const batchNames = { scheduled: '待配送', paused: '已暂停', preparing: '备货中', shipped: '已发货', delivering: '配送中', delivered: '已送达', refund_pending: '退款中', refunded: '已退款', cancelled: '已取消', exception: '待处理' }
export const priceText = cents => Number.isSafeInteger(cents) && cents >= 0 ? '¥' + (cents / 100).toFixed(2) : '待报价'
export function selectedDay(plan, number) { return plan?.days?.find(day => Number(day.day_no) === Number(number)) || null }
export function dayMeals(day) { return Object.entries(mealNames).map(([type, name]) => ({ type, name, dishes: (day?.meals || []).filter(meal => meal.meal_type === type) })) }
export function memberName(plan, ref) { return plan?.members?.find(member => String(member.member_ref) === String(ref))?.display_alias || '家庭成员' }
export function selectedProducts(plan, number) { return plan?.trade_draft?.days?.find(day => Number(day.day_no) === Number(number))?.items || [] }
export function validPlanRoute(options) {
  const version = Number(options.plan_version)
  if (!options.plan_sn || !Number.isSafeInteger(version) || version < 1) throw new Error('请从专属计划页重新选择方案')
  return { sn: String(options.plan_sn), version }
}
