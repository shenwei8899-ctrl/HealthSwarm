import {watch} from 'vue'
import {createChatEntryTransition} from '../src/services/chat-entry-transition.js'
import {createChatKeyboardLayout} from '../src/services/chat-keyboard-layout.js'
import {selectChatPrompts} from '../src/services/chat-prompts.js'
import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {ref,reactive,computed,nextTick,effectScope} from 'vue'
import {createHealthTaskFlow,HEALTH_TEXT_TASKS} from '../src/services/health-task-flow.js'
import {chatPresentation} from '../src/services/chat-presentation.js'
import {chatTimestamp,chatBusinessDate,chatMessages} from '../src/services/cloud-chat.js'

const member='11111111-1111-4111-8111-111111111111',thread='22222222-2222-4222-8222-222222222222'
const rid='33333333-3333-4333-8333-333333333333',newThread='44444444-4444-4444-8444-444444444444'
const date='2026-10-27',type='reference_meal_preview'
const selection={family_id:'family',participant_ids:['self'],plan_date:date,meal_types:['breakfast']}
function fixture({cached=true,createFailure=false}={}){
 const values=new Map(),calls=[],historyReads=[],hooks={}
 let account='synthetic',createAttempts=0,pendingOpen=null,idCount=0
 const storage={getStorageSync:k=>structuredClone(values.get(k)),setStorageSync:(k,v)=>values.set(k,structuredClone(v))}
 if(cached){
  storage.setStorageSync('homepage-chat-task',{memberId:member,type,date,selection})
  storage.setStorageSync(`health-task:${member}:${type}:${JSON.stringify(selection)}:${date}`,{memberId:member,taskType:type,entry:{thread_id:thread,agent_slug:'health-meal-planner'},requestId:rid,requests:[{request_id:rid,status:'failed'}],submitUnknown:false})
 }
 const session=()=>({accountId:account,token:'synthetic',householdId:'family'})
 const send=async o=>{
  calls.push(structuredClone(o))
  if(o.path.endsWith('/members'))return {data:[{id:member,is_owner:true}]}
  if(o.path.endsWith('/readiness')){if(pendingOpen)await pendingOpen;return {data:{capabilities:{member_id:member},entries:['consultation',type].map(entry_type=>({entry_type,status:'available'}))}}}
  if(o.path.includes('/tasks/'))return {data:{member_id:member,thread_id:thread,request_id:rid,task_type:type,agent_slug:'health-meal-planner',request_status:'dispatched',execution_status:'failed',result:{result_type:'error',code:'execution_failed',retryable:false}}}
  if(o.path.includes('/consultations?'))return {data:{items:[{thread_id:newThread,member_id:member,agent_slug:'health-consultation',business_date:null}],has_more:false,next_offset:null}}
  if(o.path.includes('/requests?agent_slug='))return {data:{requests:[]}}
  if(o.path.endsWith('/daily-conversations'))return {data:{days:[]}}
  if(o.path.endsWith('/task-entries')||o.path.endsWith('/consultations')&&o.method==='POST'){
   createAttempts++
   if(createFailure&&createAttempts===1)throw Object.assign(new Error('synthetic timeout'),{code:503})
   if(o.path.endsWith('/consultations'))return {data:{member_id:member,thread_id:newThread,agent_slug:'health-consultation',business_date:null,feedback_selection:null}}
   return {data:{member_id:member,task_type:o.data.task_type,client_request_id:o.data.client_request_id,entry_status:'ready',thread_id:newThread,agent_slug:'health-consultation',request_submit_url:'/api/agent/runs'}}
  }
  if(o.path.includes('/reference-meal-plans/')||o.path.includes('/daily-arrangements/'))return {data:{status:'absent'}}
  throw new Error('Unexpected endpoint '+o.path)
 }
 const deps={createChatEntryTransition,createChatKeyboardLayout,watch,selectChatPrompts,rememberChatEntry:()=>{},ref,reactive,computed,nextTick,HEALTH_TEXT_TASKS,chatPresentation,chatTimestamp,chatBusinessDate,isReferencePlan:()=>false,
  defineProps:()=>({route:{entry:'conversation'}}),onMounted:f=>hooks.mount=f,onShow:f=>hooks.show=f,onHide:f=>hooks.hide=f,onUnmounted:f=>hooks.unmount=f,
  storageContext:()=>account,scopedStorage:storage,getSession:session,localDate:()=>date,newHealthRequestId:()=>rid,
  loadCloudProfile:async()=>({onboarded:true,householdId:'family',selfMemberId:'self',members:[{id:'self',relation:'本人',healthMemberId:member}]}),
  dailyArrangementState:()=>({phase:'idle',busy:false}),createDailyArrangementClient:()=>({pause(){},reset(){},dispose(){}}),
  readCurrentPreparation:async()=>({status:'absent'}),request:send,
  createHealthTaskFlow:opts=>createHealthTaskFlow({...opts,send,session,revision:()=>1,storage,newId:()=>`55555555-5555-4555-8555-${String(++idCount).padStart(12,'0')}`,day:()=>date,subscribe:()=>()=>{}}),
  readChatSnapshot:async id=>{historyReads.push(id);return {messages:id===thread?[{id:'original',role:'user',requestId:rid,text:'请安排今天早餐',createdAt:'2026-10-26T18:05:40.501841',status:'failed'}]:[],runs:[]}},
  uni:{redirectTo(){},reLaunch(){},showToast(){}},
 }
 const script=readFileSync(new URL('../src/components/CloudNutritionChat.vue',import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
 const scope=effectScope(),page=scope.run(()=>new Function('deps',`const {${Object.keys(deps).join(',')}}=deps;${script};return {load,messages,visibleMessages,failedQuestion,failedTask,question,draftImage,task,flow,presentation,entryReady,restartChat,editFailedQuestion}`)(deps))
 return {page,calls,storage,historyReads,hooks,get idCount(){return idCount},changeAccount(){account='other'},pauseOpen(){let release;pendingOpen=new Promise(r=>release=r);return ()=>{pendingOpen=null;release()}},dispose(){hooks.unmount?.();scope.stop()}}
}

test('legacy UTC, explicit offsets and midnight boundaries do not depend on the device timezone',()=>{
 const before=process.env.TZ
 try{for(const zone of ['Asia/Shanghai','UTC','America/Los_Angeles']){
  process.env.TZ=zone
  assert.equal(chatTimestamp('2026-10-26T18:05:40.501841'),'2026-10-26T18:05:40.501Z')
  assert.equal(chatBusinessDate('2026-10-26T18:05:40.501841'),'2026-10-27')
  assert.equal(chatBusinessDate('2026-10-26T15:59:59.999999'),'2026-10-26')
  assert.equal(chatBusinessDate('2026-10-27T00:00:00+08:00'),'2026-10-27')
  assert.equal(chatBusinessDate('2026-10-26T16:00:00Z'),'2026-10-27')
  assert.equal(chatBusinessDate('invalid'),'')
  assert.equal(chatTimestamp('2026-02-30T00:00:00'),'')
  assert.equal(chatTimestamp('2026-10-27T24:00:00'),'')
 }}finally{if(before===undefined)delete process.env.TZ;else process.env.TZ=before}
})
test('history adapts the real server timestamp to an unambiguous UTC instant',()=>{
 const [message]=chatMessages({history:[{id:1,type:'human',content:'synthetic',created_at:'2026-10-26T18:05:40.501841'}]})
 assert.equal(message.createdAt,'2026-10-26T18:05:40.501Z')
})
test('entry restores a failed original question and shows welcome without generating an error bubble or sending',async()=>{
 const h=fixture();await h.page.load()
 assert.equal(h.page.entryReady.value,true);assert.equal(h.page.failedTask.value,true)
 assert.equal(h.page.failedQuestion.value.text,'请安排今天早餐')
 assert.equal(h.page.visibleMessages.value.length,1);assert.equal(h.page.visibleMessages.value[0].role,'user');assert.equal(h.page.presentation.value.welcome,false)
 assert.equal(h.calls.some(c=>c.method==='POST'),false);h.dispose()
})
test('editing a failed question opens ordinary chat and restores text without submitting it',async()=>{
 const h=fixture();await h.page.load();await h.page.editFailedQuestion()
 assert.equal(h.page.question.value,'请安排今天早餐');assert.equal(h.page.task.value.taskType,'consultation')
 assert.equal(h.page.task.value.entry,null)
 assert.equal(h.calls.some(c=>c.path==='/api/agent/runs'),false)
 assert.equal(h.calls.some(c=>c.method==='POST'),false);h.dispose()
})
test('a new consultation stays on its own thread after reentering and retains an edited draft',async()=>{
 const h=fixture();await h.page.load();h.page.question.value='我的修改';await h.page.restartChat()
 assert.equal(h.page.question.value,'我的修改');assert.equal(h.storage.getStorageSync('homepage-chat-task').type,'consultation')
 assert.equal(h.calls.some(c=>c.method==='POST'),false)
 await h.page.flow.createEntry()
 h.storage.setStorageSync('homepage-chat-task',{memberId:member,type:'consultation',date,newConversation:true})
 const count=h.historyReads.length;await h.page.load()
 assert.deepEqual(h.historyReads.slice(count),[newThread]);assert.equal(h.page.failedTask.value,false)
 assert.equal(h.page.presentation.value.welcome,true);h.dispose()
})
test('editing retains the original draft even when fresh-thread creation times out',async()=>{
 const h=fixture({createFailure:true});await h.page.load();await h.page.editFailedQuestion()
 await h.page.flow.createEntry()
 assert.equal(h.page.question.value,'请安排今天早餐');assert.equal(h.page.task.value.entry.pending,true)
 await h.page.load();assert.equal(h.page.question.value,'请安排今天早餐')
 assert.equal(h.calls.some(c=>c.path==='/api/agent/runs'),false);h.dispose()
})
test('uncertain fresh-thread creation reuses the original key and never falls back to the daily thread',async()=>{
 const h=fixture({createFailure:true});await h.page.load();await h.page.restartChat()
 await h.page.flow.createEntry()
 await h.page.load();await h.page.flow.createEntry()
 const creates=h.calls.filter(c=>c.path.endsWith('/consultations')&&c.method==='POST')
 assert.equal(creates.length,2);assert.equal(creates[0].data.client_request_id,creates[1].data.client_request_id)
 assert.equal(h.idCount,1)
 assert.equal(h.calls.some(c=>c.path.endsWith('/daily-consultations')),false);h.dispose()
})
for(const reason of ['account','hide'])test(`editing never restores private text after ${reason} changes while preparing a fresh consultation`,async()=>{
 const h=fixture();await h.page.load();const release=h.pauseOpen(),pending=h.page.editFailedQuestion()
 await new Promise(r=>setImmediate(r));if(reason==='account')h.changeAccount();else h.hooks.hide()
 release();await pending;assert.equal(h.page.question.value,'')
 if(reason==='hide'){await h.page.load();assert.equal(h.page.question.value,'');assert.equal(h.calls.some(c=>c.path==='/api/agent/runs'),false)}
 h.dispose()
})
