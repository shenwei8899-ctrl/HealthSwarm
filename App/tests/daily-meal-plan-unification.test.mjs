import {parseChatMealIntent,isMealPlanningCancelled} from '../src/utils/chat-meal-intent.js'
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

test('new plans use the current profile; explicit family requests include the family',()=>{
  const p={householdId:'family',selfMemberId:'self',defaultDiners:['self','other'],members:[{id:'self',healthMemberId:member},{id:'other',healthMemberId:'other'}]}
  assert.deepEqual(referenceSelection(p,'安排今天三餐',{today}).participant_ids,['self'])
  assert.deepEqual(referenceSelection(p,'给全家安排今天三餐',{today}).participant_ids,['other','self'])
  assert.deepEqual(referenceSelection(p,'只给我安排今天三餐',{today}).participant_ids,['self'])
})

function mount({read=async()=>plan()}={}){
  const hooks={},cache=new Map(),calls=[];let notify
  const flow={hide(){},async open(memberId,taskType,selection){calls.push({action:'open',memberId,taskType,selection});notify({memberId,taskType,available:true,entry:{thread_id:'thread'}})},async submit(text){calls.push({action:'submit',text});return true},async refresh(){calls.push({action:'refresh'});notify({taskType:'reference_meal_preview',requestId:'req',status:'completed',available:true})}}
  const state=()=>({phase:'idle',busy:false})
  const deps={createChatEntryTransition,createChatKeyboardLayout,watch,ref,reactive,computed,nextTick,defineProps:()=>({route:{entry:'conversation'}}),onMounted:fn=>hooks.mounted=fn,onShow:fn=>hooks.show=fn,onHide:fn=>hooks.hide=fn,onUnmounted:fn=>hooks.unmount=fn,
    parseChatMealIntent,isMealPlanningCancelled,chatPresentation,chooseReference:referenceSelection,isReferencePlan,readDailyMealPlan:read,mealQuestionAction,
    dailyArrangementState:state,createDailyArrangementClient:()=>({reset(){},dispose(){}}),
    createHealthTaskFlow:({onChange})=>{notify=onChange;return flow},
    HEALTH_TEXT_TASKS:{consultation:'咨询',reference_meal_preview:'餐单'},
    localDate:()=>today,storageContext:()=> 'scope',getSession:()=>({accountId:'self',householdId:'family',token:'synthetic'}),
    scopedStorage:{getStorageSync:k=>cache.get(k),setStorageSync:(k,v)=>cache.set(k,v)},newHealthRequestId:()=>String(calls.length)+'-id',
    readChatSnapshot:async()=>({messages:[],runs:[]}),selectChatPrompts:()=>[],uni:{showToast(){}},
    readCurrentPreparation:async()=>({status:'absent'}),request:async()=>({data:{}})}
  const source=readFileSync(new URL('../src/components/CloudNutritionChat.vue',import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
  const scope=effectScope()
  const page=scope.run(()=>new Function('deps',`const {${Object.keys(deps)}}=deps;${source};return {conversationThreadId,dailyPlans,todayPlan,loadDailyPlan,reloadToday,profile,task,entryReady,question,sendQuestion,messages,setReference:value=>referenceSelection=value}`)(deps))
  page.conversationThreadId.value='existing-consultation-anchor';page.profile.value={householdId:'family',selfMemberId:'self',members:[{id:'self',healthMemberId:member}]};page.entryReady.value=true
  return {page,calls,notify,dispose(){hooks.unmount?.();scope.stop()}}
}

test('view and repeated generation read the existing plan without submitting another task',async()=>{
  const h=mount();h.page.question.value='查看今天的餐单';await h.page.sendQuestion('reference_meal_preview')
  assert.equal(h.page.messages.value.at(-1).planDate,today);assert.equal(h.calls.length,0)
  h.page.question.value='请帮我安排今天的三餐';await h.page.sendQuestion('reference_meal_preview')
  assert.equal(h.page.messages.value.at(-1).planDate,today);assert.equal(h.calls.length,0);h.dispose()
})

test('changing dinner binds the current version and only requests dinner',async()=>{
  const h=mount();h.page.question.value='把晚餐换成蒸鱼';await h.page.sendQuestion('reference_meal_preview')
  const opened=h.calls.find(call=>call.action==='open')
  assert.equal(opened.taskType,'reference_meal_preview');assert.equal(opened.selection.daily_base_version,1)
  assert.deepEqual(opened.selection.meal_types,['dinner']);assert.ok(h.calls.some(call=>call.action==='submit'));h.dispose()
})

test('revising a completed plan reopens its reference thread with the current daily version',async()=>{
  const h=mount({read:async()=>plan(3)})
  h.page.setReference({mode:'reference',family_id:'family',plan_date:today,participant_ids:['self'],meal_types:['dinner'],daily_base_version:2})
  h.page.task.value={taskType:'reference_meal_preview',status:'completed',available:true,memberId:member,entry:{thread_id:'old-thread'}}
  h.page.question.value='把晚餐换成蒸鱼';await h.page.sendQuestion('reference_meal_preview')
  const opened=h.calls.find(call=>call.action==='open')
  assert.ok(opened,'a completed daily version must not submit through its old binding')
  assert.equal(opened.selection.daily_base_version,3)
  assert.deepEqual(opened.selection.meal_types,['dinner'])
  assert.ok(h.calls.some(call=>call.action==='submit'));h.dispose()
})

test('an explicit breakfast revision narrows a completed three-meal plan',async()=>{
  const h=mount({read:async()=>plan(3)})
  h.page.setReference({mode:'reference',family_id:'family',plan_date:today,participant_ids:['self'],meal_types:['breakfast','lunch','dinner'],daily_base_version:2})
  h.page.task.value={taskType:'reference_meal_preview',status:'completed',available:true,memberId:member,entry:{thread_id:'old-thread'}}
  h.page.question.value='把早餐改成粥';await h.page.sendQuestion()
  const opened=h.calls.find(call=>call.action==='open')
  assert.deepEqual(opened?.selection.meal_types,['breakfast'])
  assert.equal(opened.selection.daily_base_version,3);h.dispose()
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

test('tomorrow and today retain independent plan objects',async()=>{
  const h=mount({read:async(_family,date)=>plan(date===today?1:2,[meal('breakfast')],date)})
  await h.page.loadDailyPlan('family',today,0,'scope');await h.page.loadDailyPlan('family','2026-10-28',0,'scope')
  assert.equal(h.page.todayPlan.value.date,today);assert.equal(h.page.dailyPlans.value['2026-10-28'].version,2);h.dispose()
})

test('another device running the same plan prevents duplicate submission and keeps the saved plan',async()=>{
  const h=mount({read:async()=>({...plan(),pending:{request_id:'other-request',status:'running'}})})
  h.page.question.value='把晚餐换成蒸鱼';await h.page.sendQuestion('reference_meal_preview')
  assert.equal(h.calls.length,0);assert.equal(h.page.todayPlan.value.meals.length,3)
  assert.equal(h.page.question.value,'把晚餐换成蒸鱼');h.dispose()
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
