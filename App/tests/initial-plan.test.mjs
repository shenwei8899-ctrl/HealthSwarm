import test from 'node:test'
import assert from 'node:assert/strict'
import { createInitialPlanClient, initialPlanState } from '../src/services/health-initial-plan-client.js'

const member = '11111111-1111-4111-8111-111111111111', entry = '22222222-2222-4222-8222-222222222222'
const run = '33333333-3333-4333-8333-333333333333', thread = '44444444-4444-4444-8444-444444444444'
const date = '2026-10-27', selection = { kind:'single', plan_date:date, rule_code:'synthetic', rule_version:1,
  profile_versions:{[member]:1}, meals:['breakfast','lunch','dinner'].map(meal_type=>({meal_type,participant_ids:[member]})) }
const receipt = {scope:'initial_single_plan',member_id:member,preview_id:'synthetic-preview',status:'ready',plan_snapshot:{plan_date:date,meals:[]}}
function fixture() {
  const state = initialPlanState(), calls = [], store = new Map()
  let rev = 1, denial = false, timeout = false, consent = true, version = 1, saveCount = 0, pendingSave = null, expireAt = ''
  const storage = {getStorageSync:k=>store.get(k),setStorageSync:(k,v)=>store.set(k,structuredClone(v))}
  const send = async req => {
    calls.push(structuredClone(req))
    if (expireAt && req.path.includes(expireAt)) { rev++; throw Object.assign(new Error('expired'),{code:401}) }
    if (req.path.endsWith('/initial-meal-plans')) {
      saveCount++
      if (pendingSave) await pendingSave
      if (timeout) {timeout=false;throw Object.assign(new Error('timeout'),{code:'NETWORK_ERROR'})}
      return {data:{plan_id:'saved',member_id:member,plan_date:date,version:1,applied_version:1}}
    }
    if (denial) throw Object.assign(new Error('revoked'),{code:403})
    if(req.path.includes('/initial-meal-plan-context')) return {data:{member_id:member,plan_date:date,selection:{...selection,rule_version:version}}}
    if(req.path.endsWith('/members')) return {data:[{id:member}]}
    if(req.path.endsWith('/readiness')) return {data:{capabilities:{member_id:member},entries:[{entry_type:'initial_meal_preview',status:consent?'needs_input':'unavailable',reason_code:consent?'selection_required':'consent_required'}]}}
    if(req.path.endsWith('/configuration'))return {data:{policy_version:'synthetic',meal_plan:{available:true,processor:'synthetic-provider'}}}
    if(req.path.endsWith('/processing-consents')){consent=true;return {data:{accepted:true}}}
    if(req.path.endsWith('/task-entries'))return {data:{member_id:member,task_type:'initial_meal_preview',client_request_id:entry,entry_status:'ready',thread_id:thread,agent_slug:'health-meal-planner',request_submit_url:'/api/agent/runs'}}
    if(req.path==='/api/agent/runs')return {data:{request_id:run,thread_id:thread}}
    if(req.path.endsWith('/tasks/'+run))return {data:{request_id:run,member_id:member,task_type:'initial_meal_preview',thread_id:thread,agent_slug:'health-meal-planner',request_status:'dispatched',execution_status:'completed',result:{result_type:'meal_plan_preview',validation:'current_business_sources',data:receipt}}}
    throw new Error(req.path)
  }
  let index = 0
  const make = () => createInitialPlanClient({state,send,storage,revision:()=>rev,newId:()=>[entry,run,'55555555-5555-4555-8555-555555555555'][index++%3],flowOptions:{session:()=>({accountId:String(rev),token:'synthetic'}),subscribe:()=>()=>{}}})
  const client=make()
  return {state,client,calls,store,make,revoke:()=>{denial=true},timeout:()=>{timeout=true},noConsent:()=>{consent=false},changeSource:()=>{version++},switch:()=>{rev++},expireAt:path=>{expireAt=path},delaySave:p=>{pendingSave=p},saveCount:()=>saveCount}
}

test('fixed selection enters planner, generation never saves until explicit confirmation',async()=>{
  const h=fixture();await h.client.open(member,date);await h.client.generate()
  assert.deepEqual(h.calls.find(x=>x.path.endsWith('/task-entries')).data.selection,selection)
  assert.equal(h.client.preview().preview_id,receipt.preview_id);assert.equal(h.saveCount(),0)
  await h.client.confirmSave();assert.equal(h.state.saved.plan_id,'saved');assert.equal(h.saveCount(),1)
  await h.client.confirmSave();assert.equal(h.saveCount(),1)
})
test('meal-plan consent is explicit and distinct from consultation',async()=>{
  const h=fixture();h.noConsent();await h.client.open(member,date);await h.client.generate()
  assert.equal(h.calls.some(x=>x.path==='/api/agent/runs'),false)
  assert.equal(h.state.task.consentOption.purpose,'meal_plan')
  await h.client.flow.acceptConsent(true);await h.client.generate()
  assert.equal(h.calls.find(x=>x.path.endsWith('/processing-consents')).data.purpose,'meal_plan')
  assert.ok(h.client.preview())
})
test('save timeout survives page reentry and reuses the same write key',async()=>{
  const h=fixture();await h.client.open(member,date);await h.client.generate();h.timeout();await h.client.confirmSave()
  assert.ok(h.state.pending);h.client.hide();await h.client.open(member,date)
  assert.ok(h.client.preview());await h.client.confirmSave()
  const writes=h.calls.filter(x=>x.path.endsWith('/initial-meal-plans'))
  assert.equal(writes.length,2);assert.deepEqual(writes[0],writes[1]);assert.equal(h.state.pending,null)
})
test('reentry rereads existing task and does not generate another run',async()=>{
  const h=fixture();await h.client.open(member,date);await h.client.generate();h.client.hide();await h.client.open(member,date)
  assert.ok(h.client.preview());assert.equal(h.calls.filter(x=>x.path==='/api/agent/runs').length,1)
})
test('revocation before confirmation clears result and creates no plan',async()=>{
  const h=fixture();await h.client.open(member,date);await h.client.generate();h.revoke();await h.client.confirmSave()
  assert.equal(h.client.preview(),null);assert.equal(h.saveCount(),0);assert.equal(h.state.saved,null)
})
test('late save response after account change is not displayed',async()=>{
  const h=fixture();await h.client.open(member,date);await h.client.generate()
  let release;h.delaySave(new Promise(r=>{release=r}));const saving=h.client.confirmSave()
  while(!h.saveCount()) await new Promise(r=>setTimeout(r,1))
  h.switch();h.client.hide();release();await saving;assert.equal(h.state.saved,null);assert.equal(h.state.memberId,'')
})
test('new source version does not revive a previous task preview',async()=>{
  const h=fixture();await h.client.open(member,date);await h.client.generate();h.changeSource();await h.client.open(member,date)
  assert.equal(h.client.preview(),null);assert.equal(h.state.task.requestId,'')
})
test('401 during save clears private preview without requiring page hide',async()=>{
  const h=fixture();await h.client.open(member,date);await h.client.generate();h.expireAt('/initial-meal-plans');await h.client.confirmSave()
  assert.equal(h.client.preview(),null);assert.equal(h.state.saving,false);assert.equal(h.state.pending,null);assert.match(h.state.error,/登录/)
})
test('401 during context read clears the loading state without page hide',async()=>{
  const h=fixture();h.expireAt('/initial-meal-plan-context');await h.client.open(member,date)
  assert.equal(h.state.loading,false);assert.equal(h.state.memberId,'');assert.match(h.state.error,/登录/)
})
