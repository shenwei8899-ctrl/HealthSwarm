import test from 'node:test'
import assert from 'node:assert/strict'
import { archiveState, createFamilyArchivesClient } from '../src/services/family-archives-client.js'
import { profileDraft, profileChanges, measurementTimestamp } from '../src/services/family-archive-fields.js'
import { createBusinessAuthClient } from '../src/services/business-auth-client.js'
const member = { id:'unclaimed', is_active:true, is_self:true, claimed:false, profile_access:'family_shared', version:3, relationship_version:2, profile:{height_cm:165,medical_history:'synthetic'}, allowed_fields:['height_cm','medical_history'], editable_fields:['height_cm','medical_history'], authorization:{expires_at:'2020-01-01',fields:[]} }
function harness(override, storage) {
  let revision=1, stored={token:'synthetic',householdId:'f'}
  const state=archiveState(), calls=[]
  const send=async options=>{calls.push(options);if(override){const value=await override(options);if(value)return value}return {data:options.path==='/api/family'?[{id:'f',name:'shared'}]:options.path==='/api/family/f'?{id:'f',members:[structuredClone(member)]}:{items:[],total:0}}}
  const client=createFamilyArchivesClient({send,state,storage,session:{read:()=>stored,revision:()=>revision}})
  return {client,state,calls,switchAccount(){revision++;stored={token:'other',householdId:'other'}}}
}
test('unclaimed shared member stays readable with expired independent grant and writes owning versions',async()=>{
  const h=harness();await h.client.refresh();assert.equal(h.state.member.id,'unclaimed');assert.equal(h.state.member.profile.medical_history,'synthetic')
  await h.client.saveProfile({height_cm:170});await h.client.saveIdentity('family','parent')
  assert.deepEqual(h.calls.find(c=>c.method==='PUT'&&!c.path.endsWith('relationship')).data,{expected_version:3,profile:{height_cm:170}})
  assert.equal(h.calls.find(c=>c.path.endsWith('/relationship')).data.expected_version,2)
  assert.ok(h.calls.every(c=>c.path.startsWith('/api/family')))
})
test('conflict and unknown writes block resubmission until reread',async()=>{
  for(const code of [409,'NETWORK_ERROR',503]){
    const h=harness(options=>{if(options.method)throw Object.assign(new Error('failed'),{code})});await h.client.refresh();await h.client.saveProfile({height_cm:170});assert.equal(h.state.blocked,true)
    const count=h.calls.length;await h.client.saveProfile({height_cm:175});assert.equal(h.calls.length,count)
    await h.client.refresh();assert.equal(h.state.blocked,false)
  }
})
test('lost access and late responses clear all private selections',async()=>{
  for(const code of [401,403,404]){
    const h=harness(options=>{if(options.method)throw Object.assign(new Error('denied'),{code})});await h.client.refresh();await h.client.saveProfile({height_cm:170});assert.equal(h.state.member,null);assert.equal(h.state.family,null);assert.deepEqual(h.state.history,[])
  }
  let release;const h=harness(options=>options.path==='/api/family/f'?new Promise(r=>release=r):null)
  const pending=h.client.refresh();await new Promise(r=>setImmediate(r));h.switchAccount();release({data:{id:'f',members:[member]}});await pending
  assert.equal(h.state.member,null);assert.deepEqual(h.state.families,[])
})
test('failed reconciliation never unlocks an unknown write',async()=>{
  let failRead=false
  const h=harness(options=>{
    if(options.method)throw Object.assign(new Error('timeout'),{code:'NETWORK_ERROR'})
    if(failRead&&options.path.includes('/measurements'))throw Object.assign(new Error('unavailable'),{code:503})
  })
  await h.client.refresh();await h.client.saveProfile({height_cm:170});failRead=true
  await h.client.refresh();assert.equal(h.state.blocked,true)
  const before=h.calls.length;await h.client.saveProfile({height_cm:175});assert.equal(h.calls.length,before)
  failRead=false;await h.client.refresh();assert.equal(h.state.blocked,false)
})
test('hide cancels stale writes and failed loads never invent member fallback',async()=>{
  let release;const h=harness(options=>options.method?new Promise(r=>release=r):null);await h.client.refresh();const pending=h.client.saveProfile({height_cm:170});h.client.discard();release({data:{}});await pending;assert.equal(h.state.member,null)
  await h.client.refresh('foreign');assert.equal(h.state.family,null);assert.equal(h.calls.some(c=>c.path==='/api/family/foreign'),false)
})
test('profile changes preserve untouched facts and never convert unknown numbers to zero',()=>{
  const draft=profileDraft(member.profile);assert.deepEqual(profileChanges(draft,member),{});draft.height_cm='';assert.deepEqual(profileChanges(draft,member),{height_cm:null})
  draft.height_cm='NaN';assert.throws(()=>profileChanges(draft,member));draft.height_cm=165;draft.goal='unauthorized';assert.throws(()=>profileChanges(draft,member))
})
test('measurement dates reject impossible calendar values instead of normalizing them',()=>{
  for(const value of ['2026-02-31T10:00','2026-02-29T10:00','2026-04-31T10:00','2026-10-16T24:00','invalid'])assert.throws(()=>measurementTimestamp(value))
  assert.equal(measurementTimestamp('2024-02-29T10:00'),new Date('2024-02-29T10:00').toISOString())
})

test('unknown measurement creation survives rereading and replays the exact ID and frozen body',async()=>{
  const values=new Map(),storage={getStorageSync:key=>values.get(key),setStorageSync:(key,value)=>values.set(key,structuredClone(value))}
  let attempts=0
  const handler=options=>{if(options.method==='POST'&&options.path.endsWith('/measurements')&&++attempts===1)throw Object.assign(new Error('lost response'),{code:'NETWORK_ERROR'})}
  const data={id:'stable-measurement',kind:'blood_glucose',values:{glucose:5},measured_at:'2026-10-22T08:00:00+08:00',source:'manual'}
  const first=harness(handler,storage);await first.client.refresh();await first.client.saveMeasurement(data)
  assert.ok(first.state.pendingMeasurement);assert.equal(first.state.blocked,true)
  const next=harness(handler,storage);await next.client.refresh();await next.client.retryMeasurement()
  assert.deepEqual(first.calls.find(c=>c.method==='POST').data,next.calls.find(c=>c.method==='POST').data)
  assert.equal(next.state.pendingMeasurement,null)
  assert.equal([...values.values()].some(Boolean),false)
})
test('business login uses real auth contracts and stores no password or commerce identity',async()=>{
  let stored=null,revision=0;const calls=[]
  const client=createBusinessAuthClient({session:{read:()=>stored,save:v=>{stored=v;revision++},clear:()=>{stored=null;revision++},revision:()=>revision},send:async o=>{calls.push(o);return{data:o.path==='/api/auth/token'?{user_id:17,access_token:'synthetic'}:o.path==='/api/auth/me'?{id:17,username:'synthetic'}:[{id:'f',name:'family',is_owner:false}]}}})
  await client.login('synthetic','private&password');assert.equal(stored.authSource,'business');assert.equal(stored.householdId,null);assert.equal(stored.password,undefined);assert.match(calls[0].data,/private%26password/)
  await client.selectFamily('f');assert.equal(stored.householdId,'f')
  await assert.rejects(client.selectFamily('foreign'));assert.equal(stored.householdId,'f')
})
