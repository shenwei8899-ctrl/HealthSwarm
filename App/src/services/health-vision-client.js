import { request, uploadHealthFile } from './request.js'
import { sessionRevision } from './session.js'
import { scopedStorage } from './storage.js'
import { newHealthRequestId } from './health-task-flow.js'
import { mealInput } from './health-meal-input.js'
import { readDietRecord } from './cloud-meals.js'

const root = '/api/health/v1'
const copy = value => JSON.parse(JSON.stringify(value))
const uncertain = error => error.code === 'NETWORK_ERROR' || Number(error.code) >= 500
export function visionState() {
  return { members: [], memberId: '', kind: 'report', busy: false, error: '', notice: '', jobs: [], drafts: [],
    jobsOffset: 0, draftsOffset: 0, jobsNext: null, draftsNext: null, job: null, draft: null, calculation: null,
    recipes: [], pending: null, blocked: false, policy: null, consent: false, progress: 0, uploading: false, confirmation: null,
    records: [], limits: {image_mb:10,pdf_mb:20,report_pages:20,meal_images:3} }
}

/** 文件、任务、草稿与确认分别回读，页面切换和失权后不接收旧响应。 */
export function createHealthVisionClient({ state, send = request, upload = uploadHealthFile, revision = sessionRevision,
  storage = scopedStorage, newId = newHealthRequestId }) {
  let generation = 0, abortUpload = null
  const ticket = () => `${generation}:${revision()}`
  const key = () => `vision-intent:${state.memberId}:${state.kind}`
  const draftPath = id => `${root}/${state.kind === 'report' ? 'report-extractions' : 'meal-drafts'}/${id}`
  function discard() { generation++; abortUpload?.(); abortUpload = null; Object.assign(state, visionState()) }
  function saveIntent() { storage.setStorageSync(key(), state.pending ? copy(state.pending) : null) }
  async function run(action) {
    if (state.busy) return
    const mine = ticket(), context = generation
    state.busy = true; state.error = ''; state.notice = ''
    try { await action(() => mine === ticket()) }
    catch (error) {
      if (mine !== ticket()) return
      if ([401, 403, 404, 410].includes(Number(error.code)) || error.code === 'SESSION_CHANGED') {
        saveIntentClear(); discard(); state.error = '当前资料或授权已变化，请重新读取成员。'
      } else {
        state.error = Number(error.code) === 409 ? '版本或来源已变化，请重新读取候选并核对。' : error.message
        if (!uncertain(error) && state.pending) { state.pending = null; saveIntent() }
        if (Number(error.code) === 409) { state.blocked = true; state.calculation = null }
        else if (!uncertain(error)) state.blocked = false
        if (uncertain(error) && state.blocked && !state.pending) state.notice = '保存结果未确认，请刷新候选列表并重新读取核对。'
      }
    } finally { if (mine === ticket()) { state.busy = false; state.uploading = false; abortUpload = null } else if (context === generation) discard() }
  }
  function saveIntentClear() { if (state.memberId) storage.setStorageSync(key(), null) }
  async function page(current, jobsOffset = state.jobsOffset, draftsOffset = state.draftsOffset) {
    const { data } = await send({ path: `${root}/members/${state.memberId}/vision/page?kind=${state.kind}&jobs_limit=20&jobs_offset=${jobsOffset}&drafts_limit=20&drafts_offset=${draftsOffset}` })
    if (!current()) return
    if (!Array.isArray(data.jobs) || !Array.isArray(data.drafts)) throw new Error('任务列表格式异常，请重试')
    state.jobs = data.jobs; state.drafts = data.drafts; state.jobsNext = data.jobs_next_offset; state.draftsNext = data.drafts_next_offset
    state.jobsOffset = jobsOffset; state.draftsOffset = draftsOffset
  }
  async function loadDraft(current, id) {
    state.draft = null; state.calculation = null; state.blocked = true
    const { data } = await send({ path: draftPath(id) })
    if (!current()) return
    if (data.id !== id || data.member_id !== state.memberId || data.kind !== state.kind || !Number.isInteger(data.version)) throw new Error('候选与当前成员不一致')
    state.draft = data; state.calculation = null; state.blocked = false; state.confirmation = null
  }
  async function receive(current, intent, value) {
    if (!current()) return
    if (intent.operation === 'confirm') {
      if (value.review_status !== 'confirmed' || !Array.isArray(value.target_ids) || !value.confirmation_id) throw Object.assign(new Error('确认回执待核对，请重试原请求'), { code: 'NETWORK_ERROR' })
      state.draft = null; state.calculation = null
      state.pending={operation:'read',receipt:copy(value)};saveIntent()
      await readConfirmed(current,value)
      return
    } else {
      if (!value.task_id) throw Object.assign(new Error('任务回执待核对，请重试原请求'), { code: 'NETWORK_ERROR' })
      state.job = value; state.notice = '任务已提交，可读取进度；离开后从任务列表恢复。'
    }
    state.pending = null; saveIntent()
    await page(current)
  }
  async function perform(current) {
    const intent = copy(state.pending)
    if(intent.operation==='read'){await readConfirmed(current,intent.receipt);return}
    const { data } = await send(intent.request)
    await receive(current, intent, data)
  }
  async function readConfirmed(current, receipt) {
    let records=[]
    if(state.kind==='meal') {
      records=await Promise.all(receipt.target_ids.map(id=>readDietRecord(state.memberId,id,send)))
    } else if(receipt.target_ids.length) {
      const {data}=await send({path:`${root}/members/${state.memberId}/observations`})
      if(!Array.isArray(data))throw new Error('正式指标返回不完整，请重新读取。')
      records=receipt.target_ids.map(id=>data.find(row=>row.id===id))
      if(records.some(row=>!row))throw Object.assign(new Error('确认已受理，正式指标尚未全部读到，请恢复原读取。'),{code:'NETWORK_ERROR'})
    }
    if(!current())return
    state.records=records;state.confirmation=receipt;state.pending=null;saveIntent()
    state.notice='已确认并重新读取正式记录。'
    await page(current)
  }
  function prepare(operation, path, data) {
    state.pending = { operation, request: { path, method: 'POST', data,
      headers: { 'Idempotency-Key': data.client_request_id } } }
    saveIntent()
  }
  return {
    discard,
    cancelUpload() { abortUpload?.() },
    open(memberId, kind = 'report') {
      discard(); state.kind = kind === 'meal' ? 'meal' : 'report'
      return run(async current => {
        const { data } = await send({ path: root + '/members' })
        if (!current()) return
        state.members = data.filter(row => row.scopes?.includes(state.kind === 'report' ? 'report_view' : 'diet_edit'))
        state.memberId = memberId ? state.members.find(row => row.id === memberId)?.id || '' : state.members[0]?.id || ''
        if (!state.memberId) { state.notice = '选定成员当前不可读取，请选择当前用途已授权成员。'; return }
        const pending = storage.getStorageSync(key())
        if (pending?.operation==='read'&&pending.receipt?.confirmation_id || pending?.request?.data?.client_request_id && pending.request.path.startsWith(root + '/')) state.pending = pending
        const config = (await send({ path: root + '/configuration' })).data
        if (!current()) return
        const policy = config?.[state.kind]
        state.limits={...state.limits,...config.limits}
        state.policy = policy?.available === true && policy.processor && config.policy_version
          ? { processor: policy.processor, policy_version: config.policy_version } : null
        await page(current, 0, 0)
      })
    },
    page(jobsOffset, draftsOffset) { return run(current => page(current, jobsOffset, draftsOffset)) },
    acceptConsent() {
      if (!state.policy || !state.memberId || state.pending) return
      return run(async current => {
        const { data } = await send({ path: `${root}/members/${state.memberId}/processing-consents`, method: 'POST',
          data: { purpose: state.kind, accepted: true, ...state.policy } })
        if (current() && data.accepted === true) state.consent = true
      })
    },
    recognize(files, meal = {}) {
      if (state.pending || !state.consent || !files.length) return
      if(files.length>(state.kind==='meal'?state.limits.meal_images:state.limits.report_pages)){state.error='文件数量超过当前识别限制。';return}
      return run(async current => {
        for(const file of files) {
          const pdf=/\.pdf$/i.test(file.name||file.path||'')
          if(pdf&&state.kind!=='report')throw new Error('PDF仅用于报告识别。')
          const limit=pdf?state.limits.pdf_mb:state.limits.image_mb
          if(Number(file.size)>limit*1024*1024)throw new Error(`${pdf?'PDF':'图片'}不能超过${limit}MiB。`)
        }
        const uploads = []
        for (const file of files) {
          if (!current()) return
          if (!file.uploadId) {
            state.uploading = true
            const value = await upload({ filePath: file.path, fileName:file.name, limits:state.limits, size: file.size, memberId: state.memberId, purpose: state.kind,
              onProgress: progress => { if (current()) state.progress = progress }, onCancelReady: abort => { if (current()) abortUpload = abort } })
            if (!current()) return
            abortUpload = null; state.uploading = false
            file.uploadId = value.upload_id
          }
          uploads.push(file.uploadId)
        }
        if (!current()) return
        const data = { member_id: state.memberId, upload_ids: uploads, client_request_id: newId(),
          ...(state.kind === 'meal' ? { meal_type: meal.meal_type || 'lunch', eaten_at: meal.eaten_at || new Date().toISOString() } : {}) }
        prepare('task', `${root}/${state.kind === 'report' ? 'report-tasks' : 'meal-photo-tasks'}`, data)
        await perform(current)
      })
    },
    retryPending() { if (state.pending) return run(current => perform(current)) },
    readJob(job) {
      return run(async current => {
        const { data } = await send({ path: `${root}/vision-tasks/${job.task_id}` })
        if (!current()) return
        if (data.task_id !== job.task_id || data.kind !== state.kind) throw new Error('任务归属不一致')
        state.job = data
        if (data.result_id) await loadDraft(current, data.result_id)
      })
    },
    cancel(job) {
      return run(async current => {
        await send({ path: `${root}/vision-tasks/${job.task_id}/cancel`, method: 'POST' })
        if (current()) { state.notice = '已请求取消，请重新读取最终状态。'; await page(current) }
      })
    },
    retry(job) {
      if (state.pending || !['failed','cancelled'].includes(job.execution_status)) return
      return run(async current => {
        prepare('task', `${root}/vision-tasks/${job.task_id}/retry`, { client_request_id: newId() })
        await perform(current)
      })
    },
    reprocessPages(indices) {
      if(state.kind!=='report'||!state.draft||state.draft.review_status!=='pending_confirmation'||state.pending||state.blocked||!indices.length)return
      const selected=[...new Set(indices)].sort((a,b)=>a-b)
      if(selected.some(index=>!state.draft.payload.pages?.some(page=>page.page_index===index&&page.status==='failed')))return
      return run(async current=>{
        const data={draft_id:state.draft.id,version:state.draft.version,client_request_id:newId(),page_indices:selected}
        prepare('task',root+'/report-page-tasks',data)
        state.pending.request.headers['If-Match']=`"${data.version}"`;saveIntent()
        state.draft=null;state.calculation=null;state.confirmation=null;state.records=[]
        await perform(current)
      })
    },
    draft(row) { if (!state.pending) return run(current => loadDraft(current, row.id)) },
    searchRecipes(query = '') {
      return run(async current => { const { data } = await send({ path: root + '/recipes?q=' + encodeURIComponent(query) }); if (current()) state.recipes = data })
    },
    manual() {
      if (state.pending || !state.memberId || state.blocked) return
      return run(async current => {
        const data = { member_id: state.memberId, kind: state.kind, [state.kind]: state.kind === 'report'
          ? { fields: [] } : { meal_type: 'lunch', eaten_at: new Date().toISOString(), items: [] } }
        // 人工草稿无幂等契约，结果未知后通过列表回读，不自动重复创建。
        state.blocked = true
        const result = (await send({ path: root + '/manual-drafts', method: 'POST', data })).data
        if (current()) { await loadDraft(current, result.id); await page(current) }
      })
    },
    saveDraft(payload, reason) {
      if (!state.draft || state.blocked || state.pending || !reason.trim()) return
      return run(async current => {
        state.calculation = null; state.blocked = true
        const data = { version: state.draft.version, reason, [state.kind]: state.kind === 'meal' ? mealInput(payload) : copy(payload) }
        const result = (await send({ path: draftPath(state.draft.id), method: 'PATCH', data,
          headers: { 'If-Match': `"${data.version}"` } })).data
        if (current()) { state.draft = result; state.blocked = false; state.notice = '候选修改已保存，请核对后再确认正式记录。' }
      })
    },
    calculate() {
      if (!state.draft || state.kind !== 'meal' || state.blocked || state.pending) return
      return run(async current => {
        const { data } = await send({ path: draftPath(state.draft.id) + '/calculate', method: 'POST', data: { version: state.draft.version } })
        if (current() && data.draft_version === state.draft.version) state.calculation = data
      })
    },
    confirm(acceptIncomplete) {
      if (!state.draft || state.blocked || state.pending || (state.kind === 'meal' && !state.calculation)) return
      return run(async current => {
        const data = { version: state.draft.version, client_request_id: newId(), accept_incomplete: acceptIncomplete,
          ...(state.kind === 'meal' ? { calculation_id: state.calculation.calculation_id } : {}) }
        prepare('confirm', draftPath(state.draft.id) + '/confirm', data)
        await perform(current)
      })
    },
  }
}
