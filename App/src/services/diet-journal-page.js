import { request } from './request.js'
import { scopedStorage, storageContext } from './storage.js'
import { newHealthRequestId } from './health-request-id.js'
import { mealDay } from './cloud-meals.js'

const root = '/api/health/v1'
const clone = value => JSON.parse(JSON.stringify(value))
export function journalPageState() {
  return { members: [], memberId: '', day: mealDay(new Date().toISOString()), records: [], recordedDates: [],
    detail: null, busy: false, saving: false, error: '', pending: null, recoveryError: '', denied:false }
}

export function createJournalPageClient({ state, send = request, storage = scopedStorage, context = storageContext, newId = newHealthRequestId }) {
  let generation = 0
  const key = id => 'diet-journal-operation:' + id
  function hide() {
    generation++
    Object.assign(state, journalPageState(), { day: state.day })
  }
  function fail(error) {
    if ([401, 403, 404, 410].includes(Number(error.code)) || error.code === 'SESSION_CHANGED') {hide();state.denied=true}
    state.error = Number(error.code) === 409 ? '记录已变化，请重新打开后修改。' : error.message
  }
  async function load(memberId = state.memberId, day = state.day) {
    if (state.saving) return
    const mine = ++generation, scope = context()
    const current = () => mine === generation && scope === context()
    state.busy = true
    state.error = ''
    state.detail = null
    state.records = []
    state.recordedDates = []
    state.day = day
    try {
      // A committed deletion can disappear from the list before its response arrives.
      // Read its current receipt independently of the active-record detail endpoint.
      state.recoveryError = ''
      for (const storedKey of storage.getStorageInfoSync?.().keys || []) {
        if (!storedKey.startsWith('diet-journal-operation:')) continue
        const pending = storage.getStorageSync(storedKey)
        if (!pending?.path?.endsWith('/withdraw')) continue
        try {
          const id = storedKey.slice('diet-journal-operation:'.length)
          const { data } = await send({ path: `${root}/diet-logs/${encodeURIComponent(id)}/status` })
          if (!current()) return
          if (data.id === id && data.status === 'withdrawn') storage.setStorageSync(storedKey, null)
        } catch (error) {
          if (!current()) return
          state.recoveryError = '有一条删除操作待核对，请重新读取。'
        }
      }
      if (!state.members.length) {
        const { data } = await send({ path: root + '/members' })
        if (!current()) return
        state.members = data.filter(member => member.scopes?.includes('diet_edit'))
      }
      if (!memberId) memberId = state.members.find(member => member.is_owner && member.relationship_label === '本人')?.id || state.members[0]?.id || ''
      if (!state.members.length) { state.memberId = ''; return }
      if (memberId !== 'all' && !state.members.some(member => member.id === memberId)) throw new Error('当前成员不可读取饮食记录。')
      state.memberId = memberId
      const members = memberId === 'all' ? state.members : state.members.filter(member => member.id === memberId)
      const responses = await Promise.all(members.map(async member => {
        const { data } = await send({ path: `${root}/members/${member.id}/diet-journal?day=${encodeURIComponent(day)}` })
        if (!Array.isArray(data.records) || !Array.isArray(data.recorded_dates)) throw new Error('饮食日记返回不完整，请重新读取。')
        return { member, data }
      }))
      if (!current()) return
      state.records = responses.flatMap(({ member, data }) => data.records.map(record => ({ ...record, member_id: member.id })))
      state.recordedDates = [...new Set(responses.flatMap(({ data }) => data.recorded_dates))]
    } catch (error) { if (current()) fail(error) }
    finally {
      if (mine === generation) {
        if (scope !== context()) hide()
        else state.busy = false
      }
    }
  }
  async function detail(record) {
    if (state.saving) return
    const mine = ++generation, scope = context()
    state.busy = true
    state.error = ''
    state.detail = null
    try {
      const { data } = await send({ path: `${root}/members/${record.member_id}/diet-logs/${record.id}/detail` })
      if (mine !== generation || scope !== context()) return
      if (data.id !== record.id || !data.snapshot?.meal || !Number.isInteger(data.source_version)) throw new Error('记录详情返回不完整。')
      state.detail = { ...data, member_id: record.member_id }
      state.pending = storage.getStorageSync(key(record.id)) || storage.getStorageSync('meal-correction:' + record.id) || null
    } catch (error) { if (mine === generation && scope === context()) fail(error) }
    finally {
      if (mine === generation) {
        if (scope !== context()) hide()
        else state.busy = false
      }
    }
    return state.detail
  }
  async function mutate(operation, meal) {
    if (state.saving || !state.detail) return null
    const record = state.detail, scope = context(), mine = generation
    if (!state.pending) {
      const requestId = newId()
      state.pending = {
        path: `${root}/diet-logs/${record.id}` + (operation === 'withdraw' ? '/withdraw' : ''),
        method: operation === 'withdraw' ? 'POST' : 'PATCH',
        headers: { 'Idempotency-Key': requestId, 'If-Match': '"' + record.source_version + '"' },
        data: { client_request_id: requestId, expected_version: record.source_version,
          ...(operation === 'withdraw' ? {} : { meal: clone(meal), reason: '用户修改饮食记录', accept_incomplete: true }) },
      }
      storage.setStorageSync(key(record.id), state.pending)
    }
    state.saving = true
    state.error = ''
    try {
      const { data } = await send(clone(state.pending))
      if (scope !== context() || mine !== generation) return null
      const withdrawing = state.pending.path.endsWith('/withdraw')
      if (data.id !== record.id || !Number.isInteger(data.source_version) || (withdrawing ? data.status !== 'withdrawn' : !data.snapshot?.meal)) throw new Error('保存回执尚未核对，请重试原请求。')
      storage.setStorageSync(key(record.id), null)
      storage.setStorageSync('meal-correction:' + record.id, null)
      state.pending = null
      state.detail = null
      return { withdrawn: withdrawing, day: withdrawing ? state.day : mealDay(data.snapshot.meal.eaten_at) }
    } catch (error) {
      if (scope !== context() || mine !== generation) return null
      if ([400, 409, 422].includes(Number(error.code))) {
        storage.setStorageSync(key(record.id), null)
        storage.setStorageSync('meal-correction:' + record.id, null)
        state.pending = null
        if (Number(error.code) === 409) state.detail = null
      }
      fail(error)
      return null
    } finally {
      if (mine === generation) {
        if (scope !== context()) hide()
        else state.saving = false
      }
    }
  }
  function resumeCreation(memberId, day, mealType) {
    state.pending = storage.getStorageSync(`diet-journal-create:${memberId}:${day}:${mealType}`) || null
    return state.pending
  }
  async function create(memberId, meal) {
    if (state.saving || !state.members.some(member=>member.id===memberId)) return null
    const scope=context(),mine=generation
    const storedKey=`diet-journal-create:${memberId}:${mealDay(meal.eaten_at)}:${meal.meal_type}`
    if (!state.pending) {
      const id=newId()
      state.pending={path:root+'/diet-journal-recordings',method:'POST',headers:{'Idempotency-Key':id},data:{member_id:memberId,client_request_id:id,meal:clone(meal),accept_incomplete:true}}
      storage.setStorageSync(storedKey,state.pending)
    }
    state.saving=true;state.error=''
    try {
      const {data}=await send(clone(state.pending))
      if (scope!==context()||mine!==generation)return null
      if (!data.id||!Number.isInteger(data.source_version)||!data.snapshot?.meal)throw new Error('保存回执尚未核对，请重试原请求。')
      storage.setStorageSync(storedKey,null);state.pending=null
      return {id:data.id,day:mealDay(data.snapshot.meal.eaten_at)}
    } catch(error) {
      if(scope!==context()||mine!==generation)return null
      if([400,409,422].includes(Number(error.code))){storage.setStorageSync(storedKey,null);state.pending=null}
      fail(error);return null
    } finally {
      if(mine===generation){if(scope!==context())hide();else state.saving=false}
    }
  }
  return { load, detail, mutate, create, resumeCreation, hide }
}
