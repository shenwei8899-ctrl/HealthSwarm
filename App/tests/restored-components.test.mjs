import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { ref,reactive,computed,nextTick,watch,effectScope } from 'vue'
import { createHealthTaskFlow,HEALTH_TEXT_TASKS } from '../src/services/health-task-flow.js'
import { photoState,createMealPhotoClient } from '../src/services/meal-photo-client.js'
import { createCloudMealSaver,mealDay,personalMeal,mealLabels } from '../src/services/cloud-meals.js'
import { mealInput } from '../src/services/health-meal-input.js'
import { dailyArrangementState } from '../src/services/daily-arrangement-client.js'
const jsonClone=v=>v===undefined?undefined:JSON.parse(JSON.stringify(v))
const member='11111111-1111-4111-8111-111111111111',thread='22222222-2222-4222-8222-222222222222',requestId='33333333-3333-4333-8333-333333333333'
function mount(file,fields,extras={}){
 const hooks={},deps={ref,reactive,computed,nextTick,watch,defineProps:()=>({route:{}}),onMounted:fn=>hooks.mount=fn,onShow:fn=>hooks.show=fn,onHide:fn=>hooks.hide=fn,onUnload:fn=>hooks.unload=fn,onUnmounted:fn=>hooks.unmount=fn,...extras}
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
  dailyArrangementState,scopedStorage:storage(),newHealthRequestId:()=>requestId,loadCloudProfile:async()=>({}),createDailyArrangementClient:()=>({reset(){},dispose(){}}),
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
  createDailyArrangementClient:({state})=>({load:async()=>{state.arrangement={id:'arrangement',version:1}},changeMembers:async()=>{state.arrangement=null;state.error='授权撤回'},reset(){},dispose(){}}),
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
 const send=async o=>{calls.push(jsonClone(o));if(o.path.endsWith('/members'))return {data:[{id:member,is_owner:true}]};if(o.path.endsWith('/readiness'))return {data:{capabilities:{member_id:member},entries:[{entry_type:'consultation',status:'available'}]}};if(o.path.endsWith('/daily-conversations'))return {data:{days:[{date:'2026-10-20',thread_id:thread}]}};if(o.path==='/api/agent/runs'){if(++submits===1)throw Object.assign(new Error('timeout'),{code:503});exists=true;return {data:{request_id:requestId,thread_id:thread}}}if(o.path.includes('/tasks/')){if(invalid)throw Object.assign(new Error('withdrawn'),{code:410});if(!exists)throw Object.assign(new Error('not yet'),{code:404});return {data:{member_id:member,thread_id:thread,request_id:requestId,task_type:'consultation',agent_slug:'health-consultation',request_status:'dispatched',execution_status:'completed',result:{result_type:'general_education_answer',scope:'general_education',answer:'private previous answer',citations:[]}}}};throw new Error(o.path)}
 const deps={HEALTH_TEXT_TASKS,loadCloudProfile:async()=>({onboarded:true,selfMemberId:'self',members:[{id:'self',relation:'本人',healthMemberId:member}]}),dailyArrangementState:()=>({phase:'idle',busy:false}),createDailyArrangementClient:({state})=>({load:async()=>{state.phase='ready';state.arrangement={}},reset(){},dispose(){}}),storageContext:()=> 'scope',scopedStorage:saved,getSession:()=>({accountId:'self',householdId:'family',token:'synthetic'}),commerce:{connect:async()=>{}},request:send,newHealthRequestId:()=>requestId,localDate:()=> '2026-10-20',readChatSnapshot:async()=>({messages:[],runs:[]}),chatImageContent:async image=>image.localPath,persistChatImage:async image=>({localPath:image.path}),createHealthTaskFlow:options=>createHealthTaskFlow({...options,send,session:()=>({accountId:'self',token:'synthetic'}),revision:()=>1,storage:saved,newId:()=>requestId,day:()=> '2026-10-20',subscribe:()=>()=>{}}),uni:{redirectTo(){},reLaunch(){},showToast(){}}}
 return {deps,calls,invalidate:()=>invalid=true}
}
test('unknown chat retry settles the original bubble and removes only its original draft',async()=>{
 const h=chat(),p=mount('CloudNutritionChat.vue','load,question,draftImage,messages,sendQuestion,retryQuestion,flow,task',h.deps)
 await p.load();p.question.value='original';p.draftImage.value={localPath:'data:image/png;base64,QQ=='};await p.sendQuestion();assert.equal(p.messages.value[0].status,'unknown');assert.equal(p.question.value,'original')
 await p.retryQuestion();assert.equal(p.question.value,'');assert.equal(p.draftImage.value,null);assert.equal(p.messages.value[0].status,'sent');assert.deepEqual(p.messages.value.map(m=>m.role),['user','assistant']);assert.equal(h.calls.filter(c=>c.path==='/api/agent/runs').length,2);p.dispose()
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


test('family meal question confirms actual participants and uses family arrangement instead of personal planner',async()=>{
 const h=chat(),actions=[];h.deps.loadCloudProfile=async()=>({onboarded:true,selfMemberId:'self',members:[{id:'self',relation:'本人',healthMemberId:member},{id:'parent',relation:'母亲'}]})
 h.deps.createDailyArrangementClient=({state})=>({load:async date=>{actions.push({action:'load',date});state.phase='ready';state.date=date;state.arrangement={}},changeMembers:async(type,ids)=>actions.push({action:'members',type,ids}),reset(){},dispose(){}})
 const p=mount('CloudNutritionChat.vue','load,question,sendQuestion,familySelection,familyMembers,familyPanel',h.deps);await p.load();p.question.value='今晚全家吃什么？';await p.sendQuestion();assert.equal(p.familyPanel.value,true);assert.deepEqual(p.familySelection.value.ids,['self','parent']);assert.equal(p.familySelection.value.type,'dinner');await p.familyMembers(['self','parent']);assert.deepEqual(actions.find(a=>a.action==='members'),{action:'members',type:'dinner',ids:['self','parent']});assert.equal(actions.filter(a=>a.action==='load').length,3);assert.ok(!h.calls.some(c=>c.path==='/api/agent/runs'||c.path.endsWith('/task-entries')));assert.equal(p.question.value,'');p.dispose()
})


test('extra family date or food constraints are preserved and never silently sent to personal planning',async()=>{
 const h=chat(),p=mount('CloudNutritionChat.vue','load,question,chatError,sendQuestion',h.deps);await p.load();p.question.value='给全家安排明天早餐，不要牛奶';await p.sendQuestion();assert.equal(p.question.value,'给全家安排明天早餐，不要牛奶');p.question.value='全家明天早餐不要牛奶';await p.sendQuestion();assert.equal(p.question.value,'全家明天早餐不要牛奶');assert.ok(p.chatError.value.includes('原问题已保留'));assert.ok(!h.calls.some(c=>c.path==='/api/agent/runs'||c.path.endsWith('/task-entries')));p.dispose()
})

test('family retry uses the original intent date and enables failed-task recovery',async()=>{
 const h=chat(),actions=[];h.deps.createDailyArrangementClient=({state})=>({load:async(date,retry)=>{actions.push({date,retry});state.phase='error';state.error='synthetic failure'},reset(){},dispose(){}})
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
 assert.match(p.chatError.value,/尚未配置开发测试模型/);assert.ok(!h.calls.length);assert.equal(p.task.value.available,undefined);p.dispose()
})

test('saved but unlinked profiles have a working reconfirmation route and cannot start planning',async()=>{
 const h=chat(),routes=[];h.deps.uni.navigateTo=o=>routes.push(o.url)
 h.deps.loadCloudProfile=async()=>({onboarded:true,selfMemberId:'self',members:[{id:'self',relation:'本人'}],defaultDiners:['self'],healthConfiguration:{consultation:{available:true},meal_plan:{available:true}}})
 const p=mount('CloudNutritionChat.vue','load,chatError,memberArchive,requirePlanningReady',h.deps);await p.load()
 assert.match(p.chatError.value,/家庭档案/);assert.throws(()=>p.requirePlanningReady(),e=>e.businessCode==='daily_member_sources_unavailable');p.memberArchive();assert.deepEqual(routes,['/pages/profile/member?id=self']);assert.ok(!h.calls.length);p.dispose()
})

test('both daily entry clients check configuration before starting, while reading stays allowed',async()=>{
 const h=chat(),clients=[]
 h.deps.createDailyArrangementClient=options=>{clients.push(options);return {load:async()=>{},reset(){},dispose(){}}}
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

test('a failed consultation can restart with a new thread while keeping an edited draft',async()=>{
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
 const p=mount('CloudNutritionChat.vue','load,flow,task,question,draftImage,draftError,restartChat',h.deps)
 await p.load();await p.flow.restoreRequest(requestId);assert.equal(p.task.value.status,'failed')
 p.question.value='修改后的问题';p.draftImage.value={localPath:'data:image/png;base64,QQ=='}
 await p.restartChat()
 assert.equal(p.task.value.entry.thread_id,newThread);assert.equal(p.question.value,'修改后的问题')
 assert.equal(p.draftImage.value.localPath,'data:image/png;base64,QQ==')
 assert.equal(calls.filter(c=>c.path.endsWith('/task-entries')).length,1)
 assert.equal(calls.some(c=>c.path==='/api/agent/runs'),false);p.dispose()
})
