import test from 'node:test'
import assert from 'node:assert/strict'
import { createDietJournalClient, journalState, mealDate } from '../src/services/diet-journal-client.js'

function harness(override = () => {}) {
  const state = journalState(), calls = []; let revision = 1, id = 0
  const client = createDietJournalClient({ state, revision: () => revision, newId: () => `request-${++id}`,
    send: async options => {
      calls.push(structuredClone(options)); const value = await override(options); if (value) return value
      return { data: options.path.endsWith('/members') ? [{id:'a',scopes:['diet_edit']},{id:'b',scopes:['diet_edit']}] : {records:[],next_offset:null} }
    } })
  return { state, client, calls, switchAccount() { revision++ } }
}
const meal = {meal_type:'lunch',eaten_at:'2026-10-16T12:00:00+08:00',items:[{name:'synthetic',grams:100}]}
test('meal date uses Beijing day across UTC midnight', () => {
  assert.equal(mealDate('2026-10-15T17:00:00Z'), '2026-10-16')
  assert.equal(mealDate('2026-10-16T01:00:00+08:00'), '2026-10-16')
  assert.equal(mealDate('2026-10-15T15:59:59Z'), '2026-10-15')
})
test('definite family rejection can be edited without resubmitting saved members', async () => {
  let count = 0
  const h = harness(options => {
    if (options.method === 'POST') return {data:{results:++count === 1 ? [
      {member_id:'a',status:'saved',id:'saved-a'},
      {member_id:'b',status:'failed',code:'nutrition_incomplete'}
    ] : [{member_id:'b',status:'saved',id:'saved-b'}]}}
  })
  await h.client.open(); await h.client.save([{memberId:'a',meal},{memberId:'b',meal}],false)
  assert.equal(h.state.canEditFailed,true); h.client.editFailed(); assert.equal(h.state.pending,null)
  await h.client.save([{memberId:'a',meal},{memberId:'b',meal}],true)
  const writes=h.calls.filter(c=>c.method==='POST')
  assert.notEqual(writes[0].data.group_id,writes[1].data.group_id)
  assert.deepEqual(writes[1].data.members.map(r=>r.member_id),['b'])
  assert.equal(writes[1].data.members[0].accept_incomplete,true)
  assert.deepEqual(h.state.saved.map(r=>r.id),['saved-a','saved-b'])
})
test('unknown retry outcome prevents editing a previously rejected member', async () => {
  let count=0
  const h=harness(options=>{
    if(options.method==='POST') {
      if(++count===1)return {data:{results:[{member_id:'a',status:'failed',code:'nutrition_incomplete'}]}}
      throw Object.assign(new Error('timeout'),{code:'NETWORK_ERROR'})
    }
  })
  await h.client.open();await h.client.save([{memberId:'a',meal}],false)
  await h.client.save([{memberId:'a',meal}],false)
  const pending=structuredClone(h.state.pending)
  assert.equal(h.state.canEditFailed,false);h.client.editFailed()
  assert.deepEqual(h.state.pending,pending)
})
test('unknown correction retry freezes body, version and idempotency key', async () => {
  let count = 0
  const h = harness(options => {
    if (options.method === 'PATCH') {
      if (++count === 1) throw Object.assign(new Error('timeout'),{code:'NETWORK_ERROR'})
      return {data:{id:'meal',source_version:3,snapshot:{meal:structuredClone(meal),nutrition:{totals:{energy_kcal:'100'}}}}}
    }
  })
  await h.client.open(); h.state.detail={id:'meal',source_version:2,snapshot:{meal}}
  await h.client.correct(meal,'first',true); assert.ok(h.state.pending)
  await h.client.correct({...meal,items:[]},'changed',false)
  const writes = h.calls.filter(c=>c.method==='PATCH')
  assert.deepEqual(writes[0],writes[1]);assert.equal(writes[0].headers['If-Match'],'"2"')
  assert.equal(h.state.detail.source_version,3);assert.equal(h.state.pending,null)
})
test('partial family success only retries failed members with unchanged keys',async()=>{
  let count=0
  const h=harness(options=>{if(options.method==='POST')return {data:{results:++count===1?[
    {member_id:'a',status:'saved',id:'saved-a'}, {member_id:'b',status:'failed',code:'not_found'}
  ]:[{member_id:'b',status:'saved',id:'saved-b'}]}}})
  await h.client.open();await h.client.save([{memberId:'a',meal},{memberId:'b',meal}],true)
  assert.deepEqual(h.state.saved.map(x=>x.id),['saved-a']);assert.equal(h.state.pending.data.members.length,1)
  await h.client.save([{memberId:'a',meal:{items:[]}}],false)
  const writes=h.calls.filter(c=>c.method==='POST')
  assert.equal(writes[0].data.group_id,writes[1].data.group_id)
  assert.deepEqual(writes[1].data.members,[writes[0].data.members[1]])
  assert.deepEqual(h.state.saved.map(x=>x.id),['saved-a','saved-b']);assert.equal(h.state.pending,null)
})
test('revision conflict blocks overwriting until current detail is reloaded',async()=>{
  const h=harness(options=>{if(options.method==='PATCH')throw Object.assign(new Error('conflict'),{code:409})})
  await h.client.open();h.state.detail={id:'meal',source_version:1};await h.client.correct(meal,'reason',true)
  assert.equal(h.state.conflict,true);assert.equal(h.state.pending,null)
  const n=h.calls.length;await h.client.correct(meal,'again',true);assert.equal(h.calls.length,n)
})
test('late private response after account change clears every journal field',async()=>{
  let release
  const h=harness(options=>options.path.endsWith('/detail')?new Promise(r=>release=r):null)
  await h.client.open();const pending=h.client.detail({id:'private'});h.switchAccount();release({data:{id:'private',snapshot:{meal}}});await pending
  assert.equal(h.state.detail,null);assert.deepEqual(h.state.members,[]);assert.equal(h.state.busy,false)
})
