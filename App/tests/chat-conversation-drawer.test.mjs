import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { computed, effectScope, nextTick, reactive, ref, watch } from 'vue'
import { scopedStorage } from '../src/services/storage.js'
import { conversationSummary, conversationTitle, readConversations, readChatSnapshot } from '../src/services/cloud-chat.js'
import { backdropOpacity, clampDragOffset, DRAWER_SETTLE_MS, shouldCloseDrawer } from '../src/utils/drawer-swipe.js'

const member = '11111111-1111-4111-8111-111111111111'
const thread = number => `22222222-2222-4222-8222-${String(number).padStart(12, '0')}`
const item = (number, extra = {}) => ({ thread_id: thread(number), member_id: member, agent_slug: 'health-consultation', business_date: null, title: '合成首问', unavailable: false, created_at: '2026-10-28T01:00:00+00:00', ...extra })
let revision = 'synthetic-session'
globalThis.uni = { getStorageSync: () => ({ clientRevision: revision }), getSystemInfoSync: () => ({ windowWidth: 375 }) }
const pageResponse = (items, extra = {}) => ({ data: { items, has_more: false, next_offset: null, ...extra } })
const turn = () => new Promise(resolve => setImmediate(resolve))
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }

test('conversation directory uses only GET and projects the member-bound consultation fields', async () => {
  const calls = []
  const result = await readConversations(member, 20, async options => {
    calls.push(options)
    return pageResponse([item(1, { private_metadata: 'must not be projected' })], { has_more: true, next_offset: 21 })
  })
  assert.deepEqual(calls, [{ path: `/api/health/v1/members/${member}/consultations?limit=20&offset=20` }])
  assert.deepEqual(result, { items: [item(1)], hasMore: true, nextOffset: 21 })
})

test('directory rejects malformed identity, foreign member/agent, invalid dates and unsafe pagination', async () => {
  const badItems = [
    { ...item(1), thread_id: 'not-a-thread' },
    { ...item(1), member_id: thread(9) },
    { ...item(1), agent_slug: 'another-agent' },
    { ...item(1), business_date: '2026-02-30' },
    { ...item(1), business_date: undefined },
    { ...item(1), created_at: 'yesterday' },
    { ...item(1), created_at: '2026-02-30T01:00:00Z' },
    { ...item(1), created_at: '2026-10-28T01:00:00' },
  ]
  for (const row of badItems) await assert.rejects(readConversations(member, 0, async () => pageResponse([row])), /目录返回不完整/)
  for (const offset of [-1, 0.5, '0', Number.MAX_SAFE_INTEGER]) await assert.rejects(readConversations(member, offset), /分页位置/)
  await assert.rejects(readConversations('not-a-member'), /健康资料/)
  for (const body of [
    pageResponse([item(1), item(1)]),
    pageResponse(Array.from({ length: 21 }, (_, number) => item(number))),
    pageResponse([], { has_more: true, next_offset: 20 }),
    pageResponse([item(1)], { has_more: true, next_offset: 0 }),
    pageResponse([item(1)], { has_more: true, next_offset: '1' }),
    pageResponse([item(1)], { next_offset: 1 }),
    pageResponse([item(1)], { has_more: 'false' }),
  ]) await assert.rejects(readConversations(member, 0, async () => body), /目录返回不完整/)
})

test('directory and snapshots reject a response arriving after the account changes', async () => {
  for (const read of [send => readConversations(member, 0, send), send => readChatSnapshot(thread(1), send)]) {
    const previous = revision
    await assert.rejects(read(async () => { revision += '-changed'; return { data: { ...pageResponse([item(1)]).data, history: [] } } }), /账号已变化/)
    revision = previous
  }
})

