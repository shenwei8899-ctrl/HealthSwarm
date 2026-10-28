const meals = ['breakfast', 'lunch', 'dinner']
const copy = value => JSON.parse(JSON.stringify(value))
// 旧服务统一把503标为retryable；这些依赖需要用户或管理员补齐，重放不会恢复。
const setupErrors = new Set(['daily_member_sources_unavailable', 'daily_profile_source_unavailable', 'daily_rules_unavailable', 'daily_dependencies_not_ready', 'daily_member_consent_required'])
const uncertain = error => error?.code === 'NETWORK_ERROR' || Number(error?.code) >= 500 && !setupErrors.has(error?.businessCode) && (!error?.businessCode || error.retryable === true)

export function validateDailyArrangement(value, date) {
  if (value?.status !== 'ready' || value.date !== date || !value.id || !Number.isInteger(value.version) || value.version < 1 ||
    value.saved !== true || value.validation?.status !== 'passed' || value.procurement?.checked !== true ||
    !value.analysis?.text?.trim() || value.analysis.source !== 'agent' || !value.analysis.request_id || !value.analysis.run_id ||
    !Array.isArray(value.meals) || value.meals.length !== 3) throw new Error('今日安排尚未完整保存，正在核对原结果。')
  for (const type of meals) {
    const matches = value.meals.filter(meal => meal.type === type)
    if (matches.length !== 1) throw new Error('三餐结果不完整，正在重新读取。')
    const meal = matches[0]
    const purchase = meal.purchase
    const matched = purchase?.status === 'matched' && purchase.catalog_version && purchase.ingredient_requirements?.length &&
      purchase.items?.length && purchase.items.every(item => item.sku?.sku_id && Number.isInteger(item.quantity) && item.quantity > 0 && Number.isInteger(item.sku.price_cent))
    const published = purchase?.package_sn && Number.isInteger(purchase.package_version) && purchase.package_version > 0
    if (!Array.isArray(meal.members) || !meal.members.length || !Array.isArray(meal.dishes) || !meal.dishes.length ||
      !meal.detail_ref || !meal.nutrition || !meal.nutritionSource || !Array.isArray(meal.memberNotes) ||
      (!published && !matched) ||
      meal.members.some(member => !member.id || !member.name || !meal.memberNotes.some(note => note.memberId === member.id && note.dishes?.length)) ||
      meal.dishes.some(dish => !dish.id || !dish.name || !dish.recipeVersion || !dish.ingredients?.length || !dish.steps?.length)) {
      throw new Error('本餐详情尚未完整，正在重新读取。')
    }
  }
  return copy(value)
}

export function dailyArrangementState() {
  return { phase: 'idle', date: '', arrangement: null, error: '', errorCode: '', retryable: true, busy: false, pending: null, messages: [] }
}

