import test from 'node:test'
import assert from 'node:assert/strict'
import { createCloudMealSaver,personalMeal,readDietRecord,portionNote } from '../src/services/cloud-meals.js'
import { summarizeMeasurements,readMeasurements } from '../src/services/cloud-indicators.js'
import { chatMessages } from '../src/services/cloud-chat.js'
import { createHealthTaskFlow } from '../src/services/health-task-flow.js'
const ids={m:'11111111-1111-4111-8111-111111111111',t:'22222222-2222-4222-8222-222222222222',r:'33333333-3333-4333-8333-333333333333'}
const clone=v=>structuredClone(v),timeout=()=>Object.assign(new Error('timeout'),{code:'NETWORK_ERROR'})
const meal={meal_type:'lunch',eaten_at:'2026-10-20T12:00:00+08:00',items:[{item_id:ids.r,name:'米饭',grams:null,portion_source:'unknown'}],photos:[]}
function memory(){const values=new Map();return {getStorageSync:k=>clone(values.get(k)),setStorageSync:(k,v)=>values.set(k,clone(v))}}
test('shared dishes keep rough portions and one combined weight is never copied onto each dish',()=>{
 const dishes=[{name:'米饭'},{name:'青菜'}],person={dishes:['米饭','青菜'],portion:'少量',grams:'120'}
 const value=personalMeal(dishes,person,{mealType:'lunch',eatenAt:meal.eaten_at,captureScope:'家庭共享桌菜'},()=>ids.r)
 assert.deepEqual(value.items.map(i=>i.grams),[null,null]);assert.deepEqual(value.items.map(i=>i.share_ratio),[null,null]);assert.equal(portionNote(value.items[0]),'少量');assert.ok(value.items[0].uncertainties.includes('本人所选菜品合计重量：120g；各菜重量未知'))
 const single=personalMeal(dishes,{...person,dishes:['米饭']},{mealType:'lunch',eatenAt:meal.eaten_at,captureScope:'单人餐盘'},()=>ids.r)
 assert.equal(single.items[0].grams,120);assert.equal(single.items[0].portion_source,'manual')
})
function saverFixture(overrides={},storage=memory()){
 const calls=[],drafts=new Map(),records=new Map();let n=0
 const send=async o=>{calls.push(clone(o));const supplied=await overrides(o);if(supplied!==undefined)return supplied
  if(o.path.endsWith('/manual-drafts')){const draft={id:'draft-'+o.data.member_id,member_id:o.data.member_id,kind:'meal',version:1,payload:clone(o.data.meal)};drafts.set(draft.id,draft);return {data:draft}}
  if(o.path.includes('/vision/page'))return {data:{drafts:[...drafts.values()],drafts_next_offset:null}}
  if(o.path.endsWith('/calculate'))return {data:{draft_version:1,calculation_id:'calculation',complete:false}}
  if(o.path.endsWith('/confirm')){const mid=o.path.includes('draft-other')?'other':'self',id='record-'+mid;records.set(id,{id,source_version:1,snapshot:{meal}});return {data:{target_ids:[id],review_status:'confirmed'}}}
  if(o.path.includes('/diet-logs/page'))return {data:{records:[...records.values()],next_offset:null}}
  throw new Error('unexpected '+o.path)
 }
 const options={send,storage,revision:()=>1,newId:()=>String(++n)}
 return {calls,drafts,records,options,saver:createCloudMealSaver(options),storage}
}
test('lost confirmation resumes after page reconstruction with identical key and calculation',async()=>{
 let count=0;const h=saverFixture(o=>{if(o.path.endsWith('/confirm')&&++count===1)throw timeout()})
 await assert.rejects(h.saver.save([{memberId:'self',meal}],true),/timeout/)
 h.saver.hide();const fresh=createCloudMealSaver(h.options);const result=await fresh.save([],false)
 const confirms=h.calls.filter(c=>c.path.endsWith('/confirm'));assert.deepEqual(confirms[0],confirms[1]);assert.equal(h.calls.filter(c=>c.path.endsWith('/calculate')).length,1);assert.equal(result.rows[0].record.id,'record-self')
})
test('unknown non-idempotent draft creation is never blindly resubmitted',async()=>{
 let failed=false;const h=saverFixture(o=>{if(o.path.endsWith('/manual-drafts')&&!failed){failed=true;h.drafts.set('recovered',{id:'recovered',member_id:'self',kind:'meal',version:1,payload:clone(meal)});throw timeout()}})
 await assert.rejects(h.saver.save([{memberId:'self',meal}],true));const fresh=createCloudMealSaver(h.options);await fresh.save([],true)
 assert.equal(h.calls.filter(c=>c.path.endsWith('/manual-drafts')).length,1);assert.ok(h.calls.some(c=>c.path.endsWith('/meal-drafts/recovered/confirm')))
})
test('unknown creation with no matching server draft remains pending without duplicate write',async()=>{
 const h=saverFixture(o=>{if(o.path.endsWith('/manual-drafts'))throw timeout()})
 await assert.rejects(h.saver.save([{memberId:'self',meal}],true));await assert.rejects(h.saver.save([],true),/尚未确认/)
 assert.equal(h.calls.filter(c=>c.method==='POST').length,1);assert.equal(h.saver.read().rows[0].phase,'creating')
})
test('family partial save retains each receipt and never records a saved member twice',async()=>{
 let second=0;const h=saverFixture(o=>{if(o.path.includes('draft-other/confirm')&&++second===1)throw timeout()})
 await assert.rejects(h.saver.save([{memberId:'self',meal},{memberId:'other',meal}],true))
 assert.equal(h.saver.read().rows[0].phase,'saved');await createCloudMealSaver(h.options).save([],true)
 assert.equal(h.calls.filter(c=>c.path.includes('draft-self/confirm')).length,1);assert.equal(h.saver.read().rows.filter(r=>r.phase==='saved').length,2)
})
test('record reading follows authorized empty pages and rejects a missing record',async()=>{
 const calls=[];const value=await readDietRecord(ids.m,ids.r,async o=>{calls.push(o.path);return {data:calls.length===1?{records:[],next_offset:50}:{records:[{id:ids.r,source_version:3}],next_offset:null}}})
 assert.equal(value.source_version,3);assert.match(calls[1],/offset=50/)
 await assert.rejects(readDietRecord(ids.m,ids.r,async()=>({data:{records:[],next_offset:null}})),e=>e.code===404)
})
test('a lost photo draft update recovers the same original photo and saves once',async()=>{
 const storage=memory(),calls=[];let draft={id:'photo-draft',member_id:'self',review_status:'pending_confirmation',version:1,payload:{...meal,photos:[{image_index:0,upload_id:'original-upload',upload_page_index:0}]}},lost=true
 const intended=structuredClone(draft.payload);intended.items[0].uncertainties=['本人粗略份量：一般']
 const send=async o=>{calls.push(structuredClone(o));if(o.method==='PATCH'){draft={...draft,version:2,payload:structuredClone(o.data.meal)};if(lost){lost=false;throw timeout()}return {data:draft}}if(o.path.endsWith('/photo-draft'))return {data:structuredClone(draft)};if(o.path.endsWith('/calculate'))return {data:{calculation_id:'calculation',draft_version:2}};if(o.path.endsWith('/confirm'))return {data:{review_status:'confirmed',target_ids:['record']}};if(o.path.includes('/diet-logs/page'))return {data:{records:[{id:'record',source_version:2,snapshot:{meal:intended}}],next_offset:null}};throw new Error(o.path)}
 const options={send,storage,revision:()=>1,newId:()=>ids.r};const first=createCloudMealSaver(options)
 await assert.rejects(first.save([{memberId:'self',meal:intended,draftId:'photo-draft',draftVersion:1}],true));const group=await createCloudMealSaver(options).save([],true)
 assert.equal(calls.filter(c=>c.method==='PATCH').length,1);assert.equal(calls.filter(c=>c.path.endsWith('/confirm')).length,1);assert.equal(group.rows[0].record.snapshot.meal.photos[0].upload_id,'original-upload')
})
test('measurements separate fasting, postmeal and units; absent values do not count as zero',()=>{
 const groups=summarizeMeasurements([{condition:'fasting',unit:'mmol/L',glucose:5},{condition:'fasting',unit:'mmol/L',glucose:7},{condition:'fasting',unit:'mmol/L',glucose:null},{condition:'after_meal_2h',unit:'mmol/L',glucose:10}], 'blood_glucose')
 assert.equal(groups.length,2);assert.equal(groups[0].statistics.glucose.mean,6);assert.equal(groups[0].statistics.glucose.count,2);assert.equal(groups[1].statistics.glucose.mean,10)
})
test('measurement reads require identity and a valid bounded range before issuing HTTP',async()=>{
 let writes=0;const send=async()=>{writes++;return {data:{items:[]}}}
 await assert.rejects(readMeasurements('','', 'weight','2026-10-01','2026-10-20',send));await assert.rejects(readMeasurements('f','m','weight','2026-10-20','2026-10-01',send));assert.equal(writes,0)
})
test('chat history preserves server role/order and images without meal writes',()=>{
 const rows=chatMessages({history:[{id:'1',type:'human',content:'看看',image_content:'data:image/png;base64,QQ==',request_id:ids.r},{id:'2',type:'ai',content:'请补充'}]})
 assert.deepEqual(rows.map(r=>r.role),['user','assistant']);assert.equal(rows[0].image.localPath,'data:image/png;base64,QQ==');assert.equal(rows[0].requestId,ids.r)
})
function chatFixture(){const calls=[],storage=memory();let runFailure=false
 const send=async o=>{calls.push(clone(o));if(o.path.endsWith('/members'))return {data:[{id:ids.m,is_owner:true}]};if(o.path.endsWith('/readiness'))return {data:{capabilities:{member_id:ids.m},entries:[{entry_type:'consultation',status:'available'}]}};if(o.path.endsWith('/daily-conversations'))return {data:{days:[{date:'2026-10-20',thread_id:ids.t}]}};if(o.path==='/api/agent/runs'){if(runFailure)throw timeout();return {data:{request_id:ids.r,thread_id:ids.t}}}if(o.path.includes('/tasks/'))return {data:{request_id:ids.r,member_id:ids.m,task_type:'consultation',thread_id:ids.t,agent_slug:'health-consultation',request_status:'dispatched',execution_status:'failed',result:{result_type:'error',code:'provider_error'}}};throw new Error('unexpected '+o.path)}
 const flow=createHealthTaskFlow({send,session:()=>({accountId:'self',token:'test'}),revision:()=>1,storage,daily:true,day:()=> '2026-10-20',newId:()=>ids.r,subscribe:()=>()=>{}})
 return {flow,calls,fail:()=>runFailure=true}
}
test('returning to the daily conversation reuses history without creating a new thread or request',async()=>{
 const h=chatFixture();await h.flow.open(ids.m,'consultation');assert.equal(h.flow.getState().entry.thread_id,ids.t);h.flow.hide();await h.flow.open(ids.m,'consultation');assert.equal(h.calls.filter(c=>c.method==='POST').length,0)
})
test('image-only chat uses agent image content and a failed result cannot become a successful answer',async()=>{
 const h=chatFixture();await h.flow.open(ids.m,'consultation');await h.flow.submit('',false,['data:image/png;base64,QQ==']);const body=h.calls.find(c=>c.path==='/api/agent/runs').data;assert.equal(body.query,'');assert.deepEqual(body.image_content,['data:image/png;base64,QQ==']);assert.equal(h.flow.getState().result.type,'error');assert.ok(!h.calls.some(c=>/meal|vision|upload/.test(c.path)))
})
test('unknown image submit is resolved from the existing Task after returning without resubmission',async()=>{
 const h=chatFixture();await h.flow.open(ids.m,'consultation');h.fail();await h.flow.submit('',false,['data:image/png;base64,QQ==']);h.flow.hide();await h.flow.open(ids.m,'consultation'); // Task lookup settles the first request without rerunning.
 assert.equal(h.calls.filter(c=>c.path==='/api/agent/runs').length,1);assert.equal(h.flow.getState().canRetry,false)
})


