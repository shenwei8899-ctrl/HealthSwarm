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

for (const rejection of [{code:410,businessCode:'profile_source_changed'},{code:'SERVICE_NOTICE_DECLINED',noticeRejected:true},{code:503,businessCode:'stage_model_unavailable'}]) {
 test('explicit rejection clears only the rejected submission: '+rejection.code,async()=>{
  const f=fixture(async r=>{if(r.method)throw Object.assign(new Error('明确拒绝'),rejection);return {data:value}})
  await f.client.open('f','m');await f.client.generate('draft',{note:'保留这段输入'})
  assert.equal(f.state.pending,null);assert.deepEqual(f.state.value,value)
  await f.client.open('f','m');assert.equal(f.state.pending,null)
 })
}
test('read conflicts cannot erase a different uncertain write',async()=>{
 let conflict=false
 const f=fixture(async r=>{if(r.method)throw Object.assign(new Error('timeout'),{code:'NETWORK_ERROR'});if(conflict)throw Object.assign(new Error('读取冲突'),{code:409});return {data:value}})
 await f.client.open('f','m');await f.client.generate('draft');const frozen=JSON.stringify(f.state.pending)
 conflict=true;await f.client.reload();assert.equal(JSON.stringify(f.state.pending),frozen)
})
test('busy requests cannot create an unsent intent',async()=>{
 let resolve;const calls=[]
 const f=fixture(r=>{calls.push(r);return new Promise(r=>resolve=r)})
 const reading=f.client.open('f','m');await f.client.generate('draft');assert.equal(f.state.pending,null)
 resolve({data:value});await reading;assert.equal(calls.length,1)
})
test('a saved write followed by failed refresh is retried as a read only',async()=>{
 let failed=false;const calls=[]
 const f=fixture(async r=>{calls.push(r);if(r.method){failed=true;return {data:{saved:true}}}if(failed)throw Object.assign(new Error('读取超时'),{code:'NETWORK_ERROR'});return {data:value}})
 await f.client.open('f','m');const saved=await f.client.saveWeek({id:'w',version:1},[])
 assert.equal(saved.saved,true);assert.equal(f.state.pending,null);assert.ok(f.state.refreshRequired);assert.match(f.state.notice,/已保存/)
 failed=false;await f.client.retry();assert.equal(calls.filter(r=>r.method).length,1);assert.equal(f.state.refreshRequired,false)
})
test('a failed generation cannot return the previous task as a new result',async()=>{
 const f=fixture(async r=>{if(r.method)throw Object.assign(new Error('失败'),{code:409});return {data:value}})
 await f.client.open('f','m');f.state.job={id:'old',status:'ready'}
 assert.equal(await f.client.generate('draft'),undefined);assert.equal(f.state.error,'失败')
})
test('end dates display the last included day across month and year boundaries',async()=>{
 const {stageWeekEnd}=await import('../src/services/diet-stage-client.js')
 assert.equal(stageWeekEnd('2026-12-09'),'12.08');assert.equal(stageWeekEnd('2027-01-01'),'12.31')
})

test('a failed task read can recover the same ready or pending task without a new POST',async()=>{
 let outage=true;let writes=0
 const f=fixture(async r=>{if(r.method){writes++;return {data:{id:'same-task',kind:'draft',status:'pending'}}}if(r.path.includes('/generations/')){if(outage)throw Object.assign(new Error('读取失败'),{code:'NETWORK_ERROR'});return {data:{id:'same-task',kind:'draft',status:'ready',result:{goals:['规律三餐']}}}}return {data:value}})
 await f.client.open('f','m');await f.client.generate('draft');await f.client.job('same-task')
 assert.equal(f.state.recovery,'job');assert.equal(f.state.pending,null)
 outage=false;const recovered=await f.client.retry();assert.equal(recovered.id,'same-task');assert.equal(recovered.status,'ready');assert.equal(f.state.recovery,'');assert.equal(writes,1)
})

test('unread task recovery blocks a new generation until original job is read',async()=>{
 let writes=0
 const f=fixture(async r=>{if(r.method){writes++;return {data:{id:'task',kind:'week',status:'pending'}}}if(r.path.includes('/generations/'))throw Object.assign(new Error('读取失败'),{code:'NETWORK_ERROR'});return {data:value}})
 await f.client.open('f','m');await f.client.generate('week');await f.client.job('task');await f.client.generate('review');assert.equal(writes,1);assert.equal(f.state.recovery,'job')
})
