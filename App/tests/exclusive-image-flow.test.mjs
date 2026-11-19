import test from 'node:test'
import assert from 'node:assert/strict'
import {createExclusiveImageFlow} from '../src/services/exclusive-image-flow.js'

const selection={groupId:'group',tier:'economy',dayNo:1}
function setup(send){
  const applied=[],states=[],timers=[]
  let identity='family-one'
  const flow=createExclusiveImageFlow({send,scope:()=>identity,apply:value=>applied.push(value),status:value=>states.push(value),
    schedule:fn=>{timers.push(fn);return timers.length},cancel:()=>{}})
  return {flow,applied,states,timers,change:()=>{identity='family-two'}}
}
test('starts durable task then polls current day without repeated writes until ready',async()=>{
  const calls=[]
  let complete=false
  const page=setup(async(...args)=>{
    calls.push(args)
    return args[3]?.start?{status:'pending'}:{status:complete?'success':'running',images:complete?[{file_id:'one',image_url:'/one.webp'}]:[]}
  })
  await page.flow.open(selection)
  assert.deepEqual(calls.map(c=>!!c[3]?.start),[true,false])
  assert.equal(page.timers.length,1)
  complete=true
  await page.timers[0]()
  assert.deepEqual(page.applied.at(-1),[{file_id:'one',image_url:'/one.webp'}])
  assert.equal(page.states.at(-1),'success')
  assert.equal(page.timers.length,1)
})
for(const action of ['stop','change'])test(`${action} discards late images without cancelling server task`,async()=>{
  let finish
  const calls=[]
  const page=setup(async(...args)=>{calls.push(args);return args[3]?.start?{status:'pending'}:new Promise(resolve=>{finish=resolve})})
  const pending=page.flow.open(selection)
  await Promise.resolve();await Promise.resolve()
  if(action==='stop')page.flow.stop();else page.change()
  finish({status:'running',images:[{file_id:'old'}]});await pending
  assert.deepEqual(page.applied,[])
  assert.equal(page.timers.length,0)
  assert.equal(calls.length,2)
})
test('switching day invalidates previous day and retry is explicit',async()=>{
  const calls=[]
  const page=setup(async(...args)=>{calls.push(args);return {status:'failed',images:[]}})
  await page.flow.open(selection)
  assert.equal(page.timers.length,0)
  await page.flow.open({...selection,dayNo:2},{start:false})
  await page.flow.retry()
  assert.equal(calls.at(-2)[3].retry,true)
  assert.equal(calls.at(-1)[2],2)
})


test('switching day during task registration waits then reads the new day',async()=>{
  let finish
  const calls=[]
  const page=setup(async(...args)=>{
    calls.push(args)
    return args[3]?.start?new Promise(resolve=>{finish=resolve}):{status:'running',images:[{file_id:'day-'+args[2]}]}
  })
  const initial=page.flow.open(selection)
  const changed=page.flow.open({...selection,dayNo:2},{start:false})
  assert.equal(calls.length,1)
  finish({status:'pending'})
  await Promise.all([initial,changed])
  assert.deepEqual(page.applied,[[{file_id:'day-2'}]])
  assert.equal(page.timers.length,1)
  assert.equal(calls.at(-1)[2],2)
})
