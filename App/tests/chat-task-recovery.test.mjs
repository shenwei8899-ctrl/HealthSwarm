import test from 'node:test'
import assert from 'node:assert/strict'
import { createHealthTaskFlow } from '../src/services/health-task-flow.js'

const member='11111111-1111-4111-8111-111111111111', thread='22222222-2222-4222-8222-222222222222'
const entry='33333333-3333-4333-8333-333333333333', request='44444444-4444-4444-8444-444444444444'
const failure=(code,businessCode)=>Object.assign(new Error('synthetic'),{code,businessCode})
function fixture(){
  const calls=[],timers=new Map(),streams=[],snapshots=[],saved=new Map()
  let taskError=null,historyError=null,historyGate=null,postError=null,complete=false,malformed=false,otherMember=false,account='one',seq=0
  const flow=createHealthTaskFlow({session:()=>({accountId:account,token:'synthetic'}),revision:()=>account,
    storage:{getStorageSync:k=>saved.get(k),setStorageSync:(k,v)=>saved.set(k,structuredClone(v))},
    newId:(()=>{const ids=[entry,request];return ()=>ids.shift()})(),onChange:s=>snapshots.push(s),
    schedule:(fn,ms)=>{const id=++seq;timers.set(id,{fn,ms});return id},cancel:id=>timers.delete(id),watchNetwork:()=>()=>{},
    subscribe:options=>{streams.push(options);return ()=>{}},send:async o=>{
      calls.push(o)
      if(o.path.endsWith('/members'))return {data:[{id:member,is_owner:true}]}
      if(o.path.endsWith('/readiness'))return {data:{capabilities:{member_id:member},entries:[{entry_type:'consultation',status:'available'}]}}
      if(o.path.endsWith('/task-entries'))return {data:{member_id:member,task_type:'consultation',client_request_id:entry,entry_status:'ready',thread_id:thread,agent_slug:'health-consultation',request_submit_url:'/api/agent/runs'}}
      if(o.path==='/api/agent/runs'){if(postError)throw postError;return {data:{request_id:request,thread_id:thread}}}
      if(o.path.endsWith('/history')){if(historyGate)await historyGate;if(historyError)throw historyError;return {data:{thread:{id:thread,agent_id:'health-consultation'},history:[]}}}
      if(o.path.includes('/tasks/')){
        if(taskError)throw taskError
        return {data:{request_id:request,member_id:otherMember?entry:member,thread_id:thread,task_type:'consultation',agent_slug:'health-consultation',
          request_status:'dispatched',execution_status:complete?'completed':'running',result:complete?(malformed?{result_type:'unexpected'}:{result_type:'general_education_answer',scope:'general_education',answer:'合成答复',citations:[]}):null}}
      }
      throw new Error('unexpected '+o.path)
    }})
  return {flow,calls,timers,streams,snapshots,saved,
    async start(){await flow.open(member,'consultation');await flow.createEntry();return flow.submit('原问题')},
    async tick(){const [id,{fn}]=timers.entries().next().value;timers.delete(id);fn();await new Promise(r=>setImmediate(r))},
    failTask:e=>taskError=e,failHistory:e=>historyError=e,failPost:e=>postError=e,
    holdHistory:()=>{let release;historyGate=new Promise(r=>release=r);return release},
    complete:(bad=false)=>{complete=true;malformed=bad;taskError=null},mismatch:()=>otherMember=true,switch:()=>account='two'}
}

test('accepted task 404 rechecks conversation access and recovers automatically without another POST',async()=>{
  const h=fixture();h.failTask(failure(404));await h.start()
  assert.notEqual(h.flow.getState().invalidated,true)
  assert.equal(h.flow.getState().requestId,request)
  assert.equal(h.calls.filter(c=>c.path.endsWith('/history')).length,1)
  h.complete();await h.tick()
  assert.equal(h.flow.getState().result.text,'合成答复')
  assert.equal(h.calls.filter(c=>c.path==='/api/agent/runs').length,1)
  h.flow.hide()
})

test('persistent missing task preserves the conversation and original ID for safe rechecking',async()=>{
  const h=fixture();h.failTask(failure(404));await h.start();await h.tick();await h.tick()
  const state=h.flow.getState()
  assert.equal(state.readUnavailable,true);assert.equal(state.requestId,request)
  assert.equal(state.entry.thread_id,thread);assert.notEqual(state.invalidated,true)
  await h.flow.submit('不能重复提交')
  assert.equal(h.calls.filter(c=>c.path==='/api/agent/runs').length,1)
  h.complete();await h.tick()
  assert.equal(h.flow.getState().readUnavailable,false);assert.equal(h.flow.getState().result.text,'合成答复')
  h.flow.hide()
})

for(const code of [401,403,404,410])test(`missing task still clears private state when conversation recheck denies ${code}`,async()=>{
  const h=fixture();h.failTask(failure(404));h.failHistory(failure(code));await h.start()
  assert.equal(h.flow.getState().invalidated,true);assert.equal(h.flow.getState().entry,null)
  assert.equal(h.timers.size,0);h.flow.hide()
})

