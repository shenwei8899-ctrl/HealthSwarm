import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { computed, ref } from 'vue'
import { memberAge, birthDateError, ageLabel } from '../src/utils/member-age.js'
import { normalizeProfile, newMember, saveProfile } from '../src/utils/profile.js'
import { dataWarnings } from '../src/utils/health.js'
import { createPlan } from '../src/utils/demo.js'
import { normalizeMealResult } from '../src/utils/meal-result.js'
import { productsFromDemands } from '../src/utils/meal-demands.js'
import { mealContext, contextMember, linkMealContext } from '../src/utils/meal-context.js'
import { mealPlanKey } from '../src/utils/meal-plan-store.js'
import { ensureMealPlan } from '../src/services/meal-planning.js'
import { ensureExclusivePlan } from '../src/services/exclusive-planning.js'
import { getExclusivePlan, createDeliveryBatches } from '../src/utils/exclusive-plans.js'
import { createDemoOrder, getOrder } from '../src/utils/orders.js'
import { createCookingGuide } from '../src/utils/meal-flow.js'
import { localDate, todayPlan, setMealMembers } from '../src/utils/meal-state.js'
import { registerApiAdapters } from '../src/services/index.js'
import { scopedStorage } from '../src/services/storage.js'
import { setSession } from '../src/services/session.js'

const member = (id, patch={}) => ({id,name:'成员'+id,age:8,healthStatus:'none',conditions:[],doctorStatus:'none',clinicianGuidance:'',allergyStatus:'none',allergies:[],intoleranceStatus:'none',intolerances:[],avoidanceStatus:'none',avoidances:[],...patch})
function setup(members=[member(1,{relation:'本人',name:'我',birthDate:'1998-05-18',claimedBy:'creator'}),member(2)]) {
  const storage=new Map()
  globalThis.uni={getStorageSync:key=>storage.get(key),setStorageSync:(key,value)=>storage.set(key,structuredClone(value)),getStorageInfoSync:()=>({keys:[...storage.keys()]})}
  setSession({accountId:'all-members',householdId:'all-members-home'})
  const profile=normalizeProfile({members,defaultDiners:members.map(m=>m.id),usageMode:'家庭使用',goals:[],tastes:[]})
  saveProfile(profile)
  registerApiAdapters({generateMealPlan:undefined,generateExclusivePlan:undefined})
  return profile
}
// Synthetic amounts exercise the contract and are not nutrition prescriptions.
function result(input) {
  return {status:'passed',generationId:'test-generation',date:input.date,meal:input.meal,issues:[],minutes:20,steps:['按受控配方烹饪'],
    dishes:[{name:'测试菜',recipeId:'recipe',recipeVersion:'v1',ingredients:['测试食材'],steps:['按受控配方烹饪'],nutrition:{basis:'per_100g',foodState:'cooked_edible',source:'calculated',sourceReference:'test-fixture',energyKcal:100,proteinG:0,fatG:null,carbohydrateG:20,fiberG:2,sodiumMg:80}}],
    products:[{id:'sku',name:'测试食材',ingredients:['测试食材'],pack:500,unit:'g',priceCents:1000}],
    memberDemands:input.members.map((m,index)=>({memberId:m.id,sourceReference:'test-recipe-v1',ingredients:[{productId:'sku',amount:index===0?100:50,unit:'g'}]})),
    memberNotes:input.members.map((m,index)=>({id:m.id,portion:'测试份量',notes:[],dishes:[{recipeId:'recipe',recipeVersion:'v1',amount:index===0?80:40,unit:'g',foodState:'cooked_edible',sourceReference:'test-recipe-v1'}]}))}
}

test('birthdays use complete dates, infer infant months, and distinguish invalid and unknown ages',()=>{
  assert.deepEqual(memberAge({birthDate:'2018-12-01'},'2026-10-13'),{years:7,months:94})
  assert.equal(memberAge({birthDate:'2018-12-01'},'2026-12-01').years,8)
  assert.equal(ageLabel({birthDate:'2026-06-13'},'2026-10-13'),'4 个月')
  for(const value of ['',null,undefined])assert.equal(memberAge({age:value}).years,null)
  assert.equal(memberAge({age:30}).years,null)
  assert.equal(memberAge({age:30,ageSource:'self_reported'}).years,30)
  assert.equal(newMember(0).age,null)
  for(const birthday of ['2026-02-30','2027-01-01'])assert.ok(birthDateError(birthday,'2026-10-13'))
  assert.equal(memberAge({birthDate:'2026-02-30',age:8}).years,null)
})

