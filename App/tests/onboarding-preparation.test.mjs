import {readyPreparation} from './fixtures/preparation-ready.mjs'
import test from 'node:test'
import assert from 'node:assert/strict'
import {createPreparationClient} from '../src/services/preparation-client.js'
import {createEntryResolver} from '../src/services/entry-routing.js'

const saved={id:'preparation-1',date:'2026-10-26',profile_saved:true,status:'preparing',stage:'analyzing'}
function setup(handler,options={}){
 const calls=[],states=[],stored=new Map();let valid=true,saves=0
 const client=createPreparationClient({root:()=>'/preparations',send:async input=>{calls.push(input);return {data:await handler(input,calls.length)}},storage:{setStorageSync:(k,v)=>stored.set(k,v)},onChange:v=>states.push(v),onSaved:()=>saves++,current:()=>valid,wait:async()=>{},...options})
 return {client,calls,states,stored,get saves(){return saves},switchAccount(){valid=false}}
}
test('one accepted submission follows real stages and reuses the saved result',async()=>{
 const f=setup((input,n)=>n===1?saved:n===2?{...saved,stage:'arranging'}:{...saved,status:'ready',stage:'ready',arrangement:{id:'existing-result'}})
 const result=await f.client.run({body:{client_request_id:'original-key'}})
 assert.equal(result.arrangement.id,'existing-result');assert.deepEqual(f.states.map(v=>v.stage),['saving','analyzing','arranging','ready'])
 assert.equal(f.calls.filter(v=>v.method==='POST').length,1);assert.equal(f.calls[0].headers['Idempotency-Key'],'original-key')
 assert.equal(f.stored.get('onboarding-preparation-pending'),null)
})
test('a lost response retains the original pending submission and can replay its key',async()=>{
 const f=setup(()=>{throw new Error('网络暂时中断')})
 await f.client.run({body:{client_request_id:'original-key'}})
 assert.equal(f.saves,0);assert.equal(f.states.at(-1).status,'connection_error')
 assert.equal(f.stored.has('onboarding-preparation-pending'),false)
 await f.client.run({body:{client_request_id:'original-key'}})
 assert.equal(f.calls[1].headers['Idempotency-Key'],'original-key')
})
test('resuming a failed stage never submits the profile again',async()=>{
 const f=setup(()=>({...saved,status:'ready',stage:'ready'}))
 await f.client.run({id:saved.id,resume:true})
 assert.equal(f.calls[0].path,'/preparations/preparation-1/resume');assert.equal(f.calls[0].data,undefined)
})
test('business failure stops polling and preserves the saved profile',async()=>{
 const f=setup(()=>({...saved,status:'failed',message:'食材服务暂未就绪'}))
 await f.client.run({id:saved.id})
 assert.equal(f.calls.length,1);assert.equal(f.states.at(-1).profile_saved,true)
 assert.equal(f.states.at(-1).message,'食材服务暂未就绪')
})
test('account switch discards an in-flight private result',async()=>{
 let release
 const f=setup(()=>new Promise(resolve=>release=resolve))
 const waiting=f.client.run({id:saved.id});f.switchAccount();release({...saved,status:'ready'});await waiting
 assert.equal(f.states.length,0);assert.equal(f.saves,0)
})
test('foreground polling limit keeps the server preparation recoverable',async()=>{
 const f=setup(()=>saved,{pollLimit:1})
 await f.client.run({id:saved.id})
 assert.equal(f.states.at(-1).status,'waiting');assert.equal(f.states.at(-1).profile_saved,true)
 assert.equal(f.calls.every(v=>v.method!=='POST'),true)
})
test('repeated entry shares one in-flight read',async()=>{
 let release
 const f=setup(()=>new Promise(resolve=>release=resolve))
 const first=f.client.run({id:saved.id}),second=f.client.run({id:saved.id})
 assert.equal(f.calls.length,1);release({...saved,status:'ready'});await Promise.all([first,second])
})
test('a complete profile opens chat across unfinished, failed, ready and absent preparation',async()=>{
 const session={accountId:'self',token:'synthetic',householdId:'family',families:[{id:'family'}]}
 for(const [status,expected] of [['preparing','/pages/onboarding/preparing?id=preparation-1'],['failed','/pages/onboarding/preparing?id=preparation-1'],['ready','/pages/chat/index?preparation=preparation-1'],['absent','/pages/onboarding/preparing?id=preparation-1']]){
  const resolve=createEntryResolver({auth:{restore:async()=>session},session:()=>session,readProfile:async()=>({householdId:'family',completeProfile:true}),today:()=> '2026-10-26',readPreparation:async()=>status==='ready'?{...readyPreparation(),id:saved.id}:{...saved,status}})
  assert.equal(await resolve(),'/pages/chat/index')
 }
})

test('pending submission can enter preparation before the cloud profile is complete',async()=>{
 const session={accountId:'self',token:'synthetic',householdId:'family',families:[{id:'family'}]}
 const resolve=createEntryResolver({auth:{restore:async()=>session},session:()=>session,readProfile:async()=>({householdId:'family',completeProfile:false}),pendingPreparation:()=>true})
 assert.equal(await resolve(),'/pages/onboarding/preparing')
})

test('a confirmed profile can enter chat while an older submission remains uncertain',async()=>{
 const session={accountId:'self',token:'synthetic',householdId:'family',families:[{id:'family'}]}
 const resolve=createEntryResolver({auth:{restore:async()=>session},session:()=>session,readProfile:async()=>({householdId:'family',completeProfile:true}),pendingPreparation:()=>true})
 assert.equal(await resolve(),'/pages/chat/index')
})

test('direct onboarding returns the saved receipt without polling meal preparation',async()=>{
 const f=setup(()=>saved)
 const result=await f.client.run({body:{client_request_id:'original-key'},stopAfterSaved:true,throwOnError:true})
 assert.equal(result.profile_saved,true);assert.equal(result.status,'preparing');assert.equal(f.calls.length,1)
 assert.equal(f.saves,1);assert.equal(f.stored.get('onboarding-preparation-pending'),null)
})

test('direct onboarding propagates an unknown write for retry with its original key',async()=>{
 const error=Object.assign(new Error('请求超时'),{code:'NETWORK_ERROR'})
 const f=setup(()=>{throw error})
 await assert.rejects(f.client.run({body:{client_request_id:'original-key'},stopAfterSaved:true,throwOnError:true}),e=>e===error)
 assert.equal(f.saves,0);assert.equal(f.calls[0].headers['Idempotency-Key'],'original-key')
})
