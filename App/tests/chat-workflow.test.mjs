import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { computed, effectScope, nextTick, reactive, ref } from 'vue'
import { HEALTH_TEXT_TASKS } from '../src/services/health-task-flow.js'
import { chatPresentation } from '../src/services/chat-presentation.js'
import { referenceSelection as chooseReference, isReferencePlan } from '../src/services/reference-meal-plan.js'
import { parseChatMealIntent } from '../src/utils/chat-meal-intent.js'

const member = '11111111-1111-4111-8111-111111111111'
const relative = '11111111-1111-4111-8111-111111111112'
const uuid = number => `22222222-2222-4222-8222-${String(number).padStart(12, '0')}`
const clone = value => value === undefined ? undefined : JSON.parse(JSON.stringify(value))
const nextDay = (day, distance = 1) => new Date(Date.parse(day) + distance * 86400000).toISOString().slice(0, 10)
const flush = () => new Promise(resolve => setImmediate(resolve))
function deferred() { let resolve; const promise = new Promise(yes => { resolve = yes }); return { promise, resolve } }

function workflow(options = {}) {
  const calls = [], writes = [], cache = new Map(), threads = new Map(), bindings = new Map(), hooks = {}
  const identity = { scope: 'account-a', accountId: 'account-a', token: 'synthetic-a', householdId: 'family-a', dailyThread: uuid(1) }
  const clock = { day: '2026-10-28' }, route = options.route || {}
  let serial = 100, flow, snapshotOverride = null
  const id = () => uuid(++serial)
  const profile = () => ({ onboarded: true, completeProfile: true, source: 'api', householdId: identity.householdId,
    selfMemberId: 'self', defaultDiners: ['self', 'father'], healthConfiguration: { consultation: { available: true }, meal_plan: { available: true } },
    members: [{ id: 'self', relation: '本人', name: '合成本人', healthMemberId: member, allergyStatus: 'set', allergies: ['花生'], doctorStatus: 'none' },
      { id: 'father', relation: '父亲', name: '合成家人', healthMemberId: relative, restrictionStatus: 'set', restrictions: ['少辣'] }],
  })
  const addThread = (threadId, config = {}) => {
    const row = { threadId, memberId: member, taskType: 'consultation', agent: 'health-consultation', businessDate: null,
      messages: [], runs: [], owner: identity.scope, ...config }
    threads.set(threadId, row)
    return row
  }
  addThread(identity.dailyThread, { businessDate: clock.day,
    messages: [{ id: 'daily-old', role: 'user', text: '合成的当前会话', createdAt: `${clock.day}T08:00:00+08:00` }] })
  const scopedStorage = {
    getStorageSync: key => clone(cache.get(identity.scope + ':' + key)),
    setStorageSync: (key, value) => { const snapshot = clone(value); writes.push({ scope: identity.scope, key, value: snapshot }); cache.set(identity.scope + ':' + key, snapshot) },
    getStorageInfoSync: () => ({ keys: [...cache.keys()].filter(key => key.startsWith(identity.scope + ':')).map(key => key.slice(identity.scope.length + 1)) }),
  }
  const createHealthTaskFlow = ({ onChange }) => {
    let generation = 0, selected = null, selection = null, flowOptions = {}, state
    const fresh = () => ({ memberId: '', taskType: '', available: false, entry: null, requestId: '', status: '', result: null,
      readOnly: false, busy: false, loading: false, submitUnknown: false, canRetry: false })
    const publish = patch => { state = { ...(state || fresh()), ...patch }; onChange(clone(state)) }
    const hide = () => { generation++; selected = null; state = fresh(); onChange(clone(state)) }
    const bindingKey = () => identity.scope + ':' + flowOptions.conversationId + ':' + state.memberId + ':' + state.taskType + ':' + JSON.stringify(selection)
    const entryFor = row => ({ thread_id: row.threadId, agent_slug: row.agent, business_date: row.businessDate })
    flow = {
      hide,
      async open(memberId, taskType, selectedValues = null, fourth = {}) {
        const mine = ++generation
        calls.push({ action: 'open', memberId, taskType, selection: clone(selectedValues), options: clone(fourth) })
        selection = clone(selectedValues); flowOptions = clone(fourth) || {}
        state = { ...fresh(), memberId, taskType, available: true }
        selected = flowOptions.threadId || (flowOptions.conversationId ? bindings.get(bindingKey()) : taskType === 'consultation' ? identity.dailyThread : null)
        const row = selected && threads.get(selected)
        if (mine !== generation) return
        if (row && row.owner !== identity.scope) throw Object.assign(new Error('合成的跨账号访问拒绝'), { code: 403 })
        publish({ entry: row ? entryFor(row) : null, readOnly: !!row?.businessDate && row.businessDate < clock.day })
      },
      async createEntry() {
        calls.push({ action: 'create', taskType: state.taskType, memberId: state.memberId, selection: clone(selection), options: clone(flowOptions) })
        selected = id()
        const row = addThread(selected, { memberId: state.memberId, taskType: state.taskType,
          agent: state.taskType === 'consultation' ? 'health-consultation' : 'health-meal-planner',
          businessDate: !flowOptions.conversationId && state.taskType === 'consultation' ? clock.day : null })
        if (flowOptions.conversationId) bindings.set(bindingKey(), selected)
        publish({ entry: entryFor(row), requestId: '', status: '', result: null, readOnly: false })
      },
      async submit(text, retry = false, images = []) {
        const row = threads.get(state.entry?.thread_id)
        calls.push({ action: 'submit', threadId: row?.threadId, taskType: state.taskType, memberId: state.memberId, text, retry, images: clone(images), selection: clone(selection) })
        assert.ok(row, 'the component must create or restore a thread before submitting')
        assert.equal(state.readOnly, false, 'the component must never submit an archived daily conversation')
        const requestId = id(), answer = `合成回复 ${calls.filter(call => call.action === 'submit').length}`
        row.messages.push({ id: requestId + '-user', requestId, role: 'user', text, createdAt: `${clock.day}T09:00:00+08:00` },
          { id: requestId + '-answer', requestId, role: 'assistant', text: answer, createdAt: `${clock.day}T09:00:01+08:00` })
        publish({ requestId, status: 'completed', submitUnknown: false, canRetry: false, result: { type: 'answer', text: answer, citations: [] } })
        return true
      },
      async restoreRequest(requestId) { calls.push({ action: 'restoreRequest', requestId }) },
      async acceptConsent() { calls.push({ action: 'consent' }) },
      async refresh() { calls.push({ action: 'refresh' }) },
      invalidateThread() { publish({ invalidated: true, available: false, entry: null }) },
      publish,
    }
    return flow
  }
  const deps = { computed, reactive, ref, nextTick, defineProps: () => ({ route }),
    onMounted: fn => { hooks.mount = fn }, onUnmounted: fn => { hooks.unmount = fn }, onShow: fn => { hooks.show = fn }, onHide: fn => { hooks.hide = fn },
    chatPresentation, chooseReference, isReferencePlan, HEALTH_TEXT_TASKS, parseChatMealIntent,
    newHealthRequestId: id, storageContext: () => identity.scope, getSession: () => ({ ...identity }), scopedStorage,
    loadCloudProfile: async () => profile(), localDate: value => value ? nextDay(clock.day) : clock.day,
    dailyArrangementState: () => ({ phase: 'idle', busy: false, date: clock.day, arrangement: null }),
    createDailyArrangementClient: ({ state }) => ({ reset() { state.phase = 'idle'; state.busy = false; state.arrangement = null }, dispose() {},
      adopt(value) { state.phase = 'ready'; state.arrangement = value; state.date = value.date },
      async load(date) { calls.push({ action: 'loadPlan', date }); return null },
      async start(value) { calls.push({ action: 'startPlan', value }); throw new Error('normal chat must not create a saved plan') },
    }),
    readCurrentPreparation: async () => ({ status: 'absent' }),
    request: async request => { calls.push({ action: 'http', ...clone(request) }); return { data: { status: 'absent' } } },
    readChatSnapshot: async threadId => {
      calls.push({ action: 'snapshot', threadId })
      if (snapshotOverride) return snapshotOverride(threadId)
      const row = threads.get(threadId)
      if (!row || row.owner !== identity.scope) throw Object.assign(new Error('不可访问'), { code: 403 })
      return { messages: clone(row.messages), runs: clone(row.runs), thread: { id: threadId, title: '', agentId: row.agent } }
    },
    createHealthTaskFlow, chatImageContent: async image => image.localPath,
    persistChatImage: async image => ({ localPath: image.path }),
    loadChatMealPlan: async () => { calls.push({ action: 'loadChatMealPlan' }); throw new Error('normal chat must not create a saved plan') },
    uni: { showToast(value) { calls.push({ action: 'toast', ...value }) }, hideKeyboard() {}, navigateTo(value) { calls.push({ action: 'navigate', ...value }) },
      reLaunch(value) { calls.push({ action: 'reLaunch', ...value }) }, redirectTo(value) { calls.push({ action: 'redirect', ...value }) } },
  }
  const code = readFileSync(new URL('../src/components/CloudNutritionChat.vue', import.meta.url), 'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  const scope = effectScope()
  const page = scope.run(() => new Function('deps', `const {${Object.keys(deps).join(',')}}=deps;${code};return {load,profile,task,question,messages,entryReady,presentation,state,chatBusy,chatError,draftImage,draftError,draftSaving,voiceBusy,historyOpen,conversationId,conversationThreadId,conversationBusinessDate,conversationReadOnly,newConversationWelcome,newConversation,selectConversation,sendQuestion}`)(deps))
  const historyRow = threadId => { const row = threads.get(threadId); return { thread_id: threadId, member_id: row.memberId, agent_slug: row.agent, business_date: row.businessDate } }
  return { ...page, calls, writes, identity, clock, hooks, scopedStorage, threads, addThread, historyRow,
    publish: value => flow.publish(value), setSnapshot: value => { snapshotOverride = value },
    dispose() { hooks.unmount?.(); scope.stop() },
  }
}

test('ordinary arrangement requests and corrections stay in one continuous consultation without creating meal plans', async () => {
  const p = workflow()
  try {
    await p.load()
    const initialThread = p.conversationThreadId.value
    const questions = ['给我安排明天早餐', '牛奶换成豆浆，不要加糖', '生成今天的三餐食谱，少放辣椒']
    for (const question of questions) { p.question.value = question; await p.sendQuestion() }
    const submits = p.calls.filter(call => call.action === 'submit')
    assert.deepEqual(submits.map(call => call.text), questions)
    assert.deepEqual([...new Set(submits.map(call => call.threadId))], [initialThread])
    assert.ok(submits.every(call => call.taskType === 'consultation'))
    assert.equal(p.calls.filter(call => ['create', 'startPlan', 'loadPlan', 'loadChatMealPlan'].includes(call.action)).length, 0)
    assert.equal(p.calls.some(call => call.action === 'http' && call.method === 'POST'), false)
    assert.ok(p.messages.value.some(message => message.text === '合成回复 3'))
  } finally { p.dispose() }
})

test('explicit structured planning preserves chosen family members, tomorrow lunch and the complete dietary restrictions', async () => {
  const p = workflow()
  try {
    await p.load()
    const question = '请给全家安排明天午餐，不放花生，也不要辣椒，父亲少盐'
    p.question.value = question
    await p.sendQuestion('reference_meal_preview')
    const selected = p.calls.filter(call => call.action === 'open' && call.taskType === 'reference_meal_preview')
    assert.ok(selected.length >= 1)
    for (const call of selected) assert.deepEqual(call.selection, { mode: 'reference', family_id: 'family-a', plan_date: '2026-10-29', participant_ids: ['father', 'self'], meal_types: ['lunch'] })
    const submitted = p.calls.filter(call => call.action === 'submit')
    assert.equal(submitted.length, 1); assert.equal(submitted[0].taskType, 'reference_meal_preview'); assert.equal(submitted[0].text, question)
    assert.equal(p.profile.value.members[0].allergies[0], '花生')
  } finally { p.dispose() }
})

test('a new conversation immediately has its own empty welcome and creates a thread only on the first question', async () => {
  const p = workflow()
  try {
    await p.load(); assert.ok(p.messages.value.length > 0)
    const oldId = p.conversationId.value
    p.question.value = '上个会话未发送的草稿'
    await p.newConversation()
    const newId = p.conversationId.value
    assert.notEqual(newId, oldId); assert.match(newId, /^[0-9a-f-]{36}$/)
    assert.equal(p.conversationThreadId.value, ''); assert.deepEqual(p.messages.value, []); assert.equal(p.question.value, '')
    assert.equal(p.presentation.value.welcome, true); assert.equal(p.newConversationWelcome.value, true)
    assert.equal(p.calls.filter(call => call.action === 'create').length, 0)
    p.question.value = '我想了解规律早餐'
    await p.sendQuestion()
    const created = p.calls.filter(call => call.action === 'create')
    assert.equal(created.length, 1); assert.equal(created[0].options.conversationId, newId)
    assert.ok(p.conversationThreadId.value); assert.equal(p.conversationId.value, newId)
    assert.equal(p.messages.value.some(message => message.text === '合成的当前会话'), false)
    assert.equal(p.scopedStorage.getStorageSync(`conversation-summary:${member}:${p.conversationThreadId.value}`).title, '我想了解规律早餐')
  } finally { p.dispose() }
})

test('selecting another thread never merges conversations and restores the separate unsent text and photo draft', async () => {
  const p = workflow(), second = uuid(2)
  p.addThread(second, { messages: [{ id: 'second-private', role: 'user', text: '第二段会话的独立问题', createdAt: '2026-10-28T10:00:00+08:00' }] })
  try {
    await p.load(); const first = p.conversationThreadId.value
    p.question.value = '第一段的未发送草稿'; p.draftImage.value = { localPath: 'synthetic-first-photo' }; p.draftError.value = '合成图片读取提示'
    await p.selectConversation(p.historyRow(second))
    assert.deepEqual(p.messages.value.map(message => message.text), ['第二段会话的独立问题'])
    assert.equal(p.question.value, ''); assert.equal(p.draftImage.value, null)
    p.question.value = '第二段的未发送草稿'; p.draftImage.value = { localPath: 'synthetic-second-photo' }
    await p.selectConversation(p.historyRow(first))
    assert.deepEqual(p.messages.value.map(message => message.text), ['合成的当前会话'])
    assert.equal(p.question.value, '第一段的未发送草稿'); assert.equal(p.draftImage.value.localPath, 'synthetic-first-photo'); assert.equal(p.draftError.value, '合成图片读取提示')
    await p.selectConversation(p.historyRow(second))
    assert.equal(p.question.value, '第二段的未发送草稿'); assert.equal(p.draftImage.value.localPath, 'synthetic-second-photo')
    assert.equal(p.calls.filter(call => call.action === 'submit' || call.action === 'create').length, 0)
  } finally { p.dispose() }
})

for (const blocked of [{ status: 'running' }, { busy: true }, { submitUnknown: true, canRetry: true }]) {
  test(`an active or uncertain request cannot change threads or replace the current draft: ${JSON.stringify(blocked)}`, async () => {
    const p = workflow(), second = uuid(2)
    p.addThread(second)
    try {
      await p.load(); const before = p.conversationId.value, callCount = p.calls.length, writes = p.writes.length
      p.question.value = '尚未确认结果的问题'; p.publish(blocked)
      await p.newConversation(); await p.selectConversation(p.historyRow(second))
      assert.equal(p.conversationId.value, before); assert.equal(p.question.value, '尚未确认结果的问题')
      assert.equal(p.calls.length, callCount); assert.equal(p.writes.length, writes)
    } finally { p.dispose() }
  })
}

test('an earlier daily conversation stays readable but cannot submit, while a new conversation can continue', async () => {
  const p = workflow(), archived = uuid(3)
  p.addThread(archived, { businessDate: '2026-10-27', messages: [{ id: 'yesterday', role: 'user', text: '昨天每日咨询的合成记录', createdAt: '2026-10-27T09:00:00+08:00' }] })
  try {
    await p.load(); await p.selectConversation(p.historyRow(archived))
    assert.equal(p.conversationReadOnly.value, true); assert.ok(p.messages.value.some(message => message.text === '昨天每日咨询的合成记录'))
    p.question.value = '不能发送到昨天'; await p.sendQuestion()
    assert.equal(p.calls.filter(call => call.action === 'submit').length, 0); assert.equal(p.question.value, '不能发送到昨天'); assert.match(p.chatError.value, /已归档/)
    await p.newConversation(); assert.equal(p.conversationReadOnly.value, false)
    p.question.value = '在新的独立会话继续'; await p.sendQuestion()
    const submit = p.calls.find(call => call.action === 'submit'); assert.ok(submit); assert.notEqual(submit.threadId, archived)
  } finally { p.dispose() }
})

test('a standalone conversation created yesterday retains its complete history and accepts a follow-up today', async () => {
  const p = workflow(), standalone = uuid(4)
  p.addThread(standalone, { businessDate: null, messages: [{ id: 'standalone-yesterday', role: 'user', text: '独立会话昨天的问题', createdAt: '2026-10-27T11:00:00+08:00' },
    { id: 'standalone-today', role: 'assistant', text: '独立会话今天的回复', createdAt: '2026-10-28T09:00:00+08:00' }] })
  try {
    await p.load(); await p.selectConversation(p.historyRow(standalone))
    assert.equal(p.conversationReadOnly.value, false)
    assert.deepEqual(p.messages.value.map(message => message.text), ['独立会话昨天的问题', '独立会话今天的回复'])
    p.question.value = '沿用之前的记录再解释一下'; await p.sendQuestion()
    assert.equal(p.calls.find(call => call.action === 'submit').threadId, standalone)
    assert.equal(p.calls.filter(call => call.action === 'create').length, 0)
  } finally { p.dispose() }
})

test('a newly created standalone conversation resumes after the Beijing date changes without creating another thread', async () => {
  const p = workflow()
  try {
    await p.load(); await p.newConversation()
    p.question.value = '独立对话第一天的问题'; await p.sendQuestion()
    const conversationId = p.conversationId.value, threadId = p.conversationThreadId.value
    assert.equal(p.threads.get(threadId).businessDate, null)
    p.clock.day = nextDay(p.clock.day); p.hooks.hide(); await p.load()
    assert.equal(p.conversationId.value, conversationId); assert.equal(p.conversationThreadId.value, threadId); assert.equal(p.conversationReadOnly.value, false)
    assert.deepEqual(p.messages.value.map(message => message.text), ['独立对话第一天的问题', '合成回复 1'])
    p.question.value = '第二天沿着这个问题继续'; await p.sendQuestion()
    assert.equal(p.calls.filter(call => call.action === 'create').length, 1)
    assert.deepEqual([...new Set(p.calls.filter(call => call.action === 'submit').map(call => call.threadId))], [threadId])
  } finally { p.dispose() }
})

test('the first structured plan in a new conversation retains a consultation anchor that the conversation directory can reopen', async () => {
  const p = workflow()
  try {
    await p.load(); await p.newConversation()
    const conversationId = p.conversationId.value
    p.question.value = '请给我安排明天早餐，不放花生'
    await p.sendQuestion('reference_meal_preview')
    const anchor = p.conversationThreadId.value
    assert.ok(anchor, 'a plan-only first action still needs a primary consultation in the consultations directory')
    assert.equal(p.threads.get(anchor)?.taskType, 'consultation')
    assert.equal(p.scopedStorage.getStorageSync('conversation-index:' + anchor).id, conversationId)
    assert.ok(p.scopedStorage.getStorageSync('conversation-threads:' + conversationId).some(row => row.task_type === 'reference_meal_preview'))
    assert.equal(p.calls.filter(call => call.action === 'submit').length, 1, 'creating the anchor must not submit an extra AI question')
    await p.selectConversation(p.historyRow(p.identity.dailyThread))
    await p.selectConversation(p.historyRow(anchor))
    assert.equal(p.conversationId.value, conversationId)
    assert.deepEqual(p.messages.value.map(message => message.text), ['请给我安排明天早餐，不放花生', '合成回复 1'])
    assert.equal(p.calls.filter(call => call.action === 'submit').length, 1, 'reopening the conversation is read-only')
  } finally { p.dispose() }
})

test('a late history read from the previous account cannot overwrite the new account view, draft or summary cache', async () => {
  const p = workflow(), second = uuid(2), accountB = uuid(9), delayed = deferred()
  p.addThread(second)
  try {
    await p.load()
    p.setSnapshot(async threadId => threadId === second ? delayed.promise : { messages: clone(p.threads.get(threadId).messages), runs: [] })
    const oldSelection = p.selectConversation(p.historyRow(second)); await flush()
    p.identity.scope = 'account-b'; p.identity.accountId = 'account-b'; p.identity.token = 'synthetic-b'; p.identity.householdId = 'family-b'; p.identity.dailyThread = accountB
    p.addThread(accountB, { businessDate: p.clock.day, messages: [{ id: 'account-b-message', role: 'user', text: '新账号当前的问题', createdAt: '2026-10-28T08:00:00+08:00' }] })
    await p.load(); p.question.value = '新账号尚未发送的草稿'
    delayed.resolve({ messages: [{ id: 'late-old-account', role: 'user', text: '必须丢弃的旧账号正文', createdAt: '2026-10-28T10:00:00+08:00' }], runs: [] })
    await oldSelection
    assert.deepEqual(p.messages.value.map(message => message.text), ['新账号当前的问题'])
    assert.equal(p.question.value, '新账号尚未发送的草稿'); assert.equal(p.conversationThreadId.value, accountB)
    assert.equal(p.writes.filter(write => write.scope === 'account-b').some(write => JSON.stringify(write.value).includes('必须丢弃的旧账号正文')), false)
  } finally { p.dispose() }
})

test('a thread invalidated while its history is loading cannot restore the late saved messages', async () => {
  const p = workflow(), second = uuid(2), delayed = deferred()
  p.addThread(second)
  try {
    await p.load()
    p.setSnapshot(async threadId => threadId === second ? delayed.promise : { messages: clone(p.threads.get(threadId).messages), runs: [] })
    const selection = p.selectConversation(p.historyRow(second)); await flush()
    p.publish({ invalidated: true, available: false, entry: null, error: '合成的资料来源失效' })
    assert.deepEqual(p.messages.value, [])
    delayed.resolve({ messages: [{ id: 'revoked-late-history', role: 'assistant', text: '不得重新显示的失效正文', createdAt: '2026-10-28T10:00:00+08:00' }], runs: [] })
    await selection
    assert.equal(p.task.value.invalidated, true)
    assert.deepEqual(p.messages.value, [])
    assert.equal(p.writes.some(write => JSON.stringify(write.value).includes('不得重新显示的失效正文')), false)
  } finally { p.dispose() }
})
