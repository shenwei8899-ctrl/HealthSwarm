import test from 'node:test'
import assert from 'node:assert/strict'
import {captureMenuDishes} from '../src/services/capture-menu.js'
const id='11111111-1111-4111-8111-111111111111'
const plan=(dishes,kind='arrangement')=>({meals:[{meal_type:'lunch',source:{kind},meal:{dishes}}]})
test('menu import keeps exact recipe versions but never planned weights or nutrition',()=>{
 const dish=captureMenuDishes(plan([{name:'清蒸鱼',recipe_version_id:id,grams:300,nutrition:{energy_kcal:500}}]),'lunch').dishes[0]
 assert.deepEqual(dish,{name:'清蒸鱼',recipe_version_id:id,grams:null,portion_source:'unknown',portion_confirmed:false})
 assert.equal(captureMenuDishes(plan([{name:'清蒸鱼',recipe_version_id:id}],'reference'),'lunch').dishes[0].recipe_version_id,null)
})
test('same-name ambiguous recipes stay unknown even after a third duplicate',()=>{
 const dishes=[{name:'清蒸鱼',recipe_version_id:id},{name:'清蒸鱼',recipe_version_id:'22222222-2222-4222-8222-222222222222'},{name:'清蒸鱼',recipe_version_id:id}]
 const result=captureMenuDishes(plan(dishes),'lunch');assert.equal(result.dishes.length,1);assert.equal(result.dishes[0].recipe_version_id,null)
})
test('unready, stale, absent and snack menus give actionable notices without candidates',()=>{
 for(const [p,type,hint] of [[{meals:[]},'lunch',/还没有/],[{meals:[],pending:{status:'pending'}},'lunch',/准备/],[{...plan([{name:'饭'}]),needs_regeneration:['lunch']},'lunch',/失效/],[plan([{name:'饭'}]),'snack',/加餐/]]){
  const r=captureMenuDishes(p,type);assert.deepEqual(r.dishes,[]);assert.match(r.notice,hint)
 }
})