test('daily planner threads use a separate request identity on the next Beijing date',async()=>{
 const storage=memory(),calls=[];let date='2026-10-20',n=0
 const send=async o=>{calls.push(clone(o));if(o.path.endsWith('/members'))return {data:[{id:ids.m,is_owner:true}]};if(o.path.endsWith('/readiness'))return {data:{capabilities:{member_id:ids.m},entries:[{entry_type:'meal_preview',status:'available'}]}};if(o.path.endsWith('/task-entries'))return {data:{...o.data,member_id:ids.m,thread_id:n===1?ids.t:ids.r,agent_slug:'health-meal-planner',entry_status:'ready',request_submit_url:'/api/agent/runs'}};throw Error(o.path)}
 const flow=createHealthTaskFlow({send,storage,daily:true,day:()=>date,session:()=>({accountId:'self',token:'test'}),revision:()=>1,newId:()=>++n===1?ids.t:ids.r})
 await flow.open(ids.m,'meal_preview');await flow.createEntry();assert.equal(flow.getState().entry.thread_id,ids.t)
 date='2026-10-21';await flow.open(ids.m,'meal_preview');assert.equal(flow.getState().entry,null);await flow.createEntry();assert.equal(flow.getState().entry.thread_id,ids.r);assert.equal(calls.filter(c=>c.path.endsWith('/task-entries')).length,2)
})

