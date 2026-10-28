import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {createEntryResolver} from '../src/services/entry-routing.js'

function client({complete=true,enabled=true,switchDuringOpen=false}={}){
 const calls=[],saved=[];let revision=1
 const source={source:'api',householdId:'family',selfMemberId:'self',onboarded:complete,completeProfile:complete,members:[{id:'self',version:3,relation:'爸爸'}]}
 const deps={getSession:()=>({token:'synthetic',householdId:'family'}),sessionRevision:()=>revision,pendingInvitation:()=>null,
 normalizeProfile:p=>structuredClone(p),saveProfile:p=>saved.push(p),newHealthRequestId:()=> 'request',
 scopedStorage:{getStorageSync:()=>null,setStorageSync(){}},
 request:async o=>{calls.push(structuredClone(o));
  if(o.path==='/api/health/v1/configuration')return {data:{consultation:{available:enabled,processor:'processor'},policy_version:'policy'}}
  if(o.method==='POST'){if(switchDuringOpen)revision++;return {data:{...source,members:[{...source.members[0],healthMemberId:'health-self'}]}}}
  return {data:source}
 }}
 const code=readFileSync(new URL('../src/services/cloud-profile.js',import.meta.url),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
 const load=new Function('deps',`const {${Object.keys(deps)}}=deps;${code};return loadCloudProfile`)(deps)
 return {load,calls,saved}
}
test('complete existing own profile automatically opens consultation without manual consent fields',async()=>{
 const c=client();const p=await c.load();assert.equal(p.members[0].healthMemberId,'health-self')
 const writes=c.calls.filter(o=>o.method==='POST');assert.equal(writes.length,1)
 assert.deepEqual(writes[0].data,{action:'open_consultation',client_request_id:'request',member_id:'self',expected_version:3})
 assert.equal(c.saved.length,1)
})
test('incomplete profile keeps onboarding without creating consultation',async()=>{
 const c=client({complete:false});await c.load();assert.equal(c.calls.filter(o=>o.method==='POST').length,0)
})
test('an unavailable model leaves the saved profile readable without opening consultation',async()=>{
 const c=client({enabled:false});await c.load();assert.equal(c.calls.filter(o=>o.method==='POST').length,0);assert.equal(c.saved.length,1)
})
test('account switch during automatic opening cannot cache the prior private profile',async()=>{
 const c=client({switchDuringOpen:true});await assert.rejects(c.load(),/账号已变化/);assert.equal(c.saved.length,0)
})
test('onboarding and member details no longer ask for manual consultation approval',()=>{
 const onboarding=readFileSync(new URL('../src/pages/onboarding/index.vue',import.meta.url),'utf8')
 const detail=readFileSync(new URL('../src/components/CloudMemberDetail.vue',import.meta.url),'utf8')
 assert.doesNotMatch(onboarding,/analysisAccepted|同意上述数据处理|保存并开启本人咨询/)
 assert.match(onboarding,/完成建档，开始对话/)
 assert.doesNotMatch(detail,/我已核对资料并同意|同意并开始分析|@click="confirmProfile"/)
})


test('complete profile opens chat without requiring meal preparation or another confirmation',async()=>{
 const session={accountId:'self',token:'synthetic',householdId:'family',families:[{id:'family'}]}
 const resolve=createEntryResolver({auth:{restore:async()=>session},session:()=>session,readProfile:async()=>({householdId:'family',completeProfile:true,onboarded:false})})
 assert.equal(await resolve(),'/pages/chat/index')
 const chat=readFileSync(new URL('../src/components/CloudNutritionChat.vue',import.meta.url),'utf8')
 const check=chat.match(/if\((!next\.completeProfile&&!next\.onboarded)\)\{uni\.redirectTo/)[1]
 assert.equal(new Function('next',`return ${check}`)({completeProfile:true,onboarded:false}),false)
})
