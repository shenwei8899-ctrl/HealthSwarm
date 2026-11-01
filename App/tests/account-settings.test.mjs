import test from 'node:test'
import assert from 'node:assert/strict'
import { createAccountSettingsClient } from '../src/services/account-settings-client.js'
import { createFeedbackDraft } from '../src/services/product-feedback-draft.js'
const id='11111111-1111-4111-8111-111111111111',imageId='22222222-2222-4222-8222-222222222222'

test('account avatar resolves API-relative assets and rejects another account',async()=>{
 const options={session:()=>({accountId:'7',token:'synthetic',clientRevision:'r'}),baseUrl:'https://api.example.test',send:async()=>({data:{id:7,avatar:'/minio/public/avatar/a.jpg'}})}
 assert.equal(await createAccountSettingsClient(options).avatar(),'https://api.example.test/minio/public/avatar/a.jpg')
 await assert.rejects(createAccountSettingsClient({...options,send:async()=>({data:{id:8}})}).avatar(),/账号资料不一致/)
})
test('late avatar upload cannot update a new login',async()=>{
 let account={accountId:'7',token:'a',clientRevision:'r'},finish
 const client=createAccountSettingsClient({session:()=>account,upload:()=>new Promise(resolve=>finish=resolve)})
 const pending=client.saveAvatar('temporary.jpg');account={accountId:'8',token:'b',clientRevision:'s'}
 finish({success:true,avatar_url:'https://example.test/avatar.jpg'})
 await assert.rejects(pending,{code:'SESSION_CHANGED'})
})
test('avatar and feedback require verified save receipts',async()=>{
 const client=createAccountSettingsClient({session:()=>({accountId:'7'}),upload:async()=>({success:false}),send:async()=>({data:{id,status:'draft'}})})
 await assert.rejects(client.saveAvatar('temp'),/未确认/)
 await assert.rejects(client.submit(id,'建议',[]),/未确认/)
})
test('feedback retries retain image receipts and submission ID after uncertain response',async()=>{
 let submissions=0,uploads=0,ids=[]
 const draft=createFeedbackDraft({newId:()=>id,context:()=> 'account',client:{image:async()=>{uploads++;return imageId},submit:async key=>{ids.push(key);if(++submissions===1)throw Error('网络中断');return {id:key}}}})
 draft.state.content='希望增加字号设置';draft.state.images=[{path:'local.jpg',size:100}]
 await draft.submit();assert.equal(draft.state.saved,false);assert.match(draft.state.error,/网络/)
 await draft.submit();assert.equal(draft.state.saved,true);assert.equal(uploads,1);assert.deepEqual(ids,[id,id])
})
test('empty, overlong and oversized feedback does not write',async()=>{
 const draft=createFeedbackDraft({newId:()=>id,context:()=> 'account',client:{submit:()=>{throw Error('unexpected write')}}})
 for(const content of ['  ','文'.repeat(201)]){draft.state.content=content;await draft.submit();assert.match(draft.state.error,/1至200/)}
 draft.state.content='建议';draft.state.images=[{path:'large',size:5*1024*1024+1}]
 await draft.submit();assert.match(draft.state.error,/5MB/)
})
test('busy submit is serialized',async()=>{
 let finish,calls=0,ids=0
 const draft=createFeedbackDraft({newId:()=>String(++ids),context:()=> 'account',client:{submit:()=>{calls++;return new Promise(resolve=>finish=resolve)}}})
 draft.state.content='建议';const pending=draft.submit();await draft.submit();assert.equal(calls,1)
 finish({});await pending;assert.equal(draft.state.saved,true)
})
test('account switch during image upload prevents the subsequent feedback write',async()=>{
 let scope='a',finish,writes=0
 const draft=createFeedbackDraft({newId:()=>id,context:()=>scope,client:{image:()=>new Promise(resolve=>finish=resolve),submit:()=>writes++}})
 draft.state.content='建议';draft.state.images=[{path:'local',size:100}]
 const pending=draft.submit();scope='b';finish(imageId);await pending
 assert.equal(writes,0);assert.equal(draft.state.saved,false);assert.match(draft.state.error,/变化/)
})

test('editing after a failed submission receives a new request ID',async()=>{
 let sequence=0,keys=[]
 const draft=createFeedbackDraft({newId:()=>String(++sequence),context:()=> 'account',client:{submit:async key=>{keys.push(key);throw Error('network')}}})
 draft.state.content='第一条建议';await draft.submit()
 draft.state.content='修改后的建议';await draft.submit()
 assert.deepEqual(keys,['1','2']);assert.equal(draft.state.saved,false)
})
