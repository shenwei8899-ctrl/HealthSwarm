import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {reactive,ref,computed,nextTick,watch,effectScope} from 'vue'
import {detailState,createMealDetailClient,mealNames,formalRoute,detailKey} from '../src/services/meal-detail-client.js'

import {createTodayMealPlan,todayMealPlanState} from '../src/services/today-meal-plan.js'

const sheetSource=readFileSync(new URL('../src/components/MealDetailSheet.vue',import.meta.url),'utf8')
const routeSource=readFileSync(new URL('../src/pages/meals/detail.vue',import.meta.url),'utf8')
const script=source=>source.split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm,'')
const target={kind:'formal',familyId:'family',date:'2026-11-03',mealType:'dinner',sourceId:'saved',version:2,dailyPlanVersion:4}
const meal={type:'dinner',members:[],dishes:[{name:'合成测试菜品'}]}

function harness({stack=2,backThrows=false,fallbackThrows=false}={}){
 const scope=effectScope(),calls=[],events=[],hooks={},timers=new Map(),props=reactive({standalone:true,members:[],leaving:false,returnError:''})
 let page,exposed,timerId=0
 const uni={
  getWindowInfo:()=>({windowHeight:800,statusBarHeight:24}),hideKeyboard(){},
  navigateBack:options=>{calls.push({method:'back',options});if(backThrows)throw Error('back failed')},
  reLaunch:options=>{calls.push({method:'fallback',options});if(fallbackThrows)throw Error('fallback failed')},
  showToast:options=>calls.push({method:'toast',options}),
 }
 const routeDeps={ref,watch,getCurrentInstance:()=>({}),storageContext:()=> 'A',
  onLoad:fn=>fn(),onShow:fn=>{hooks.show=fn},onUnload:fn=>{hooks.unload=fn},onBackPress:fn=>{hooks.back=fn},
  openerChannel:()=>({on(){}}),getSession:()=>({householdId:'family'}),request:async()=>({data:{members:[]}}),
  getCurrentPages:()=>Array.from({length:stack},()=>({})),uni,
  setTimeout:fn=>{timers.set(++timerId,fn);return timerId},clearTimeout:id=>timers.delete(id)}
 page=scope.run(()=>new Function('deps',`const {${Object.keys(routeDeps)}}=deps;${script(routeSource)};return {leave,detail,leaving,returnError}`)(routeDeps))
 const deps={reactive,ref,computed,nextTick,onMounted(){},onUnmounted(){},onShow(){},
  defineProps:()=>props,defineEmits:()=>((event,...args)=>{events.push(event);if(event==='leave')page.leave(...args)}),defineExpose:value=>{exposed=value},
  detailState,createMealDetailClient,mealNames,formalRoute,detailKey,createTodayMealPlan,todayMealPlanState,
  request:async()=>({data:{arrangement_id:'saved',version:2,meal}}),storageContext:()=> 'A',scopedStorage:{},newHealthRequestId:()=> 'test-request',
  dailyArrangementState:()=>({}),createDailyArrangementClient:()=>({reset(){},dispose(){}}),uni,
 }
 const sheet=scope.run(()=>new Function('deps',`const {${Object.keys(deps)}}=deps;${script(sheetSource)};return {state,requestBack,busy,purchaseOpen,purchaseRef,cookingOpen,cookingBusy,memberBusy,showDish,bodyTop}`)(deps))
 page.detail.value=exposed
 scope.run(()=>watch(page.leaving,value=>{props.leaving=value},{flush:'sync'}))
 // Execute the handler actually bound to the header, then the route's leave handler.
 const clickExpression=sheetSource.match(/class="detail-back"[^>]*@click="([^"]+)"/)[1]
 assert.match(routeSource,/@leave="leave"/)
 const click=()=>new Function('requestBack',clickExpression)(sheet.requestBack)
 return {sheet,page,calls,events,click,nativeBack:event=>hooks.back(event),open:extra=>exposed.open({...target,...extra}),
  dispose:()=>{hooks.unload();scope.stop()}}
}

test('header tap leaves a meal page once and uses an explicit one-page return',async()=>{
 const h=harness();try{
  await h.open();assert.equal(h.sheet.busy.value,false)
  h.click();h.click()
  assert.equal(h.calls.length,1);assert.equal(h.calls[0].method,'back');assert.equal(h.calls[0].options.delta,1)
  assert.equal(h.page.leaving.value,true)
  assert.equal(h.nativeBack({from:'navigateBack'}),false)
 }finally{h.dispose()}
})

test('no previous page and a failed native return both reach the chat fallback',async()=>{
 for(const stack of [1,2]){
  const h=harness({stack});try{
   await h.open();h.click()
   if(stack===2)h.calls[0].options.fail({errMsg:'navigateBack:fail'})
   const fallback=h.calls.find(c=>c.method==='fallback')
   assert.ok(fallback);assert.equal(fallback.options.url,'/pages/chat/index')
   assert.equal(h.page.leaving.value,true)
  }finally{h.dispose()}
 }
})

test('fallback failure reports an error, unlocks return, and permits retry',async()=>{
 const h=harness();try{
  await h.open();h.click();h.calls[0].options.fail({});h.calls[1].options.fail({})
  assert.equal(h.page.leaving.value,false);assert.match(h.page.returnError.value,/暂时无法返回/)
  assert.equal(h.calls[2].method,'toast')
  h.click();assert.equal(h.calls[3].method,'back');assert.equal(h.page.returnError.value,'')
 }finally{h.dispose()}
})

test('synchronous navigation errors also unlock return after fallback fails',async()=>{
 const h=harness({backThrows:true,fallbackThrows:true});try{
  await h.open();h.click()
  assert.equal(h.page.leaving.value,false);assert.match(h.page.returnError.value,/暂时无法返回/)
  assert.deepEqual(h.calls.map(c=>c.method),['back','fallback','toast'])
 }finally{h.dispose()}
})

test('return closes purchase and cooking overlays before changing the underlying view',async()=>{
 for(const native of [false,true]){
  const h=harness();try{
   await h.open();h.sheet.showDish(0);await nextTick()
   h.sheet.purchaseOpen.value=true;h.sheet.purchaseRef.value={isBusy:false}
   const back=()=>native?h.nativeBack({from:'backbutton'}):h.click()
   back();assert.equal(h.sheet.purchaseOpen.value,false);assert.equal(h.sheet.state.view,'dish')
   h.sheet.cookingOpen.value=true;back();assert.equal(h.sheet.cookingOpen.value,false)
   h.sheet.bodyTop.value=200;back();await nextTick();assert.equal(h.sheet.state.view,'meal')
   assert.equal(h.calls.length,0)
   if(native)assert.equal(back(),false);else{back();assert.equal(h.calls[0].method,'back')}
  }finally{h.dispose()}
 }
})

test('direct dish entry leaves the route and pending writes block return',async()=>{
 const h=harness();try{
  await h.open({initialView:'dish'})
  h.sheet.cookingBusy.value=true;h.click();assert.equal(h.calls.length,0)
  assert.equal(h.nativeBack({from:'backbutton'}),true)
  h.sheet.cookingBusy.value=false;h.click();assert.equal(h.calls[0].method,'back')
 }finally{h.dispose()}
})

test('an unloaded page ignores a late failed return callback',async()=>{
 const h=harness();await h.open();h.click();h.dispose()
 h.calls[0].options.fail({});assert.equal(h.calls.length,1)
})
