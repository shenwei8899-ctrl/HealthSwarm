import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { ref, reactive, computed } from 'vue'
import { conversationPreviewState, createConversationPreview } from '../src/services/conversation-preview.js'

const row = { thread_id:'root',member_id:'self',title:'合成历史' }
const snapshot = (id,related=[]) => ({messages:[{id,role:'assistant',text:id,createdAt:'2026-11-10T00:00:00Z'}],relatedThreads:related.map(thread_id=>({thread_id}))})
const deferred=()=>{let resolve;const promise=new Promise(yes=>resolve=yes);return {promise,resolve}}
const turn=()=>new Promise(resolve=>setImmediate(resolve))
function fixture(read) {
  const state=conversationPreviewState(),denied=[],calls=[];let identity='one'
  const client=createConversationPreview({state,context:()=>identity,read:async id=>{calls.push(id);return read(id)},storage:{getStorageSync:()=>undefined},onDenied:(...args)=>denied.push(args)})
  return {state,client,calls,denied,changeIdentity(){identity='two'}}
}

test('preview reads linked history once, handles cycles and keeps deterministic message order',async()=>{
  const h=fixture(async id=>snapshot(id,id==='root'?['child','sibling']:id==='child'?['root','sibling']:['child']))
  await h.client.open(row)
  assert.deepEqual(h.calls,['root','child','sibling']);assert.equal(h.state.messages.length,3);assert.equal(h.state.loading,false)
})
test('root messages become readable before a related thread finishes',async()=>{
  const gate=deferred(),h=fixture(async id=>id==='root'?snapshot(id,['child']):gate.promise)
  const reading=h.client.open(row);await turn();assert.deepEqual(h.state.messages.map(m=>m.id),['root']);assert.equal(h.state.loading,true)
  gate.resolve(snapshot('child'));await reading;assert.equal(h.state.messages.length,2)
})
test('rapidly selecting another preview discards a late previous response',async()=>{
  const gate=deferred(),h=fixture(async id=>id==='root'?gate.promise:snapshot(id))
  const previous=h.client.open(row);await h.client.open({...row,thread_id:'next'});gate.resolve(snapshot('late-private'));await previous
  assert.deepEqual(h.state.messages.map(m=>m.id),['next'])
})
test('closing, disposing or changing identity prevents late private messages from appearing',async()=>{
  for(const action of ['clear','dispose','identity']){
    const gate=deferred(),h=fixture(()=>gate.promise),reading=h.client.open(row)
    if(action==='identity')h.changeIdentity();else h.client[action]()
    gate.resolve(snapshot('private'));await reading;assert.deepEqual(h.state.messages,[]);assert.equal(h.state.loading,false)
  }
})
test('a denied root is reported without reading children or restoring any task',async()=>{
  const h=fixture(async()=>{throw Object.assign(Error('denied'),{code:403})});await h.client.open(row)
  assert.deepEqual(h.state.messages,[]);assert.deepEqual(h.denied,[['root',403]]);assert.match(h.state.error,/不可访问/)
})
test('a denied child leaves authorized root messages readable',async()=>{
  const h=fixture(async id=>{if(id==='root')return snapshot(id,['child']);throw Object.assign(Error('denied'),{code:410})})
  await h.client.open(row);assert.deepEqual(h.state.messages.map(m=>m.id),['root']);assert.match(h.state.notice,/授权/);assert.deepEqual(h.denied,[])
})

for (const code of [403, 404, 409, 410, 'NETWORK_ERROR']) {
  test(`cached related messages are removed on ${code} only when access is denied`,async()=>{
    const gate=deferred(),state=conversationPreviewState(),invalidated=[]
    const root=snapshot('root',['child']),child=snapshot('private-child')
    const cache={read:async id=>{
      if(id==='root')return root
      await gate.promise
      throw Object.assign(Error('unavailable'),{code})
    },invalidate:(...args)=>invalidated.push(args)}
    const client=createConversationPreview({state,cache,context:()=> 'session',storage:{getStorageSync:()=>undefined}})
    const reading=client.open(row,{fromCache:true,snapshot:root,snapshots:[{...root,threadId:'root'},{...child,threadId:'child'}]})
    await turn()
    assert.deepEqual(state.messages.map(m=>m.id),['root','private-child'])
    gate.resolve();await reading
    const denied=code!=='NETWORK_ERROR'
    assert.deepEqual(state.messages.map(m=>m.id),denied?['root']:['root','private-child'])
    assert.deepEqual(invalidated,denied?[['child','self']]:[])
    assert.equal(state.loading,false)
    assert.match(state.notice,denied?/授权/:/重新读取/)
  })
}
test('an authentication failure rejects sibling responses that arrive later',async()=>{
  const gate=deferred(),h=fixture(async id=>{if(id==='root')return snapshot(id,['denied','late']);if(id==='denied')throw Object.assign(Error('expired'),{code:401});return gate.promise})
  await h.client.open(row);gate.resolve(snapshot('late-private'));await turn();assert.deepEqual(h.state.messages,[]);assert.deepEqual(h.denied,[['root',401]])
})
test('legacy reference history remains readable without writing storage or opening a task',async()=>{
  const state=conversationPreviewState(),calls=[]
  const client=createConversationPreview({state,read:async id=>{calls.push(id);return snapshot(id)},context:()=> 'one',storage:{getStorageSync:key=>key==='conversation-index:root'?{memberId:'self',id:'group'}:key==='conversation-threads:group'?[{thread_id:'legacy',task_type:'reference_meal_preview'}]:undefined}})
  await client.open(row);assert.deepEqual(calls,['root','legacy']);assert.equal(state.messages.length,2)
})

test('read-only business cards reject direct calls to mutating or navigation handlers',async()=>{
  for(const [name,handler] of [['HealthChatBusinessCard','save'],['HealthChatBusinessCard','inspect'],['ReferenceMealPlanCard','purchase'],['ChatMealRecordCard','withdraw'],['ChatMealRecordCard','detail'],['ConversationFoodPackages','open']]){
    const calls=[],props={readOnly:true,result:{kind:'meal_plan_preview',data:{preview_id:'preview'}},plan:{preview_id:'preview'},receipt:{id:'record'},requestId:'request'}
    const deps={ref,reactive,computed,watch:()=>{},onUnmounted:()=>{},onMounted:()=>{},onShow:()=>{},onHide:()=>{},onUnload:()=>{},defineProps:()=>props,defineEmits:()=>()=>{},storageContext:()=> 'one',request:async()=>calls.push('http'),commerce:{connect:async()=>calls.push('commerce')},scopedStorage:{getStorageSync:()=>{calls.push('storage')}},chatMealRecordState:()=>({record:{status:'saved'}}),createChatMealRecordClient:()=>({withdraw:async()=>calls.push('withdraw'),hide(){}}),uni:{navigateTo:()=>calls.push('navigate')}}
    const source=readFileSync(new URL(`../src/components/${name}.vue`,import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
    const action=new Function('deps',`const {${Object.keys(deps).join(',')}}=deps;${source};return ${handler}`)(deps)
    await action({available:true,offer_token:'token'});assert.deepEqual(calls,[],name+'.'+handler)
  }
})