test('snapshots reject mismatched thread metadata before exposing messages and retain only safe metadata', async () => {
  await assert.rejects(readChatSnapshot(thread(1), async () => ({ data: { thread: { id: thread(2) }, history: [{ type: 'human', content: 'foreign private text' }] } })), /当前选择不一致/)
  const result = await readChatSnapshot(thread(1), async () => ({ data: { thread: { id: thread(1), title: ' 今日\n饮食 ', agent_id: 'health-consultation', internal: 'not returned' }, history: [], runs: [] } }))
  assert.deepEqual(result, { messages: [], runs: [], relatedThreads: [], thread: { id: thread(1), title: '今日 饮食', agentId: 'health-consultation' } })
  assert.equal((await readChatSnapshot(thread(1), async () => ({ data: { history: [] } }))).thread, null)
})

test('titles use the first user message, keep emoji intact and distinguish image-only conversations', () => {
  assert.equal(conversationSummary([{ role: 'assistant', text: 'Ignore assistant summary' }, { role: 'user', text: ' 晚餐\n少放盐 ' }, { role: 'user', text: 'later' }]), '晚餐 少放盐')
  assert.equal(conversationSummary([{ role: 'user', text: '', image: { localPath: 'synthetic' } }]), '[图片]')
  assert.equal(conversationSummary([]), '新对话')
  assert.equal(conversationTitle('😀'.repeat(38)), '😀'.repeat(36) + '…')
  assert.equal(conversationTitle(null), '新对话')
})