test('children and other self-reports are allowed, while infant fixtures do not allocate adult solids',()=>{
  const profile=setup([member(1),member(2,{age:null}),member(3,{healthStatus:'set',conditions:['其他'],otherCondition:'孕期'})])
  assert.deepEqual(createPlan(profile).blocked,[])
  assert.deepEqual(dataWarnings(member(1,{age:1,height:75,weight:10})),[])
  assert.ok(dataWarnings(member(1,{height:0})).length)
  const infant=setup([member(1,{birthDate:localDate()})])
  const plan=createPlan(infant)
  assert.equal(plan.blocked.length,0);assert.deepEqual(plan.products,[]);assert.deepEqual(plan.dishes,[])
  assert.match(plan.memberNotes[0].portion,/喂养/)
})

test('real results aggregate distinct member demands and cooked nutrition without linear diner assumptions',()=>{
  const profile=setup(),input={members:profile.members,date:localDate(),meal:'晚餐'}
  const plan=normalizeMealResult(result(input),input)
  assert.equal(plan.products[0].need,150);assert.equal(plan.products[0].quantity,1)
  assert.deepEqual(plan.memberNotes.map(note=>note.dishes[0].amount),[80,40])
  assert.equal(plan.nutrition.kcal,120);assert.equal(plan.nutrition.protein,0);assert.equal(plan.nutrition.fat,null)
  assert.equal(plan.nutrition.sodium,96)
  assert.equal(productsFromDemands([{id:'a',unit:'g',pack:100}], [{ingredients:[{productId:'a',unit:'g',amount:40}]},{ingredients:[{productId:'a',unit:'g',amount:40}]}])[0].quantity,1)
})

test('infant feeding advice may have no solid dishes or products',()=>{
  const profile=setup([member(1,{birthDate:localDate(),age:null})])
  const input={members:profile.members,date:localDate(),meal:'晚餐'}
  const value={status:'passed',generationId:'feeding-only',date:input.date,meal:input.meal,issues:[],steps:[],dishes:[],products:[],
    memberDemands:[{memberId:1,sourceReference:'feeding-review',ingredients:[]}],
    memberNotes:[{id:1,portion:'请在对话中确认当前喂养方式',notes:['暂不安排家庭固体菜品'],dishes:[]}]}
  const plan=normalizeMealResult(value,input)
  assert.deepEqual(plan.dishes,[]);assert.deepEqual(plan.products,[])
  assert.equal(plan.nutrition,null);assert.deepEqual(plan.blocked,[])
})

test('contract rejects foreign members, unit mismatch, missing recipe evidence, and duplicate servings',()=>{
  const profile=setup(),input={members:profile.members,date:localDate(),meal:'晚餐'}
  for(const mutate of [
    value=>value.memberDemands[0].memberId=999,
    value=>value.memberDemands[0].ingredients[0].unit='kg',
    value=>value.memberDemands[0].ingredients[0].amount=-1,
    value=>value.dishes[0].ingredients=[],
    value=>value.memberNotes[0].dishes[0].recipeVersion='other',
    value=>value.memberNotes[0].dishes.push({...value.memberNotes[0].dishes[0]}),
  ]){const value=result(input);mutate(value);assert.throws(()=>normalizeMealResult(value,input),{code:'INVALID_MEAL_RESULT'})}
})

test('server passed flag cannot bypass local ingredient conflicts or turn demo nutrition into actual totals',()=>{
  const profile=setup([member(1,{allergyStatus:'set',allergies:['含蛋']})]),input={members:profile.members,date:localDate(),meal:'晚餐'}
  const value=result(input);value.products[0].ingredients.push('鸡蛋')
  assert.match(normalizeMealResult(value,input).blocked[0],/含蛋/)
  value.products[0].ingredients=['测试食材'];value.dishes[0].nutrition.source='demo'
  assert.equal(normalizeMealResult(value,input).nutrition.kcal,null)
  const question={status:'needs_info',generationId:'question',date:input.date,meal:input.meal,issues:[{type:'needs_info',message:'请说明目前喂养方式'}]}
  assert.deepEqual(normalizeMealResult(question,input).products,[])
  assert.throws(()=>normalizeMealResult({...question,issues:[]},input),{code:'INVALID_MEAL_RESULT'})
})