test('invalid daily consultation starts a fresh authorized thread instead of replaying the invalid daily UUID',async()=>{
 const storage=memory(),calls=[]
 const send=async o=>{calls.push(clone(o));if(o.path.endsWith('/members'))return {data:[{id:ids.m,is_owner:true}]};if(o.path.endsWith('/readiness'))return {data:{capabilities:{member_id:ids.m},entries:[{entry_type:'consultation',status:'available'}]}};if(o.path.endsWith('/daily-conversations'))return {data:{days:[{date:'2026-10-20',thread_id:ids.t}]}};if(o.path.endsWith('/task-entries'))return {data:{...o.data,member_id:ids.m,thread_id:ids.r,agent_slug:'health-consultation',entry_status:'ready',request_submit_url:'/api/agent/runs'}};throw Error(o.path)}
 const flow=createHealthTaskFlow({send,storage,daily:true,day:()=> '2026-10-20',session:()=>({accountId:'self',token:'test'}),revision:()=>1,newId:()=>ids.r})
 await flow.open(ids.m,'consultation');flow.invalidateThread();assert.equal(flow.getState().invalidated,true);await flow.open(ids.m,'consultation');assert.equal(flow.getState().entry,null);await flow.createEntry();assert.equal(flow.getState().entry.thread_id,ids.r);assert.ok(!calls.some(c=>c.path.endsWith('/daily-consultations')))
})

