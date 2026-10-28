import {selectChatPrompts} from '../src/services/chat-prompts.js'
import {referenceSelection as chooseReference,isReferencePlan} from '../src/services/reference-meal-plan.js'
import { addressNavigation } from './address-test-helpers.mjs'
import {readyPreparation} from './fixtures/preparation-ready.mjs'
import {preparationReady as checkPreparation} from '../src/services/preparation-ready.js'
import test from 'node:test'
import {parseChatMealIntent} from '../src/utils/chat-meal-intent.js'
import {loadChatMealPlan} from '../src/services/chat-meal-plan.js'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { ref,reactive,computed,nextTick,watch,effectScope } from 'vue'
import {chatTimestamp,chatBusinessDate} from '../src/services/cloud-chat.js'
import {chatPresentation} from '../src/services/chat-presentation.js'
import { createHealthTaskFlow,HEALTH_TEXT_TASKS } from '../src/services/health-task-flow.js'
import { photoState,createMealPhotoClient } from '../src/services/meal-photo-client.js'
import { createCloudMealSaver,mealDay,personalMeal,mealLabels } from '../src/services/cloud-meals.js'
import { mealInput } from '../src/services/health-meal-input.js'
import { dailyArrangementState,createDailyArrangementClient } from '../src/services/daily-arrangement-client.js'
import {readDailyMealPlan,mealQuestionAction} from '../src/services/daily-meal-plan.js'
const jsonClone=v=>v===undefined?undefined:JSON.parse(JSON.stringify(v))
const member='11111111-1111-4111-8111-111111111111',thread='22222222-2222-4222-8222-222222222222',requestId='33333333-3333-4333-8333-333333333333'
function mount(file,fields,extras={}){
 const hooks={},deps={parseChatMealIntent,loadChatMealPlan,selectChatPrompts,rememberChatEntry:()=>{},ref,reactive,computed,nextTick,watch,chatTimestamp,chatBusinessDate,chatPresentation,defineProps:()=>({route:{}}),onMounted:fn=>hooks.mount=fn,onShow:fn=>hooks.show=fn,onHide:fn=>hooks.hide=fn,onUnload:fn=>hooks.unload=fn,onUnmounted:fn=>hooks.unmount=fn,...extras}
 if(file==='CloudMealPurchase.vue') Object.assign(deps,addressNavigation(deps.storageContext,deps.uni))
 const source=readFileSync(new URL('../src/components/'+file,import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
 const scope=effectScope();const page=scope.run(()=>new Function('deps',`const {${Object.keys(deps).join(',')}}=deps;${source};return {${fields}}`)(deps))
 return {...page,hooks,dispose(){hooks.unmount?.();hooks.unload?.();scope.stop()}}
}
function storage(){const m=new Map();return {getStorageSync:k=>jsonClone(m.get(k)),setStorageSync:(k,v)=>m.set(k,jsonClone(v)),getStorageInfoSync:()=>({keys:[...m.keys()]})}}

test('confirmed dishes save without an extra nutrition switch and preserve unknown nutrition',async()=>{
 const cache=storage(),calls=[];let serial=0,submitted=null
 const send=async options=>{
  calls.push(options)
  if(options.path.endsWith('/manual-drafts')){submitted=options.data.meal;return {data:{id:'draft',member_id:member,version:1}}}
  if(options.path.endsWith('/calculate'))return {data:{draft_version:1,calculation_id:'calculation',totals:{kcal:null},complete:false}}
  if(options.path.endsWith('/confirm')){assert.equal(options.data.accept_incomplete,true);return {data:{review_status:'confirmed',target_ids:['record']}}}
  if(options.path.includes('/diet-logs/page'))return {data:{records:[{id:'record',source_version:1,totals:{kcal:null},items:submitted.items}],next_offset:null}}
  throw new Error(options.path)
 }
 const p=mount('CloudMealCapture.vue','load,people,dishes,save,saved,canSave',{
  photoState,createMealPhotoClient:()=>({open:async()=>{},discard(){}}),
  createCloudMealSaver:()=>createCloudMealSaver({send,storage:cache,revision:()=>1,newId:()=>String(++serial)}),
  personalMeal,mealLabels,mealDay,scopedStorage:cache,storageContext:()=> 'scope',getSession:()=>({householdId:'family'}),
  request:async()=>({data:[{id:member,display_name:'我',scopes:['diet_edit']}]}),commerce:{},uni:{},
 })
 try{
  await p.load();p.dishes.value=[{name:'香菇鸡肉'},{name:'青菜'}]
  await p.save();assert.equal(calls.length,0,'unconfirmed dishes still cannot save')
  p.people.value[0].dishes=['香菇鸡肉'];p.people.value[0].portion='一般'
  assert.equal(p.canSave.value,true);await p.save()
  assert.equal(p.saved.value.rows[0].record.totals.kcal,null)
  assert.equal(submitted.items[0].grams,null);assert.equal(submitted.items[0].share_ratio,null)
  assert.equal(submitted.items[0].portion_source,'unknown');assert.equal(submitted.items.length,1)
  assert.ok(calls.some(c=>c.path.endsWith('/confirm')))
 }finally{p.dispose()}
})

for(const file of ['CloudMealDetail.vue','CloudRecipe.vue'])test(`${file} rereads after same-account foreground and hides revoked content`,async()=>{
 let denied=false,reads=0
 const p=mount(file,'load,error,'+(file==='CloudRecipe.vue'?'dish':'meal'),{storageContext:()=> 'same-account',getSession:()=>({householdId:'family'}),defineProps:()=>({route:{arrangement:'arrangement',date:'2026-10-22',version:1,meal:'lunch',dish:'dish'}}),
  dailyArrangementState,scopedStorage:storage(),newHealthRequestId:()=>requestId,loadCloudProfile:async()=>({}),createDailyArrangementClient:()=>({pause(){},reset(){},dispose(){}}),
  request:async()=>{reads++;if(denied)throw Object.assign(new Error('授权撤回'),{code:403});return {data:{arrangement_id:'arrangement',version:1,meal:{type:'lunch',dishes:[{id:'dish',steps:['合成做法']}],memberNotes:[]}}}}
 })
 await p.load();denied=true;p.hooks.show();await new Promise(resolve=>setImmediate(resolve))
 assert.equal(reads,2);assert.equal((p.dish||p.meal).value,null);assert.match(p.error.value,/授权/);p.dispose()
})

test('diet correction authorization loss removes the record and its editable private copy',async()=>{
 const p=mount('HealthMealJournal.vue','save,detail,meal,reason,records,error,editing',{
  sessionRevision:()=>1,scopedStorage:storage(),newHealthRequestId:()=>requestId,mealDay,mealLabels,readDietRecord:async()=>{},feedbackUrl:()=>'',portionNote:()=>'',mealInput,
  request:async()=>{throw Object.assign(new Error('授权撤回'),{code:403})},
 })
 p.detail.value={id:'record',member_id:member,source_version:1,snapshot:{meal:{items:[]}}};p.meal.value={meal_type:'lunch',eaten_at:'2026-10-22T12:00:00+08:00',items:[]};p.reason.value='合成更正';p.records.value=[p.detail.value];p.editing.value=true
 await p.save();assert.equal(p.detail.value,null);assert.equal(p.meal.value,null);assert.deepEqual(p.records.value,[]);assert.equal(p.editing.value,false);p.dispose()
})

test('member change authorization loss also removes the independently displayed meal snapshot',async()=>{
 const p=mount('CloudMealDetail.vue','load,confirm,meal,error',{
  storageContext:()=> 'same-account',getSession:()=>({householdId:'family'}),defineProps:()=>({route:{arrangement:'arrangement',date:'2026-10-22',version:1,meal:'lunch'}}),
  dailyArrangementState,scopedStorage:storage(),newHealthRequestId:()=>requestId,loadCloudProfile:async()=>({}),
  createDailyArrangementClient:({state})=>({load:async()=>{state.arrangement={id:'arrangement',version:1}},changeMembers:async()=>{state.arrangement=null;state.error='授权撤回'},pause(){},reset(){},dispose(){}}),
  request:async()=>({data:{arrangement_id:'arrangement',version:1,meal:{type:'lunch',memberNotes:[],dishes:[]}}}),
 })
 await p.load();await p.confirm([member]);assert.equal(p.meal.value,null);assert.match(p.error.value,/授权/);p.dispose()
})

function gramsEditor(coarse) {
 const source=readFileSync(new URL('../src/components/HealthMealEditor.vue',import.meta.url),'utf8')
 const attributes=source.match(/实际克数[\s\S]*?<input\b([^>]+)>/)[1]
 const model=attributes.match(/v-model="([^"]+)"/),display=attributes.match(/:value="([^"]+)"/)
 const handler=attributes.match(/@input="([^"]+)"/)[1]
 return mount('HealthMealEditor.vue',`display:(item)=>(${display?.[1]||model[1]}),input:(item,value)=>{const $event={detail:{value}};${model?model[1]+'=value;':''}${handler}}`,{
  defineProps:()=>({coarse,disabled:false,meal:{items:[]}}),defineEmits:()=>()=>{},
 })
}

test('actual grams displays the eaten weight instead of a hidden whole-dish weight',()=>{
 const p=gramsEditor(true)
 assert.equal(Number(p.display({grams:200,share_ratio:0.5})),100)
 assert.equal(p.display({grams:200,share_ratio:null}),'')
 p.dispose()
})

for(const ratio of [0.5,null])test(`actual grams entry replaces the hidden ${ratio} share with a whole personal portion`,()=>{
 const p=gramsEditor(true),item={grams:200,share_ratio:ratio,portion_source:'unknown'}
 p.input(item,'120')
 const sent=mealInput({items:[item]}).items[0]
 assert.equal(sent.share_ratio,1)
 assert.equal(Number(sent.grams)*sent.share_ratio,120)
 assert.equal(sent.portion_source,'manual')
 p.input(item,'')
 const cleared=mealInput({items:[item]}).items[0]
 assert.equal(cleared.grams,null)
 assert.equal(cleared.share_ratio,null)
 p.dispose()
})

test('whole-dish grams editing keeps the separately visible personal share',()=>{
 const p=gramsEditor(false),item={grams:200,share_ratio:0.5,portion_source:'estimated'}
 assert.equal(Number(p.display(item)),200)
 p.input(item,'120')
 assert.equal(item.share_ratio,0.5)
 assert.equal(Number(item.grams)*item.share_ratio,60)
 p.dispose()
})

function feedbackPages({emptyMiddle=false,repeatOffset=false}={}) {
 const rows=Array.from({length:101},(_,i)=>({id:`meal-${i}`,source_version:1,snapshot:{meal:{
  eaten_at:new Date(Date.UTC(2026,9,21-i,4)).toISOString(),meal_type:'dinner',items:[],
 }}}))
 const calls=[],page=mount('CloudDietFeedback.vue','load,date,current,error,records,analyses',{
  mealDay,mealLabels,feedbackUrl:()=>'',storageContext:()=> 'scope',request:async options=>{
   calls.push(jsonClone(options))
   if(options.path.endsWith('/members'))return {data:[{id:member,scopes:['diet_edit']}]}
   if(options.path.endsWith('/diet-logs'))return {data:rows.slice(0,100)}
   if(options.path.includes('/diet-logs/page')){
    const offset=Number(new URL('https://synthetic.invalid'+options.path).searchParams.get('offset'))
    return {data:{records:emptyMiddle&&offset===50?[]:rows.slice(offset,offset+50),next_offset:repeatOffset?offset:offset+50<rows.length?offset+50:null}}
   }
   if(options.path.endsWith('/diet-analysis'))return {data:{source:{record_id:options.data.record_id},findings:['合成反馈']}}
   throw Error(options.path)
  },
 })
 page.date.value=mealDay(rows[100].snapshot.meal.eaten_at)
 return {page,calls,rows}
}

for(const emptyMiddle of [false,true])test(`feedback pages find an older saved meal beyond the legacy 100-row window (empty page: ${emptyMiddle})`,async()=>{
 const {page,calls}=feedbackPages({emptyMiddle})
 await page.load()
 assert.equal(page.error.value,'')
 assert.deepEqual(page.current.value.map(r=>r.id),['meal-100'])
 assert.equal(page.analyses.value.length,1)
 assert.deepEqual(calls.filter(o=>o.path.includes('/diet-logs/page')).map(o=>Number(new URL('https://synthetic.invalid'+o.path).searchParams.get('offset'))),[0,50,100])
 assert.ok(!calls.some(o=>o.path.endsWith('/diet-logs')))
 page.dispose()
})

test('feedback pagination reports a stalled cursor instead of claiming no saved meal',async()=>{
 const {page,calls}=feedbackPages({repeatOffset:true})
 await page.load()
 assert.ok(page.error.value.includes('分页'))
 assert.ok(!calls.some(o=>o.path.endsWith('/diet-analysis')))
 page.dispose()
})

function chat(){let submits=0,exists=false,invalid=false;const saved=storage(),calls=[]
 const send=async o=>{calls.push(jsonClone(o));if(o.path.includes('/daily-meal-plans/'))return {data:{status:'absent',date:o.path.split('/').at(-1),version:0,meals:[]}};if(o.path.includes('/reference-meal-plans/'))return {data:{status:'absent'}};if(o.path.includes('/daily-arrangements/'))return {data:readyPreparation('2026-10-20').arrangement};if(o.path.includes('/consultations?'))return {data:{items:[{thread_id:thread,member_id:member,agent_slug:'health-consultation',business_date:'2026-10-20'}],has_more:false,next_offset:null}};if(o.path.includes('/requests?agent_slug='))return {data:{requests:[]}};if(o.path.endsWith('/members'))return {data:[{id:member,is_owner:true}]};if(o.path.endsWith('/readiness'))return {data:{capabilities:{member_id:member},entries:[{entry_type:'consultation',status:'available'}]}};if(o.path.endsWith('/daily-conversations'))return {data:{days:[{date:'2026-10-20',thread_id:thread}]}};if(o.path==='/api/agent/runs'){if(++submits===1)throw Object.assign(new Error('timeout'),{code:503});exists=true;return {data:{request_id:requestId,thread_id:thread}}}if(o.path.includes('/tasks/')){if(invalid)throw Object.assign(new Error('withdrawn'),{code:410});if(!exists)throw Object.assign(new Error('not yet'),{code:404});return {data:{member_id:member,thread_id:thread,request_id:requestId,task_type:'consultation',agent_slug:'health-consultation',request_status:'dispatched',execution_status:'completed',result:{result_type:'general_education_answer',scope:'general_education',answer:'private previous answer',citations:[]}}}};throw new Error(o.path)}
 const deps={chooseReference,isReferencePlan,preparationReady:value=>checkPreparation(value,'2026-10-20'),readCurrentPreparation:async()=>readyPreparation('2026-10-20'),preparationRoute:()=>'/pages/onboarding/preparing',HEALTH_TEXT_TASKS,loadCloudProfile:async()=>({onboarded:true,selfMemberId:'self',householdId:'family',defaultDiners:['self'],members:[{id:'self',relation:'本人',healthMemberId:member}]}),dailyArrangementState:()=>({phase:'idle',busy:false}),createDailyArrangementClient:({state})=>({adopt:arrangement=>{state.phase='ready';state.arrangement=arrangement},load:async()=>{state.phase='ready';state.arrangement={}},pause(){},reset(){},dispose(){}}),storageContext:()=> 'scope',scopedStorage:saved,getSession:()=>({accountId:'self',householdId:'family',token:'synthetic'}),commerce:{connect:async()=>{}},request:send,newHealthRequestId:()=>requestId,localDate:()=> '2026-10-20',readChatSnapshot:async()=>({messages:[],runs:[]}),chatImageContent:async image=>image.localPath,persistChatImage:async image=>({localPath:image.path}),createHealthTaskFlow:options=>createHealthTaskFlow({...options,send,session:()=>({accountId:'self',token:'synthetic'}),revision:()=>1,storage:saved,newId:()=>requestId,day:()=> '2026-10-20',subscribe:()=>()=>{}}),uni:{redirectTo(){},reLaunch(){},showToast(){}}}
 deps.mealQuestionAction=mealQuestionAction;deps.readDailyMealPlan=(family,date)=>readDailyMealPlan(family,date,deps.request)
 return {deps,calls,invalidate:()=>invalid=true}
}
for(const rejects of [false,true])test(`chat rereads after session refresh during profile loading (rejected: ${rejects})`,async()=>{
 const h=chat();let scope='before',reads=0;const original=h.deps.loadCloudProfile
 h.deps.storageContext=()=>scope
 h.deps.loadCloudProfile=async()=>{reads++;if(reads===1){scope='after';if(rejects)throw new Error('账号已变化，请重新进入。')}return {...await original(),testRead:reads}}
 const p=mount('CloudNutritionChat.vue','load,entryReady,entryError,profileLoading,profile',h.deps)
 await p.load();assert.equal(reads,2);assert.equal(p.entryReady.value,true);assert.equal(p.profile.value.testRead,2);assert.equal(p.entryError.value,'');assert.equal(p.profileLoading.value,false);p.dispose()
})

test('chat stops automatic recovery after a second session change and permits manual retry',async()=>{
 const h=chat();let revision=0,changing=true,reads=0;const original=h.deps.loadCloudProfile
 h.deps.storageContext=()=>String(revision)
 h.deps.loadCloudProfile=async()=>{reads++;if(changing)revision++;return original()}
 const p=mount('CloudNutritionChat.vue','load,entryReady,entryError,profileLoading,profile',h.deps)
 await p.load();assert.equal(reads,2);assert.equal(p.entryReady.value,false);assert.equal(p.profile.value,null);assert.equal(p.profileLoading.value,false);assert.match(p.entryError.value,/登录状态仍在更新/)
 changing=false;await p.load();assert.equal(p.entryReady.value,true);assert.equal(p.entryError.value,'');p.dispose()
})

for(const field of ['accountId','token','householdId'])test(`chat discards results and routes through entry when ${field} changes`,async()=>{
 const h=chat();let scope='before',reads=0;const session=h.deps.getSession(),routes=[];const original=h.deps.loadCloudProfile
 h.deps.getSession=()=>({...session});h.deps.storageContext=()=>scope;h.deps.uni.reLaunch=o=>routes.push(o.url)
 h.deps.loadCloudProfile=async()=>{reads++;scope='after';session[field]='changed';return original()}
 const p=mount('CloudNutritionChat.vue','load,entryReady,entryError,profileLoading,profile,messages',h.deps)
 await p.load();assert.equal(reads,1);assert.equal(p.entryReady.value,false);assert.equal(p.profile.value,null);assert.deepEqual(p.messages.value,[]);assert.equal(p.profileLoading.value,false);assert.match(p.entryError.value,/已变化/);assert.deepEqual(routes,['/pages/index/index']);p.dispose()
})

test('chat automatically rereads after assigning the first household',async()=>{
 const h=chat();let scope='unassigned',reads=0;const session={...h.deps.getSession(),householdId:null},original=h.deps.loadCloudProfile
 h.deps.getSession=()=>({...session});h.deps.storageContext=()=>scope
 h.deps.loadCloudProfile=async()=>{reads++;scope='assigned';session.householdId='family';return original()}
 const p=mount('CloudNutritionChat.vue','load,entryReady',h.deps)
 await p.load();assert.equal(reads,2);assert.equal(p.entryReady.value,true);p.dispose()
})

test('chat recovers when session changes during conversation restoration without showing old messages',async()=>{
 const h=chat();let scope='before',snapshots=0
 h.deps.storageContext=()=>scope
 h.deps.readChatSnapshot=async()=>{snapshots++;if(snapshots===1)scope='after';return {messages:[{id:String(snapshots),role:'assistant',text:snapshots===1?'stale private message':'current message'}],runs:[]}}
 const p=mount('CloudNutritionChat.vue','load,entryReady,messages,profileLoading',h.deps)
 await p.load();assert.equal(snapshots,2);assert.equal(p.entryReady.value,true);assert.deepEqual(p.messages.value.map(m=>m.text),['current message']);assert.equal(p.profileLoading.value,false);p.dispose()
})

test('hidden chat ignores old loads; foreground load restores it and duplicate loads share the request',async()=>{
 const h=chat();let finish,reads=0;const original=h.deps.loadCloudProfile
 h.deps.loadCloudProfile=async()=>{reads++;if(reads===1)await new Promise(resolve=>finish=resolve);return original()}
 const p=mount('CloudNutritionChat.vue','load,entryReady,profile,profileLoading',h.deps)
 const first=p.load(),duplicate=p.load();assert.equal(reads,1);p.hooks.hide();await p.load();assert.equal(reads,2);assert.equal(p.entryReady.value,true);finish();await Promise.all([first,duplicate]);assert.equal(p.entryReady.value,true);assert.equal(p.profileLoading.value,false);p.dispose()
})

test('chat initialization failure displays a consultation error and can be retried',async()=>{
 const h=chat(),original=h.deps.loadCloudProfile;let denied=true
 h.deps.loadCloudProfile=async()=>{if(denied)throw Object.assign(new Error('咨询授权已撤回'),{code:403});return original()}
 const p=mount('CloudNutritionChat.vue','load,entryReady,entryError,profileLoading',h.deps)
 await p.load();assert.equal(p.entryReady.value,false);assert.equal(p.profileLoading.value,false);assert.match(p.entryError.value,/咨询授权/)
 denied=false;await p.load();assert.equal(p.entryReady.value,true);assert.equal(p.entryError.value,'');p.dispose()
})
test('unknown chat retry settles the original bubble and removes only its original draft',async()=>{
 const h=chat(),p=mount('CloudNutritionChat.vue','load,question,draftImage,messages,sendQuestion,retryQuestion,flow,task',h.deps)
 await p.load();p.question.value='original';p.draftImage.value={localPath:'data:image/png;base64,QQ=='};await p.sendQuestion();assert.equal(p.messages.value[0].status,'unknown');assert.equal(p.question.value,'original')
 await p.retryQuestion();assert.equal(p.question.value,'');assert.equal(p.draftImage.value,null);assert.equal(p.messages.value[0].status,'sent');assert.deepEqual(p.messages.value.map(m=>m.role),['user','assistant']);assert.equal(h.calls.filter(c=>c.path==='/api/agent/runs').length,2);p.dispose()
})
test('a caught send TypeError retains the draft and logs only its stage and public code frames',async()=>{
 const h=chat(),logs=[],secret='synthetic-private-question-profile-token'
 const failure=new TypeError(secret)
 failure.stack=`TypeError: ${secret}\n    at sendQuestion (https://example.test/private-account/CloudNutritionChat.js?token=${secret}:123:9)\n    at ${secret} (https://example.test/private-account/request.js?query=${secret}:45:6)\n    at ${secret}`
 h.deps.console={error:(...args)=>logs.push(args)}
 h.deps.newHealthRequestId=()=>{throw failure}
 const p=mount('CloudNutritionChat.vue','load,question,draftImage,messages,sendQuestion',h.deps)
 try{
  await p.load();p.question.value=secret;p.draftImage.value={localPath:'data:image/png;base64,PRIVATE'}
  await p.sendQuestion()
  assert.equal(p.question.value,secret);assert.equal(p.draftImage.value.localPath,'data:image/png;base64,PRIVATE');assert.deepEqual(p.messages.value,[])
  assert.equal(logs.length,1)
  assert.deepEqual(logs[0],['[health-chat-send]',{stage:'queue-message',name:'TypeError',message:'TypeError',stack:'at CloudNutritionChat.js:123:9\nat request.js:45:6'}])
  assert.ok(!JSON.stringify(logs).includes(secret));assert.ok(!JSON.stringify(logs).includes('private-account'));assert.ok(!JSON.stringify(logs).includes('base64'))
  assert.ok(!h.calls.some(c=>c.path==='/api/agent/runs'))
 }finally{p.dispose()}
})
test('a withdrawn chat source clears the already displayed private conversation',async()=>{
 const h=chat(),p=mount('CloudNutritionChat.vue','load,question,messages,sendQuestion,retryQuestion,flow',h.deps)
 await p.load();p.question.value='original';await p.sendQuestion();await p.retryQuestion();assert.ok(p.messages.value.some(m=>m.text==='private previous answer'));h.invalidate();await p.flow.refresh();assert.deepEqual(p.messages.value,[]);assert.equal(p.question.value,'');p.dispose()
})
test('capture discards private in-memory state before restoring another account cache',async()=>{
 let scope='A';const cache=new Map(),saved={getStorageSync:k=>jsonClone(cache.get(scope+':'+k)),setStorageSync:(k,v)=>cache.set(scope+':'+k,jsonClone(v))}
 const p=mount('CloudMealCapture.vue','load,people,members,dishes,photo,saved,hide,store',{
  photoState,createMealPhotoClient:({state})=>({open:async id=>{state.memberId=id},discard:()=>Object.assign(state,photoState())}),createCloudMealSaver:()=>({read:()=>null,hide(){}}),personalMeal,mealLabels,mealDay,scopedStorage:saved,storageContext:()=>scope,getSession:()=>({householdId:scope}),request:async()=>({data:[{id:scope+'-member',display_name:scope,scopes:['diet_edit']}]}),uni:{},commerce:{}})
 await p.load();p.dishes.value=[{name:'A private meal'}];p.photo.value='/a-private-photo';p.saved.value={rows:[{memberId:'A-member'}]};p.hide();scope='B';await p.load();await nextTick()
 assert.equal(p.members.value[0].id,'B-member');assert.deepEqual(p.dishes.value,[]);assert.equal(p.photo.value,'');assert.equal(p.saved.value,null);assert.ok(!JSON.stringify(cache.get('B:cloud-capture-ui')).includes('A private'));p.dispose()
})
test('retaking the single meal photo submits the replacement upload only',async()=>{
 const cache=storage(),calls=[];let picker,n=0
 const send=async o=>{calls.push(o);if(o.path.endsWith('/members'))return {data:[{id:member,display_name:'self',scopes:['diet_edit','ai_use']}]};if(o.path.endsWith('/configuration'))return {data:{policy_version:'p1',meal:{available:true,processor:'synthetic'}}};if(o.path.includes('/vision/page'))return {data:{jobs:[],drafts:[],jobs_next_offset:null,drafts_next_offset:null}};if(o.path.endsWith('/processing-consents'))return {data:{accepted:true}};if(o.path.endsWith('/meal-photo-tasks'))return {data:{task_id:'job'}};if(o.path.endsWith('/vision-tasks/job'))return {data:{task_id:'job',execution_status:'running'}};throw new Error(o.path)}
 const p=mount('CloudMealCapture.vue','load,chooseImage,analyze,vision,consent',{
  photoState,createMealPhotoClient:options=>createMealPhotoClient({...options,send,storage:cache,revision:()=>1,upload:async(_id,path)=>({upload_id:path}),newId:()=>String(++n)}),createCloudMealSaver:()=>({read:()=>null,hide(){}}),personalMeal,mealLabels,mealDay,scopedStorage:cache,storageContext:()=> 'scope',request:send,getSession:()=>({householdId:'family'}),uni:{chooseImage:o=>picker=o},commerce:{}})
 await p.load();p.chooseImage('camera');await picker.success({tempFilePaths:['first']});picker.complete();p.chooseImage('camera');await picker.success({tempFilePaths:['replacement']});picker.complete();p.consent.value=true;await p.analyze();assert.deepEqual(calls.find(c=>c.path.endsWith('/meal-photo-tasks')).data.upload_ids,['replacement']);p.dispose()
})
test('late journal detail response cannot restore private state after leaving',async()=>{
 let release;const p=mount('HealthMealJournal.vue','load,hide,detail',{
  defineProps:()=>({memberId:member,detailId:'record'}),sessionRevision:()=>1,scopedStorage:storage(),mealDay,mealLabels,request:async o=>({data:o.path.endsWith('/members')?[{id:member,scopes:['diet_edit']}]:{records:[],next_offset:null}}),readDietRecord:()=>new Promise(resolve=>release=resolve)})
 const loading=p.load();while(!release)await nextTick();p.hide();release({id:'record',source_version:1,snapshot:{meal:{eaten_at:'2026-10-20T12:00:00+08:00'}}});await loading;assert.equal(p.detail.value,null);p.dispose()
})
test('journal conflict rereads the current version before a second correction',async()=>{
 const cache=storage(),writes=[];let attempt=0
 const record=version=>({id:'record',member_id:member,source_version:version,snapshot:{meal:{meal_type:'lunch',eaten_at:'2026-10-20T12:00:00+08:00',items:[]}}})
 const p=mount('HealthMealJournal.vue','detail,edit,save,reason,editing',{
  defineProps:()=>({}),sessionRevision:()=>1,scopedStorage:cache,mealDay,mealLabels,newHealthRequestId:()=>String(++attempt),mealInput:v=>v,readDietRecord:async()=>record(3),request:async o=>{writes.push(o);if(writes.length===1)throw Object.assign(new Error('conflict'),{code:409});return {data:{}}}})
 p.detail.value=record(1);p.edit();p.reason.value='correction';await p.save();assert.equal(p.detail.value.source_version,3);assert.equal(p.editing.value,false);p.edit();p.reason.value='rechecked';await p.save();assert.equal(writes[1].data.expected_version,3);p.dispose()
})


test('member switch cannot attach current candidate dishes to another members older photo draft',async()=>{
 const cache=storage(),other='other-member'
 const p=mount('CloudMealCapture.vue','load,vision,useCandidates,togglePerson,people,savedMeal,origin',{
 photoState,createMealPhotoClient:({state})=>({open:async id=>{state.memberId=id;state.draft={id:id==='other-member'?'old-B':'original-A',version:1};state.meal={meal_type:'lunch',eaten_at:'2026-10-20T12:00:00+08:00',photos:[{upload_id:id==='other-member'?'B-photo':'A-photo'}],items:[{item_id:'item',name:id==='other-member'?'B dish':'A dish',locations:[{image_index:0}]}]}},discard(){}}),createCloudMealSaver:()=>({read:()=>null,hide(){}}),personalMeal,mealLabels,mealDay,scopedStorage:cache,storageContext:()=> 'scope',request:async()=>({data:[{id:member,scopes:['diet_edit']},{id:other,scopes:['diet_edit']}]}),getSession:()=>({householdId:'family'}),commerce:{},uni:{}})
 await p.load();p.useCandidates();p.togglePerson(p.people.value[1]);await nextTick();const b=p.people.value[1];b.dishes=['A dish'];const result=p.savedMeal(b)
 assert.equal(p.vision.draft.id,'old-B');assert.equal(p.origin.value.draft.id,'original-A');assert.equal(result.draftId,undefined);assert.deepEqual(result.meal.photos,[]);assert.ok(result.meal.items[0].uncertainties.some(s=>s.includes('未关联照片原图')));p.dispose()
})

test('one invalid conversation does not hide other valid messages in the same day',async()=>{
 const h=chat(),cache=h.deps.scopedStorage;cache.setStorageSync(`homepage-chat-threads:${member}:2026-10-20`,[{thread_id:'expired'},{thread_id:thread}])
 h.deps.readChatSnapshot=async id=>{if(id==='expired')throw Object.assign(Error('source changed'),{code:410});return {messages:[{id:'ok',role:'assistant',text:'valid same-day',createdAt:'2026-10-20T00:00:00Z'},{id:'yesterday',role:'assistant',text:'old date',createdAt:'2026-10-19T00:00:00Z'}],runs:[]}}
 const p=mount('CloudNutritionChat.vue','load,messages',h.deps);await p.load();assert.deepEqual(p.messages.value.map(m=>m.text),['valid same-day']);assert.deepEqual(cache.getStorageSync(`homepage-chat-threads:${member}:2026-10-20`).map(t=>t.thread_id),[thread]);p.dispose()
})


test('editing recognized dish names retains the original photo draft and leaves new locations empty',async()=>{
 const cache=storage();let modal
 const p=mount('CloudMealCapture.vue','load,vision,useCandidates,manual,people,savedMeal',{
 photoState,createMealPhotoClient:({state})=>({open:async id=>{state.memberId=id;state.draft={id:'original-photo',version:1};state.meal={meal_type:'lunch',eaten_at:'2026-10-20T12:00:00+08:00',photos:[{upload_id:'original-upload'}],items:[{item_id:'original-item',name:'wrong name',locations:[{image_index:0}]}]}},discard(){}}),createCloudMealSaver:()=>({read:()=>null,hide(){}}),personalMeal,mealLabels,mealDay,scopedStorage:cache,storageContext:()=> 'scope',request:async()=>({data:[{id:member,scopes:['diet_edit']}]}),getSession:()=>({householdId:'family'}),commerce:{},uni:{showModal:o=>modal=o}})
 await p.load();p.useCandidates();p.manual();modal.success({confirm:true,content:'corrected name'});p.people.value[0].dishes=['corrected name'];const result=p.savedMeal(p.people.value[0]);assert.equal(result.draftId,'original-photo');assert.equal(result.meal.photos[0].upload_id,'original-upload');assert.equal(result.meal.items[0].excluded,true);assert.ok(!result.meal.items[1].locations?.length);p.dispose()
})


test('family reference question preserves all selected actors, meal and original constraints',async()=>{
 const h=chat(),opened=[],queries=[]
 h.deps.loadCloudProfile=async()=>({onboarded:true,householdId:'family',selfMemberId:'self',members:[{id:'self',relation:'本人',healthMemberId:member},{id:'parent',relation:'母亲',healthMemberId:'parent-health'}]})
 h.deps.createHealthTaskFlow=({onChange})=>({hide(){},invalidateThread(){},open:async(id,type,selection)=>{opened.push({id,type,selection});onChange({memberId:id,taskType:type,available:true,entry:{thread_id:thread,agent_slug:type==='consultation'?'health-consultation':'health-meal-planner'}})},submit:async text=>{queries.push(text);return true}})
 const p=mount('CloudNutritionChat.vue','load,question,sendQuestion',h.deps)
 await p.load();p.question.value='给全家安排明天早餐，不要牛奶';await p.sendQuestion('reference_meal_preview')
 const entry=opened.find(o=>o.type==='reference_meal_preview')
 assert.equal(entry.selection.family_id,'family');assert.deepEqual(entry.selection.participant_ids,['parent','self']);assert.deepEqual(entry.selection.meal_types,['breakfast'])
 assert.deepEqual(queries,['给全家安排明天早餐，不要牛奶']);assert.equal(p.question.value,'');p.dispose()
})

test('an ordinary tomorrow breakfast request stays in the continuous consultation',async()=>{
 const h=chat(),opened=[],queries=[]
 h.deps.localDate=date=>date?'2026-10-21':'2026-10-20'
 h.deps.createHealthTaskFlow=({onChange})=>({hide(){},open:async(id,type,selection)=>{opened.push({id,type,selection});onChange({memberId:id,taskType:type,available:true,entry:{thread_id:thread,agent_slug:type==='consultation'?'health-consultation':'health-meal-planner'}})},submit:async text=>{queries.push(text);return true}})
 const p=mount('CloudNutritionChat.vue','load,question,sendQuestion,chatError',h.deps)
 await p.load();p.question.value='给我安排明天早餐';await p.sendQuestion()
 assert.equal(opened.some(o=>o.type==='reference_meal_preview'),false)
 assert.equal(opened.at(-1).type,'consultation');assert.equal(opened.at(-1).id,member)
 assert.deepEqual(queries,['给我安排明天早餐']);assert.equal(p.chatError.value,'');assert.equal(p.question.value,'');p.dispose()
})

test('unsupported reference dates preserve the complete question before creating a task',async()=>{
 const h=chat(),p=mount('CloudNutritionChat.vue','load,question,chatError,sendQuestion',h.deps)
 await p.load();p.question.value='给全家安排下周一早餐，不要牛奶';await p.sendQuestion('reference_meal_preview')
 assert.equal(p.question.value,'给全家安排下周一早餐，不要牛奶');assert.match(p.chatError.value,/原问题已保留/)
 assert.ok(!h.calls.some(c=>c.path==='/api/agent/runs'||c.path.endsWith('/task-entries')));p.dispose()
})

test('family retry uses the original intent date and enables failed-task recovery',async()=>{
 const h=chat(),actions=[];h.deps.createDailyArrangementClient=({state})=>({load:async(date,retry)=>{actions.push({date,retry});state.phase='error';state.error='synthetic failure'},adopt(){},pause(){},reset(){},dispose(){}})
 const p=mount('CloudNutritionChat.vue','load,familyPlan,question',h.deps);await p.load();await p.familyPlan('今晚全家吃什么？');p.question.value='another question';await p.familyPlan('',true);assert.equal(actions.at(-1).retry,true);assert.equal(actions.at(-1).date,actions.at(-2).date);assert.equal(p.question.value,'another question');p.dispose()
})

test('correction saves unknown nutrition and retries the exact original payload after uncertain transport',async()=>{
 const cache=storage(),calls=[];let attempts=0
 const record={id:'record',member_id:member,source_version:1,snapshot:{meal:{meal_type:'lunch',eaten_at:'2026-10-25T12:00:00+08:00',items:[{item_id:'dish',name:'青菜',grams:null,share_ratio:null,portion_source:'unknown',excluded:false}]},nutrition:{totals:{energy_kcal:null}}}}
 const p=mount('HealthMealJournal.vue','detail,meal,edit,save,reason,pending,editing,eatenWeight',{
  defineProps:()=>({}),sessionRevision:()=>1,scopedStorage:cache,mealDay,mealLabels,newHealthRequestId:()=>requestId,mealInput,
  readDietRecord:async()=>({...record,source_version:2}),request:async o=>{calls.push(jsonClone(o));if(++attempts===1)throw new Error('timeout');return {data:{}}},
 })
 try{
  p.detail.value=record;p.edit();p.reason.value='核对菜品';await p.save()
  assert.equal(calls[0].data.accept_incomplete,true);assert.equal(calls[0].data.meal.items[0].grams,null);assert.equal(calls[0].data.meal.items[0].share_ratio,null)
  assert.ok(p.pending.value);p.meal.value.items[0].grams=888;p.reason.value='later edit';await p.save()
  assert.deepEqual(calls[1],calls[0]);assert.equal(p.pending.value,null);assert.equal(p.editing.value,false);assert.equal(p.detail.value.snapshot.nutrition.totals.energy_kcal,null)
  assert.equal(p.eatenWeight({grams:200,share_ratio:.5}),'100 g');assert.equal(p.eatenWeight({grams:200,share_ratio:null}),'重量未知')
 }finally{p.dispose()}
})

function checkoutHarness(cache,options={}){
 const calls=[],state=reactive({ready:false,busy:false,selected:[],slots:[{id:2}],address:{id:options.address||1},slotId:2,quote:null})
 const product={id:1,priceCents:100,quantity:1};let scope='account:family:session:1'
 const route={arrangement:'arrangement',version:1,date:'2026-10-25',meal:options.meal||'lunch',...(options.meal==='daily'?{meals:['breakfast','lunch']}:{})}
 const p=mount('CloudMealPurchase.vue','refresh,checkout,chooseAddress,checkoutOpen,error,preview',{
  defineProps:()=>({route,meal:{members:[]}}),scopedStorage:cache,storageContext:()=>scope,getSession:()=>({householdId:'family'}),
  commerceMealView:()=>({products:[product]}),commerce:{session:()=>({token:'ok'}),connect:async()=>{calls.push('connect')}},
  useMealCommercePage:()=>({state,plan:computed(()=>({products:[product]})),invalidateQuote(){state.quote=null},reset(){state.ready=false},dispose(){},
   async load(){state.ready=true;state.selected=[1];calls.push('load')},async prepare(){state.quote={address_id:state.address.id};calls.push('quote')},}),
  request:async o=>{calls.push(o.method||'GET');if(options.revoked)throw Object.assign(Error('revoked'),{code:403});return {data:{arrangement_id:route.arrangement,version:options.version||1,purchase:{available:!options.unavailable,items:[],package_sn:'package',package_version:1}}}},
  uni:{navigateTo:o=>{calls.push(o.url);if(options.failNavigation)o.fail()}},
 })
 return {p,calls,state,setScope:v=>scope=v}
}
for(const meal of ['lunch','daily'])test(`${meal} checkout returns from address selection, revalidates and quotes the new address once`,async()=>{
 const cache=storage(),first=checkoutHarness(cache,{meal});await first.p.refresh();await first.p.checkout();first.p.chooseAddress();assert.equal(first.state.quote,null);first.p.dispose()
 const returned=checkoutHarness(cache,{meal,address:2})
 try{await returned.p.refresh();assert.equal(returned.p.checkoutOpen.value,true);assert.equal(returned.state.quote.address_id,2);assert.deepEqual(returned.calls,['GET','connect','POST','load','quote']);await returned.p.refresh();assert.equal(returned.calls.filter(c=>c==='POST').length,1);assert.equal(returned.calls.filter(c=>c==='quote').length,1)}finally{returned.p.dispose()}
})
for(const problem of ['expired','session','version','revoked','unavailable','failed-navigation'])test(`address return cannot restore checkout after ${problem}`,async()=>{
 const cache=storage(),first=checkoutHarness(cache,{failNavigation:problem==='failed-navigation'});await first.p.refresh();first.p.chooseAddress();first.p.dispose()
 const key=cache.getStorageInfoSync().keys.find(k=>k.startsWith('meal-checkout-address-return:'))
 if(problem==='expired'){const value=cache.getStorageSync(key);value.at=Date.now()-16*60*1000;cache.setStorageSync(key,value)}
 const h=checkoutHarness(cache,{version:problem==='version'?2:1,revoked:problem==='revoked',unavailable:problem==='unavailable'});if(problem==='session')h.setScope('account:family:session:2')
 try{await h.p.refresh();assert.equal(h.p.checkoutOpen.value,false);assert.ok(!h.calls.includes('POST'));assert.ok(!h.calls.includes('quote'));assert.equal(cache.getStorageSync(key),null)}finally{h.p.dispose()}
})


test('unconfigured consultation gives the service reason without invoking member readiness',async()=>{
 const h=chat();h.deps.loadCloudProfile=async()=>({onboarded:true,selfMemberId:'self',members:[{id:'self',relation:'本人'}],healthConfiguration:{consultation:{available:false,reason:'尚未配置开发测试模型'}}})
 const p=mount('CloudNutritionChat.vue','load,chatError,task',h.deps);await p.load()
 assert.match(p.chatError.value,/尚未配置开发测试模型/);assert.ok(!h.calls.some(c=>c.path.endsWith('/readiness')));assert.equal(p.task.value.available,undefined);p.dispose()
})

test('saved but unlinked profiles have a working reconfirmation route and cannot start planning',async()=>{
 const h=chat(),routes=[];h.deps.uni.navigateTo=o=>routes.push(o.url)
 h.deps.loadCloudProfile=async()=>({onboarded:true,selfMemberId:'self',members:[{id:'self',relation:'本人'}],defaultDiners:['self'],healthConfiguration:{consultation:{available:true},meal_plan:{available:true}}})
 const p=mount('CloudNutritionChat.vue','load,chatError,memberArchive,requirePlanningReady',h.deps);await p.load()
 assert.match(p.chatError.value,/家庭档案/);assert.throws(()=>p.requirePlanningReady(),e=>e.businessCode==='daily_member_sources_unavailable');p.memberArchive();assert.deepEqual(routes,['/pages/profile/member?id=self']);assert.ok(!h.calls.some(c=>c.path.endsWith('/task-entries')||c.path==='/api/agent/runs'));p.dispose()
})

test('both daily entry clients check configuration before starting, while reading stays allowed',async()=>{
 const h=chat(),clients=[]
 h.deps.createDailyArrangementClient=options=>{clients.push(options);return {load:async()=>{},adopt(){},pause(){},reset(){},dispose(){}}}
 h.deps.loadCloudProfile=async()=>({onboarded:true,selfMemberId:'self',members:[],healthConfiguration:{meal_plan:{available:false,reason:'模型未就绪'},consultation:{available:false,reason:'模型未就绪'}}})
 const p=mount('CloudNutritionChat.vue','load',h.deps);await p.load()
 assert.equal(clients.length,2);for(const client of clients)assert.throws(client.beforeStart,e=>e.businessCode==='daily_dependencies_not_ready'&&e.retryable===false);p.dispose()
})

test('another claimed family member must confirm their own analysis authorization',async()=>{
 const h=chat();h.deps.loadCloudProfile=async()=>({onboarded:true,selfMemberId:'self',members:[{id:'self',relation:'本人',healthMemberId:member},{id:'parent',relation:'母亲',claimed:true}],defaultDiners:['self','parent'],healthConfiguration:{meal_plan:{available:true}}})
 const p=mount('CloudNutritionChat.vue','load,requirePlanningReady',h.deps);await p.load()
 assert.throws(()=>p.requirePlanningReady(),e=>e.businessCode==='daily_member_consent_required'&&/该成员登录/.test(e.message));p.dispose()
})

test('chat blocks sending until the actual profile load settles and shows why',async()=>{
 const h=chat();let finish
 h.deps.loadCloudProfile=()=>new Promise(resolve=>{finish=resolve})
 const p=mount('CloudNutritionChat.vue','load,question,sendQuestion,chatBusy',h.deps)
 const loading=p.load();p.question.value='请介绍均衡饮食';await p.sendQuestion()
 assert.equal(p.chatBusy.value,true)
 assert.equal(h.calls.length,0);assert.equal(p.question.value,'请介绍均衡饮食')
 finish({onboarded:true,selfMemberId:'self',members:[{id:'self',relation:'本人',healthMemberId:member}]});await loading
 assert.equal(p.chatBusy.value,false);p.dispose()
})

test('failed initial profile load keeps the draft and exposes a retryable error on send',async()=>{
 const h=chat();h.deps.loadCloudProfile=async()=>{throw new Error('合成网络中断')}
 const p=mount('CloudNutritionChat.vue','load,question,sendQuestion,chatError',h.deps)
 await p.load();p.question.value='请介绍均衡饮食';await p.sendQuestion()
 assert.match(p.chatError.value,/合成网络中断/)
 assert.equal(p.question.value,'请介绍均衡饮食');assert.equal(h.calls.length,0);p.dispose()
})

test('a failed consultation restarts empty and preserves the edited draft until its first send',async()=>{
 const h=chat(),saved=storage(),newThread='44444444-4444-4444-8444-444444444444',calls=[]
 const send=async o=>{
  calls.push(o)
  if(o.path.endsWith('/members'))return {data:[{id:member,is_owner:true}]}
  if(o.path.endsWith('/readiness'))return {data:{capabilities:{member_id:member},entries:[{entry_type:'consultation',status:'available'}]}}
  if(o.path.endsWith('/daily-conversations'))return {data:{days:[{date:'2026-10-20',thread_id:thread}]}}
  if(o.path.includes('/tasks/'))return {data:{member_id:member,thread_id:thread,request_id:requestId,task_type:'consultation',agent_slug:'health-consultation',request_status:'dispatched',execution_status:'failed'}}
  if(o.path.endsWith('/task-entries'))return {data:{member_id:member,task_type:'consultation',client_request_id:requestId,entry_status:'ready',thread_id:newThread,agent_slug:'health-consultation',request_submit_url:'/api/agent/runs'}}
  throw Error(o.path)
 }
 h.deps.scopedStorage=saved
 h.deps.createHealthTaskFlow=options=>createHealthTaskFlow({...options,send,session:()=>({token:'synthetic',accountId:'self'}),revision:()=>1,storage:saved,newId:()=>requestId,day:()=> '2026-10-20',subscribe:()=>()=>{}})
 const p=mount('CloudNutritionChat.vue','load,flow,task,question,draftImage,draftError,restartChat,conversationId,messages',h.deps)
 await p.load();await p.flow.restoreRequest(requestId);assert.equal(p.task.value.status,'failed')
 p.question.value='修改后的问题';p.draftImage.value={localPath:'data:image/png;base64,QQ=='}
 await p.restartChat()
 assert.equal(p.task.value.entry,null);assert.equal(p.conversationId.value,requestId);assert.deepEqual(p.messages.value,[]);assert.equal(p.question.value,'修改后的问题')
 assert.equal(p.draftImage.value.localPath,'data:image/png;base64,QQ==')
 assert.equal(calls.filter(c=>c.path.endsWith('/task-entries')).length,0)
 assert.equal(calls.some(c=>c.path==='/api/agent/runs'),false);p.dispose()
})


for(const status of ['absent','failed','stale','preparing'])test(`direct homepage with ${status} meal preparation permits ordinary chat`,async()=>{
 const h=chat(),routes=[];h.deps.readCurrentPreparation=async()=>({status})
 h.deps.uni.redirectTo=o=>routes.push(o.url)
 const p=mount('CloudNutritionChat.vue','load,entryReady,question,sendQuestion,messages',h.deps)
 await p.load();p.question.value='日常饮食如何规律';await p.sendQuestion()
 assert.deepEqual(routes,[]);assert.equal(p.entryReady.value,true)
 assert.equal(h.calls.filter(c=>c.path==='/api/agent/runs').length,1);p.dispose()
})

test('a pending optional meal read does not block homepage chat readiness',async()=>{
 const h=chat();let finish;h.deps.readCurrentPreparation=()=>new Promise(resolve=>finish=resolve)
 const p=mount('CloudNutritionChat.vue','load,entryReady',h.deps);await p.load()
 assert.equal(p.entryReady.value,true);p.dispose();finish({status:'absent'})
})

function todayMeals({reference={status:'absent'},arrangement={status:'absent'},readError=null}={}){
 const h=chat(),reads=[]
 h.deps.readCurrentPreparation=async()=>({status:'blocked',message:'配餐所需的营养规则或档案编码规则尚未配置完成，档案已保存，请等待服务配置后继续准备'})
 h.deps.dailyArrangementState=dailyArrangementState
 h.deps.createDailyArrangementClient=createDailyArrangementClient
 const send=h.deps.request
 h.deps.request=async input=>{
  if(input.path.includes('/daily-meal-plans/')){
   reads.push(input);if(readError)throw readError
   if(reference.status==='reference_ready')return {data:{status:'ready',date:'2026-10-20',version:0,meals:[{meal_type:'breakfast',source:{kind:'reference',id:reference.preview_id},meal:{dishes:[]},members:[]}]}}
   if(arrangement.status==='ready')return {data:{status:'ready',date:arrangement.date,version:0,formal_arrangement:arrangement,meals:arrangement.meals.map(meal=>({meal_type:meal.type,source:{kind:'formal',id:arrangement.id,version:arrangement.version},meal,members:meal.members}))}}
   return {data:{status:'absent',date:'2026-10-20',version:0,meals:[]}}
  }
  return send(input)
 }
 return {h,reads,page:mount('CloudNutritionChat.vue','load,loadOptionalMeals,shortcut,state,entryReady,todayPlan,mealReadError,mealsLoading,inlineTodayOpen,profile',h.deps)}
}

test('viewing today reads saved meals without starting or retrying formal preparation',async()=>{
 const {page,reads}=todayMeals();await page.load();await page.loadOptionalMeals('family',1,'scope');await page.shortcut('today')
 assert.equal(page.entryReady.value,true);assert.equal(page.inlineTodayOpen.value,true)
 assert.equal(page.state.error,'');assert.equal(page.mealReadError.value,'');assert.equal(page.todayPlan.value.status,'absent')
 assert.ok(reads.length>0);assert.ok(reads.every(r=>!r.method||r.method==='GET'))
 assert.ok(reads.every(r=>!r.path.endsWith('/daily-arrangements')&&!r.path.includes('/resume')))
 page.dispose()
})

test('a saved reference remains available when the formal preparation lacks rules',async()=>{
 const reference={scope:'daily_reference',status:'reference_ready',professional_status:'not_reviewed',nutrition_status:'not_calculated',preview_id:'saved-preview',plan_date:'2026-10-20',meals:[{}]}
 const {page}=todayMeals({reference});await page.load();await page.loadOptionalMeals('family',1,'scope')
 assert.equal(page.todayPlan.value.meals[0].source.id,'saved-preview');assert.equal(page.state.error,'');assert.equal(page.entryReady.value,true);page.dispose()
})

test('today still restores a validated saved formal arrangement through GET',async()=>{
 const {page}=todayMeals({arrangement:readyPreparation('2026-10-20').arrangement});await page.load();await page.loadOptionalMeals('family',1,'scope')
 assert.equal(page.state.phase,'ready');assert.equal(page.state.arrangement.date,'2026-10-20');page.dispose()
})

test('meal transport failures remain visible in the meal panel without blocking chat',async()=>{
 const {page}=todayMeals({readError:new Error('connection lost')});await page.load();await page.loadOptionalMeals('family',1,'scope')
 assert.match(page.mealReadError.value,/无法读取/);assert.equal(page.entryReady.value,true);assert.equal(page.mealsLoading.value,false);page.dispose()
})

test('withdrawn meal access still clears private homepage state',async()=>{
 const {page}=todayMeals({readError:Object.assign(new Error('permission revoked'),{code:403})});await page.load();await page.loadOptionalMeals('family',1,'scope')
 assert.equal(page.entryReady.value,false);assert.equal(page.profile.value,null);assert.equal(page.todayPlan.value,null);page.dispose()
})

test('a formal arrangement from another date cannot appear as todays saved meal',async()=>{
 const {page}=todayMeals({arrangement:readyPreparation('2026-10-19').arrangement});await page.load();await page.loadOptionalMeals('family',1,'scope')
 assert.equal(page.state.arrangement,null);assert.match(page.mealReadError.value,/无法读取/);page.dispose()
})

test('a real-style 401 that clears the session cannot leave the private homepage visible',async()=>{
 const h=chat(),routes=[];let scope='scope',session={token:'synthetic',householdId:'family'}
 h.deps.storageContext=()=>scope;h.deps.getSession=()=>session;h.deps.uni.reLaunch=o=>routes.push(o.url)
 const send=h.deps.request
 h.deps.request=async input=>{
  if(input.path.includes('/daily-meal-plans/')){scope='guest';session=null;throw Object.assign(new Error('expired'),{code:401})}
  return send(input)
 }
 const p=mount('CloudNutritionChat.vue','load,entryReady,profile,mealsLoading,latestReference',h.deps)
 await p.load();await new Promise(setImmediate)
 assert.equal(p.entryReady.value,false);assert.equal(p.profile.value,null);assert.equal(p.latestReference.value,null);assert.equal(p.mealsLoading.value,false)
 assert.deepEqual(routes,['/pages/index/index']);p.dispose()
})

test('an older meal failure cannot clear the new accounts loaded profile',async()=>{
 const h=chat();let scope='A',rejectOld,first=true
 h.deps.storageContext=()=>scope
 const profile=h.deps.loadCloudProfile
 h.deps.loadCloudProfile=async()=>({...await profile(),testOwner:scope})
 const send=h.deps.request
 h.deps.request=async input=>{
  if(input.path.includes('/daily-meal-plans/')&&first){first=false;return new Promise((resolve,reject)=>rejectOld=reject)}
  return send(input)
 }
 const p=mount('CloudNutritionChat.vue','load,entryReady,profile,mealsLoading',h.deps)
 await p.load();scope='B';await p.load();await new Promise(setImmediate)
 rejectOld(Object.assign(new Error('old request expired'),{code:401}));await new Promise(setImmediate)
 assert.equal(p.entryReady.value,true);assert.equal(p.profile.value.testOwner,'B');assert.equal(p.mealsLoading.value,false);p.dispose()
})

test('shuffling changes only the four prompts and preserves scroll, draft, messages and network state',async()=>{
 const h=chat();h.deps.selectChatPrompts=options=>selectChatPrompts({...options,hour:18,random:()=>0.3})
 const p=mount('CloudNutritionChat.vue','load,prompts,shufflePrompts,scrollTarget,question,messages',h.deps)
 await p.load();await new Promise(setImmediate)
 const previous=p.prompts.value.map(q=>q.id),calls=h.calls.length
 p.scrollTarget.value='unchanged-target';p.question.value='保留我的草稿'
 p.messages.value=[{id:'existing',text:'保留我的消息'}]
 p.shufflePrompts()
 assert.equal(p.prompts.value.length,4);assert.ok(p.prompts.value.every(q=>!previous.includes(q.id)))
 assert.equal(p.scrollTarget.value,'unchanged-target');assert.equal(p.question.value,'保留我的草稿')
 assert.deepEqual(p.messages.value,[{id:'existing',text:'保留我的消息'}]);assert.equal(h.calls.length,calls)
 assert.deepEqual(h.deps.scopedStorage.getStorageSync('homepage-prompt-ids'),p.prompts.value.map(q=>q.id));p.dispose()
})

test('same-scope foreground loads keep the current prompt group and a new welcome rotates it',async()=>{
 const h=chat(),p=mount('CloudNutritionChat.vue','load,prompts,restartChat',h.deps)
 await p.load();const first=p.prompts.value.map(q=>q.id)
 await p.load();assert.deepEqual(p.prompts.value.map(q=>q.id),first)
 p.hooks.hide();p.hooks.show();await new Promise(setImmediate)
 assert.deepEqual(p.prompts.value.map(q=>q.id),first)
 await p.restartChat();assert.ok(p.prompts.value.every(q=>!first.includes(q.id)))
 assert.ok(!h.calls.some(c=>c.path==='/api/agent/runs'));p.dispose()
})

test('return keeps the existing chat and draft visible while a profile read is pending or fails',async()=>{
 const h=chat(),original=h.deps.loadCloudProfile;let rejectRead,reads=0
 h.deps.loadCloudProfile=()=>++reads===1?original():new Promise((_,reject)=>{rejectRead=reject})
 const p=mount('CloudNutritionChat.vue','load,entryReady,returning,returnVerified,returnError,inputBusy,question,messages,scrollTarget,profile',h.deps)
 await p.load();await new Promise(setImmediate)
 p.question.value='未发送的草稿';p.messages.value=[{id:'old',role:'user',text:'之前的内容'}];p.scrollTarget.value='message-old'
 p.hooks.hide();p.hooks.show()
 assert.equal(p.entryReady.value,true);assert.equal(p.returning.value,true);assert.equal(p.returnVerified.value,false)
 assert.equal(p.inputBusy.value,false);assert.equal(p.question.value,'未发送的草稿');assert.equal(p.messages.value[0].text,'之前的内容');assert.equal(p.scrollTarget.value,'message-old')
 rejectRead(Object.assign(new Error('网络暂不可用'),{code:'NETWORK_ERROR'}));await new Promise(setImmediate)
 assert.equal(p.entryReady.value,true);assert.equal(p.returning.value,false);assert.equal(p.returnVerified.value,false);assert.match(p.returnError.value,/网络/)
 assert.equal(p.inputBusy.value,false);assert.equal(p.messages.value[0].text,'之前的内容');p.dispose()
})

test('a session change during the background return clears old private content',async()=>{
 const h=chat(),original=h.deps.loadCloudProfile;let scope='old',release,reads=0;const routes=[]
 h.deps.storageContext=()=>scope;h.deps.uni.reLaunch=o=>routes.push(o.url)
 h.deps.loadCloudProfile=()=>++reads===1?original():new Promise(resolve=>{release=resolve})
 const p=mount('CloudNutritionChat.vue','load,entryReady,profile,messages,question',h.deps)
 await p.load();await new Promise(setImmediate);p.messages.value=[{id:'old',text:'private'}];p.question.value='private draft'
 p.hooks.hide();p.hooks.show();scope='new';release(await original());await new Promise(setImmediate)
 assert.equal(p.entryReady.value,false);assert.equal(p.profile.value,null);assert.deepEqual(p.messages.value,[]);assert.equal(p.question.value,'');assert.deepEqual(routes,['/pages/index/index']);p.dispose()
})

test('a successful return restores the same thread without moving scroll or replacing a draft',async()=>{
 const h=chat(),original=h.deps.loadCloudProfile;let finish,reads=0
 h.deps.loadCloudProfile=()=>++reads===1?original():new Promise(resolve=>{finish=()=>original().then(resolve)})
 const p=mount('CloudNutritionChat.vue','load,entryReady,returning,returnVerified,returnError,question,messages,scrollTarget,task',h.deps)
 await p.load();await new Promise(setImmediate);p.messages.value=[{id:'old',role:'user',text:'已有对话'}];p.question.value='已有草稿';p.scrollTarget.value='message-old'
 const threadBefore=p.task.value.entry.thread_id
 p.hooks.hide();p.hooks.show();assert.equal(p.entryReady.value,true);finish();await new Promise(setImmediate);await new Promise(setImmediate)
 assert.equal(p.returning.value,false);assert.equal(p.returnVerified.value,true);assert.equal(p.returnError.value,'')
 assert.equal(p.task.value.entry.thread_id,threadBefore);assert.equal(p.messages.value[0].text,'已有对话');assert.equal(p.question.value,'已有草稿');assert.equal(p.scrollTarget.value,'message-old');p.dispose()
})

test('authorization denial during return removes the previously visible chat',async()=>{
 const h=chat(),original=h.deps.loadCloudProfile;let reads=0
 h.deps.loadCloudProfile=()=>++reads===1?original():Promise.reject(Object.assign(new Error('已撤销'),{code:403}))
 const p=mount('CloudNutritionChat.vue','load,entryReady,entryError,profile,messages,question',h.deps)
 await p.load();await new Promise(setImmediate);p.messages.value=[{id:'old',text:'private'}];p.question.value='private draft'
 p.hooks.hide();p.hooks.show();await new Promise(setImmediate)
 assert.equal(p.entryReady.value,false);assert.equal(p.profile.value,null);assert.deepEqual(p.messages.value,[]);assert.equal(p.question.value,'');assert.match(p.entryError.value,/授权/);p.dispose()
})

test('return removes a thread whose source was revoked while the page was covered',async()=>{
 const h=chat();let reads=0
 h.deps.readChatSnapshot=async()=>{if(++reads>1)throw Object.assign(new Error('来源已撤销'),{code:410});return {messages:[],runs:[]}}
 const p=mount('CloudNutritionChat.vue','load,entryReady,entryError,messages,question',h.deps)
 await p.load();await new Promise(setImmediate);p.messages.value=[{id:'old',text:'private'}];p.question.value='private draft'
 p.hooks.hide();p.hooks.show();await new Promise(setImmediate);await new Promise(setImmediate)
 assert.equal(p.entryReady.value,false);assert.deepEqual(p.messages.value,[]);assert.equal(p.question.value,'');assert.match(p.entryError.value,/授权|来源/);p.dispose()
})

test('switching family clears in-memory suggestions before the next profile finishes',async()=>{
 const h=chat();let scope='first',finish;h.deps.storageContext=()=>scope
 const initial=h.deps.loadCloudProfile
 h.deps.loadCloudProfile=()=>scope==='first'?initial():new Promise(resolve=>finish=resolve)
 const p=mount('CloudNutritionChat.vue','load,prompts,profile',h.deps)
 await p.load();assert.equal(p.prompts.value.length,4)
 scope='second';const loading=p.load();assert.deepEqual(p.prompts.value,[]);assert.equal(p.profile.value,null)
 finish({onboarded:true,householdId:'second',selfMemberId:'self',members:[{id:'self',relation:'本人',healthMemberId:member}]})
 await loading;assert.equal(p.prompts.value.length,4);p.dispose()
})

for(const action of ['consultation','reference_meal_preview'])test(`suggestion action ${action} controls routing independently of display wording`,async()=>{
 const h=chat(),opened=[],queries=[]
 h.deps.createHealthTaskFlow=({onChange})=>({hide(){},open:async(id,type,selection)=>{opened.push({type,selection});onChange({memberId:id,taskType:type,available:true,entry:{thread_id:thread}})},submit:async text=>{queries.push(text);return true}})
 const p=mount('CloudNutritionChat.vue','load,askPrompt,task',h.deps);await p.load()
 const text=action==='consultation'?'午餐吃什么更省时间？':'给我一点早餐灵感'
 await p.askPrompt({id:'wording-independent',text,action})
 assert.equal(p.task.value.taskType,action);assert.deepEqual(queries,[text])
 if(action==='reference_meal_preview')assert.deepEqual(opened.at(-1).selection.meal_types,['breakfast'])
 p.dispose()
})

test('record suggestions navigate without sending or replacing an existing draft',async()=>{
 const h=chat(),routes=[];h.deps.uni.navigateTo=o=>routes.push(o.url)
 const p=mount('CloudNutritionChat.vue','load,askPrompt,question',h.deps);await p.load();await new Promise(setImmediate)
 const calls=h.calls.length;p.question.value='已有草稿'
 await p.askPrompt({id:'new-record-label',text:'换一种记录文案',action:'open_records'})
 assert.deepEqual(routes,['/pages/records/index']);assert.equal(p.question.value,'已有草稿');assert.equal(h.calls.length,calls);p.dispose()
})

test('busy suggestion controls cannot shuffle or overwrite the draft',async()=>{
 const h=chat(),p=mount('CloudNutritionChat.vue','load,prompts,sending,shufflePrompts,askPrompt,question',h.deps)
 await p.load();const ids=p.prompts.value.map(p=>p.id);p.sending.value=true;p.question.value='正在发送'
 p.shufflePrompts();await p.askPrompt({text:'另一个问题',action:'consultation'})
 assert.deepEqual(p.prompts.value.map(p=>p.id),ids);assert.equal(p.question.value,'正在发送');p.dispose()
})

test('an explicit tomorrow breakfast action binds the selected reference meal scope',async()=>{
 const h=chat(),opened=[],queries=[]
 h.deps.localDate=date=>date?'2026-10-21':'2026-10-20'
 h.deps.createHealthTaskFlow=({onChange})=>({hide(){},open:async(id,type,selection)=>{opened.push({id,type,selection});onChange({memberId:id,taskType:type,available:true,entry:{thread_id:thread,agent_slug:type==='consultation'?'health-consultation':'health-meal-planner'}})},submit:async text=>{queries.push(text);return true}})
 const p=mount('CloudNutritionChat.vue','load,question,sendQuestion,chatError',h.deps)
 await p.load();p.question.value='给我安排明天早餐';await p.sendQuestion('reference_meal_preview')
 const entry=opened.find(o=>o.type==='reference_meal_preview')
 assert.ok(entry);assert.equal(entry.id,member);assert.equal(entry.selection.plan_date,'2026-10-21')
 assert.deepEqual(entry.selection.participant_ids,['self']);assert.deepEqual(entry.selection.meal_types,['breakfast'])
 assert.deepEqual(queries,['给我安排明天早餐']);assert.equal(p.chatError.value,'');assert.equal(p.question.value,'');p.dispose()
})


test('meal revisions preserve tomorrow and family while explicit meals narrow the selected scope',async()=>{
 const h=chat(),opened=[],queries=[]
 h.deps.readDailyMealPlan=async(_family,date)=>queries.length?({status:'ready',date,version:0,meals:['breakfast','lunch','dinner'].map(meal_type=>({meal_type,source:{kind:'reference',id:'saved-plan'},meal:{dishes:[]},members:[{id:'parent'},{id:'self'}]}))}):({status:'absent',date,version:0,meals:[]})
 h.deps.localDate=date=>date?'2026-10-21':'2026-10-20'
 h.deps.loadCloudProfile=async()=>({onboarded:true,householdId:'family',selfMemberId:'self',members:[{id:'self',relation:'本人',healthMemberId:member},{id:'parent',relation:'母亲',healthMemberId:'parent-health'}]})
 h.deps.createHealthTaskFlow=({onChange})=>({hide(){},open:async(id,type,selection)=>{opened.push({id,type,selection});onChange({memberId:id,taskType:type,available:true,entry:{thread_id:thread,agent_slug:type==='consultation'?'health-consultation':'health-meal-planner'}})},submit:async text=>{queries.push(text);return true}})
 const p=mount('CloudNutritionChat.vue','load,question,sendQuestion,chatError',h.deps)
 await p.load();p.question.value='给全家安排明天三餐';await p.sendQuestion('reference_meal_preview')
 const count=opened.length,original=opened.at(-1).selection
 for(const [index,text] of ['把早餐改成粥','早餐换成不含鸡蛋的','把这个餐单换一下','这个食谱改成粥'].entries()){
  p.question.value=text;await p.sendQuestion()
  assert.equal(opened.length,count+1,text);assert.deepEqual(opened.at(-1).selection.meal_types,['breakfast']);assert.equal(p.chatError.value,'');assert.equal(p.question.value,'')
 }
 assert.deepEqual(original,{mode:'reference',family_id:'family',plan_date:'2026-10-21',participant_ids:['parent','self'],meal_types:['breakfast','lunch','dinner'],daily_base_version:0})
 assert.deepEqual(queries,['给全家安排明天三餐','把早餐改成粥','早餐换成不含鸡蛋的','把这个餐单换一下','这个食谱改成粥'])
 p.question.value='给我安排今天晚饭';await p.sendQuestion('reference_meal_preview')
 assert.equal(opened.length,count+2);assert.deepEqual(opened.at(-1).selection,{mode:'reference',family_id:'family',plan_date:'2026-10-20',participant_ids:['self'],meal_types:['dinner'],daily_base_version:0})
 p.question.value='换个话题，糖尿病家庭怎么吃？';await p.sendQuestion();assert.equal(opened.at(-1).type,'consultation')
 p.dispose()
})


test('plain answers to reference plan questions stay in the selected meal thread',async()=>{
 const h=chat(),opened=[],queries=[];let active
 h.deps.localDate=date=>date?'2026-10-21':'2026-10-20'
 h.deps.createHealthTaskFlow=({onChange})=>({hide(){},open:async(id,type,selection)=>{opened.push({id,type,selection});active={memberId:id,taskType:type,available:true,entry:{thread_id:thread,agent_slug:type==='consultation'?'health-consultation':'health-meal-planner'}};onChange(active)},submit:async text=>{queries.push(text);onChange({...active,requestId,result:{type:'needs_input',questions:['请补充你的用餐偏好。']}});return true}})
 const p=mount('CloudNutritionChat.vue','load,question,sendQuestion,task,chatError',h.deps)
 await p.load();p.question.value='给我安排明天早餐';await p.sendQuestion('reference_meal_preview')
 const count=opened.length
 for(const text of ['清淡一点','两个人','家里有小米']){
  p.question.value=text;await p.sendQuestion();assert.equal(opened.length,count,text)
  assert.equal(p.task.value.taskType,'reference_meal_preview');assert.equal(p.chatError.value,'')
 }
 assert.deepEqual(queries,['给我安排明天早餐','清淡一点','两个人','家里有小米'])
 p.question.value='换个话题';await p.sendQuestion();assert.equal(opened.at(-1).type,'consultation');p.dispose()
})


test('public chat shell is immediately present while fresh private entry data remains required for sending',async()=>{
 const h=chat();let resolveProfile
 h.deps.chatPresentation=chatPresentation
 h.deps.loadCloudProfile=()=>new Promise(resolve=>resolveProfile=resolve)
 const p=mount('CloudNutritionChat.vue','load,question,sendQuestion,presentation,entryReady,profileLoading,chatBusy,messages',h.deps)
 const cold=p.load()
 assert.equal(p.profileLoading.value,true);assert.equal(p.entryReady.value,false)
 assert.equal(p.presentation.value.welcome,true);assert.equal(p.chatBusy.value,true)
 p.question.value='你好';await p.sendQuestion();assert.equal(h.calls.filter(o=>o.path==='/api/agent/runs').length,0)
 resolveProfile({onboarded:true,selfMemberId:'self',householdId:'family',members:[{id:'self',relation:'本人',healthMemberId:member}]})
 await cold;assert.equal(p.entryReady.value,true)
 p.messages.value=[{id:'prior',role:'assistant',text:'same account result'}]
 p.hooks.hide();const warm=p.load()
 assert.equal(p.messages.value[0].text,'same account result');assert.equal(p.entryReady.value,false);assert.equal(p.chatBusy.value,true)
 resolveProfile({onboarded:true,selfMemberId:'self',householdId:'family',members:[{id:'self',relation:'本人',healthMemberId:member}]})
 await warm;assert.equal(p.entryReady.value,true);p.dispose()
})
