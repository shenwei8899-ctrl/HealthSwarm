import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {computed,effectScope,nextTick,reactive,ref,watch} from 'vue'
import {todayMealPlanState,createTodayMealPlan} from '../src/services/today-meal-plan.js'
import {detailGesture} from '../src/services/meal-detail-client.js'

const date='2026-10-30'
const profile={householdId:'family',selfMemberId:'self',members:[{id:'self',healthMemberId:'health-self'}]}
const absent=()=>({status:'absent',date,version:0,meals:[]})
const ready=()=>({status:'ready',date,version:1,meals:['breakfast','lunch','dinner'].map(meal_type=>({meal_type,source:{kind:'reference',id:'preview'},meal:{dishes:[{name:'菜品一'},{name:'菜品二'}]}}))})
function fixture({read=async()=>absent(),available=true,consent=false,unknown=false,accepted=true,invalid=false,pollLimit=45}={}){
 const state=todayMealPlanState(),calls=[],timers=new Map(),cache=new Map(),published=[]
 let owner='account:family',sequence=0,calendar=date
 const client=createTodayMealPlan({state,day:()=>calendar,context:()=>owner,read:async(...args)=>{calls.push(['read',...args]);return read(...args)},
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
 return {state,client,calls,timers,cache,published,setOwner:value=>owner=value,setDay:value=>calendar=value,async tick(){const next=timers.entries().next().value;assert.ok(next,'expected scheduled read');timers.delete(next[0]);await next[1]()}}
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

test('an incomplete historical dinner regenerates only dinner and keeps verified breakfast',async()=>{
 const plan=ready();plan.meals=plan.meals.slice(0,1);plan.needs_regeneration=['dinner'];plan.version=8
 const h=fixture({read:async()=>plan});await h.client.open(profile)
 assert.equal(h.state.plan.meals.length,1)
 const opened=h.calls.find(c=>c[0]==='open')
 assert.deepEqual(opened[3].meal_types,['dinner']);assert.equal(opened[3].daily_base_version,8)
 assert.equal(h.calls.filter(c=>c[0]==='submit').length,1)
 await h.tick();assert.equal(h.timers.size,1,'continue following the missing dinner while the task is active')
})

test('regenerating an old meal retains its authorized diners instead of changing to the default self',async()=>{
 const plan=ready();plan.meals=plan.meals.slice(0,1);plan.needs_regeneration=['dinner'];plan.regeneration_participants={dinner:['partner']}
 const h=fixture({read:async()=>plan})
 await h.client.open({...profile,members:[...profile.members,{id:'partner',healthMemberId:'health-partner'}]})
 const opened=h.calls.find(c=>c[0]==='open')
 assert.deepEqual(opened[3].participant_ids,['partner']);assert.equal(opened[1],'health-partner')
 assert.equal(h.state.plan.meals[0].meal_type,'breakfast')
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

function sheetFixture(){
 const source=readFileSync(new URL('../src/components/TodayMealPlanSheet.vue',import.meta.url),'utf8').split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm,'')
 const scope=effectScope(),props=reactive({open:true,profile,busy:false,unavailable:false}),events=[],calls=[],hooks={}
 const deps={computed,reactive,ref,watch,defineProps:()=>props,defineEmits:()=> (...args)=>events.push(args),
  onUnmounted:fn=>{hooks.unmount=fn},onHide:fn=>{hooks.hide=fn},onShow:fn=>{hooks.show=fn},
  todayMealPlanState,localDate:()=>date,
  detailGesture,
  createTodayMealPlan:()=>({open:()=>calls.push('open'),pause:()=>calls.push('pause'),clear:()=>calls.push('clear'),dispose:()=>calls.push('dispose')})}
 const view=scope.run(()=>new Function('deps',`const {${Object.keys(deps)}}=deps;${source};return {state,expanded,displayDate,loadingLabel,start,cancelTouch,end,detail,dish}`)(deps))
 return {view,props,events,calls,hooks,dispose(){hooks.unmount();scope.stop()}}
}

test('closing the actual sheet pauses instead of discarding its menu; removing the profile clears it',async()=>{
 const h=sheetFixture();try{
  h.view.state.plan=ready();h.props.open=false;await nextTick()
  assert.equal(h.calls.at(-1),'pause');assert.equal(h.view.state.plan.version,1)
  h.props.profile=null;await nextTick();assert.equal(h.calls.at(-1),'clear')
 }finally{h.dispose()}
})

test('the actual sheet exposes separate reading and generating copy with a compact local date',()=>{
 const h=sheetFixture();try{
  assert.equal(h.view.displayDate.value,'10月30日 · 周五')
  assert.equal(h.view.loadingLabel.value,'正在读取今日餐单')
  h.view.state.phase='generating';assert.equal(h.view.loadingLabel.value,'正在搭配今天的三餐')
 }finally{h.dispose()}
})

test('sheet actions cannot navigate an unverified preview, hidden sheet or closed sheet',async()=>{
 const h=sheetFixture(),item=ready().meals[0];try{
  h.view.detail(item);h.view.dish({item,dishIndex:0});assert.equal(h.events.length,0)
  h.view.state.verified=true;h.view.detail(item);h.view.dish({item,dishIndex:0});assert.equal(h.events.length,2)
  h.hooks.hide();h.view.detail(item);assert.equal(h.events.length,2)
  h.hooks.show();h.props.open=false;await nextTick();h.view.detail(item);assert.equal(h.events.length,2)
 }finally{h.dispose()}
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

test('card handlers enforce the preview interaction gate even when invoked directly',()=>{
 const source=readFileSync(new URL('../src/components/DailyMealPlanCard.vue',import.meta.url),'utf8').split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm,'')
 const props={interactive:false},events=[],deps={computed,allTypes:['breakfast','lunch','dinner'],defineProps:()=>props,defineEmits:()=> (...args)=>events.push(args)}
 const card=new Function('deps',`const {${Object.keys(deps)}}=deps;${source};return {openDetail,openDish}`)(deps),item=ready().meals[0]
 card.openDetail(item);card.openDish(item,0);assert.equal(events.length,0)
 props.interactive=true;card.openDetail(item);card.openDish(item,0)
 assert.deepEqual(events,[['detail',item],['dish',{item,dishIndex:0}]])
})
