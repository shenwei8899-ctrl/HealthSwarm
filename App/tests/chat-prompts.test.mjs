import test from 'node:test'
import assert from 'node:assert/strict'
import { CHAT_PROMPT_POOL, PERSONALIZED_CHAT_PROMPT_POOL, selectChatPrompts } from '../src/services/chat-prompts.js'
import { chatPromptProfileKey, chatPromptTopics } from '../src/services/chat-prompt-profile.js'

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
    assert.ok(p.text.length <= 8, p.text)
  }
})

test('selection does not mutate the pool or caller history and tolerates a stale cache', () => {
  const snapshot = JSON.stringify(CHAT_PROMPT_POOL), previousIds = ['removed-prompt', 'records']
  selectChatPrompts({ previousIds, random: () => 0 })
  assert.equal(JSON.stringify(CHAT_PROMPT_POOL), snapshot)
  assert.deepEqual(previousIds, ['removed-prompt', 'records'])
  assert.equal(selectChatPrompts({ previousIds: 'old-format' }).length, 4)
})

const household = members => ({ members, defaultDiners: ['self'] })
const hypertension = { id: 'mother', name: '妈妈', relation: '母亲', healthStatus: 'set', conditions: ['高血压'] }

test('hypertension remains dominant through repeated shuffles at every hour', () => {
  for (let hour = 0; hour < 24; hour++) {
    let previousIds = []
    for (let round = 0; round < 20; round++) {
      const group = selectChatPrompts({ profile: household([hypertension]), previousIds, hour, random: () => round / 20 })
      assert.equal(group.length, 4)
      assert.equal(group.filter(p => p.topic === 'hypertension').length, 3)
      assert.equal(new Set(group.filter(p => p.topic).map(p => p.category)).size, 3)
      assert.ok(group.every(p => !previousIds.includes(p.id)))
      previousIds = group.map(p => p.id)
    }
  }
})

test('all readable family members contribute regardless of default diners or selection', () => {
  const profile = household([{ id: 'self', relation: '本人', healthStatus: 'none' }, hypertension,
    { id: 'father', name: '爸爸', healthStatus: 'set', conditions: ['糖尿病'] }])
  const group = selectChatPrompts({ profile, random: () => 0.2 })
  assert.ok(group.some(p => p.topic === 'hypertension'))
  assert.ok(group.some(p => p.topic === 'diabetes'))
  assert.equal(group.filter(p => p.topic).length, 3)
  assert.equal(selectChatPrompts({ profile: household([hypertension, { ...hypertension, id: 'other', name: '家人' }]) }).filter(p => p.topic === 'hypertension').length, 3)
})

test('unknown, cleared and inactive conditions never revive residual disease selections', () => {
  for (const healthStatus of ['none', 'unknown', undefined]) {
    const profile = household([{ ...hypertension, healthStatus }])
    assert.equal(chatPromptTopics(profile).length, 0)
    assert.ok(selectChatPrompts({ profile }).every(p => !p.topic))
  }
  assert.equal(chatPromptTopics(household([{ ...hypertension, is_active: false }])).length, 0)
  assert.deepEqual(chatPromptTopics({ members: [null, { conditions: '高血压', healthStatus: 'set' }] }), [])
})

test('goals and preferences personalize without asserting disease', () => {
  const profile = household([{ id: 'self', relation: '本人', healthStatus: 'none', goals: ['控压'], tastePreferences: ['少盐'] }])
  const group = selectChatPrompts({ profile })
  assert.equal(group.filter(p => p.topic === 'salt').length, 3)
  assert.ok(group.every(p => !p.text.includes('高血压')))
  const combined = chatPromptTopics(household([{ ...hypertension, goals: ['控压'], tastePreferences: ['少盐'] }]))
  assert.deepEqual(combined.map(t => t.id), ['hypertension'])
})

test('restriction topics honor status and explicit content', () => {
  const member = { id: 'self', relation: '本人', allergyStatus: 'set', allergies: ['花生'], intoleranceStatus: 'set', intolerances: ['乳糖不耐受'], avoidanceStatus: 'set', avoidances: ['海鲜'] }
  const group = selectChatPrompts({ profile: household([member]) })
  assert.deepEqual(new Set(group.filter(p => p.topic).map(p => p.topic)), new Set(['allergy', 'intolerance', 'avoidance']))
  assert.equal(chatPromptTopics(household([{ ...member, allergyStatus: 'none', intoleranceStatus: 'unknown', avoidanceStatus: 'none' }])).length, 0)
})

