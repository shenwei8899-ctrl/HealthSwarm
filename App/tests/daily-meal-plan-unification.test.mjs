import {chatPromptProfileKey} from '../src/services/chat-prompt-profile.js'
import {syntheticIntent} from './fixtures/health-intent.mjs'
import {todayMealPlanState,createTodayMealPlan} from '../src/services/today-meal-plan.js'
import { mealPairingText } from '../src/utils/dish-commerce-presentation.js'
import {parseMultiDayMealIntent,parseChatMealIntent,isMealPlanningCancelled} from '../src/utils/chat-meal-intent.js'
import {watch} from 'vue'
import {createChatEntryTransition} from '../src/services/chat-entry-transition.js'
import {createChatKeyboardLayout} from '../src/services/chat-keyboard-layout.js'
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { ref, reactive, computed, nextTick, effectScope } from 'vue'
import { mealQuestionAction, readDailyMealPlan } from '../src/services/daily-meal-plan.js'
import { referenceSelection, isReferencePlan } from '../src/services/reference-meal-plan.js'
import { chatPresentation } from '../src/services/chat-presentation.js'
import { canPurchaseAllMeals } from '../src/utils/meal-presentation.js'

const today='2026-10-27',member='11111111-1111-4111-8111-111111111111'
const meal=(type,id='old')=>({meal_type:type,source:{kind:'reference',id},meal:{meal_type:type,dishes:[{name:id}]},members:[{id:'self',name:'我'}]})
const plan=(version=1,meals=[meal('breakfast'),meal('lunch'),meal('dinner')],date=today)=>({id:'plan',status:'ready',version,date,meals,purchase_options:[]})

test('view, generation and targeted change are distinct actions',()=>{
  assert.equal(mealQuestionAction('查看今天的餐单'),'view')
  assert.equal(mealQuestionAction('请帮我安排今天的三餐'),'generate')
  assert.equal(mealQuestionAction('把晚餐换成蒸鱼'),'change')
  assert.equal(mealQuestionAction('蔬菜怎么做更好吃'),'consultation')
  assert.equal(mealQuestionAction('换个话题，糖尿病家庭怎么吃？'),'consultation')
})

test('daily plan response rejects wrong date and duplicate meal types',async()=>{
  await assert.rejects(()=>readDailyMealPlan('f',today,async()=>({data:plan(1,[], '2026-10-28')})),/不完整/)
  await assert.rejects(()=>readDailyMealPlan('f',today,async()=>({data:plan(1,[meal('breakfast'),meal('breakfast')])})),/来源/)
})

test('new plans use default diners and explicit requests can use the whole family or only the current person',()=>{
  const p={householdId:'family',selfMemberId:'self',defaultDiners:['self','other'],members:[{id:'self',healthMemberId:member},{id:'other',healthMemberId:'other'}]}
  assert.deepEqual(referenceSelection(p,'安排今天三餐',{today}).participant_ids,['other','self'])
  assert.deepEqual(referenceSelection(p,'给全家安排今天三餐',{today}).participant_ids,['other','self'])
  assert.deepEqual(referenceSelection(p,'只给我安排今天三餐',{today}).participant_ids,['self'])
})