test('definite rejection can be corrected without repeating a previously saved family member',async()=>{
 let reject=true;const h=saverFixture(o=>{if(o.path.endsWith('/manual-drafts')&&o.data.member_id==='other'&&reject){reject=false;throw Object.assign(Error('invalid meal'),{code:422})}})
 await assert.rejects(h.saver.save([{memberId:'self',meal},{memberId:'other',meal}],true));assert.equal(h.saver.read().rows[0].phase,'saved');assert.equal(h.saver.read().rows[1].phase,'rejected')
 await assert.rejects(h.saver.save([],true),/重新核对/);assert.equal(h.saver.releaseRejected().editable,true)
 const corrected=clone(meal);corrected.items[0].name='corrected meal'
 const result=await h.saver.save([{memberId:'self',meal},{memberId:'other',meal:corrected}],true);assert.ok(result.rows.every(r=>r.phase==='saved'));assert.equal(h.calls.filter(c=>c.path.includes('draft-self/confirm')).length,1);assert.equal(h.calls.filter(c=>c.path.endsWith('/manual-drafts')).at(-1).data.meal.items[0].name,'corrected meal')
})

test('unknown meal writes cannot be released as a definite rejection',async()=>{
 const h=saverFixture(o=>{if(o.path.endsWith('/manual-drafts'))throw timeout()});await assert.rejects(h.saver.save([{memberId:'self',meal}],true));assert.equal(h.saver.releaseRejected(),null);assert.equal(h.saver.read().rows[0].phase,'creating')
})


test('a rejected row can release an unattempted photo row and confirm conflicts can be rechecked',async()=>{
 const storage=memory();storage.setStorageSync('meal-capture-pending',{rows:[{phase:'rejected',memberId:'a'},{phase:'patching',memberId:'b',draftId:'photo'}]});const saver=createCloudMealSaver({storage});assert.equal(saver.releaseRejected().editable,true)
 const h=saverFixture(o=>{if(o.path.endsWith('/confirm'))throw Object.assign(Error('version conflict'),{code:409})});await assert.rejects(h.saver.save([{memberId:'self',meal}],true));assert.equal(h.saver.read().rows[0].phase,'rejected');assert.equal(h.saver.releaseRejected().editable,true)
})