// 仅缓存请求标识；已保存菜单、分析和聊天正文每次从服务端读取。
export function createDailyArrangementClient({ state, send, context, storage, newId, beforeStart = async () => {}, wait = ms => new Promise(resolve => setTimeout(resolve, ms)), pollLimit = 60 }) {
  let generation = 0, disposed = false, flight = null, flightContext = '', ownerScope = context().scope
  const current = (ticket, scope) => !disposed && ticket === generation && scope === context().scope
  const key = date => 'daily-arrangement-intent:' + date
  const root = () => '/api/family/' + encodeURIComponent(context().familyId) + '/daily-arrangements'
  async function read(date, scope) {
    const value = (await send({ path: root() + '/' + date })).data
    if (scope !== context().scope) throw Object.assign(new Error('账号已变化'), {code:'SESSION_CHANGED'})
    return value
  }
  function receive(value, date) {
    if (value.status === 'ready') {
      state.arrangement = null;state.phase='loading'
      state.arrangement = validateDailyArrangement(value, date)
      state.phase = 'ready'; state.pending = null
      state.error = value.update?.status === 'failed' ? value.update.message || '调整未完成，原安排已保留。' : ''
      storage.setStorageSync(key(date), null)
    } else {
      state.phase = value.status
      state.arrangement = null
      if (value.status === 'failed' || value.status === 'unavailable') throw new Error(value.message || '今日安排暂未完成，请重试。')
    }
  }
  async function load(date, retry = false) {
    const input = context(), scope = input.scope
    if (disposed) return
    if (ownerScope !== scope) {
      generation++; flight = null; ownerScope = scope; Object.assign(state, dailyArrangementState())
    }
    if (flight && flightContext === scope + ':' + date) return flight
    const ticket = ++generation
    flightContext = scope + ':' + date
    if (state.date !== date || state.arrangement?.date !== date) state.arrangement = null
    state.date = date; state.busy = true; state.error = ''; state.errorCode = ''; state.retryable = true; state.phase = state.arrangement ? 'ready' : 'loading'
    flight = (async () => {
      try {
        if (!input.familyId) throw new Error('请先保存家庭档案。')
        let value
        for(let attempt=0;attempt<3;attempt++) {
          try { value=await read(date,scope);break }
          catch(error) { if(!uncertain(error)||attempt===2)throw error;await wait(1000);if(!current(ticket,scope))return }
        }
        if (!current(ticket, scope)) return
        if(retry && (value.update?.status || value.status)!=='ready' && !['absent','stale'].includes(value.status)) {
          await beforeStart()
          if (!current(ticket, scope)) return
          value=(await send({path:root()+'/'+date+'/resume?retry_failed=true',method:'POST'})).data
        }
        if (!current(ticket, scope)) return
        const mutationKey='daily-arrangement-change:'+value.id
        const mutation=value.id && storage.getStorageSync(mutationKey)
        if(mutation) {
          try {
            await send({path:root()+'/'+date+'/members',method:'POST',headers:{'Idempotency-Key':mutation.client_request_id},data:mutation})
          } catch (error) {
            if (!current(ticket,scope)) return
            if (Number(error.code) !== 409) throw error
            storage.setStorageSync(mutationKey,null)
            value=await read(date,scope)
            if (!current(ticket,scope)) return
            receive(value,date)
            state.error='成员调整或安排版本已变化，已读取当前安排，请重新核对后确认。'
            return
          }
          if(!current(ticket,scope))return
          storage.setStorageSync(mutationKey,null)
          value=await read(date,scope)
          if(!current(ticket,scope))return
        }
        receive(value, date)
        if (value.status === 'ready' && value.update?.status !== 'generating') return
        if (['absent','stale'].includes(value.status) || retry && value.status === 'retryable') {
          await beforeStart()
          if (!current(ticket, scope)) return
          const pending = storage.getStorageSync(key(date)) || { client_request_id: newId(), date }
          state.pending = pending; storage.setStorageSync(key(date), pending)
          try {
            value = (await send({ path: root(), method: 'POST', headers: { 'Idempotency-Key': pending.client_request_id }, data: pending })).data
          } catch (error) {
            if (!current(ticket, scope)) return
            if (!uncertain(error)) throw error
            value = await read(date, scope)
            // 没有持久结果时只重放同一个键，不能创建第二个生成任务。
            if (value.status === 'absent') value = (await send({ path: root(), method: 'POST', headers: { 'Idempotency-Key': pending.client_request_id }, data: pending })).data
          }
        }
        for (let attempt = 0; attempt <= pollLimit; attempt++) {
          if (!current(ticket, scope)) return
          try { receive(value, date) }
          catch (error) {
            if (['failed', 'unavailable'].includes(value.status) || attempt === pollLimit) throw error
          }
          if (state.phase === 'ready' && value.update?.status !== 'generating') return
          if (attempt === pollLimit) throw new Error('今日安排仍在处理中，可重试读取，系统会继续核对同一任务。')
          if (!state.arrangement) state.phase = 'generating'
          await wait(2000)
          if (!current(ticket, scope)) return
          try { value = await read(date, scope) } catch (error) { if (!uncertain(error)) throw error }
        }
      } catch (error) {
        if (current(ticket, scope)) {
          if ([401,403,404,410].includes(Number(error.code))) {
            if (state.arrangement) storage.setStorageSync('daily-arrangement-change:'+state.arrangement.id,null)
            storage.setStorageSync(key(date),null)
            state.arrangement=null;state.pending=null;state.messages=[]
          }
          state.phase = state.arrangement ? 'ready' : 'error'; state.error = error.message || '暂时无法读取今日安排，请重试。'
          state.errorCode = error.businessCode || ''; state.retryable = !setupErrors.has(error.businessCode) && (!error.businessCode || error.retryable === true)
        }
      } finally {
        if (current(ticket, scope)) state.busy = false
        else if(ticket===generation&&scope!==context().scope)Object.assign(state,dailyArrangementState())
        if (ticket === generation) flight = null
      }
    })()
    return flight
  }
  return {
    adopt(value) {
      generation++;flight=null;state.date=value.date
      state.busy=false;state.error='';receive(value,value.date)
    },
    load,
    async detail(id, type, version) {
      const input = context(), ticket = generation
      const { data } = await send({ path: root() + '/' + state.date + '/meals/' + type + '?arrangement_id=' + encodeURIComponent(id) + '&version=' + version })
      if (!current(ticket, input.scope)) throw new Error('账号或日期已变化，请重新进入。')
      if (data.arrangement_id !== id || data.version !== version || data.meal?.type !== type) throw new Error('本餐安排已更新，请重新读取。')
      return data
    },
    async changeMembers(type, ids, { dailyPlanVersion } = {}) {
      if (state.busy || !state.arrangement) return
      const input = context(), ticket = generation, before = copy(state.arrangement)
      state.busy = true; state.error = ''
      try {
        const storageKey = 'daily-arrangement-change:' + before.id
        let pending = storage.getStorageSync(storageKey)
        if (pending && (pending.meal!==type || JSON.stringify([...pending.member_ids].sort())!==JSON.stringify([...ids].sort()))) throw new Error('上次成员调整结果尚未确认，请先重新读取原安排。')
        if (!pending) {
          pending = { client_request_id: newId(), version: before.version, meal: type, member_ids: ids,
            ...(Number.isInteger(dailyPlanVersion) ? {daily_plan_version:dailyPlanVersion} : {}) }
          storage.setStorageSync(storageKey, pending)
        }
        await send({ path: root() + '/' + state.date + '/members', method: 'POST', headers: { 'Idempotency-Key': pending.client_request_id }, data: pending })
        if (!current(ticket, input.scope)) return
        storage.setStorageSync(storageKey, null)
        state.busy = false
        return await load(state.date)
      } catch (error) { if (current(ticket, input.scope)) {
        if(!uncertain(error) && !String(error.message).includes('上次成员调整')) storage.setStorageSync('daily-arrangement-change:'+before.id,null)
        if (Number(error.code) === 409) {
          try {
            const value=await read(state.date,input.scope)
            if (!current(ticket,input.scope)) return
            receive(value,state.date)
            state.error='成员调整或安排版本已变化，已读取当前安排，请重新核对后确认。'
          } catch (readError) {
            if (current(ticket,input.scope)) {state.arrangement=null;state.phase='error';state.error=readError.message}
          }
          return
        }
        if ([401,403,404,410].includes(Number(error.code))) {state.arrangement=null;state.phase='error';state.pending=null}
        state.error = error.message
      } }
      finally { if (current(ticket, input.scope)) state.busy = false;else if(ticket===generation&&input.scope!==context().scope)Object.assign(state,dailyArrangementState()) }
    },
    pause() { generation++; flight = null; state.busy = false },
    reset() { generation++; flight = null; Object.assign(state, dailyArrangementState()) },
    dispose() { disposed = true; generation++; flight = null },
  }
}
