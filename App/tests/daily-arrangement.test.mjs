import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createDailyArrangementClient, dailyArrangementState, validateDailyArrangement } from '../src/services/daily-arrangement-client.js'

const day='2026-10-17'
function ready() {
  return {status:'ready',id:'saved-1',version:1,date:day,saved:true,validation:{status:'passed'},procurement:{checked:true},
    analysis:{source:'agent',request_id:'request-1',run_id:'run-1',text:'合成测试：以下说明与三餐同源。'},
    meals:['breakfast','lunch','dinner'].map(type=>({type,detail_ref:type,members:[{id:'member-1',name:'合成成员'}],
      dishes:[{id:'recipe-1',name:'合成菜',recipeVersion:'version-1',ingredients:[{name:'合成食材'}],steps:['合成步骤']}],
      memberNotes:[{memberId:'member-1',dishes:[{grams:100}]}],nutrition:{protein:10},nutritionSource:{source:'synthetic-test-only'},
      purchase:{package_sn:'package-'+type,package_version:1,items:[]}}))}
}
function setup(handler) {
  const state=dailyArrangementState(),data=new Map(),calls=[]
  let scope='A',familyId='family-A',count=0
  const client=createDailyArrangementClient({state,context:()=>({scope,familyId}),storage:{getStorageSync:key=>data.get(scope+key),setStorageSync:(key,value)=>data.set(scope+key,structuredClone(value))},
    send:async input=>{calls.push(structuredClone(input));return {data:await handler(input,calls)}},newId:()=>'request-'+ ++count,wait:async()=>{},pollLimit:3})
  return {client,state,calls,data,switch(){scope='B';familyId='family-B'}}
}

for(const code of ['daily_member_sources_unavailable','daily_profile_source_unavailable','daily_rules_unavailable','daily_dependencies_not_ready'])test(`setup error ${code} stops even when the old API labels its 503 retryable`,async()=>{
 const f=setup(()=>{throw Object.assign(new Error('依赖尚未就绪'),{code:503,businessCode:code,retryable:true})})
 await f.client.load(day)
 assert.equal(f.calls.length,1);assert.equal(f.state.errorCode,code);assert.equal(f.state.retryable,false);assert.equal(f.state.phase,'error')
})

test('a setup failure during creation is not read back or replayed as an uncertain write',async()=>{
 const f=setup(input=>{if(!input.method)return {status:'absent',date:day};throw Object.assign(new Error('规则未就绪'),{code:503,businessCode:'daily_rules_unavailable',retryable:true})})
 await f.client.load(day);assert.equal(f.calls.length,2);assert.equal(f.state.retryable,false);assert.equal(f.state.errorCode,'daily_rules_unavailable')
})

test('retrying a failed task checks configuration before sending resume',async()=>{
 const state=dailyArrangementState(),calls=[]
 const client=createDailyArrangementClient({state,send:async input=>{calls.push(input);return {data:{status:'failed',date:day,id:'failed'}}},context:()=>({scope:'A',familyId:'family'}),storage:{getStorageSync(){},setStorageSync(){}},newId:()=> 'id',beforeStart:()=>{throw Object.assign(new Error('模型尚未配置'),{businessCode:'daily_dependencies_not_ready',retryable:false})}})
 await client.load(day,true);assert.equal(calls.length,1);assert.equal(state.retryable,false);assert.equal(state.errorCode,'daily_dependencies_not_ready')
})

test('an explicitly retryable business 503 still recovers the saved arrangement',async()=>{
 let reads=0
 const f=setup(()=>{if(++reads===1)throw Object.assign(new Error('临时不可用'),{code:503,businessCode:'upstream_busy',retryable:true});return ready()})
 await f.client.load(day)
 assert.equal(reads,2);assert.equal(f.state.phase,'ready');assert.equal(f.state.errorCode,'');assert.equal(f.state.retryable,true)
})