function drawer(options = {}) {
  const props = reactive({ open: false, memberId: member, activeThreadId: '', busy: false, displayName: '合成用户' })
  const emitted = [], ready = [], hooks = {}, cache = new Map(), writes = []
  const identity = { scope: 'synthetic-scope', revision: 'one' }
  const deps = { computed, ref, watch, backdropOpacity, clampDragOffset, DRAWER_SETTLE_MS, shouldCloseDrawer, defineProps: () => props, defineEmits: () => (...args) => args[0]==='ready'?ready.push(args[1]):emitted.push(args),
    onShow: callback => { hooks.show = callback }, onHide: callback => { hooks.hide = callback }, onUnmounted: callback => { hooks.unmount = callback },
    readConversations: async () => ({ items: [], hasMore: false, nextOffset: null }),
    readChatSnapshot: async () => ({ messages: [] }), conversationTitle, conversationSummary,
    scopedStorage: { getStorageSync: key => cache.get(key), setStorageSync: (key, value) => { writes.push([key, value]); cache.set(key, value) } },
    storageContext: () => identity.scope, sessionRevision: () => identity.revision, ...options,
  }
  const source = readFileSync(new URL('../src/components/ChatConversationDrawer.vue', import.meta.url), 'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  const scope = effectScope()
  const state = scope.run(() => new Function('deps', `const {${Object.keys(deps).join(',')}}=deps;${source};return {rows,groups,loading,error,notice,hasMore,nextOffset,load,retry,close,newConversation,select,profile,dragOffset,dragPhase,panelStyle,backdropStyle,beginDrag,moveDrag,endDrag}`)(deps))
  return { ...state, props, emitted, cache, writes, identity, hooks,
    async open() { props.open = true; await nextTick(); await turn() },
    dispose() { hooks.unmount?.(); scope.stop() },
  }
}

test('directory titles render without requesting any history or writing a title cache', async () => {
  const today = new Date(Date.now() + 8 * 3600000).toISOString().slice(0,10)
  const p=drawer({readConversations:async()=>({items:[item(1,{business_date:today,title:'服务端首问'}),item(2,{unavailable:true,title:'该对话暂不可访问'})],hasMore:false,nextOffset:null}),
    readChatSnapshot:()=>{throw new Error('目录禁止读取完整历史')}})
  try{
    await p.open();assert.equal(p.loading.value,false);assert.equal(p.rows.value[0].title,'服务端首问');assert.equal(p.writes.length,0)
    p.select(p.rows.value[1]);assert.equal(p.emitted.length,0)
    p.select(p.rows.value[0]);assert.equal(p.emitted.at(-1)[0],'select');assert.match(p.notice.value,/授权或资料来源/)
    assert.equal(p.groups.value[0].label,'今天')
  }finally{p.dispose()}
})
test('cached private titles cannot replace a denied server directory title',async()=>{
 const p=drawer({readConversations:async()=>({items:[item(1,{title:'该对话暂不可访问',unavailable:true})],hasMore:false,nextOffset:null})})
 try{p.cache.set(`conversation-summary:${member}:${thread(1)}`,{title:'撤权前的私密问题'});await p.open();assert.equal(p.rows.value[0].title,'该对话暂不可访问')}finally{p.dispose()}
})
test('closing or changing the account rejects a late directory without private cache writes',async()=>{
 for(const change of ['close','account']){
  const wait=deferred(),p=drawer({readConversations:()=>wait.promise})
  try{await p.open();if(change==='close'){p.props.open=false;await nextTick()}else p.identity.scope='other-account'
   wait.resolve({items:[item(1)],hasMore:false,nextOffset:null});await turn();assert.deepEqual(p.rows.value,[]);assert.equal(p.writes.length,0)
  }finally{p.dispose()}
 }
})
test('reply activity blocks creation but permits history browsing and preserves the directory on close',async()=>{
 const p=drawer({readConversations:async()=>({items:[item(1)],hasMore:false,nextOffset:null})})
 try{await p.open();p.props.busy=true;p.newConversation();assert.equal(p.emitted.length,0);p.select(p.rows.value[0]);assert.equal(p.emitted.at(-1)[0],'select');p.props.browseBusy=true;p.select(p.rows.value[0]);assert.equal(p.emitted.length,1);p.profile();assert.deepEqual(p.emitted.at(-1),['profile']);p.close();assert.equal(p.rows.value.length,1)}finally{p.dispose()}
})
test('pagination retains its first page and retries the same failed offset',async()=>{
 let fail=true;const offsets=[]
 const p=drawer({readConversations:async(_member,offset)=>{offsets.push(offset);if(!offset)return {items:[item(1)],hasMore:true,nextOffset:1};if(fail)throw new Error('offline');return {items:[item(1),item(2)],hasMore:false,nextOffset:null}}})
 try{await p.open();await p.load(true);assert.equal(p.rows.value.length,1);assert.match(p.error.value,/暂时无法读取/);fail=false;await p.load(true);assert.deepEqual(offsets,[0,1,1]);assert.equal(p.rows.value.length,2)}finally{p.dispose()}
})


test('legacy local task links recover a short title in one read-only batch without downloading history',async()=>{
 const original=scopedStorage.getStorageSync,calls=[]
 scopedStorage.getStorageSync=key=>key==='conversation-index:'+thread(1)?{memberId:member,id:thread(90)}:key==='conversation-threads:'+thread(90)?[{thread_id:thread(2),task_type:'reference_meal_preview'}]:undefined
 try{
  const page=await readConversations(member,0,async options=>{
   calls.push(options)
   if(!options.method)return pageResponse([item(1,{title:'新对话'})])
   assert.equal(options.path.endsWith('/consultations/directory'),true)
   assert.deepEqual(options.data,{offset:0,links:[{root_thread_id:thread(1),thread_id:thread(2)}]})
   return pageResponse([item(1,{title:'旧餐单的首个问题'})])
  })
  assert.equal(page.items[0].title,'旧餐单的首个问题');assert.equal(calls.length,2)
  assert.equal(calls.some(call=>call.path.endsWith('/history')),false)
 }finally{scopedStorage.getStorageSync=original}
})

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))

