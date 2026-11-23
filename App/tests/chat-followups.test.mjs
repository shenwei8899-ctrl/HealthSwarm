import test from 'node:test'
import assert from 'node:assert/strict'
import {normalizeFollowups,followupMessageId,createChatFollowups} from '../src/services/chat-followups.js'
import {chatMessages} from '../src/services/cloud-chat.js'

const items=[{label:'只有15分钟怎么做',question:'这份清淡晚餐只有15分钟准备，应该如何调整？'},{label:'换成不吃鱼的搭配',question:'这份晚餐不吃鱼，可以替换成哪些食物？'}]
const ready={message_id:42,status:'ready',followups:items}
function setup(send,context=()=> 'account:family'){
 const state={items:[],status:'idle'},timers=[]
 return {state,timers,...createChatFollowups({state,send,context,schedule:fn=>{timers.push(fn);return fn},cancel:fn=>{const i=timers.indexOf(fn);if(i>=0)timers.splice(i,1)}})}
}
test('only bounded natural text questions and valid server message ids are accepted',()=>{
 assert.deepEqual(normalizeFollowups(items),items)
 for(const value of [null,{},[items[0],items[0]],Array(3).fill(items[0]),[{label:'',question:'x'}],[{label:'x',question:'x\n'}],[{label:'x',question:'a'.repeat(161)}]])assert.deepEqual(normalizeFollowups(value),[])
 for(const id of ['request-answer','01',-1,0,null,'9007199254740992'])assert.equal(followupMessageId(id),null)
 assert.equal(followupMessageId('42'),42)
})
test('saved suggestions do not call the server or regenerate',async()=>{
 const p=setup(()=>{throw Error('must not call')})
 await p.load({threadId:'thread',messageId:42,saved:items})
 assert.deepEqual(p.state.items,items)
})
test('absent suggestions generate once, pending recovery only reads',async()=>{
 const calls=[],p=setup(async o=>{calls.push(o.method);return {data:calls.length===1?{message_id:42,status:'absent'}:calls.length===2?{message_id:42,status:'pending'}:ready}})
 await p.load({threadId:'thread',messageId:42})
 assert.deepEqual(calls,['GET','POST'])
 await p.timers.shift()();await new Promise(r=>setImmediate(r))
 assert.deepEqual(calls,['GET','POST','GET']);assert.deepEqual(p.state.items,items)
})
test('a lost POST is not automatically reposted',async()=>{
 const calls=[],p=setup(async o=>{calls.push(o.method);if(o.method==='POST')throw Error('lost');return {data:{message_id:42,status:'absent'}}})
 await p.load({threadId:'thread',messageId:42})
 assert.deepEqual(calls,['GET','POST']);assert.deepEqual(p.state.items,[]);assert.equal(p.timers.length,0)
})
test('account changes and disposed conversation reject late answers',async()=>{
 for(const changeAccount of [false,true]){
  let resolve,scope='a';const p=setup(()=>new Promise(r=>resolve=r),()=>scope)
  const flight=p.load({threadId:'thread',messageId:42})
  if(changeAccount)scope='b';else p.clear()
  resolve({data:ready});await flight
  assert.deepEqual(p.state.items,[])
 }
})
test('mismatched message ids and old-server missing endpoints never display another reply',async()=>{
 for(const send of [async()=>({data:{...ready,message_id:43}}),async()=>{throw Object.assign(Error('old server'),{code:404})}]){
  const p=setup(send);await p.load({threadId:'thread',messageId:42});assert.deepEqual(p.state.items,[])
 }
})
test('history projection retains valid saved questions without altering the answer',()=>{
 const [message]=chatMessages({history:[{id:42,role:'assistant',content:'清淡晚餐建议',followups:items}]})
 assert.equal(message.text,'清淡晚餐建议');assert.deepEqual(message.followups,items)
})
