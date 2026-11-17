import test from 'node:test'
import assert from 'node:assert/strict'
import {createDishSwap,dishSwapState} from '../src/services/dish-swap.js'
import {createTodayMealPlan,todayMealPlanState} from '../src/services/today-meal-plan.js'

const day='2026-11-16'
const dish={dish_key:'toast',name:'吐司'},other={dish_key:'soup',name:'辛奇汤'}
const item={meal_type:'lunch',source:{kind:'reference',id:'source'},meal:{dishes:[dish,other]}}
const plan={date:day,status:'ready',version:3,meals:[item],purchase_options:[]}
const candidates=n=>Array.from({length:n},(_,i)=>({candidate_id:'candidate-'+i,dish:{name:'候选'+i,ingredients:['菠菜100克'],steps:['炒熟']}}))
const receipt=n=>({data:{date:day,version:3,meals:[{meal_type:'lunch',dishes:[{dish_key:'toast',candidates:candidates(n)}]}]}})
function harness(send){let owner='A';const state=dishSwapState(),saved=[];let id=0;const client=createDishSwap({state,send,context:()=>owner,family:()=> 'family',day:()=>day,newId:()=>String(++id),onPlan:p=>saved.push(p)});return{state,client,saved,switchOwner(){owner='B'}}}

for(const n of [0,1,2,3])test(`shows actual ${n} candidates and only enables that dish`,async()=>{
 const h=harness(async()=>receipt(n));await h.client.load(plan)
 assert.equal(h.client.candidates(item,dish,plan).length,n)
 assert.equal(h.client.candidates(item,other,plan).length,0)
 h.client.open(item,dish,plan);assert.equal(h.state.open,n>0)
 assert.equal(h.client.candidates(item,dish,{...plan,version:2}).length,0)
})
test('late candidate replies cannot cross an account switch or a newer load',async()=>{
 let resolve;const h=harness(()=>new Promise(r=>resolve=r));const pending=h.client.load(plan);h.switchOwner();resolve(receipt(3));await pending
 assert.equal(h.client.candidates(item,dish,plan).length,0)
 assert.equal(h.state.open,false)
})
test('successful replacement sends exact original identity and adopts authoritative plan',async()=>{
 const calls=[],next={...plan,version:4,meals:[{...item,meal:{dishes:[{dish_key:'spinach',name:'菠菜'},other]}}]}
 const h=harness(async r=>{calls.push(r);return r.method==='POST'?{data:next}:r.path.includes('version=4')?{data:{date:day,version:4,meals:[]}}:receipt(2)})
 await h.client.load(plan);h.client.open(item,dish,plan);await h.client.choose(candidates(2)[0])
 const write=calls.find(r=>r.method==='POST');assert.deepEqual(write.data,{version:3,meal_type:'lunch',dish_key:'toast',candidate_id:'candidate-0',client_request_id:'1'})
 assert.deepEqual(h.saved,[next]);assert.deepEqual(plan.meals[0].meal.dishes,[dish,other]);assert.equal(h.state.open,false);assert.equal(h.state.busy,false)
})
test('unknown write response keeps candidate and idempotency key for retry',async()=>{
 const writes=[];const h=harness(async r=>{if(r.method!=='POST')return receipt(2);writes.push(r.data);throw Error('网络断开')})
 await h.client.load(plan);h.client.open(item,dish,plan);await h.client.choose(candidates(2)[0]);await h.client.choose(candidates(2)[1]);await h.client.choose(candidates(2)[0])
 assert.equal(writes.length,2);assert.deepEqual(writes[0],writes[1]);assert.equal(h.saved.length,0);assert.match(h.state.error,/网络/)
})
test('candidate read failure remains an error and cannot enable a hidden action',async()=>{
 const h=harness(async()=>{throw Error('候选读取失败')});await h.client.load(plan);assert.match(h.state.error,/失败/);h.client.open(item,dish,plan);assert.equal(h.state.open,false)
})
test('saved swap updates today menu and its cache synchronously',()=>{
 const state=todayMealPlanState(),cache=new Map(),profile={householdId:'family',members:[]}
 const client=createTodayMealPlan({state,day:()=>day,context:()=> 'A',storage:{getStorageSync:k=>cache.get(k),setStorageSync:(k,v)=>cache.set(k,v)}})
 client.acceptSavedPlan(plan,profile);assert.equal(state.plan.version,3);assert.equal(state.verified,true)
 client.acceptSavedPlan({...plan,version:2},profile);assert.equal(state.plan.version,3)
 assert.equal(cache.get('today-menu:snapshot-v1').plan.version,3);client.dispose()
})
