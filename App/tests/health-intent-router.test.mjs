import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {referenceSelection} from '../src/services/reference-meal-plan.js'
import {chatMessages} from '../src/services/cloud-chat.js'

const profile={householdId:'family',selfMemberId:'self',members:[{id:'self',healthMemberId:'member'}]}
const chat=readFileSync(new URL('../src/components/CloudNutritionChat.vue',import.meta.url),'utf8')
const preparation=chat.slice(chat.indexOf('      const previousVersion=referenceSelection?.daily_base_version'),chat.indexOf('\n      if(disposed',chat.indexOf('      const previousVersion=referenceSelection?.daily_base_version')))
const prepare=new Function('context',`return (async()=>{
 const {profile,text,intent,loadDailyPlan}=context
 const chooseReference=context.chooseReference,localDate=()=> '2026-11-27',props={route:{}},epoch=0,scope='synthetic'
 let referenceSelection=null,referenceFollowUp=false,continuing=false,action='change'
 const mealIntent=intent?.route==='single_day_meal'?intent:null,referenceAdjustment=false
 ${preparation}
 return referenceSelection
})()`)

for(const [text,date,meals] of [
 ['重新生成今日餐单','2026-11-27',['breakfast','lunch','dinner']],
 ['重新安排今天菜单','2026-11-27',['breakfast','lunch','dinner']],
 ['重新生成明日餐单','2026-11-28',['breakfast','lunch','dinner']],
 ['换一下午餐','2026-11-27',['lunch']],
])test('validated meal scope reaches plan read in a fresh conversation: '+text,async()=>{
 const calls=[]
 const selection=await prepare({profile:{value:profile},text,intent:{route:'single_day_meal',action:'change',business_date:date,meal_types:meals},chooseReference:referenceSelection,loadDailyPlan:async(...args)=>{calls.push(args);return {version:1}}})
 assert.deepEqual(calls,[['family',date,0,'synthetic']])
 assert.deepEqual(selection.meal_types,meals)
 assert.deepEqual(selection.participant_ids,['self'])
})
test('an unclassified broad change still requires a meal scope before reading a plan',async()=>{
 await assert.rejects(prepare({profile:{value:profile},text:'换一下',intent:null,chooseReference:referenceSelection,loadDailyPlan:()=>assert.fail('must clarify first')}),/请说明要调整早餐、午餐还是晚餐/)
})
test('backend exact date reaches reference selection for the day after tomorrow',()=>{
 const selection=referenceSelection(profile,'后天吃啥',{today:'2026-11-09',tomorrow:'2026-11-10',intent:{route:'single_day_meal',business_date:'2026-11-11',meal_types:['breakfast','lunch','dinner']}})
 assert.equal(selection.plan_date,'2026-11-11')
})
test('backend selected meal types are retained rather than inferred again',()=>{
 const selection=referenceSelection(profile,'换一下',{today:'2026-11-09',intent:{route:'single_day_meal',business_date:'2026-11-15',meal_types:['lunch']}})
 assert.equal(selection.plan_date,'2026-11-15');assert.deepEqual(selection.meal_types,['lunch'])
})
test('plan entry survives server history reload without exposing serialized protocol',()=>{
 const messages=chatMessages({history:[{id:1,role:'assistant',request_id:'request',content:JSON.stringify({result_type:'health_intent',route:'exclusive_plan',action:'handoff',message:'目前可生成 21 天 AI 专属计划'})}]})
 assert.equal(messages[0].text,'目前可生成 21 天 AI 专属计划')
 assert.equal(messages[0].exclusivePlanEntry,true)
 assert.equal(messages[0].requestId,'request')
})
