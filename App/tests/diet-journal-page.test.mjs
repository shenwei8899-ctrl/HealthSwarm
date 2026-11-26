import test from 'node:test'
import assert from 'node:assert/strict'
import { journalWeek, createJournalDraft, syncJournalDraft, journalDraftMeal, quantityText } from '../src/services/diet-journal-presentation.js'
import { journalPageState, createJournalPageClient } from '../src/services/diet-journal-page.js'

const record = () => ({ id: 'record', member_id: 'self', source_version: 2, snapshot: { meal: {
  meal_type: 'lunch', eaten_at: '2026-11-23T04:30:00Z', photos: [{upload_id:'original-photo'}], items: [
    {item_id:'noodle',name:'牛肉面',grams:200,share_ratio:.5,portion_source:'manual',locations:[{image_index:0}],uncertainties:['本人份量原文：一碗']},
    {item_id:'tea',name:'奶茶',grams:null,share_ratio:null,food_id:'old-map',uncertainties:['本人份量原文：一杯']},
  ],
} } })
test('calendar crosses year boundary using Beijing week', () => {
  assert.deepEqual(journalWeek('2027-01-01').map(d=>d.date),['2026-12-28','2026-12-29','2026-12-30','2026-12-31','2027-01-01','2027-01-02','2027-01-03'])
})
test('photo edit preserves original evidence and does not multiply personal weight twice', () => {
  const source=record(), draft=createJournalDraft(source)
  assert.equal(draft.rows[0].grams,100)
  draft.rows[0].grams='150';draft.rows[0].portion='少量';draft.date='2026-11-22'
  const meal=journalDraftMeal(source,draft)
  assert.equal(meal.eaten_at,'2026-11-22T12:30:00+08:00')
  assert.equal(meal.items[0].grams,150);assert.equal(meal.items[0].share_ratio,1)
  assert.deepEqual(meal.photos,source.snapshot.meal.photos)
  assert.deepEqual(meal.items[0].locations,source.snapshot.meal.items[0].locations)
  assert.match(quantityText(meal.items[0]),/150 g.*少量/)
})
test('changed text cannot borrow old food mapping, grams or photo locations', () => {
  const source=record(),draft=createJournalDraft(source)
  draft.foodText='奶茶 半杯\n牛肉面 一碗'
  syncJournalDraft(draft,()=> 'new-food')
  const meal=journalDraftMeal(source,draft)
  assert.equal(meal.items[0].name,'奶茶 半杯');assert.equal(meal.items[0].food_id,undefined)
  assert.equal(meal.items[0].grams,null);assert.deepEqual(meal.items[0].locations,[])
  assert.equal(meal.items[1].item_id,'noodle')
})
test('changed grams remove stale numeric weight from current description', () => {
  const source=record();source.snapshot.meal.items[0].uncertainties=['本人份量原文：200克']
  const draft=createJournalDraft(source);draft.rows[0].grams='150'
  const saved={...source,snapshot:{meal:journalDraftMeal(source,draft)}}
  assert.equal(quantityText(saved.snapshot.meal.items[0]),'150 g')
  assert.equal(createJournalDraft(saved).rows[0].text,'牛肉面')
})
test('editing grams cannot retain an unconvertible per-serving document reference', () => {
  const source=record(),item=source.snapshot.meal.items[0]
  Object.assign(item,{nutrition_source:{source_id:'per-serving-document'},servings:2,grams:null,share_ratio:1})
  const draft=createJournalDraft(source);draft.rows[0].grams='150'
  const saved=journalDraftMeal(source,draft).items[0]
  assert.equal(saved.nutrition_source,null);assert.equal(saved.servings,null);assert.equal(saved.grams,150)
})
function harness(send) {
  const state=journalPageState(), entries=new Map();let scope='first'
  const client=createJournalPageClient({state,send,context:()=>scope,newId:()=> 'stable-id',storage:{getStorageSync:k=>entries.get(k),setStorageSync:(k,v)=>entries.set(k,structuredClone(v))}})
  return {state,client,switchAccount(){scope='second'}}
}
test('unknown write response freezes request including version and deletes only after authoritative receipt',async()=>{
  const writes=[];let first=true
  const h=harness(async request=>{writes.push(structuredClone(request));if(first){first=false;throw Object.assign(new Error('timeout'),{code:'NETWORK_ERROR'})}return {data:{id:'record',source_version:3,status:'withdrawn'}}})
  h.state.detail=record()
  assert.equal(await h.client.mutate('withdraw'),null);assert.ok(h.state.pending)
  h.state.detail.source_version=7
  const result=await h.client.mutate('correct',{})
  assert.deepEqual(writes[0],writes[1]);assert.equal(result.withdrawn,true);assert.equal(h.state.pending,null)
})
test('new date response wins when old request finishes late',async()=>{
  let release
  const h=harness(async request=>request.path.includes('2026-11-22')?new Promise(r=>release=r):{data:{records:[{id:'new'}],recorded_dates:['2026-11-23']}})
  h.state.members=[{id:'self',scopes:['diet_edit']}]
  const old=h.client.load('self','2026-11-22');await h.client.load('self','2026-11-23')
  release({data:{records:[{id:'old'}],recorded_dates:['2026-11-22']}});await old
  assert.equal(h.state.records[0].id,'new');assert.equal(h.state.day,'2026-11-23')
})
test('account change clears private detail after pending read',async()=>{
  let release;const h=harness(()=>new Promise(r=>release=r))
  const pending=h.client.detail(record());h.switchAccount();release({data:record()});await pending
  assert.equal(h.state.detail,null);assert.equal(h.state.busy,false)
})
