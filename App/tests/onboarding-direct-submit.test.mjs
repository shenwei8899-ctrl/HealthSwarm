import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {createPreparationClient} from '../src/services/preparation-client.js'

function harness(){
 let revision=1,fail=false,delayed=null
 const values=new Map(),calls=[],profileSaves=[]
 const profile={householdId:'family',members:[{name:'合成成员'}],healthConfiguration:{policy_version:'policy-1',consultation:{available:true,processor:'processor-a'},meal_plan:{available:true,processor:'processor-b'}}}
 const deps={createPreparationClient,
  saveCloudProfile:async(p,options)=>{profileSaves.push({profile:structuredClone(p),options});if(fail)throw new Error('保存失败');return {...p,completeProfile:true}},
  loadCloudProfile:async()=>({...profile,completeProfile:true}),getSession:()=>({token:'synthetic',householdId:'family'}),sessionRevision:()=>revision,storageContext:()=>`scope:${revision}`,
  scopedStorage:{getStorageSync:k=>values.get(k),setStorageSync:(k,v)=>values.set(k,v)},newHealthRequestId:()=> 'original-key',
  cloudProfileInput:(p,id)=>({client_request_id:id,members:structuredClone(p.members)}),
  request:async input=>{calls.push(structuredClone(input));if(delayed)await delayed;if(fail)throw Object.assign(new Error('请求超时'),{code:'NETWORK_ERROR'});return {data:{id:'receipt',date:'2026-10-28',profile_saved:true,status:'preparing',stage:'analyzing'}}}}
 const source=readFileSync(new URL('../src/services/onboarding-preparation.js',import.meta.url),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
 const {submitOnboardingPreparation:submit,saveOnboardingProfile:save}=new Function('deps',`const {${Object.keys(deps)}}=deps;${source};return {submitOnboardingPreparation,saveOnboardingProfile}`)(deps)
 return {submit,save,profile,values,calls,profileSaves,setFail:v=>fail=v,switchAccount:()=>revision++,delay(){let release;delayed=new Promise(r=>release=r);return ()=>{delayed=null;release()}}}
}

test('direct submission confirms profile while meals are still preparing',async()=>{
 const h=harness(),receipt=await h.submit(h.profile,{consentAccepted:true})
 assert.equal(receipt.profile_saved,true);assert.equal(h.calls.length,1)
 assert.equal(h.values.get('onboarding-preparation-pending'),null)
})

test('lost receipt reuses the original body and key without dropping newer edits',async()=>{
 const h=harness();h.setFail(true)
 await assert.rejects(h.submit(h.profile,{consentAccepted:true}),e=>e.code==='NETWORK_ERROR')
 assert.equal(h.values.get('onboarding-preparation-pending').client_request_id,'original-key')
 h.profile.members[0].name='后来编辑';h.setFail(false)
 await assert.rejects(h.submit(h.profile),e=>e.code===409)
 assert.deepEqual(h.calls[0].data,h.calls[1].data)
 assert.equal(h.calls[0].headers['Idempotency-Key'],h.calls[1].headers['Idempotency-Key'])
 assert.equal(h.profile.members[0].name,'后来编辑')
})

test('late profile receipt cannot complete onboarding for another account',async()=>{
 const h=harness(),release=h.delay(),pending=h.submit(h.profile,{consentAccepted:true})
 h.switchAccount();release()
 await assert.rejects(pending,e=>e.code==='SESSION_CHANGED')
 assert.notEqual(h.values.get('onboarding-preparation-pending'),null)
})

test('new onboarding requires an explicit decision and current processing details',async()=>{
 const h=harness()
 await assert.rejects(h.submit(h.profile),/明确选择是否同意/)
 assert.equal(h.calls.length,0)
 h.profile.healthConfiguration.meal_plan.processor=''
 await assert.rejects(h.submit(h.profile,{consentAccepted:true}),/处理说明尚未读取/)
 assert.equal(h.calls.length,0)
})

test('new profile saves do not submit or wait for preparation, even without any meal configuration',async()=>{
 const h=harness();h.profile.healthConfiguration={};h.values.set('onboarding-preparation-active','failed-old-task')
 const saved=await h.save(h.profile)
 assert.equal(saved.completeProfile,true);assert.equal(h.calls.length,0)
 assert.equal(h.profileSaves.length,1);assert.deepEqual(h.profileSaves[0].options,{reviewOnly:true})
 assert.equal(h.values.get('onboarding-preparation-active'),null)
})
test('failed ordinary saving retains recovery state and never reports success',async()=>{
 const h=harness();h.values.set('onboarding-preparation-active','old-task');h.setFail(true)
 await assert.rejects(h.save(h.profile),/保存失败/)
 assert.equal(h.calls.length,0);assert.equal(h.values.get('onboarding-preparation-active'),'old-task')
})
test('an uncertain legacy save is replayed once without starting a replacement or polling meals',async()=>{
 const h=harness();h.setFail(true)
 await assert.rejects(h.submit(h.profile,{consentAccepted:true}))
 const original=structuredClone(h.calls[0]);h.setFail(false)
 const result=await h.save(h.profile)
 assert.equal(result.completeProfile,true);assert.equal(h.profileSaves.length,0)
 assert.equal(h.calls.length,2);assert.deepEqual(h.calls[1],original)
 assert.equal(h.values.get('onboarding-preparation-pending'),null)
 assert.equal(h.values.get('onboarding-preparation-active'),null)
})
test('legacy recovery cannot silently discard edits made after the uncertain submission',async()=>{
 const h=harness();h.setFail(true);await assert.rejects(h.submit(h.profile,{consentAccepted:true}))
 h.profile.members[0].name='后续修改';h.setFail(false)
 await assert.rejects(h.save(h.profile),e=>e.businessCode==='previous_profile_submission_settled')
 assert.equal(h.profileSaves.length,0);assert.equal(h.profile.members[0].name,'后续修改')
})
