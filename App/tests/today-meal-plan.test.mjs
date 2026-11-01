import test from 'node:test'
import assert from 'node:assert/strict'
import {todayMealPlanState,createTodayMealPlan} from '../src/services/today-meal-plan.js'

const date='2026-10-30'
const profile={householdId:'family',selfMemberId:'self',members:[{id:'self',healthMemberId:'health-self'}]}
const absent=()=>({status:'absent',date,version:0,meals:[]})
const ready=()=>({status:'ready',date,version:1,meals:['breakfast','lunch','dinner'].map(meal_type=>({meal_type,source:{kind:'reference',id:'preview'},meal:{dishes:[{name:'菜品一'},{name:'菜品二'}]}}))})
function fixture({read=async()=>absent(),available=true,consent=false,unknown=false,accepted=true,invalid=false,pollLimit=45}={}){
 const state=todayMealPlanState(),calls=[],timers=new Map(),cache=new Map(),published=[]
 let owner='account:family',sequence=0
 const client=createTodayMealPlan({state,day:()=>date,context:()=>owner,read:async(...args)=>{calls.push(['read',...args]);return read(...args)},
  storage:{getStorageSync:k=>cache.get(k),setStorageSync:(k,v)=>cache.set(k,v)},
  schedule:fn=>{timers.set(++sequence,fn);return sequence},cancel:id=>timers.delete(id),pollLimit,onPlan:plan=>published.push(plan),
  createFlow:({storage,onChange})=>{
   calls.push(['flow']);let value={}
   return {getState:()=>value,
    async open(member,type,selection,options){calls.push(['open',member,type,selection,options]);storage.setStorageSync('task',{member});value={available,consentOption:consent?{}:null,...(unknown?{requestId:'existing',submitUnknown:true}:{})};if(invalid){value.invalidated=true;onChange(value)}},
    async createEntry(){calls.push(['entry']);value.entry={thread_id:'thread'}},
    async submit(query){calls.push(['submit',query]);value={...value,requestId:'new',status:accepted?'queued':'',submitUnknown:!accepted};return accepted},
    pause(){calls.push(['pause']);onChange(value)},
   }
  }})
 return {state,client,calls,timers,cache,published,setOwner:value=>owner=value,async tick(){const next=timers.entries().next().value;assert.ok(next,'expected scheduled read');timers.delete(next[0]);await next[1]()}}
}
test('opening an existing menu only reads and publishes its saved business plan',async()=>{
 const h=fixture({read:async()=>ready()});await h.client.open(profile)
 assert.equal(h.state.phase,'ready');assert.equal(h.state.plan.meals.length,3);assert.equal(h.published.length,1)
 assert.deepEqual(h.calls,[['read','family',date]])
})
test('an authoritative absent menu generates once, then renders the read model in place',async()=>{
 let plan=absent();const h=fixture({read:async()=>plan});await h.client.open(profile)
 assert.equal(h.state.phase,'generating');assert.equal(h.state.plan,null)
 const opened=h.calls.find(c=>c[0]==='open');assert.equal(opened[2],'reference_meal_preview')
 assert.deepEqual(opened[3],{mode:'reference',family_id:'family',plan_date:date,participant_ids:['self'],meal_types:['breakfast','lunch','dinner'],daily_base_version:0})
 assert.equal(h.calls.filter(c=>c[0]==='submit').length,1)
 plan=ready();await h.tick();assert.equal(h.state.phase,'ready');assert.equal(h.state.plan.version,1)
 assert.equal(h.timers.size,0);assert.deepEqual([...h.cache.keys()],['today-menu:task'])
})
test('a task running on another device is followed without creating a flow or submitting',async()=>{
 let plan={...absent(),pending:{status:'running',request_id:'other'}}
 const h=fixture({read:async()=>plan});await h.client.open(profile)
 assert.equal(h.state.phase,'generating');assert.equal(h.calls.some(c=>c[0]==='flow'),false)
 plan=ready();await h.tick();assert.equal(h.state.phase,'ready')
})
test('reopening a pending menu never creates a second generation',async()=>{
 const h=fixture({read:async()=>({...absent(),pending:{status:'queued'}})})
 await h.client.open(profile);h.client.pause();await h.client.open(profile)
 assert.equal(h.calls.some(c=>c[0]==='submit'),false);assert.equal(h.timers.size,1)
})
for(const code of [503,401,403,404,409,410])test(`failed menu read ${code} never becomes absent or a generation POST`,async()=>{
 const h=fixture({read:async()=>{throw Object.assign(new Error('read refused'),{code})}})
 await h.client.open(profile);assert.equal(h.state.phase,'error');assert.equal(h.state.plan,null)
 assert.equal(h.calls.some(c=>c[0]==='flow'),false)
})
test('uncertain submission is followed with reads and never resubmitted',async()=>{
 const h=fixture({accepted:false});await h.client.open(profile);await h.tick();await h.tick()
 assert.equal(h.calls.filter(c=>c[0]==='submit').length,1);assert.equal(h.state.phase,'generating');h.client.pause()
})
test('a cached uncertain task survives reopening without a fresh POST',async()=>{
 const h=fixture({unknown:true});await h.client.open(profile)
 assert.equal(h.calls.some(c=>c[0]==='entry'||c[0]==='submit'),false);assert.equal(h.state.phase,'generating');h.client.pause()
})
test('required input and processing consent never get an invented answer or automatic acceptance',async()=>{
 const h=fixture({read:async()=>({...absent(),pending:{status:'needs_input',questions:['食物限制？']}})})
 await h.client.open(profile);assert.equal(h.state.phase,'error');assert.equal(h.calls.length,1)
 const blocked=fixture({available:false,consent:true});await blocked.client.open(profile)
 assert.equal(blocked.state.phase,'error');assert.equal(blocked.calls.some(c=>c[0]==='entry'||c[0]==='submit'),false)
})
test('closing a menu invalidates a late read before it can create an AI task',async()=>{
 let resolve;const h=fixture({read:()=>new Promise(r=>resolve=r)})
 const opening=h.client.open(profile);h.client.clear();resolve(absent());await opening
 assert.equal(h.state.phase,'idle');assert.equal(h.calls.length,1);assert.equal(h.timers.size,0)
})
test('an account change discards late private data',async()=>{
 let resolve;const h=fixture({read:()=>new Promise(r=>resolve=r)})
 const opening=h.client.open(profile);h.setOwner('new-account');resolve(ready());await opening
 assert.equal(h.state.plan,null);assert.equal(h.state.phase,'idle');assert.equal(h.published.length,0)
})
test('an older open cannot overwrite the newer menu',async()=>{
 const reads=[];const h=fixture({read:()=>new Promise(r=>reads.push(r))})
 const a=h.client.open(profile),b=h.client.open(profile);reads[1](ready());await b;reads[0](absent());await a
 assert.equal(h.state.phase,'ready');assert.equal(h.calls.some(c=>c[0]==='submit'),false)
})
test('poll exhaustion ends the loading view and keeps no live timer',async()=>{
 const h=fixture({read:async()=>({...absent(),pending:{status:'running'}}),pollLimit:2})
 await h.client.open(profile);await h.tick();await h.tick()
 assert.equal(h.state.phase,'error');assert.equal(h.timers.size,0)
})
test('an existing saved menu remains visible while another task is running or fails',async()=>{
 let plan={...ready(),pending:{status:'running'}};const h=fixture({read:async()=>plan})
 await h.client.open(profile);assert.equal(h.state.phase,'ready')
 plan={...ready(),pending:{status:'failed'}};await h.tick()
 assert.equal(h.state.phase,'ready');assert.equal(h.state.issue,true);assert.equal(h.state.plan.meals.length,3)
})
test('authorization invalidation from the task flow is finite and clears menu contents',async()=>{
 const h=fixture({invalid:true});await h.client.open(profile)
 assert.equal(h.state.phase,'error');assert.equal(h.state.plan,null);assert.equal(h.calls.some(c=>c[0]==='submit'),false)
})
test('a refused poll cannot leave the previous private meal visible',async()=>{
 let denied=false;const h=fixture({read:async()=>{if(denied)throw Object.assign(new Error('denied'),{code:403});return {...ready(),pending:{status:'running'}}}})
 await h.client.open(profile);denied=true;await h.tick();assert.equal(h.state.plan,null);assert.equal(h.state.phase,'error')
})
