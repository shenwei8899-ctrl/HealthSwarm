import test from 'node:test'
import assert from 'node:assert/strict'
import {createMealDetailClient,detailState,formalRoute,detailGesture} from '../src/services/meal-detail-client.js'
const target={kind:'formal',familyId:'family',date:'2026-10-28',mealType:'breakfast',sourceId:'saved',version:2,dailyPlanVersion:4}
const meal={type:'breakfast',members:[],dishes:[{id:'dish',name:'合成菜品',steps:['合成步骤']}]}
const receipt=(t=target)=>({data:{arrangement_id:t.sourceId,version:t.version,meal:{...meal,type:t.mealType}}})
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return{promise,resolve}}
test('sheet opens synchronously while a read is pending and performs no writes',async()=>{
 const state=detailState(),wait=deferred(),calls=[]
 const client=createMealDetailClient({state,context:()=> 'A',send:input=>{calls.push(input);return wait.promise}})
 const pending=client.open(target);assert.equal(state.open,true);assert.equal(state.phase,'loading');assert.equal(state.meal,null)
 wait.resolve(receipt());await pending;assert.equal(state.phase,'ready');assert.equal(state.meal.dishes[0].name,'合成菜品')
 assert.equal(calls.length,1);assert.equal(calls[0].method,undefined);assert.match(calls[0].path,/daily_plan_version=4$/)
})
test('late breakfast response cannot replace a subsequently opened dinner',async()=>{
 const first=deferred(),second=deferred(),state=detailState(),t={...target,mealType:'dinner'}
 let count=0;const client=createMealDetailClient({state,context:()=> 'A',send:()=>++count===1?first.promise:second.promise})
 const a=client.open(target),b=client.open(t);second.resolve(receipt(t));await b;first.resolve(receipt());await a
 assert.equal(state.target.mealType,'dinner');assert.equal(state.meal.type,'dinner')
})
test('closing or changing identity discards an in-flight detail read',async()=>{
 for(const action of ['close','identity']){const state=detailState(),wait=deferred();let scope='A'
 const client=createMealDetailClient({state,context:()=>scope,send:()=>wait.promise});const pending=client.open(target)
 if(action==='close')client.close();else scope='B'
 wait.resolve(receipt());await pending;assert.equal(state.meal,null)
 if(action==='close')assert.equal(state.open,false)
 }
})
test('wrong saved version or revoked permission cannot enable a detail action',async()=>{
 for(const send of [async()=>receipt({...target,version:9}),async()=>{throw Object.assign(new Error('授权已变化'),{code:403})}]){
  const state=detailState(),client=createMealDetailClient({state,context:()=> 'A',send});await client.open(target)
  assert.equal(state.phase,'error');assert.ok(state.error)
 }
})
test('reference read retains unknown nutrition and validates the exact daily source',async()=>{
 const state=detailState(),ref={...target,kind:'reference',sourceId:'preview',version:undefined}
 const item={meal_type:'breakfast',source:{kind:'reference',id:'preview'},members:[],meal:{dishes:[{name:'参考菜',ingredients:['食材适量'],steps:['原文步骤'],nutrition_quote:'原食谱说明'}]}}
 let version=4
 const client=createMealDetailClient({state,context:()=> 'A',send:async()=>({data:{status:'ready',date:target.date,version,meals:[item],purchase_options:[]}})})
 await client.open(ref);assert.equal(state.phase,'ready');assert.equal(state.meal.nutrition,undefined);assert.deepEqual(state.meal.dishes[0].ingredients,['食材适量'])
 version=5;await client.open(ref);assert.equal(state.phase,'error')
})
test('summary purchase preserves its meal set and all version bindings',()=>{
 assert.deepEqual(formalRoute({...target,purchaseMeals:['breakfast','dinner']}),{date:target.date,meal:'daily',meals:['breakfast','dinner'],arrangement:'saved',version:2,daily_plan_version:4})
})
test('reading down a long recipe never triggers sheet dismissal away from its top',()=>{
 assert.equal(detailGesture({delta:-60,expanded:false}),'expand')
 assert.equal(detailGesture({delta:120,expanded:true,scrollTop:180}),'none')
 assert.equal(detailGesture({delta:90,expanded:true,scrollTop:0}),'collapse')
 assert.equal(detailGesture({delta:90,expanded:false,scrollTop:0}),'close')
})
