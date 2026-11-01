export const FAMILY_CARD_DURATION = 1100
const copy = member => member ? JSON.parse(JSON.stringify(member)) : null
const idOf = member => String(member?.id ?? '')

// Two immutable display snapshots survive the whole transition. No network or writes.
export function createFamilyCardTransition({ changed = () => {}, settled = () => {}, schedule = setTimeout, cancel = clearTimeout } = {}) {
  let members = [], scope = '', timer = null, serial = 0
  let state = { from: null, to: null, busy: false, ticket: 0, direction: 1, queuedId: null }
  const publish = () => changed({ ...state })
  const clearTimer = () => { if (timer !== null) cancel(timer); timer = null }
  function reset(nextMembers, nextScope, preferredId) {
    clearTimer(); serial++; members = nextMembers || []; scope = nextScope
    const member = members.find(m => idOf(m) === String(preferredId ?? '')) || members[0]
    state = { from: null, to: copy(member), busy: false, ticket: serial, direction: 1, queuedId: null }
    publish()
  }
  function select(id) {
    const target = members.find(m => idOf(m) === String(id))
    if (!target) return false
    if (state.busy) {
      state = { ...state, queuedId: idOf(target) === idOf(state.to) ? null : idOf(target) }
      publish(); return true
    }
    if (idOf(target) === idOf(state.to)) return false
    const direction = members.indexOf(target) > members.findIndex(m => idOf(m) === idOf(state.to)) ? 1 : -1
    state = { from: copy(state.to), to: copy(target), busy: true, ticket: ++serial, direction, queuedId: null }
    const ticket = serial, context = scope
    timer = schedule(() => finish(ticket, context), FAMILY_CARD_DURATION + 160)
    publish(); return true
  }
  function finish(ticket, context = scope) {
    if (!state.busy || ticket !== state.ticket || context !== scope) return false
    clearTimer()
    const queuedId = state.queuedId
    state = { ...state, from: null, busy: false, queuedId: null }
    publish(); settled(idOf(state.to))
    if (queuedId !== null) select(queuedId)
    return true
  }
  function dispose() {
    clearTimer(); members = []; scope = ''; serial++
    state = { from: null, to: null, busy: false, ticket: serial, direction: 1, queuedId: null }
    publish()
  }
  return { reset, select, finish, dispose, current: () => ({ ...state }) }
}

export function restrictionProgress(member) {
  const fields = [['allergyStatus', 'allergies'], ['intoleranceStatus', 'intolerances'], ['avoidanceStatus', 'avoidances'], ['doctorStatus', 'clinicianGuidance']]
  const confirmed = fields.filter(([status, field]) => member?.[status] === 'none' || member?.[status] === 'set' &&
    (Array.isArray(member[field]) ? member[field].some(v => String(v).trim()) : String(member[field] || '').trim())).length
  return { confirmed, pending: fields.length - confirmed }
}

export function memberHealthSummary(member) {
  if (member?.healthStatus === 'none') return '没有已知基础病'
  if (member?.healthStatus !== 'set') return '基础健康信息待补充'
  return (member.conditions || []).map(v => v === '其他' ? member.otherCondition || '其他情况待补充' : v).join('、') || '具体健康情况待补充'
}

export function memberGoalSummary(member) {
  return (member?.goals || []).filter(v => typeof v === 'string' && v.trim()).join('、') || '饮食目标待补充'
}
