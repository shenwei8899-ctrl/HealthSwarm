import test from 'node:test'
import assert from 'node:assert/strict'
import {dishTitle,dishKey,mealNutrition,dishPortion,dishMemberPortions,canPurchaseAllMeals,mealTypes} from '../src/utils/meal-presentation.js'

const fullPlan=()=>({status:'ready',meals:mealTypes.map(type=>({meal_type:type,source:{kind:'reference',id:'saved'},meal:{dishes:[{name:type}]}})),purchase_options:[{kind:'reference',id:'saved',meal_types:[...mealTypes]}]})

test('all-meal purchase requires three populated meals in the displayed scope',()=>{
 const plan=fullPlan()
 assert.equal(canPurchaseAllMeals(plan),true)
 for(const scope of [['dinner'],['breakfast','lunch']])assert.equal(canPurchaseAllMeals(plan,scope),false)
 for(const type of mealTypes){
  const missing=fullPlan();missing.meals=missing.meals.filter(item=>item.meal_type!==type)
  assert.equal(canPurchaseAllMeals(missing),false)
  const empty=fullPlan();empty.meals.find(item=>item.meal_type===type).meal.dishes=[]
  assert.equal(canPurchaseAllMeals(empty),false)
 }
})

test('all-meal purchase requires a matching purchase source in a ready plan',()=>{
 assert.equal(canPurchaseAllMeals(null),false)
 assert.equal(canPurchaseAllMeals({...fullPlan(),status:'absent'}),false)
 assert.equal(canPurchaseAllMeals({...fullPlan(),purchase_options:[]}),false)
 assert.equal(canPurchaseAllMeals({...fullPlan(),purchase_options:[{kind:'reference',id:'stale',meal_types:[...mealTypes]}]}),false)
 assert.equal(canPurchaseAllMeals({...fullPlan(),purchase_options:[{kind:'reference',id:'saved',meal_types:[]}]}),false)
 // Every displayed meal must have a complete purchasing group.
 assert.equal(canPurchaseAllMeals({...fullPlan(),purchase_options:[{kind:'reference',id:'saved',meal_types:['dinner']}]}),false)
})

test('display titles preserve source names and dish identity',()=>{
 const dish={name:'亚洲风味清蒸三文鱼 | Asian-Style Steamed Salmon',file_id:'recipe',chunk_id:'part'}
 assert.equal(dishTitle(dish),'亚洲风味清蒸三文鱼')
 assert.match(dish.name,/Asian-Style/)
 assert.equal(dishKey(dish),'recipe:part:'+dish.name)
 assert.equal(dishTitle({name:'Salmon'}),'Salmon')
})

test('meal summary uses saved meal totals and never per-100g dish numbers',()=>{
 assert.deepEqual(mealNutrition({nutrition:{kcal:0,protein:null},dishes:[{nutrition:{energyKcal:200}}]}),[{key:'kcal',label:'能量',unit:'千卡',value:0}])
 assert.deepEqual(mealNutrition({nutrition:{kcal:NaN,protein:-1}}),[])
 assert.equal(dishPortion({memberNotes:[{dishes:[{dishId:'r',grams:120}]},{dishes:[{dishId:'r',grams:80}]}]},{id:'r'}),'本餐安排 200 克')
})

test('dish cards only use the recorded allocation for each member and exact dish',()=>{
 const dish={id:'recipe',dish_key:'display-key',portion_quote:'300 克',ingredients:[{planned_grams:'180'}]}
 const meal={memberNotes:[
  {memberId:'me',name:'我',dishes:[{dishId:'recipe',grams:100.5},{dishId:'other',grams:90}]},
  {memberId:'dad',name:'爸爸',dishes:[{dishId:'recipe',grams:150}]},
  {memberId:'mom',name:'妈妈',dishes:[{dishId:'recipe',grams:null}]},
  {memberId:'other',name:'家人',dishes:[{dishId:'display-key',grams:120}]}
 ]}
 assert.deepEqual(dishMemberPortions(meal,dish),[
  {memberId:'me',name:'我',grams:100.5},{memberId:'dad',name:'爸爸',grams:150}
 ])
 assert.deepEqual(dishMemberPortions({members:[{id:'me',name:'我'}]},dish),[])
})


test('single dish purchase scope carries exact dish and daily version',async()=>{
 const {savedPurchaseScope,addDishToMeal}=await import('../src/services/meal-dish-actions.js')
 const target={familyId:'f',date:'2026-11-02',mealType:'dinner',dailyPlanVersion:8}
 assert.deepEqual(savedPurchaseScope(target,[{dish_key:'fish'}]),{familyId:'f',date:'2026-11-02',mealType:'dinner',version:8,dishKeys:['fish']})
 const calls=[]
 await addDishToMeal(target,{dish_key:'fish'},'breakfast','request',async input=>{calls.push(input);return {data:{date:target.date,version:9,status:'ready'}}})
 assert.equal(calls.length,1);assert.match(calls[0].path,/daily-meal-plans\/2026-11-02\/dishes$/)
 assert.equal(calls[0].data.meal_type,'breakfast');assert.equal(calls[0].data.source_meal,'dinner')
 assert.equal(calls.some(c=>/diet|recording/.test(c.path)),false)
})

test('restoring a saved dinner answer retains dinner scope even if its receipt has three meals',async()=>{
 const {chatMessages}=await import('../src/services/cloud-chat.js')
 const result=chatMessages({history:[{id:'question',type:'human',content:'今天晚餐吃什么'},
  {id:'answer',type:'ai',content:JSON.stringify({preview_id:'saved',scope:'daily_reference',plan_date:'2026-11-02',meals:['breakfast','lunch','dinner'].map(meal_type=>({meal_type,dishes:[]}))})}]})
 assert.deepEqual(result[1].planMeals,['dinner'])
 assert.equal(result[1].planDate,'2026-11-02')
})

test('all-meal purchase rejects ingredient gaps and an explicitly unready meal',()=>{
 const partial=fullPlan();partial.purchase_options[0].gaps=[{ingredient:'salt',reason:'no_match'}]
 assert.equal(canPurchaseAllMeals(partial),false)
 const unready=fullPlan();unready.meals[2].purchase_ready=false
 assert.equal(canPurchaseAllMeals(unready),false)
})
