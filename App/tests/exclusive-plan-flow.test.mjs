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
test('首次进入只读取，明确点击生成后才提交，重进与切档复用服务端任务',async()=>{
  let current={status:'empty',plans:[]}
  const h=harness(async r=>{if(r.method==='POST')current={status:'generating',group_id:'g',plans:[]};return {data:current}})
  await h.flow.open();assert.equal(h.calls.filter(r=>r.method==='POST').length,0)
  await h.flow.act('ensure');h.flow.select('premium');await h.flow.open()
  assert.equal(h.calls.filter(r=>r.method==='POST').length,1)
  assert.equal(h.state.group.group_id,'g')
})
test('响应丢失后保留原请求号，恢复不多建推荐组',async()=>{
  let fail=true
  const h=harness(async r=>{if(r.method==='POST' && fail){fail=false;throw new Error('offline')}return {data:{status:r.method?'generating':'empty',group_id:'g',plans:[]}}})
  await h.flow.open();await h.flow.act('ensure');assert.equal(h.values.get('exclusive-plan-intent:week-v1:f').client_request_id,'stable-request')
  await h.flow.open();await h.flow.act('ensure')
  assert.deepEqual(h.calls.filter(r=>r.method==='POST').map(r=>r.data.client_request_id),['stable-request','stable-request'])
})
test('网关错误保留请求编号和原幂等键，重新生成后清除错误', async () => {
  let failed = false
  const h = harness(async request => {
    if (!request.method) return {data: {status: 'empty'}}
    if (!failed) {
      failed = true
      throw Object.assign(new Error('Bad Gateway'), {code: 502, traceId: 'gateway-trace'})
    }
    return {data: {status: 'generating', group_id: 'g'}}
  })
  await h.flow.open()
  await h.flow.act('ensure')
  assert.match(h.state.error, /暂时无法连接/)
  assert.equal(h.state.traceId, 'gateway-trace')
  await h.flow.act('ensure')
  assert.equal(h.state.status, 'generating')
  assert.equal(h.state.traceId, '')
  assert.equal(h.state.error, '')
  assert.equal(h.calls[1].data.client_request_id, h.calls[2].data.client_request_id)
})
test('首次读取遇到网关错误时不进入空计划状态', async () => {
  const h = harness(async () => {
    throw Object.assign(new Error('Bad Gateway'), {code: 502})
  })
  await h.flow.open()
  assert.equal(h.state.status, 'reading')
  assert.match(h.state.error, /暂时无法连接/)
  assert.equal(h.state.busy, false)
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
test('Agent 预览三档直接展示，无需读取商城计划', async () => {
  let commerceCalls = 0
  const h = harness(async () => ({data: {
    status: 'ready', group_id: 'g', preview_only: true,
    plans: ['premium', 'economy', 'standard'].map(tier_code => ({tier_code})),
  }}), {servicePlans: async () => { commerceCalls++ }})
  await h.flow.open()
  assert.equal(commerceCalls, 0)
  assert.deepEqual(h.state.plans.map(plan => plan.tier_code), ['economy', 'standard', 'premium'])
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

test('每日食材随日期切换，未知小计与真实零价保持不同', async () => {
  const { planDayProcurement, matchedSubtotalText } = await import('../src/services/plan-presentation.js')
  const plan = {days: [
    {day_no: 1, procurement: {ingredients: [{ingredient: '鸡蛋1个'}], pricing: {matched_subtotal_cent: null}}},
    {day_no: 2, procurement: {ingredients: [{ingredient: '菠菜100克'}], pricing: {matched_subtotal_cent: 0}}},
  ]}
  assert.equal(planDayProcurement(plan, 2).ingredients[0].ingredient, '菠菜100克')
  assert.equal(matchedSubtotalText(planDayProcurement(plan, 1).pricing), '暂无可核算小计')
  assert.equal(matchedSubtotalText(planDayProcurement(plan, 2).pricing), '¥0.00')
  assert.equal(planDayProcurement(plan, 3), null)
})
