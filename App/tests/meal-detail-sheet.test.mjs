import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {ref,watch,nextTick,effectScope,reactive,computed,compile,createSSRApp} from 'vue'
import {renderToString} from 'vue/server-renderer'
import {createMealDetailClient,detailState,formalRoute,detailGesture} from '../src/services/meal-detail-client.js'
const target={kind:'formal',familyId:'family',date:'2026-10-28',mealType:'breakfast',sourceId:'saved',version:2,dailyPlanVersion:4}
const meal={type:'breakfast',members:[],dishes:[{id:'dish',name:'合成菜品',steps:['合成步骤']}]}
const receipt=(t=target)=>({data:{arrangement_id:t.sourceId,version:t.version,meal:{...meal,type:t.mealType}}})
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return{promise,resolve,reject}}

test('a verified reference meal remains readable when purchase matching is unavailable',async()=>{
 const state=detailState(),calls=[]
 const dinner={meal_type:'dinner',source:{kind:'reference',id:'saved'},purchase_ready:false,meal:{dishes:[{name:'合成晚餐',ingredients:['西兰花','牛肉']} ]},members:[]}
 const client=createMealDetailClient({state,context:()=> 'A',send:async input=>{
  calls.push(input)
  return {data:{status:'ready',date:target.date,version:4,meals:[dinner],purchase_options:[]}}
 }})
 await client.open({...target,kind:'reference',mealType:'dinner',purchaseReady:false})
 assert.equal(state.phase,'ready')
 assert.deepEqual(state.meal.dishes[0].ingredients,['西兰花','牛肉'])
 assert.equal(state.target.purchaseReady,false)
 assert.equal(calls.length,1)
 assert.match(calls[0].path,/daily-meal-plans/)
 client.dispose()
})

test('an expired formal source reads its versioned daily snapshot and stays unavailable for purchase',async()=>{
 const state=detailState(),calls=[]
 const item={meal_type:target.mealType,source:{kind:'formal',id:target.sourceId,version:target.version},purchase_ready:false,meal,members:[]}
 const client=createMealDetailClient({state,context:()=> 'A',send:async input=>{
  calls.push(input)
  assert.match(input.path,/daily-meal-plans\//)
  return {data:{date:target.date,status:'ready',version:target.dailyPlanVersion,meals:[item],purchase_options:[]}}
 }})
 await client.open({...target,purchaseReady:false,seed:{dishes:[{name:'旧预览'}]}})
 assert.equal(state.phase,'ready');assert.deepEqual(state.meal.dishes,meal.dishes)
 assert.equal(state.target.purchaseReady,false);assert.equal(state.target.purchaseOption,null)
 assert.equal(calls.length,1);assert.equal(calls[0].method,undefined)
 client.dispose()
})

for(const mismatch of ['dailyVersion','sourceVersion','sourceId','mealType','date'])test(`expired formal snapshots reject ${mismatch} changes`,async()=>{
 const state=detailState()
 const item={meal_type:target.mealType,source:{kind:'formal',id:target.sourceId,version:target.version},purchase_ready:false,meal}
 const data={date:target.date,status:'ready',version:target.dailyPlanVersion,meals:[item]}
 if(mismatch==='dailyVersion')data.version++
 if(mismatch==='sourceVersion')item.source.version++
 if(mismatch==='sourceId')item.source.id='another'
 if(mismatch==='mealType')item.meal_type='dinner'
 if(mismatch==='date')data.date='2026-10-29'
 const client=createMealDetailClient({state,context:()=> 'A',send:async()=>({data})})
 await client.open({...target,purchaseReady:false,seed:meal})
 assert.equal(state.phase,'error');assert.equal(state.meal,null)
 client.dispose()
})

test('denied daily snapshots cannot fall back to a private formal preview',async()=>{
 const state=detailState()
 const client=createMealDetailClient({state,context:()=> 'A',send:async()=>{throw Object.assign(Error('授权已变化'),{code:403})}})
 await client.open({...target,purchaseReady:false,seed:meal})
 assert.equal(state.phase,'error');assert.equal(state.meal,null);assert.match(state.error,/授权/)
 client.dispose()
})

function routeHarness({profileFails=false}={}){
 const source=readFileSync(new URL('../src/pages/meals/detail.vue',import.meta.url),'utf8').split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm,'')
 const scope=effectScope(),timers=new Map(),hooks={},calls=[]
 let owner='A',timerId=0
 const deps={ref,watch,getCurrentInstance:()=>({}),storageContext:()=>owner,takeMealPageTarget:()=>null,
  onLoad:fn=>fn(),onShow:fn=>{hooks.show=fn},onUnload:fn=>{hooks.unload=fn},onBackPress:fn=>{hooks.back=fn},
  openerChannel:()=>({on:(_name,fn)=>{hooks.receive=fn}}),getSession:()=>({householdId:'family'}),
  request:async()=>{if(profileFails)throw Error('profile unavailable');return{data:{members:[]}}},
  getCurrentPages:()=>[{},{}],uni:{navigateBack:()=>calls.push('back')},
  setTimeout:fn=>{timers.set(++timerId,fn);return timerId},clearTimeout:id=>timers.delete(id)}
 const page=scope.run(()=>new Function('deps',`const {${Object.keys(deps)}}=deps;${source};return {detail,pendingTarget,opened,error,retry}`)(deps))
 return{page,calls,timers,receive:value=>hooks.receive({owner:'A',target,...value}),
  mount:component=>{page.detail.value=component},changeOwner:()=>{owner='B'},show:()=>hooks.show(),
  back:event=>hooks.back(event),timeout:()=>{for(const callback of [...timers.values()])callback()},
  dispose:()=>{hooks.unload();scope.stop()}}
}

