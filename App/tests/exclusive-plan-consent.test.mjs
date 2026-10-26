import test from 'node:test'
import assert from 'node:assert/strict'
import {createPlanConsent} from '../src/services/exclusive-plan-consent.js'

function harness(){
 let scope=1
 const members=[{id:'self',name:'本人',version:2,canConfirmAnalysis:true},{id:'child',name:'孩子',version:3,canConfirmAnalysis:true}]
 const calls=[],consented=new Set()
 const flow=createPlanConsent({family:()=> 'family',revision:()=>scope,
 send:async o=>o.path.endsWith('/configuration')?{data:{meal_plan:{available:true,processor:'approved'},policy_version:'p2'}}:o.path.endsWith('/readiness')?{data:{capabilities:{member_id:o.path.split('/')[5],tasks:[{task_type:'meal_preview',status:'unavailable',reason_code:'missing_scopes'},{task_type:'initial_meal_preview',status:consented.has(o.path.split('/')[5])?'needs_input':'unavailable',reason_code:consented.has(o.path.split('/')[5])?'selection_required':'consent_required'}]},entries:[{entry_type:'initial_meal_preview',status:'unavailable',reason_code:'dependency_not_ready',missing_dependencies:['profile_projection']}]}}:{data:{householdId:'family',defaultDiners:members.map(m=>m.id),members:members.map(m=>({...m,healthMemberId:m.id}))}},
 startAnalysis:async(fid,member,policy,purpose)=>{calls.push({fid,member,policy,purpose});consented.add(member.id)}})
 return {flow,calls,members,change:()=>scope++}
}
test('consultation alone never silently grants meal_plan and an unchecked form does not submit',async()=>{
 const h=harness();await h.flow.load();assert.equal(h.calls.length,0)
 assert.equal(await h.flow.accept(),false);assert.equal(h.calls.length,0)
})
test('only explicitly selected authorized members are confirmed with current version and purpose',async()=>{
 const h=harness();await h.flow.load();h.flow.state.members[0].checked=true
 assert.equal(await h.flow.accept(),false)
 assert.equal(h.calls.length,1);assert.equal(h.calls[0].purpose,'meal_plan');assert.equal(h.calls[0].member.version,2)
 assert.deepEqual(h.calls[0].policy,{processor:'approved',policy_version:'p2'})
 assert.equal(h.flow.state.busy,false)
 assert.equal(h.flow.state.members.length,1);h.flow.state.members[0].checked=true
 assert.equal(await h.flow.accept(),true);assert.equal(h.calls.length,2);assert.equal(h.flow.state.busy,false)
})
test('late authorization reads cannot restore another account data',async()=>{
 const resolvers=[];let revision=1
 const h=createPlanConsent({family:()=> 'f',revision:()=>revision,startAnalysis:async()=>assert.fail(),send:()=>new Promise(r=>resolvers.push(r))})
 const pending=h.load();revision++;h.stop();resolvers.forEach(resolve=>resolve({data:{}}));await pending
 assert.deepEqual(h.state.members,[])
})

test('another adult cannot be confirmed by manually checking their disabled option',async()=>{
 const h=harness();h.members[0].canConfirmAnalysis=false;h.members[1].canConfirmAnalysis=false
 await h.flow.load();h.flow.state.members.forEach(m=>m.checked=true)
 assert.equal(await h.flow.accept(),false);assert.equal(h.calls.length,0)
})
