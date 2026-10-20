import test from 'node:test'
import assert from 'node:assert/strict'
import { createEntryResolver } from '../src/services/entry-routing.js'

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