test('reopening shows its directory before a delayed refresh and replaces revoked titles', async () => {
  const gate = deferred(); let calls = 0
  const p = drawer({readConversations:async()=>++calls===1?{items:[item(1)],hasMore:false,nextOffset:null}:gate.promise})
  try {
    await p.open(); p.close(); p.props.open=false; await nextTick(); await p.open()
    assert.equal(p.rows.value[0].title,'合成首问'); assert.equal(p.loading.value,true)
    gate.resolve({items:[item(1,{title:'该对话暂不可访问',unavailable:true})],hasMore:false,nextOffset:null}); await turn()
    assert.equal(p.rows.value[0].unavailable,true); assert.equal(p.rows.value[0].title,'该对话暂不可访问')
    p.select(item(1)); assert.equal(p.emitted.filter(event=>event[0]==='select').length,0)
  } finally {gate.resolve({items:[],hasMore:false,nextOffset:null});p.dispose()}
})

test('a failed refresh preserves rows and retries the first page rather than loading more', async () => {
  const offsets=[];let fail=false
  const p=drawer({readConversations:async(_id,offset)=>{offsets.push(offset);if(fail)throw Error('timeout');return {items:[item(1)],hasMore:true,nextOffset:1}}})
  try {
    await p.open();fail=true;await p.load();assert.equal(p.rows.value.length,1)
    fail=false;p.retry();await turn();assert.deepEqual(offsets,[0,0,0])
  } finally {p.dispose()}
})

test('refresh rebuilds the loaded window and cursor after an insertion at the front', async () => {
  let inserted=false;const offsets=[]
  const p=drawer({readConversations:async(_id,offset)=>{offsets.push(offset);return {items:[item(inserted?[3,1,2][offset]:[1,2][offset])],hasMore:offset<(inserted?2:1),nextOffset:offset<(inserted?2:1)?offset+1:null}}})
  try {
    await p.open();await p.load(true);inserted=true;await p.load()
    assert.deepEqual(p.rows.value.map(row=>row.thread_id),[thread(3),thread(1)])
    assert.equal(p.nextOffset.value,2);await p.load(true)
    assert.deepEqual(p.rows.value.map(row=>row.thread_id),[thread(3),thread(1),thread(2)])
    assert.deepEqual(offsets,[0,1,0,1,2])
  } finally {p.dispose()}
})

test('a changed login revision purges retained titles before reopening',async()=>{
  const gate=deferred();let calls=0
  const p=drawer({readConversations:async()=>++calls===1?{items:[item(1)],hasMore:false,nextOffset:null}:gate.promise})
  try{await p.open();p.props.open=false;await nextTick();p.identity.revision='new-login';await p.open();assert.deepEqual(p.rows.value,[])}
  finally{gate.resolve({items:[],hasMore:false,nextOffset:null});p.dispose()}
})

test('drag helpers clamp distance and decide only on a third of the panel or a fast flick', () => {
  assert.equal(clampDragOffset(80, 285), 80)
  assert.equal(clampDragOffset(-40, 285), 0)
  assert.equal(clampDragOffset(400, 285), 285)
  assert.equal(clampDragOffset(Number.NaN, 285), 0)
  assert.equal(clampDragOffset(50, 0), 0)
  assert.equal(shouldCloseDrawer({ distance: 95, width: 285, duration: 900 }), true)
  assert.equal(shouldCloseDrawer({ distance: 94, width: 285, duration: 900 }), false)
  assert.equal(shouldCloseDrawer({ distance: 40, width: 285, duration: 50 }), true)
  assert.equal(shouldCloseDrawer({ distance: 40, width: 285, duration: 900 }), false)
  assert.equal(shouldCloseDrawer({ distance: 10, width: 285, duration: 5 }), false)
  assert.equal(backdropOpacity(0, 285), 1)
  assert.equal(backdropOpacity(142.5, 285), 0.5)
  assert.equal(backdropOpacity(285, 285), 0)
  assert.equal(backdropOpacity(400, 285), 0)
  assert.equal(backdropOpacity(10, 0), 1)
})

