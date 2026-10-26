import { request } from './request.js'
import { sessionRevision } from './session.js'
import { scopedStorage } from './storage.js'
import { newHealthRequestId } from './health-task-flow.js'
const root = '/api/health/v1', copy = value => JSON.parse(JSON.stringify(value))
const uncertain = error => error.code === 'NETWORK_ERROR' || Number(error.code) >= 500
const stable = value => JSON.stringify(value, (_, item) => item && typeof item === 'object' && !Array.isArray(item)
  ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))) : item)
export function healthPlanState() {
  return { members: [], memberId: '', plans: [], offset: 0, nextOffset: null, plan: null, approval: null,
    previous: [], busy: false, error: '', notice: '', pending: null, blocked: false, adoption: null }
}
/** 用户明确采用当前批准，事务冲突和未知结果沿原请求恢复。 */
export function createHealthPlanClient({ state, send = request, revision = sessionRevision, storage = scopedStorage, newId = newHealthRequestId }) {
  let generation = 0
  const ticket = () => `${generation}:${revision()}`
  const key = () => `plan-action:${state.memberId}`
  function discard() { generation++; Object.assign(state, healthPlanState()) }
  const save = () => storage.setStorageSync(key(), state.pending ? copy(state.pending) : null)
  async function run(action) {
    if (state.busy) return
    const mine = ticket(), context = generation; state.busy = true; state.error = ''; state.notice = ''
    try { await action(() => mine === ticket()) }
    catch (error) {
      if (mine !== ticket()) return
      if ([401, 403, 404, 410].includes(Number(error.code)) || error.code === 'SESSION_CHANGED') {
        if (state.memberId) storage.setStorageSync(key(), null)
        discard(); state.error = '当前餐单或成员授权已变化，请重新读取。'
      } else {
        state.error = Number(error.code) === 409 ? '餐单、批准或采用状态已变化，请重新读取后确认。' : error.message
        if (!uncertain(error)) { state.pending = null; save() }
        if (Number(error.code) === 409) { state.blocked = true; state.approval = null }
      }
    } finally { if (mine === ticket()) state.busy = false; else if (context === generation) discard() }
  }
  async function page(current, offset = 0) {
    const { data } = await send({ path: `${root}/members/${state.memberId}/meal-plans?limit=20&offset=${offset}` })
    if (current()) { state.plans = data.plans; state.offset = offset; state.nextOffset = data.next_offset }
  }
  async function read(current, planId) {
    state.plan = null; state.approval = null; state.previous = []; state.adoption = null
    const plan = (await send({ path: `${root}/meal-plans/${planId}` })).data
    if (!current()) return
    if (plan.plan_id !== planId || plan.member_id !== state.memberId || !Number.isInteger(plan.version)) throw new Error('餐单与当前成员不一致')
    const approval = (await send({ path: `${root}/meal-plans/${planId}/approval-state?version=${plan.version}` })).data
    if (!current()) return
    if (approval.plan_id !== planId || approval.version !== plan.version) throw new Error('专业批准与当前餐单版本不一致')
    const memberIds = Object.keys(plan.members || {})
    const previous = await Promise.all((memberIds.length ? memberIds : [state.memberId]).map(async id => {
      const { data } = await send({ path: `${root}/members/${id}/adopted-plan?plan_date=${encodeURIComponent(plan.plan_date)}` })
      if (data.member_id !== id || data.plan_date !== plan.plan_date) throw new Error('当前采用归属不一致')
      return data.status === 'ready' && data.plan?.current === true ? data.plan : null
    }))
    if (!current()) return
    state.plan = plan; state.approval = approval; state.previous = [...new Map(previous.filter(Boolean).map(row => [row.adoption_id, row])).values()].sort((a,b) => a.adoption_id.localeCompare(b.adoption_id))
    state.adoption = state.previous.find(row => row.plan_id === planId && row.plan_version === plan.version) || null
    state.blocked = false
  }
  async function perform(current) {
    const intent = copy(state.pending), { data } = await send(intent.request)
    if (!current()) return
    if (!data.adoption_id || (intent.operation === 'adopt' && data.plan_id !== intent.planId)) throw Object.assign(new Error('采用回执待核对，请原样重试'), { code: 'NETWORK_ERROR' })
    state.pending = null; save(); state.adoption = data
    state.notice = data.current === true ? '当前餐单已正式采用；实际吃了什么仍需另行记餐。' : '操作已确认，当前采用状态：' + data.status
    await read(current, intent.planId)
  }
  return { discard,
    open(memberId = '') {
      discard()
      return run(async current => {
        const { data } = await send({ path: root + '/members' })
        if (!current()) return
        state.members = data.filter(row => row.scopes?.includes('diet_edit'))
        state.memberId = memberId ? state.members.find(row => row.id === memberId)?.id || '' : state.members[0]?.id || ''
        if (!state.memberId) { state.error = '选定成员当前无餐单权限，请重新选择已授权成员。'; return }
        const intent = storage.getStorageSync(key())
        if (intent?.request?.data?.client_request_id && intent.request.path.startsWith(root + '/')) state.pending = intent
        await page(current)
      })
    },
    page(offset = 0) { if (!state.pending) return run(current => page(current, offset)) },
    detail(plan) { if (!state.pending) return run(current => read(current, typeof plan === 'string' ? plan : plan.plan_id)) },
    adopt(replaceAccepted = false) {
      if (!state.plan || !state.approval?.available || state.pending || state.blocked || state.adoption?.current) return
      if (state.previous.length && !replaceAccepted) { state.error = '请先明确确认替代所列当日采用。'; return }
      return run(async current => {
        const selected = { plan: copy(state.plan), approval: copy(state.approval), previous: copy(state.previous) }
        await read(current, selected.plan.plan_id)
        if (!current()) return
        if (state.plan.version !== selected.plan.version || stable(state.approval) !== stable(selected.approval) || stable(state.previous) !== stable(selected.previous)) {
          state.error = '来源或采用已变化，已读取新状态，请重新核对后确认。'; return
        }
        const profiles = state.approval.sources?.profiles
        if (!profiles || !Object.keys(profiles).length || Object.values(profiles).some(row => !Number.isInteger(row.version))) throw new Error('批准缺少完整档案版本，暂不能采用')
        const data = { client_request_id: newId(), version: state.plan.version, review_id: state.approval.review_id,
          profile_versions: Object.fromEntries(Object.entries(profiles).map(([id, row]) => [id, row.version])),
          replaces_adoptions: Object.fromEntries(state.previous.map(row => [row.adoption_id, row.version])) }
        state.pending = { operation: 'adopt', planId: state.plan.plan_id, request: { path: `${root}/meal-plans/${state.plan.plan_id}/adopt`, method: 'POST', data } }; save()
        await perform(current)
      })
    },
    withdraw(reason) {
      if (!state.adoption?.current || !reason.trim() || state.pending || state.blocked) return
      return run(async current => {
        const data = { client_request_id: newId(), version: state.adoption.version, reason: reason.trim() }
        state.pending = { operation: 'withdraw', planId: state.plan.plan_id, request: { path: `${root}/meal-plan-adoptions/${state.adoption.adoption_id}/withdraw`, method: 'POST', data } }; save()
        await perform(current)
      })
    },
    retry() { if (state.pending) return run(current => perform(current)) },
  }
}
