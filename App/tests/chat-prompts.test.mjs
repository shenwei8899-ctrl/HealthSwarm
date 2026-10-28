import test from 'node:test'
import assert from 'node:assert/strict'
import { CHAT_PROMPT_POOL, selectChatPrompts } from '../src/services/chat-prompts.js'

test('every hour has four distinct usable prompts and successive groups do not overlap', () => {
  for (let hour = 0; hour < 24; hour++) {
    let previousIds = []
    for (let round = 0; round < 20; round++) {
      const group = selectChatPrompts({ previousIds, hour, random: () => round / 20 })
      assert.equal(group.length, 4)
      assert.equal(new Set(group.map(p => p.id)).size, 4)
      assert.ok(group.every(p => !previousIds.includes(p.id)))
      assert.ok(group.every(p => !p.hours || hour >= p.hours[0] && hour < p.hours[1]))
      assert.ok(group.filter(p => p.action === 'open_records').length <= 1)
      previousIds = group.map(p => p.id)
    }
  }
})

test('the pool has unique labels and identities, supported actions, and short card text', () => {
  assert.equal(new Set(CHAT_PROMPT_POOL.map(p => p.id)).size, CHAT_PROMPT_POOL.length)
  assert.equal(new Set(CHAT_PROMPT_POOL.map(p => p.text)).size, CHAT_PROMPT_POOL.length)
  for (const p of CHAT_PROMPT_POOL) {
    assert.ok(['consultation', 'reference_meal_preview', 'open_records'].includes(p.action))
    assert.ok(p.text.length <= 12)
  }
})

test('selection does not mutate the pool or caller history and tolerates a stale cache', () => {
  const snapshot = JSON.stringify(CHAT_PROMPT_POOL), previousIds = ['removed-prompt', 'records']
  selectChatPrompts({ previousIds, random: () => 0 })
  assert.equal(JSON.stringify(CHAT_PROMPT_POOL), snapshot)
  assert.deepEqual(previousIds, ['removed-prompt', 'records'])
  assert.equal(selectChatPrompts({ previousIds: 'old-format' }).length, 4)
})