test('the panel follows the finger one-to-one and snaps back below a third', async () => {
  const realNow = Date.now, p = drawer({ readConversations: async () => ({ items: [item(1)], hasMore: false, nextOffset: null }) })
  let clock = 1000000
  try {
    await p.open()
    Date.now = () => clock
    p.beginDrag({ touches: [{ clientX: 280, clientY: 120 }] })
    assert.equal(p.dragPhase.value, 'dragging')
    assert.equal(p.dragOffset.value, 0)
    p.moveDrag({ touches: [{ clientX: 200, clientY: 120 }] })
    assert.equal(p.dragOffset.value, 80)
    assert.equal(p.panelStyle.value.transform, 'translateX(-80px)')
    assert.ok(Math.abs(Number(p.backdropStyle.value.opacity) - (1 - 80 / 285)) < 1e-9)
    p.moveDrag({ touches: [{ clientX: 300, clientY: 120 }] })
    assert.equal(p.dragOffset.value, 0)
    p.moveDrag({ touches: [{ clientX: 200, clientY: 120 }] })
    clock += 800
    p.endDrag()
    assert.equal(p.dragPhase.value, 'settling')
    assert.equal(p.dragOffset.value, 0)
    await sleep(DRAWER_SETTLE_MS + 60)
    assert.deepEqual(p.emitted, [])
    assert.equal(p.dragPhase.value, '')
  } finally { Date.now = realNow; p.dispose() }
})

test('dragging a third of the panel closes the drawer once and retains the directory', async () => {
  const p = drawer({ readConversations: async () => ({ items: [item(1)], hasMore: false, nextOffset: null }) })
  try {
    await p.open()
    assert.equal(p.rows.value.length, 1)
    p.beginDrag({ touches: [{ clientX: 280, clientY: 120 }] })
    p.moveDrag({ touches: [{ clientX: 185, clientY: 120 }] })
    assert.equal(p.dragOffset.value, 95)
    p.endDrag()
    assert.equal(p.dragPhase.value, 'settling')
    assert.equal(p.dragOffset.value, 285)
    await sleep(DRAWER_SETTLE_MS + 60)
    assert.deepEqual(p.emitted, [['close']])
    assert.equal(p.rows.value.length, 1)
    assert.equal(p.dragPhase.value, '')
  } finally { p.dispose() }
})

test('a short flick closes the drawer but the same slow drag does not', async () => {
  const realNow = Date.now
  try {
    for (const [elapsed, closes] of [[50, true], [900, false]]) {
      const p = drawer({ readConversations: async () => ({ items: [item(1)], hasMore: false, nextOffset: null }) })
      let clock = 1000000
      try {
        await p.open()
        Date.now = () => clock
        p.beginDrag({ touches: [{ clientX: 280, clientY: 120 }] })
        p.moveDrag({ touches: [{ clientX: 240, clientY: 120 }] })
        clock += elapsed
        p.endDrag()
        assert.equal(p.dragOffset.value, closes ? 285 : 0)
        await sleep(DRAWER_SETTLE_MS + 60)
        assert.deepEqual(p.emitted, closes ? [['close']] : [])
      } finally { Date.now = realNow; p.dispose() }
    }
  } finally { Date.now = realNow }
})

test('a drag cannot open the drawer, run while closed, or outlive a hidden page', async () => {
  const p = drawer({ readConversations: async () => ({ items: [item(1)], hasMore: false, nextOffset: null }) })
  try {
    p.beginDrag({ touches: [{ clientX: 280, clientY: 120 }] })
    assert.equal(p.dragPhase.value, '')
    await p.open()
    p.beginDrag({ touches: [{ clientX: 280, clientY: 120 }] })
    p.moveDrag({ touches: [{ clientX: 185, clientY: 120 }] })
    p.endDrag()
    assert.equal(p.dragPhase.value, 'settling')
    p.hooks.hide()
    assert.equal(p.dragPhase.value, '')
    assert.equal(p.dragOffset.value, 0)
    await sleep(DRAWER_SETTLE_MS + 60)
    assert.deepEqual(p.emitted, [])
  } finally { p.dispose() }
})
