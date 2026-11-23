import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {reactive,ref,computed,nextTick,watch,effectScope} from 'vue'
import {detailState,createMealDetailClient,mealNames,formalRoute,detailKey} from '../src/services/meal-detail-client.js'

import {createTodayMealPlan,todayMealPlanState} from '../src/services/today-meal-plan.js'
import {dishSwapState,createDishSwap} from '../src/services/dish-swap.js'
import {localDate} from '../src/utils/meal-state.js'

const sheetSource=readFileSync(new URL('../src/components/MealDetailSheet.vue',import.meta.url),'utf8')
const routeSource=readFileSync(new URL('../src/pages/meals/detail.vue',import.meta.url),'utf8')
const script=source=>source.split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm,'')
const target={kind:'formal',familyId:'family',date:'2026-11-03',mealType:'dinner',sourceId:'saved',version:2,dailyPlanVersion:4}
const meal={type:'dinner',members:[],dishes:[{name:'合成测试菜品'}]}

function harness({stack=2,backThrows=false,fallbackThrows=false,initialTarget=null,overrides={}}={}){
 const scope=effectScope(),calls=[],events=[],hooks={},timers=new Map(),props=reactive({standalone:true,members:[],leaving:false,returnError:''})
 let page,exposed,timerId=0
 const uni={
  getWindowInfo:()=>({windowHeight:800,statusBarHeight:24}),hideKeyboard(){},
  navigateBack:options=>{calls.push({method:'back',options});if(backThrows)throw Error('back failed')},
  reLaunch:options=>{calls.push({method:'fallback',options});if(fallbackThrows)throw Error('fallback failed')},
  showToast:options=>calls.push({method:'toast',options}),
 }
 const routeDeps={ref,watch,getCurrentInstance:()=>({}),storageContext:()=> 'A',
  onLoad:fn=>fn({mealNavigation:'1'}),onShow:fn=>{hooks.show=fn},onUnload:fn=>{hooks.unload=fn},onBackPress:fn=>{hooks.back=fn},
  takeMealPageTarget:key=>key==='1'?initialTarget:null,
  openerChannel:()=>({on(){}}),getSession:()=>({householdId:'family'}),request:async()=>({data:{members:[]}}),
  getCurrentPages:()=>Array.from({length:stack},()=>({})),uni,
  setTimeout:fn=>{timers.set(++timerId,fn);return timerId},clearTimeout:id=>timers.delete(id)}
 page=scope.run(()=>new Function('deps',`const {${Object.keys(routeDeps)}}=deps;${script(routeSource)};return {leave,detail,leaving,returnError,opened}`)(routeDeps))
 const deps={localDate,dishSwapState,createDishSwap,reactive,ref,computed,nextTick,onMounted(){},onUnmounted(){},onShow(){},
  defineProps:()=>props,defineEmits:()=>((event,...args)=>{events.push(event);if(event==='leave')page.leave(...args)}),defineExpose:value=>{exposed=value},
  detailState,createMealDetailClient,mealNames,formalRoute,detailKey,createTodayMealPlan,todayMealPlanState,
  request:async()=>({data:{arrangement_id:'saved',version:2,meal}}),storageContext:()=> 'A',scopedStorage:{},newHealthRequestId:()=> 'test-request',
  dailyArrangementState:()=>({}),createDailyArrangementClient:()=>({reset(){},dispose(){}}),uni,...overrides,
 }
 const sheet=scope.run(()=>new Function('deps',`const {${Object.keys(deps)}}=deps;${script(sheetSource)};return {state,requestBack,busy,purchaseOpen,purchaseRef,recordOpen,recordRef,recordClosed,memberBusy,showDish,bodyTop,startMembers,toggleMember,memberIds,saveMembers,title,memberError,referenceRevisionState,cancelMembers}`)(deps))
 page.detail.value=exposed
 scope.run(()=>watch(page.leaving,value=>{props.leaving=value},{flush:'sync'}))
 // Execute the handler actually bound to the header, then the route's leave handler.
 const clickExpression=sheetSource.match(/class="detail-back"[^>]*@click="([^"]+)"/)[1]
 assert.match(routeSource,/@leave="leave"/)
 const click=()=>new Function('requestBack',clickExpression)(sheet.requestBack)
 return {sheet,page,calls,events,click,nativeBack:event=>hooks.back(event),open:extra=>exposed.open({...target,...extra}),
  dispose:()=>{hooks.unload();scope.stop()}}
}

test('the detail page opens a route handoff when its native component becomes ready',async()=>{
 const h=harness({initialTarget:{...target,initialView:'dish',dishIndex:0}})
 try{await nextTick();assert.equal(h.page.opened.value,true)}
 finally{h.dispose()}
})

test('member selection opens above the meal and back cancels the draft without leaving the page',async()=>{
 const h=harness();try{
  await h.open();h.sheet.state.meal.members=[{id:'a',name:'家人甲'}];h.sheet.bodyTop.value=120
  h.sheet.startMembers();await nextTick()
  assert.equal(h.sheet.state.view,'members');assert.equal(h.sheet.title.value,'晚餐安排')
  assert.equal(h.sheet.bodyTop.value,120);assert.deepEqual(h.sheet.memberIds.value,['a'])
  h.sheet.toggleMember('b');assert.deepEqual(h.sheet.memberIds.value,['a','b'])
  h.sheet.requestBack();assert.equal(h.sheet.state.view,'meal');assert.equal(h.calls.length,0)
  h.sheet.startMembers();assert.deepEqual(h.sheet.memberIds.value,['a'])
  h.sheet.memberBusy.value=true;h.sheet.requestBack();assert.equal(h.sheet.state.view,'members')
  h.sheet.memberBusy.value=false;h.sheet.state.target.kind='reference'
  await h.sheet.saveMembers();assert.equal(h.sheet.state.view,'meal');assert.equal(h.calls.length,0)
 }finally{h.dispose()}
})

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

