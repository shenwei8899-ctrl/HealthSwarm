import test from 'node:test'
import assert from 'node:assert/strict'
import { createMealPhotoClient, photoState } from '../src/services/meal-photo-client.js'

const meal = { meal_type:'lunch',eaten_at:'2026-10-19T12:00:00+08:00',photos:[{image_index:0,upload_id:'photo',upload_page_index:0}],items:[{item_id:'item',name:'合成米饭',grams:null,share_ratio:null,locations:[{image_index:0,bbox:[0,0,1,1]}]}] }
const draft = () => ({id:'draft',member_id:'member',kind:'meal',version:1,review_status:'pending_confirmation',payload:structuredClone(meal)})
function setup(overrides={}, memory=new Map()) {
  const state=photoState(),calls=[];let rev=1,next=0
  let config={policy_version:'synthetic-v1',meal:{available:true,processor:'synthetic'},limits:{meal_images:3}}
  const send=async options=>{
    calls.push(structuredClone(options));const value=await overrides.send?.(options);if(value!==undefined)return value
    const path=options.path
    if(path.endsWith('/members'))return {data:[{id:'member',scopes:['diet_edit','ai_use']},{id:'other',scopes:['diet_edit']}]}
    if(path.endsWith('/configuration'))return {data:structuredClone(config)}
    if(path.includes('/vision/page'))return {data:{jobs:[],drafts:[],jobs_next_offset:null,drafts_next_offset:null}}
    if(path.endsWith('/processing-consents'))return {data:{accepted:true}}
    if(path.endsWith('/meal-photo-tasks'))return {data:{task_id:'task',execution_status:'pending'}}
    if(path.endsWith('/vision-tasks/task'))return {data:{task_id:'task',kind:'meal',execution_status:'completed',result_id:'draft'}}
    if(path.endsWith('/meal-drafts/draft')&&options.method==='PATCH')return {data:{...draft(),version:2,payload:options.data.meal}}
    if(path.endsWith('/meal-drafts/draft'))return {data:draft()}
    if(path.endsWith('/calculate'))return {data:{calculation_id:'calc',draft_version:state.draft.version,complete:true,totals:{energy_kcal:'120'}}}
    if(path.endsWith('/confirm'))return {data:{target_ids:['record'],review_status:'confirmed'}}
    if(path.includes('/diet-logs/page'))return {data:{records:[{id:'record',source_version:2,snapshot:{nutrition:{totals:{energy_kcal:'120'}}}}],next_offset:null}}
    throw new Error('unexpected '+path)
  }
  const client=createMealPhotoClient({state,send,revision:()=>rev,storage:{getStorageSync:k=>structuredClone(memory.get(k)),setStorageSync:(k,v)=>memory.set(k,structuredClone(v))},newId:()=>`key-${++next}`,upload:overrides.upload|| (async()=>({upload_id:'photo',purpose:'meal'}))})
  return {state,client,calls,memory,config,changeAccount:()=>rev++}
}
test('capture can reuse freshly authorized member list while still reading policy and drafts',async()=>{
  const h=setup()
  await h.client.open('member',[{id:'member',scopes:['diet_edit','ai_use']},{id:'hidden',scopes:[]}])
  assert.equal(h.state.memberId,'member')
  assert.deepEqual(h.state.members.map(m=>m.id),['member'])
  assert.ok(h.calls.some(c=>c.path.endsWith('/configuration')))
  assert.ok(h.calls.some(c=>c.path.includes('/vision/page')))
  assert.ok(!h.calls.some(c=>c.path.endsWith('/members')))
})
test('unconfigured service permits private upload but never sends consent or recognition',async()=>{
  const h=setup();h.config.meal.available=false;h.config.meal.reason='模型未配置'
  await h.client.open();await h.client.addPhoto('local');await h.client.start('lunch',meal.eaten_at,true)
  assert.match(h.state.error,/模型未配置/);assert.equal(h.state.uploads.length,1)
  assert.equal(h.calls.filter(c=>c.method==='POST').length,0)
})
test('recognition requires explicit current policy consent and AI scope',async()=>{
  const h=setup();await h.client.open();await h.client.addPhoto('local')
  await h.client.start('lunch',meal.eaten_at,false);assert.equal(h.calls.filter(c=>c.method==='POST').length,0)
  h.config.policy_version='v2';await h.client.start('lunch',meal.eaten_at,true)
  assert.match(h.state.error,/重新勾选/);assert.equal(h.calls.filter(c=>c.method==='POST').length,0)
  await h.client.open('other');await h.client.addPhoto('local');await h.client.start('lunch',meal.eaten_at,true)
  assert.match(h.state.error,/AI 使用授权/)
})
test('upload to task to corrected candidate calculation and explicit confirmation',async()=>{
  const h=setup();await h.client.open();await h.client.addPhoto('local');await h.client.start('lunch',meal.eaten_at,true)
  assert.equal(h.state.draft.id,'draft');assert.equal(h.state.saved,null)
  h.state.meal.items[0].grams=100;h.state.meal.items[0].share_ratio=1;h.client.changed()
  await h.client.calculate();assert.equal(h.state.calculation,null)
  await h.client.saveDraft('核对份量');assert.equal(h.state.draft.version,2)
  assert.deepEqual(h.state.meal.photos,meal.photos);assert.deepEqual(h.state.meal.items[0].locations,meal.items[0].locations)
  await h.client.calculate();assert.equal(h.calls.filter(c=>c.path.endsWith('/confirm')).length,0)
  await h.client.confirm(false);assert.equal(h.state.saved.id,'record');assert.equal(h.state.saved.source_version,2)
})
test('unknown task create survives reopen and replays the exact request',async()=>{
  let count=0;const h=setup({send:o=>{if(o.path.endsWith('/meal-photo-tasks')&&++count===1)throw Object.assign(new Error('timeout'),{code:'NETWORK_ERROR'})}})
  await h.client.open();await h.client.addPhoto('local');await h.client.start('lunch',meal.eaten_at,true)
  const original=structuredClone(h.state.pending.request);h.client.discard();await h.client.open();await h.client.retryPending()
  assert.deepEqual(h.calls.filter(c=>c.path.endsWith('/meal-photo-tasks')),[original,original]);assert.equal(h.state.pending,null)
})
test('unknown confirm survives reopen and does not recalculate or create a new key',async()=>{
  let count=0;const h=setup({send:o=>{if(o.path.endsWith('/confirm')&&++count===1)throw Object.assign(new Error('timeout'),{code:503})}})
  await h.client.open();await h.client.draft('draft');await h.client.calculate();await h.client.confirm(false)
  const original=structuredClone(h.state.pending.request);await h.client.open();await h.client.retryPending()
  assert.deepEqual(h.calls.filter(c=>c.path.endsWith('/confirm')),[original,original])
  assert.equal(h.calls.filter(c=>c.path.endsWith('/calculate')).length,1);assert.equal(h.state.saved.id,'record')
})
test('changes invalidate calculation and incomplete result needs explicit acceptance',async()=>{
  const h=setup();await h.client.open();await h.client.draft('draft');await h.client.calculate();h.client.changed()
  await h.client.confirm(true);assert.equal(h.state.calculation,null);assert.equal(h.calls.filter(c=>c.path.endsWith('/confirm')).length,0)
  await h.client.saveDraft('份量');await h.client.calculate();h.state.calculation.complete=false
  await h.client.confirm(false);assert.match(h.state.error,/明确接受/);await h.client.confirm(true);assert.equal(h.state.saved.id,'record')
})
test('version conflict discards stale preview and requires reload',async()=>{
  const h=setup({send:o=>{if(o.method==='PATCH')throw Object.assign(new Error('changed'),{code:409})}})
  await h.client.open();await h.client.draft('draft');h.client.changed();await h.client.saveDraft('纠正')
  assert.equal(h.state.conflict,true);assert.equal(h.state.pending,null);await h.client.calculate();assert.equal(h.state.calculation,null)
  await h.client.draft('draft');assert.equal(h.state.conflict,false)
})
test('late private response after account switch cannot repopulate state or storage',async()=>{
  let finish;const h=setup({send:o=>o.path.endsWith('/meal-drafts/draft')?new Promise(r=>finish=r):undefined})
  await h.client.open();const pending=h.client.draft('draft');h.changeAccount();finish({data:draft()});await pending
  assert.equal(h.state.draft,null);assert.equal(h.state.memberId,'');assert.equal(h.memory.size,0)
})
test('permission loss clears private state and recovery marker',async()=>{
  const h=setup({send:o=>{if(o.path.endsWith('/meal-drafts/draft'))throw Object.assign(new Error('revoked'),{code:403})}})
  await h.client.open();await h.client.addPhoto('local');await h.client.draft('draft')
  assert.equal(h.state.memberId,'');assert.equal(h.memory.get('meal-photo-flow:member'),null)
})
test('storage contains source IDs and requests but never candidate body or local image paths',async()=>{
  const h=setup();await h.client.open();await h.client.addPhoto('private-file');await h.client.start('lunch',meal.eaten_at,true)
  const saved=JSON.stringify([...h.memory.values()]);assert(!saved.includes('合成米饭'));assert(!saved.includes('private-file'))
})
test('late upload after leave does not attach to a different member',async()=>{
  let finish;const h=setup({upload:()=>new Promise(r=>finish=r)});await h.client.open()
  const pending=h.client.addPhoto('file');h.client.discard();finish({upload_id:'photo'});await pending;assert.deepEqual(h.state.uploads,[])
})

