import test from 'node:test'
import assert from 'node:assert/strict'
import { createEntryResolver, createEntryCoordinator } from '../src/services/entry-routing.js'
import { createSharedSessionRestore } from '../src/services/session-restore.js'

function setup(families, householdId=null, onboarded=false) {
  let account={accountId:'17',token:'synthetic-token',families,householdId}
  const calls=[]
  const resolve=createEntryResolver({session:()=>account,auth:{
    restore:async()=>{calls.push('restore');return account},
    selectFamily:async id=>{calls.push('select:'+id);account={...account,householdId:id};return account},
  },readProfile:async()=>{calls.push('profile');return {householdId:account.householdId,onboarded}}})
  return {resolve,calls,read:()=>account,set:value=>{account=value}}
}
test('first account with no families enters onboarding without inventing a family or reading demo state',async()=>{
  const h=setup([])
  assert.equal(await h.resolve(),'/pages/onboarding/index')
  assert.deepEqual(h.calls,['restore'])
  assert.equal(h.read().householdId,null)
})
test('a single authorized family is selected and cloud completion decides onboarding or home',async()=>{
  for(const onboarded of [false,true]){
    const h=setup([{id:'family-1'}],null,onboarded)
    assert.equal(await h.resolve(),onboarded?'/pages/chat/index':'/pages/onboarding/index')
    assert.deepEqual(h.calls,['restore','select:family-1','profile'])
  }
})
test('multiple families require selection and never silently choose the first',async()=>{
  const h=setup([{id:'family-1'},{id:'family-2'}])
  assert.equal(await h.resolve(),'/pages/family-select/index')
  assert.deepEqual(h.calls,['restore'])
})
test('a restored authorized selection is preserved, while a removed selection is not reused',async()=>{
  const families=[{id:'family-1'},{id:'family-2'}]
  const h=setup(families,'family-2',true)
  assert.equal(await h.resolve(),'/pages/chat/index');assert.deepEqual(h.calls,['restore','profile'])
  const removed=setup(families,'removed-family',true)
  assert.equal(await removed.resolve(),'/pages/family-select/index')
})
test('an unavailable profile never falls back to a local completed flag',async()=>{
  let account={accountId:'17',token:'token',householdId:'family-1',families:[{id:'family-1'}]}
  const resolve=createEntryResolver({auth:{restore:async()=>account},session:()=>account,readProfile:async()=>{throw Object.assign(new Error('network down'),{code:'NETWORK_ERROR'})}})
  await assert.rejects(resolve(),/network down/)
})
test('logout or account switching during a profile read prevents late routing into private home',async()=>{
  let account={accountId:'17',token:'token',householdId:'family-1',families:[{id:'family-1'}]},finish
  const resolve=createEntryResolver({auth:{restore:async()=>account},session:()=>account,readProfile:()=>new Promise(r=>{finish=r})})
  const pending=resolve();await Promise.resolve();account=null
  finish({householdId:'family-1',onboarded:true})
  await assert.rejects(pending,e=>e.code==='SESSION_CHANGED')
})

test('a freshly restored confirmed WeChat family enters chat without another profile or configuration read',async()=>{
  const account={accountId:'17',token:'synthetic',householdId:'family-1',families:[{id:'family-1',onboardingRequired:false}]}
  let reads=0,restores=0
  const resolve=createEntryResolver({session:()=>account,auth:{restore:async()=>{restores++;return account}},readProfile:async()=>{reads++;throw Error('unexpected profile')}})
  assert.equal(await resolve(),'/pages/chat/index')
  assert.equal(restores,1);assert.equal(reads,0)
})

test('ready-family shortcut still gives pending invitation and profile preparation priority',async()=>{
  const account={accountId:'17',token:'synthetic',householdId:'family-1',families:[{id:'family-1',onboardingRequired:false}]}
  for(const [invitation,preparation,expected] of [['family_pending',false,'/pages/invite/index?token=family_pending'],['',true,'/pages/onboarding/preparing']]){
    const resolve=createEntryResolver({session:()=>account,auth:{restore:async()=>account},readProfile:()=>assert.fail('no duplicate profile read'),invitation:()=>invitation,pendingPreparation:()=>preparation})
    assert.equal(await resolve(),expected)
  }
})

