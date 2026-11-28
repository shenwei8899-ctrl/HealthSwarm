import test from 'node:test'
import assert from 'node:assert/strict'
import {createDishSwap,dishSwapState,watchDishSwap} from '../src/services/dish-swap.js'
import {readFileSync} from 'node:fs'
import {compile,createSSRApp,ref,reactive,nextTick} from 'vue'
import {renderToString} from 'vue/server-renderer'

const day='2026-11-28'
const dish=key=>({dish_key:key,name:key,origin:{source:{kind:'reference'}}})
const breakfast={meal_type:'breakfast',meal:{dishes:[dish('rice')]}}
const dinner={meal_type:'dinner',meal:{dishes:[dish('fish')]}}
const plan={date:day,version:3,status:'ready',meals:[breakfast,dinner]}
const flush=()=>new Promise(setImmediate)
function fixture(){
 const state=dishSwapState(),requests=[];let scope='A'
 const client=createDishSwap({state,day:()=>day,context:()=>scope,family:()=> 'family',send:options=>new Promise((resolve,reject)=>requests.push({options,resolve,reject})),schedule:()=>1,cancel(){}})
 const resolve=(index,meal,key,rows=1)=>requests[index].resolve({data:{date:day,version:3,meals:[{meal_type:meal,dishes:[{dish_key:key,candidates:Array.from({length:rows},(_,i)=>({candidate_id:key+i,dish:{name:key+i}}))}]}]}})
 return {state,client,requests,resolve,switchAccount:()=>{scope='B'}}
}

test('entry opens before candidates arrive, coalesces clicks, and closing does not reopen on late response',async()=>{
 const h=fixture()
 try{
  h.client.open(breakfast,breakfast.meal.dishes[0],plan)
  assert.equal(h.state.open,true);assert.equal(h.state.target.status,'loading')
  h.client.open(breakfast,breakfast.meal.dishes[0],plan);await flush()
  assert.equal(h.requests.length,1);assert.match(h.requests[0].options.path,/meal_type=breakfast&dish_key=rice/)
  h.client.close();h.resolve(0,'breakfast','rice');await flush()
  assert.equal(h.state.open,false)
  h.client.open(breakfast,breakfast.meal.dishes[0],plan)
  assert.equal(h.state.target.status,'ready');assert.equal(h.requests.length,1)
 }finally{h.client.clear()}
})

test('one blocked meal does not prevent clicked dish loading and partial replies merge',async()=>{
 const h=fixture()
 try{
  const prefetch=h.client.prepare(plan,['dinner']);await flush()
  h.client.open(breakfast,breakfast.meal.dishes[0],plan);await flush()
  assert.equal(h.requests.length,2)
  h.resolve(1,'breakfast','rice');await flush()
  assert.equal(h.state.target.status,'ready')
  assert.equal(h.client.candidates(breakfast,breakfast.meal.dishes[0],plan).length,1)
  h.resolve(0,'dinner','fish');await prefetch
  assert.equal(h.state.entries.length,2)
  assert.equal(h.client.candidates(breakfast,breakfast.meal.dishes[0],plan).length,1)
 }finally{h.client.clear()}
})

test('empty and failed reads are distinct and manual retry shares in-flight request',async()=>{
 const h=fixture()
 try{
  h.client.open(breakfast,breakfast.meal.dishes[0],plan);await flush()
  h.requests[0].reject(Error('offline'));await flush()
  assert.equal(h.state.target.status,'error');assert.match(h.state.target.error,/offline/)
  h.client.retry();h.client.retry();await flush();assert.equal(h.requests.length,2)
  h.resolve(1,'breakfast','rice',0);await flush()
  assert.equal(h.state.target.status,'empty');assert.equal(h.state.open,true)
 }finally{h.client.clear()}
})

test('late scoped replies after account change do not restore entries or choices',async()=>{
 const h=fixture();h.client.open(breakfast,breakfast.meal.dishes[0],plan);await flush()
 h.switchAccount();h.client.clear();h.resolve(0,'breakfast','rice');await flush()
 assert.equal(h.state.open,false);assert.deepEqual(h.state.entries,[])
})

test('actual sheet renders loading, empty, error and ready independently from images',async()=>{
 const source=readFileSync(new URL('../src/components/DishSwapSheet.vue',import.meta.url),'utf8')
 const render=compile(source.match(/<template>([\s\S]*?)<\/template>\s*<style/)[1])
 const show=async status=>renderToString(createSSRApp({render,setup:()=>({state:{open:true,target:{dish:dish('rice'),status,error:'offline',candidates:[]}},dishTitle:d=>d?.name,recipeCover:()=>null})}))
 assert.match(await show('loading'),/正在查找可换菜品/)
 assert.match(await show('empty'),/暂无符合本餐要求/)
 assert.match(await show('error'),/重新加载/)
 assert.doesNotMatch(await show('ready'),/正在查找可换菜品|暂无符合本餐要求|重新加载/)
})


test('visible-meal watcher only prefetches displayed dinner and same-meal click bypasses slow prefetch',async()=>{
 const h=fixture(),value=ref(plan),enabled=ref(true)
 const stop=watchDishSwap({client:h.client,plan:()=>value.value,enabled:()=>enabled.value,mealTypes:()=>['dinner']})
 try{
  await flush();assert.equal(h.requests.length,1);assert.match(h.requests[0].options.path,/meal_type=dinner$/)
  h.client.open(dinner,dinner.meal.dishes[0],plan);await flush()
  assert.equal(h.requests.length,2);assert.match(h.requests[1].options.path,/meal_type=dinner&dish_key=fish/)
  h.resolve(1,'dinner','fish');await flush();assert.equal(h.state.target.status,'ready')
  h.resolve(0,'dinner','fish',0);await flush()
  assert.equal(h.state.target.status,'empty');assert.deepEqual(h.state.target.candidates,[])
 }finally{stop()}
})