test('native back first delegates to the open purchase sheet',()=>{
 const h=routeHarness();try{
  h.mount({handleBack:()=>true});assert.equal(h.back(),true)
  assert.equal(h.back({from:'navigateBack'}),false)
  h.mount({handleBack:()=>false});assert.equal(h.back(),false)
 }finally{h.dispose()}
})

test('native detail ref arriving after the payload opens once, without waiting for another user action',async()=>{
 const h=routeHarness(),opens=[]
 try{
  h.receive();await nextTick();assert.equal(h.page.opened.value,false)
  h.mount({open:value=>opens.push(value)});await nextTick();await nextTick()
  assert.equal(opens.length,1);assert.deepEqual(opens[0],target);assert.equal(h.page.opened.value,true)
  assert.equal(h.timers.size,0)
  await nextTick();assert.equal(opens.length,1)
 }finally{h.dispose()}
})

test('payload arriving after the native detail ref retains dish and purchase entry modes',async()=>{
 for(const extra of [{initialView:'dish',dishIndex:1},{initialView:'purchase'}]){
  const h=routeHarness(),opens=[],chosen={...target,...extra}
  try{
   h.mount({open:value=>opens.push(value)});await nextTick();assert.equal(opens.length,0)
   h.receive({target:chosen});await nextTick()
   assert.equal(opens.length,1);assert.deepEqual(opens[0],chosen);assert.equal(h.page.opened.value,true)
  }finally{h.dispose()}
 }
})

test('a mount timeout is visible and a later mount still opens the pending meal',async()=>{
 const h=routeHarness(),opens=[]
 try{
  h.receive();h.timeout();assert.match(h.page.error.value,/未能打开/)
  h.page.retry();assert.equal(h.page.error.value,'')
  h.mount({open:value=>opens.push(value)});await nextTick()
  assert.equal(opens.length,1);assert.equal(h.page.opened.value,true);assert.equal(h.page.error.value,'')
 }finally{h.dispose()}
})

