import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { compile, createSSRApp, ref, computed, watch } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { dishTitle, dishKey, recipeDisplay, ingredientLabels, referenceIngredientLabel, referenceGapDetail } from '../src/utils/meal-presentation.js'
import { detailState, createMealDetailClient } from '../src/services/meal-detail-client.js'
import { normalizeDishNutrition } from '../src/utils/dish-nutrition.js'
import { recipeCover } from '../src/utils/recipe-cover.js'
import { recipeTime, recipeIngredients, recipeNutrition } from '../src/utils/dish-commerce-presentation.js'
import { purchaseGroups, referencePurchaseFor } from '../src/services/meal-workspace.js'

const original = () => ({file_id:'file',chunk_id:'chunk',name:'Chicken Pasta',ingredients:['1 Tbsp olive oil','¼ tsp salt'],steps:['Cook about 2 minutes. Drain.'],nutrition_quote:'Calories: 452',step_images:['https://example.org/step1.jpg']})
const translated = () => ({...original(),translation_status:'ready',display_zh:{name:'鸡肉意面',ingredients:['橄榄油 1 汤匙','盐 1/4 茶匙'],steps:['煮约 2 分钟，然后沥干。'],nutrition_quote:'热量：452'}})

test('Chinese display preserves original recipe identity, units, purchase refs and step images',()=>{
 const dish=translated(),before=structuredClone(dish),view=recipeDisplay(dish)
 assert.equal(dishTitle(dish),'鸡肉意面')
 assert.equal(dishKey(dish),dishKey(original()))
 assert.deepEqual(view.ingredients,['橄榄油 1 汤匙','盐 1/4 茶匙'])
 assert.deepEqual(view.step_images,['https://example.org/step1.jpg'])
 assert.equal(referenceIngredientLabel(ingredientLabels([dish]),'¼ tsp salt'),'盐 1/4 茶匙')
 assert.deepEqual(dish,before)
 assert.equal(view.nutrition_quote,'热量：452')
 assert.equal(view.nutrition,undefined)
})

test('missing or incomplete translations show Chinese status while preserving original indexes',()=>{
 const dish=original()
 for(const current of [dish,{...dish,display_zh:{name:'鸡肉意面',ingredients:['橄榄油'],steps:[]}}]){
  const view=recipeDisplay(current)
  assert.equal(view.ingredients.length,2)
  assert.equal(view.steps.length,1)
  assert.ok(view.ingredients.every(text=>text==='中文译文暂未就绪'))
  assert.equal(view.nutrition_quote,'中文译文暂未就绪')
 }
 assert.equal(dishTitle(dish),'菜谱中文译文待补充')
})

async function guide(dish){
 const source=readFileSync(new URL('../src/components/CookingGuide.vue',import.meta.url),'utf8')
 const script=source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
 const template=source.match(/<template>([\s\S]*?)<\/template>/)[1]
 const props={dishes:[dish],continuous:true,action:''}
 const deps={recipeTime,recipeIngredients,recipeNutrition,computed,ref,watch,normalizeDishNutrition,dishTitle,recipeDisplay,recipeCover,defineProps:()=>props,defineEmits:()=>()=>{}}
 return renderToString(createSSRApp({render:compile(template,{isCustomElement:tag=>tag==='scroll-view'}),components:{FoodImageSlot:{props:['src'],template:'<img :src="src" />'},DishNutritionCard:{template:'<view />'}},setup(){
  const setup=new Function('deps',`const {${Object.keys(deps).join(',')}}=deps;${script};return {dish,display,cover,summary,notes,tab,nutritionOpen,key,name,ingredient,stepCopy,recipeTime,commerceIngredients,commerceNutrition}`)(deps)
  return {...props,...setup}
 }}))
}

test('actual cooking template renders Chinese recipe and original matching step image',async()=>{
 const html=await guide(translated())
 assert.match(html,/橄榄油 1 汤匙/)
 assert.match(html,/盐 1\/4 茶匙/)
 assert.match(html,/煮约 2 分钟/)
 assert.match(html,/热量：452/)
 assert.match(html,/https:\/\/example.org\/step1.jpg/)
 assert.doesNotMatch(html,/olive oil|Cook about|Calories:/)
})

