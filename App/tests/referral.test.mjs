import test from 'node:test'
import assert from 'node:assert/strict'
import { createReferralEntry } from '../src/services/referral-entry-client.js'
import { createWechatAuthClient } from '../src/services/wechat-auth-client.js'

const codeA='a'.repeat(24),codeB='b'.repeat(24)
function fixture(send){
  const values=new Map();let account=null,time=1000000
  const store={getStorageSync:k=>values.get(k),setStorageSync:(k,v)=>values.set(k,v)}
  const calls=[]
  const entry=createReferralEntry({storage:store,session:()=>account,now:()=>time,send:async options=>{
    calls.push(options);return send?send(options):{data:{valid:true,receipt:options.data.code,expires_at:time/1000+604800}}
  }})
  return {entry,calls,account:v=>account=v,advance:v=>time+=v}
}
test('first valid invitation survives welcome redirects and duplicate foreground events',async()=>{
  const f=fixture();await Promise.all([f.entry.capture({query:{ref:codeA}}),f.entry.capture({query:{ref:codeB}})])
  assert.equal(await f.entry.pending(),codeA);assert.equal(f.calls.length,1)
  f.entry.consume(codeB);assert.equal(await f.entry.pending(),codeA)
  f.entry.consume(codeA);assert.equal(await f.entry.pending(),'')
})
test('QR scene decoding and expiry permit a new valid source after seven days',async()=>{
  const f=fixture();await f.entry.capture({query:{scene:encodeURIComponent('r='+codeA)}})
  assert.equal(f.calls[0].data.channel,'qr');f.advance(604801000)
  assert.equal(await f.entry.pending(),'');await f.entry.capture({query:{ref:codeB}})
  assert.equal(await f.entry.pending(),codeB)
})
test('invalid code and logged-in users do not create a candidate; provider failure does not block',async()=>{
  const f=fixture();await f.entry.capture({query:{ref:'family-token'}});assert.equal(f.calls.length,0)
  f.account({token:'existing'});await f.entry.capture({query:{ref:codeA}});assert.equal(f.calls.length,0)
  const failing=fixture(()=>{throw Error('offline')});await failing.entry.capture({query:{ref:codeA}})
  assert.equal(await failing.entry.pending(),'')
})
test('invalid first entry does not occupy first-valid attribution',async()=>{
  const f=fixture(options=>({data:options.data.code===codeA?{valid:false}:{valid:true,receipt:'valid',expires_at:900000}}))
  await f.entry.capture({query:{ref:codeA}});await f.entry.capture({query:{ref:codeB}})
  assert.equal(await f.entry.pending(),'valid')
})
test('logout or an account appearing during anonymous resolution discards late receipt',async()=>{
  let done;const f=fixture(()=>new Promise(resolve=>{done=resolve}))
  const pending=f.entry.capture({query:{ref:codeA}});await Promise.resolve();f.entry.clear()
  done({data:{valid:true,receipt:'late',expires_at:999999}});await pending;assert.equal(await f.entry.pending(),'')
})
test('login waits for referral capture, sends optional receipt and consumes only after saved session',async()=>{
  const events=[];let revision=0,fail=true
  const client=createWechatAuthClient({isWechat:true,appId:'wx1234567890abcdef',getCode:async()=> 'wx-code',
    session:{revision:()=>revision,save:()=>{events.push('saved');revision++}},
    referral:{pending:async()=> 'signed-receipt',consume:receipt=>events.push(receipt)},
    send:async options=>{
      if(options.path.endsWith('/config'))return {data:{available:true,appid:'wx1234567890abcdef'}}
      assert.equal(options.data.referral_receipt,'signed-receipt')
      if(fail)throw Error('unknown outcome')
      return {data:{account:{id:1,name:'我'},families:[],access_token:'synthetic',expires_at:Date.now()/1000+1000}}
    }})
  await assert.rejects(client.login(),/unknown/);assert.deepEqual(events,[])
  fail=false;await client.login();assert.deepEqual(events,['saved','signed-receipt'])
})
