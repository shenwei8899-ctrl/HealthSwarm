export function archiveState() {
  return { families: [], family: null, member: null, measurements: [], history: [], historyTotal: 0, measurementTotal: 0, busy: false, blocked: false, error: '', notice: '', pendingMeasurement: null }
}
// All private page state stays in memory and belongs to one current session and selection.
export function createFamilyArchivesClient({ send, session, state, storage }) {
  let generation = 0
  const ticket = () => ({ generation, revision: session.revision() })
  const current = t => t.generation === generation && t.revision === session.revision()
  const clearData = () => { state.family = null; state.member = null; state.measurements = []; state.history = []; state.historyTotal = 0; state.measurementTotal = 0; state.pendingMeasurement = null }
  const pendingKey = () => `family-measurement-intent:${state.family?.id}:${state.member?.id}`
  function discard() { generation++; clearData(); state.families = []; state.busy = false; state.error = ''; state.notice = ''; state.blocked = false }
  function failure(error, t, write) {
    if (t.generation !== generation) return
    if (!current(t) || [401, 403, 404, 410].includes(Number(error.code))) { clearData(); state.families = []; state.blocked = true }
    else if (write && (error.code === 409 || error.code === 'NETWORK_ERROR' || Number(error.code) >= 500)) state.blocked = true
    state.error = error.code === 409 ? '资料已被更新，请重新读取后再修改。' : write && state.blocked ? '操作结果或访问权限已变化，请重新读取后再操作。' : error.message
  }
  async function refresh(familyId = session.read()?.householdId, memberId = state.member?.id) {
    discard(); const t = ticket(); state.busy = true; state.blocked = true
    try {
      if (!session.read()?.token) throw Object.assign(new Error('请先登录健康业务账号'), { code: 401 })
      const rows = (await send({ path: '/api/family' })).data
      if (!current(t)) return
      if (!Array.isArray(rows)) throw new Error('家庭列表格式异常')
      state.families = rows
      if (!familyId || !rows.some(row => row.id === familyId)) return
      const family = (await send({ path: '/api/family/' + encodeURIComponent(familyId) })).data
      if (!current(t)) return
      if (family?.id !== familyId || !Array.isArray(family.members)) throw new Error('家庭档案格式异常')
      state.family = family
      const member = memberId ? family.members.find(row => row.id === memberId && row.is_active) : family.members.find(row => row.is_self && row.is_active)
      if (!member) throw Object.assign(new Error('指定成员已不可访问，请返回家庭档案核查。'), {code:404})
      if (member.profile_access !== 'family_shared') throw Object.assign(new Error('该档案当前不可读取'), { code: 403 })
      state.member = member
      state.pendingMeasurement = storage?.getStorageSync(pendingKey()) || null
      const base = memberPath()
      const [history, measurements] = await Promise.all([send({ path: base + '/history?limit=20' }), send({ path: base + '/measurements?days=366&limit=100&include_voided=true' })])
      if (!current(t)) return
      if (!Array.isArray(history.data?.items) || !Array.isArray(measurements.data?.items)) throw new Error('历史记录格式异常')
      state.history = history.data.items; state.historyTotal = history.data.total
      state.measurements = measurements.data.items; state.measurementTotal = measurements.data.total
      state.blocked = false
    } catch (error) { failure(error, t, false) }
    finally {
      if (t.generation === generation) { if (!current(t)) { clearData(); state.families = [] }; state.busy = false }
    }
  }
  function memberPath() {
    if (!state.family?.id || !state.member?.is_active || state.member.profile_access !== 'family_shared') throw new Error('请先选择可访问的成员')
    return '/api/family/' + encodeURIComponent(state.family.id) + '/members/' + encodeURIComponent(state.member.id)
  }
  async function write(suffix, method, data) {
    if (state.busy || state.blocked) return
    const t = ticket(), familyId = state.family?.id, memberId = state.member?.id
    state.busy = true; state.error = ''; state.notice = ''
    try {
      await send({ path: memberPath() + suffix, method, data })
      if (!current(t)) return
      await refresh(familyId, memberId)
      if (!state.error && state.member?.id === memberId) state.notice = '已保存，并重新读取服务端记录。'
      return true
    } catch (error) { failure(error, t, true) }
    finally { if (t.generation === generation) { if (!current(t)) clearData(); state.busy = false } }
  }
  async function saveMeasurement(data, record) {
    if (state.busy || state.blocked) return
    if (record) {
      if (!state.measurements.some(row => row.id === record.id && !row.voided_at)) return
      return write('/measurements/' + encodeURIComponent(record.id), 'PUT', {...data,expected_version:record.version})
    }
    const revision=session.revision(),familyId=state.family?.id,memberId=state.member?.id,key=pendingKey(),pending=state.pendingMeasurement
    if(pending&&JSON.stringify(pending)!==JSON.stringify(data)){state.error='上次实测记录结果尚未确认，请先恢复原请求。';return}
    state.pendingMeasurement=JSON.parse(JSON.stringify(pending||data))
    storage?.setStorageSync(key,state.pendingMeasurement)
    const saved=await write('/measurements','POST',state.pendingMeasurement)
    if(revision!==session.revision()||state.family?.id!==familyId||state.member?.id!==memberId)return
    if(saved){storage?.setStorageSync(key,null);state.pendingMeasurement=null}
    else if(state.pendingMeasurement&&!state.blocked){storage?.setStorageSync(key,null);state.pendingMeasurement=null}
  }
  return { refresh, discard, saveMeasurement,
    async retryMeasurement() {
      if(state.busy||!state.pendingMeasurement)return
      const data=JSON.parse(JSON.stringify(state.pendingMeasurement)),fid=state.family.id,mid=state.member.id
      await refresh(fid,mid)
      if(!state.blocked&&state.family?.id===fid&&state.member?.id===mid)await saveMeasurement(data)
    },
    saveProfile(profile) { return write('', 'PUT', { expected_version: state.member?.version, profile }) },
    saveIdentity(name, relationship) { return write('/relationship', 'PUT', { expected_version: state.member?.relationship_version, name, relationship }) },
    voidMeasurement(record, reason) {
      if (!state.measurements.some(row => row.id === record.id && !row.voided_at)) return
      return write('/measurements/' + encodeURIComponent(record.id) + '/void', 'POST', { expected_version: record.version, reason })
    },
  }
}