for(const mode of ['payload','answer_unavailable','planner_output_invalid'])test(`result failure ${mode} retries reads then marks only the original message failed`,async()=>{
  const h=fixture()
  if(mode==='payload')h.complete(true);else h.failTask(failure(409,mode))
  await h.start();assert.notEqual(h.flow.getState().invalidated,true)
  await h.tick();await h.tick()
  const state=h.flow.getState()
  assert.equal(state.status,'failed');assert.equal(state.result.type,'error')
  assert.equal(state.requestId,request);assert.equal(state.entry.thread_id,thread)
  assert.equal(state.available,true);assert.notEqual(state.invalidated,true);assert.equal(h.timers.size,0)
  assert.equal(h.calls.filter(c=>c.path==='/api/agent/runs').length,1);h.flow.hide()
})

test('a transient malformed result recovers to the authoritative answer on its original request',async()=>{
  const h=fixture();h.complete(true);await h.start();h.complete();await h.tick()
  assert.equal(h.flow.getState().result.text,'合成答复');assert.equal(h.flow.getState().status,'completed');h.flow.hide()
})

for(const code of [400,404,422,429])test(`definite submit rejection ${code} retains original message identity and exposes failure`,async()=>{
  const h=fixture();h.failPost(failure(code));assert.equal(await h.start(),false)
  const state=h.flow.getState()
  assert.equal(state.status,'failed');assert.equal(state.requestId,request);assert.equal(state.submitUnknown,false)
  assert.equal(state.entry.thread_id,thread);assert.notEqual(state.invalidated,true);h.flow.hide()
})

test('submit 404 with revoked conversation access still clears private state',async()=>{
 const h=fixture();h.failPost(failure(404));h.failHistory(failure(403));await h.start()
 assert.equal(h.flow.getState().invalidated,true);assert.equal(h.flow.getState().entry,null);h.flow.hide()
})

for(const businessCode of [undefined,'daily_plan_version_changed'])test(`submit conflict preserves a verified conversation, code=${businessCode}`,async()=>{
 const h=fixture();h.failPost(failure(409,businessCode))
 try{
  assert.equal(await h.start(),false)
  const state=h.flow.getState()
  assert.notEqual(state.invalidated,true)
  assert.equal(state.entry.thread_id,thread)
  assert.equal(state.submitRejected,true)
  assert.equal(state.submitUnknown,false)
  assert.equal(state.failureStatus,409)
  assert.equal(h.calls.filter(c=>c.path.endsWith('/history')).length,1)
  assert.equal(h.calls.filter(c=>c.path==='/api/agent/runs').length,1)
 }finally{h.flow.hide()}
})

test('submit conflict still invalidates a conversation whose access recheck fails',async()=>{
 const h=fixture();h.failPost(failure(409));h.failHistory(failure(403))
 try{await h.start();assert.equal(h.flow.getState().invalidated,true);assert.equal(h.flow.getState().entry,null)}finally{h.flow.hide()}
})

test('a known processing-policy conflict on submit remains invalidated',async()=>{
 const h=fixture();h.failPost(failure(409,'policy_changed'))
 try{await h.start();assert.equal(h.flow.getState().invalidated,true);assert.equal(h.flow.getState().entry,null)}finally{h.flow.hide()}
})

test('event endpoint 404 falls back to the authoritative task read instead of invalidating chat',async()=>{
  const h=fixture();await h.start();h.complete();h.streams.at(-1).onError(failure(404))
  await new Promise(r=>setImmediate(r))
  assert.equal(h.flow.getState().result.text,'合成答复');assert.notEqual(h.flow.getState().invalidated,true);h.flow.hide()
})

test('mismatched member and policy changes remain fail closed',async()=>{
  for(const mismatch of [true,false]){
    const h=fixture();if(mismatch)h.mismatch();else h.failTask(failure(409,'policy_changed'))
    await h.start();assert.equal(h.flow.getState().invalidated,true);assert.equal(h.flow.getState().result,null);h.flow.hide()
  }
})

test('a definitely rejected submit is not restored as a phantom running task after returning',async()=>{
 const h=fixture();h.failPost(failure(422));await h.start()
 assert.equal(h.saved.get(`health-task:${member}:consultation`).requestId,'')
 h.flow.pause();assert.equal(await h.flow.resume(),true)
 await h.flow.refresh()
 assert.equal(h.flow.getState().status,'failed')
 assert.equal(h.calls.filter(c=>c.path.includes('/tasks/')).length,0);h.flow.hide()
})

for(const action of ['pause','hide','switch'])test(`late conversation access recheck after ${action} cannot restart recovery`,async()=>{
 const h=fixture();h.failTask(failure(404));const release=h.holdHistory(),pending=h.start()
 while(!h.calls.some(c=>c.path.endsWith('/history')))await new Promise(r=>setImmediate(r))
 if(action==='switch')h.switch();else h.flow[action]()
 const count=h.snapshots.length
 release();await pending
 assert.equal(h.snapshots.length,count);assert.equal(h.timers.size,0);h.flow.hide()
})