test('context retains member and date provenance, ignores unrelated chats, and supports correction and withdrawal',()=>{
  const profile=setup(),date=localDate(),future=localDate(new Date(Date.now()+86400000))
  assert.equal(contextMember(profile,'我没有怀孕，今晚吃什么'),1)
  assert.equal(contextMember(profile,'孩子今天吃饭不好吞咽'),2)
  assert.equal(contextMember({...profile,members:[...profile.members,member(3)]},'孩子正在吃辅食'),null)
  scopedStorage.setStorageSync('chat-'+date,[{id:'clinical',role:'user',text:'我正在哺乳，今晚吃什么',memberId:1}])
  const key=mealPlanKey(profile,'晚餐',date)
  scopedStorage.setStorageSync('chat-'+date,[...scopedStorage.getStorageSync('chat-'+date),{id:'unrelated',role:'user',text:'你好'}])
  assert.equal(mealPlanKey(profile,'晚餐',date),key)
  linkMealContext(future,date)
  assert.equal(mealContext(future)[0].date,date);assert.equal(mealContext(future)[0].memberId,1)
  scopedStorage.setStorageSync('chat-'+date,[{id:'clinical',role:'user',text:'我没有在哺乳',memberId:1}])
  assert.match(mealContext(future)[0].text,/没有/)
  scopedStorage.setStorageSync('chat-'+date,[{id:'clinical',role:'user',text:'我正在哺乳',withdrawn:true}])
  assert.deepEqual(mealContext(future),[])
  assert.ok(!Object.keys(profile.members[0]).some(key=>/lifeStage|gestational|lactation/.test(key)))
})

test('reopening menus uses persisted results and member changes affect only their meal',()=>{
  const profile=setup(),first=todayPlan(profile,'晚餐')
  const original=first.dishes[0].name;first.dishes[0].name='外部修改'
  assert.equal(todayPlan(profile,'晚餐').dishes[0].name,original)
  setMealMembers(profile,'早餐',[2])
  assert.deepEqual(todayPlan(profile,'早餐').members.map(m=>m.id),[2])
  assert.deepEqual(todayPlan(profile,'晚餐').members.map(m=>m.id),[1,2])
})

test('real adapter deduplicates concurrent generation and reuses the saved result across pages',async()=>{
  const profile=setup();let calls=0,finish
  registerApiAdapters({generateMealPlan:input=>{calls++;return new Promise(resolve=>finish=()=>resolve(result(input)))}})
  const a=ensureMealPlan(profile,'晚餐',{mode:'api'}),b=ensureMealPlan(profile,'晚餐',{mode:'api'})
  assert.equal(calls,1);finish()
  const [one,two]=await Promise.all([a,b]);assert.equal(one.generationId,two.generationId)
  await ensureMealPlan(profile,'晚餐',{mode:'api'});assert.equal(calls,1)
  assert.equal(todayPlan(profile,'晚餐').sourceType,'api')
})

test('saved chat context produces the same generated meal across pages',async()=>{
  const profile=setup(),date=localDate();let received
  scopedStorage.setStorageSync('chat-'+date,[{id:'feeding-note',role:'user',text:'孩子今天吞咽不方便',memberId:2}])
  registerApiAdapters({generateMealPlan:async input=>{received=input;return result(input)}})
  const returned=await ensureMealPlan(profile,'晚餐',{mode:'api'})
  assert.equal(received.context[0].id,'feeding-note')
  assert.equal(returned.generationId,'test-generation')
  assert.equal(todayPlan(profile,'晚餐').generationId,returned.generationId)
})

