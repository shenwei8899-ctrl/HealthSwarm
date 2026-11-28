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
function harness(send,options={}){let owner='A';const state=dishSwapState(),saved=[];let id=0;const client=createDishSwap({state,send,context:()=>owner,family:()=> 'family',day:()=>day,newId:()=>String(++id),onPlan:p=>saved.push(p),...options});return{state,client,saved,switchOwner(){owner='B'}}}
function timers(){
 const pending=new Map(),delays=[];let id=0
 return {pending,delays,schedule(fn,delay){delays.push(delay);pending.set(++id,fn);return id},cancel(id){pending.delete(id)},async tick(){const [id,fn]=pending.entries().next().value;pending.delete(id);fn();await Promise.resolve();await Promise.resolve()}}
}

test('duplicate names and sources do not consume the three candidate slots',async()=>{
 const rows=[
  {candidate_id:'fish-a',dish:{name:'糖醋松鼠鱼',file_id:'fish-a',recipe_text_source:'original'}},
  {candidate_id:'fish-b',dish:{name:' 糖醋 松鼠鱼！',file_id:'fish-b',recipe_text_source:'original'}},
  {candidate_id:'fish-copy',dish:{name:'另一标题',source:{file_id:'fish-a'},recipe_text_source:'original'}},
  {candidate_id:'egg',dish:{name:'鸡蛋三明治',file_id:'egg',recipe_text_source:'original'}},
  {candidate_id:'chicken',dish:{name:'清蒸鸡肉',file_id:'chicken',recipe_text_source:'original'}},
 ]
 const response=receipt(0);response.data.meals[0].dishes[0].candidates=rows
 const h=harness(async()=>response);await h.client.load(plan);h.client.open(item,dish,plan)
 assert.deepEqual(h.state.target.candidates.map(c=>c.candidate_id),['fish-a','egg','chicken'])
 assert.equal(h.state.target.candidates[0],rows[0])
 h.client.pause()
 const pending=h.client.load(plan)
 assert.deepEqual(h.client.candidates(item,dish,plan).map(c=>c.candidate_id),['fish-a','egg','chicken'])
 await pending
 assert.deepEqual(h.client.candidates(item,dish,plan).map(c=>c.candidate_id),['fish-a','egg','chicken'])
})

test('untranslated titles do not merge distinct original recipes and repeated IDs render once',async()=>{
 const rows=[
  {candidate_id:'a',dish:{name:'Steamed fish',file_id:'a',chunk_id:'1'}},
  {candidate_id:'a',dish:{name:'Other title',file_id:'other',chunk_id:'2'}},
  {candidate_id:'b',dish:{name:'Roast chicken',file_id:'b',chunk_id:'3'}},
  {candidate_id:'c',dish:{name:'Egg sandwich',file_id:'c',chunk_id:'4'}},
 ]
 const response=receipt(0);response.data.meals[0].dishes[0].candidates=rows
 const h=harness(async()=>response);await h.client.load(plan)
 assert.deepEqual(h.client.candidates(item,dish,plan).map(c=>c.candidate_id),['a','b','c'])
})

