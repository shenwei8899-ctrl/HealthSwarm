import test from 'node:test'
import assert from 'node:assert/strict'
import { createConversationHistoryCache } from '../src/services/conversation-history.js'
const snapshot = text => ({messages:[{id:'answer',role:'assistant',text}],runs:[],relatedThreads:[]})
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject}}

test('verified snapshots are immediate, detached from consumers, and isolated by member',async()=>{
  let reads=0
  const cache=createConversationHistoryCache({context:()=> 'session',read:async()=>{reads++;return snapshot('saved')}})
  await cache.read('thread','self');const copy=cache.peek('thread','self');copy.messages[0].text='edited'
  assert.equal(cache.peek('thread','self').messages[0].text,'saved');assert.equal(cache.peek('thread','other'),null)
  await cache.read('thread','self');assert.equal(reads,1)
})
test('a refresh does not clear visible cached data while its response is pending',async()=>{
  const gate=deferred();let reads=0
  const cache=createConversationHistoryCache({context:()=> 'session',read:async()=>++reads===1?snapshot('old'):gate.promise})
  await cache.read('thread','self');const refresh=cache.read('thread','self',{refresh:true})
  assert.equal(cache.peek('thread','self').messages[0].text,'old');gate.resolve(snapshot('new'));await refresh
  assert.equal(cache.peek('thread','self').messages[0].text,'new')
})
test('prefetch and selection deduplicate the same in-flight read',async()=>{
  const gate=deferred();let reads=0
  const cache=createConversationHistoryCache({context:()=> 'session',read:async()=>{reads++;return gate.promise}})
  const a=cache.read('thread','self'),b=cache.read('thread','self',{refresh:true})
  gate.resolve(snapshot('saved'));await Promise.all([a,b]);assert.equal(reads,1)
})
test('account or session changes purge cached messages and reject late private responses',async()=>{
  const gate=deferred();let scope='one'
  const cache=createConversationHistoryCache({context:()=> scope,read:()=>gate.promise})
  const reading=cache.read('thread','self');await Promise.resolve();scope='two';gate.resolve(snapshot('private'))
  await assert.rejects(reading,{code:'STALE_HISTORY'});assert.equal(cache.peek('thread','self'),null)
})
test('known revocation purges a cached title and invalidation prevents late repopulation',async()=>{
  const gate=deferred();let reads=0
  const cache=createConversationHistoryCache({context:()=> 'session',read:async()=>++reads===1?snapshot('old'):gate.promise})
  await cache.read('thread','self');const reading=cache.read('thread','self',{refresh:true});await Promise.resolve()
  cache.invalidate('thread','self');gate.resolve(snapshot('late-private'))
  await assert.rejects(reading,{code:'STALE_HISTORY'});assert.equal(cache.peek('thread','self'),null)
})
test('permission denial removes cached content while network failure preserves the last snapshot',async()=>{
  for(const code of [403,'NETWORK_ERROR']){
    let fail=false
    const cache=createConversationHistoryCache({context:()=> 'session',read:async()=>{if(fail)throw Object.assign(Error('failure'),{code});return snapshot('old')}})
    await cache.read('thread','self');fail=true;await assert.rejects(cache.read('thread','self',{refresh:true}))
    assert.equal(cache.peek('thread','self')===null,code===403)
  }
})
test('memory cache evicts old entries and does not retain oversized image histories',async()=>{
  const cache=createConversationHistoryCache({context:()=> 'session',maxEntries:2,maxBytes:1000,read:async id=>snapshot(id==='image'?'x'.repeat(1000):id)})
  await cache.read('a','self');await cache.read('b','self');cache.peek('a','self');await cache.read('c','self')
  assert.equal(cache.peek('b','self'),null);await cache.read('image','self');assert.equal(cache.peek('image','self'),null)
})
