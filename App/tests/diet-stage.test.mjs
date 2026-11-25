import test from 'node:test'
import assert from 'node:assert/strict'
import { createDietStageClient, dietStageState, currentStageWeek, stageEntryUrl } from '../src/services/diet-stage-client.js'

function fixture(send) {
  const state = dietStageState(), data = new Map()
  let rev = 1, owner = 'a', id = 0
  const storage = { getStorageSync: k => data.get(k), setStorageSync: (k,v) => data.set(k,v) }
  const client = createDietStageClient({ state, send, storage, revision: () => rev, context: () => owner, newId: () => 'request-'+(++id) })
  return { state, client, storage, switch: () => { rev++; owner = 'b' } }
}
const value = { stage: { id:'s', version:1 }, profile_version:3, today:'2026-11-25', weeks:[] }

test('opening stage reads only and never generates a plan or a model request', async () => {
  const calls=[]
  const f=fixture(async request => { calls.push(request); return { data:value } })
  await f.client.open('f','m')
  assert.equal(calls.length,1); assert.equal(calls[0].method,undefined)
  assert.equal(f.state.value.profile_version,3)
})
test('late read after an account change cannot reveal old member data', async () => {
  let resolve
  const f=fixture(() => new Promise(r => {resolve=r}))
  const opening=f.client.open('f','m'); f.switch(); resolve({data:value}); await opening
  assert.equal(f.state.value,null); assert.equal(f.state.busy,false)
})
test('unknown write retains frozen request and explicit retry reuses original id and count', async () => {
  const calls=[]; let failure=true
  const f=fixture(async request => {
    calls.push(JSON.parse(JSON.stringify(request)))
    if(request.method && failure) throw Object.assign(new Error('timeout'), {code:'NETWORK_ERROR'})
    return {data:value}
  })
  await f.client.open('f','m')
  await f.client.saveWeek({id:'w',version:2},[{id:'a',title:'准备早餐',target:3,count:1}])
  assert.ok(f.state.pending); const frozen=JSON.parse(JSON.stringify(f.state.pending))
  failure=false; await f.client.retry()
  assert.deepEqual(calls.filter(r=>r.method)[1], frozen)
  assert.equal(f.state.pending,null)
})
test('version conflict clears pending and does not automatically overwrite current list', async () => {
  const f=fixture(async request => {
    if(request.method) throw Object.assign(new Error('版本变化'), {code:409})
    return {data:value}
  })
  await f.client.open('f','m'); await f.client.saveWeek({id:'w',version:2},[])
  assert.equal(f.state.pending,null); assert.equal(f.state.error,'版本变化')
})
test('a second mutation cannot replace an uncertain original request', async () => {
  const f=fixture(async request => {
    if(request.method) throw Object.assign(new Error('timeout'),{code:'NETWORK_ERROR'})
    return {data:value}
  })
  await f.client.open('f','m'); await f.client.generate('review')
  const pending=JSON.stringify(f.state.pending)
  await f.client.generate('draft',{goals:['new']})
  assert.equal(JSON.stringify(f.state.pending),pending)
})
test('authorization failure clears saved stage and private summary', async () => {
  let deny=false
  const f=fixture(async () => {if(deny)throw Object.assign(new Error('无权限'),{code:403});return {data:value}})
  await f.client.open('f','m'); f.state.job={result:{summary:'private'}}; deny=true
  await f.client.reload()
  assert.equal(f.state.value,null); assert.equal(f.state.job,null)
})
test('continuous week boundaries exclude the stop date and member navigation carries both identities', () => {
  const v={today:'2026-12-02',weeks:[{id:'old',starts_on:'2026-11-25',ends_on:'2026-12-02'},
    {id:'new',starts_on:'2026-12-02',ends_on:'2026-12-09'}]}
  assert.equal(currentStageWeek(v).id,'new')
  assert.equal(stageEntryUrl('f','m'),'/pages/health/diet-stage?familyId=f&memberId=m')
})
test('switching to a historical phase cancels an older pending poll', async t => {
  t.mock.timers.enable({apis:['setTimeout']})
  const calls=[]
  const f=fixture(async request => {calls.push(request.path); return {data:value}})
  await f.client.open('f','m'); f.state.job={id:'old',status:'pending'}
  f.client.poll('old')
  await f.client.history('historic')
  t.mock.timers.tick(5000)
  await new Promise(resolve=>setImmediate(resolve))
  assert.equal(calls.filter(path=>path.includes('/generations/')).length,0)
  assert.equal(f.state.job,null)
})
test('an in-flight polling response cannot restart polling after page hide', async t => {
  t.mock.timers.enable({apis:['setTimeout']})
  let resolveJob, jobs=0
  const f=fixture(async request => {
    if(request.path.includes('/generations/')) {jobs++;return new Promise(resolve=>{resolveJob=resolve})}
    return {data:value}
  })
  await f.client.open('f','m'); f.state.job={id:'old',status:'pending'}
  f.client.poll('old'); t.mock.timers.tick(2200)
  assert.equal(jobs,1)
  f.client.stop()
  resolveJob({data:{id:'old',status:'pending'}})
  await new Promise(resolve=>setImmediate(resolve))
  t.mock.timers.tick(10000)
  await new Promise(resolve=>setImmediate(resolve))
  assert.equal(jobs,1)
})
