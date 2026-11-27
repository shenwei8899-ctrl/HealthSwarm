import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import * as Vue from 'vue'
import { parse, compileScript } from 'vue/compiler-sfc'
import { renderToString } from 'vue/server-renderer'
import { referenceNutritionItems } from '../src/utils/reference-serving.js'
import { recipeIngredients } from '../src/utils/dish-commerce-presentation.js'
import * as presentation from '../src/utils/dish-commerce-presentation.js'
import * as meals from '../src/utils/meal-presentation.js'
import * as nutrition from '../src/utils/dish-nutrition.js'
import * as covers from '../src/utils/recipe-cover.js'

test('only source recipe totals are shown; zero and unknown remain distinct', () => {
  const items = referenceNutritionItems({ nutrition_total: { basis: 'whole_dish', quantity_basis: 'source_recipe', energyKcal: 240, sodiumMg: 0 } })
  assert.equal(items[0].text, '240')
  assert.equal(items.find(x => x.key === 'sodiumMg').text, '0')
  assert.equal(items.find(x => x.key === 'proteinG').text, '暂未核算')
  for(const nutrition_total of [undefined,{basis:'whole_dish',energyKcal:500},{basis:'per_100g',quantity_basis:'source_recipe',energyKcal:100},{basis:'whole_dish',quantity_basis:'planned',energyKcal:500}]){
    const dish={nutrition_total,nutrition:{energyKcal:100},member_servings:[{nutrition:{energyKcal:170}}]}
    assert.ok(referenceNutritionItems(dish).every(x=>!x.available))
  }
})

test('ingredient display keeps source quantities and never appends planned amounts', () => {
  const dish = { name: '合成菜', ingredients: ['大米 100克', '水 适量'], steps: [],
    serving_suggestion: { ingredient_amounts: [{ position: 0, amount: 80, unit: '克' }] } }
  const rows = recipeIngredients(dish)
  const before = structuredClone(dish)
  assert.equal(rows[0].amount, '大米 100克')
  assert.equal(rows[1].amount, '水 适量')
  assert.deepEqual(dish, before)
})

const stub={render:()=>Vue.h('div')}
const modules={vue:Vue,'./FoodImageSlot.vue':{default:stub},'./DishNutritionCard.vue':{default:stub},
  '../utils/reference-serving.js':{referenceNutritionItems},'../utils/dish-commerce-presentation.js':presentation,
  '../utils/meal-presentation.js':meals,'../utils/dish-nutrition.js':nutrition,'../utils/recipe-cover.js':covers}
function loadComponent(name){
  const {descriptor}=parse(readFileSync(new URL('../src/components/'+name+'.vue',import.meta.url),'utf8'))
  let code=compileScript(descriptor,{id:'serving-test-'+name,inlineTemplate:true,templateOptions:{compilerOptions:{isCustomElement:tag=>['view','text','scroll-view','image'].includes(tag)}}}).content
  code=code.replace(/import\s+(\{[^}]*\}|[\w$]+)\s+from\s*['"]([^'"]+)['"]\s*;?/g,(_,binding,path)=>{
    assert.ok(modules[path],'missing test dependency '+path)
    return 'const '+(binding.startsWith('{')?binding.replace(/\bas\b/g,':'):'{default:'+binding+'}')+'=modules['+JSON.stringify(path)+'];\n'
  }).replace('export default','return')
  return new Function('modules',code)(modules)
}
const servingsComponent=loadComponent('ReferenceMemberServings')
const nutritionComponent=loadComponent('ReferenceDishNutrition')
modules['./ReferenceMemberServings.vue']={default:servingsComponent}
modules['./ReferenceDishNutrition.vue']={default:nutritionComponent}
const cookingComponent=loadComponent('CookingGuide')

test('rendered member card shows cooked grams without ingredient allocation',async()=>{
  const html=await renderToString(Vue.createSSRApp(servingsComponent,{servings:[{member_id:'a',name:'成员甲',cooked_grams:150,description:'备菜原料分配：原料甲100克'}]}))
  assert.match(html,/成员甲/);assert.match(html,/150/);assert.match(html,/熟食建议/)
  assert.doesNotMatch(html,/备菜原料分配|原料甲|原料分配用于备菜/)
})

test('rendered nutrition has one whole recipe basis and no selectors or member name',async()=>{
  const dish={nutrition_total:{basis:'whole_dish',quantity_basis:'source_recipe',energyKcal:240},member_servings:[{member_id:'a',name:'不应作为按钮的成员',nutrition:{energyKcal:170}}]}
  const html=await renderToString(Vue.createSSRApp(nutritionComponent,{dish}))
  assert.match(html,/整道菜合计/);assert.match(html,/按原食谱用量/);assert.match(html,/240/)
  assert.doesNotMatch(html,/<button|每100克|不应作为按钮的成员/)
  const old=await renderToString(Vue.createSSRApp(nutritionComponent,{dish:{nutrition_total:{basis:'whole_dish',energyKcal:999}}}))
  assert.doesNotMatch(old,/999/);assert.match(old,/暂未核算/)
})

test('reference cooking page suppresses its separate per100 summary but preserves source ingredients',async()=>{
  const dish={id:'a',recipe_id:'reference-a',name:'合成菜',recipe_text_source:'original',ingredients:['原料甲100克'],steps:['加热'],
    member_servings:[{member_id:'a',name:'成员甲',cooked_grams:150,description:'禁止重复的原料分配'}],
    serving_suggestion:{ingredient_amounts:[{position:0,amount:500,unit:'克'}]},
    nutrition:{basis:'per_100g',foodState:'cooked_edible',source:'calculated',energyKcal:100}}
  const html=await renderToString(Vue.createSSRApp(cookingComponent,{dishes:[dish],continuous:true}).component('scroll-view',stub))
  assert.match(html,/原料甲100克/);assert.match(html,/制作步骤/);assert.match(html,/成员甲/)
  assert.doesNotMatch(html,/每100克成品可食部分|本餐建议|禁止重复的原料分配/)
  const formal=await renderToString(Vue.createSSRApp(cookingComponent,{dishes:[{...dish,recipe_id:undefined}],continuous:true}).component('scroll-view',stub))
  assert.match(formal,/每100克成品可食部分/)
})