test('reopening preserves manually selected candidate instead of old task result',async()=>{
  const h=setup({send:o=>o.path.endsWith('/meal-drafts/second')?{data:{...draft(),id:'second'}}:undefined})
  await h.client.open();await h.client.job('task');await h.client.draft('second');await h.client.open()
  assert.equal(h.state.draft.id,'second');assert.equal(h.state.job,null)
})

test('changing candidates clears previous confirmation receipt',async()=>{
  const h=setup({send:o=>o.path.endsWith('/meal-drafts/second')?{data:{...draft(),id:'second'}}:undefined})
  await h.client.open();await h.client.draft('draft');await h.client.calculate();await h.client.confirm(false)
  assert.equal(h.state.saved.id,'record');await h.client.draft('second');assert.equal(h.state.saved,null)
})

test('definite quota rejection clears frozen request and allows changing member after reopen',async()=>{
  const h=setup({send:o=>{if(o.path.endsWith('/meal-photo-tasks'))throw Object.assign(new Error('任务额度已达上限'),{code:429})}})
  await h.client.open();await h.client.addPhoto('local');await h.client.start('lunch',meal.eaten_at,true)
  assert.equal(h.state.pending,null);assert.match(h.state.error,/额度/)
  await h.client.open();assert.equal(h.state.pending,null)
  h.client.removePhoto('photo');assert.equal(h.state.uploads.length,0)
  await h.client.open('other');assert.equal(h.state.memberId,'other')
})
