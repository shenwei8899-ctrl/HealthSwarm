import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { computed, reactive, ref } from 'vue'
import { archiveDate, archiveMeals, archiveCard, plannedGrams } from '../src/services/meal-archive-presentation.js'
import { createHealthPlanClient, healthPlanState } from '../src/services/health-plan-client.js'
import { createMealArchiveClient, mealArchiveState } from '../src/services/meal-archive-client.js'
import { dishTitle } from '../src/utils/meal-presentation.js'
import { recipeCovers } from '../src/data/recipe-covers.js'

const a = '11111111-1111-4111-8111-111111111111', b = '22222222-2222-4222-8222-222222222222'
const planId = '33333333-3333-4333-8333-333333333333'
const plan = id => ({ plan_id: planId, member_id: id, version: 2, plan_date: '2026-10-30',
  meals: [{ meal_type: 'breakfast', dishes: [{ name: '合成早餐', planned_grams: '0' }] }] })

test('archive dates use the Shanghai day boundary and reject invalid dates', () => {
  const now = new Date('2026-10-29T16:00:00Z')
  assert.equal(archiveDate('2026-10-30', now).caption, '今天 · 周五')
  assert.equal(archiveDate('2026-10-29', now).caption, '昨天 · 周四')
  assert.equal(archiveDate('2025-10-30', now).caption, '2025年 · 周四')
  for (const value of ['2026-02-30', undefined, '', '2026-10-30<script>']) {
    assert.equal(archiveDate(value, now).title, '日期待核对')
  }
})

test('cards show saved snapshot dishes without inventing meals or adoption status', () => {
  const source = plan(a), before = structuredClone(source)
  const card = archiveCard(source)
  assert.equal(card.title, '10月30日的餐单')
  assert.equal(card.summary, '个人餐单 · 1餐')
  assert.deepEqual(archiveMeals(source).map(row => row.summary), ['合成早餐', '本餐未记录', '本餐未记录'])
  assert.equal(card.approved, undefined); assert.equal(card.adopted, undefined)
  assert.deepEqual(source, before)
  assert.equal(plannedGrams(0), '0g'); assert.equal(plannedGrams(null), '份量未知')
  const family = archiveCard({ ...source, members: { [a]: {}, [b]: {} } })
  assert.equal(family.summary, '2位成员 · 1餐')
})

function mount(override = async () => null, options = { memberId: a }) {
  const hooks = {}, calls = [], storage = new Map(), navigation = []; let epoch = 1
  const send = async options => {
    calls.push(structuredClone(options))
    const replacement = await override(options)
    if (replacement) return replacement
    if (options.path.includes('/daily-meal-plans')) return { data: { plans: [], next_before: null } }
    if (options.path.endsWith('/members')) return { data: [a, b].map((id, index) => ({ id, display_name: index ? '家人' : '本人', scopes: ['diet_edit'] })) }
    if (options.path.includes('/meal-plans?')) return { data: { plans: [plan(options.path.includes(b) ? b : a)], next_offset: null } }
    if (options.path.endsWith('/meal-plans/' + planId)) return { data: plan(currentMember()) }
    if (options.path.includes('/approval-state?')) return { data: { plan_id: planId, version: 2, available: true, review_id: 'review', sources: { profiles: { [currentMember()]: { version: 1 } } } } }
    if (options.path.includes('/adopted-plan?')) return { data: { member_id: currentMember(), plan_date: '2026-10-30', status: 'not_adopted', plan: null } }
    throw new Error('Unexpected request: ' + options.path)
  }
  function currentMember() { return page.state.memberId }
  const deps = { computed, reactive, ref, archiveCard, archiveDate, plannedGrams, healthPlanState, mealArchiveState, dishTitle,
    createMealArchiveClient: ({ state }) => createMealArchiveClient({ state, send, session:()=>({householdId:'family'}), context:()=>String(epoch) }),
    onLoad: fn => hooks.load = fn, onShow: fn => hooks.show = fn, onHide: fn => hooks.hide = fn, onUnload: fn => hooks.unload = fn, onBackPress: fn => hooks.back = fn,
    createHealthPlanClient: ({ state }) => createHealthPlanClient({ state, send, revision: () => epoch, newId: () => 'fixed-request',
      storage: { getStorageSync: key => storage.get(key), setStorageSync: (key, value) => storage.set(key, structuredClone(value)) } }),
    uni: { pageScrollTo: () => {}, navigateBack: () => navigation.push('back'), navigateTo: options => navigation.push(options.url) },
  }
  const script = readFileSync(new URL('../src/pages/health/plans.vue', import.meta.url), 'utf8')
    .match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  const fields = 'state,memberId,selectedPlanId,view,replace,reason,reviewExpanded,client,select,back,changeMember,retry,chat,savedState,savedClient,savedDish,legacyMode'
  const page = new Function('deps', `const {${Object.keys(deps)}}=deps;${script};return {${fields}}`)(deps)
  hooks.load(options)
  return { ...page, hooks, calls, navigation, switchAccount: () => epoch++ }
}

