import * as planning from '../src/services/meal-planning.js'
import * as exclusivePlanning from '../src/services/exclusive-planning.js'
import * as contexts from '../src/utils/meal-context.js'
import { isMockMode, isCommerceEnabled } from '../src/services/config.js'
import * as health from '../src/utils/health.js'
import * as portions from '../src/utils/scan-portions.js'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { ref, computed, nextTick, watch, effectScope } from 'vue'
import * as profiles from '../src/utils/profile.js'
import * as orders from '../src/utils/orders.js'
import * as actions from '../src/utils/order-actions.js'
import * as mealState from '../src/utils/meal-state.js'
import * as customization from '../src/utils/meal-customization.js'
import * as mealFlow from '../src/utils/meal-flow.js'
import * as exclusive from '../src/utils/exclusive-plans.js'
import * as bundles from '../src/utils/meal-bundles.js'
import * as demo from '../src/utils/demo.js'
import * as memory from '../src/utils/memory.js'
import * as healthCases from '../src/utils/health-cases.js'
import * as checkout from '../src/utils/checkout-state.js'
import { scopedStorage, storageScope,storageContext } from '../src/services/storage.js'
import { setSession, clearSession } from '../src/services/session.js'
import { mockService } from '../src/services/mock.js'
import { failNextMock, mockDelay } from '../src/services/mock-control.js'
import { callApiAdapter } from '../src/services/index.js'
import { request } from '../src/services/request.js'

