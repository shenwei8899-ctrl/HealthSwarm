import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {createPreparationClient} from '../src/services/preparation-client.js'

function harness(){
 let revision=1,fail=false,delayed=null
 const values=new Map(),calls=[]
 const profile={householdId:'family',members:[{name:'合成成员'}]}
 const deps={createPreparationClient,getSession:()=>({token:'synthetic',householdId:'family'}),sessionRevision:()=>revision,storageContext:()=>`scope:${revision}`,
  scopedStorage:{getStorageSync:k=>values.get(k),setStorageSync:(k,v)=>values.set(k,v)},newHealthRequestId:()=> 'original-key',
  cloudProfileInput:(p,id)=>({client_request_id:id,members:structuredClone(p.members)}),
  request:async input=>{calls.push(structuredClone(input));if(delayed)await delayed;if(fail)throw Object.assign(new Error('请求超时'),{code:'NETWORK_ERROR'});return {data:{id:'receipt',date:'2026-10-28',profile_saved:true,status:'preparing',stage:'analyzing'}}}}
 const source=readFileSync(new URL('../src/services/onboarding-preparation.js',import.meta.url),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
 const {submitOnboardingPreparation:submit}=new Function('deps',`const {${Object.keys(deps)}}=deps;${source};return {submitOnboardingPreparation}`)(deps)
 return {submit,profile,values,calls,setFail:v=>fail=v,switchAccount:()=>revision++,delay(){let release;delayed=new Promise(r=>release=r);return ()=>{delayed=null;release()}}}
}

test('direct submission confirms profile while meals are still preparing',async()=>{
 const h=harness(),receipt=await h.submit(h.profile)
 assert.equal(receipt.profile_saved,true);assert.equal(h.calls.length,1)
 assert.equal(h.values.get('onboarding-preparation-pending'),null)
})

test('lost receipt reuses the original body and key without dropping newer edits',async()=>{
 const h=harness();h.setFail(true)
 await assert.rejects(h.submit(h.profile),e=>e.code==='NETWORK_ERROR')
 assert.equal(h.values.get('onboarding-preparation-pending').client_request_id,'original-key')
 h.profile.members[0].name='后来编辑';h.setFail(false)
 await assert.rejects(h.submit(h.profile),e=>e.code===409)
 assert.deepEqual(h.calls[0].data,h.calls[1].data)
 assert.equal(h.calls[0].headers['Idempotency-Key'],h.calls[1].headers['Idempotency-Key'])
 assert.equal(h.profile.members[0].name,'后来编辑')
})

test('late profile receipt cannot complete onboarding for another account',async()=>{
 const h=harness(),release=h.delay(),pending=h.submit(h.profile)
 h.switchAccount();release()
 await assert.rejects(pending,e=>e.code==='SESSION_CHANGED')
 assert.notEqual(h.values.get('onboarding-preparation-pending'),null)
})
