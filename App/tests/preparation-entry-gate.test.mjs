import test from 'node:test'
import assert from 'node:assert/strict'
import {createEntryResolver} from '../src/services/entry-routing.js'
import {createPreparationClient} from '../src/services/preparation-client.js'
import {readyPreparation} from './fixtures/preparation-ready.mjs'
const session=()=>({accountId:'synthetic',token:'synthetic',householdId:'family-A',families:[{id:'family-A'},{id:'family-B'}]})
function resolver(value){const active=session();return createEntryResolver({auth:{restore:async()=>active},session:()=>active,today:()=> '2026-10-26',readProfile:async()=>({householdId:'family-A',completeProfile:true}),readPreparation:async()=>value})}
for(const status of ['absent','failed','blocked','stale'])test(`saved profile opens home while meal preparation is ${status}`,async()=>{
 let reads=0;const active=session();const resolve=createEntryResolver({auth:{restore:async()=>active},session:()=>active,readProfile:async()=>({householdId:'family-A',completeProfile:true}),readPreparation:async()=>{reads++;return {status}}})
 assert.equal(await resolve(),'/pages/chat/index');assert.equal(reads,0)
})
test('old and incomplete meal receipts do not gate the authenticated homepage',async()=>{
 for(const value of [{status:'ready',id:'broken'},readyPreparation('2026-10-25'),readyPreparation()])assert.equal(await resolver(value)(),'/pages/chat/index')
})
test('switching family while the profile loads cannot route to private home',async()=>{
 let active=session();const resolve=createEntryResolver({auth:{restore:async()=>active},session:()=>active,readProfile:async()=>{active={...active,householdId:'family-B'};return {householdId:'family-A',completeProfile:true}}})
 await assert.rejects(resolve,e=>e.code==='SESSION_CHANGED')
})

test('absent preparation starts from saved profile without resubmitting profile fields',async()=>{
 const calls=[],values=new Map(),states=[]
 const client=createPreparationClient({root:()=>'/preparations',send:async input=>{calls.push(input);return {data:calls.length===1?{status:'absent'}:{...readyPreparation(),status:'blocked'}}},storage:{getStorageSync:k=>values.get(k),setStorageSync:(k,v)=>values.set(k,v)},newId:()=> 'saved-key',onChange:v=>states.push(v)})
 await client.run();assert.equal(calls.length,2);assert.equal(calls[1].path,'/preparations/from-profile');assert.deepEqual(calls[1].data,{client_request_id:'saved-key'});assert.equal(states.at(-1).status,'blocked')
})
test('saved-profile response loss replays the same request key',async()=>{
 const calls=[],values=new Map();let fail=true
 const client=createPreparationClient({root:()=>'/preparations',send:async input=>{calls.push(input);if(!input.method)return {data:{status:'absent'}};if(fail){fail=false;throw new Error('network lost')}return {data:{...readyPreparation(),status:'blocked'}}},storage:{getStorageSync:k=>values.get(k),setStorageSync:(k,v)=>values.set(k,v)},newId:()=> 'saved-key',onChange:()=>{}})
 await client.run();await client.run();assert.deepEqual(calls.filter(v=>v.method==='POST').map(v=>v.data.client_request_id),['saved-key','saved-key'])
})
test('switching identity after the read prevents saved-profile POST',async()=>{
 let current=true;const calls=[];const client=createPreparationClient({root:()=>'/preparations',send:async input=>{calls.push(input);current=false;return {data:{status:'absent'}}},storage:{getStorageSync:()=>null,setStorageSync:()=>{}},current:()=>current,newId:()=> 'saved-key',onChange:()=>{}})
 await client.run();assert.equal(calls.length,1)
})

test('a failed preparation left open overnight recovers through current saved profile',async()=>{
 const calls=[],values=new Map(),states=[]
 const client=createPreparationClient({root:()=>'/preparations',newId:()=> 'today-key',storage:{getStorageSync:k=>values.get(k),setStorageSync:(k,v)=>values.set(k,v)},send:async input=>{calls.push(input);if(input.path.endsWith('/resume'))throw Object.assign(new Error('date changed'),{code:409,businessCode:'preparation_date_changed'});return {data:input.path.endsWith('/current')?{status:'stale'}:{...readyPreparation(),status:'blocked'}}},onChange:v=>states.push(v)})
 await client.run({id:'yesterday',resume:true})
 assert.deepEqual(calls.map(v=>v.path),['/preparations/yesterday/resume','/preparations/current','/preparations/from-profile'])
 assert.equal(states.at(-1).status,'blocked')
})
test('an arbitrary conflict never starts a replacement saved-profile preparation',async()=>{
 const calls=[],states=[]
 const client=createPreparationClient({root:()=>'/preparations',newId:()=> 'key',storage:{getStorageSync:()=>null,setStorageSync:()=>{}},send:async input=>{calls.push(input);throw Object.assign(new Error('request conflict'),{code:409,businessCode:'request_conflict'})},onChange:v=>states.push(v)})
 await client.run({id:'original',resume:true});assert.equal(calls.length,1);assert.equal(states.at(-1).status,'submission_error')
})

test('a stale replay receipt is confirmed before a new key prepares the latest profile',async()=>{
 const calls=[],states=[],values=new Map([['onboarding-preparation-existing-pending',{client_request_id:'lost-key'}]])
 const stale={status:'stale',id:'old-preparation',date:'2026-10-26',profile_saved:true,retryable:false,error_code:'preparation_sources_changed'}
 const client=createPreparationClient({root:()=>'/preparations',newId:()=> 'new-key',storage:{getStorageSync:k=>values.get(k),setStorageSync:(k,v)=>values.set(k,v)},send:async input=>{calls.push(input);return {data:input.path.endsWith('/current')||input.data?.client_request_id==='lost-key'?stale:{...readyPreparation(),status:'blocked'}}},onChange:v=>states.push(v)})
 await client.run()
 assert.deepEqual(calls.map(v=>v.method==='POST'?v.data.client_request_id:'GET'),['GET','lost-key','GET','new-key'])
 assert.equal(states.at(-1).status,'blocked');assert.equal(values.get('onboarding-preparation-existing-pending'),null)
})