const archived = { id:'saved-day',family_id:'family',plan_date:'2026-11-19',version:4,
  meals:[{meal_type:'dinner',members:[{id:a,name:'本人'}],dishes:[{name:'已保存的晚餐',ingredients:['青菜'],steps:['煮熟'] }]}] }

test('archive thumbnails belong to the same saved meal and keep the source snapshot unchanged',()=>{
 const snapshot={meals:[{meal_type:'breakfast',dishes:[{name:'无图鸡蛋'},{name:'真实青菜',image_url:'/uploads/greens.jpg'}]},
  {meal_type:'lunch',dishes:[{name:'无图午餐'}]},
  {meal_type:'dinner',dishes:[{name:'晚餐',cover:{image_url:'https://example.test/dinner.jpg'}}]}]}
 const original=structuredClone(snapshot),rows=archiveMeals(snapshot)
 assert.equal(rows[0].image,'/uploads/greens.jpg');assert.equal(rows[0].imageLabel,'真实青菜')
 assert.equal(rows[0].summary,'无图鸡蛋 · 真实青菜');assert.equal(rows[1].image,'')
 assert.equal(rows[2].image,'https://example.test/dinner.jpg');assert.deepEqual(snapshot,original)
})
test('only exact immutable recipe sources supply covers; missing meals and malformed image values stay empty',()=>{
 const cover=recipeCovers[0],source={kb_id:cover.kb_id,file_id:cover.file_id,file_hash:cover.file_hash}
 const row=dish=>archiveMeals({meals:[{meal_type:'breakfast',dishes:[dish]}]})[0]
 assert.equal(row({name:'真实菜谱',source}).image,cover.image_url)
 assert.equal(row({name:'旧版本',source:{...source,file_hash:'changed'}}).image,'')
 for(const image_url of [{url:'/uploads/wrong.jpg'},'javascript:alert(1)','//foreign.test/image.jpg'])assert.equal(row({name:'无效图片',image_url}).image,'')
 assert.ok(archiveMeals({meals:[]}).every(meal=>meal.image===''&&meal.summary==='本餐未记录'))
})

test('My Meals reads successful daily snapshots by default, without querying old member drafts',async()=>{
 const p=mount(async options=>({data:options.path.endsWith('/archive')?archived:{plans:[archived],next_before:null}}),{})
 await p.hooks.show()
 assert.equal(p.legacyMode.value,false)
 assert.equal(p.savedState.plans[0].meals[0].dishes[0].name,'已保存的晚餐')
 assert.equal(p.calls[0].path,'/api/family/family/daily-meal-plans?limit=20')
 await p.select(p.savedState.plans[0])
 assert.equal(p.view.value,'detail')
 assert.deepEqual(p.savedState.plan,archived)
 assert.equal(p.calls[1].path,'/api/family/family/daily-meal-plans/2026-11-19/archive')
 p.savedDish.value=p.savedState.plan.meals[0].dishes[0]
 p.back();assert.equal(p.savedDish.value,null);assert.equal(p.view.value,'detail')
 p.back();assert.equal(p.view.value,'list');assert.equal(p.savedState.plans.length,1)
 assert.equal(p.calls.every(call=>!call.method||call.method==='GET'),true)
})

