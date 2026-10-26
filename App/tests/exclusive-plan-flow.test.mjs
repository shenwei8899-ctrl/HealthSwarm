import test from 'node:test'
import assert from 'node:assert/strict'
import { createExclusivePlanFlow, exclusivePlanState, planMoney } from '../src/services/exclusive-plan-flow.js'
import { validPlanRoute, dayMeals, priceText } from '../src/services/plan-presentation.js'

function harness(send, commerce={}) {
  const state=exclusivePlanState(), values=new Map(), scheduled=[], calls=[]
  let scope=1
  const flow=createExclusivePlanFlow({state,send:async request=>{calls.push(request);return send(request)},commerce,family:()=> 'f',revision:()=>scope,
    storage:{getStorageSync:k=>values.get(k),setStorageSync:(k,v)=>values.set(k,v)},newId:()=> 'stable-request',later:fn=>{scheduled.push(fn);return scheduled.length},cancelLater:()=>{}})
  return {state,flow,calls,values,scheduled,changeAccount:()=>scope++}
}
test('首次进入只提交一次，重进与切档复用服务端任务',async()=>{
  let current={status:'empty',plans:[]}
  const h=harness(async r=>{if(r.method==='POST')current={status:'generating',group_id:'g',plans:[]};return {data:current}})
  await h.flow.open();h.flow.select('premium');await h.flow.open()
  assert.equal(h.calls.filter(r=>r.method==='POST').length,1)
  assert.equal(h.state.group.group_id,'g')
})
test('响应丢失后保留原请求号，恢复不多建推荐组',async()=>{
  let fail=true
  const h=harness(async r=>{if(r.method==='POST' && fail){fail=false;throw new Error('offline')}return {data:{status:r.method?'generating':'empty',group_id:'g',plans:[]}}})
  await h.flow.open();assert.equal(h.values.get('exclusive-plan-intent:v1:f').client_request_id,'stable-request')
  await h.flow.open()
  assert.deepEqual(h.calls.filter(r=>r.method==='POST').map(r=>r.data.client_request_id),['stable-request','stable-request'])
})
test('账号改变时丢弃迟到计划，不跨账号展示',async()=>{
  let release
  const h=harness(()=>new Promise(resolve=>release=resolve))
  const pending=h.flow.open();h.changeAccount();release({data:{status:'generating',group_id:'private'}});await pending
  assert.equal(h.state.group,null);assert.equal(h.state.plans.length,0)
})
test('商城缺档或返回不同版本时拒绝展示混合推荐组',async()=>{
  const h=harness(async()=>({data:{status:'ready',group_id:'g',plans:[{plan_sn:'p',plan_version:1}]}}),{servicePlans:async()=>({recommendation_group_ref:'g',items:[{plan_sn:'p',plan_version:2,tier_code:'economy',recommendation_group_ref:'g'}]})})
  await h.flow.open();assert.equal(h.state.plans.length,0);assert.match(h.state.error,/更新/)
})
test('未配置不会偷偷填套餐或持续自动重试',async()=>{
  const h=harness(async()=>{throw Object.assign(new Error('暂未开放'),{businessCode:'exclusive_plan_policy_missing',code:503})})
  await h.flow.open();assert.equal(h.state.status,'unavailable');assert.equal(h.scheduled.length,0);assert.equal(h.calls.length,1)
})
test('未知金额与真实零价格不同，路由必须包含版本',()=>{
  assert.equal(planMoney(null),'待报价');assert.equal(priceText(0),'¥0.00')
  assert.throws(()=>validPlanRoute({plan_sn:'p'}));assert.throws(()=>validPlanRoute({plan_sn:'p',plan_version:'1.5'}))
  assert.deepEqual(validPlanRoute({plan_sn:'p',plan_version:'2'}),{sn:'p',version:2})
})
test('同一餐可有多道菜，不用样例补缺失餐次',()=>{
  const meals=dayMeals({meals:[{meal_type:'breakfast',recipe_name:'粥'},{meal_type:'breakfast',recipe_name:'蛋'}]})
  assert.equal(meals[0].dishes.length,2);assert.equal(meals[1].dishes.length,0)
})
