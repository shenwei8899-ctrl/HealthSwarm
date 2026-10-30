import {watch} from 'vue'
import {createChatEntryTransition} from '../src/services/chat-entry-transition.js'
import {createChatKeyboardLayout} from '../src/services/chat-keyboard-layout.js'
import test from 'node:test'
import assert from 'node:assert/strict'
import { parseChatMealIntent } from '../src/utils/chat-meal-intent.js'
import { loadChatMealPlan } from '../src/services/chat-meal-plan.js'

const day = '2026-10-31'
const parse = text => parseChatMealIntent(text, day)
const profile = { selfMemberId: 'self', defaultDiners: ['self', 'other'], members: [{id:'self'}, {id:'other'}] }
const arrangement = () => ({date:day, version:1, meals:['breakfast','lunch','dinner'].map(type=>({type,members:[{id:'self'},{id:'other'}]}))})

test('explicit requests in the reported conversation enter real meal planning', () => {
  for (const text of ['为我配餐，必须为我进行配餐今天怎么吃', '一个人，直接为我进行这顿配餐', '今天怎么吃', '帮我搭配今天的三餐', '配餐']) {
    assert.ok(parse(text), text)
  }
  assert.equal(parse('为我配餐，必须为我进行配餐今天怎么吃').audience, 'self')
  assert.equal(parse('按家庭档案为我配餐').audience,'self')
  assert.deepEqual(parse('今天怎么吃').meals, ['breakfast','lunch','dinner'])
})

test('nutrition education and cancelled requests remain ordinary conversation', () => {
  for (const text of ['糖尿病家庭怎么吃？', '糖尿病配餐有什么原则？', '请介绍糖尿病配餐原则', '请帮我解释糖尿病配餐', '给我科普一下糖尿病如何配餐', '糖尿病今天怎么吃', '什么是配餐', '不要为我配餐', '不需要帮我配餐', '停止配餐', '取消这次配餐', '不要给父亲配餐', '你好']) assert.equal(parse(text), null, text)
  assert.ok(parse('我有糖尿病，请为我配餐'))
  for (const text of ['糖尿病患者怎样安排今天的三餐？', '糖尿病如何制定配餐方案？', '为什么糖尿病需要制定食谱？']) assert.equal(parse(text), null, text)
})

test('date and meal selection follow the explicit request across the month boundary', () => {
  assert.deepEqual(parse('给我安排明天早餐'), {date:'2026-11-01',meals:['breakfast'],audience:'self',unsupportedDate:false,requiresProfileReview:false})
  assert.equal(parse('今晚全家吃什么？').audience, 'family')
  assert.deepEqual(parse('今天午餐和晚餐吃什么').meals, ['lunch','dinner'])
  assert.equal(parse('帮我规划下周餐单').unsupportedDate, true)
  assert.equal(parse('给我配餐，不要加花生，我过敏').requiresProfileReview, true)
  assert.deepEqual(parse('给我安排明早早饭').meals,['breakfast'])
  assert.equal(parse('给我安排明晚晚饭').date,'2026-11-01')
})

test('personal requests adjust only requested meals and return the saved arrangement', async () => {
  const state = {phase:'idle',error:'',arrangement:null}, calls=[]
  const client = {
    async load(date){calls.push(['load',date]);state.phase='ready';state.arrangement=arrangement()},
    async changeMembers(type,ids){calls.push(['members',type,ids]);state.arrangement={...state.arrangement,version:state.arrangement.version+1,meals:state.arrangement.meals.map(meal=>meal.type===type?{...meal,members:ids.map(id=>({id}))}:meal)}}
  }
  const result=await loadChatMealPlan(parse('为我安排今天午餐'),{client,state,profile})
  assert.equal(result,state.arrangement)
  assert.deepEqual(calls,[['load',day],['members','lunch',['self']]])
  assert.deepEqual(result.meals.find(m=>m.type==='dinner').members.map(m=>m.id),['self','other'])
})

test('already matching members do not create additional generation or mutation', async () => {
  const state={phase:'ready',error:'',arrangement:arrangement()},calls=[]
  const client={async load(){calls.push('read')},async changeMembers(){calls.push('write')}}
  assert.ok(await loadChatMealPlan(parse('今晚全家吃什么'),{client,state,profile}))
  assert.deepEqual(calls,['read'])
})

test('failed or cancelled loads cannot publish a menu or change membership', async () => {
  for (const cancelled of [false,true]) {
    let current=true,writes=0
    const state={phase:'idle',error:'',arrangement:null}
    const client={async load(){current=!cancelled;Object.assign(state,{phase:'error',error:'规则尚未就绪'})},async changeMembers(){writes++}}
    assert.equal(await loadChatMealPlan(parse('为我配餐'),{client,state,profile,isCurrent:()=>current}),null)
    assert.equal(writes,0)
  }
})

test('new restrictions and unsupported dates keep the request actionable without generating unsafe meals', async () => {
  const client={async load(){assert.fail('must first confirm missing information')}}
  await assert.rejects(loadChatMealPlan(parse('给我配餐，不要加花生'),{client,state:{},profile}),/家庭档案/)
  await assert.rejects(loadChatMealPlan(parse('给我规划下周餐单'),{client,state:{},profile}),/今天或明天/)
  for (const condition of ['肾病', '糖尿病', '高血压', '孕期']) {
    const intent=parse(`我有${condition}，请为我配餐`)
    assert.equal(intent.requiresProfileReview,true)
    await assert.rejects(loadChatMealPlan(intent,{client,state:{},profile}),/家庭档案.*按档案为我配餐/)
  }
  assert.equal(parse('按档案为我配餐').requiresProfileReview,false)
  for(const span of ['三天','两天','十一天','3天','14天']) {
    assert.equal(parse(`给我安排${span}食谱`).unsupportedDate,true)
    await assert.rejects(loadChatMealPlan(parse(`给我安排${span}食谱`),{client,state:{},profile}),/今天或明天/)
  }
  assert.equal(parse('给我安排一天食谱').unsupportedDate,false)
})

test('failed membership changes retain the server error and do not return the earlier family menu as personal', async () => {
  const state={phase:'ready',error:'',arrangement:arrangement()}
  const client={async load(){},async changeMembers(){state.error='成员授权已失效'}}
  assert.equal(await loadChatMealPlan(parse('为我配餐'),{client,state,profile}),null)
  assert.equal(state.error,'成员授权已失效')
})

test('explicit retry resumes the existing daily task through the client', async () => {
  const state={phase:'ready',error:'',arrangement:arrangement()},calls=[]
  const client={async load(date,retry){calls.push([date,retry])},async changeMembers(){assert.fail('no membership change needed')}}
  assert.ok(await loadChatMealPlan(parse('今天全家吃什么'),{client,state,profile,retry:true}))
  assert.deepEqual(calls,[[day,true]])
})

test('a general today request preserves the saved participants for each meal', async () => {
  const saved=arrangement();saved.meals[1].members=[{id:'other'}]
  const state={phase:'ready',error:'',arrangement:saved}
  const client={async load(){},async changeMembers(){assert.fail('no participant change was requested')}}
  assert.equal(await loadChatMealPlan(parse('今天怎么吃'),{client,state,profile}),saved)
  assert.deepEqual(saved.meals[1].members,[{id:'other'}])
})
