// A detail read never publishes a purchase or starts a nutrition task.
export const mealNames = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐', daily: '所选餐次' }
export function detailState() {
  return { open: false, phase: 'idle', target: null, meal: null, error: '', view: 'meal', dishIndex: 0, expanded: false }
}
export function detailKey(target, scope = '') {
  return JSON.stringify([scope, target.familyId, target.date, target.mealType, target.kind, target.sourceId, target.version ?? null, target.dailyPlanVersion ?? null])
}
export function formalRoute(target) {
  return { date: target.date, meal: target.purchaseMeals?.length?'daily':target.mealType, ...(target.purchaseMeals?.length?{meals:target.purchaseMeals}:{}), arrangement: target.sourceId, version: target.version,
    ...(target.dailyPlanVersion != null ? { daily_plan_version: target.dailyPlanVersion } : {}) }
}
export function detailGesture({ delta, expanded, scrollTop = 0 }) {
  if (delta < -28 && !expanded) return 'expand'
  if (delta > 70 && scrollTop <= 2) return expanded ? 'collapse' : 'close'
  return 'none'
}
export function createMealDetailClient({ state, send, context }) {
  let generation = 0, disposed = false
  const cache = new Map()
  async function open(target) {
    if (!target?.familyId || !/^\d{4}-\d{2}-\d{2}$/.test(target.date || '') || !mealNames[target.mealType] || !target.sourceId) throw new Error('餐单来源不完整，请重新读取餐单。')
    if (!['formal', 'reference', 'selection'].includes(target.kind) || target.kind === 'formal' && (!Number.isInteger(target.version) || target.version < 1)) throw new Error('餐单版本不完整，请重新读取。')
    const ticket = ++generation, scope = context(), selected = { ...target }, key = detailKey(selected, scope)
    const current = () => !disposed && ticket === generation && scope === context() && state.open
    // 已有菜品先展示；操作仍须等待本次来源和版本核对完成。
    Object.assign(state, detailState(), { open: true, phase: 'loading', target: selected, meal: cache.get(key) || target.seed || null, view: target.initialView || 'meal', dishIndex:Number.isInteger(target.dishIndex)?target.dishIndex:0 })
    try {
      let meal
      if (target.kind === 'formal') {
        const r = formalRoute(target)
        const { data } = await send({ path: `/api/family/${encodeURIComponent(target.familyId)}/daily-arrangements/${target.date}/meals/${target.mealType}?arrangement_id=${encodeURIComponent(r.arrangement)}&version=${r.version}${r.daily_plan_version != null ? '&daily_plan_version=' + r.daily_plan_version : ''}` })
        if (!current()) return
        if (data.arrangement_id !== target.sourceId || data.version !== target.version || data.meal?.type !== target.mealType) throw new Error('本餐已更新，请重新读取餐单。')
        meal = data.meal
      } else if (target.dailyPlanVersion != null) {
        const { data } = await send({ path: `/api/family/${encodeURIComponent(target.familyId)}/daily-meal-plans/${target.date}` })
        if (!current()) return
        const item = data?.meals?.find(item => item.meal_type === target.mealType && item.source?.kind === target.kind && item.source.id === target.sourceId)
        if (data.status !== 'ready' || data.date !== target.date || data.version !== target.dailyPlanVersion || !item) throw new Error(data.needs_regeneration?.includes(target.mealType)?'本餐需要重新安排，请返回今日餐单。':'这份参考餐单已有更新，请重新读取。')
        selected.purchaseReady = item.purchase_ready !== false
        meal = { ...item.meal, members: item.members || [] }
        // Keep the purchase option belonging to this version and source.
        selected.purchaseOption = data.purchase_options?.find(o => o.kind === 'reference' && o.id === target.sourceId && o.meal_types?.includes(target.mealType)) || null
      } else {
        if (target.kind === 'reference') {
          const { data } = await send({ path: `/api/health/v1/reference-meal-plans/${encodeURIComponent(target.sourceId)}` })
          if (!current()) return
          if (data.preview_id !== target.sourceId || data.plan_date !== target.date) throw new Error('参考餐单来源已变化，请重新读取。')
          if(data.status==='needs_regeneration'||data.purchase_ready===false)throw new Error('本餐需要重新安排，请返回今日餐单。')
          meal = data.meals?.find(item => item.meal_type === target.mealType)
          if (meal) meal = { ...meal, members: data.members || [] }
        } else meal = target.seed
      }
      if (!current()) return
      if (!meal || !Array.isArray(meal.dishes) || !meal.dishes.length) throw new Error('本餐暂无可读取的菜品。')
      if(state.dishIndex<0||state.dishIndex>=meal.dishes.length)throw new Error('本餐已没有这道菜，请返回重新读取。')
      selected.seed = meal
      cache.set(key, meal)
      if (cache.size > 12) cache.delete(cache.keys().next().value)
      state.meal = meal; state.phase = 'ready'
    } catch (error) {
      if (!current()) return
      state.phase = 'error'; state.error = error.message || '暂时无法读取详情，请重试。'
      state.meal = null; cache.delete(key); delete selected.seed
    }
  }
  return { open, retry: () => state.target && open(state.target),
    close() { generation++; Object.assign(state, detailState()) },
    clear() { generation++; cache.clear(); Object.assign(state, detailState()) },
    dispose() { disposed = true; generation++; cache.clear(); Object.assign(state, detailState()) } }
}