test('an unclassified gateway 503 remains recoverable',async()=>{
 let reads=0
 const f=setup(()=>{if(++reads===1)throw Object.assign(new Error('gateway'),{code:503,retryable:false});return ready()})
 await f.client.load(day);assert.equal(reads,2);assert.equal(f.state.phase,'ready')
})
test('ready requires three complete saved meals and a genuine Agent request/run reference',()=>{
  assert.equal(validateDailyArrangement(ready(),day).id,'saved-1')
  for(const mutate of [v=>v.meals.pop(),v=>v.saved=false,v=>v.validation.status='pending',v=>v.procurement.checked=false,v=>v.analysis.source='demo',v=>v.analysis.run_id='',v=>v.meals[0].dishes[0].steps=[],v=>v.meals[0].memberNotes=[],v=>delete v.meals[0].purchase,v=>v.meals[0].purchase.package_version=0]){
    const value=ready();mutate(value);assert.throws(()=>validateDailyArrangement(value,day))
  }
})

test('a saved matched menu can be viewed before a commerce member publishes its purchase package',()=>{
  const value=ready()
  for(const meal of value.meals) meal.purchase={status:'matched',catalog_version:'catalog-1',
    ingredient_requirements:[{ingredient_id:'tomato',required_value:'300',required_unit:'g'}],
    items:[{quantity:1,sku:{sku_id:'sku-1',price_cent:800}}]}
  assert.equal(validateDailyArrangement(value,day).meals.length,3)
  value.meals[0].purchase.items[0].sku.price_cent=null
  assert.throws(()=>validateDailyArrangement(value,day))
})

test('stale profile sources create the next saved version and reopening does not regenerate it',async()=>{
  let starts=0
  const value=ready();value.version=2
  const f=setup(input=>{
    if(input.method==='POST'){starts++;return {status:'generating',id:value.id,date:day}}
    return starts?value:{status:'stale',date:day,id:value.id}
  })
  await f.client.load(day)
  assert.equal(f.state.arrangement.version,2)
  await f.client.load(day)
  assert.equal(starts,1)
})