test('unconfirmed and unknown family status still reads the genuine profile and cannot assume completion',async()=>{
  for(const flag of [true,undefined])for(const complete of [true,false]){
    const account={accountId:'17',token:'synthetic',householdId:'family-1',families:[{id:'family-1',onboardingRequired:flag}]}
    let reads=0
    const resolve=createEntryResolver({session:()=>account,auth:{restore:async()=>account},readProfile:async()=>{reads++;return {householdId:'family-1',completeProfile:complete}}})
    assert.equal(await resolve(),complete?'/pages/chat/index':'/pages/onboarding/index');assert.equal(reads,1)
  }
})

test('an invitation arriving while the profile is reading takes priority over the older chat result',async()=>{
  const account={accountId:'17',token:'synthetic',householdId:'family-1',families:[{id:'family-1'}]}
  let invitation='',finish
  const resolve=createEntryResolver({session:()=>account,auth:{restore:async()=>account},invitation:()=>invitation,readProfile:()=>new Promise(done=>finish=done)})
  const loading=resolve();await Promise.resolve();invitation='family_arrived'
  finish({householdId:'family-1',completeProfile:true})
  assert.equal(await loading,'/pages/invite/index?token=family_arrived')
})

function coordinator() {
  let account={accountId:'17',token:'synthetic',authSource:'wechat',householdId:'family-1',clientRevision:'revision-1',families:[{id:'family-1',onboardingRequired:false}]}
  let invitation='',preparation=false,profile=true,time=10000,calls=0,implementation=async()=>'/pages/chat/index'
  const resolve=createEntryCoordinator({session:()=>account,invitation:()=>invitation,pendingPreparation:()=>preparation,profileState:()=>profile,now:()=>time,resolve:()=>{calls++;return implementation()}})
  return {resolve,get calls(){return calls},get account(){return account},set account(value){account=value},set invitation(value){invitation=value},set preparation(value){preparation=value},set profile(value){profile=value},set time(value){time=value},set implementation(value){implementation=value}}
}

test('one verified entry decision is reused for five seconds; a foreground fresh check still validates immediately',async()=>{
  const h=coordinator()
  assert.equal(await h.resolve(),'/pages/chat/index')
  h.time=14999;await h.resolve();assert.equal(h.calls,1)
  await h.resolve({fresh:true});assert.equal(h.calls,2)
  h.time=19999;await h.resolve();assert.equal(h.calls,3)
})

test('concurrent entry checks share only the same session validation and do not share persistent health data',async()=>{
  const h=coordinator();let finish
  h.implementation=()=>new Promise(done=>finish=done)
  const first=h.resolve(),second=h.resolve({fresh:true})
  assert.equal(first,second);await Promise.resolve();assert.equal(h.calls,1)
  finish('/pages/chat/index');await first
  h.account={...h.account,accountId:'another'}
  const third=h.resolve();await Promise.resolve();assert.equal(h.calls,2)
  finish('/pages/onboarding/index');await third
})

test('an invitation arriving during in-flight validation is handled by that resolver instead of competing generations',async()=>{
  const h=coordinator();let finish
  h.implementation=()=>new Promise(done=>finish=done)
  const first=h.resolve();await Promise.resolve();h.invitation='arrived-during-validation'
  const second=h.resolve({fresh:true});assert.equal(first,second);assert.equal(h.calls,1)
  finish('/pages/invite/index?token=arrived-during-validation')
  assert.equal(await second,'/pages/invite/index?token=arrived-during-validation')
})

