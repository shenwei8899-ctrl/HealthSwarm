import test from 'node:test'
import assert from 'node:assert/strict'
import {recognizedMealDish,bindMealSource} from '../src/services/meal-nutrition.js'
import {personalMeal} from '../src/services/cloud-meals.js'
import {readFileSync} from 'node:fs'
import {createMealPhotoClient,photoState} from '../src/services/meal-photo-client.js'

const estimate={draft_id:'draft',grams:'250',nutrients:{energy_kcal:'120',protein_g:'18',fat_g:'4',carbohydrate_g:'3',sodium_mg:'200'}}
const input={item_id:'fish',name:'清蒸鱼',photo_estimate:estimate,portion_source:'unknown',share_ratio:null,grams:null}
const person={dishes:['清蒸鱼']},options={mealType:'dinner',eatenAt:'2026-11-04T18:00:00+08:00',captureScope:'单人餐盘'}
test('photo estimate defaults to reference grams and persists unchanged as actual grams change',()=>{
 const dish=recognizedMealDish(input)
 assert.equal(dish.grams,250);assert.equal(dish.portion_source,'estimated');assert(dish.portion_confirmed)
 let meal=personalMeal([dish],person,options)
 assert.equal(meal.items[0].grams,250);assert.equal(meal.items[0].share_ratio,1);assert.deepEqual(meal.items[0].photo_estimate,estimate)
 dish.grams=150;dish.portion_source='manual';meal=personalMeal([dish],person,options)
 assert.equal(meal.items[0].grams,150);assert.equal(meal.items[0].photo_estimate.grams,'250')
})
test('whole table estimate never becomes each person intake and replacing source clears estimate',()=>{
 const dish=recognizedMealDish(input)
 const meal=personalMeal([dish],person,{...options,captureScope:'家庭共享桌菜'})
 assert.equal(meal.items[0].grams,null);assert.equal(meal.items[0].share_ratio,null)
 bindMealSource(dish,{id:'food',type:'food',name:'清蒸鱼'})
 assert.equal(dish.photo_estimate,null);assert.equal(dish.grams,250);assert.equal(dish.portion_source,'estimated')
 assert.equal(personalMeal([dish],person,options).items[0].photo_estimate,null)
})

const component=readFileSync(new URL('../src/components/CloudMealCapture.vue',import.meta.url),'utf8')
for(const failedRead of ['task','draft'])test(`re-recognition recovers ${failedRead} read failure without a second paid task`,async()=>{
 const vision=photoState(),cache=new Map(),config={policy_version:'v1',meal:{available:true,processor:'synthetic'}}
 Object.assign(vision,{memberId:'member',members:[{id:'member',scopes:['diet_edit','ai_use']}],config,consent:{memberId:'member',policy_version:'v1',processor:'synthetic',persisted:true}})
 let posts=0,failed=false
 const photoClient=createMealPhotoClient({state:vision,revision:()=>1,storage:{getStorageSync:k=>cache.get(k),setStorageSync:(k,v)=>cache.set(k,v)},newId:()=>`request-${posts+1}`,send:async o=>{
  if(o.path.endsWith('/configuration'))return {data:config}
  if(o.path.includes('/processing-consents'))return {data:{accepted:true,processor:'synthetic',policy_version:'v1'}}
  if(o.path.endsWith('/meal-photo-tasks')){posts++;return {data:{task_id:'new-task'}}}
  if(o.path.includes('/vision-tasks/')){if(failedRead==='task'&&!failed){failed=true;throw Object.assign(Error('read failed'),{code:503})}return {data:{task_id:'new-task',execution_status:'success',result_id:'new-draft'}}}
  if(o.path.includes('/meal-drafts/')){if(failedRead==='draft'&&!failed){failed=true;throw Object.assign(Error('read failed'),{code:503})}return {data:{id:'new-draft',member_id:'member',kind:'meal',payload:{items:[]},review_status:'pending_confirmation'}}}
  throw Error('unexpected '+o.path)
 }})
 const origin={value:{draft:{id:'old-draft'},meal:{photos:[{upload_id:'old-upload'}]}}}
 const useCandidates=()=>{if(vision.draft)origin.value.draft=vision.draft}
 const deps={supplement:{value:null},locked:{value:false},manualOpen:{value:false},saved:{value:null},epoch:0,storageContext:()=>1,captureLocked:{value:false},origin,vision,photoClient,mealType:{value:'dinner'},date:{value:'2026-11-04'},time:{value:'18:00'},dishes:{value:[]},notice:{value:''},useCandidates,pollResult:()=>{},job:async id=>{await photoClient.job(id);useCandidates()}}
 const body=component.slice(component.indexOf('async function reestimate(){'),component.indexOf('function useCandidates(){'))
 const reestimate=new Function('deps',`const {${Object.keys(deps).join(',')}}=deps;${body};return reestimate`)(deps)
 await reestimate();assert.equal(posts,1);assert.equal(origin.value.draft.id,'old-draft')
 await reestimate();assert.equal(posts,1);assert.equal(origin.value.draft.id,'new-draft')
})

test('a fresh shared-table recognition clears previous personal dishes and combined grams',()=>{
 const person={dishes:['鱼','饭'],grams:200,noneConfirmed:false,portion:'一般'}
 const deps={supplement:{value:null},locked:{value:false},manualOpen:{value:false},saved:{value:null},manualOpen:{value:false},saved:{value:null},vision:{memberId:'member',meal:{items:[{item_id:'chicken',name:'鸡肉',photo_estimate:estimate}]},draft:{id:'new',version:1}},origin:{value:{draft:{id:'old',version:1}}},hasDishes:{value:true},dishes:{value:[]},source:{value:''},captureScope:{value:'家庭共享桌菜'},selected:{value:[person]},people:{value:[person]},notice:{value:''},recognizedMealDish,queueNutrition:()=>{},matchCandidates:()=>{}}
 const body=component.slice(component.indexOf('function useCandidates(){'),component.indexOf('async function job('))
 new Function('deps',`const {${Object.keys(deps).join(',')}}=deps;${body};useCandidates()`)(deps)
 assert.deepEqual(person.dishes,[]);assert.equal(person.grams,'');assert.equal(deps.dishes.value[0].name,'鸡肉')
})

test('a late recognition start cannot clear dishes from a reopened page',async()=>{
 let release
 const dishes={value:[{name:'new page dish'}]},origin={value:{draft:{id:'new-page'}}},vision={job:null}
 const deps={supplement:{value:null},locked:{value:false},manualOpen:{value:false},saved:{value:null},storageContext:()=>1,captureLocked:{value:false},origin,vision,photoClient:{start:()=>new Promise(r=>release=r)},mealType:{value:'dinner'},date:{value:'2026-11-04'},time:{value:'18:00'},dishes,notice:{value:'new page'},useCandidates:()=>{throw Error('late adoption')},pollResult:()=>{throw Error('late polling')},job:()=>{}}
 const body=component.slice(component.indexOf('async function reestimate(){'),component.indexOf('function useCandidates(){'))
 const page=new Function('deps',`const {${Object.keys(deps).join(',')}}=deps;let epoch=0;${body};return {analyze,advance(){epoch++}}`)(deps)
 const pending=page.analyze();page.advance();vision.job={execution_status:'running'};release();await pending
 assert.equal(dishes.value[0].name,'new page dish');assert.equal(origin.value.draft.id,'new-page');assert.equal(deps.notice.value,'new page')
})