test('merged detail renders exact merchant images and nutrition without replacing existing recipe steps',async()=>{
 const html=await guide({...translated(),cooking_minutes:15,
  ingredient_products:[{sku_id:12,product_name:'商城橄榄油',ingredient_refs:['1 Tbsp olive oil'],image_url:'https://example.org/oil.jpg'}],
  nutrition_highlights:[{sku_id:12,quote:'原商品营养摘录'}]})
 assert.match(html,/约 15 分钟/)
 assert.match(html,/https:\/\/example.org\/oil.jpg/)
 assert.match(html,/商城橄榄油/)
 assert.match(html,/原商品营养摘录/)
 assert.match(html,/橄榄油 1 汤匙/)
 assert.match(html,/煮约 2 分钟/)
 assert.match(html,/热量：452/)
})

test('historical recipe reads supplemental Chinese using the same saved receipt and makes no writes',async()=>{
 const state=detailState(),calls=[]
 const client=createMealDetailClient({state,context:()=> 'A',send:async request=>{
  calls.push(request)
  return {data:{preview_id:'old',plan_date:'2026-11-03',members:[],meals:[{meal_type:'dinner',dishes:[translated()]}]}}
 }})
 await client.open({familyId:'family',kind:'reference',date:'2026-11-03',mealType:'dinner',sourceId:'old',seed:{dishes:[original()]}})
 assert.equal(state.phase,'ready')
 assert.equal(dishTitle(state.meal.dishes[0]),'鸡肉意面')
 assert.equal(ingredientLabels(state.target.seed.dishes)['¼ tsp salt'],'盐 1/4 茶匙')
 assert.equal(calls.length,1)
 assert.equal(calls[0].path,'/api/health/v1/reference-meal-plans/old')
 assert.equal(calls[0].method,undefined)
})

test('closing or switching accounts discards supplemental historical responses',async()=>{
 let resolve,scope='A'
 const state=detailState(),client=createMealDetailClient({state,context:()=>scope,send:()=>new Promise(r=>resolve=r)})
 const opening=client.open({familyId:'family',kind:'reference',date:'2026-11-03',mealType:'dinner',sourceId:'old',seed:{dishes:[original()]}})
 scope='B';client.clear()
 resolve({data:{preview_id:'old',plan_date:'2026-11-03',meals:[{meal_type:'dinner',dishes:[translated()]}]}})
 await opening
 assert.equal(state.meal,null)
 assert.equal(state.open,false)
})

test('all-day reference purchases retain Chinese labels for ingredients belonging to later meals',()=>{
 const prior=globalThis.uni
 globalThis.uni={getStorageSync:()=>({accountId:'test',householdId:'family'})}
 try{
  const second={...translated(),ingredients:['1 C broccoli'],display_zh:{...translated().display_zh,ingredients:['西兰花 1 杯']}}
  const plan={date:'2026-11-03',version:1,meals:[
   {meal_type:'breakfast',source:{kind:'reference',id:'saved'},meal:{dishes:[translated()]}},
   {meal_type:'dinner',source:{kind:'reference',id:'saved'},meal:{dishes:[second]}},
  ],purchase_options:[{kind:'reference',id:'saved',meal_types:['breakfast','dinner'],items:[],gaps:[{ingredient:'1 C broccoli'}]}]}
  const group=purchaseGroups(plan)[0],purchase=referencePurchaseFor(group)
  assert.equal(purchase.ingredientLabels['1 C broccoli'],'西兰花 1 杯')
  assert.equal(purchase.gaps[0].ingredient,'1 C broccoli')
 }finally{globalThis.uni=prior}
})

test('actual meal overview keeps concise nutrition and Chinese dishes without preparation diagnostics',async()=>{
 const source=readFileSync(new URL('../src/components/MealDetailSheet.vue',import.meta.url),'utf8')
 const template=source.split('<template v-if="state.view===\'meal\'">')[1].split('</template>')[0]
 const html=await renderToString(createSSRApp({render:compile(template),components:{FoodImageSlot:{template:'<view />'}},setup:()=>({
  state:{meal:{members:[{name:'我'}],dishes:[translated()]}},nutritionSummary:[{key:'protein',label:'蛋白质',value:32,unit:'克'}],
  dishKey,dishTitle,recipeCover,showDish:()=>{},
 })}))
 assert.match(html,/鸡肉意面/)
 assert.match(html,/蛋白质 32 克/)
 assert.doesNotMatch(html,/食材准备说明|自行准备|tsp salt|看做法/)
 assert.equal(referenceGapDetail({reason:'needs_confirmation',detail:'SKU information missing'}),'请核对具体品种、形态和用量。')
 assert.equal(referenceGapDetail({reason:'no_match',detail:'No matching SKU'}),'商城商品名中暂未找到对应食材。')
})
