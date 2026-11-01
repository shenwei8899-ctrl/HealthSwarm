import test from 'node:test'
import assert from 'node:assert/strict'
import { createAccountSettingsClient } from '../src/services/account-settings-client.js'
const account={accountId:'7',token:'synthetic-token',clientRevision:'r'}

test('settings reads nickname from the current account profile',async()=>{
 const client=createAccountSettingsClient({session:()=>account,send:async()=>({data:{id:7,username:'小林',avatar:null}})})
 assert.deepEqual(await client.profile(),{nickname:'小林',avatar:''})
})
test('nickname save only updates account username and confirms the saved value',async()=>{
 const requests=[]
 const client=createAccountSettingsClient({session:()=>account,send:async options=>{requests.push(options);return {data:{id:7,username:'小林_2026'}}}})
 assert.equal(await client.saveNickname('  小林_2026  '),'小林_2026')
 assert.deepEqual(requests,[{path:'/api/auth/profile',method:'PUT',data:{username:'小林_2026'}}])
})
for(const nickname of ['', '林', '名'.repeat(21), '小林😀','小 林'])test(`invalid nickname never writes: ${JSON.stringify(nickname)}`,async()=>{
 let writes=0
 const client=createAccountSettingsClient({session:()=>account,send:async()=>{writes++}})
 await assert.rejects(client.saveNickname(nickname),/2–20/)
 assert.equal(writes,0)
})
test('duplicate nickname and uncertain save do not become success',async()=>{
 const rejected=createAccountSettingsClient({session:()=>account,send:async()=>{throw Error('用户名已存在')}})
 await assert.rejects(rejected.saveNickname('小林'),/已存在/)
 const mismatched=createAccountSettingsClient({session:()=>account,send:async()=>({data:{id:7,username:'旧昵称'}})})
 await assert.rejects(mismatched.saveNickname('小林'),/未确认/)
})
test('account switch during nickname save rejects the late response',async()=>{
 let current=account,finish
 const client=createAccountSettingsClient({session:()=>current,send:()=>new Promise(resolve=>finish=resolve)})
 const pending=client.saveNickname('小林');current={accountId:'8',token:'new',clientRevision:'s'}
 finish({data:{id:7,username:'小林'}})
 await assert.rejects(pending,{code:'SESSION_CHANGED'})
})