test('a dated archive link opens its exact saved date',async()=>{
 const p=mount(async()=>({data:archived}),{date:'2026-11-19'})
 await p.hooks.show()
 assert.equal(p.view.value,'detail');assert.deepEqual(p.savedState.plan,archived)
 assert.equal(p.calls.length,1)
})

test('returning from a dated archive link loads the saved list and resets the detail date',async()=>{
 const p=mount(async input=>({data:input.path.endsWith('/archive')?archived:{plans:[archived],next_before:null}}),{date:'2026-11-19'})
 await p.hooks.show();await p.back()
 assert.equal(p.view.value,'list');assert.deepEqual(p.savedState.plans,[archived])
 assert.match(p.calls[1].path,/daily-meal-plans\?limit=20$/)
 p.hooks.hide();await p.hooks.show()
 assert.match(p.calls.at(-1).path,/daily-meal-plans\?limit=20$/)
})

test('native back closes a saved dish and detail before allowing page navigation',async()=>{
 const p=mount(async input=>({data:input.path.endsWith('/archive')?archived:{plans:[archived],next_before:null}}),{})
 await p.hooks.show();await p.select(p.savedState.plans[0]);p.savedDish.value=archived.meals[0].dishes[0]
 assert.equal(p.hooks.back({from:'backbutton'}),true);assert.equal(p.savedDish.value,null);assert.equal(p.view.value,'detail')
 assert.equal(p.hooks.back({from:'backbutton'}),true);assert.equal(p.view.value,'list')
 assert.equal(p.hooks.back({from:'backbutton'}),false)
 assert.equal(p.hooks.back({from:'navigateBack'}),false)
 assert.equal(p.navigation.length,0)
})

test('archive lists use the same translated title as details without changing the source',()=>{
 const dish={name:'Steamed broccoli',display_zh:{name:'清蒸西兰花'}}
 const before=structuredClone(dish)
 const card=archiveCard({...archived,meals:[{meal_type:'dinner',dishes:[dish]}]})
 assert.equal(card.meals.find(meal=>meal.type==='dinner').summary,dishTitle(dish))
 assert.equal(card.meals.find(meal=>meal.type==='dinner').summary,'清蒸西兰花')
 assert.deepEqual(dish,before)
})

test('leaving daily archives discards a late list or detail read',async()=>{
 let release
 const p=mount(()=>new Promise(resolve=>release=resolve),{})
 const pending=p.hooks.show();p.hooks.hide()
 release({data:{plans:[archived],next_before:null}});await pending
 assert.deepEqual(p.savedState.plans,[])
})

test('archive request failures remain visible instead of becoming an empty saved list',async()=>{
 const p=mount(async()=>{throw Error('暂时无法读取保存餐单')},{})
 await p.hooks.show();assert.match(p.savedState.error,/无法读取/)
})

test('daily archives paginate by date and reject another family snapshot',async()=>{
 const state=mealArchiveState(),calls=[]
 const older={...archived,id:'older',plan_date:'2026-11-18'}
 const client=createMealArchiveClient({state,session:()=>({householdId:'family'}),context:()=> 'A',send:async options=>{
  calls.push(options)
  return {data:calls.length===1?{plans:[archived],next_before:'2026-11-19'}:calls.length===2?{plans:[older],next_before:null}:{...archived,family_id:'another-family'}}
 }})
 await client.list();await client.list(true)
 assert.deepEqual(state.plans.map(plan=>plan.plan_date),['2026-11-19','2026-11-18'])
 assert.match(calls[1].path,/before=2026-11-19/)
 await client.detail('2026-11-19')
 assert.equal(state.plan,null);assert.match(state.error,/家庭/)
})

