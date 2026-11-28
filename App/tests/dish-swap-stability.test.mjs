import test from 'node:test'
import assert from 'node:assert/strict'
import {createDishSwap,dishSwapState} from '../src/services/dish-swap.js'

const settle=()=>new Promise(setImmediate)
const day='2026-11-21',dish={dish_key:'known'},item={meal_type:'lunch'}
const plan={date:day,status:'ready',version:3}
const reply=(version=3,available=true)=>({data:{date:day,version,meals:[{meal_type:'lunch',dishes:[
 {dish_key:'known',candidates:available?[{candidate_id:'c1'}]:[]},
 {dish_key:'unknown',candidates:[]}
]}]}})
function harness(options={}) {
 const state=dishSwapState()
 const client=createDishSwap({state,day:()=>day,context:()=> 'A',family:()=> 'family',...options})
 return {state,client}
}

test('same-version reload and verified return retain buttons while disabling stale actions',async()=>{
 let resolve
 const h=harness({send:()=>new Promise(r=>{resolve=r})})
 let pending=h.client.load(plan);await Promise.resolve();resolve(reply());await pending
 for(const pause of [false,true]){
  if(pause){h.client.pause();assert.equal(h.state.entries.length,0)}
  pending=h.client.load({...plan});await Promise.resolve()
  assert.equal(h.client.candidates(item,dish,plan).length,1)
  assert.equal(h.state.loading,true)
  h.client.open(item,dish,plan);assert.equal(h.state.open,true)
  resolve(reply());await pending
  assert.equal(h.state.loading,false)
 }
 assert.equal(h.client.candidates(item,{dish_key:'unknown'},plan).length,0)
 h.client.clear()
})

test('temporary read failure keeps verified same-version candidates, authoritative empty removes them',async()=>{
 let mode='ok',retry
 const h=harness({send:async()=>{if(mode==='fail')throw Error('offline');return reply(3,mode!=='empty')},schedule:fn=>(retry=fn,1),cancel:()=>{retry=null}})
 await h.client.load(plan)
 mode='fail';await h.client.load({...plan})
 assert.equal(h.client.candidates(item,dish,plan).length,1);assert.ok(retry)
 mode='empty';await h.client.load(plan)
 assert.equal(h.client.candidates(item,dish,plan).length,0);assert.equal(retry,null)
 h.client.clear()
})

for(const change of ['account','family','date','version','clear'])test(`cached candidates never cross ${change}`,async()=>{
 let owner='A',family='family',date=day,resolve
 const h=harness({context:()=>owner,family:()=>family,day:()=>date,send:()=>new Promise(r=>{resolve=r})})
 let pending=h.client.load(plan);await Promise.resolve();resolve(reply());await pending
 h.client.pause()
 if(change==='account')owner='B'
 if(change==='family')family='other'
 if(change==='date')date='2026-11-22'
 if(change==='clear')h.client.clear()
 const next=change==='version'?{...plan,version:4}:plan
 pending=h.client.load(next)
 assert.equal(h.client.candidates(item,dish,next).length,0)
 if(change!=='date'){await Promise.resolve();resolve(reply(next.version));await pending}
 h.client.clear()
})

test('409 refreshes current plan and then requests the new version without writes',async()=>{
 const paths=[],saved=[]
 const h=harness({send:async r=>{paths.push(r.path);assert.equal(r.method,undefined)
  if(r.path.endsWith('version=3'))throw Object.assign(Error('changed'),{code:409})
  return reply(4)
 },readPlan:async()=>({...plan,version:4}),onPlan:p=>saved.push(p)})
 await h.client.load(plan)
 assert.equal(paths.length,2);assert.match(paths[1],/version=4$/)
 assert.equal(saved[0].version,4);assert.equal(h.state.version,4)
 assert.equal(h.client.candidates(item,dish,saved[0]).length,1)
 h.client.clear()
})

test('failed conflict refresh retries the plan read instead of the obsolete candidates',async()=>{
 let candidates=0,reads=0,retry
 const h=harness({send:async()=>{candidates++;throw Object.assign(Error('changed'),{code:409})},
  readPlan:async()=>{reads++;throw Error('offline')},schedule:fn=>(retry=fn,1),cancel:()=>{retry=null}})
 await h.client.load(plan);assert.equal(candidates,1);assert.equal(reads,1)
 retry();await settle()
 assert.equal(candidates,1);assert.equal(reads,2)
 h.client.clear();assert.equal(retry,null)
})

test('persistent conflict backs off rather than looping immediately',async()=>{
 let candidates=0,reads=0,retry
 const h=harness({send:async()=>{candidates++;throw Object.assign(Error('changed'),{code:409})},
  readPlan:async()=>{reads++;return plan},schedule:fn=>(retry=fn,1),cancel:()=>{retry=null}})
 await h.client.load(plan)
 assert.equal(candidates,2);assert.equal(reads,1);assert.ok(retry)
 h.client.clear()
})

test('late plan refresh after pause cannot restore candidates or adopt a plan',async()=>{
 let resolve,adopted=0
 const h=harness({send:async()=>{throw Object.assign(Error('changed'),{code:409})},
  readPlan:()=>new Promise(r=>{resolve=r}),onPlan:()=>{adopted++}})
 const pending=h.client.load(plan);await settle()
 h.client.pause();resolve({...plan,version:4});await pending
 assert.equal(adopted,0);assert.equal(h.state.entries.length,0)
 h.client.clear()
})

test('revoked access discards cached candidates rather than restoring them on return',async()=>{
 let deny=false,resolve
 const h=harness({send:()=>deny?Promise.reject(Object.assign(Error('denied'),{code:403})):new Promise(r=>{resolve=r})})
 let pending=h.client.load(plan);await Promise.resolve();resolve(reply());await pending
 deny=true;await h.client.load(plan);assert.equal(h.state.entries.length,0)
 deny=false;pending=h.client.load(plan);assert.equal(h.state.entries.length,0)
 await Promise.resolve();resolve(reply());await pending;h.client.clear()
})


test('non-current and non-ready plans never read account credentials or start requests',async()=>{
 const unexpected=()=>{throw Error('must not be called')}
 const client=createDishSwap({state:dishSwapState(),day:()=>day,context:unexpected,family:unexpected,send:unexpected})
 await client.load({...plan,date:'2026-11-20'})
 await client.load({...plan,status:'absent'})
 client.clear()
})
