import test from 'node:test'
import assert from 'node:assert/strict'
import {createMealNutritionClient,mealNutritionState,recognizedMealDish,bindMealSource,exactMealSource} from '../src/services/meal-nutrition.js'
import {personalMeal} from '../src/services/cloud-meals.js'

test('per-dish personal weights map to one person without spreading a combined family weight',()=>{
 const dishes=[{name:'米饭',food_id:'rice',grams:150,portion_confirmed:true},{name:'鱼',recipe_version_id:'fish',grams:180,portion_confirmed:true}]
 const person={dishes:['米饭','鱼'],grams:330}
 const options={mealType:'dinner',eatenAt:'2026-11-04T18:00:00+08:00',captureScope:'单人餐盘'}
 const personal=personalMeal(dishes,person,options,()=> 'synthetic-id')
 assert.deepEqual(personal.items.map(i=>[i.grams,i.share_ratio,i.portion_source]),[[150,1,'manual'],[180,1,'manual']])
 const family=personalMeal(dishes,person,{...options,captureScope:'家庭共享桌菜'},()=> 'synthetic-id')
 assert(family.items.every(i=>i.grams===null&&i.share_ratio===null&&i.portion_source==='unknown'))
})
test('published portions remain estimated references rather than invented measured grams',()=>{
 const meal=personalMeal([{name:'米饭',food_id:'rice',portion_confirmed:true,portion_reference_id:'bowl',portion_count:1.5}],{dishes:['米饭']},{mealType:'dinner',eatenAt:'2026-11-04T18:00:00+08:00',captureScope:'单人餐盘'},()=> 'id')
 assert.equal(meal.items[0].grams,null);assert.equal(meal.items[0].portion_count,1.5);assert.equal(meal.items[0].portion_source,'estimated')
})
test('nutrition search returns versioned food and recipe options without binding them',async()=>{
 const state=mealNutritionState(),calls=[]
 const client=createMealNutritionClient({state,revision:()=>1,send:async o=>{calls.push(o);return {data:[{id:'food',type:'food',name:'合成鱼',dataset_version:'v1'},{id:'recipe',type:'recipe',name:'合成鱼',dataset_version:'v1'}]}}})
 await client.search(' 合成鱼 ','member');assert.deepEqual(state.sources.map(s=>s.type),['food','recipe']);assert.equal(calls.length,1)
 await client.portions({recipe_version_id:'recipe'});assert.match(calls[1].path,/recipe_version_id=recipe/)
 assert(calls.every(o=>!o.method));assert.deepEqual(state.results,[])
})
test('late nutrition cannot replace changed portions or a different account',async()=>{
 const state=mealNutritionState();let release,rev=1
 const client=createMealNutritionClient({state,revision:()=>rev,send:()=>new Promise(resolve=>release=resolve)})
 const first=client.preview([{memberId:'one',meal:{items:[]}}]);client.invalidate();release({data:{member_id:'one',totals:{energy_kcal:'100'}}});await first;assert.deepEqual(state.results,[])
 const second=client.preview([{memberId:'one',meal:{items:[]}}]);rev++;release({data:{member_id:'one',totals:{energy_kcal:'100'}}});await second;assert.deepEqual(state,mealNutritionState())
})
test('missing nutrition is preserved and preview never confirms a record or calls vision',async()=>{
 const state=mealNutritionState(),calls=[]
 const client=createMealNutritionClient({state,revision:()=>1,send:async o=>{calls.push(o);return {data:{member_id:'one',complete:false,totals:{energy_kcal:null}}}}})
 await client.preview([{memberId:'one',meal:{items:[{name:'未知菜'}]}}]);assert.equal(state.results[0].totals.energy_kcal,null)
 assert.equal(calls.length,1);assert.match(calls[0].path,/meal-nutrition-preview$/);assert.equal(state.results[0].complete,false)
})

