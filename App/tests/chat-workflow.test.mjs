import {watch} from 'vue'
import {createChatEntryTransition} from '../src/services/chat-entry-transition.js'
import {createChatKeyboardLayout} from '../src/services/chat-keyboard-layout.js'
import {mealQuestionAction,readDailyMealPlan} from '../src/services/daily-meal-plan.js'
import {selectChatPrompts,CHAT_PROMPT_POOL} from '../src/services/chat-prompts.js'
import {chatTimestamp,chatBusinessDate} from '../src/services/cloud-chat.js'
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { computed, effectScope, nextTick, reactive, ref } from 'vue'
import { HEALTH_TEXT_TASKS } from '../src/services/health-task-flow.js'
import { chatPresentation } from '../src/services/chat-presentation.js'
import { referenceSelection as chooseReference, isReferencePlan } from '../src/services/reference-meal-plan.js'
import { parseChatMealIntent,isMealPlanningCancelled } from '../src/utils/chat-meal-intent.js'

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
  const clock = { day: '2026-10-28' }, route = options.route || {entry:'conversation'}
  let serial = 100, flow, snapshotOverride = null
  const id = () => uuid(++serial)
  const profile = () => { const value=({ onboarded: true, completeProfile: true, source: 'api', householdId: identity.householdId,
    selfMemberId: 'self', defaultDiners: ['self', 'father'], healthConfiguration: { consultation: { available: true }, meal_plan: { available: true } },
    members: [{ id: 'self', relation: '本人', name: '合成本人', healthMemberId: member, allergyStatus: 'set', allergies: ['花生'], doctorStatus: 'none' },
      { id: 'father', relation: '父亲', name: '合成家人', healthMemberId: relative, restrictionStatus: 'set', restrictions: ['少辣'] }],
  });if(options.relativeFirst)value.members.reverse();if(options.diners)value.defaultDiners=options.diners;return value }
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
    const publish = patch => {
      state = { ...(state || fresh()), ...patch }
      const row = selected && threads.get(selected)
      if (row && state.requestId) row.taskSnapshot = clone({ requestId: state.requestId, status: state.status, result: state.result })
      onChange(clone(state))
    }
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
        publish({ entry: row ? entryFor(row) : null, ...(row?.taskSnapshot || {}), readOnly: !!row?.businessDate && row.businessDate < clock.day })
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
      async restoreReferenceRequest(threadId,requestId) {
        const row=threads.get(threadId)
        assert.ok(row&&row.owner===identity.scope&&row.memberId===state.memberId)
        selected=threadId;bindings.set(bindingKey(),threadId)
        publish({entry:entryFor(row),requestId,status:'needs_input',result:{type:'needs_input',questions:['合成待补充问题']}})
        return true
      },
      async acceptConsent() { calls.push({ action: 'consent' }) },
      pause() { generation++ },
      async resume() { return true },
      async refresh() { calls.push({ action: 'refresh' }) },
      invalidateThread() { publish({ invalidated: true, available: false, entry: null }) },
      publish,
    }
    return flow
  }
  const deps = { watch,createChatEntryTransition,createChatKeyboardLayout, mealQuestionAction,readDailyMealPlan:options.readDailyMealPlan|| (async(_family,date)=>({date,status:'absent',version:0,meals:[]})),selectChatPrompts,chatTimestamp,chatBusinessDate,rememberChatEntry(){},computed, reactive, ref, nextTick:options.nextTick||nextTick, defineProps: () => ({ route }),
    onMounted: fn => { hooks.mount = fn }, onUnmounted: fn => { hooks.unmount = fn }, onShow: fn => { hooks.show = fn }, onHide: fn => { hooks.hide = fn },
    chatPresentation, chooseReference, isReferencePlan, HEALTH_TEXT_TASKS, parseChatMealIntent,isMealPlanningCancelled,
    newHealthRequestId: id, storageContext: () => identity.scope, getSession: () => ({ ...identity }), scopedStorage,
    loadCloudProfile: async () => profile(), localDate: value => value ? nextDay(clock.day) : clock.day,
    dailyArrangementState: () => ({ phase: 'idle', busy: false, date: clock.day, arrangement: null }),
    createDailyArrangementClient: ({ state }) => ({ pause() {},reset() { state.phase = 'idle'; state.busy = false; state.arrangement = null }, dispose() {},
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
  const page = scope.run(() => new Function('deps', `const {${Object.keys(deps).join(',')}}=deps;${code};return {entryView,welcomeMounted,askPrompt,dailyPlans,resumePlanQuestion,load,profile,task,question,messages,entryReady,presentation,state,chatBusy,retryBusy,chatError,draftImage,draftError,draftSaving,voiceBusy,historyOpen,conversationId,conversationThreadId,conversationBusinessDate,conversationReadOnly,newConversationWelcome,newConversation,selectConversation,sendQuestion}`)(deps))
  const historyRow = threadId => { const row = threads.get(threadId); return { thread_id: threadId, member_id: row.memberId, agent_slug: row.agent, business_date: row.businessDate } }
  return { ...page, calls, writes, identity, clock, hooks, scopedStorage, threads, addThread, historyRow,
    get flow(){return flow},
    publish: value => flow.publish(value), setSnapshot: value => { snapshotOverride = value },
    dispose() { hooks.unmount?.(); scope.stop() },
  }
}

test('a home suggestion appears and clears the composer before conversation creation or history reads finish',async()=>{
 const p=workflow({route:{}}),createGate=deferred(),historyGate=deferred(),submitGate=deferred()
 try{
  await p.load();const create=p.flow.createEntry,submit=p.flow.submit
  p.flow.createEntry=async()=>{await createGate.promise;await create()}
  p.flow.submit=async(...args)=>{await submitGate.promise;return submit(...args)}
  p.setSnapshot(async()=>{await historyGate.promise;return {messages:[],runs:[]}})
  const pending=p.askPrompt({text:'忙起来怎么规律吃饭？',action:'consultation'})
  const row=p.messages.value[0],localId=row.id
  assert.equal(row.text,'忙起来怎么规律吃饭？');assert.equal(row.status,'sending')
  assert.equal(row.requestId,undefined);assert.equal(p.question.value,'');assert.equal(p.chatBusy.value,true)
  await p.askPrompt({text:'不要重复发送',action:'consultation'})
  assert.equal(p.messages.value.length,1);assert.equal(p.question.value,'')
  createGate.resolve();await flush()
  assert.equal(p.messages.value[0].id,localId);assert.equal(p.question.value,'')
  historyGate.resolve();await flush()
  assert.equal(p.messages.value.length,1);assert.equal(p.messages.value[0].id,localId)
  p.question.value='下一条新草稿';submitGate.resolve();await pending
  const users=p.messages.value.filter(m=>m.role==='user')
  assert.equal(users.length,1);assert.equal(users[0].id,localId);assert.ok(users[0].requestId)
  assert.equal(p.question.value,'下一条新草稿');assert.equal(p.calls.filter(c=>c.action==='submit').length,1)
 }finally{createGate.resolve();historyGate.resolve();submitGate.resolve();p.dispose()}
})

test('history recovery cannot bind the newly displayed question to an old completed request',async()=>{
 const p=workflow({route:{}}),gate=deferred(),oldRequest=uuid(911)
 try{
  await p.load();const create=p.flow.createEntry
  p.flow.createEntry=async()=>{await gate.promise;await create()}
  const pending=p.askPrompt({text:'忙起来怎么规律吃饭？',action:'consultation'})
  p.publish({requestId:oldRequest,status:'completed',result:{type:'answer',text:'旧任务的回复'}})
  assert.equal(p.messages.value.find(m=>m.text==='忙起来怎么规律吃饭？').requestId,undefined)
  gate.resolve();await pending
  const row=p.messages.value.find(m=>m.text==='忙起来怎么规律吃饭？')
  assert.notEqual(row.requestId,oldRequest);assert.equal(p.messages.value.filter(m=>m.text===row.text).length,1)
 }finally{gate.resolve();p.dispose()}
})

for(const edit of ['unchanged','new draft','edited then erased'])test(`creation failure retains the displayed question and respects ${edit}`,async()=>{
 const p=workflow({route:{}}),gate=deferred()
 try{
  await p.load();p.flow.createEntry=async()=>{await gate.promise;throw new Error('合成创建失败')}
  const pending=p.askPrompt({text:'忙起来怎么规律吃饭？',action:'consultation'})
  assert.equal(p.question.value,'')
  if(edit!=='unchanged')p.question.value='新的草稿'
  if(edit==='edited then erased')p.question.value=''
  gate.resolve();await pending
  assert.equal(p.messages.value[0].text,'忙起来怎么规律吃饭？');assert.equal(p.messages.value[0].status,'failed')
  assert.equal(p.question.value,edit==='unchanged'?'忙起来怎么规律吃饭？':edit==='new draft'?'新的草稿':'')
  assert.equal(p.calls.filter(c=>c.action==='submit').length,0)
 }finally{gate.resolve();p.dispose()}
})

test('hiding during conversation history restores an unsubmitted question and rejects the late send',async()=>{
 const p=workflow({route:{}}),gate=deferred()
 try{
  await p.load();p.setSnapshot(async()=>{await gate.promise;return {messages:[],runs:[]}})
  const pending=p.askPrompt({text:'忙起来怎么规律吃饭？',action:'consultation'});await flush()
  assert.equal(p.question.value,'');p.hooks.hide()
  assert.equal(p.question.value,'忙起来怎么规律吃饭？')
  gate.resolve();await pending
  assert.equal(p.messages.value[0].status,'failed');assert.equal(p.calls.filter(c=>c.action==='submit').length,0)
 }finally{gate.resolve();p.dispose()}
})

test('an account change while preparing cannot republish the question or replace the new draft',async()=>{
 const p=workflow({route:{}}),gate=deferred()
 try{
  await p.load();p.setSnapshot(async()=>{await gate.promise;return {messages:[],runs:[]}})
  const pending=p.askPrompt({text:'旧账号的提问',action:'consultation'});await flush()
  p.identity.scope='account-b';p.identity.accountId='account-b';p.identity.householdId='family-b'
  await p.load();p.question.value='新账号草稿'
  gate.resolve();await pending
  assert.equal(p.question.value,'新账号草稿');assert.equal(p.messages.value.some(m=>m.text==='旧账号的提问'),false)
  assert.equal(p.calls.filter(c=>c.action==='submit').length,0)
 }finally{gate.resolve();p.dispose()}
})

test('invalidated history removes optimistic text without restoring private content into the composer',async()=>{
 const p=workflow({route:{}}),gate=deferred()
 try{
  await p.load();p.setSnapshot(async()=>{await gate.promise;throw Object.assign(new Error('来源已失效'),{code:409})})
  const pending=p.askPrompt({text:'忙起来怎么规律吃饭？',action:'consultation'});await flush()
  gate.resolve();await pending
  assert.deepEqual(p.messages.value,[]);assert.equal(p.question.value,'')
  assert.equal(p.calls.filter(c=>c.action==='submit').length,0)
 }finally{gate.resolve();p.dispose()}
})

test('a lost submission response reuses the displayed message and never clears the next draft',async()=>{
 const p=workflow({route:{}}),gate=deferred(),requestId=uuid(912)
 try{
  await p.load()
  p.flow.submit=async text=>{
   p.publish({requestId,status:'提交中',busy:true,submitUnknown:true,canRetry:true,pendingText:text})
   await gate.promise;p.publish({busy:false,error:'提交结果尚未确认'});return false
  }
  const pending=p.askPrompt({text:'忙起来怎么规律吃饭？',action:'consultation'}),id=p.messages.value[0].id
  await flush();assert.equal(p.messages.value.filter(m=>m.role==='user').length,1)
  assert.equal(p.question.value,'');p.question.value='下一条草稿';gate.resolve();await pending
  const row=p.messages.value.find(m=>m.role==='user')
  assert.equal(row.id,id);assert.equal(row.requestId,requestId);assert.equal(row.status,'unknown')
  assert.equal(p.question.value,'下一条草稿')
  p.publish({submitUnknown:false,canRetry:false,status:'queued',error:''})
  assert.equal(p.question.value,'下一条草稿');assert.equal(p.messages.value.filter(m=>m.role==='user').length,1)
 }finally{gate.resolve();p.dispose()}
})

test('plain login or cold entry shows home despite an existing server daily conversation',async()=>{
  const p=workflow({route:{}})
  try{
    await p.load();await flush()
    assert.equal(p.welcomeMounted.value,true)
    assert.equal(p.entryView.value.phase,'home')
    assert.deepEqual(p.messages.value,[])
    assert.notEqual(p.conversationId.value,p.identity.dailyThread)
    assert.equal(p.conversationThreadId.value,'')
    assert.equal(p.calls.some(c=>c.action==='snapshot'||c.action==='create'||c.action==='submit'),false)
    assert.equal(p.writes.some(w=>w.key==='homepage-conversation'||w.key==='homepage-chat-task'),false)
    const id=p.conversationId.value
    await p.load();await flush()
    assert.equal(p.conversationId.value,id,'a reread must not create a new landing identity')
  }finally{p.dispose()}
})

test('home ignores saved conversation and pending task without deleting or replacing them',async()=>{
  const p=workflow({route:{}}),oldId=uuid(91)
  const saved={id:oldId,threadId:oldId,memberId:member,scope:p.identity.scope}
  const pending={memberId:member,type:'reference_meal_preview',date:p.clock.day,conversationId:oldId,requestId:uuid(92),submitUnknown:true}
  try{
    p.scopedStorage.setStorageSync('homepage-conversation',saved)
    p.scopedStorage.setStorageSync('homepage-chat-task',pending)
    await p.load();await flush()
    assert.equal(p.welcomeMounted.value,true)
    assert.deepEqual(p.messages.value,[])
    assert.notEqual(p.conversationId.value,oldId)
    assert.deepEqual(p.scopedStorage.getStorageSync('homepage-conversation'),saved)
    assert.deepEqual(p.scopedStorage.getStorageSync('homepage-chat-task'),pending)
    assert.equal(p.calls.some(c=>c.action==='snapshot'||c.action==='submit'),false)
  }finally{p.dispose()}
})

test('the first home question starts its own conversation and return preserves its draft and messages',async()=>{
  const p=workflow({route:{}})
  try{
    await p.load();await flush()
    p.question.value='合成的首页新问题';await p.sendQuestion();await flush()
    const threadId=p.conversationThreadId.value,id=p.conversationId.value
    assert.notEqual(threadId,p.identity.dailyThread)
    assert.equal(p.calls.filter(c=>c.action==='create').length,1)
    assert.equal(p.calls.filter(c=>c.action==='submit').length,1)
    assert.equal(p.entryView.value.phase==='home',false)
    assert.equal(p.messages.value.some(m=>m.id==='daily-old'),false)
    p.question.value='合成的未发送草稿';p.hooks.hide();p.hooks.show();await flush()
    assert.equal(p.conversationId.value,id)
    assert.equal(p.conversationThreadId.value,threadId)
    assert.equal(p.question.value,'合成的未发送草稿')
    assert.ok(p.messages.value.some(m=>m.text==='合成的首页新问题'))
    assert.equal(p.calls.filter(c=>c.action==='submit').length,1)
  }finally{p.dispose()}
})

test('returning to an untouched home preserves the home and its unsubmitted draft',async()=>{
  const p=workflow({route:{}})
  try{
    await p.load();await flush()
    const id=p.conversationId.value
    p.hooks.hide();p.hooks.show();await flush()
    assert.equal(p.welcomeMounted.value,true)
    p.question.value='尚未发送';p.hooks.hide();p.hooks.show();await flush()
    assert.equal(p.conversationId.value,id)
    assert.equal(p.question.value,'尚未发送')
    assert.equal(p.calls.some(c=>c.action==='snapshot'||c.action==='create'||c.action==='submit'),false)
  }finally{p.dispose()}
})

test('choosing history from home opens that thread and later rereads do not reset it to home',async()=>{
  const p=workflow({route:{}})
  try{
    await p.load();await p.selectConversation(p.historyRow(p.identity.dailyThread));await flush()
    assert.equal(p.conversationThreadId.value,p.identity.dailyThread)
    assert.ok(p.messages.value.some(m=>m.id==='daily-old'))
    assert.equal(p.welcomeMounted.value,false)
    await p.load();await flush()
    assert.equal(p.conversationThreadId.value,p.identity.dailyThread)
    assert.ok(p.messages.value.some(m=>m.id==='daily-old'))
  }finally{p.dispose()}
})

test('a business question prepares its own conversation without restoring unrelated old messages',async()=>{
  const p=workflow({route:{question:'合成的订单咨询'}})
  try{
    await p.load();await flush()
    assert.equal(p.question.value,'合成的订单咨询')
    assert.deepEqual(p.messages.value,[])
    await p.sendQuestion()
    assert.equal(p.calls.filter(c=>c.action==='submit').at(-1).text,'合成的订单咨询')
    assert.notEqual(p.conversationThreadId.value,p.identity.dailyThread)
  }finally{p.dispose()}
})

test('history selected from an explicit task carries conversation intent through navigation',async()=>{
  const p=workflow({route:{taskType:'consultation'}})
  try{
    await p.load();await p.selectConversation(p.historyRow(p.identity.dailyThread))
    assert.equal(p.calls.find(c=>c.action==='reLaunch').url,'/pages/chat/index?entry=conversation')
    assert.equal(p.scopedStorage.getStorageSync('homepage-conversation').threadId,p.identity.dailyThread)
  }finally{p.dispose()}
})

test('unknown submission blocks new questions but allows idle retry of its original request',async()=>{
  const p=workflow()
  try{
    await p.load()
    p.publish({submitUnknown:true,canRetry:true,busy:false,loading:false,refreshing:false})
    assert.equal(p.chatBusy.value,true)
    assert.equal(!!p.retryBusy.value,false)
    p.publish({refreshing:true});assert.equal(p.retryBusy.value,true)
    p.publish({refreshing:false,busy:true});assert.equal(p.retryBusy.value,true)
  }finally{p.dispose()}
})

for(const returnImmediately of [false,true])test(`leaving during the pre-submit scroll cancels the pending send${returnImmediately?' even after immediately returning':''}`,async()=>{
  const reached=deferred(),scroll=deferred()
  let holdScroll=false
  const p=workflow({nextTick:async()=>{
    if(holdScroll){holdScroll=false;reached.resolve();await scroll.promise}
    await nextTick()
  }})
  let pending
  try{
    await p.load()
    const threadId=p.conversationThreadId.value,text='合成离页前尚未提交的问题'
    p.question.value=text;holdScroll=true
    pending=p.sendQuestion()
    await reached.promise
    p.hooks.hide()
    if(returnImmediately){
      p.hooks.show();await flush()
      assert.equal(p.entryReady.value,true)
      assert.equal(p.chatBusy.value,false,'the returned page has finished checking its retained task')
    }
    scroll.resolve();await pending
    assert.equal(p.calls.filter(call=>call.action==='submit').length,0)
    assert.equal(p.threads.get(threadId).messages.some(message=>message.text===text),false)
    assert.equal(p.question.value,text,'an unsubmitted question remains available as a draft')
  }finally{scroll.resolve();await pending;p.dispose()}
})

test('typed meal intent uses the current profile and a dinner revision preserves the other meals', async () => {
  let saved=null
  const p = workflow({readDailyMealPlan:async(_family,date)=>saved||{date,status:'absent',version:0,meals:[]}})
  try {
    await p.load()
    const initialThread = p.conversationThreadId.value,first='按我的档案为我配餐'
    p.question.value=first;await p.sendQuestion()
    const original=p.calls.filter(call=>call.action==='submit').at(-1)
    assert.equal(original.taskType,'reference_meal_preview')
    assert.deepEqual(original.selection,{mode:'reference',family_id:'family-a',plan_date:p.clock.day,participant_ids:['self'],meal_types:['breakfast','lunch','dinner'],daily_base_version:0})
    assert.equal(original.memberId,member)
    assert.equal(p.profile.value.members[0].allergies[0],'花生')
    saved={date:p.clock.day,status:'ready',version:1,meals:['breakfast','lunch','dinner'].map(meal_type=>({meal_type,members:[{id:'self'}],meal:{dishes:[{name:meal_type}]},source:{id:'saved-'+meal_type}}))}
    const untouched=clone(saved.meals.slice(0,2))
    const revision='晚餐换成清淡一点的，早餐和午餐保持原样'
    p.question.value=revision;await p.sendQuestion()
    const submits = p.calls.filter(call => call.action === 'submit')
    assert.deepEqual(submits.map(call=>call.text),[first,revision])
    assert.ok(submits.every(call=>call.taskType==='reference_meal_preview'))
    assert.deepEqual(submits[1].selection,{...original.selection,meal_types:['dinner'],daily_base_version:1})
    assert.deepEqual(saved.meals.slice(0,2),untouched)
    p.question.value='只改晚餐，其他两餐保持原样';await p.sendQuestion()
    assert.equal(p.calls.filter(call=>call.action==='submit').at(-1).taskType,'reference_meal_preview')
    p.question.value='给我的父亲调整今天晚餐';await p.sendQuestion()
    assert.deepEqual(p.calls.filter(call=>call.action==='submit').at(-1).selection.participant_ids,['father'])
    assert.equal(p.conversationThreadId.value,initialThread,'meal tasks remain attached to the visible conversation')
    assert.equal(p.calls.some(call=>['startPlan','loadChatMealPlan'].includes(call.action)),false)
  } finally { p.dispose() }
})

for(const prompt of [false,true])test(`nutrition questions leave a pending meal follow-up${prompt?' from ordinary prompt cards':' when typed'}`,async()=>{
  const p=workflow()
  try{
    await p.load()
    for(const text of ['日常蛋白质怎么选？','蔬菜怎么做更好吃？','鸡蛋番茄怎么搭配？','早餐怎样省时准备？']){
      p.question.value='按我的档案为我配餐';await p.sendQuestion()
      p.publish({status:'completed',result:{type:'needs_input',questions:['需要安排哪些餐次？']}})
      p.question.value=text;await p.sendQuestion(prompt?'consultation':'')
      assert.equal(p.calls.filter(call=>call.action==='submit').at(-1).taskType,'consultation',text)
    }
  }finally{p.dispose()}
})

test('natural meal wording needs no button, keyword or prompt action; general nutrition stays consultation',async()=>{
  const p=workflow()
  try{
    await p.load()
    for(const text of ['今天怎么吃','帮我搭配今天的三餐','晚餐推荐一下','给我安排明天早餐']){
      p.question.value=text;await p.sendQuestion('consultation')
      assert.equal(p.calls.filter(call=>call.action==='submit').at(-1).taskType,'reference_meal_preview',text)
    }
    p.publish({status:'completed',result:{type:'needs_input',questions:['请补充资料']}})
    for(const text of ['什么是配餐','请解释蛋白质的作用','不要为我配餐，介绍膳食纤维','停止配餐','取消这次配餐','不要给父亲配餐']){
      p.question.value=text;await p.sendQuestion()
      assert.equal(p.calls.filter(call=>call.action==='submit').at(-1).taskType,'consultation',text)
    }
    const count=p.calls.filter(call=>call.action==='submit').length
    p.question.value='为我安排下周三餐';await p.sendQuestion()
    assert.equal(p.calls.filter(call=>call.action==='submit').length,count)
    assert.match(p.chatError.value,/今天或明天/)
    assert.equal(p.question.value,'为我安排下周三餐')
  }finally{p.dispose()}
})

test('a needs-input answer can narrow the plan to dinner without repeating a generation keyword',async()=>{
  const p=workflow()
  try{
    await p.load();p.question.value='按档案为我配餐';await p.sendQuestion()
    p.publish({status:'completed',result:{type:'needs_input',questions:['需要安排哪些餐次？']}})
    p.question.value='只要晚餐';await p.sendQuestion()
    const last=p.calls.filter(call=>call.action==='submit').at(-1)
    assert.deepEqual(last.selection.meal_types,['dinner'])
    assert.equal(last.taskType,'reference_meal_preview')
  }finally{p.dispose()}
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
    for (const call of selected) assert.deepEqual(call.selection, { mode: 'reference', family_id: 'family-a', plan_date: '2026-10-29', participant_ids: ['father', 'self'], meal_types: ['lunch'],daily_base_version:0 })
    const submitted = p.calls.filter(call => call.action === 'submit')
    assert.equal(submitted.length, 1); assert.equal(submitted[0].taskType, 'reference_meal_preview'); assert.equal(submitted[0].text, question)
    assert.equal(p.profile.value.members[0].allergies[0], '花生')
  } finally { p.dispose() }
})

for (const followUp of ['请帮我安排今天三餐', '可以，直接安排三餐', '体重70公斤，没有过敏']) {
  test(`reference needs_input续聊保留线程和选择：${followUp}`, async () => {
    const p = workflow()
    try {
      await p.load(); p.question.value = '整理本人今天三餐'; await p.sendQuestion('reference_meal_preview')
      const original = p.calls.filter(call => call.action === 'submit').at(-1)
      p.publish({ status: 'completed', result: { type: 'needs_input', questions: ['请补充就餐资料'] } })
      p.question.value = followUp; await p.sendQuestion()
      const latest = p.calls.filter(call => call.action === 'submit').at(-1)
      assert.equal(latest.taskType, 'reference_meal_preview')
      assert.equal(latest.threadId, original.threadId)
      assert.deepEqual(latest.selection, original.selection)
    } finally { p.dispose() }
  })
}

test('选回会话只读验证后恢复未完成reference上下文，取消后不再恢复', async () => {
  const p = workflow()
  try {
    await p.load(); const main = p.conversationThreadId.value
    p.question.value = '整理今天三餐'; await p.sendQuestion('reference_meal_preview')
    const original = p.calls.filter(call => call.action === 'submit').at(-1)
    p.publish({ status: 'completed', result: { type: 'needs_input', questions: ['请补充就餐资料'] } })
    await p.newConversation()
    const writes = p.calls.filter(call => call.action === 'submit' || call.action === 'create').length
    await p.selectConversation(p.historyRow(main))
    assert.equal(p.task.value.taskType, 'reference_meal_preview')
    assert.equal(p.task.value.entry.thread_id, original.threadId)
    assert.equal(p.calls.filter(call => call.action === 'submit' || call.action === 'create').length, writes)
    p.question.value = '体重70公斤'; await p.sendQuestion()
    assert.equal(p.calls.filter(call => call.action === 'submit').at(-1).threadId, original.threadId)
    p.publish({ status: 'completed', result: { type: 'needs_input', questions: ['请补充就餐资料'] } })
    p.question.value = '取消配餐，换个话题，解释膳食纤维'; await p.sendQuestion()
    assert.equal(p.calls.filter(call => call.action === 'submit').at(-1).taskType, 'consultation')
    await p.newConversation(); await p.selectConversation(p.historyRow(main))
    assert.equal(p.task.value.taskType, 'consultation')
  } finally { p.dispose() }
})

for (const field of ['scope', 'threadId', 'requestId']) {
  test(`缓存special的${field}不匹配时保持已验证主咨询，不提交或创建历史任务`, async () => {
    const p = workflow()
    try {
      await p.load(); const main = p.conversationThreadId.value, conversation = p.conversationId.value
      p.question.value = '整理今天三餐'; await p.sendQuestion('reference_meal_preview')
      p.publish({ status: 'completed', result: { type: 'needs_input', questions: ['请补充资料'] } })
      const key = 'conversation-task:' + conversation, saved = p.scopedStorage.getStorageSync(key)
      assert.ok(saved)
      p.scopedStorage.setStorageSync(key, { ...saved, [field]: field === 'scope' ? 'another-session' : uuid(999) })
      await p.newConversation()
      const writes = p.calls.filter(call => call.action === 'submit' || call.action === 'create').length
      await p.selectConversation(p.historyRow(main))
      assert.equal(p.task.value.taskType, 'consultation')
      assert.equal(p.task.value.entry.thread_id, main)
      assert.equal(p.calls.filter(call => call.action === 'submit' || call.action === 'create').length, writes)
    } finally { p.dispose() }
  })
}

test('needs_input期间明确改变日期和家庭成员仍生成新选择，非法日期不提交', async () => {
  const p = workflow()
  try {
    await p.load(); p.question.value = '整理今天早餐'; await p.sendQuestion('reference_meal_preview')
    const original = p.calls.filter(call => call.action === 'submit').at(-1)
    p.publish({ status: 'completed', result: { type: 'needs_input', questions: ['请补充资料'] } })
    p.question.value = '请给全家安排明天晚餐'; await p.sendQuestion()
    const latest = p.calls.filter(call => call.action === 'submit').at(-1)
    assert.equal(latest.taskType, 'reference_meal_preview')
    assert.notEqual(latest.threadId, original.threadId)
    assert.equal(latest.selection.plan_date, '2026-10-29')
    assert.deepEqual(latest.selection.participant_ids, ['father', 'self'])
    assert.deepEqual(latest.selection.meal_types, ['dinner'])
    p.publish({ status: 'completed', result: { type: 'needs_input', questions: ['请补充资料'] } })
    const submitted = p.calls.filter(call => call.action === 'submit').length
    p.question.value = '请帮我安排后天三餐'; await p.sendQuestion()
    assert.equal(p.calls.filter(call => call.action === 'submit').length, submitted)
    assert.match(p.chatError.value, /今天或明天/)
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

test('a relative meal task preserves its self-owned conversation and both actors histories',async()=>{
  const p=workflow({relativeFirst:true,diners:['father']})
  try{
    await p.load();await p.newConversation()
    p.question.value='本人的咨询';await p.sendQuestion()
    const anchor=p.conversationThreadId.value,group=p.conversationId.value
    p.question.value='给父亲安排今天午餐';await p.sendQuestion('reference_meal_preview')
    assert.equal(p.calls.filter(call=>call.action==='submit').at(-1).memberId,relative)
    assert.equal(p.scopedStorage.getStorageSync('conversation-index:'+anchor).memberId,member)
    assert.equal(p.scopedStorage.getStorageSync('homepage-chat-task').memberId,member)
    assert.equal(p.scopedStorage.getStorageSync('homepage-chat-task').taskMemberId,relative)
    await p.selectConversation(p.historyRow(p.identity.dailyThread));await p.selectConversation(p.historyRow(anchor))
    assert.equal(p.conversationId.value,group)
    assert.equal(p.messages.value.find(message=>message.text==='本人的咨询').memberId,member)
    assert.equal(p.messages.value.find(message=>message.text==='给父亲安排今天午餐').memberId,relative)
  }finally{p.dispose()}
})

test('a relative needs-input meal question reenters within its original conversation and task',async()=>{
  const p=workflow({relativeFirst:true,diners:['father']})
  try{
    await p.load();await p.newConversation();p.question.value='先保留本人的咨询';await p.sendQuestion()
    const group=p.conversationId.value,reference=uuid(900),request=uuid(901)
    p.addThread(reference,{memberId:relative,taskType:'reference_meal_preview',agent:'health-meal-planner'})
    p.dailyPlans.value[p.clock.day]={date:p.clock.day,status:'absent',version:0,meals:[],pending:{status:'needs_input',member_id:relative,thread_id:reference,request_id:request,questions:['合成待补充问题'],selection:{mode:'reference',family_id:'family-a',plan_date:p.clock.day,participant_ids:['father'],meal_types:['lunch'],daily_base_version:0}}}
    await p.resumePlanQuestion()
    assert.equal(p.scopedStorage.getStorageSync('homepage-chat-task').conversationId,group)
    await p.load()
    assert.equal(p.conversationId.value,group);assert.equal(p.task.value.taskType,'reference_meal_preview')
    assert.equal(p.task.value.entry.thread_id,reference)
    assert.ok(p.messages.value.some(message=>message.text==='先保留本人的咨询'))
    assert.equal(p.calls.filter(call=>call.action==='submit').length,1)
  }finally{p.dispose()}
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


test('meal suggestion cards use the same structured route as typed requests',async()=>{
  const p=workflow()
  try{
    await p.load()
    for(const prompt of CHAT_PROMPT_POOL.slice(0,6))await p.askPrompt(prompt)
    assert.equal(p.calls.filter(call=>call.action==='submit').length,6)
    assert.ok(p.calls.filter(call=>call.action==='submit').every(call=>call.taskType==='reference_meal_preview'))
    assert.equal(p.calls.some(call=>call.action==='startPlan'),false)
  }finally{p.dispose()}
})
