import test from 'node:test'
import assert from 'node:assert/strict'
import { createPlanDeck, planDeckState, PLAN_DECK_DURATION } from '../src/services/exclusive-plan-deck.js'

function harness(reduced = false) {
  const state = planDeckState(), commits = [], timers = new Map()
  let clock = 0, next = 0
  const deck = createPlanDeck({ state, commit: tier => commits.push(tier), reducedMotion: () => reduced,
    now: () => clock, later: fn => { timers.set(++next, fn); return next }, cancelLater: id => timers.delete(id) })
  return { state, commits, timers, deck, advance: value => { clock += value }, finish() { clock += PLAN_DECK_DURATION; return deck.finish(state.token, true) }, timeout() { const fn = [...timers.values()][0]; assert.ok(fn); fn() } }
}

test('selection moves complete cards before committing a new detail target', () => {
  const h = harness()
  h.deck.request('premium')
  assert.equal(h.state.front, 'standard')
  assert.equal(h.state.from, 'standard'); assert.equal(h.state.to, 'premium')
  assert.equal(h.state.direction, 'forward'); assert.equal(h.state.moving, true)
  assert.deepEqual(h.commits, [])
  h.finish()
  assert.equal(h.state.front, 'premium'); assert.equal(h.state.moving, false)
  assert.deepEqual(h.commits, ['premium']); assert.equal(h.timers.size, 0)
})

test('rapid clicks retain the last requested tier without an intermediate extra transition', () => {
  const h = harness()
  h.deck.request('premium'); h.deck.request('economy'); h.deck.request('standard')
  assert.equal(h.timers.size, 1)
  h.finish()
  assert.equal(h.state.from, 'premium'); assert.equal(h.state.to, 'standard')
  assert.equal(h.state.direction, 'backward')
  h.finish()
  assert.deepEqual(h.commits, ['premium', 'standard'])
  assert.equal(h.state.front, 'standard'); assert.equal(h.timers.size, 0)
})

test('a child event or previous animation event cannot finish a new transition early', () => {
  const h = harness()
  h.deck.request('economy'); const old = h.state.token
  assert.equal(h.deck.finish(old, true), false)
  h.deck.request('premium'); h.finish()
  assert.equal(h.deck.finish(old, true), false)
  assert.equal(h.deck.finish(h.state.token, true), false)
  assert.equal(h.state.moving, true)
  h.finish(); assert.equal(h.state.front, 'premium')
})

test('a missing native animationend event settles through the timer fallback', () => {
  const h = harness()
  h.deck.request('economy'); h.timeout()
  assert.equal(h.state.front, 'economy'); assert.equal(h.state.moving, false)
  assert.deepEqual(h.commits, ['economy'])
})

test('leaving the page or replacing the recommendation group cancels pending selection', () => {
  const h = harness()
  h.deck.request('economy'); const staleTimer = [...h.timers.values()][0], token = h.state.token
  h.deck.request('premium'); h.deck.reset('standard')
  staleTimer(); h.deck.finish(token)
  assert.equal(h.timers.size, 0); assert.equal(h.state.front, 'standard')
  assert.equal(h.state.requested, 'standard'); assert.equal(h.state.moving, false)
  assert.deepEqual(h.commits, [])
})

test('unmount prevents any subsequent timer or click from selecting another plan', () => {
  const h = harness()
  h.deck.request('premium'); const stale = [...h.timers.values()][0]
  h.deck.dispose(); stale(); h.deck.request('economy')
  assert.equal(h.state.front, 'standard'); assert.equal(h.state.moving, false)
  assert.equal(h.timers.size, 0); assert.deepEqual(h.commits, [])
})

test('reduced motion selects immediately with no animation or timer', () => {
  const h = harness(true)
  h.deck.request('economy')
  assert.equal(h.state.front, 'economy'); assert.equal(h.state.moving, false)
  assert.deepEqual(h.commits, ['economy']); assert.equal(h.timers.size, 0)
})

test('the current tier and unknown values never create a transition', () => {
  const h = harness()
  h.deck.request('standard'); h.deck.request('unrecognized')
  assert.equal(h.state.front, 'standard'); assert.equal(h.state.requested, 'standard')
  assert.equal(h.timers.size, 0); assert.deepEqual(h.commits, [])
})