test('restored whole-dish weight and oil are scaled to actual personal intake, unknown share stays unknown',()=>{
 const dish=recognizedMealDish({name:'旧菜谱',grams:'300',share_ratio:'0.5',portion_source:'estimated',adjustments:[{role:'oil',mode:'append',food_id:'oil',grams:'20'}]})
 assert.equal(dish.grams,150);assert.equal(dish.adjustments[0].grams,10);assert.equal(dish.portion_confirmed,true)
 assert.equal(dish.portion_source,'estimated')
 const unknown=recognizedMealDish({name:'旧菜谱',grams:'300',share_ratio:null,portion_source:'manual'})
 assert.equal(unknown.grams,null);assert.equal(unknown.portion_confirmed,false)
 const reference=recognizedMealDish({name:'饭',portion_reference_id:'bowl',portion_count:'2',share_ratio:0.5,portion_source:'estimated'})
 assert.equal(reference.portion_count,1);assert.equal(reference.grams,null)
})

test('nutrition preview and auxiliary source queries settle independently',async()=>{
 const state=mealNutritionState();let previewReply
 const client=createMealNutritionClient({state,revision:()=>1,send:o=>o.method==='POST'?new Promise(r=>previewReply=r):Promise.resolve({data:[]})})
 const reading=client.preview([{memberId:'one',meal:{items:[]}}]);await client.search('鱼','member')
 previewReply({data:{member_id:'one',complete:true,totals:{energy_kcal:'120'}}});await reading
 assert.equal(state.results[0].totals.energy_kcal,'120');assert.equal(state.busy,false)
 await client.search('鱼','member');assert.equal(state.results[0].totals.energy_kcal,'120')
})

test('opening an unmapped dish rejects another dishs late portion references',async()=>{
 const state=mealNutritionState();let reply
 const client=createMealNutritionClient({state,revision:()=>1,send:()=>new Promise(r=>reply=r)})
 const reading=client.portions({food_id:'A'});await client.portions({name:'B'})
 reply({data:[{id:'portion-A',food_id:'A'}]});await reading
 assert.deepEqual(state.portions,[]);assert.equal(state.portionBusy,false)
})

test('serialized source replacement clears the other source and obsolete portion/seasoning fields',()=>{
 const meal=personalMeal([{name:'鱼',food_id:'new-food',grams:100,portion_confirmed:true,adjustments:[]}],{dishes:['鱼']},{mealType:'dinner',eatenAt:'2026-11-04T18:00:00+08:00',captureScope:'单人餐盘'},()=> 'id')
 const combined={recipe_version_id:'old-recipe',portion_reference_id:'old-bowl',portion_count:1,adjustments:[{mode:'replace'}],...meal.items[0]}
 assert.equal(combined.recipe_version_id,null);assert.equal(combined.portion_reference_id,null);assert.deepEqual(combined.adjustments,[])
})


test('existing-source reference and serving count survive personal serialization and restoration',()=>{
 const ref={reference:'knowledge://kb/file#'+'a'.repeat(64),version:'b'.repeat(64)}
 const dish={name:'合成卷',grams:200,portion_confirmed:true,source_basis:'per100g',adjustments:[{role:'oil'}]}
 bindMealSource(dish,{id:ref.reference,type:'knowledge',nutrition_source:ref,name:'合成卷',basis:'per_serving',basis_label:'2 wraps'})
 assert.equal(dish.grams,null);assert.equal(dish.portion_confirmed,false);assert.deepEqual(dish.adjustments,[])
 Object.assign(dish,{servings:0.5,portion_confirmed:true})
 const meal=personalMeal([dish],{dishes:['合成卷']},{mealType:'dinner',eatenAt:'2026-11-04T18:00:00+08:00',captureScope:'单人餐盘'},()=> 'id')
 assert.deepEqual(meal.items[0].nutrition_source,ref);assert.equal(meal.items[0].servings,0.5);assert.equal(meal.items[0].grams,null)
 const restored=recognizedMealDish(meal.items[0]);assert.equal(restored.servings,0.5);assert.equal(restored.portion_confirmed,true)
 bindMealSource(dish,{id:'food',type:'food',name:'其他食物',basis:'per100g'})
 assert.equal(dish.nutrition_source,null);assert.equal(dish.servings,null);assert.equal(dish.portion_confirmed,false)
})

test('only an unambiguous exact food name may be auto mapped',()=>{
 const rows=[{name:'清蒸鱼｜Steamed fish',id:'one'}]
 assert.equal(exactMealSource('清蒸鱼',rows).id,'one')
 assert.equal(exactMealSource('鱼',rows),null)
 assert.equal(exactMealSource('清蒸鱼',[...rows,{name:'清蒸鱼',id:'two'}]),null)
})
