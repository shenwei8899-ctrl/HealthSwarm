import test from 'node:test'
import assert from 'node:assert/strict'
import {ensureMealItemIds,createCapturePortionDraft,confirmCapturePortions,selectedIntakeDishes} from '../src/services/meal-item-intake.js'
import {personalMeal} from '../src/services/cloud-meals.js'
import {preserveMealEvidence} from '../src/services/meal-supplement.js'
const options={mealType:'dinner',eatenAt:'2026-11-24T18:00:00+08:00',captureScope:'家庭共享桌菜'}
const dishes=()=>[{item_id:'a',name:'同名菜',food_id:'food-a'},{item_id:'b',name:'同名菜',food_id:'food-b'}]
const person=id=>({memberId:id,name:id,selected:true,dishes:['同名菜'],portion:'不确定',grams:''})
test('same-named dishes and members retain independent personal gram values',()=>{
 const foods=dishes(),draft=createCapturePortionDraft([person('one'),person('two')],foods)
 draft[0].rows[0].grams='150';draft[0].rows[0].portion='一般';draft[0].rows[1].selected=false
 draft[1].rows[0].grams='80';draft[1].rows[1].grams='60'
 const [one,two]=confirmCapturePortions(draft,foods)
 assert.deepEqual(personalMeal(foods,one,options).items.map(i=>[i.item_id,i.grams,i.share_ratio]),[['a',150,1]])
 assert.deepEqual(personalMeal(foods,two,options).items.map(i=>[i.item_id,i.grams,i.share_ratio]),[['a',80,1],['b',60,1]])
 assert.match(personalMeal(foods,one,options).items[0].uncertainties.join('\n'),/本人粗略份量：一般/)
})
test('opening and cancelling a draft cannot mutate confirmed personal intake',()=>{
 const p=person('one'),foods=dishes(),before=structuredClone(p),draft=createCapturePortionDraft([p],foods)
 draft[0].rows[0].grams=222;draft[0].noneConfirmed=true;assert.deepEqual(p,before)
})
test('legacy combined grams and overall portion never become per-dish measurements',()=>{
 const foods=[{item_id:'a',name:'菜A'},{item_id:'b',name:'菜B'}],p={...person('one'),dishes:['菜A','菜B'],grams:'300',portion:'较多'}
 const draft=createCapturePortionDraft([p],foods);assert.equal(draft[0].legacyTotal,'300')
 assert.deepEqual(draft[0].rows.map(r=>[r.grams,r.portion]),[['','不确定'],['','不确定']])
 const meal=personalMeal(foods,confirmCapturePortions(draft,foods)[0],options)
 assert.ok(meal.items.every(i=>i.grams===null&&i.share_ratio===null));assert.ok(meal.items.every(i=>!i.uncertainties.some(s=>s.includes('合计重量'))))
})
test('a single legacy personal gram value stays attached to its one dish',()=>{
 const food=[{item_id:'a',name:'菜A'}],draft=createCapturePortionDraft([{...person('one'),dishes:['菜A'],grams:'120',portion:'一般'}],food)
 assert.equal(personalMeal(food,confirmCapturePortions(draft,food)[0],options).items[0].grams,120)
})
test('shared table photo estimates are not assigned to every family member',()=>{
 const food=[{item_id:'a',name:'同名菜',grams:500,portion_confirmed:true,portion_source:'estimated'}]
 const draft=createCapturePortionDraft([person('one'),person('two')],food,false)
 assert.ok(draft.every(p=>p.rows[0].grams===''))
})
test('single plate source amount is preserved until explicitly cleared or changed',()=>{
 const food=[{item_id:'a',name:'同名菜',food_id:'food',grams:100,portion_source:'estimated',portion_confirmed:true}]
 const draft=createCapturePortionDraft([person('one')],food,true)
 let p=confirmCapturePortions(draft,food)[0];assert.equal(personalMeal(food,p,options).items[0].portion_source,'estimated')
 draft[0].rows[0].grams='';p=confirmCapturePortions(draft,food)[0];assert.equal(personalMeal(food,p,options).items[0].grams,null)
 draft[0].rows[0].grams='180';p=confirmCapturePortions(draft,food)[0];assert.equal(personalMeal(food,p,options).items[0].portion_source,'manual')
})
test('changing nutrient source cannot retain a former serving conversion',()=>{
 const food=[{item_id:'a',name:'同名菜',source_basis:'per_serving',servings:2,portion_confirmed:true,portion_source:'manual',nutrition_source:{reference:'old'}}]
 const draft=createCapturePortionDraft([person('one')],food,true)
 const p=confirmCapturePortions(draft,food)[0];food[0].nutrition_source={reference:'new'}
 const meal=personalMeal(food,p,options);assert.equal(meal.items[0].servings,null);assert.equal(meal.items[0].grams,null)
})
test('invalid per-item grams cannot be accepted or silently turned into unknown',()=>{
 for(const value of ['0','-1','NaN','Infinity','10001','1e2']){
  const food=dishes(),draft=createCapturePortionDraft([person('one')],food);draft[0].rows[0].grams=value
  assert.throws(()=>confirmCapturePortions(draft,food),/实际克数/)
 }
})
test('none eaten produces no selected intake and requires explicit confirmation',()=>{
 const food=dishes(),draft=createCapturePortionDraft([person('one')],food);draft[0].rows.forEach(r=>r.selected=false)
 assert.throws(()=>confirmCapturePortions(draft,food),/勾选/);draft[0].noneConfirmed=true
 const p=confirmCapturePortions(draft,food)[0];assert.deepEqual(selectedIntakeDishes(p,food),[]);assert.throws(()=>personalMeal(food,p,options),/未吃/)
})
test('deleted or replaced item IDs cannot inherit a stale personal weight',()=>{
 const food=dishes(),draft=createCapturePortionDraft([person('one')],food);draft[0].rows[0].grams=180
 assert.throws(()=>confirmCapturePortions(draft,[{item_id:'replacement',name:'同名菜'}]),/勾选|变化/)
})
test('IDs are assigned once and existing photo item IDs are never replaced',()=>{
 const food=[{name:'菜A'},{name:'菜B',item_id:'photo-id'}];let ids=0;ensureMealItemIds(food,()=>String(++ids));ensureMealItemIds(food,()=>String(++ids))
 assert.equal(ids,1);assert.equal(food[1].item_id,'photo-id')
})
test('personal gram edits preserve original photo and location associations',()=>{
 const food=dishes(),draft=createCapturePortionDraft([person('one')],food);draft[0].rows[0].grams=130
 const meal=personalMeal(food,confirmCapturePortions(draft,food)[0],options)
 const original={...meal,photos:[{upload_id:'synthetic-photo'}],items:meal.items.map(i=>({...i,locations:[{image_index:0}]}))}
 const saved=preserveMealEvidence(meal,original);assert.deepEqual(saved.photos,original.photos);assert.deepEqual(saved.items[0].locations,[{image_index:0}]);assert.equal(saved.items[0].grams,130)
})