function mount({read=async()=>plan()}={}){
  const hooks={},cache=new Map(),calls=[];let notify
  const flow={hide(){},async open(memberId,taskType,selection,options){calls.push({action:'open',memberId,taskType,selection,options});notify({memberId,taskType,available:true,entry:{thread_id:'thread'}})},async submit(text){calls.push({action:'submit',text});return true},async refresh(){calls.push({action:'refresh'});notify({taskType:'reference_meal_preview',requestId:'req',status:'completed',available:true})}}
  const state=()=>({phase:'idle',busy:false})
  const deps={chatPromptProfileKey,todayMealPlanState,createTodayMealPlan:()=>({open:async()=>{},isGenerating:()=>false,pause(){},clear(){},dispose(){}}),defineOptions:()=>{},mealPairingText,createChatEntryTransition,createChatKeyboardLayout,watch,ref,reactive,computed,nextTick,defineProps:()=>({route:{entry:'conversation'}}),onMounted:fn=>hooks.mounted=fn,onShow:fn=>hooks.show=fn,onHide:fn=>hooks.hide=fn,onUnmounted:fn=>hooks.unmount=fn,
    listWeeklyMealPlans:async()=>[],parseMultiDayMealIntent,parseChatMealIntent,isMealPlanningCancelled,chatPresentation,chooseReference:referenceSelection,isReferencePlan,readDailyMealPlan:read,mealQuestionAction,canPurchaseAllMeals,
    openMealPage:(target,options)=>calls.push({action:'navigate',target,options}),
    dailyArrangementState:state,createDailyArrangementClient:()=>({reset(){},dispose(){}}),
    createHealthTaskFlow:({onChange})=>{notify=onChange;return flow},
    HEALTH_TEXT_TASKS:{consultation:'咨询',reference_meal_preview:'餐单'},
    localDate:()=>today,storageContext:()=> 'scope',getSession:()=>({accountId:'self',householdId:'family',token:'synthetic'}),
    scopedStorage:{getStorageSync:k=>cache.get(k),setStorageSync:(k,v)=>cache.set(k,v)},newHealthRequestId:()=>String(calls.length)+'-id',
    readChatSnapshot:async()=>({messages:[],runs:[]}),selectChatPrompts:()=>[],uni:{showToast(){}},
    readCurrentPreparation:async()=>({status:'absent'}),request:async request=>({data:syntheticIntent(request.data,today)})}
  const source=readFileSync(new URL('../src/components/CloudNutritionChat.vue',import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
  const scope=effectScope()
  const page=scope.run(()=>new Function('deps',`const {${Object.keys(deps)}}=deps;${source};return {conversationThreadId,dailyPlans,todayPlan,loadDailyPlan,reloadToday,profile,task,entryReady,question,sendQuestion,messages,buyAllMeals,voiceBusy,planPurchaseBusy,setReference:value=>referenceSelection=value}`)(deps))
  page.conversationThreadId.value='existing-consultation-anchor';page.profile.value={householdId:'family',selfMemberId:'self',members:[{id:'self',healthMemberId:member}]};page.entryReady.value=true
  return {page,calls,notify,dispose(){hooks.unmount?.();scope.stop()}}
}

test('completed live chat displays the returned pairing explanation before retaining its meal card',()=>{
 const h=mount()
 try{
  const data={scope:'daily_reference',status:'reference_ready',professional_status:'not_reviewed',nutrition_status:'not_calculated',preview_id:'saved',plan_date:today,meals:[{meal_type:'lunch',dishes:[]}],pairing_summary:'本次搭配说明与营养原文'}
  h.notify({memberId:member,taskType:'reference_meal_preview',requestId:'request-summary',status:'completed',result:{type:'business',kind:'meal_plan_preview',data}})
  const answer=h.page.messages.value.at(-1)
  assert.equal(answer.text,data.pairing_summary)
  assert.deepEqual(answer.business.data,data)
 }finally{h.dispose()}
})

test('all-meal purchase opens the clicked plan date and version rather than today',()=>{
 const h=mount(),tomorrow=plan(7,undefined,'2026-10-28')
 tomorrow.purchase_options=[{kind:'reference',id:'old',meal_types:['breakfast','lunch','dinner']}]
 h.page.dailyPlans.value[today]=plan(2)
 h.page.buyAllMeals(tomorrow)
 assert.deepEqual(h.calls,[{action:'navigate',target:{date:'2026-10-28',version:7},options:{all:true}}])
 h.dispose()
})

test('all-meal purchase ignores partial menus and busy interactions',()=>{
 const h=mount(),full=plan()
 full.purchase_options=[{kind:'reference',id:'old',meal_types:['breakfast','lunch','dinner']}]
 h.page.buyAllMeals({...full,meals:[meal('dinner')]})
 h.page.buyAllMeals(null)
 h.page.voiceBusy.value=true;h.page.buyAllMeals(full)
 h.page.voiceBusy.value=false;h.page.planPurchaseBusy.value=true;h.page.buyAllMeals(full)
 assert.deepEqual(h.calls,[])
 h.dispose()
})

test('view and repeated generation read the existing plan without submitting another task',async()=>{
  const h=mount();h.page.question.value='查看今天的餐单';await h.page.sendQuestion('reference_meal_preview')
  assert.equal(h.page.messages.value.at(-1).planDate,today);assert.equal(h.calls.length,0)
  h.page.question.value='请帮我安排今天的三餐';await h.page.sendQuestion('reference_meal_preview')
  assert.equal(h.page.messages.value.at(-1).planDate,today);assert.equal(h.calls.length,0);h.dispose()
})

test('a chat request to change dinner gives guidance without submitting',async()=>{
  const h=mount()
  try{
    h.page.question.value='把晚餐换成蒸鱼';await h.page.sendQuestion()
    assert.equal(h.page.messages.value.at(-1).text,'已安排的菜品请在餐单里调整。')
    assert.equal(h.calls.some(call=>call.action==='submit'),false)
  }finally{h.dispose()}
})

test('an invalidated lunch is regenerated in a fresh thread at the current daily version',async()=>{
  const current={...plan(8,[]),status:'needs_regeneration',needs_regeneration:['lunch'],regeneration_participants:{lunch:['self']}}
  const h=mount({read:async()=>current})
  try{
    h.page.question.value='安排今天午餐'
    await h.page.sendQuestion('reference_meal_preview')
    const opened=h.calls.find(call=>call.action==='open')
    assert.ok(opened,'an expired lunch must permit a replacement task')
    assert.equal(opened.options.fresh,true)
    assert.equal(opened.selection.daily_base_version,8)
    assert.deepEqual(opened.selection.meal_types,['lunch'])
    assert.equal(h.calls.filter(call=>call.action==='submit').length,1)
  }finally{h.dispose()}
})

test('rebuilding a family lunch preserves its diners unless the user explicitly changes them',async()=>{
  for(const explicit of [false,true]){
    const current={...plan(8,[]),status:'needs_regeneration',needs_regeneration:['lunch'],regeneration_participants:{lunch:['other','self']}}
    const h=mount({read:async()=>current})
    try{
      h.page.profile.value.members.push({id:'other',healthMemberId:'other-health'})
      h.page.question.value=explicit?'只给我安排今天午餐':'安排今天午餐'
      await h.page.sendQuestion('reference_meal_preview')
      const opened=h.calls.find(call=>call.action==='open')
      assert.deepEqual(opened.selection.participant_ids,explicit?['self']:['other','self'])
      assert.equal(opened.options.fresh,true)
    }finally{h.dispose()}
  }
})

test('rebuilding meals with different diners retains the question for separate requests',async()=>{
  const current={...plan(8,[]),status:'needs_regeneration',needs_regeneration:['lunch','dinner'],regeneration_participants:{lunch:['self'],dinner:['other','self']}}
  const h=mount({read:async()=>current})
  try{
    h.page.profile.value.members.push({id:'other',healthMemberId:'other-health'})
    h.page.question.value='安排今天午餐和晚餐'
    await h.page.sendQuestion('reference_meal_preview')
    assert.equal(h.calls.some(call=>call.action==='submit'),false)
    assert.equal(h.page.question.value,'安排今天午餐和晚餐')
  }finally{h.dispose()}
})

test('a completed plan stays read-only when asked to change it in chat',async()=>{
  const h=mount({read:async()=>plan(3)})
  try{
    h.page.setReference({mode:'reference',family_id:'family',plan_date:today,participant_ids:['self'],meal_types:['dinner'],daily_base_version:2})
    h.page.task.value={taskType:'reference_meal_preview',status:'completed',available:true,memberId:member,entry:{thread_id:'old-thread'}}
    h.page.question.value='把晚餐换成蒸鱼';await h.page.sendQuestion()
    assert.equal(h.calls.some(call=>call.action==='submit'),false)
  }finally{h.dispose()}
})

test('a breakfast revision request does not reopen a completed three-meal plan',async()=>{
  const h=mount({read:async()=>plan(3)})
  try{
    h.page.setReference({mode:'reference',family_id:'family',plan_date:today,participant_ids:['self'],meal_types:['breakfast','lunch','dinner'],daily_base_version:2})
    h.page.question.value='把早餐改成粥';await h.page.sendQuestion()
    assert.equal(h.calls.some(call=>call.action==='open'),false)
  }finally{h.dispose()}
})

for(const code of [404,409,410])test(`authoritative daily-plan refusal ${code} removes the saved private card`,async()=>{
  let denied=false
  const h=mount({read:async()=>{if(denied)throw Object.assign(new Error('来源不可读取'),{code});return plan()}})
  await h.page.loadDailyPlan('family',today,0,'scope');assert.ok(h.page.todayPlan.value)
  denied=true;await assert.rejects(()=>h.page.loadDailyPlan('family',today,0,'scope'))
  assert.equal(h.page.todayPlan.value,null);h.dispose()
})

test('a transient daily-plan read failure preserves the last verified card',async()=>{
  let denied=false
  const h=mount({read:async()=>{if(denied)throw Object.assign(new Error('network'),{code:503});return plan()}})
  await h.page.loadDailyPlan('family',today,0,'scope')
  denied=true;await assert.rejects(()=>h.page.loadDailyPlan('family',today,0,'scope'))
  assert.equal(h.page.todayPlan.value.version,1);h.dispose()
})

test('an earlier read cannot replace a later completed read for the same date',async()=>{
  const pending=[];const h=mount({read:()=>new Promise(resolve=>pending.push(resolve))})
  const a=h.page.loadDailyPlan('family',today,0,'scope'),b=h.page.loadDailyPlan('family',today,0,'scope')
  pending[1](plan(2));await b;pending[0](plan(1));await a
  assert.equal(h.page.todayPlan.value.version,2);h.dispose()
})

test('reading dinner and refreshing the same day share one read',async()=>{
  const pending=[]
  let started
  const firstRead=new Promise(resolve=>{started=resolve})
  const send=()=>new Promise(resolve=>{pending.push(resolve);started()})
  const h=mount({read:(family,date,_transport,options)=>readDailyMealPlan(family,date,send,options)})
  try {
    h.page.question.value='看看今天的晚餐餐单'
    const sending=h.page.sendQuestion('reference_meal_preview')
    await firstRead
    const refresh=h.page.loadDailyPlan('family',today,0,'scope')
    assert.equal(pending.length,1)
    pending[0]({data:plan(12)})
    await Promise.all([sending,refresh])
    assert.equal(h.calls.filter(call=>call.action==='submit').length,0)
    assert.equal(h.page.todayPlan.value.version,12)
  } finally { h.dispose() }
})

test('a read after publication supersedes an outstanding pre-publication read',async()=>{
  const pending=[]
  const send=()=>new Promise(resolve=>pending.push(resolve))
  const before=readDailyMealPlan('family',today,send)
  const after=readDailyMealPlan('family',today,send,{fresh:true})
  pending[1]({data:plan(13)})
  assert.equal((await after).version,13)
  pending[0]({data:plan(12)})
  assert.equal((await before).version,13)
})

test('tomorrow and today retain independent plan objects',async()=>{
  const h=mount({read:async(_family,date)=>plan(date===today?1:2,[meal('breakfast')],date)})
  await h.page.loadDailyPlan('family',today,0,'scope');await h.page.loadDailyPlan('family','2026-10-28',0,'scope')
  assert.equal(h.page.todayPlan.value.date,today);assert.equal(h.page.dailyPlans.value['2026-10-28'].version,2);h.dispose()
})

test('another device running the same plan prevents duplicate submission and keeps the saved plan',async()=>{
  const h=mount({read:async()=>({...plan(1,[meal('lunch')]),pending:{request_id:'other-request',status:'running'}})})
  try{
    h.page.question.value='今晚吃什么';await h.page.sendQuestion()
    assert.equal(h.calls.length,0)
    assert.deepEqual(h.page.todayPlan.value.meals.map(item=>item.meal_type),['lunch'])
    assert.equal(h.page.messages.value.at(-1).planPending,true)
  }finally{h.dispose()}
})

test('a short answer continues the bound meal question and keeps its original selection',async()=>{
  const h=mount();const selection={mode:'reference',family_id:'family',plan_date:today,participant_ids:['self'],meal_types:['dinner'],daily_base_version:1}
  h.page.setReference(selection);h.page.task.value={taskType:'reference_meal_preview',result:{type:'needs_input'},available:true,memberId:member,entry:{thread_id:'thread'}}
  h.page.question.value='不吃花生';await h.page.sendQuestion()
  assert.equal(h.calls.filter(call=>call.action==='open').length,0)
  assert.equal(h.page.task.value.taskType,'reference_meal_preview');assert.ok(h.calls.some(call=>call.action==='submit'&&call.text==='不吃花生'));h.dispose()
})

test('a needs-input answer preserves all bound diners and meals even when the saved plan differs',async()=>{
  const h=mount()
  h.page.profile.value.members.push({id:'other',healthMemberId:'other-health'})
  const selection={mode:'reference',family_id:'family',plan_date:today,participant_ids:['other','self'],meal_types:['breakfast','lunch','dinner'],daily_base_version:1}
  h.page.setReference(selection)
  h.page.task.value={taskType:'reference_meal_preview',result:{type:'needs_input'},available:true,memberId:member,entry:{thread_id:'thread'}}
  h.page.question.value='早餐加点豆浆';await h.page.sendQuestion()
  assert.deepEqual(selection.participant_ids,['other','self'])
  assert.deepEqual(selection.meal_types,['breakfast','lunch','dinner'])
  assert.equal(h.calls.filter(call=>call.action==='open').length,0)
  assert.ok(h.calls.some(call=>call.action==='submit'));h.dispose()
})


test('completed plan refreshes a stale running chat request',async()=>{
  const h=mount();h.page.setReference({plan_date:today});h.page.task.value={taskType:'reference_meal_preview',requestId:'req',status:'running'}
  await h.page.loadDailyPlan('family',today,0,'scope');await nextTick()
  assert.equal(h.calls.filter(call=>call.action==='refresh').length,1);assert.equal(h.page.task.value.status,'completed');h.dispose()
})

test('manual reload refreshes a running chat request when the plan is still pending',async()=>{
  const h=mount({read:async()=>({...plan(),pending:{request_id:'req',status:'running'}})});h.page.setReference({plan_date:today});h.page.task.value={taskType:'reference_meal_preview',requestId:'req',status:'running'}
  await h.page.reloadToday()
  assert.equal(h.calls.filter(call=>call.action==='refresh').length,1);assert.equal(h.page.task.value.status,'completed');h.dispose()
})

for(const question of ['查看今天晚餐餐单','看看今天晚饭的菜单','今天晚上可以吃什么'])test('read-only dinner scope is retained: '+question,async()=>{const h=mount();h.page.question.value=question;await h.page.sendQuestion();assert.deepEqual(h.page.messages.value.at(-1).planMeals,['dinner']);assert.equal(h.calls.some(c=>c.action==='submit'),false);h.dispose()})