test('return closes purchase and recording overlays before changing the underlying view',async()=>{
 for(const native of [false,true]){
  const h=harness();try{
   await h.open();h.sheet.showDish(0);await nextTick()
   h.sheet.purchaseOpen.value=true;h.sheet.purchaseRef.value={isBusy:false}
   const back=()=>native?h.nativeBack({from:'backbutton'}):h.click()
   back();assert.equal(h.sheet.purchaseOpen.value,false);assert.equal(h.sheet.state.view,'dish')
   h.sheet.recordOpen.value=true;h.sheet.recordRef.value={handleBack:()=>h.sheet.recordClosed()};back();assert.equal(h.sheet.recordOpen.value,false)
   h.sheet.bodyTop.value=200;back();await nextTick();assert.equal(h.sheet.state.view,'meal')
   assert.equal(h.calls.length,0)
   if(native)assert.equal(back(),false);else{back();assert.equal(h.calls[0].method,'back')}
  }finally{h.dispose()}
 }
})

test('direct dish entry leaves the route and pending writes block return',async()=>{
 const h=harness();try{
  await h.open({initialView:'dish'})
  h.sheet.recordRef.value={isBusy:true};h.click();assert.equal(h.calls.length,0)
  assert.equal(h.nativeBack({from:'backbutton'}),true)
  h.sheet.recordRef.value={isBusy:false};h.click();assert.equal(h.calls[0].method,'back')
 }finally{h.dispose()}
})

test('an unloaded page ignores a late failed return callback',async()=>{
 const h=harness();await h.open();h.click();h.dispose()
 h.calls[0].options.fail({});assert.equal(h.calls.length,1)
})


test('unchanged formal members confirm immediately without a mutation',async()=>{
 const h=harness();try{
  await h.open();h.sheet.state.meal.members=[{id:'a'}];h.sheet.startMembers()
  await h.sheet.saveMembers();assert.equal(h.sheet.state.view,'meal');assert.equal(h.sheet.memberBusy.value,false)
 }finally{h.dispose()}
})

test('changed reference members lock duplicate confirms immediately and surface rejected requests',async()=>{
 let reject,submissions=0
 const h=harness({overrides:{createTodayMealPlan:()=>({clear(){},dispose(){},open(){submissions++;return new Promise((_,fail)=>{reject=fail})}})}})
 try{
  await h.open();h.sheet.state.target.kind='reference';h.sheet.state.meal.members=[{id:'a'}]
  h.sheet.startMembers();h.sheet.toggleMember('b')
  const pending=h.sheet.saveMembers();assert.equal(h.sheet.memberBusy.value,true)
  await h.sheet.saveMembers();assert.equal(submissions,1)
  reject(Error('网络暂不可用'));await pending
  assert.equal(h.sheet.memberError.value,'网络暂不可用');assert.equal(h.sheet.memberBusy.value,false)
  assert.equal(h.sheet.state.view,'members');assert.deepEqual(h.sheet.memberIds.value,['a','b'])
  h.sheet.cancelMembers();h.sheet.startMembers();assert.deepEqual(h.sheet.memberIds.value,['a'])
 }finally{h.dispose()}
})

test('member footer has one confirm and feedback remains outside the scrolling member list',()=>{
 const actions=sheetSource.match(/<view class="member-actions">[^\n]+/)[0]
 assert.equal((actions.match(/<button/g)||[]).length,1)
 assert.match(actions,/@click="saveMembers"/);assert.doesNotMatch(sheetSource,/取消调整<\/button>/)
 assert.match(sheetSource,/<\/scroll-view>\s*<view v-if="memberBusy[^>]+class="member-feedback"/)
 assert.match(sheetSource,/aria-label="取消调整并关闭成员选择"[^>]+@click="cancelMembers"/)
})


test('changed formal members refresh the meal and dismiss the picker only after success',async()=>{
 let memberState,version=2,ids=['a'],mutation
 const arrangement=()=>({id:'saved',version,meals:[{...meal,members:ids.map(id=>({id}))}]})
 const h=harness({overrides:{dailyArrangementState:()=>memberState={},
  createDailyArrangementClient:()=>({reset(){},dispose(){},async load(){memberState.arrangement=arrangement()},async changeMembers(type,selected,options){mutation={type,selected,options};version=3;ids=selected;memberState.arrangement=arrangement()}}),
  request:async()=>({data:{arrangement_id:'saved',version,meal:{...meal,members:ids.map(id=>({id}))}}})}})
 try{
  await h.open();h.sheet.startMembers();h.sheet.toggleMember('b');await h.sheet.saveMembers()
  assert.deepEqual(mutation,{type:'dinner',selected:['a','b'],options:{dailyPlanVersion:4}})
  assert.equal(h.sheet.state.view,'meal');assert.equal(h.sheet.state.phase,'ready')
  assert.deepEqual(h.sheet.state.meal.members.map(m=>m.id),['a','b']);assert.equal(h.sheet.memberBusy.value,false)
 }finally{h.dispose()}
})
