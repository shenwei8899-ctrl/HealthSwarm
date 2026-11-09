import test from 'node:test'
import assert from 'node:assert/strict'
import {referenceSelection} from '../src/services/reference-meal-plan.js'
import {chatMessages} from '../src/services/cloud-chat.js'

const profile={householdId:'family',selfMemberId:'self',members:[{id:'self',healthMemberId:'member'}]}
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
