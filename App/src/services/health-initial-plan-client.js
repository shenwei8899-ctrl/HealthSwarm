import { request } from './request.js'
import { sessionRevision } from './session.js'
import { scopedStorage } from './storage.js'
import { createHealthTaskFlow, newHealthRequestId } from './health-task-flow.js'

const root = '/api/health/v1'
const copy = value => JSON.parse(JSON.stringify(value))
export const initialPlanState = () => ({ memberId: '', date: '', selection: null, loading: false, saving: false,
  error: '', notice: '', task: {}, pending: null, saved: null })

/** 单日选择复用健康Run；确认写入保留原请求键，页面恢复只读原任务。 */
export function createInitialPlanClient({ state, send = request, storage = scopedStorage, revision = sessionRevision,
  newId = newHealthRequestId, flowOptions = {}, onSaved = () => {} }) {
  let generation = 0
  const ticket = () => `${generation}:${revision()}`
  const key = () => `initial-plan-save:${state.memberId}:${state.date}`
  const flow = createHealthTaskFlow({ ...flowOptions, send, storage, revision, newId,
    onChange(task) { state.task = task; if (task.invalidated) { state.saved = null; state.pending = null; storage.setStorageSync(key(), null) } } })
  function hide() { generation++; flow.hide(); Object.assign(state, initialPlanState()) }
  function clearChangedSession(context, mine) {
    if (context !== generation || mine === ticket()) return false
    hide(); state.error = '登录或账号已变化，请重新进入计划页面。'; return true
  }
  function preview() {
    const data = state.task.result?.kind === 'meal_plan_preview' ? state.task.result.data : null
    return data?.status === 'ready' && data.member_id === state.memberId && data.preview_id &&
      data.plan_snapshot?.plan_date === state.date && data.scope === 'initial_single_plan' ? data : null
  }
  function failure(error) {
    state.error = error.message || '暂时无法读取计划，请重试。'
    if ([401,403,404,409,410].includes(Number(error.code)) || error.code === 'SESSION_CHANGED') {
      state.saved = null; state.pending = null; state.selection = null; storage.setStorageSync(key(), null); flow.hide()
    }
  }
  async function open(memberId, date) {
    hide(); state.memberId = memberId; state.date = date
    const mine = ticket(), context = generation; state.loading = true
    try {
      const { data } = await send({ path: `${root}/members/${memberId}/initial-meal-plan-context?plan_date=${encodeURIComponent(date)}` })
      if (mine !== ticket()) return
      if (data.member_id !== memberId || data.plan_date !== date) throw new Error('计划范围与当前选择不一致')
      state.selection = data.selection; state.notice = data.message || ''
      if (!data.selection) return
      const pending = storage.getStorageSync(key())
      if (pending?.previewId && pending?.requestId) state.pending = pending
      await flow.open(memberId, 'initial_meal_preview', data.selection)
    } catch (error) { if (mine === ticket()) failure(error) }
    finally { if (!clearChangedSession(context, mine) && mine === ticket()) state.loading = false }
  }
  async function generate(query = '请按本线程已绑定的成员、日期、档案和批准规则生成完整早餐、午餐、晚餐。先读取初始配餐上下文，再调用预览工具，使用真实回执返回结果。') {
    if (!state.selection || state.loading || state.saving || state.pending || state.task.busy || state.task.loading) return
    if (state.task.requestId && !['completed','failed','cancelled','interrupted','rejected'].includes(state.task.status)) return
    const mine = ticket(), context = generation; state.error = ''; state.saved = null
    if (!state.task.entry?.thread_id) await flow.createEntry()
    if (mine === ticket() && state.task.entry?.thread_id) await flow.submit(query)
    clearChangedSession(context, mine)
  }
  async function confirmSave() {
    if (state.loading || state.saving || state.saved || !state.selection || state.task.busy) return
    const mine = ticket(), context = generation; state.saving = true; state.error = ''
    try {
      if (!state.pending) {
        const shown = preview()
        if (!shown) throw new Error('请先生成并核对完整三餐。')
        await flow.refresh()
        if (mine !== ticket()) return
        const current = preview()
        if (!current || current.preview_id !== shown.preview_id) throw new Error('计划或来源已变化，请重新读取后确认。')
        state.pending = { previewId: current.preview_id, requestId: newId() }
        storage.setStorageSync(key(), copy(state.pending))
      }
      const pending = copy(state.pending)
      const { data } = await send({ path: `${root}/members/${state.memberId}/initial-meal-plans`, method: 'POST',
        headers: { 'Idempotency-Key': pending.requestId }, data: { client_request_id: pending.requestId, preview_id: pending.previewId } })
      if (mine !== ticket()) return
      if (!data.plan_id || data.member_id !== state.memberId || data.plan_date !== state.date || data.applied_version !== 1) throw new Error('保存回执待核对，请用原请求重试。')
      state.saved = data; state.pending = null; storage.setStorageSync(key(), null)
      onSaved(data)
    } catch (error) { if (mine === ticket()) failure(error) }
    finally { if (!clearChangedSession(context, mine) && mine === ticket()) state.saving = false }
  }
  return { open, hide, generate, confirmSave, preview, flow }
}