test('automatic generation does not require a commerce member and the saved meal contains its purchase panel',()=>{
  const chat=readFileSync(new URL('../src/components/CloudNutritionChat.vue',import.meta.url),'utf8')
  const detail=readFileSync(new URL('../src/components/CloudMealDetail.vue',import.meta.url),'utf8')
  assert.doesNotMatch(chat,/beforeStart:\s*\(\)\s*=>\s*commerce\.connect/)
  assert.match(detail,/<CloudMealPurchase\b/)
  assert.doesNotMatch(detail,/查看本餐采购清单|function purchase\(/)
})
test('reopening a saved day only reads and does not submit generation',async()=>{
  const f=setup(()=>ready());await f.client.load(day);await f.client.load(day)
  assert.equal(f.state.phase,'ready');assert.equal(f.calls.length,2);assert.ok(f.calls.every(call=>!call.method))
})
test('analysis text alone never reveals an incomplete card',async()=>{
  const partial=ready();partial.meals.pop()
  const f=setup(()=>partial);await f.client.load(day)
  assert.equal(f.state.phase,'error');assert.equal(f.state.arrangement,null)
})

test('an incomplete replacement cannot keep the old card marked ready',async()=>{
 let partial=false
 const f=setup(()=>{const value=ready();if(partial){value.version=2;value.meals.pop()}return value})
 await f.client.load(day);partial=true;await f.client.load(day)
 assert.equal(f.state.arrangement,null);assert.equal(f.state.phase,'error')
})

test('an incomplete create receipt is polled until the complete persisted arrangement is read',async()=>{
 let reads=0
 const f=setup(input=>{if(input.method==='POST'){const partial=ready();partial.meals.pop();return partial}return ++reads===1?{status:'absent',date:day}:ready()})
 await f.client.load(day);assert.equal(f.state.phase,'ready');assert.equal(f.state.arrangement.meals.length,3);assert.equal(reads,2)
})
test('a lost create response queries the original daily result without submitting another generation',async()=>{
  let reads=0,starts=0
  const f=setup(input=>{
    if(input.method==='POST'){starts++;throw Object.assign(new Error('timeout'),{code:'NETWORK_ERROR'})}
    return ++reads===1?{status:'absent',date:day}:ready()
  })
  await f.client.load(day);assert.equal(starts,1);assert.equal(f.state.phase,'ready')
})
test('an unconfirmed save replays exactly the original key, including after a page reload',async()=>{
  const payloads=[]
  const f=setup(input=>{
    if(input.method==='POST'){payloads.push(input.data);if(payloads.length===1)throw Object.assign(new Error('timeout'),{code:'NETWORK_ERROR'});return ready()}
    return {status:'absent',date:day}
  })
  await f.client.load(day);assert.equal(payloads.length,2);assert.deepEqual(payloads[0],payloads[1]);assert.equal(f.state.phase,'ready')
})
test('concurrent first opens share one generation',async()=>{
  let release;const gate=new Promise(resolve=>release=resolve);let starts=0
  const f=setup(async input=>{if(input.method==='POST'){starts++;await gate;return ready()}return {status:'absent',date:day}})
  const first=f.client.load(day),second=f.client.load(day);release();await Promise.all([first,second]);assert.equal(starts,1)
})
test('an account switch cannot resume a former family task in the new family',async()=>{
  let release;const f=setup(()=>new Promise(resolve=>release=resolve))
  const pending=f.client.load(day);f.switch();release({status:'generating',date:day});await pending
  assert.equal(f.calls.length,1);assert.equal(f.state.arrangement,null)
})
test('background generation is polled with GET only until final persistence',async()=>{
  let reads=0
  const f=setup(()=>++reads<3?{status:'generating',date:day}:ready())
  await f.client.load(day);assert.equal(reads,3);assert.equal(f.state.phase,'ready');assert.ok(f.calls.every(call=>!call.method))
})

test('a failed revision keeps the published arrangement readable',async()=>{
  const f=setup(()=>({...ready(),update:{status:'failed',version:2,message:'调整失败，原安排保留'}}))
  await f.client.load(day)
  assert.equal(f.state.arrangement.version,1);assert.equal(f.state.phase,'ready');assert.match(f.state.error,/保留/)
})

for (const code of [401,403,404,410]) test(`daily authorization loss ${code} removes the previously published card`,async()=>{
  let denied=false
  const f=setup(()=>{if(denied)throw Object.assign(new Error('授权已失效'),{code});return ready()})
  await f.client.load(day);denied=true;await f.client.load(day)
  assert.equal(f.state.arrangement,null);assert.notEqual(f.state.phase,'ready')
  assert.equal(f.calls.length,2)
})

test('an unknown member change followed by a conflict reads the current version and releases the old intent',async()=>{
  let stage='ready',writes=0
  const f=setup(input=>{
    if(input.method==='POST'){writes++;throw Object.assign(new Error('原调整已变化'),{code:stage==='timeout'?'NETWORK_ERROR':409})}
    const value=ready();if(stage==='conflict')value.version=2;return value
  })
  await f.client.load(day);stage='timeout';await f.client.changeMembers('lunch',['member-2'])
  stage='conflict';await f.client.load(day)
  assert.equal(f.state.arrangement.version,2);assert.match(f.state.error,/重新|核对|变化/)
  const previousWrites=writes;await f.client.load(day);assert.equal(writes,previousWrites)
})

test('a direct member conflict replaces the old version before another confirmation',async()=>{
  let changed=false
  const f=setup(input=>{
    if(input.method==='POST'){changed=true;throw Object.assign(new Error('版本冲突'),{code:409})}
    const value=ready();if(changed)value.version=2;return value
  })
  await f.client.load(day);await f.client.changeMembers('lunch',['member-2'])
  assert.equal(f.state.arrangement.version,2);assert.match(f.state.error,/重新|核对|变化/)
})

test('a pending revision retains the original version until replacement commits',async()=>{
  let reads=0
  const f=setup(()=>++reads<3?({...ready(),update:{status:'generating',version:2}}):({...ready(),version:2}))
  await f.client.load(day)
  assert.equal(f.state.arrangement.version,2);assert.ok(f.calls.every(call=>!call.method))
})
test('unavailable service keeps the card hidden and reports a service error',async()=>{
  const f=setup(()=>{throw Object.assign(new Error('营养服务尚未配置'),{code:503})});await f.client.load(day)
  assert.equal(f.state.arrangement,null);assert.match(f.state.error,/服务/);assert.ok(!f.calls.some(call=>call.method==='POST'))
})
test('detail must match the displayed arrangement and version',async()=>{
  const f=setup(input=>input.path.includes('/meals/')?{arrangement_id:'saved-1',version:2,meal:{type:'dinner'}}:ready())
  await f.client.load(day);await assert.rejects(f.client.detail('saved-1','dinner',1),/更新/)
})

test('transient initial read retries without creating a second task',async()=>{
  let reads=0
  const f=setup(()=>{if(++reads===1)throw Object.assign(new Error('timeout'),{code:'NETWORK_ERROR'});return ready()})
  await f.client.load(day);assert.equal(f.state.phase,'ready');assert.equal(f.calls.length,2)
  assert.ok(f.calls.every(call=>!call.method))
})

test('explicit retry restarts only a failed daily request through its existing endpoint',async()=>{
  const f=setup(input=>input.path.endsWith('/resume?retry_failed=true')?ready():{status:'failed',id:'saved-1',date:day,message:'合成生成失败'})
  await f.client.load(day);assert.equal(f.state.phase,'error')
  assert.equal(f.calls.length,1)
  await f.client.load(day,true);assert.equal(f.state.phase,'ready')
  assert.ok(!f.calls.some(call=>call.path.endsWith('/daily-arrangements')&&call.method==='POST'))
})

test('lost member-change response is recovered with the exact original key on reload',async()=>{
  let writes=0;const payloads=[]
  const f=setup(input=>{
    if(input.path.endsWith('/members')){payloads.push(input.data);if(++writes===1)throw Object.assign(new Error('timeout'),{code:'NETWORK_ERROR'});return {status:'generating'}}
    return ready()
  })
  await f.client.load(day);await f.client.changeMembers('dinner',['member-2'])
  assert.match(f.state.error,/timeout/)
  await f.client.load(day)
  assert.equal(f.state.phase,'ready');assert.equal(writes,2);assert.deepEqual(payloads[0],payloads[1])
})

test('saved meal viewing does not depend on a commerce login',()=>{
  const page=readFileSync(new URL('../src/pages/shop/index.vue',import.meta.url),'utf8')
  assert.match(page,/<CloudMealDetail v-else-if="!isMockMode/)
  assert.match(page,/<CommerceAccess v-else/)
  const detail=readFileSync(new URL('../src/components/CloudMealDetail.vue',import.meta.url),'utf8')
  assert.ok(!detail.includes('commerce.session'))
  assert.ok(detail.includes('/meals/'))
})
test('formal UI places the real analysis before the gated card and has no placeholder menus',()=>{
  const ui=readFileSync(new URL('../src/components/CloudNutritionChat.vue',import.meta.url),'utf8')
  assert.ok(ui.indexOf('class="analysis-message"')<ui.indexOf('<DailyArrangementCard'))
  assert.match(ui,/v-if="cardVisible && state.phase==='ready'"/)
  assert.ok(!ui.includes('本餐有待处理的饮食问题'));assert.ok(!ui.includes('测试数据'))
  assert.ok(ui.includes('/pages/chat/camera'));assert.ok(ui.includes('/pages/scan/index'))
})