function setup() {
  const data = new Map(), calls = { modals: [], toasts: [] }
  globalThis.uni = { getStorageSync: key => data.get(key), setStorageSync: (key, value) => data.set(key, structuredClone(value)), getStorageInfoSync: () => ({ keys: [...data.keys()] }),
    showModal: options => { assert.ok([...options.confirmText].length <= 4); calls.modals.push(options) }, showToast: options => calls.toasts.push(options), showActionSheet: options => { calls.actionSheet = options }, navigateTo() {}, reLaunch() {} }
  return { data, calls }
}
const address = { id:'address-1',name:'测试',phone:'13800000000',region:'上海',detail:'测试路1号' }
function planOrder() {
  return orders.createDemoOrder({ items:[{id:'sku-1',name:'番茄',quantity:2,priceCents:100,pack:500,unit:'g'}],totalCents:600,meal:'晚餐',sourcePlanId:'plan',addressSnapshot:address,
    deliveryBatches:[{index:1,date:'2026-10-09',fulfillmentStatus:'shipped'},{index:2,date:'2026-10-10',fulfillmentStatus:'preparing'},{index:3,date:'2026-10-11',fulfillmentStatus:'preparing'}] })
}
function evaluatePage(path, extras, exposed) {
  let show, unload
  const deps = { ref, computed, nextTick, watch, ...profiles, ...orders, ...actions, ...mealState, ...customization, ...mealFlow, ...exclusive, ...bundles, ...demo, ...memory, ...healthCases, ...checkout, ...health, ...portions, ...planning, ...exclusivePlanning, ...contexts, isMockMode, isCommerceEnabled, callApiAdapter,
    scopedStorage, storageScope:storageContext, mockDelay, service:mockService, mockService,
    onHide() {}, onBackPress() {}, onLoad(callback) { callback(extras.options || {}) }, onShow(callback) { show=callback }, onUnload(callback) { unload=callback }, ...extras }
  const source=readFileSync(new URL('../src/pages/'+path,import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
  const scope=effectScope()
  const page=scope.run(()=>new Function('deps',`const {${Object.keys(deps).join(',')}}=deps;\n${source}\nreturn {${exposed}}`)(deps))
  return {...page,show,dispose(){unload?.();scope.stop()}}
}

function onboardingPage(extras = {}) {
  return evaluatePage('onboarding/index.vue', extras, 'profile,step,memberIndex,current,visibleMembers,dinerCount,invited,mode,add,selectMember,toggleDiner,next')
}

test('merged onboarding starts with one unknown self profile and no implicit relatives',()=>{
  setup();setSession({accountId:'onboarding',householdId:'home'})
  const page=onboardingPage()
  assert.equal(page.step.value,0);assert.equal(page.current.value.name,'我');assert.equal(page.profile.value.members.length,1)
  assert.equal(page.current.value.age,null);assert.equal(page.current.value.birthDate,'');assert.equal(page.current.value.height,'')
  assert.equal(page.dinerCount.value,1);assert.equal(page.profile.value.sharedDinerCount,1);page.dispose()
})

test('adding profiles does not select diners and explicit selections support more than four people',()=>{
  setup();setSession({accountId:'onboarding',householdId:'home'});const page=onboardingPage()
  page.mode('家庭使用')
  for(const name of ['妈妈','爸爸','姐姐','弟弟']){page.add();page.current.value.name=name}
  assert.equal(new Set(page.profile.value.members.map(m=>m.id)).size,5)
  assert.equal(page.dinerCount.value,1)
  for(const member of page.profile.value.members.slice(1))page.toggleDiner(member.id)
  assert.equal(page.dinerCount.value,5);assert.equal(page.profile.value.sharedDinerCount,5)
  page.next();assert.equal(page.step.value,1)
  assert.equal(profiles.getProfile().defaultDiners.length,5)
  assert.equal(demo.createPlan(profiles.getProfile()).count,5);page.dispose()
})

test('member tabs and personal mode preserve relatives and restore the family diner selection',()=>{
  setup();setSession({accountId:'onboarding',householdId:'home'});const page=onboardingPage(),self=page.current.value
  page.mode('家庭使用');page.add();const mom=page.current.value;mom.name='妈妈';mom.height='160';page.toggleDiner(mom.id)
  page.selectMember(self.id);self.weight='58';assert.equal(mom.height,'160')
  page.mode('个人使用');assert.deepEqual(page.profile.value.defaultDiners,[self.id]);assert.equal(page.visibleMembers.value.length,1)
  assert.equal(page.profile.value.members.length,2);assert.equal(page.dinerCount.value,1)
  page.mode('家庭使用');assert.deepEqual(page.profile.value.defaultDiners,[self.id,mom.id]);page.selectMember(mom.id)
  assert.equal(page.current.value.height,'160');assert.equal(self.weight,'58');page.dispose()
})

test('at least one diner remains selected and all visible member names are validated',()=>{
  const {calls}=setup();setSession({accountId:'onboarding',householdId:'home'});const page=onboardingPage(),self=page.current.value
  page.mode('家庭使用');page.toggleDiner(self.id);assert.equal(page.dinerCount.value,1);assert.match(calls.toasts[0].title,/至少/)
  page.add();const other=page.current.value;other.name='';page.selectMember(self.id);page.next()
  assert.equal(page.step.value,0);assert.equal(page.current.value.id,other.id)
  assert.equal(scopedStorage.getStorageSync('family-profile-v2'),undefined);page.dispose()
})

test('old four-step drafts migrate to three steps without losing member data or selections',()=>{
  for(const [oldStep,newStep] of [[0,0],[1,0],[2,1],[3,2]]){
    setup();setSession({accountId:'onboarding',householdId:'home'})
    const saved=profiles.normalizeProfile({usageMode:'家庭使用',members:[{...profiles.newMember(0),id:1,name:'我',relation:'本人'},{...profiles.newMember(1),id:2,name:'妈妈',height:'160'}],defaultDiners:[1],sharedDinerCount:4})
    scopedStorage.setStorageSync('frontend-onboarding-progress-v1',{profile:saved,step:oldStep,memberIndex:1})
    const page=onboardingPage();assert.equal(page.step.value,newStep);assert.equal(page.current.value.name,'妈妈')
    assert.equal(page.current.value.height,'160');assert.deepEqual(page.profile.value.defaultDiners,[1]);assert.equal(page.profile.value.sharedDinerCount,1);page.dispose()
  }
})

test('three-step progress restores and completion does not resurrect the draft',async()=>{
  setup();setSession({accountId:'onboarding',householdId:'home'});let redirect
  uni.redirectTo=options=>{redirect=options.url}
  let page=onboardingPage();page.mode('家庭使用');page.add();page.current.value.name='妈妈';page.toggleDiner(page.current.value.id)
  page.next();await nextTick();page.dispose()
  page=onboardingPage();assert.equal(page.step.value,1);assert.equal(page.current.value.name,'妈妈');assert.equal(page.dinerCount.value,2)
  page.next();assert.equal(page.step.value,2);await nextTick();page.next();await nextTick()
  assert.equal(redirect,'/pages/chat/index?from=onboarding');assert.equal(scopedStorage.getStorageSync('frontend-onboarded-v1'),true)
  assert.equal(scopedStorage.getStorageSync('frontend-onboarding-progress-v1'),null);page.dispose()
})

test('invited members start at basic information and keep the household draft and diners',async()=>{
  setup();setSession({accountId:'onboarding',householdId:'home'})
  const saved=profiles.normalizeProfile({usageMode:'家庭使用',members:[{...profiles.newMember(0),id:1,name:'我',relation:'本人'},{...profiles.newMember(1),id:2,name:'妈妈'}],defaultDiners:[1]})
  profiles.saveProfile(saved);const draft={profile:saved,step:2,memberIndex:0,version:2}
  scopedStorage.setStorageSync('frontend-onboarding-progress-v1',draft);let redirect;uni.redirectTo=options=>{redirect=options.url}
  const page=onboardingPage({options:{member:'2'}});assert.equal(page.invited.value,true);assert.equal(page.step.value,0);assert.equal(page.current.value.id,2)
  page.current.value.height='160';page.next();page.next();page.next();await nextTick()
  assert.equal(redirect,'/pages/profile/index');assert.deepEqual(profiles.getProfile().defaultDiners,[1])
  assert.deepEqual(scopedStorage.getStorageSync('frontend-onboarding-progress-v1'),draft);page.dispose()
})

test('accounts and households isolate profiles, orders, addresses, chat history and logout',()=>{
  const {data}=setup()
  data.set('family-profile-v2',{householdName:'旧账号资料',members:[]})
  setSession({accountId:'A',householdId:'home-1'})
  scopedStorage.setStorageSync('chat-2026-10-09',[{text:'A私聊'}]);scopedStorage.setStorageSync('frontend-addresses-v1',[address])
  const created=planOrder();profiles.saveProfile(profiles.normalizeProfile({householdName:'A的家',members:[{id:1,name:'A'}]}))
  setSession({accountId:'B',householdId:'home-1'})
  assert.equal(orders.getOrders().length,0);assert.equal(scopedStorage.getStorageInfoSync().keys.length,0);assert.equal(mockService.selectedAddress(),null)
  setSession({accountId:'A',householdId:'home-2'});assert.equal(orders.getOrders().length,0)
  setSession({accountId:'A',householdId:'home-1'});assert.equal(orders.getOrder(created.id).id,created.id);assert.equal(profiles.getProfile().householdName,'A的家')
  assert.deepEqual(scopedStorage.getStorageInfoSync().keys.filter(k=>k.startsWith('chat-')),['chat-2026-10-09'])
  clearSession();assert.equal(orders.getOrders().length,0);assert.equal(scopedStorage.getStorageSync('chat-2026-10-09'),undefined)
})

test('delayed mock writes abort after account switch rather than writing into another account',async()=>{
  setup();setSession({accountId:'A',householdId:'home'})
  const saving=mockService.saveAddress(address)
  setSession({accountId:'B',householdId:'home'})
  await assert.rejects(saving,/账号已切换/);assert.equal(mockService.selectedAddress(),null)
})

test('receipt preserves paused and refund states and leaves other batches unchanged',()=>{
  setup();const created=planOrder();actions.pauseOrder(created.id)
  const before=orders.getOrder(created.id);assert.equal(before.deliveryBatches[0].fulfillmentStatus,'shipped')
  const after=actions.receiveOrder(created.id,1)
  assert.equal(after.status,'paused');assert.equal(after.planPaused,true);assert.deepEqual(after.deliveryBatches.slice(1),before.deliveryBatches.slice(1))
  actions.cancelOrderRemaining(created.id);const refunded=orders.getOrder(created.id);assert.equal(refunded.refundStatus,'pending')
  assert.equal(actions.receiveOrder(created.id,1).status,'refund_pending')
})

test('single batch address edits persist without altering paid address snapshot or other batches',()=>{
  setup();const created=planOrder(),before=orders.getOrder(created.id)
  const after=actions.changeOrderBatchAddress(created.id,2,{...address,detail:'测试路99号'})
  assert.equal(orders.getOrder(created.id).deliveryBatches[1].addressSnapshot.detail,'测试路99号')
  assert.deepEqual(after.addressSnapshot,before.addressSnapshot);assert.deepEqual(after.deliveryBatches[0],before.deliveryBatches[0]);assert.deepEqual(after.deliveryBatches[2],before.deliveryBatches[2])
  assert.throws(()=>actions.changeOrderBatchAddress(created.id,1,address),/当前状态/)
})

test('remaining cancellation excludes shipped and received batches and does not invent a refund amount',()=>{
  setup();const created=planOrder();actions.receiveOrder(created.id,2)
  const preview=actions.remainingRefundPreview(created.id)
  assert.deepEqual(preview.batchIndices,[3]);assert.equal(preview.amountCents,null)
  assert.equal(actions.cancelOrderRemaining(created.id).status,'refund_pending')
})

test('resume requires confirmation of a fresh schedule and preserves shipped batches',()=>{
  setup();const created=planOrder();actions.pauseOrder(created.id)
  const before=orders.getOrder(created.id),preview=actions.previewResume(created.id)
  assert.equal(orders.getOrder(created.id).planPaused,true);assert.deepEqual(preview.batches.map(b=>b.index),[2,3])
  const after=actions.resumeOrder(created.id,preview)
  assert.equal(after.planPaused,false);assert.equal(after.status,'paid');assert.deepEqual(after.deliveryBatches[0],before.deliveryBatches[0])
  actions.pauseOrder(created.id);const stale=actions.previewResume(created.id)
  actions.changeOrderBatchAddress(created.id,2,{...address,detail:'改址'})
  assert.throws(()=>actions.resumeOrder(created.id,stale),/排程已变化/)
})

test('after-sales validate quantities, deduplicate one batch and keep applications on different batches',()=>{
  setup();const created=planOrder(),form={batchIndex:1,items:[{id:'sku-1',name:'番茄',quantity:1}],expectation:'希望退款',reason:'少件／漏件',description:'缺少1包',attachments:['/tmp/evidence.jpg']}
  assert.throws(()=>actions.submitOrderAfterSale(created.id,{...form,items:[{id:'sku-1',quantity:3}]}),/数量/)
  assert.throws(()=>actions.submitOrderAfterSale(created.id,{...form,items:[{id:'sku-1',quantity:-1}]}),/数量/)
  actions.submitOrderAfterSale(created.id,form);actions.submitOrderAfterSale(created.id,form);actions.submitOrderAfterSale(created.id,{...form,batchIndex:2})
  const saved=orders.getOrder(created.id);assert.equal(saved.afterSales.length,2);assert.equal(saved.afterSales[0].description,'缺少1包');assert.deepEqual(saved.afterSales[0].attachments,form.attachments)
})

test('server allowedActions restrict mutations and cancelled orders cannot be received',()=>{
  setup();const created=planOrder();orders.updateOrder(created.id,{allowedActions:[]})
  assert.throws(()=>actions.receiveOrder(created.id,1),/当前状态/)
  orders.updateOrder(created.id,{allowedActions:['receive'],status:'cancelled'})
  assert.equal(actions.canOrderAction(orders.getOrder(created.id),'receive',1),false)
  assert.equal(orders.orderStatus({status:'future-server-state'}).label,'状态待确认')
})

test('checkout invalidates when same-count diners, address, recipe or expiration change',()=>{
  const input={members:['A','B'],address:'addr-1',products:[{id:1,quantity:1}],version:1}
  const quote=checkout.createCheckoutQuote(input,1000)
  assert.doesNotThrow(()=>checkout.validateCheckoutQuote(quote,input,2000))
  for(const changed of [{...input,members:['A','C']},{...input,address:'addr-2'},{...input,version:2}])assert.throws(()=>checkout.validateCheckoutQuote(quote,changed,2000),/变化/)
  assert.throws(()=>checkout.validateCheckoutQuote(quote,input,301000),/过期/)
})

test('order creation is idempotent and unknown payment cannot be repeated',async()=>{
  setup();const input={clientRequestId:'checkout-1',items:[],meal:'午餐',totalCents:100}
  const one=await mockService.createOrder(input),two=await mockService.createOrder(input)
  assert.equal(one.id,two.id);assert.equal(orders.getOrders().length,1);assert.equal(one.status,'pending')
  await mockService.payOrder(one.id,'unknown');await assert.rejects(mockService.payOrder(one.id,'success'),/查询支付结果/)
  assert.equal((await mockService.paymentResult(one.id)).paymentStatus,'unknown')
})

test('21 batch SKU snapshots and estimates agree and batch IDs differ across orders',()=>{
  setup();const plan=exclusive.adaptExclusivePlan(exclusive.getExclusivePlan('balanced')),batches=exclusive.createDeliveryBatches(plan,'2026-10-09')
  assert.equal(batches.length,21);assert.ok(batches.every(b=>b.items.length))
  const amount=batches.flatMap(b=>b.items).reduce((sum,p)=>sum+p.quantity*p.priceCents,0);assert.equal(amount,plan.totalEstimateCents)
  const first=orders.createDemoOrder({items:batches[0].items,totalCents:amount,meal:'三餐',deliveryBatches:batches}),second=orders.createDemoOrder({items:batches[0].items,totalCents:amount,meal:'三餐',deliveryBatches:batches})
  assert.notEqual(first.deliveryBatches[0].batchId,second.deliveryBatches[0].batchId)
})

test('unconfigured API adapters and transport reject without demo fallback or network calls',async()=>{
  setup();uni.request=()=>{throw new Error('unexpected network')}
  await assert.rejects(callApiAdapter('createOrder',{}),error=>error.code==='ADAPTER_NOT_READY')
  await assert.rejects(request({path:'/orders',method:'POST'}),error=>error.code==='API_NOT_CONFIGURED')
  assert.equal(orders.getOrders().length,0)
})

test('receipt page prevents duplicate dialogs and duplicate submissions',async()=>{
  const {calls}=setup(),created=planOrder()
  const page=evaluatePage('orders/detail.vue',{options:{id:created.id}},'order,confirmReceived,selectedBatchIndex,busy')
  await page.show();page.confirmReceived();page.confirmReceived();assert.equal(calls.modals.length,1)
  const submission=calls.modals[0].success({confirm:true});assert.equal(page.busy.value,true);page.confirmReceived();await submission
  assert.equal(calls.modals.length,1);assert.deepEqual(orders.getOrder(created.id).receivedBatchIndices,[1]);page.dispose()
})

test('after-sale page preserves filled input and evidence on failure and allows retry',async()=>{
  setup();const created=planOrder(),page=evaluatePage('orders/detail.vue',{options:{id:created.id}},'requestAfterSale,serviceForm,submitAfterSale,error,existingService')
  await page.show();page.requestAfterSale();page.serviceForm.value.items[0].quantity=1;page.serviceForm.value.description='少件说明';page.serviceForm.value.attachments=['/tmp/evidence.jpg']
  failNextMock('afterSale');await page.submitAfterSale();assert.match(page.error.value,/重试/);assert.equal(page.serviceForm.value.description,'少件说明');assert.equal(orders.getOrder(created.id).afterSales.length,0)
  await page.submitAfterSale();assert.equal(page.existingService.value.description,'少件说明');page.dispose()
})

test('order detail ignores a slow obsolete refresh after a newer response',async()=>{
  setup();const created=planOrder();let finishFirst,calls=0
  const service={...mockService,order:()=>++calls===1?new Promise(resolve=>{finishFirst=resolve}):Promise.resolve({...created,status:'cancelled'})}
  const page=evaluatePage('orders/detail.vue',{options:{id:created.id},service},'order,loadOrder')
  const first=page.loadOrder();await page.loadOrder();finishFirst(created);await first;assert.equal(page.order.value.status,'cancelled');page.dispose()
})

test('chat retry keeps one user message and unloaded reply does not write memory',async()=>{
  setup();const page=evaluatePage('chat/index.vue',{},'ask,messages,replyError,retryReply')
  failNextMock('chat');await page.ask('今晚全家吃什么');assert.ok(page.replyError.value);await page.retryReply();assert.equal(page.messages.value.filter(m=>m.role==='user').length,1)
  const before=profiles.getProfile().memories.length,pending=page.ask('我以后不吃香菜');page.dispose();await pending;assert.equal(profiles.getProfile().memories.length,before)
})

test('checkout page duplicate payment creates one order and unknown outcome blocks repayment',async()=>{
  const {calls}=setup();await mockService.saveAddress(address)
  const page=evaluatePage('shop/index.vue',{options:{meal:'dinner'}},'checkout,pay,paying,paymentState,paidOrderId,queryPayment')
  page.show();page.checkout();const pending=page.pay();assert.equal(page.paying.value,true);await page.pay();calls.actionSheet.success({tapIndex:3});await pending
  assert.equal(orders.getOrders().length,1);assert.equal(page.paymentState.value,'unknown');await page.pay();assert.equal(orders.getOrders().length,1)
  await page.queryPayment();assert.equal(page.paymentState.value,'unknown');page.dispose()
})

test('all literal modal button labels fit WeChat constraints',()=>{
  function files(directory){return readdirSync(directory,{withFileTypes:true}).flatMap(entry=>entry.isDirectory()?files(directory+'/'+entry.name):[directory+'/'+entry.name])}
  for(const file of files(fileURLToPath(new URL('../src/pages',import.meta.url))).filter(file=>file.endsWith('.vue'))){
    for(const match of readFileSync(decodeURIComponent(file),'utf8').matchAll(/(?:confirmText|cancelText):\s*'([^']+)'/g))assert.ok([...match[1]].length<=4,file+': '+match[1])
  }
})

test('same-count member updates only apply the latest result and block checkout while pending',async()=>{
  setup();const completions=[]
  const page=evaluatePage('shop/index.vue',{options:{meal:'dinner'},mockDelay:()=>new Promise(resolve=>completions.push(resolve))},'confirmDiners,plan,checkout,orderOpen,menuUpdating')
  page.show();const first=page.confirmDiners([1,2]),second=page.confirmDiners([1,3])
  page.checkout();assert.equal(page.orderOpen.value,false);assert.equal(page.menuUpdating.value,true)
  completions[1]();await second;completions[0]();await first
  assert.deepEqual(page.plan.value.members.map(member=>member.id),[1,3]);assert.equal(page.menuUpdating.value,false);page.dispose()
})

test('failed member refresh preserves prior menu and disables stale checkout until retry succeeds',async()=>{
  setup();const page=evaluatePage('shop/index.vue',{options:{meal:'dinner'}},'confirmDiners,plan,checkout,orderOpen,menuError,retryMenuUpdate')
  page.show();const original=page.plan.value.members.map(member=>member.id)
  failNextMock('menu');await page.confirmDiners([1,2]);assert.ok(page.menuError.value);assert.deepEqual(page.plan.value.members.map(member=>member.id),original)
  page.checkout();assert.equal(page.orderOpen.value,false);await page.retryMenuUpdate();assert.equal(page.menuError.value,'');page.checkout();assert.equal(page.orderOpen.value,true);page.dispose()
})

test('exclusive checkout waits for a complete generated plan in API mode',()=>{
  setup()
  const page=evaluatePage('shop/index.vue',{
    options:{meal:'dinner',source:'exclusive-plan',plan:'balanced',start:'2026-10-20',batches:'21'},isMockMode:false,
    adaptExclusivePlan:template=>({...template,sourceType:null,fixturePlans:[],blocked:['专属计划尚未生成'],products:[],estimateCents:0,totalEstimateCents:0}),
  },'products,deliveryBatches,checkout,orderOpen')
  assert.deepEqual(page.products.value,[])
  assert.deepEqual(page.deliveryBatches.value,[])
  page.checkout();assert.equal(page.orderOpen.value,false)
  page.dispose()
})

async function apiRuntime() {
  const dataUrl=source=>'data:text/javascript;base64,'+Buffer.from(source).toString('base64')
  const config=dataUrl(readFileSync(new URL('../src/services/config.js',import.meta.url),'utf8').replace('import.meta.env',"({VITE_SERVICE_MODE:'api',VITE_API_BASE_URL:'https://integration.invalid'})"))
  const session=dataUrl(readFileSync(new URL('../src/services/session.js',import.meta.url),'utf8').replace("'./config.js'",JSON.stringify(config)))
  const storage=dataUrl(readFileSync(new URL('../src/services/storage.js',import.meta.url),'utf8').replace("'./config.js'",JSON.stringify(config)).replace("'./session.js'",JSON.stringify(session)))
  const navigation=dataUrl(readFileSync(new URL('../src/services/navigation.js',import.meta.url),'utf8').replace("'./config.js'",JSON.stringify(config)))
  const transport=dataUrl(readFileSync(new URL('../src/services/request.js',import.meta.url),'utf8').replace("'./config.js'",JSON.stringify(config)).replace("'./session.js'",JSON.stringify(session)).replace("'./storage.js'",JSON.stringify(storage)))
  return {config:await import(config),session:await import(session),storage:await import(storage),navigation:await import(navigation),transport:await import(transport)}
}

test('API runtime namespaces cannot read mock data and unadapted routes are blocked',async()=>{
  setup();setSession({accountId:'A',householdId:'home'});scopedStorage.setStorageSync('demo-orders-v1',[{id:'demo'}])
  const api=await apiRuntime();api.session.setSession({accountId:'A',householdId:'home'})
  assert.equal(api.storage.scopedStorage.getStorageSync('demo-orders-v1'),undefined);assert.throws(()=>api.config.requireMock(),error=>error.code==='ADAPTER_NOT_READY')
  assert.equal(api.navigation.canOpenPage('/pages/index/index'),true);assert.equal(api.navigation.canOpenPage('/pages/shop/index'),false)
  const replacements=[]
  const history={replaceState:(_state,_title,url)=>replacements.push(url)}
  api.navigation.guardInitialH5Route({hash:'#/pages/shop/index?meal=dinner',pathname:'/preview/',search:''},history)
  assert.deepEqual(replacements,['/preview/#/pages/index/index'])
  api.navigation.guardInitialH5Route({hash:'#/pages/account/index',pathname:'/',search:''},history)
  assert.equal(replacements.length,1)
})

test('HTTP transport detects expired sessions, timeout and obsolete responses without retrying writes',async()=>{
  setup();const api=await apiRuntime();api.session.setSession({accountId:'A',householdId:'home',token:'test-token'})
  let calls=0,callback;uni.request=options=>{calls++;callback=options}
  const failed=api.transport.request({path:'/orders',method:'POST'});assert.equal(callback.header.Authorization,'Bearer test-token')
  callback.fail({errMsg:'request:fail timeout'});await assert.rejects(failed,error=>error.code==='NETWORK_ERROR');assert.equal(calls,1)
  const expired=api.transport.request({path:'/orders'});callback.success({statusCode:401,header:{'x-request-id':'trace-1'}})
  await assert.rejects(expired,error=>error.code===401&&error.traceId==='trace-1');assert.equal(api.session.getSession(),null)
  api.session.setSession({accountId:'A',householdId:'home'});const obsolete=api.transport.request({path:'/orders'});api.session.setSession({accountId:'B',householdId:'home'});callback.success({statusCode:401})
  await assert.rejects(obsolete,error=>error.code==='SESSION_CHANGED');assert.equal(api.session.getSession().accountId,'B')
  const relogin=api.transport.request({path:'/orders'});api.session.setSession({accountId:'B',householdId:'home',token:'renewed'});callback.success({statusCode:401})
  await assert.rejects(relogin,error=>error.code==='SESSION_CHANGED');assert.equal(api.session.getSession().token,'renewed')
})

test('anonymous WeChat credential errors preserve an existing session and structured business errors',async()=>{
  setup();const api=await apiRuntime();api.session.setSession({accountId:'A',token:'existing-token'})
  let callback;uni.request=options=>{callback=options}
  const invalid=api.transport.request({path:'/api/auth/wechat/login',method:'POST',authenticated:false})
  assert.deepEqual(callback.header,{})
  callback.success({statusCode:401,data:{detail:{code:'WECHAT_CODE_INVALID',message:'请重新登录'}}})
  await assert.rejects(invalid,e=>e.code===401&&e.businessCode==='WECHAT_CODE_INVALID'&&e.message==='请重新登录')
  assert.equal(api.session.getSession().token,'existing-token')
  assert.match(api.storage.storageScope(),/unassigned/)
})

test('health requests keep server error details and cannot replace the session bearer token',async()=>{
  setup();const api=await apiRuntime();api.session.setSession({accountId:'A',householdId:'home',token:'current-token'})
  let callback;uni.request=options=>{callback=options}
  const pending=api.transport.request({path:'/api/health/v1/members',method:'POST',data:{client_request_id:'intent'},headers:{Authorization:'Bearer other-token','Idempotency-Key':'intent','If-Match':'"3"'}})
  assert.equal(callback.header.Authorization,'Bearer current-token')
  assert.equal(callback.header['Idempotency-Key'],'intent')
  assert.equal(callback.header['If-Match'],'"3"')
  callback.success({statusCode:409,data:{code:'version_conflict',message:'草稿版本已变化',trace_id:'health-trace',retryable:true}})
  await assert.rejects(pending,error=>error.code===409&&error.businessCode==='version_conflict'&&error.message==='草稿版本已变化'&&error.traceId==='health-trace'&&error.retryable===true)
  assert.equal(api.session.getSession().token,'current-token')
})

test('a failed request from an old login cannot surface data in a new session',async()=>{
  setup();const api=await apiRuntime();api.session.setSession({accountId:'A',householdId:'home',token:'old-token'})
  let callback;uni.request=options=>{callback=options}
  const pending=api.transport.request({path:'/api/health/v1/members'})
  api.session.setSession({accountId:'A',householdId:'home',token:'new-token'})
  callback.fail({errMsg:'request:fail timeout'})
  await assert.rejects(pending,error=>error.code==='SESSION_CHANGED')
  assert.equal(api.session.getSession().token,'new-token')
})

test('photo analysis failure retains image and retries without saving a fictional result',async()=>{
  setup();uni.chooseImage=options=>options.success({tempFilePaths:['/tmp/photo.jpg']})
  const page=evaluatePage('scan/index.vue',{},'chooseImage,analyze,status,imagePath,analysisError,confirmRecord')
  failNextMock('photo');await page.chooseImage('album');assert.equal(page.status.value,'error');assert.equal(page.imagePath.value,'/tmp/photo.jpg')
  page.confirmRecord('records');assert.equal(profiles.getRecords().length,0);await page.analyze();assert.equal(page.status.value,'result');page.dispose()
})

test('latest photo analysis wins and unloading prevents a stale result',async()=>{
  setup();const completions=[];let image=0;uni.chooseImage=options=>options.success({tempFilePaths:['/tmp/photo-'+(++image)+'.jpg']})
  const page=evaluatePage('scan/index.vue',{mockDelay:()=>new Promise(resolve=>completions.push(resolve))},'chooseImage,status,imagePath')
  const first=page.chooseImage('album'),second=page.chooseImage('album');completions[1]();await second;completions[0]();await first
  assert.equal(page.imagePath.value,'/tmp/photo-2.jpg');assert.equal(page.status.value,'result')
  const third=page.chooseImage('camera');page.dispose();completions[2]();await third;assert.equal(page.status.value,'analyzing')
})


test('pregnancy context belongs to the stated member, can be withdrawn, and adds no profile stage fields',async()=>{
  setup();const page=evaluatePage('chat/index.vue',{},'ask,messages,withdrawContext,profile')
  const original=structuredClone(profiles.getProfile().members)
  await page.ask('我怀孕了，今晚吃什么？')
  const message=page.messages.value.find(message=>message.role==='user')
  assert.equal(message.memberId,original.find(member=>member.relation==='本人').id)
  assert.equal(message.contextRecorded,true)
  assert.ok(!page.messages.value.at(-1).text.includes('位成人'))
  assert.deepEqual(profiles.getProfile().members,original)
  await page.withdrawContext(message)
  assert.equal(message.withdrawn,true);assert.deepEqual(contexts.mealContext(mealState.localDate()),[])
  page.dispose()
})

test('an ambiguous special circumstance is clarified in dialogue before attaching it to a member',async()=>{
  setup();const page=evaluatePage('chat/index.vue',{},'ask,messages')
  await page.ask('家人正在哺乳，安排晚餐')
  assert.match(page.messages.value.at(-1).text,/哪位家庭成员/)
  assert.equal(page.messages.value[0].memberId,undefined)
  page.dispose()
})