test('delivery schedule regenerates the selected date before checkout',async()=>{
  setup()
  let load,show,finish
  const cache=new Map(),navigations=[]
  const pending=[]
  const deps={ref,computed,isMockMode:false,AppNavBar:null,backHome(){},getProfile:()=>({members:[]}),getExclusivePlan:id=>({id}),
    adaptExclusivePlan:(template,profile,date)=>cache.get(date)||{...template,name:'待生成',sourceType:null,fixturePlans:[],days:[],blocked:['未生成'],totalEstimateCents:0,estimateCents:0},
    ensureExclusivePlan:(template,profile,{startDate})=>new Promise(resolve=>pending.push(()=>{const plan={id:template.id,name:'日期计划',sourceType:'api',fixturePlans:Array.from({length:21},()=>[]),days:Array.from({length:21},()=>({meals:[]})),blocked:[],totalEstimateCents:2100,estimateCents:100};cache.set(startDate,plan);resolve(plan)})),
    createDeliveryBatches:(plan,date)=>[{date}],defaultPlanStartDate:()=> '2026-10-20',mockService:{selectedAddress:()=>({name:'收货人',phone:'13800000000',region:'上海',detail:'测试地址'})},
    onLoad:callback=>load=callback,onShow:callback=>show=callback}
  const source=readFileSync(new URL('../src/pages/exclusive-plans/schedule.vue',import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
  const page=new Function('deps',`const {${Object.keys(deps).join(',')}}=deps;\n${source}\nreturn {startDate,ready,batches,loading,error,changeDate,pay}`)(deps)
  globalThis.uni.navigateTo=options=>navigations.push(options.url)
  globalThis.uni.showToast=()=>{}
  load({id:'balanced'})
  const initial=show();pending.shift()();await initial
  assert.equal(page.batches.value[0].date,'2026-10-20')
  const changed=page.changeDate({detail:{value:'2026-10-21'}})
  assert.equal(page.ready.value,false);assert.equal(page.batches.value.length,0)
  page.pay();assert.deepEqual(navigations,[])
  pending.shift()();await changed
  assert.equal(page.batches.value[0].date,'2026-10-21')
  page.pay();assert.match(navigations[0],/start=2026-10-21/)
})

test('late old results cannot overwrite a newer profile result',async()=>{
  const profile=setup(),finish=[]
  registerApiAdapters({generateMealPlan:input=>new Promise(resolve=>finish.push(()=>resolve(result(input))))})
  const old=ensureMealPlan(profile,'晚餐',{mode:'api'})
  const next=structuredClone(profile);next.members[0].name='新的称呼';saveProfile(next)
  const current=ensureMealPlan(next,'晚餐',{mode:'api'})
  finish[1]();await current;finish[0]()
  await assert.rejects(old,{code:'STALE_MEAL_REQUEST'})
  assert.equal(todayPlan(next,'晚餐').members[0].name,'新的称呼')
})

test('missing adapters and account changes fail without persisting fabricated results',async()=>{
  const profile=setup()
  await assert.rejects(ensureMealPlan(profile,'晚餐',{mode:'api'}),{code:'ADAPTER_NOT_READY'})
  assert.equal(scopedStorage.getStorageSync('generated-meals-v1'),undefined)
  let finish;registerApiAdapters({generateMealPlan:input=>new Promise(resolve=>finish=()=>resolve(result(input)))})
  const request=ensureMealPlan(profile,'晚餐',{mode:'api'})
  setSession({accountId:'another',householdId:'another'});finish()
  await assert.rejects(request,{code:'STALE_MEAL_REQUEST'})
  assert.equal(scopedStorage.getStorageSync('generated-meals-v1'),undefined)
})

test('21-day service validates every date and meal and derives packaging from member demands',async()=>{
  const profile=setup(),startDate=localDate()
  registerApiAdapters({generateExclusivePlan:async input=>({generationId:'21-day-fixture',days:Array.from({length:21},(_,index)=>{
    const date=new Date(input.startDate+'T00:00:00Z');date.setUTCDate(date.getUTCDate()+index)
    const target=date.toISOString().slice(0,10)
    return {date:target,plans:['早餐','午餐','晚餐'].map(meal=>result({members:input.members,date:target,meal}))}
  })})})
  const plan=await ensureExclusivePlan(getExclusivePlan('balanced'),profile,{mode:'api',startDate,force:true})
  assert.equal(plan.fixturePlans.length,21);assert.deepEqual(plan.blocked,[])
  assert.equal(plan.estimateCents,1000);assert.equal(plan.totalEstimateCents,21000)
  const batches=createDeliveryBatches(plan,startDate)
  assert.equal(batches[0].items[0].need,450);assert.equal(batches[0].items[0].quantity,1)
  registerApiAdapters({generateExclusivePlan:async()=>({generationId:'bad',days:[]})})
  await assert.rejects(ensureExclusivePlan(getExclusivePlan('balanced'),profile,{mode:'api',startDate,force:true}),/结果不完整/)
})

test('paid recipe and order snapshots survive current health changes while advice flags the specific conflict',()=>{
  const profile=setup(),plan=createPlan(profile),template=getExclusivePlan('balanced'),batch=createDeliveryBatches(template,localDate(),1)
  const order=createDemoOrder({items:plan.products,totalCents:100,meal:'晚餐',sourcePlanId:'balanced',deliveryBatches:batch,cookingGuides:[{index:1,guides:[createCookingGuide(plan)]}]})
  const original=structuredClone(getOrder(order.id))
  profile.members[0].allergyStatus='set';profile.members[0].allergies=['鱼类'];saveProfile(profile)
  assert.ok(todayPlan(profile,'晚餐').blocked.length)
  assert.deepEqual(getOrder(order.id),original)
})
