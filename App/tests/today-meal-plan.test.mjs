import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {createRequire} from 'node:module'
import {computed,effectScope,nextTick,reactive,ref,watch} from 'vue'
import {todayMealPlanState,createTodayMealPlan} from '../src/services/today-meal-plan.js'
import {detailGesture} from '../src/services/meal-detail-client.js'
import {mealCandidates} from './fixtures/meal-candidates.mjs'
import {readDailyMealPlan} from '../src/services/daily-meal-plan.js'

const date='2026-10-30'
const profile={householdId:'family',selfMemberId:'self',members:[{id:'self',healthMemberId:'health-self'}]}
const absent=()=>({status:'absent',date,version:0,meals:[]})
const ready=()=>({status:'ready',date,version:1,meals:['breakfast','lunch','dinner'].map(meal_type=>({meal_type,source:{kind:'reference',id:'preview'},meal:{dishes:[{name:'菜品一'},{name:'菜品二'}]}}))})
const candidatePending=()=>({status:'reference_candidates',request_id:'original',thread_id:'original-thread',member_id:'health-self',
 selection:{mode:'reference',family_id:'family',participant_ids:['self'],plan_date:date,meal_types:['breakfast']}})
function fixture({read=async()=>absent(),available=true,consent=false,unknown=false,accepted=true,invalid=false,pollLimit,submittedState={},initialState,onPlan=()=>{}}={}){
 const state=initialState||todayMealPlanState(),calls=[],timers=new Map(),cache=new Map(),published=[],scheduledDelays=[]
 let owner='account:family',sequence=0,calendar=date,taskValue={},taskChanged=()=>{}
 const client=createTodayMealPlan({state,day:()=>calendar,context:()=>owner,read:async(...args)=>{calls.push(['read',...args]);return read(...args)},
  storage:{getStorageSync:k=>cache.get(k),setStorageSync:(k,v)=>cache.set(k,v)},
  schedule:(fn,ms)=>{scheduledDelays.push(ms);timers.set(++sequence,fn);return sequence},cancel:id=>timers.delete(id),pollLimit,onPlan:plan=>{published.push(plan);onPlan(plan)},
  createFlow:({storage,onChange})=>{
   calls.push(['flow']);taskChanged=onChange
   return {getState:()=>taskValue,
    async open(member,type,selection,options){calls.push(['open',member,type,selection,options]);storage.setStorageSync('task',{member});taskValue={available,consentOption:consent?{}:null,...(unknown?{requestId:'existing',submitUnknown:true}:{})};if(invalid){taskValue.invalidated=true;onChange(taskValue)}},
    async createEntry(){calls.push(['entry']);taskValue.entry={thread_id:'thread'}},
    async submit(query){calls.push(['submit',query]);taskValue={...taskValue,requestId:'new',status:accepted?'queued':'',submitUnknown:!accepted,...submittedState};return accepted},
    pause(){calls.push(['pause']);onChange(taskValue)},
   }
  }})
 return {state,client,calls,timers,cache,published,scheduledDelays,setTask(value){Object.assign(taskValue,value);taskChanged(taskValue)},setOwner:value=>owner=value,setDay:value=>calendar=value,async tick(){const next=timers.entries().next().value;assert.ok(next,'expected scheduled read');timers.delete(next[0]);await next[1]()}}
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

test('a failed saved task does not start another generation on the next visit',async()=>{
 const plan={...absent(),needs_regeneration:['breakfast','lunch','dinner'],pending:{status:'failed',request_id:'old'}}
 const h=fixture({read:async()=>plan})
 await h.client.open(profile)
 assert.equal(h.state.phase,'error');assert.equal(h.state.action,'regenerate')
 assert.match(h.state.notice,/失败|重新/)
 assert.equal(h.timers.size,0)
 assert.equal(h.calls.some(c=>c[0]==='flow'||c[0]==='submit'),false)
 await h.client.open(profile,{retryFailed:true})
 assert.equal(h.calls.filter(c=>c[0]==='submit').length,1)
})

for(const saved of [false,true])test(`a first-read candidate pending is terminal without an owned flow and ${saved?'preserves the saved menu':'never becomes a saved menu'}`,async()=>{
 const plan={...(saved?ready():absent()),pending:candidatePending()},h=fixture({read:async()=>plan})
 await h.client.open(profile)
 assert.equal(h.state.action,'candidates');assert.equal(h.state.pending.request_id,'original');assert.equal(h.timers.size,0)
 assert.equal(h.state.phase,saved?'ready':'error');assert.equal(h.state.verified,saved)
 assert.deepEqual(h.state.plan,saved?plan:null);assert.equal(h.calls.some(c=>c[0]==='flow'||c[0]==='submit'),false)
})

test('an external active task becoming candidate stops reads and keeps its bound continuation without posting',async()=>{
 let plan={...absent(),pending:{status:'running',request_id:'original'}},h=fixture({read:async()=>plan})
 await h.client.open(profile);assert.equal(h.timers.size,1)
 plan={...absent(),pending:candidatePending()};await h.tick()
 assert.equal(h.state.action,'candidates');assert.deepEqual(h.state.pending,candidatePending());assert.equal(h.timers.size,0)
 assert.equal(h.state.plan,null);assert.equal(h.published.length,0);assert.equal(h.calls.some(c=>c[0]==='flow'||c[0]==='submit'),false)
})

for(const change of [pending=>delete pending.selection,pending=>delete pending.member_id,pending=>delete pending.request_id,
 pending=>delete pending.thread_id,pending=>pending.selection.family_id='another-family',pending=>pending.selection.plan_date='2026-10-31',
 pending=>pending.selection.meal_types=['unknown']])test('an invalid candidate pending cannot create a generation: '+change.toString(),async()=>{
 const pending=candidatePending();change(pending)
 const h=fixture({read:()=>readDailyMealPlan('family',date,async()=>({data:{...absent(),pending}}))})
 await h.client.open(profile);assert.equal(h.state.phase,'error');assert.equal(h.state.plan,null)
 assert.equal(h.calls.some(c=>c[0]==='flow'||c[0]==='submit'),false);assert.equal(h.timers.size,0)
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

for(const immediate of [true,false])test(`a ${immediate?'fast':'polled'} candidate stops menu loading without publishing ready or generating again`,async()=>{
 const data=mealCandidates(date,'self',['breakfast','lunch','dinner']),task={status:'completed',result:{type:'business',kind:'meal_plan_candidates',data}}
 const h=fixture({submittedState:immediate?task:{}})
 await h.client.open(profile)
 if(!immediate){h.setTask(task);await h.tick()}
 assert.equal(h.state.phase,'error');assert.equal(h.state.plan,null);assert.equal(h.state.verified,false)
 assert.equal(h.state.action,'candidates');assert.match(h.state.notice,/待核对候选.*尚未确认/)
 assert.equal(h.state.pending.status,'reference_candidates');assert.equal(h.state.pending.request_id,'new')
 assert.equal(h.state.pending.thread_id,'thread');assert.equal(h.state.pending.member_id,'health-self')
 assert.equal(h.state.pending.selection.plan_date,date);assert.equal(h.published.length,0);assert.equal(h.timers.size,0)
 assert.equal(h.calls.filter(c=>c[0]==='submit').length,1)
})

test('a dinner candidate for another diner preserves saved breakfast and never advances to the missing lunch group',async()=>{
 const plan=ready();plan.meals=plan.meals.slice(0,1);plan.needs_regeneration=['dinner'];plan.regeneration_participants={dinner:['partner']}
 const data=mealCandidates(date,'partner',['dinner']),h=fixture({read:async()=>plan,
  submittedState:{status:'completed',result:{type:'business',kind:'meal_plan_candidates',data}}})
 await h.client.open({...profile,members:[...profile.members,{id:'partner',healthMemberId:'health-partner'}]})
 assert.deepEqual(h.state.plan,plan);assert.equal(h.state.plan.version,1);assert.equal(h.state.plan.meals.length,1)
 assert.equal(h.state.action,'candidates');assert.equal(h.state.pending.member_id,'health-partner')
 assert.deepEqual(h.state.pending.selection.meal_types,['dinner']);assert.equal(h.timers.size,0)
 assert.equal(h.calls.filter(c=>c[0]==='open').length,1);assert.equal(h.calls.filter(c=>c[0]==='submit').length,1)
 assert.equal(h.published.some(value=>value.meals.some(meal=>meal.meal_type==='dinner'||meal.meal_type==='lunch')),false)
})

test('the default five-minute budget follows the same active task past 45 polls and refreshes it after the finite limit',async()=>{
 let plan={...absent(),pending:{status:'running',request_id:'original'}}
 const h=fixture({read:async()=>plan});await h.client.open(profile)
 for(let count=0;count<45;count++)await h.tick()
 assert.equal(h.state.phase,'generating');assert.equal(h.state.label,'三餐仍在生成，请稍候')
 assert.equal(h.state.pending.request_id,'original');assert.equal(h.timers.size,1)
 for(let count=45;count<149;count++)await h.tick()
 assert.equal(h.state.phase,'generating');assert.equal(h.timers.size,1)
 await h.tick()
 assert.equal(h.state.phase,'error');assert.equal(h.state.action,'refresh');assert.equal(h.timers.size,0)
 assert.match(h.state.notice,/仍在处理中.*原任务/);assert.equal(h.state.pending.request_id,'original')
 assert.equal(h.calls.filter(c=>c[0]==='read').length,151)
 assert.deepEqual(h.scheduledDelays,Array(150).fill(2000))
 await h.client.open(profile,{readOnly:true});assert.equal(h.timers.size,1)
 plan=ready();await h.tick();assert.equal(h.state.phase,'ready');assert.equal(h.timers.size,0)
 assert.equal(h.calls.some(c=>c[0]==='flow'||c[0]==='submit'),false)
})

for(const result of ['failure','needs_input'])test(`a slow owned task ${result} stops despite its matching pending read model still running`,async()=>{
 let plan=absent();const h=fixture({read:async()=>plan});await h.client.open(profile)
 plan={...absent(),pending:{status:'running',request_id:'new'}}
 for(let count=0;count<46;count++)await h.tick()
 assert.equal(h.state.phase,'generating');assert.equal(h.state.label,'三餐仍在生成，请稍候')
 h.setTask(result==='failure'?{status:'failed',notice:'本次配餐已停止。'}:
  {status:'completed',result:{type:'needs_input',questions:['请确认忌口。']}})
 await h.tick()
 assert.equal(h.state.phase,'error');assert.equal(h.timers.size,0)
 if(result==='failure')assert.equal(h.state.notice,'本次配餐已停止。')
 else{assert.equal(h.state.action,'answer');assert.deepEqual(h.state.pending.questions,['请确认忌口。'])}
 assert.equal(h.calls.filter(c=>c[0]==='submit').length,1)
})

for(const result of ['failure','needs_input'])test(`an old owned ${result} cannot interrupt another device's accepted active task`,async()=>{
 let plan=absent();const h=fixture({read:async()=>plan});await h.client.open(profile)
 plan={...absent(),pending:{status:'running',request_id:'other-device'}}
 h.setTask(result==='failure'?{status:'failed',result:{type:'error',code:'planner_output_invalid'}}:
  {status:'completed',result:{type:'needs_input',questions:['旧任务问题']}})
 await h.tick()
 assert.equal(h.state.phase,'generating');assert.equal(h.state.pending.request_id,'other-device')
 assert.equal(h.state.action,'');assert.equal(h.timers.size,1)
 plan=ready();await h.tick()
 assert.equal(h.state.phase,'ready');assert.equal(h.state.pending,null);assert.equal(h.timers.size,0)
 assert.equal(h.calls.filter(c=>c[0]==='submit').length,1)
})

test('closing during a slow pending read rejects its late result and never restarts generation',async()=>{
 let delayed=false,resolve
 const plan={...absent(),pending:{status:'running',request_id:'original'}}
 const h=fixture({read:()=>delayed?new Promise(done=>resolve=done):Promise.resolve(plan)})
 await h.client.open(profile);for(let count=0;count<46;count++)await h.tick()
 delayed=true;const pending=h.tick();h.client.pause();resolve(ready());await pending
 assert.equal(h.state.plan,null);assert.equal(h.state.pending.request_id,'original')
 assert.equal(h.published.length,0);assert.equal(h.timers.size,0)
 assert.equal(h.calls.some(c=>c[0]==='flow'||c[0]==='submit'),false)
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

test('an incomplete historical dinner regenerates only dinner and keeps verified breakfast',async()=>{
 const plan=ready();plan.meals=plan.meals.slice(0,2);plan.needs_regeneration=['dinner'];plan.version=8
 const h=fixture({read:async()=>plan});await h.client.open(profile)
 assert.equal(h.state.plan.meals.length,2)
 const opened=h.calls.find(c=>c[0]==='open')
 assert.deepEqual(opened[3].meal_types,['dinner']);assert.equal(opened[3].daily_base_version,8)
 assert.equal(opened[4].fresh,true)
 assert.equal(h.calls.filter(c=>c[0]==='submit').length,1)
 await h.tick();assert.equal(h.timers.size,1,'continue following the missing dinner while the task is active')
})

test('opening a breakfast-only saved menu arranges the missing lunch and dinner without replacing breakfast',async()=>{
 let plan=ready();plan.meals=plan.meals.slice(0,1)
 const breakfast=plan.meals[0],h=fixture({read:async()=>plan})
 await h.client.open(profile)
 assert.equal(h.state.plan.meals[0],breakfast)
 assert.deepEqual(h.calls.find(c=>c[0]==='open')[3].meal_types,['lunch','dinner'])
 assert.equal(h.calls.filter(c=>c[0]==='submit').length,1)
 assert.match(h.calls.find(c=>c[0]==='submit')[1],/午餐、晚餐.*保留其他/)
 assert.doesNotMatch(h.calls.find(c=>c[0]==='submit')[1],/早餐/)
 plan={...ready(),version:2,meals:[breakfast,...ready().meals.slice(1)]};await h.tick()
 assert.deepEqual(h.state.plan.meals.map(meal=>meal.meal_type),['breakfast','lunch','dinner'])
 assert.equal(h.state.notice,'');assert.equal(h.timers.size,0)
})

test('read-only refresh of a partial menu exposes missing meals without submitting',async()=>{
 const plan=ready();plan.meals=plan.meals.slice(0,1)
 const h=fixture({read:async()=>plan});await h.client.open(profile,{readOnly:true})
 assert.equal(h.state.plan.meals.length,1);assert.equal(h.state.action,'regenerate')
 assert.equal(h.calls.some(c=>c[0]==='flow'),false)
})

for(const immediate of [true,false])test(`a ${immediate?'fast':'polled'} task follow-up survives a lagging daily read model`,async()=>{
 const task={status:'completed',result:{type:'needs_input',questions:['请确认今天需要避开的食材。']}}
 const h=fixture({submittedState:immediate?task:{}})
 await h.client.open(profile)
 if(!immediate){h.setTask(task);await h.tick()}
 assert.equal(h.state.phase,'error');assert.equal(h.state.action,'answer')
 assert.deepEqual(h.state.pending.questions,task.result.questions)
 assert.equal(h.state.pending.request_id,'new');assert.equal(h.state.pending.thread_id,'thread')
 assert.equal(h.state.pending.member_id,'health-self')
 assert.deepEqual(h.state.pending.selection.meal_types,['breakfast','lunch','dinner'])
 assert.equal(h.calls.filter(c=>c[0]==='submit').length,1);assert.equal(h.timers.size,0)
})

test('a definite task failure stops skeletons with the actual failure reason and no second submission',async()=>{
 const h=fixture({accepted:false,submittedState:{status:'failed',submitUnknown:false,notice:'营养助手资料尚未就绪。'}})
 await h.client.open(profile)
 assert.equal(h.state.phase,'error');assert.equal(h.state.notice,'营养助手资料尚未就绪。')
 assert.equal(h.state.action,'regenerate')
 assert.equal(h.calls.filter(c=>c[0]==='submit').length,1);assert.equal(h.timers.size,0)
})

for(const status of ['failed','completed'])test(`an accepted task with ${status} error stops immediately instead of showing empty skeletons`,async()=>{
 const h=fixture({submittedState:{status,result:{type:'error',code:'planner_output_invalid'}}})
 await h.client.open(profile)
 assert.equal(h.state.phase,'error');assert.match(h.state.notice,/餐单结果无法核对/)
 assert.equal(h.state.action,'regenerate')
 assert.equal(h.timers.size,0);assert.equal(h.calls.filter(c=>c[0]==='submit').length,1)
})

test('regenerating an old meal retains its authorized diners instead of changing to the default self',async()=>{
 const plan=ready();plan.meals=plan.meals.slice(0,1);plan.needs_regeneration=['dinner'];plan.regeneration_participants={dinner:['partner']}
 const h=fixture({read:async()=>plan})
 await h.client.open({...profile,members:[...profile.members,{id:'partner',healthMemberId:'health-partner'}]})
 const opened=h.calls.find(c=>c[0]==='open')
 assert.deepEqual(opened[3].participant_ids,['partner']);assert.equal(opened[1],'health-partner')
 assert.equal(h.state.plan.meals[0].meal_type,'breakfast')
})

test('different diner groups finish sequentially only after the prior group is saved',async()=>{
 let plan=ready();plan.meals=plan.meals.slice(0,1);plan.needs_regeneration=['dinner'];plan.regeneration_participants={dinner:['partner']}
 const h=fixture({read:async()=>plan}),family={...profile,members:[...profile.members,{id:'partner',healthMemberId:'health-partner'}]}
 await h.client.open(family)
 assert.deepEqual(h.calls.find(c=>c[0]==='open')[3].meal_types,['dinner'])
 h.setTask({status:'completed'});await h.tick()
 assert.equal(h.calls.filter(c=>c[0]==='submit').length,1,'completed task alone cannot repeat its still-missing meal')
 plan={...ready(),version:2,meals:[ready().meals[0],ready().meals[2]]}
 await h.tick()
 const opened=h.calls.filter(c=>c[0]==='open')
 assert.equal(opened.length,2);assert.deepEqual(opened[1][3].meal_types,['lunch'])
 assert.deepEqual(opened[1][3].participant_ids,['self'])
 assert.equal(h.calls.filter(c=>c[0]==='submit').length,2)
 plan={...ready(),version:3};await h.tick()
 assert.equal(h.state.plan.meals.length,3);assert.equal(h.state.action,'');assert.equal(h.timers.size,0)
})

for(const status of ['failed','rejected','cancelled','interrupted'])test(`a saved usable menu ignores historical ${status} without regenerating`,async()=>{
 const h=fixture({read:async()=>({...ready(),pending:{status}})})
 await h.client.open(profile);await h.client.open(profile)
 assert.equal(h.state.issue,false);assert.equal(h.state.notice,'');assert.equal(h.state.action,'')
 assert.equal(h.state.plan.meals.length,3);assert.equal(h.calls.some(c=>c[0]==='flow'),false)
})

test('a single transient poll failure recovers without interrupting the saved menu',async()=>{
 let reads=0
 const h=fixture({read:async()=>{
  reads++
  if(reads===2)throw Object.assign(new Error('temporary outage'),{code:503})
  return reads===1?{...ready(),pending:{status:'running'}}:ready()
 }})
 await h.client.open(profile);await h.tick()
 assert.equal(h.state.plan.meals.length,3);assert.equal(h.state.issue,false);assert.equal(h.timers.size,1)
 await h.tick()
 assert.equal(h.state.notice,'');assert.equal(h.state.action,'');assert.equal(h.timers.size,0)
 assert.equal(h.calls.some(c=>c[0]==='submit'),false)
})

test('three consecutive transient poll failures stop with a read-only refresh action',async()=>{
 let reads=0
 const h=fixture({read:async()=>{
  if(reads++)throw Object.assign(new Error('offline'),{code:'NETWORK_ERROR'})
  return {...ready(),pending:{status:'running'}}
 }})
 await h.client.open(profile);await h.tick();await h.tick();await h.tick()
 assert.equal(h.state.phase,'ready');assert.equal(h.state.action,'refresh');assert.equal(h.timers.size,0)
 assert.equal(h.state.plan.meals.length,3)
 await h.client.open(profile,{readOnly:true})
 assert.equal(h.state.plan.meals.length,3);assert.equal(h.calls.some(c=>c[0]==='flow'),false)
})

test('poll exhaustion can resume the same running task by reading instead of resubmitting',async()=>{
 let plan={...ready(),pending:{status:'running'}}
 const h=fixture({read:async()=>plan,pollLimit:1})
 await h.client.open(profile);await h.tick()
 assert.equal(h.state.action,'refresh');assert.equal(h.state.phase,'ready')
 await h.client.open(profile,{readOnly:true})
 assert.equal(h.timers.size,1);assert.equal(h.state.action,'')
 plan=ready();await h.tick()
 assert.equal(h.state.notice,'');assert.equal(h.calls.some(c=>c[0]==='flow'),false)
})

test('a refresh of an absent or failed plan never submits a generation',async()=>{
 for(const plan of [absent(),{...absent(),pending:{status:'failed'}}]){
  const h=fixture({read:async()=>plan})
  await h.client.open(profile,{readOnly:true})
  assert.equal(h.state.phase,'error');assert.equal(h.state.action,'regenerate')
  assert.equal(h.calls.some(c=>c[0]==='flow'),false)
 }
})

test('a pending follow-up exposes its actual question and bound continuation without generating',async()=>{
 const pending={status:'needs_input',request_id:'original',selection:{family_id:'family',plan_date:date},questions:['请明确本次调整的忌口。']}
 for(const plan of [ready(),absent()]){
  const h=fixture({read:async()=>({...plan,pending})})
  await h.client.open(profile)
  assert.equal(h.state.action,'answer');assert.deepEqual(h.state.pending,pending)
  assert.equal(h.calls.some(c=>c[0]==='flow'),false)
 }
})

test('a refresh cannot retain a menu across a family, profile version or account change',async()=>{
 for(const change of ['family','version','account']){
  let denied=false
  const h=fixture({read:async()=>{if(denied)throw Object.assign(new Error('offline'),{code:503});return ready()}})
  await h.client.open(profile);denied=true
  if(change==='account')h.setOwner('another-account')
  await h.client.open({...profile,...(change==='family'?{householdId:'another-family'}:change==='version'?{familyVersion:2}:{})},{readOnly:true})
  assert.equal(h.state.plan,null);assert.equal(h.state.phase,'error')
 }
})

test('an authoritative refusal on refresh clears the last verified private menu immediately',async()=>{
 let denied=false
 const h=fixture({read:async()=>{if(denied)throw Object.assign(new Error('denied'),{code:403});return ready()}})
 await h.client.open(profile);denied=true
 await h.client.open(profile,{readOnly:true})
 assert.equal(h.state.plan,null);assert.equal(h.state.pending,null);assert.equal(h.timers.size,0)
})

test('ordinary reopening previews the same scoped menu but waits for verification before publishing again',async()=>{
 let reads=0,resolve
 const h=fixture({read:()=>++reads===1?Promise.resolve(ready()):new Promise(done=>resolve=done)})
 await h.client.open(profile);h.client.pause()
 const opening=h.client.open(profile)
 assert.equal(h.state.plan.version,1);assert.equal(h.state.phase,'ready')
 assert.equal(h.state.verified,false);assert.equal(h.state.checking,true);assert.equal(h.published.length,1)
 resolve({...ready(),version:2});await opening
 assert.equal(h.state.verified,true);assert.equal(h.state.checking,false);assert.equal(h.state.plan.version,2)
 assert.equal(h.published.length,2);assert.equal(h.calls.some(c=>c[0]==='flow'),false)
})

test('a failed reopen retains a read-only preview until a successful refresh verifies it',async()=>{
 let failed=false
 const h=fixture({read:async()=>{if(failed)throw Object.assign(new Error('offline'),{code:503});return ready()}})
 await h.client.open(profile);failed=true;await h.client.open(profile)
 assert.equal(h.state.plan.version,1);assert.equal(h.state.verified,false);assert.equal(h.state.checking,false)
 assert.equal(h.state.action,'refresh');assert.match(h.state.notice,/仅供预览/)
 failed=false;await h.client.open(profile,{readOnly:true})
 assert.equal(h.state.verified,true);assert.equal(h.state.notice,'');assert.equal(h.calls.some(c=>c[0]==='flow'),false)
})

for(const change of ['account','family','member','version','date'])test(`ordinary reopen cannot preview a different ${change}`,async()=>{
 let resolve,reads=0
 const h=fixture({read:()=>++reads===1?Promise.resolve(ready()):new Promise(done=>resolve=done)})
 await h.client.open(profile)
 if(change==='account')h.setOwner('new-account')
 if(change==='date')h.setDay('2026-10-31')
 const opening=h.client.open({...profile,...(change==='family'?{householdId:'new-family'}:change==='member'?{selfMemberId:'partner'}:change==='version'?{familyVersion:2}:{})},{readOnly:true})
 assert.equal(h.state.plan,null);assert.equal(h.state.verified,false);assert.equal(h.state.phase,'loading')
 h.client.clear();resolve(ready());await opening
 assert.equal(h.state.plan,null);assert.equal(h.published.length,1)
})

test('closing while a cached menu is being verified prevents its late result from publishing',async()=>{
 let reads=0,resolve
 const h=fixture({read:()=>++reads===1?Promise.resolve(ready()):new Promise(done=>resolve=done)})
 await h.client.open(profile)
 const opening=h.client.open(profile);h.client.pause();resolve({...ready(),version:2});await opening
 assert.equal(h.state.plan.version,1);assert.equal(h.state.verified,false);assert.equal(h.published.length,1)
 h.client.dispose();assert.equal(h.state.plan,null)
})

test('an authoritative absent menu replaces its preview without restoring it or generating on refresh',async()=>{
 let plan=ready();const h=fixture({read:async()=>plan})
 await h.client.open(profile);plan=absent();await h.client.open(profile,{readOnly:true})
 assert.equal(h.state.plan,null);assert.equal(h.state.verified,false);assert.equal(h.state.action,'regenerate')
 assert.equal(h.calls.some(c=>c[0]==='flow'),false)
})

function contentFixture(state=reactive(todayMealPlanState())){
 const source=readFileSync(new URL('../src/components/TodayMealPlanContent.vue',import.meta.url),'utf8').split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm,'')
 const props=reactive({state,busy:false,interactive:true}),events=[]
 const deps={computed,defineProps:()=>props,defineEmits:()=> (...args)=>events.push(args),localDate:()=>date}
 const view=new Function('deps',`const {${Object.keys(deps)}}=deps;${source};return {mealEntries,missingMeals,displayDate,loadingLabel,detail,dish,act}`)(deps)
 return {view,props,events}
}

function sheetFixture({clientOptions,readOnly=false}={}){
 const source=readFileSync(new URL('../src/components/TodayMealPlanSheet.vue',import.meta.url),'utf8').split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm,'')
 const scope=effectScope(),state=reactive(todayMealPlanState()),props=reactive({open:true,state,profile,busy:false,interactive:true,unavailable:false,readOnly}),events=[],calls=[],hooks={}
 const clientFixture=clientOptions?fixture({...clientOptions,initialState:state}):null
 const client=clientFixture?.client||{open:()=>calls.push('open'),pause:()=>calls.push('pause'),clear:()=>calls.push('clear'),dispose:()=>calls.push('dispose')}
 const load=()=>{if(!props.profile||props.unavailable){client.clear();return}if(!props.open){client.pause();return}void client.open(props.profile,{readOnly:props.readOnly})}
 const handle=(...args)=>{if(args[0]!=='action'){events.push(args);return}if(['answer','candidates'].includes(state.action))events.push(['continue',state.pending]);else void client.open(props.profile,{readOnly:props.readOnly||state.action==='refresh'})}
 const deps={computed,ref,watch,defineProps:()=>props,defineEmits:()=>handle,localDate:()=>date,detailGesture}
 const view=scope.run(()=>{
  watch(()=>[props.open,props.profile,props.unavailable,props.readOnly],load,{immediate:true})
  return new Function('deps',`const {${Object.keys(deps)}}=deps;${source};return {expanded,displayDate,start,cancelTouch,end,detail,dish,act}`)(deps)
 })
 hooks.unmount=()=>client.dispose()
 return {view:{...view,state,loadingLabel:computed(()=>state.label)},props,events,calls,hooks,clientFixture,dispose(){hooks.unmount();scope.stop()}}
}

test('actual sheet consumes the saved three-meal plan and opens the selected real meal',async()=>{
 let plan=absent()
 const h=sheetFixture({clientOptions:{read:async()=>plan}})
 try{
  await new Promise(done=>setImmediate(done))
  assert.equal(h.view.state.phase,'generating')
  assert.equal(h.clientFixture.calls.filter(c=>c[0]==='submit').length,1)
  plan=ready();await h.clientFixture.tick();await nextTick()
  assert.equal(h.view.state.phase,'ready');assert.equal(h.view.state.verified,true)
  assert.deepEqual(h.view.state.plan.meals.map(meal=>meal.meal_type),['breakfast','lunch','dinner'])
  assert.equal(h.view.state.plan.meals.every(meal=>meal.meal.dishes.length===2),true)
  h.view.detail(plan.meals[1])
  assert.deepEqual(h.events.at(-1),['detail',plan.meals[1]])
  assert.equal(h.clientFixture.timers.size,0)
 }finally{h.dispose()}
})

test('actual sheet preserves a task follow-up and continues it without another generation',async()=>{
 const h=sheetFixture({clientOptions:{submittedState:{status:'completed',result:{type:'needs_input',questions:['请确认忌口。']}}}})
 try{
  await new Promise(done=>setImmediate(done));await nextTick()
  assert.equal(h.view.state.phase,'error');assert.equal(h.view.state.action,'answer')
  h.view.act()
  assert.equal(h.events.at(-1)[0],'continue');assert.equal(h.events.at(-1)[1].request_id,'new')
  assert.deepEqual(h.events.at(-1)[1].questions,['请确认忌口。'])
  assert.equal(h.clientFixture.calls.filter(c=>c[0]==='submit').length,1)
 }finally{h.dispose()}
})

test('the actual menu opens a bound candidate in chat and its read-only entry never repeats a generation POST',async()=>{
 const h=sheetFixture({clientOptions:{submittedState:{status:'completed',result:{type:'business',kind:'meal_plan_candidates',data:mealCandidates(date,'self',['breakfast','lunch','dinner'])}}}})
 try{
  await new Promise(done=>setImmediate(done));await nextTick();h.view.act()
  assert.equal(h.events.at(-1)[0],'continue');assert.equal(h.events.at(-1)[1].status,'reference_candidates')
  assert.equal(h.events.at(-1)[1].request_id,'new');assert.equal(h.clientFixture.calls.filter(c=>c[0]==='submit').length,1)
 }finally{h.dispose()}
 const readOnly=sheetFixture({readOnly:true,clientOptions:{read:async()=>absent()}})
 try{
  await new Promise(done=>setImmediate(done))
  readOnly.view.act();await new Promise(done=>setImmediate(done))
  assert.equal(readOnly.clientFixture.calls.some(c=>c[0]==='flow'||c[0]==='submit'),false)
  assert.equal(readOnly.view.state.plan,null);assert.equal(readOnly.view.state.verified,false)
 }finally{readOnly.dispose()}
})

test('actual sheet ends timed-out skeletons and refreshes the existing task without another POST',async()=>{
 let plan={...absent(),pending:{status:'running',request_id:'original'}}
 const h=sheetFixture({clientOptions:{read:async()=>plan,pollLimit:1}})
 try{
  await new Promise(done=>setImmediate(done));await h.clientFixture.tick();await nextTick()
  assert.equal(h.view.state.phase,'error');assert.equal(h.view.state.action,'refresh')
  assert.equal(h.clientFixture.timers.size,0)
  h.view.act();await new Promise(done=>setImmediate(done))
  assert.equal(h.clientFixture.timers.size,1)
  plan=ready();await h.clientFixture.tick();await nextTick()
  assert.equal(h.view.state.phase,'ready');assert.equal(h.view.state.plan.meals.length,3)
  assert.equal(h.clientFixture.calls.some(c=>c[0]==='submit'),false)
 }finally{h.dispose()}
})

test('closing the actual sheet pauses instead of discarding its menu; removing the profile clears it',async()=>{
 const h=sheetFixture();try{
  h.view.state.plan=ready();h.view.state.phase='generating';h.props.open=false;await nextTick()
  assert.equal(h.view.state.plan.version,1);assert.equal(h.view.state.phase,'generating')
  h.props.open=true;await nextTick();assert.equal(h.view.state.phase,'generating')
 }finally{h.dispose()}
})

test('the actual sheet exposes separate reading and generating copy with a compact local date',()=>{
 const h=sheetFixture();try{
  assert.equal(h.view.displayDate.value,'10月30日 · 周五')
  assert.equal(h.view.loadingLabel.value,'正在读取今日餐单')
  h.view.state.phase='generating';h.view.state.label='正在搭配今天的三餐';assert.equal(h.view.loadingLabel.value,'正在搭配今天的三餐')
  h.view.state.label='三餐仍在生成，请稍候';assert.equal(h.view.loadingLabel.value,'三餐仍在生成，请稍候')
 }finally{h.dispose()}
})

test('sheet actions cannot navigate an unverified preview, inactive page or closed sheet',async()=>{
 const h=sheetFixture(),item=ready().meals[0];try{
  h.view.detail(item);h.view.dish({item,dishIndex:0});assert.equal(h.events.length,0)
  h.view.state.verified=true;h.view.detail(item);h.view.dish({item,dishIndex:0});assert.equal(h.events.length,2)
  h.props.interactive=false;h.view.detail(item);h.view.act();assert.equal(h.events.length,2)
  h.props.interactive=true;h.props.open=false;await nextTick();h.view.detail(item);h.view.act();assert.equal(h.events.length,2)
 }finally{h.dispose()}
})

test('shared content gates preview interactions and busy recovery actions',()=>{
 const h=contentFixture(),item=ready().meals[0]
 h.view.detail(item);h.view.dish({item,dishIndex:0});assert.equal(h.events.length,0)
 h.props.state.verified=true;h.view.detail(item);h.view.dish({item,dishIndex:0});assert.equal(h.events.length,2)
 h.props.busy=true;h.view.act();assert.equal(h.events.length,2)
 h.props.busy=false;h.view.act();assert.deepEqual(h.events.at(-1),['action'])
 h.props.interactive=false;h.view.detail(item);h.view.act();assert.equal(h.events.length,3)
})

test('header gestures expand, collapse and close while horizontal gestures are ignored',async()=>{
 const h=sheetFixture();try{
  const swipe=(x,y)=>{h.view.start({touches:[{clientX:0,clientY:100}]});h.view.end({changedTouches:[{clientX:x,clientY:100+y}]})}
  h.view.start({touches:[{clientX:0,clientY:100}]});h.view.cancelTouch();h.view.end({changedTouches:[{clientX:0,clientY:50}]});assert.equal(h.view.expanded.value,false)
  swipe(90,-40);assert.equal(h.view.expanded.value,false)
  swipe(0,-40);assert.equal(h.view.expanded.value,true)
  swipe(0,90);assert.equal(h.view.expanded.value,false);assert.equal(h.events.length,0)
  swipe(0,90);assert.deepEqual(h.events,[['close']])
  h.props.open=false;await nextTick();h.view.expanded.value=true;h.props.open=true;await nextTick()
  assert.equal(h.view.expanded.value,false)
 }finally{h.dispose()}
})

test('WeChat sheet controls receive taps independently from the header drag regions',()=>{
 const require=createRequire(import.meta.url)
 const weixinRequire=createRequire(require.resolve('@dcloudio/uni-mp-weixin/package.json'))
 const {compile}=weixinRequire('@dcloudio/uni-mp-compiler')
 const source=readFileSync(new URL('../src/components/TodayMealPlanSheet.vue',import.meta.url),'utf8')
 const assets=[]
 compile(source.match(/<template>([\s\S]*?)<\/template>/)[1],{
  filename:'components/TodayMealPlanSheet.wxml',
  miniProgram:{directive:'wx:',event:{key:true},class:{array:true},
   slot:{fallbackContent:false,dynamicSlotNames:true},emitFile:asset=>assets.push(asset)},
 })
 const wxml=String(assets[0].source)
 const tag=name=>wxml.match(new RegExp(`<[^>]+class="${name}"[^>]*>`))?.[0]||''
 for(const name of ['tm-header','tm-controls']){
  assert.ok(tag(name),`${name} must exist`)
  assert.doesNotMatch(tag(name),/\b(?:bind|catch)touch/)
 }
 for(const name of ['tm-handle','tm-heading']){
  for(const event of ['touchstart','touchend','touchcancel'])assert.match(tag(name),new RegExp(`\\bbind${event}=`))
 }
 for(const name of ['tm-expand','tm-close'])assert.match(tag(name),/\bbindtap=/)
})

test('card handlers enforce the preview interaction gate even when invoked directly',()=>{
 const source=readFileSync(new URL('../src/components/DailyMealPlanCard.vue',import.meta.url),'utf8').split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm,'')
 const props={interactive:false},events=[],deps={computed,allTypes:['breakfast','lunch','dinner'],defineProps:()=>props,defineEmits:()=> (...args)=>events.push(args)}
 const card=new Function('deps',`const {${Object.keys(deps)}}=deps;${source};return {openDetail,openDish}`)(deps),item=ready().meals[0]
 card.openDetail(item);card.openDish(item,0);assert.equal(events.length,0)
 props.interactive=true;card.openDetail(item);card.openDish(item,0)
 assert.deepEqual(events,[['detail',item],['dish',{item,dishIndex:0}]])
})

test('compact meal entries always keep three labels and disable missing or empty meals',()=>{
 const h=contentFixture()
 assert.deepEqual(h.view.mealEntries.value.map(meal=>meal.name),['早餐','午餐','晚餐'])
 assert.deepEqual(h.view.mealEntries.value.map(meal=>meal.icon),['sunrise','sun','moon-stars'])
 assert.ok(h.view.mealEntries.value.every(meal=>!meal.item))
 const plan=ready();plan.meals=[plan.meals[0]]
 h.props.state.plan=plan
 assert.ok(h.view.mealEntries.value[0].item)
 assert.equal(h.view.missingMeals.value,'午餐、晚餐')
 h.props.state.plan.meals[0].meal.dishes=[]
 assert.equal(h.view.mealEntries.value[0].item,undefined)
 h.props.state.verified=true;h.view.detail(undefined)
 assert.equal(h.events.length,0)
})