for(const n of [0,1,2,3])test(`shows actual ${n} candidates and only enables that dish`,async()=>{
 const h=harness(async()=>receipt(n));await h.client.load(plan)
 assert.equal(h.client.candidates(item,dish,plan).length,n)
 assert.equal(h.client.candidates(item,other,plan).length,0)
 h.client.open(item,dish,plan);assert.equal(h.state.open,true);assert.equal(h.state.target.status,n>0?'ready':'empty')
 assert.equal(h.client.candidates(item,dish,{...plan,version:2}).length,0)
})
test('late candidate replies cannot cross an account switch or a newer load',async()=>{
 let resolve;const h=harness(()=>new Promise(r=>resolve=r));const pending=h.client.load(plan);await Promise.resolve();h.switchOwner();resolve(receipt(3));await pending
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
test('candidate read failure is silent and automatically recovers',async()=>{
 const clock=timers();let reads=0
 const h=harness(async()=>{if(++reads===1)throw Error('候选读取失败');return receipt(3)},clock)
 await h.client.load(plan);assert.equal(h.state.error,'');assert.equal(h.state.loading,false)
 h.client.open(item,dish,plan);assert.equal(h.state.open,true);assert.deepEqual(clock.delays,[2000])
 await clock.tick();assert.equal(reads,2);assert.equal(h.client.candidates(item,dish,plan).length,3)
 assert.equal(clock.pending.size,0);assert.equal(h.state.error,'')
})

test('background retries back off to one minute and clear cancels them',async()=>{
 const clock=timers();let reads=0
 const h=harness(async()=>{reads++;throw Error('候选读取失败')},clock)
 await h.client.load(plan)
 for(let i=0;i<6;i++)await clock.tick()
 assert.deepEqual(clock.delays,[2000,5000,10000,30000,60000,60000,60000])
 assert.equal(h.state.error,'');h.client.clear();assert.equal(clock.pending.size,0);assert.equal(reads,7)
})

for(const change of ['account','day','new-plan'])test(`queued retry is discarded after ${change} changes`,async()=>{
 const clock=timers();let reads=0,date=day
 const h=harness(async()=>{reads++;throw Error('候选读取失败')},{...clock,day:()=>date})
 await h.client.load(plan)
 if(change==='account')h.switchOwner()
 if(change==='day')date='2026-11-17'
 if(change==='new-plan'){await h.client.load({...plan,version:4});assert.equal(clock.pending.size,1)}
 else await clock.tick()
 assert.equal(reads,change==='new-plan'?2:1);h.client.clear();assert.equal(clock.pending.size,0)
})

for(const code of [401,403])test(`authorization ${code} waits for account revalidation`,async()=>{
 const clock=timers(),h=harness(async()=>{throw Object.assign(Error('无权限'),{code})},clock)
 await h.client.load(plan);assert.equal(h.state.error,'');assert.equal(clock.pending.size,0)
})
test('saved swap updates today menu and its cache synchronously',()=>{
 const state=todayMealPlanState(),cache=new Map(),profile={householdId:'family',members:[]}
 const client=createTodayMealPlan({state,day:()=>day,context:()=> 'A',storage:{getStorageSync:k=>cache.get(k),setStorageSync:(k,v)=>cache.set(k,v)}})
 client.acceptSavedPlan(plan,profile);assert.equal(state.plan.version,3);assert.equal(state.verified,true)
 client.acceptSavedPlan({...plan,version:2},profile);assert.equal(state.plan.version,3)
 assert.equal(cache.get('today-menu:snapshot-v1').plan.version,3);client.dispose()
})

test('profile change while choosing removes only the stale meal’s options and surfaces the rearrange message',async()=>{
 const dinner={...item,meal_type:'dinner'},mixed={...plan,meals:[item,dinner]}
 const saved=receipt(2),lunch=saved.data.meals[0]
 saved.data.meals.push({...lunch,meal_type:'dinner'})
 const message='本餐资料已更新，请先重新安排'
 const h=harness(async r=>{
  if(r.method!=='POST')return saved
  throw Object.assign(new Error(message),{code:409,businessCode:'swap_meal_needs_regeneration'})
 })
 await h.client.load(mixed);h.client.open(item,dish,mixed);await h.client.choose(candidates(2)[0])
 assert.equal(h.state.error,message);assert.deepEqual(h.state.target.candidates,[])
 assert.deepEqual(h.state.needsRegeneration,['lunch'])
 assert.deepEqual(h.client.candidates(item,dish,mixed),[])
 assert.equal(h.client.candidates(dinner,dish,mixed).length,2)
 h.client.close()
 assert.equal(h.state.error,'')
 assert.deepEqual(h.state.needsRegeneration,['lunch'])
})
