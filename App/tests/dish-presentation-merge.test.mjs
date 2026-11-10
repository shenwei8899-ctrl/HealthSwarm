import test from 'node:test'
import assert from 'node:assert/strict'
import { mealPairingText, recipeTime, recipeIngredients, recipeNutrition } from '../src/utils/dish-commerce-presentation.js'
import { chatMessages } from '../src/services/cloud-chat.js'
import { publicImageUrl } from '../src/services/public-images.js'
import { createMealDetailClient, detailState } from '../src/services/meal-detail-client.js'

// Local contract fixtures only; these tests never call a server or create business data.
test('live and restored meal descriptions preserve the same backend text and meal scope', () => {
  const data = {preview_id:'saved',scope:'daily_reference',pairing_summary:'  原始搭配说明\n原始营养说明  ',meals:[{meal_type:'dinner'}]}
  const [answer] = chatMessages({history:[{id:'answer',type:'ai',content:JSON.stringify(data)}]})
  assert.equal(answer.text,mealPairingText(data))
  assert.equal(answer.text,'原始搭配说明\n原始营养说明')
  assert.deepEqual(answer.business.data,data)
  assert.equal(mealPairingText({pairing_summary:{text:'invalid'}}),'餐单已更新。')
  assert.equal(mealPairingText({pairing_summary:'  '}),'餐单已更新。')
})

test('time is displayed only from positive integer minutes', () => {
  assert.equal(recipeTime({cooking_minutes:20}),'约 20 分钟 · 含备菜')
  for(const cooking_minutes of [undefined,null,0,-1,'20',1.5,Infinity])assert.equal(recipeTime({cooking_minutes}),'制作时间待补充')
})

const recipe = () => ({ingredients:['tomato 1–2 portions','egg 2'],steps:['cook'],file_id:'source',chunk_id:'chunk',
  display_zh:{ingredients:['番茄 1–2 份','鸡蛋 2 个'],steps:['炒制']},
  ingredient_products:[{sku_id:12,product_name:'商城番茄',ingredient_refs:['tomato 1–2 portions'],image_url:'/uploads/tomato.jpg'}],
  nutrition_highlights:[{sku_id:12,quote:'<p>每100克含量 &amp; 原文</p>'},{sku_id:99,quote:'其他商品'}]})

test('ingredients match exact original references, preserve units, and never invent grams', () => {
  const dish=recipe(),before=structuredClone(dish),items=recipeIngredients(dish)
  assert.equal(items[0].name,'商城番茄');assert.equal(items[0].amount,'番茄 1–2 份')
  assert.equal(items[0].image,'/uploads/tomato.jpg');assert.equal(items[1].amount,'鸡蛋 2 个');assert.equal(items[1].skuId,'')
  assert.deepEqual(dish,before)
  dish.ingredient_products[0].ingredient_refs=['tomato']
  assert.equal(recipeIngredients(dish)[0].skuId,'')
})

test('translation guards and existing object ingredient quantities survive merging', () => {
  const dish=recipe();dish.display_zh.ingredients=['不完整译文']
  assert.equal(recipeIngredients(dish)[0].amount,'中文译文暂未就绪')
  assert.equal(recipeIngredients({ingredients:[{name:'原食材',planned_grams:20}]})[0].amount,'原食材 20g')
  assert.equal(recipeIngredients({ingredients:[{name:'原食材',planned_grams:null}]})[0].amount,'原食材')
})

test('nutrition quotes belong to this recipe SKU; missing or foreign quotes remain absent', () => {
  const dish=recipe()
  assert.deepEqual(recipeNutrition(dish),[{name:'商城番茄',skuId:12,quote:'每100克含量 & 原文'}])
  dish.nutrition_highlights[0].sku_id='12'
  assert.equal(recipeNutrition(dish).length,1)
  dish.ingredient_products[0].ingredient_refs=['unrelated']
  assert.deepEqual(recipeNutrition(dish),[])
  assert.deepEqual(recipeNutrition({}),[])
})

test('product-linked recipe ingredients expose every spec and product nutrition without choosing a SKU', () => {
  const dish={ingredients:['番茄 200克'],display_zh:{ingredients:['番茄 200克'],steps:[]},ingredient_products:[{
    product_id:'tomato',product_name:'番茄',ingredient_refs:['番茄 200克'],image_url:'/uploads/tomato.jpg',
    skus:[{sku_id:'small',sku_name:'500克',sale_status:'available'},{sku_id:'large',sku_name:'1千克',sale_status:'unavailable'}],
  }],nutrition_highlights:[{product_id:'tomato',quote:'富含商品资料中已填写的营养说明'}]}

  assert.deepEqual(recipeIngredients(dish)[0].skus.map(item=>item.sku_id),['small','large'])
  assert.deepEqual(recipeNutrition(dish),[{
    name:'番茄',productId:'tomato',quote:'富含商品资料中已填写的营养说明',
  }])
})

test('known legacy merchant images use the same gateway while source/static media remain intact', () => {
  const options={baseUrl:'https://gateway.example/',origin:'https://h5.example'}
  for(const path of ['/uploads/a.jpg','http://8.136.134.29/uploads/a.jpg'])assert.equal(publicImageUrl(path,options),'https://gateway.example/uploads/a.jpg')
  assert.equal(publicImageUrl('/minio/public/a.jpg',options),'https://gateway.example/minio/public/a.jpg')
  assert.equal(publicImageUrl('/static/a.jpg',options),'/static/a.jpg')
  assert.equal(publicImageUrl('/uploads/a.jpg',{baseUrl:'',origin:'https://h5.example'}),'https://h5.example/uploads/a.jpg')
})

test('selecting the second dish keeps its nutrition and SKU fields across detail reads', async () => {
  const state=detailState(),dish=recipe(),calls=[]
  const client=createMealDetailClient({state,context:()=> 'account',send:async input=>{
    calls.push(input)
    return {data:{status:'ready',date:'2026-11-05',version:4,meals:[{meal_type:'lunch',source:{kind:'reference',id:'saved'},meal:{dishes:[{name:'first'},dish]}}]}}
  }})
  await client.open({familyId:'family',date:'2026-11-05',mealType:'lunch',kind:'reference',sourceId:'saved',dailyPlanVersion:4,dishIndex:1,initialView:'dish'})
  assert.equal(state.phase,'ready');assert.equal(state.dishIndex,1)
  assert.deepEqual(recipeNutrition(state.meal.dishes[state.dishIndex]),recipeNutrition(dish))
  assert.equal(calls.length,1);assert.equal(calls[0].method,undefined)
})
