import { request } from './request.js'
import { sessionRevision } from './session.js'
import { newHealthRequestId } from './health-task-flow.js'

const root = '/api/health/v1'
const copy = value => JSON.parse(JSON.stringify(value))
export function mealDate(value) {
  const time = Date.parse(value)
  return Number.isFinite(time) ? new Date(time + 8 * 3600000).toISOString().slice(0, 10) : '日期未知'
}
export function journalState() {
  return { members: [], memberId: '', records: [], nextOffset: null, offset: 0, detail: null,
    recipes: [], busy: false, error: '', notice: '', pending: null, saved: [], results: [], conflict: false, canEditFailed: false }
}

/** 页面只展示服务端事实；未知写入保留冻结请求以便原键重试。 */
export function createDietJournalClient({ state, send = request, revision = sessionRevision, newId = newHealthRequestId }) {
  let generation = 0
  const ticket = () => `${generation}:${revision()}`
  const clear = () => { generation++; Object.assign(state, journalState()) }
  async function run(action) {
    if (state.busy) return
    const mine = ticket(), context = generation; state.busy = true; state.error = ''; state.notice = ''
    try { await action(() => ticket() === mine) }
    catch (error) {
      if (ticket() !== mine) return
      if ([401, 403, 404, 410].includes(Number(error.code)) || error.code === 'SESSION_CHANGED') {
        clear(); state.error = '当前记录或授权已变化，请重新读取。'
      } else {
        state.error = error.code === 409 ? '记录或请求内容已变化，请重新读取当前记录后再更正。' : error.message
        state.conflict = error.code === 409
        if (error.code === 409 || error.code === 422 || error.code === 400) state.pending = null
      }
    } finally { if (ticket() === mine) state.busy = false; else if (context === generation) clear() }
  }
  async function list(current, offset = 0) {
    const id = state.memberId
    state.records = []; state.detail = null
    const result = (await send({ path: `${root}/members/${id}/diet-logs/page?limit=20&offset=${offset}` })).data
    if (current()) { state.records = result.records; state.nextOffset = result.next_offset; state.offset = offset }
  }
  return {
    discard: clear,
    editFailed() {
      if (state.busy || !state.canEditFailed) return
      state.pending = null; state.canEditFailed = false
      state.notice = '可修改明确未保存的成员后重新提交；已保存成员保持不变。'
    },
    open(memberId = '') {
      clear()
      return run(async current => {
        const result = (await send({ path: root + '/members' })).data
        if (!current()) return
        state.members = result.filter(row => row.scopes?.includes('diet_edit'))
        state.memberId = state.members.find(row => row.id === memberId)?.id || state.members[0]?.id || ''
        if (state.memberId) await list(current)
      })
    },
    select(memberId) {
      if (state.busy || state.pending || !state.members.some(row => row.id === memberId)) return
      generation++; state.memberId = memberId; state.saved = []; state.results = []; state.conflict = false
      return run(current => list(current))
    },
    page(offset = 0) { if (!state.pending && state.memberId) return run(current => list(current, offset)) },
    detail(record) {
      if (state.pending) return
      state.detail = null; state.conflict = false
      return run(async current => {
        const value = (await send({ path: `${root}/members/${state.memberId}/diet-logs/${record.id}/detail` })).data
        if (current()) state.detail = value
      })
    },
    searchRecipes(query) {
      return run(async current => {
        state.recipes = []
        const rows = (await send({ path: root + '/recipes?q=' + encodeURIComponent(query) })).data
        if (current()) state.recipes = rows
      })
    },
    correct(meal, reason, acceptIncomplete) {
      if (state.busy || !state.detail || state.conflict) return
      if (!state.pending) {
        const data = { expected_version: state.detail.source_version, client_request_id: newId(), meal: copy(meal),
          reason, accept_incomplete: acceptIncomplete }
        state.pending = { path: `${root}/diet-logs/${state.detail.id}`, method: 'PATCH', data,
          headers: { 'Idempotency-Key': data.client_request_id, 'If-Match': `"${data.expected_version}"` } }
      }
      return run(async current => {
        const value = (await send(copy(state.pending))).data
        if (!current()) return
        state.detail = value; state.pending = null; state.saved = [value]; state.conflict = false
        state.records = state.records.map(row => row.id === value.id ? value : row)
        state.notice = '已保留原记录并重新计算，旧分析已失效。'
      })
    },
    save(meals, acceptIncomplete) {
      if (state.busy) return
      if (!state.pending) {
        meals = meals.filter(row => !state.saved.some(saved => saved.member_id === row.memberId))
        if (!meals.length || meals.some(row => !state.members.some(m => m.id === row.memberId))) return
        const groupId = newId()
        state.pending = { path: root + '/family-meal-recordings', method: 'POST',
          headers: { 'Idempotency-Key': groupId }, data: { group_id: groupId,
            members: meals.map(row => ({ member_id: row.memberId, client_request_id: newId(), meal: copy(row.meal), accept_incomplete: acceptIncomplete })) } }
      }
      return run(async current => {
        state.canEditFailed = false
        const request = copy(state.pending), value = (await send(request)).data
        if (!current()) return
        state.results = value.results
        const saved = value.results.filter(row => row.status === 'saved')
        state.saved = [...state.saved.filter(row => !saved.some(next => next.member_id === row.member_id)), ...saved]
        const failed = new Set(value.results.filter(row => row.status === 'failed').map(row => row.member_id))
        state.pending = failed.size ? { ...request, data: { ...request.data, members: request.data.members.filter(row => failed.has(row.member_id)) } } : null
        state.canEditFailed = failed.size > 0 && value.results.filter(row => row.status === 'failed').every(row => row.code !== 'idempotency_conflict')
        state.notice = failed.size ? `已保存${state.saved.length}人，${failed.size}人未保存，可原样重试或修改未保存项。` : `已保存${state.saved.length}人的实际摄入。`
      })
    },
  }
}