test('daily archives count the recorded diners across meals without duplicating members',()=>{
 const card=archiveCard({...archived,meals:[...archived.meals,{...archived.meals[0],meal_type:'lunch',members:[{id:a},{id:b}]}]})
 assert.equal(card.summary,'2位成员 · 2餐')
})

test('detail opens above the list, returns to the same page, and prevents duplicate reads while busy', async () => {
  const p = mount(); await p.hooks.show()
  p.state.offset = 20; p.replace.value = true; p.reason.value = '旧输入'
  const first = p.select(p.state.plans[0]); const second = p.select(p.state.plans[0])
  await Promise.all([first, second])
  assert.equal(p.view.value, 'detail'); assert.equal(p.replace.value, false); assert.equal(p.reason.value, '')
  assert.equal(p.calls.filter(row => row.path.endsWith('/meal-plans/' + planId)).length, 1)
  p.back(); assert.equal(p.view.value, 'list'); assert.equal(p.selectedPlanId.value, '')
  assert.equal(p.state.offset, 20); assert.equal(p.navigation.length, 0)
})

test('member selection survives foreground refresh and old confirmations do not carry over', async () => {
  const p = mount(); await p.hooks.show(); p.replace.value = true
  await p.changeMember(b); assert.equal(p.memberId.value, b); assert.equal(p.replace.value, false)
  p.hooks.hide(); await p.hooks.show()
  assert.equal(p.state.memberId, b); assert.equal(p.state.plans[0].member_id, b)
})

test('an external plan link reads that exact plan even when it is outside the first list page', async () => {
  const p = mount(async options => options.path.includes('/meal-plans?') ? { data: { plans: [], next_offset: null } } : null)
  p.hooks.load({ memberId: a, planId }); await p.hooks.show()
  assert.equal(p.view.value, 'detail'); assert.equal(p.state.plan.plan_id, planId)
})

test('retrying an unavailable explicit member never silently selects another member', async () => {
  const p = mount(async options => options.path.endsWith('/members')
    ? { data: [{ id: a, display_name: '其他成员', scopes: ['diet_edit'] }] } : null)
  p.hooks.load({ memberId: b }); await p.hooks.show(); await p.hooks.show()
  assert.equal(p.memberId.value, b); assert.equal(p.state.memberId, '')
  assert.match(p.state.error, /无餐单权限/)
  assert.equal(p.calls.some(row => row.path.includes('/meal-plans?')), false)
})

test('hiding during initial loading cannot refill the page with private records', async () => {
  let release
  const p = mount(options => options.path.endsWith('/members') ? new Promise(resolve => release = resolve) : null)
  const waiting = p.hooks.show(); p.hooks.hide()
  release({ data: [{ id: a, scopes: ['diet_edit'] }] }); await waiting
  assert.equal(p.state.members.length, 0); assert.equal(p.state.plans.length, 0)
  assert.equal(p.calls.length, 1)
})

test('an uncertain adoption is restored with its original request and opens the verified detail', async () => {
  let attempts = 0
  const p = mount(async options => {
    if (options.path.endsWith('/adopt')) {
      if (++attempts === 1) throw Object.assign(new Error('响应丢失'), { code: 'NETWORK_ERROR' })
      return { data: { adoption_id: 'adoption', plan_id: planId, status: 'adopted', current: true } }
    }
    return null
  })
  await p.hooks.show(); await p.select(p.state.plans[0]); await p.client.adopt()
  assert.ok(p.state.pending)
  p.hooks.hide(); await p.hooks.show(); assert.ok(p.state.pending)
  await p.retry()
  assert.equal(p.state.pending, null); assert.equal(p.view.value, 'detail'); assert.equal(p.reviewExpanded.value, true)
  const writes = p.calls.filter(row => row.path.endsWith('/adopt'))
  assert.equal(writes.length, 2); assert.deepEqual(writes[0], writes[1])
})