for(const [name,change] of [
  ['account',h=>{h.account={...h.account,accountId:'18'}}],
  ['token',h=>{h.account={...h.account,token:'new-token'}}],
  ['family',h=>{h.account={...h.account,householdId:'other-family'}}],
  ['auth source',h=>{h.account={...h.account,authSource:'business'}}],
  ['session revision',h=>{h.account={...h.account,clientRevision:'new-revision'}}],
  ['family permission',h=>{h.account={...h.account,families:[]}}],
  ['invitation',h=>{h.invitation='pending-invitation'}],
  ['preparation',h=>{h.preparation=true}],
  ['known incomplete profile',h=>{h.profile=false}],
  ['logout',h=>{h.account=null}],
])test(`entry reuse is invalidated by ${name}`,async()=>{
  const h=coordinator();await h.resolve();change(h);await h.resolve();assert.equal(h.calls,2)
})

test('an expired token and a clock moving backwards cannot reuse an old entry validation',async()=>{
  const h=coordinator();h.account={...h.account,expiresAt:10.1}
  await h.resolve();h.time=10100;await h.resolve();assert.equal(h.calls,2)
  const backwards=coordinator();await backwards.resolve();backwards.time=9999;await backwards.resolve();assert.equal(backwards.calls,2)
})

test('a failed fresh validation invalidates the earlier successful entry, including transient network errors',async()=>{
  for(const code of [401,403,'NETWORK_ERROR']){
    const h=coordinator();await h.resolve();h.implementation=async()=>{throw Object.assign(Error('validation failed'),{code})}
    await assert.rejects(h.resolve({fresh:true}),error=>error.code===code)
    await assert.rejects(h.resolve(),error=>error.code===code);assert.equal(h.calls,3)
  }
})

test('a late older result cannot seed the new account entry cache',async()=>{
  const h=coordinator();let finish
  h.implementation=()=>new Promise(done=>finish=done)
  const first=h.resolve();await Promise.resolve()
  h.account={...h.account,accountId:'18',clientRevision:'new'}
  finish('/pages/chat/index');await first
  h.implementation=async()=>'/pages/onboarding/index'
  assert.equal(await h.resolve(),'/pages/onboarding/index');assert.equal(h.calls,2)
})

test('session restoration shares in-flight requests without reusing a completed or failed authorization result',async()=>{
  let account={accountId:'17',token:'synthetic',householdId:'family-1',authSource:'wechat',clientRevision:'one'},calls=0,finish
  const restore=createSharedSessionRestore(()=>{calls++;return new Promise(done=>finish=done)},()=>account)
  const first=restore(),second=restore();assert.equal(first,second)
  await Promise.resolve();assert.equal(calls,1);finish(account);await first
  const third=restore();await Promise.resolve();assert.equal(calls,2);finish(account);await third
  account={...account,clientRevision:'two'}
  const fourth=restore();await Promise.resolve();assert.equal(calls,3);finish(account);await fourth
  let failingCalls=0
  const failing=createSharedSessionRestore(async()=>{failingCalls++;throw Error('network')},()=>account)
  await assert.rejects(failing());await assert.rejects(failing());assert.equal(failingCalls,2)
})

test('a session changed before deferred restoration starts cannot validate the old caller as the new account',async()=>{
  let account={accountId:'17',token:'synthetic',clientRevision:'one'},calls=0
  const restore=createSharedSessionRestore(async()=>{calls++;return account},()=>account)
  const old=restore();account={accountId:'18',token:'new',clientRevision:'two'}
  await assert.rejects(old,error=>error.code==='SESSION_CHANGED');assert.equal(calls,0)
  assert.equal((await restore()).accountId,'18');assert.equal(calls,1)
})


test('unconfirmed users can repair or confirm the exact family profile without bypassing AI onboarding',async()=>{
  const { protectedDestination } = await import('../src/services/navigation.js')
  const entry='/pages/onboarding/index'
  for(const path of ['/pages/profile/index','/pages/profile/member?id=mother','/pages/family-shared/index?memberId=mother'])assert.equal(protectedDestination(path,entry),path)
  assert.equal(protectedDestination('/pages/chat/agent?memberId=mother',entry),entry)
  assert.equal(protectedDestination('/pages/profile/member?id=mother','/pages/index/index'),'/pages/index/index')
})