test('custom conditions keep their stated context and protein goals do not become muscle goals', () => {
  const group = selectChatPrompts({ profile: household([{ id: 'self', relation: '本人', healthStatus: 'set', conditions: ['其他'], otherCondition: '合成基础病' }]) })
  assert.equal(group.filter(p => p.topic === 'other-condition').length, 3)
  assert.deepEqual(chatPromptTopics(household([{ goals: ['补充蛋白质'] }])).map(t => t.id), ['protein'])
  assert.deepEqual(chatPromptTopics(household([{ goals: ['constructor'], tastePreferences: ['toString'] }])), [])
  assert.equal(selectChatPrompts({ profile: household([{ healthStatus: 'set', conditions: ['toString'] }]) }).length, 4)
})

test('large families rotate equally ranked needs instead of permanently excluding a member', () => {
  const profile = household([{ ...hypertension, conditions: ['高血压', '糖尿病', '高血脂', '肾脏疾病', '高尿酸／痛风'] }])
  const first = selectChatPrompts({ profile, random: () => 0.3 })
  const next = selectChatPrompts({ profile, previousIds: first.map(p => p.id), random: () => 0.3 })
  assert.equal(new Set([...first, ...next].map(p => p.topic).filter(Boolean)).size, 5)
})

test('profile identity tracks relevant edits but ignores cache timestamps and member order', () => {
  const profile = household([hypertension, { id: 'self', relation: '本人' }])
  const key = chatPromptProfileKey(profile)
  assert.equal(chatPromptProfileKey({ ...profile, revision: 999, members: [...profile.members].reverse() }), key)
  assert.notEqual(chatPromptProfileKey(household([{ ...hypertension, name: '家人 A' }, profile.members[1]])), key)
  assert.notEqual(chatPromptProfileKey(household([{ ...hypertension, healthStatus: 'none' }, profile.members[1]])), key)
  assert.notEqual(chatPromptProfileKey(household([hypertension])), key)
})

test('authored personalized questions fit cards and selection never mutates source data', () => {
  assert.equal(new Set(PERSONALIZED_CHAT_PROMPT_POOL.map(p => p.id)).size, PERSONALIZED_CHAT_PROMPT_POOL.length)
  for (const p of PERSONALIZED_CHAT_PROMPT_POOL) assert.ok(p.text.length <= 8, p.text)
  const profile = household([hypertension]), before = JSON.stringify(profile)
  selectChatPrompts({ profile, previousIds: null })
  assert.equal(selectChatPrompts({ profile: household([{ ...hypertension, goals: ['减脂'] }]), previousIds: [null, 1, {}] }).length, 4)
  assert.equal(JSON.stringify(profile), before)
})

test('questions are authored without label-prefix assembly and each topic has varied sentence forms', () => {
  const labelPrefix = /^(高血压|糖尿病|高血脂|高尿酸|肾脏疾病|少盐|控糖|少油|低嘌呤|减脂|增肌|均衡饮食|多吃蔬菜|清淡饮食|补充蛋白|有基础病|食物过敏|食物不耐受|有忌口)，/
  const topicIds = new Set(PERSONALIZED_CHAT_PROMPT_POOL.map(p => p.topic))
  for (const topic of topicIds) {
    const pool = PERSONALIZED_CHAT_PROMPT_POOL.filter(p => p.topic === topic)
    assert.equal(new Set(pool.map(p => p.text)).size, pool.length)
    assert.ok(new Set(pool.map(p => p.form)).size >= 3)
    assert.ok(pool.every(p => !labelPrefix.test(p.text)))
  }
})

test('related cards vary sentence forms for a disease and for mixed goals', () => {
  for (const member of [hypertension, { id: 'self', relation: '本人', healthStatus: 'none', goals: ['控糖', '控压'], tastePreferences: ['少油'] }]) {
    let previousIds = []
    for (let round = 0; round < 30; round++) {
      const group = selectChatPrompts({ profile: household([member]), previousIds, random: () => round / 30 }).filter(p => p.topic)
      assert.equal(group.length, 3)
      assert.ok(new Set(group.map(p => p.form)).size >= 2)
      assert.equal(new Set(group.map(p => p.text)).size, 3)
      previousIds = group.map(p => p.id)
    }
  }
})
