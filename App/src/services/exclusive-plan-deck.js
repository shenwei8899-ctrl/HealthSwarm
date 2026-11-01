import { planTiers } from './exclusive-plan-flow.js'

export const PLAN_DECK_DURATION = 800
export const planDeckState = () => ({ front: 'standard', requested: 'standard', from: '', to: '', moving: false, direction: 'forward', token: 0 })

/** Presentation state only: switching cards never starts or retries a server task. */
export function createPlanDeck({ state, commit, later = setTimeout, cancelLater = clearTimeout, now = Date.now, reducedMotion = () => false }) {
  let timer = null, startedAt = 0, disposed = false
  function clear() { if (timer !== null) cancelLater(timer); timer = null }
  function reset(tier = 'standard') {
    clear()
    const front = planTiers.includes(tier) ? tier : 'standard'
    Object.assign(state, { front, requested: front, from: '', to: '', moving: false, token: state.token + 1 })
  }
  function start(tier) {
    if (disposed || tier === state.front) return
    if (reducedMotion()) { state.front = tier; commit(tier); return }
    Object.assign(state, { from: state.front, to: tier, moving: true,
      direction: planTiers.indexOf(tier) > planTiers.indexOf(state.front) ? 'forward' : 'backward', token: state.token + 1 })
    startedAt = now()
    const token = state.token
    timer = later(() => finish(token), PLAN_DECK_DURATION + 120)
  }
  function request(tier) {
    if (disposed || !planTiers.includes(tier)) return
    state.requested = tier
    if (!state.moving) start(tier)
  }
  function finish(token, animationEvent = false) {
    if (disposed || !state.moving || token !== state.token) return false
    // A bubbled child event or a late native event must not finish a newer transition.
    if (animationEvent && now() - startedAt < PLAN_DECK_DURATION - 60) return false
    clear()
    Object.assign(state, { front: state.to, from: '', to: '', moving: false })
    commit(state.front)
    if (state.requested !== state.front) start(state.requested)
    return true
  }
  function dispose() { reset(state.front); disposed = true }
  return { request, finish, reset, dispose }
}