test('an opening failure is retryable and does not leave the route blank',async()=>{
 const h=routeHarness();let opens=0
 try{
  h.mount({open:()=>{if(++opens===1)throw Error('synthetic opening failure')}})
  h.receive();await nextTick()
  assert.equal(h.page.opened.value,false);assert.match(h.page.error.value,/synthetic/)
  h.page.retry();await nextTick()
  assert.equal(opens,2);assert.equal(h.page.opened.value,true);assert.equal(h.page.error.value,'')
 }finally{h.dispose()}
})

test('a failed member refresh cannot prevent the saved meal from opening',async()=>{
 const h=routeHarness({profileFails:true}),opens=[]
 try{
  h.receive();h.mount({open:value=>opens.push(value)});await nextTick();await nextTick()
  assert.equal(opens.length,1);assert.equal(h.page.opened.value,true);assert.equal(h.page.error.value,'')
 }finally{h.dispose()}
})

test('late native mounts cannot open a meal after leaving or changing account',async()=>{
 for(const action of ['leave','account']){
  const h=routeHarness(),opens=[]
  try{
   h.receive();await nextTick()
   if(action==='leave')h.dispose();else{h.changeOwner();h.show()}
   h.mount({open:value=>opens.push(value)});await nextTick();h.timeout()
   assert.equal(opens.length,0);assert.equal(h.timers.size,0)
  }finally{h.dispose()}
 }
})
test('sheet opens synchronously while a read is pending and performs no writes',async()=>{
 const state=detailState(),wait=deferred(),calls=[]
 const client=createMealDetailClient({state,context:()=> 'A',send:input=>{calls.push(input);return wait.promise}})
 const pending=client.open(target);assert.equal(state.open,true);assert.equal(state.phase,'loading');assert.equal(state.meal,null)
 wait.resolve(receipt());await pending;assert.equal(state.phase,'ready');assert.equal(state.meal.dishes[0].name,'合成菜品')
 assert.equal(calls.length,1);assert.equal(calls[0].method,undefined);assert.match(calls[0].path,/daily_plan_version=4$/)
})
test('late breakfast response cannot replace a subsequently opened dinner',async()=>{
 const first=deferred(),second=deferred(),state=detailState(),t={...target,mealType:'dinner'}
 let count=0;const client=createMealDetailClient({state,context:()=> 'A',send:()=>++count===1?first.promise:second.promise})
 const a=client.open(target),b=client.open(t);second.resolve(receipt(t));await b;first.resolve(receipt());await a
 assert.equal(state.target.mealType,'dinner');assert.equal(state.meal.type,'dinner')
})
test('closing or changing identity discards an in-flight detail read',async()=>{
 for(const action of ['close','identity']){const state=detailState(),wait=deferred();let scope='A'
 const client=createMealDetailClient({state,context:()=>scope,send:()=>wait.promise});const pending=client.open(target)
 if(action==='close')client.close();else scope='B'
 wait.resolve(receipt());await pending;assert.equal(state.meal,null)
 if(action==='close')assert.equal(state.open,false)
 }
})
test('wrong saved version or revoked permission cannot enable a detail action',async()=>{
 for(const send of [async()=>receipt({...target,version:9}),async()=>{throw Object.assign(new Error('授权已变化'),{code:403})}]){
  const state=detailState(),client=createMealDetailClient({state,context:()=> 'A',send});await client.open(target)
  assert.equal(state.phase,'error');assert.ok(state.error)
 }
})
test('reference read retains unknown nutrition and validates the exact daily source',async()=>{
 const state=detailState(),ref={...target,kind:'reference',sourceId:'preview',version:undefined}
 const item={meal_type:'breakfast',source:{kind:'reference',id:'preview'},members:[],meal:{dishes:[{name:'参考菜',ingredients:['食材适量'],steps:['原文步骤'],nutrition_quote:'原食谱说明'}]}}
 let version=4
 const client=createMealDetailClient({state,context:()=> 'A',send:async()=>({data:{status:'ready',date:target.date,version,meals:[item],purchase_options:[]}})})
 await client.open(ref);assert.equal(state.phase,'ready');assert.equal(state.meal.nutrition,undefined);assert.deepEqual(state.meal.dishes[0].ingredients,['食材适量'])
 version=5;await client.open(ref);assert.equal(state.phase,'error')
})

