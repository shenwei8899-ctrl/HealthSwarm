export const FAMILY_CARD_DURATION = 320
const copy = member => member ? JSON.parse(JSON.stringify(member)) : null
const idOf = member => String(member?.id ?? '')
const clamp = value => Math.max(0, Math.min(1, value))

// Snapshots belong to one gesture; only a completed turn changes selection.
export function createFamilyCardTransition({ changed = () => {}, settled = () => {}, schedule = setTimeout, cancel = clearTimeout } = {}) {
  let members = [], scope = '', timer = null, startTimer = null, serial = 0
  const idle = member => ({ from: null, to: member, busy: false, phase: 'idle', progress: 0, duration: 0, ticket: serial, direction: 1, queuedId: null, commit: false })
  let state = idle(null)
  const publish = () => changed({ ...state })
  function clearTimers() {
    if (timer !== null) cancel(timer)
    if (startTimer !== null) cancel(startTimer)
    timer = startTimer = null
  }
  function reset(nextMembers, nextScope, preferredId) {
    clearTimers(); serial++; members = nextMembers || []; scope = nextScope
    state = idle(copy(members.find(m => idOf(m) === String(preferredId ?? '')) || members[0]))
    publish()
  }
  /** 拖动只预览相邻成员，不提交选择，也不启动完成计时。 */
  function preview(id, direction, progress) {
    if (state.busy && state.phase !== 'dragging') return false
    const target = members.find(m => idOf(m) === String(id))
    const origin = state.busy ? state.from : state.to
    if (!target || !origin || idOf(target) === idOf(origin)) return false
    if (!state.busy) state = { ...state, from: copy(origin), busy: true, phase: 'dragging', ticket: ++serial }
    state = { ...state, to: idOf(state.to) === idOf(target) ? state.to : copy(target), direction, progress: clamp(progress), duration: 0 }
    publish(); return true
  }
  /** 从当前位置收尾；取消只回原卡，不发送成员切换事件。 */
  function release(commit) {
    if (state.phase !== 'dragging') return false
    const endpoint = commit ? 1 : 0
    const duration = Math.round(FAMILY_CARD_DURATION / 2 * (1 + Math.abs(endpoint - state.progress)))
    state = { ...state, phase: 'settling', duration, commit }
    const ticket = state.ticket, context = scope
    // Mount both layers before moving a click-triggered turn away from progress 0.
    timer = schedule(() => finish(ticket, context), duration + 180)
    publish()
    startTimer = schedule(() => {
      if (state.ticket !== ticket || context !== scope || state.phase !== 'settling') return
      startTimer = null
      state = { ...state, progress: endpoint }; publish()
    }, 24)
    return true
  }
  function select(id) {
    const target = members.find(m => idOf(m) === String(id))
    if (!target) return false
    if (state.busy) {
      if (state.phase === 'dragging') return false
      state = { ...state, queuedId: idOf(target) === idOf(state.to) ? null : idOf(target) }
      publish(); return true
    }
    if (idOf(target) === idOf(state.to)) return false
    const direction = members.indexOf(target) > members.findIndex(m => idOf(m) === idOf(state.to)) ? 1 : -1
    return preview(id, direction, 0) && release(true)
  }
  function finish(ticket, context = scope) {
    if (state.phase !== 'settling' || ticket !== state.ticket || context !== scope) return false
    clearTimers()
    const { queuedId, commit } = state
    const member = commit ? state.to : state.from
    state = idle(member)
    publish()
    if (commit) settled(idOf(member))
    if (queuedId !== null) select(queuedId)
    return true
  }
  function dispose() {
    clearTimers(); members = []; scope = ''; serial++; state = idle(null); publish()
  }
  return { reset, select, preview, release, finish, dispose, current: () => ({ ...state }) }
}

/** 同一进度同时驱动前后卡片，左右滑动互为镜像，始终有正面可见。 */
export function familyCardPose(progress, direction, incoming = false) {
  const p = clamp(progress), amount = incoming ? 1 - p : p
  return {
    opacity: incoming ? p : 1 - p,
    transform: incoming
      ? `translate(${direction * 8 * amount}%, ${-10 * amount}px) rotate(${-direction * 8.2 * amount}deg)`
      : `translate(${-direction * 3 * amount}%, ${8 * amount}px) rotate(${direction * 8 * amount}deg)`,
  }
}

/** 单指横向拖动；速度仅取最近约百毫秒，停住再松手不会被误判成甩动。 */
export function createFamilyCardGesture({ controller, getMembers, getIndex, getWidth, now = Date.now }) {
  let touch = null
  function cancel() {
    const moved = touch?.axis === 'x'
    touch = null
    controller.release(false)
    return moved
  }
  function start(event) {
    if (touch) cancel()
    if (controller.current().busy || event.touches?.length !== 1) return false
    const p = event.touches[0]
    touch = { x: p.clientX, y: p.clientY, id: p.identifier, axis: '', index: getIndex(), width: getWidth(), samples: [{ x: p.clientX, at: now() }], progress: 0, direction: 1 }
    return true
  }
  function move(event) {
    if (!touch) return false
    if (event.touches?.length !== 1 || event.touches[0].identifier !== touch.id) return cancel(), false
    const p = event.touches[0], dx = p.clientX - touch.x, dy = p.clientY - touch.y
    if (!touch.axis) {
      if (Math.max(Math.abs(dx), Math.abs(dy)) < 8) return false
      if (Math.abs(dx) > Math.abs(dy) * 1.25) touch.axis = 'x'
      else if (Math.abs(dy) > Math.abs(dx) * 1.25) touch.axis = 'y'
      else return false
    }
    if (touch.axis !== 'x') return false
    const at = now()
    touch.samples = touch.samples.filter(s => at - s.at <= 100)
    touch.samples.push({ x: p.clientX, at })
    const direction = dx < 0 ? 1 : -1
    const member = getMembers()[touch.index + direction]
    touch.direction = direction
    touch.progress = member ? clamp(Math.abs(dx) / (Math.max(1, touch.width) * .65)) : 0
    if (member) controller.preview(member.id, direction, touch.progress)
    else if (controller.current().phase === 'dragging') controller.preview(controller.current().to.id, controller.current().direction, 0)
    return true
  }
  function end(event) {
    if (!touch) return false
    const p = event.changedTouches?.[0]
    if (!p || p.identifier !== touch.id) return cancel()
    move({ touches: [p] })
    if (!touch) return false
    const current = touch, at = now()
    const sample = current.samples.find(s => at - s.at <= 100 && at > s.at)
    const velocity = sample ? (p.clientX - sample.x) / (at - sample.at) : 0
    touch = null
    const flick = -velocity * current.direction > .5 && current.progress > .1
    controller.release(current.progress >= .35 || flick)
    return current.axis === 'x'
  }
  return { start, move, end, cancel }
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
