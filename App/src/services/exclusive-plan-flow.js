/** 服务端推荐组是唯一任务来源；页面切换只读取，不重新排餐。 */
export const planTiers = ['economy', 'standard', 'premium']
export const planTierNames = { economy: '经济型', standard: '标准型', premium: '品质型' }
export const planMoney = value => Number.isSafeInteger(value) && value >= 0 ? (value / 100).toFixed(2) : '待报价'
export const exclusivePlanState = () => ({ status: 'empty', busy: false, error: '', errorCode: '', group: null, plans: [], tier: 'standard' })

export function createExclusivePlanFlow({ state, send, commerce, family, revision, storage, newId,
  later = setTimeout, cancelLater = clearTimeout }) {
  let epoch = 0, timer = null
  const key = () => 'exclusive-plan-intent:v1:' + family()
  const stop = () => { epoch++; if (timer) cancelLater(timer); timer = null; state.busy = false }
  async function run(work) {
    if (state.busy) return
    const token = epoch, scope = revision(), fid = family()
    const active = () => token === epoch && scope === revision() && fid === family()
    state.busy = true; state.error = ''; state.errorCode = ''
    try {
      if (!fid) throw new Error('请先选择家庭并完成建档')
      await work(active, fid)
    } catch (error) {
      if (!active()) return
      state.error = error.message || '计划暂未准备好'; state.errorCode = error.businessCode || ''
      if (error.businessCode === 'exclusive_plan_policy_missing') state.status = 'unavailable'
      if ([401, 403, 404, 410].includes(Number(error.code)) || error.code === 'SESSION_CHANGED') {
        state.plans = []; state.group = null
      }
    } finally {
      if (active()) { state.busy = false; schedule() }
      else if (token === epoch) Object.assign(state, exclusivePlanState())
    }
  }
  function schedule() {
    if (timer) cancelLater(timer)
    timer = state.status === 'generating' && !state.error ? later(() => { timer = null; refresh() }, 2500) : null
  }
  async function accept(group, active) {
    if (!active()) return
    state.group = group; state.status = group.status; state.plans = []
    if (group.status === 'ready') {
      const result = await commerce.servicePlans(group.group_id)
      if (!active()) return
      const items = result.items || []
      if (result.recommendation_group_ref !== group.group_id || items.length !== 3 ||
          new Set(items.map(p => p.tier_code)).size !== 3 || items.some(p => !planTiers.includes(p.tier_code) ||
            p.recommendation_group_ref !== group.group_id || !group.plans.some(ref => ref.plan_sn === p.plan_sn && ref.plan_version === p.plan_version))) {
        throw new Error('计划已更新，请重新读取')
      }
      state.plans = planTiers.map(tier => items.find(p => p.tier_code === tier))
    }
    if (group.status === 'failed') state.error = group.error?.message || '计划暂未准备完成'
  }
  async function submit(action, active, fid) {
    let intent = storage.getStorageSync(key())
    if (!intent) {
      intent = { client_request_id: newId(), action,
        ...(action === 'retry' && state.group?.group_id ? { group_id: state.group.group_id } : {}) }
      storage.setStorageSync(key(), intent)
    }
    try {
      const { data } = await send({ path: `/api/health/v1/families/${encodeURIComponent(fid)}/exclusive-plans`, method: 'POST', data: intent })
      if (!active()) return
      storage.setStorageSync(key(), null)
      await accept(data, active)
    } catch (error) {
      if (active() && Number(error.code) >= 400 && Number(error.code) < 500) storage.setStorageSync(key(), null)
      throw error
    }
  }
  function refresh() {
    return run(async (active, fid) => {
      const suffix = state.group?.group_id ? '/' + encodeURIComponent(state.group.group_id) : ''
      const { data } = await send({ path: `/api/health/v1/families/${encodeURIComponent(fid)}/exclusive-plans${suffix}` })
      await accept(data, active)
    })
  }
  return { stop, refresh,
    open() {
      stop(); Object.assign(state, exclusivePlanState())
      return run(async (active, fid) => {
        const { data } = await send({ path: `/api/health/v1/families/${encodeURIComponent(fid)}/exclusive-plans` })
        if (!active()) return
        await accept(data, active)
        if (!active()) return
        if (storage.getStorageSync(key()) || ['empty', 'stale'].includes(data.status)) await submit('ensure', active, fid)
      })
    },
    act(action) { if (!['retry', 'regenerate', 'ensure'].includes(action)) return; return run((active, fid) => submit(action, active, fid)) },
    select(tier) { if (planTiers.includes(tier)) state.tier = tier },
  }
}