test('a reference meal shows its saved dishes immediately but remains unverified until the read finishes',async()=>{
 const state=detailState(),wait=deferred(),calls=[]
 const chosen={...target,kind:'reference',sourceId:'preview',seed:meal}
 const client=createMealDetailClient({state,context:()=> 'A',send:input=>{calls.push(input);return wait.promise}})
 const reading=client.open(chosen)
 assert.equal(state.open,true);assert.equal(state.phase,'loading');assert.equal(state.meal.dishes[0].name,'合成菜品')
 assert.equal(calls.length,1);assert.equal(calls[0].method,undefined)
 wait.resolve({data:{status:'ready',date:chosen.date,version:4,meals:[{meal_type:'breakfast',source:{kind:'reference',id:'preview'},meal}],purchase_options:[]}})
 await reading;assert.equal(state.phase,'ready')
})

test('reopening a reference uses only its exact scoped version cache while still checking the server',async()=>{
 const state=detailState(),calls=[];let scope='A',wait
 const chosen={...target,kind:'reference',sourceId:'preview'}
 const client=createMealDetailClient({state,context:()=>scope,send:input=>{calls.push(input);wait=deferred();return wait.promise}})
 const result=t=>({data:{status:'ready',date:t.date,version:t.dailyPlanVersion,meals:[{meal_type:t.mealType,source:{kind:'reference',id:t.sourceId},meal}],purchase_options:[]}})
 let reading=client.open(chosen);assert.equal(state.meal,null);wait.resolve(result(chosen));await reading
 client.close();reading=client.open(chosen)
 assert.equal(state.meal.dishes[0].name,'合成菜品');assert.equal(state.phase,'loading');assert.equal(calls.length,2)
 wait.resolve(result(chosen));await reading
 for(const change of ['version','source','account']){
  client.close();const next={...chosen}
  if(change==='version')next.dailyPlanVersion++
  if(change==='source')next.sourceId='other-preview'
  if(change==='account')scope='B'
  reading=client.open(next);assert.equal(state.meal,null,change)
  wait.resolve(result(next));await reading
 }
})

test('a rejected reference read removes its preview and retry cannot redisplay the rejected seed',async()=>{
 for(const code of [403,410,'changed-version']){
  const state=detailState();let wait
  const chosen={...target,kind:'reference',sourceId:'preview',seed:meal}
  const client=createMealDetailClient({state,context:()=> 'A',send:()=>{wait=deferred();return wait.promise}})
  const reading=client.open(chosen);assert.ok(state.meal)
  if(code==='changed-version')wait.resolve({data:{status:'ready',date:chosen.date,version:99,meals:[]}})
  else wait.reject(Object.assign(new Error('来源失效'),{code}))
  await reading;assert.equal(state.phase,'error');assert.equal(state.meal,null)
  const retry=client.retry();assert.equal(state.phase,'loading');assert.equal(state.meal,null)
  wait.reject(new Error('仍未通过核对'));await retry
 }
})
test('summary purchase preserves its meal set and all version bindings',()=>{
 assert.deepEqual(formalRoute({...target,purchaseMeals:['breakfast','dinner']}),{date:target.date,meal:'daily',meals:['breakfast','dinner'],arrangement:'saved',version:2,daily_plan_version:4})
})
test('reading down a long recipe never triggers sheet dismissal away from its top',()=>{
 assert.equal(detailGesture({delta:-60,expanded:false}),'expand')
 assert.equal(detailGesture({delta:120,expanded:true,scrollTop:180}),'none')
 assert.equal(detailGesture({delta:90,expanded:true,scrollTop:0}),'collapse')
 assert.equal(detailGesture({delta:90,expanded:false,scrollTop:0}),'close')
})

