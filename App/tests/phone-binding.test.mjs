import test from 'node:test'
import assert from 'node:assert/strict'
import { createPhoneBindingClient } from '../src/services/phone-binding-client.js'
import { readFileSync } from 'node:fs'
import { ref } from 'vue'

// In-memory protocol doubles only: no database records, real grant or claimed WeChat success.
function harness() {
  let account='account-a', revision=1, userId=12, state, clock=1000, handler
  const calls=[]
  const status=(bound=false)=>({user_id:userId,phone_bound:bound,phone_masked:bound?'138****0000':null,verification_source:bound?'wechat_phone':null,verified_at:bound?1234:null})
  const commerce={connect:async()=>{},sessionRevision:()=>revision,session:()=>({userId}),
    request:async(path,options)=>{calls.push({path,options});if(handler)return handler(path,options);return path.endsWith('/config')?{available:true,appid:'app'}:status()},
    mutate:()=>{throw Error('Never persist a phone grant in mutation storage')}}
  const client=createPhoneBindingClient({commerce,accountContext:()=>account,appId:'app',randomKey:()=> 'phone-test-idempotency-key',update:v=>{state=v},now:()=>clock})
  return {client,calls,status,get state(){return state},handle:f=>{handler=f},switchAccount:()=>{account='account-b';userId=13;revision++},advance:()=>{clock+=46000}}
}
const grant={errMsg:'getPhoneNumber:ok',code:'unit-only-not-a-wechat-grant'}
test('consent cancellation does not submit and binding targets only the authenticated account',async()=>{
  const h=harness();await h.client.load();await h.client.authorize({errMsg:'getPhoneNumber:fail user deny'})
  assert.equal(h.calls.length,2);assert.match(h.state.error,/取消/)
  h.handle(async()=>h.status(true));await h.client.authorize(grant)
  const post=h.calls.at(-1);assert.equal(post.path,'/account/phone/wechat')
  assert.deepEqual(post.options,{method:'POST',data:{phone_code:grant.code},key:'phone-test-idempotency-key'})
  assert.equal(h.state.status.user_id,12);assert.equal(h.state.binding,false)
  assert.equal(JSON.stringify(h.state).includes(grant.code),false)
})
test('double taps submit only once and hidden-page response cannot repaint',async()=>{
  const h=harness();await h.client.load();let finish
  h.handle(()=>new Promise(r=>{finish=r}));const a=h.client.authorize(grant)
  await h.client.authorize(grant);assert.equal(h.calls.filter(x=>x.options?.method==='POST').length,1)
  h.client.dispose();finish(h.status(true));await a
  assert.equal(h.state.ready,false);assert.equal(h.state.status,null);assert.equal(h.state.binding,false)
})
test('account switching during submission discards the old result and releases the loading state',async()=>{
  const h=harness();await h.client.load();const old=h.status(true);let finish
  h.handle(()=>new Promise(r=>{finish=r}));const a=h.client.authorize(grant)
  h.switchAccount();finish(old);await a
  assert.equal(h.state.status,null);assert.equal(h.state.binding,false);assert.equal(h.state.ready,false)
})
test('uncertain submission reads status only, blocks another grant, and can recover a committed binding',async()=>{
  for(const committed of [false,true]){
    const h=harness();await h.client.load()
    h.handle(async(path,options)=>{if(options?.method==='POST')throw Object.assign(Error('timeout'),{code:'NETWORK_ERROR'});return h.status(committed)})
    await h.client.authorize(grant);assert.equal(h.calls.filter(x=>x.options?.method==='POST').length,1)
    assert.equal(h.state.status.phone_bound,committed)
    await h.client.authorize(grant);assert.equal(h.calls.filter(x=>x.options?.method==='POST').length,1)
    assert.equal(h.state.binding,false);assert.equal(h.state.uncertain,!committed)
  }
})
test('wrong AppID, mismatched user and unavailable service never enable submission',async()=>{
  for(const variant of ['appid','user','unavailable']){
    const h=harness();h.handle(async path=>path.endsWith('/config')?{available:variant!=='unavailable',appid:variant==='appid'?'other':'app'}:{...h.status(),user_id:variant==='user'?99:12})
    await h.client.load();await h.client.authorize(grant)
    assert.equal(h.calls.filter(x=>x.options?.method==='POST').length,0)
  }
})
test('a conflict stays unbound and never auto-registers or retries',async()=>{
  const h=harness();await h.client.load();h.handle(async()=>{throw Object.assign(Error('手机号已被其他账号使用'),{code:40962})})
  await h.client.authorize(grant);assert.equal(h.state.status.phone_bound,false);assert.equal(h.state.uncertain,false)
  assert.equal(h.calls.length,3);assert.match(h.state.error,/其他账号/)
})
