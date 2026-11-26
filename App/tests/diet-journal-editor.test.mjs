import test from 'node:test'
import assert from 'node:assert/strict'
import {journalEditorState,createJournalEditor} from '../src/pages/records/journal-editor.js'
import {journalPageState,createJournalPageClient} from '../src/services/diet-journal-page.js'
const day='2026-11-25'
const make=(id,mealType='lunch',member_id='self')=>({id,member_id,source_version:1,snapshot:{meal:{meal_type:mealType,eaten_at:day+'T12:30:00+08:00',photos:[],items:[{item_id:id,name:id,uncertainties:[],grams:null,share_ratio:null,portion_source:'unknown'}]}}})
function fixture(){
 const page=journalPageState(),state=journalEditorState(),storage=new Map(),writes=[]
 let identity='account',next=0,failCreate=false,failRead=false,denyWithdraw=false,denied=0
 const records=[make('one'),make('two')]
 const client=createJournalPageClient({state:page,context:()=>identity,newId:()=>`request-${++next}`,storage:{getStorageSync:k=>storage.get(k),setStorageSync:(k,v)=>storage.set(k,v),getStorageInfoSync:()=>({keys:[...storage.keys()]})},send:async r=>{
  if(denyWithdraw&&r.path.endsWith('/withdraw'))throw Object.assign(new Error('denied'),{code:403})
  if(failRead&&!r.method)throw new Error('offline')
  if(r.method){writes.push(structuredClone(r));if(r.path.endsWith('diet-journal-recordings')){if(failCreate)throw new Error('network');return {data:make('created',r.data.meal.meal_type,r.data.member_id)}}
   return {data:{...make(r.path.split('/').at(-1)),source_version:2,snapshot:{meal:r.data.meal}}}}
  if(r.path.endsWith('/members'))return {data:[{id:'self',scopes:['diet_edit']},{id:'other',scopes:['diet_edit']}]}
  if(r.path.includes('diet-journal?'))return {data:{records:r.path.includes('/self/')&&r.path.includes(day)?records:[],recorded_dates:[]}}
  return {data:records.find(d=>r.path.includes('/'+d.id+'/'))}
 }})
 const editor=createJournalEditor({state,page,client,context:()=>identity,onDenied:()=>denied++})
 return {page,state,editor,records,writes,storage,failCreate:v=>failCreate=v,failRead:v=>failRead=v,denyWithdraw:v=>denyWithdraw=v,denied:()=>denied,switchAccount:()=>identity='different'}
}
test('meal dropdown switches records without relocating them and preserves each record draft',async()=>{
 const h=fixture();await h.editor.open({memberId:'self',day,mealType:'lunch'})
 h.state.draft.foodText='草稿午餐';await h.editor.select({mealType:'dinner'})
 assert.equal(h.state.record.id,'');assert.equal(h.state.draft.foodText,'')
 h.state.draft.foodText='草稿晚餐';await h.editor.select({mealType:'lunch'})
 assert.equal(h.state.draft.foodText,'草稿午餐');assert.equal(h.state.records.length,2)
 await h.editor.record('two');assert.equal(h.state.draft.foodText,'two')
 h.state.draft.foodText='第二条';await h.editor.record('one');assert.equal(h.state.draft.foodText,'草稿午餐')
 assert.equal(h.records[0].snapshot.meal.meal_type,'lunch');assert.equal(h.writes.length,0)
})
test('unknown creation freezes its body/key and is restored even when a record already appears',async()=>{
 const h=fixture();await h.editor.open({memberId:'self',day,mealType:'dinner'})
 h.state.draft.foodText='蒸蛋';h.state.draft.rows=[{key:'egg',text:'蒸蛋',portion:'一般',grams:'',original:null}]
 h.failCreate(true);assert.equal(await h.editor.save(),null);assert.ok(h.page.pending)
 await h.editor.select({mealType:'lunch'});assert.equal(h.state.mealType,'dinner')
 h.editor.clear();h.records.push(make('created','dinner'));await h.editor.open({memberId:'self',day,mealType:'dinner'})
 assert.equal(h.state.record.id,'');assert.equal(h.state.draft.foodText,'蒸蛋');assert.ok(h.page.pending)
 h.failCreate(false);await h.editor.save();assert.deepEqual(h.writes[0],h.writes[1]);assert.equal(h.page.pending,null)
})
test('member drafts remain separate and account changes clear private editor state',async()=>{
 const h=fixture();await h.editor.open({memberId:'self',day,mealType:'lunch'});h.state.draft.foodText='私人草稿'
 await h.editor.select({memberId:'other'});assert.equal(h.state.draft.foodText,'')
 await h.editor.select({memberId:'self'});assert.equal(h.state.draft.foodText,'私人草稿')
 h.switchAccount();assert.equal(await h.editor.save(),null);assert.equal(h.state.open,false);assert.equal(h.state.record,null)
})
test('save clears only the current draft and leaves the other meal untouched',async()=>{
 const h=fixture();await h.editor.open({memberId:'self',day,mealType:'dinner'});h.state.draft.foodText='未保存晚餐'
 await h.editor.select({mealType:'lunch'});await h.editor.save()
 await h.editor.select({mealType:'dinner'});assert.equal(h.state.draft.foodText,'未保存晚餐')
 assert.equal(h.writes.length,1);assert.equal(h.writes[0].method,'PATCH');assert.ok(h.writes[0].path.endsWith('/one'))
})

test('failed initial read can be retried, and denied withdrawal clears the editor and notifies its owner',async()=>{
 const h=fixture();h.failRead(true);await h.editor.open({memberId:'self',day,mealType:'lunch'})
 assert.equal(h.state.open,true);assert.equal(h.page.busy,false);assert.equal(h.state.draft,null)
 h.failRead(false);await h.editor.reload();assert.ok(h.state.draft)
 h.denyWithdraw(true);await h.editor.withdraw();assert.equal(h.state.open,false);assert.equal(h.state.record,null);assert.equal(h.denied(),1)
})