function purchaseFooter({phase='loading',purchaseReady=true,view='meal',kind='formal',items=[]}={}){
 const source=readFileSync(new URL('../src/components/MealDetailSheet.vue',import.meta.url),'utf8')
 const state=reactive({phase,view}),target=ref({purchaseReady,kind,dailyPlanVersion:4,date:'2026-11-19'})
 const reference=computed(()=>target.value.kind==='reference'),referencePurchase=ref({items}),busy=ref(false)
 const expression=source.match(/const canPurchase=computed\(\(\)=>([^\n]+)\)/)[1]
 const canPurchase=new Function('computed','state','target','reference','referencePurchase','return computed(()=>'+expression+')')(computed,state,target,reference,referencePurchase)
 const dish=ref({dish_key:'synthetic-dish'}),purchaseDish=ref(null),purchaseMounted=ref(false),purchaseOpen=ref(false)
 const showPurchase=new Function('busy','canPurchase','state','dish','purchaseDish','purchaseMounted','purchaseOpen',source.match(/function showPurchase\(\)[^\n]+/)[0]+';return showPurchase')(busy,canPurchase,state,dish,purchaseDish,purchaseMounted,purchaseOpen)
 const template=source.match(/<view v-if="state.view==='dish'[^\n]+class="detail-footer"[\s\S]*?<\/view>/)[0]
 const render=compile(template)
 const html=()=>renderToString(createSSRApp({render,setup:()=>({state,target,busy,canPurchase,showPurchase,startRecord:()=>{},localDate:()=> '2026-11-19'})}))
 return {state,target,busy,canPurchase,purchaseDish,purchaseMounted,purchaseOpen,showPurchase,html}
}

test('purchase footer stays present and disabled while loading, then enables after verification',async()=>{
 const h=purchaseFooter()
 assert.match(await h.html(),/detail-buy[^>]*disabled/);assert.match(await h.html(),/正在准备…/)
 h.showPurchase();assert.equal(h.purchaseMounted.value,false)
 h.state.phase='ready'
 assert.doesNotMatch(await h.html(),/disabled/);assert.match(await h.html(),/>购买<\/button>/)
 h.showPurchase();assert.equal(h.purchaseOpen.value,true);assert.equal(h.purchaseDish.value,null)
})

for(const scenario of [{phase:'error'},{phase:'ready',purchaseReady:false},{phase:'ready',kind:'reference',purchaseReady:undefined}])test('blocked purchase keeps a disabled footer: '+JSON.stringify(scenario),async()=>{
 const h=purchaseFooter(scenario)
 if(scenario.kind==='reference')h.target.value.purchaseReady=undefined
 const html=await h.html();assert.match(html,/detail-buy[^>]*disabled/);assert.match(html,/暂不可购买/)
 h.showPurchase();assert.equal(h.purchaseMounted.value,false);assert.equal(h.purchaseOpen.value,false)
})

test('busy handlers cannot open procurement and dish purchase retains only its selected dish',async()=>{
 const h=purchaseFooter({phase:'ready',view:'dish'})
 h.busy.value=true;assert.match(await h.html(),/detail-buy[^>]*disabled/)
 h.showPurchase();assert.equal(h.purchaseMounted.value,false)
 h.busy.value=false;h.showPurchase();assert.equal(h.purchaseOpen.value,true)
 assert.equal(h.purchaseDish.value.dish_key,'synthetic-dish')
})

test('member selection does not render the underlying purchase footer',async()=>{
 const h=purchaseFooter({phase:'ready',view:'members'})
 assert.doesNotMatch(await h.html(),/detail-footer|detail-buy/)
})
