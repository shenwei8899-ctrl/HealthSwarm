import { request } from './request.js'
import { readDietRecord } from './cloud-meals.js'
import { uploadMealPhoto } from './health-upload.js'
import { sessionRevision } from './session.js'
import { scopedStorage } from './storage.js'
import { newHealthRequestId } from './health-task-flow.js'

const root = '/api/health/v1', clone = value => JSON.parse(JSON.stringify(value))
export const photoState = () => ({ members: [], memberId: '', config: null, uploads: [], jobs: [], drafts: [],
  jobsOffset: 0, draftsOffset: 0, jobsNext: null, draftsNext: null, job: null, draft: null, meal: null,
  calculation: null, dirty: false, conflict: false, pending: null, saved: null, sources: [], busy: false, error: '', notice: '' })

/** 页面持有候选编辑状态，正式记录和任务终态始终由服务端回读。 */
export function createMealPhotoClient({ state, send = request, upload = uploadMealPhoto, revision = sessionRevision,
  storage = scopedStorage, newId = newHealthRequestId } = {}) {
  let generation = 0
  const key = () => 'meal-photo-flow:' + state.memberId
  const checkpoint = () => storage.setStorageSync(key(), { taskId: state.job?.task_id || null,
    draftId: state.draft?.id || null, pending: state.pending && state.pending.operation !== 'patch' ? state.pending : null,
    uploads: state.uploads.map(row => ({ upload_id: row.upload_id })) })
  const discard = () => { generation++; Object.assign(state, photoState()) }
  async function run(action) {
    if (state.busy) return
    const epoch = generation, rev = revision(), current = () => epoch === generation && rev === revision()
    state.busy = true; state.error = ''; state.notice = ''
    try { await action(current) }
    catch (error) {
      if (!current()) return
      if ([401, 403, 404, 410].includes(Number(error.code))) {
        storage.setStorageSync(key(), null); discard(); state.error = '当前成员授权或来源已变化，请重新读取。'
      } else {
        state.error = error.message || '请求未完成'
        if ([400, 409, 413, 422, 429].includes(Number(error.code))) {
          state.pending = null; state.calculation = null; state.conflict = Number(error.code) === 409; checkpoint()
        }
      }
    } finally { if (current()) state.busy = false; else if (epoch === generation) discard() }
  }
  async function list(current) {
    const data = (await send({ path: `${root}/members/${state.memberId}/vision/page?kind=meal&jobs_offset=${state.jobsOffset}&drafts_offset=${state.draftsOffset}` })).data
    if (current()) Object.assign(state, { jobs: data.jobs, drafts: data.drafts, jobsNext: data.jobs_next_offset, draftsNext: data.drafts_next_offset })
  }
  async function readDraft(id, current) {
    const draft = (await send({ path: `${root}/meal-drafts/${encodeURIComponent(id)}` })).data
    if (!current()) return
    if (draft.member_id !== state.memberId || draft.kind !== 'meal') throw new Error('候选所属成员不一致')
    Object.assign(state, { draft, meal: clone(draft.payload), dirty: false, conflict: false, calculation: null, saved: null }); checkpoint()
  }
  async function readJob(id, current) {
    const job = (await send({ path: `${root}/vision-tasks/${encodeURIComponent(id)}` })).data
    if (!current()) return
    state.job = job; checkpoint()
    if (job.result_id && !state.dirty && !state.pending) await readDraft(job.result_id, current)
  }
  async function perform(current) {
    const pending = clone(state.pending)
    const value = (await send(pending.request)).data
    if (!current()) return
    state.pending = null
    if (pending.operation === 'task') { state.job = { task_id: value.task_id }; state.uploads = []; checkpoint(); await readJob(value.task_id, current) }
    if (pending.operation === 'patch') { Object.assign(state, { draft: value, meal: clone(value.payload), dirty: false, calculation: null }); checkpoint() }
    if (pending.operation === 'confirm') {
      state.saved = { id: value.target_ids[0] }; state.calculation = null; state.draft.review_status = 'confirmed'; checkpoint()
      const saved = await readDietRecord(state.memberId,state.saved.id,send)
      if (!current()) return
      state.saved = saved
      state.notice = '已保存为正式饮食记录，可在饮食记录中查看。'
    }
  }
  return {
    discard,
    open(memberId = '') {
      discard()
      return run(async current => {
        const [members, config] = await Promise.all([send({ path: root + '/members' }), send({ path: root + '/configuration' })])
        if (!current()) return
        state.members = members.data.filter(row => row.scopes?.includes('diet_edit')); state.config = config.data
        state.memberId = state.members.find(row => row.id === memberId)?.id || state.members[0]?.id || ''
        if (!state.memberId) return
        const stored = storage.getStorageSync(key()) || {}
        state.pending = stored.pending || null; state.uploads = stored.uploads || []
        await list(current); if (!current()) return
        if (stored.draftId) await readDraft(stored.draftId, current)
        if (current() && stored.taskId) await readJob(stored.taskId, current)
      })
    },
    page(kind, offset) { if (state.busy || !state.memberId || state.pending) return; state[kind + 'Offset'] = offset; return run(list) },
    addPhoto(filePath) {
      if (!state.memberId || state.pending || state.uploads.length >= 3) return
      return run(async current => { const data = await upload(state.memberId, filePath); if (current()) { state.uploads.push(data); checkpoint() } })
    },
    removePhoto(id) { if (state.busy || state.pending) return; state.uploads = state.uploads.filter(row => row.upload_id !== id); checkpoint() },
    start(mealType, eatenAt, accepted) {
      if (state.pending || !state.memberId || !state.uploads.length) return
      return run(async current => {
        const config = (await send({ path: root + '/configuration' })).data
        if (!current()) return
        const prior = state.config; state.config = config
        if (!config.meal.available) throw new Error(config.meal.reason || '识别服务未启用')
        if (!state.members.find(row => row.id === state.memberId)?.scopes?.includes('ai_use')) throw new Error('需要成员 AI 使用授权')
        if (!accepted || prior.policy_version !== config.policy_version || prior.meal.processor !== config.meal.processor) throw new Error('请核对当前处理方和政策后重新勾选同意')
        await send({ path: `${root}/members/${state.memberId}/processing-consents`, method: 'POST', data: {
          purpose: 'meal', accepted: true, processor: config.meal.processor, policy_version: config.policy_version } })
        if (!current()) return
        const id = newId()
        state.pending = { operation: 'task', request: { path: root + '/meal-photo-tasks', method: 'POST', headers: { 'Idempotency-Key': id },
          data: { member_id: state.memberId, upload_ids: state.uploads.map(row => row.upload_id), client_request_id: id, meal_type: mealType, eaten_at: eatenAt } } }
        state.draft = null; state.meal = null; state.calculation = null; state.saved = null; state.dirty = false; state.job = null
        checkpoint(); await perform(current)
      })
    },
    retryPending() { if (state.pending) return run(perform) },
    job(id) { if (!state.pending && !state.dirty) return run(current => readJob(id, current)) },
    cancel() { if (!state.job || state.pending) return; return run(async current => { const value = (await send({ path: `${root}/vision-tasks/${state.job.task_id}/cancel`, method: 'POST' })).data; if (current()) state.job = value }) },
    retryJob() {
      if (state.busy || !state.config?.meal?.available || !state.job || state.pending || !['failed', 'cancelled'].includes(state.job.execution_status)) return
      const id = newId(); state.pending = { operation: 'task', request: { path: `${root}/vision-tasks/${state.job.task_id}/retry`, method: 'POST', headers: { 'Idempotency-Key': id }, data: { client_request_id: id } } }; checkpoint(); return run(perform)
    },
    draft(id) { if (!state.pending) return run(async current => { await readDraft(id, current); if(current()){state.job=null;checkpoint()} }) },
    changed() { state.dirty = true; state.calculation = null; state.saved = null },
    search(query) { return run(async current => { const [foods, recipes] = await Promise.all(['foods','recipes'].map(kind => send({ path: `${root}/${kind}?q=${encodeURIComponent(query)}` }))); if (current()) state.sources = [...foods.data.map(row => ({ ...row, type: 'food' })), ...recipes.data.map(row => ({ ...row, type: 'recipe' }))] }) },
    saveDraft(reason) {
      if (state.busy || state.pending || !state.draft || !state.dirty || state.conflict || !reason.trim()) return
      state.pending = { operation: 'patch', request: { path: `${root}/meal-drafts/${state.draft.id}`, method: 'PATCH', headers: { 'If-Match': `"${state.draft.version}"` }, data: { version: state.draft.version, reason, meal: clone(state.meal) } } }
      return run(perform)
    },
    calculate() {
      if (!state.draft || state.dirty || state.pending || state.conflict || state.draft.review_status !== 'pending_confirmation') return
      return run(async current => { state.calculation = null; const value = (await send({ path: `${root}/meal-drafts/${state.draft.id}/calculate`, method: 'POST', data: { version: state.draft.version } })).data; if (current()) state.calculation = value })
    },
    confirm(acceptIncomplete) {
      if (state.busy || state.dirty || state.pending || !state.calculation || state.calculation.draft_version !== state.draft?.version) return
      if (!state.calculation.complete && !acceptIncomplete) { state.error = '请补齐资料，或明确接受缺失营养保持未知'; return }
      const id = newId(); state.pending = { operation: 'confirm', request: { path: `${root}/meal-drafts/${state.draft.id}/confirm`, method: 'POST', headers: { 'Idempotency-Key': id }, data: { version: state.draft.version, client_request_id: id, calculation_id: state.calculation.calculation_id, accept_incomplete: acceptIncomplete } } }
      checkpoint(); return run(perform)
    },
  }
}
