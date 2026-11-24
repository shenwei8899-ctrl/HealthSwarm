import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {ref,computed,reactive,watch,nextTick} from 'vue'
import {createExclusivePlanBrowser,exclusiveBrowseState} from '../src/services/exclusive-plan-browser.js'
import {selectedDay,dayMeals,validPlanRoute} from '../src/services/plan-presentation.js'
import {ingredientCopy} from '../src/utils/dish-commerce-presentation.js'

function setup() {
  const hooks={},navigations=[]
  const fixture={tier_name:'标准型',days:Array.from({length:7},(_,i)=>i+1).map(day_no=>({day_no,meals:[
    {id:'breakfast-'+day_no,meal_type:'breakfast',recipe_name:'早餐'+day_no,ingredients:['燕麦 30g'],steps:['煮熟。'],recipe_snapshot:{}},
    {id:'lunch-'+day_no,meal_type:'lunch',recipe_name:'午餐'+day_no,ingredients:['鱼肉 100g',{name:'姜',planned_grams:2},null],steps:['蒸熟。'],recipe_snapshot:{image_url:'/saved.webp'}},
  ]}))}
  let current=true,clear
  const deps={ref,computed,reactive,watch,exclusiveBrowseState,createExclusivePlanBrowser:options=>createExclusivePlanBrowser({...options,later:()=>null}),storageContext:()=> 'family',selectedDay,dayMeals,validPlanRoute,ingredientCopy,
    onLoad:fn=>hooks.load=fn,onShow:fn=>hooks.show=fn,onHide:fn=>hooks.hide=fn,onUnload:fn=>hooks.unload=fn,
    getSession:()=>({householdId:'family'}),sessionRevision:()=>1,
    useCommercePage:fn=>{clear=fn;return {busy:ref(false),error:ref(''),run:work=>work(()=>current)}},
    recipeCover:snapshot=>snapshot?.image_url?{image_url:snapshot.image_url}:null,
    createExclusiveImageFlow:()=>({open(){},stop(){}}),exclusiveImages(){},
    planTiers:['economy','standard','premium'],readExclusivePreview:async()=>fixture,
    request:async({path})=>{
      if(!current)throw Object.assign(Error('授权已失效'),{code:403})
      if(path.endsWith('/directory'))return {data:{tier_name:'标准型',days:fixture.days.map(d=>({day_no:d.day_no,available:true,content_version:'c',version:'s'}))}}
      const match=path.match(/\/days\/(\d+)/)
      if(match){const day=fixture.days.find(d=>d.day_no===Number(match[1]));return {data:{day_no:day.day_no,version:'v'+day.day_no,unchanged:false,day}}}
      return {data:{items:[],tier_name:'标准型'}}
    },commerce:{},
    uni:{navigateTo:input=>navigations.push(input.url),navigateBack(){}},
  }
  const text=readFileSync(new URL('../src/pages/exclusive-plans/detail.vue',import.meta.url),'utf8')
  const script=text.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
  const page=new Function('deps',`const {${Object.keys(deps)}}=deps;${script};return {load,plan,period,dayNo,mealType,meal,panel,panelRecipe,selectedDishId,ingredientGroups,ingredientSummary,visible,selectDay,selectMeal,openRecipe,openIngredients,closePanel,purchase}`)(deps)
  hooks.load({group_id:'saved-group',tier:'standard'});page.visible.value=true
  return {...page,fixture,hooks,navigations,invalidate(){current=false;clear()}}
}

test('recipe panel uses the exact selected plan snapshot, including original ingredients, steps and media',async()=>{
  const p=setup();await p.load();p.selectMeal('lunch');p.openRecipe(p.meal.value.dishes[0])
  assert.equal(p.panel.value,'recipe');assert.equal(p.panelRecipe.value.name,'午餐1')
  assert.deepEqual(p.panelRecipe.value.steps,['蒸熟。']);assert.equal(p.panelRecipe.value.image_url,'/saved.webp')
  assert.equal(p.panelRecipe.value.recipe_text_source,'original')
  assert.equal(p.ingredientSummary(p.meal.value.dishes[0]),'鱼肉 100g · 姜 2g')
})
test('ingredient panel is scoped to the current meal and never invents categories or amounts',async()=>{
  const p=setup();await p.load();p.openIngredients()
  assert.deepEqual(p.ingredientGroups.value.map(g=>g.items),[['燕麦 30g']])
  p.selectMeal('lunch');assert.equal(p.panel.value,'');p.openIngredients()
  assert.deepEqual(p.ingredientGroups.value.map(g=>g.items),[['鱼肉 100g','姜 2g']])
  assert.equal(p.period.value,7)
})
test('day changes close the old panel, reset the meal and reject unavailable days',async()=>{
  const p=setup();await p.load();p.openRecipe(p.meal.value.dishes[0]);await p.selectDay(7);await nextTick()
  assert.equal(p.panel.value,'');assert.equal(p.selectedDishId.value,'');assert.equal(p.mealType.value,'breakfast')
  assert.equal(p.meal.value.dishes[0].recipe_name,'早餐7');p.selectDay(8);assert.equal(p.dayNo.value,7)
})
test('empty meals remain empty and cannot open an ingredient panel or an unrelated recipe',async()=>{
  const p=setup();await p.load();p.selectMeal('dinner');p.openIngredients();p.openRecipe(p.fixture.days[0].meals[0])
  assert.equal(p.panel.value,'');assert.equal(p.meal.value.dishes.length,0)
  p.selectMeal('unknown');assert.equal(p.mealType.value,'dinner')
})
test('hiding, reloading or invalidating a plan dismisses its panel and discards its recipe',async()=>{
  const p=setup();await p.load();p.openRecipe(p.meal.value.dishes[0]);p.hooks.hide()
  assert.equal(p.panelRecipe.value,null);assert.equal(p.panel.value,'')
  p.visible.value=true;p.openIngredients();await p.load();assert.equal(p.panel.value,'')
  p.openIngredients();p.invalidate();assert.equal(p.plan.value,null);assert.equal(p.panel.value,'')
  await p.load();assert.equal(p.plan.value,null)
})
test('purchase continues to use the entire saved plan regardless of the selected day or meal',async()=>{
  const p=setup();await p.load();await p.selectDay(7);p.selectMeal('lunch');p.purchase()
  assert.deepEqual(p.navigations,['/pages/exclusive-plans/detail?group_id=saved-group&tier=standard&purchase=1'])
})
