import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'

function cacheHarness() {
  let scope='account-a:family-a:rev1', invite='', preparing=false, now=1000, reads=0, route='/pages/chat/index'
  let session={accountId:'a',householdId:'family-a',token:'synthetic'}
  const source=readFileSync(new URL('../src/services/app-entry.js',import.meta.url),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
  const deps={
    scopedStorage:{getStorageSync:()=>preparing},storageContext:()=>scope,
    createEntryResolver:()=>async()=>{reads++;return route},wechatAuth:{},loadCloudProfile(){},
    getSession:()=>session,pendingInvitation:()=>invite,invitationRoute:()=>'',Date:{now:()=>now},
  }
  const cache=new Function('deps',`const {${Object.keys(deps)}}=deps;${source};return {resolveAppEntry,rememberChatEntry}`)(deps)
  return {cache,get reads(){return reads},setScope:value=>scope=value,setInvitation:value=>invite=value,
    setPreparing:value=>preparing=value,setTime:value=>now=value,setRoute:value=>route=value,setSession:value=>session=value}
}
test('verified chat is immediately navigable for the same account and household',async()=>{
  const h=cacheHarness()
  h.cache.rememberChatEntry({householdId:'family-a',onboarded:true})
  assert.equal(await h.cache.resolveAppEntry(),'/pages/chat/index');assert.equal(h.reads,0)
  h.setTime(61000);await h.cache.resolveAppEntry();assert.equal(h.reads,1)
})
test('session, invitation and pending preparation changes invalidate the cached entry',async()=>{
  for (const change of [h=>h.setScope('account-b:family-b:rev2'),h=>h.setInvitation('invite'),h=>h.setPreparing(true)]) {
    const h=cacheHarness();h.cache.rememberChatEntry({householdId:'family-a',onboarded:true})
    change(h);h.setRoute('/pages/onboarding/index')
    assert.equal(await h.cache.resolveAppEntry(),'/pages/onboarding/index');assert.equal(h.reads,1)
  }
})
test('foreground forced verification discards prior cached success',async()=>{
  const h=cacheHarness();h.cache.rememberChatEntry({householdId:'family-a',onboarded:true})
  h.setRoute('/pages/onboarding/index')
  assert.equal(await h.cache.resolveAppEntry({force:true}),'/pages/onboarding/index')
  assert.equal(await h.cache.resolveAppEntry(),'/pages/onboarding/index')
  assert.equal(h.reads,2)
})
test('a profile from another family cannot seed the cache',async()=>{
  const h=cacheHarness();h.cache.rememberChatEntry({householdId:'family-b',onboarded:true})
  h.setRoute('/pages/onboarding/index')
  assert.equal(await h.cache.resolveAppEntry(),'/pages/onboarding/index');assert.equal(h.reads,1)
})
