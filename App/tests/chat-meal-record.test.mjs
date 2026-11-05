import test from 'node:test'
import assert from 'node:assert/strict'
import { createChatMealRecordClient, chatMealRecordState } from '../src/services/chat-meal-record.js'
import { chatMessages } from '../src/services/cloud-chat.js'

const receipt = (status = 'saved', version = 1) => ({ id: 'meal', member_id: 'member', member_name: '本人', source_version: version, status,
  meal_type: 'lunch', eaten_at: '2026-11-02T12:00:00+08:00', items: [{ name: '番茄炒蛋', quantity_text: '未知' }] })
function harness(override = () => null) {
  const state = chatMealRecordState(), entries = new Map(), calls = []; let scope = 'one', count = 0, current = receipt()
  const client = createChatMealRecordClient({ state, id: 'meal', context: () => scope, newId: () => `key-${++count}`,
    storage: { getStorageSync: key => entries.get(scope + key), setStorageSync: (key, value) => entries.set(scope + key, structuredClone(value)) },
    send: async request => { calls.push(structuredClone(request)); const result = await override(request); if (result) return result
      if (request.method === 'POST') current = receipt('withdrawn', 2)
      return { data: structuredClone(current) } },
  })
  return { state, client, calls, entries, switchAccount() { scope = 'two' } }
}

test('withdrawal is visible only after the same stored record is read back', async () => {
  const h = harness(); await h.client.refresh(); assert.equal(h.state.record.status, 'saved')
  await h.client.withdraw(); assert.equal(h.state.record.status, 'withdrawn'); assert.equal(h.state.record.source_version, 2)
  assert.equal(h.calls.filter(row => row.method === 'POST').length, 1); assert.equal(h.state.pending, null)
})

test('lost withdrawal response retries the immutable version body and request key', async () => {
  let writes = 0
  const h = harness(request => { if (request.method === 'POST' && ++writes === 1) throw Object.assign(new Error('timeout'), { code: 'NETWORK_ERROR' }) })
  await h.client.refresh(); await h.client.withdraw(); assert.ok(h.state.pending)
  h.state.record.source_version = 9
  await h.client.withdraw()
  const posts = h.calls.filter(row => row.method === 'POST')
  assert.deepEqual(posts[0], posts[1]); assert.equal(posts[1].data.expected_version, 1)
  assert.equal(h.state.record.status, 'withdrawn')
})

test('an uncertain retry cannot present an invented successful withdrawal', async () => {
  const h = harness(request => request.method === 'POST' ? { data: receipt() } : null)
  await h.client.refresh(); await h.client.withdraw()
  assert.equal(h.state.record.status, 'saved'); assert.ok(h.state.pending); assert.match(h.state.error, /尚未确认/)
})

test('a current version conflict clears the old request and leaves the saved record intact', async () => {
  const h = harness(request => { if (request.method === 'POST') throw Object.assign(new Error('请刷新后操作'), { code: 409 }) })
  await h.client.refresh(); await h.client.withdraw()
  assert.equal(h.state.pending, null); assert.equal(h.state.record.status, 'saved'); assert.match(h.state.error, /刷新/)
})

for (const action of ['account', 'hide']) test(`late private responses cannot publish after ${action} changes`, async () => {
  let release
  const h = harness(() => new Promise(resolve => { release = resolve }))
  const pending = h.client.refresh()
  if (action === 'account') h.switchAccount(); else h.client.hide()
  release({ data: receipt() }); await pending
  assert.equal(h.state.record, null); assert.equal(h.state.busy, false)
})

test('authorization loss removes the visible private receipt', async () => {
  let revoked = false
  const h = harness(() => { if (revoked) throw Object.assign(new Error('无权访问'), { code: 404 }) })
  await h.client.refresh(); revoked = true; await h.client.refresh()
  assert.equal(h.state.record, null); assert.equal(h.state.pending, null)
})

test('reopening after an uncertain withdrawal verifies the stored result without creating a write', async () => {
  const h = harness(() => ({ data: receipt('withdrawn', 2) }))
  await h.client.refresh(); assert.equal(h.state.record.status, 'withdrawn'); assert.equal(h.calls.length, 1)
})

test('server history carries actual receipts into the same dialogue turn', () => {
  const rows = chatMessages({ history: [{ id: 'answer', type: 'ai', content: '已记录', request_id: 'request', recorded_meals: [receipt()] }] })
  assert.equal(rows[0].recordedMeals[0].id, 'meal')
})
