import { request } from './request.js'
import { sessionRevision } from './session.js'
import { scopedStorage, storageContext } from './storage.js'
import { newHealthRequestId } from './health-request-id.js'

export const stageGoalOptions = ['规律三餐', '增加在家用餐', '增加蔬菜搭配', '增加蒸煮菜品', '丰富食物种类']
export function dietStageState() {
  return { value: null, job: null, busy: false, error: '', pending: null }
}
export function currentStageWeek(value, day = value?.today) {
  return value?.weeks?.find(row => row.starts_on <= day && row.ends_on > day) || null
}
export function stageEntryUrl(familyId, memberId) {
  return '/pages/health/diet-stage?familyId=' + encodeURIComponent(familyId) + '&memberId=' + encodeURIComponent(memberId)
}

/** 服务端事实拥有状态；不确定写入保留原键，切换账号丢弃迟到响应。 */
export function createDietStageClient({ state, send = request, revision = sessionRevision,
  context = storageContext, storage = scopedStorage, newId = newHealthRequestId }) {
  let epoch = 0, family = '', member = '', timer = null, selectedStage = '', pollVersion = 0
  const key = () => 'diet-stage-pending:' + family + ':' + member
  const root = () => '/api/health/v1/families/' + encodeURIComponent(family) + '/members/' + encodeURIComponent(member) + '/diet-stage'
  const copy = value => JSON.parse(JSON.stringify(value))
  function stopPolling() { pollVersion++; clearTimeout(timer); timer = null }
  function stop() { epoch++; stopPolling(); state.busy = false }
  function discard() { stop(); state.value = null; state.job = null; state.pending = null; state.error = '' }
  async function run(fn) {
    if (state.busy) return
    const ticket = ++epoch, rev = revision(), owner = context()
    const valid = () => ticket === epoch && rev === revision() && owner === context()
    state.busy = true; state.error = ''
    try { await fn(valid) }
    catch (error) {
      if (!valid()) return
      if ([401, 403, 404, 410].includes(Number(error.code))) {
        state.value = null; state.job = null
      }
      state.error = error.message || '暂时未完成，请重试'
      if ([400, 409, 422].includes(Number(error.code))) {
        state.pending = null; storage.setStorageSync(key(), null)
      }
    } finally {
      if (valid()) state.busy = false
      else if (ticket === epoch) discard()
    }
  }
  async function read(valid) {
    const { data } = await send({ path: root() + (selectedStage ? '?stage_id=' + encodeURIComponent(selectedStage) : '') })
    if (valid()) state.value = data
  }
  async function submit(valid) {
    const frozen = copy(state.pending)
    const { data } = await send(frozen)
    if (!valid()) return
    state.pending = null; storage.setStorageSync(key(), null)
    if (frozen.path.endsWith('/generations')) state.job = data
    else { state.job = null; selectedStage = ''; await read(valid) }
  }
  function write(path, method, body) {
    if (state.pending) {
      state.error = '上次提交结果尚未确认，请先重试原操作'
      return
    }
    stopPolling()
    state.pending = { path, method, data: { ...copy(body), client_request_id: newId() } }
    storage.setStorageSync(key(), state.pending)
    return run(submit)
  }
  const api = {
    stop, discard,
    open(fid, mid) {
      discard(); family = fid; member = mid; selectedStage = ''
      state.pending = storage.getStorageSync(key()) || null
      return run(read)
    },
    reload() { return run(read) },
    history(id = '') { stop(); selectedStage = id; state.job = null; state.value = null; return run(read) },
    generate(kind, { goals = [], note = '' } = {}) {
      return write(root() + '/generations', 'POST', {
        kind, goals, note, stage_id: state.value?.stage?.id || null,
      })
    },
    save(draft, draftId, { next = false } = {}) {
      return write(root(), 'PUT', { goals: draft.goals, actions: draft.actions,
        draft_id: draftId, profile_version: state.value.profile_version,
        expected_version: state.value.stage?.version || 0,
        previous_stage_id: next ? state.value.stage.id : null })
    },
    saveWeek(week, actions) {
      return write(root() + '/' + encodeURIComponent(state.value.stage.id) + '/weeks/' + encodeURIComponent(week.id),
        'PUT', { expected_version: week.version, actions })
    },
    retry() { if (state.pending) return run(submit) },
    job(id) {
      return run(async valid => {
        const { data } = await send({ path: root() + '/generations/' + encodeURIComponent(id) })
        if (valid()) state.job = data
      })
    },
    poll(id, changed = () => {}) {
      stopPolling()
      const mine = pollVersion, stage = selectedStage
      const owner = context(), rev = revision()
      timer = setTimeout(async () => {
        if (mine !== pollVersion || stage !== selectedStage) return
        if (owner !== context() || rev !== revision()) return discard()
        await api.job(id)
        if (mine !== pollVersion || stage !== selectedStage) return
        changed()
        if (state.job?.status === 'pending' && !state.error) api.poll(id, changed)
        if (state.job?.kind === 'week' && state.job.status === 'ready') await api.reload()
      }, 2200)
    },
  }
  return api
}
