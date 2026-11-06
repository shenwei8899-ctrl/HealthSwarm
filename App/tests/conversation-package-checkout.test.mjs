import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { ref, computed } from 'vue'
import { resolveCheckoutAddress } from '../src/services/address-model.js'
import { packagePrice } from '../src/utils/package-presentation.js'

function mount() {
  const calls = [], hooks = {}
  let scope = 'A', picker, readError, readData
  const offer = { name:'测试牛奶',sku_id:64,price_cent:1350,spec:'950 ml',image_url:'/milk.jpg',available:true,offer_token:'receipt' }
  const addresses = [{id:1,name:'测试地址',isDefault:true},{id:2,name:'另一个地址'}]
  const api = {
    connect:async()=>{}, pendingOrder:()=>null,
    confirmRecommendation:async()=>{calls.push('confirm-package')},
    addresses:async()=>addresses,
    slots:async id=>{calls.push(['slots',id]);return {supported:true,items:[{id:10,available:true},{id:20,available:true}]}},
    quoteRecommendation:async(sn,version,address,slot)=>{
      calls.push(['quote',address,slot])
      return {checkout_token:'quote',expires_at:new Date(Date.now()+60000).toISOString(),goods_amount_cent:1350,shipping_fee_cent:500,payable_amount_cent:1850,
        items:[{sku_id:64,quantity:1,line_amount_cent:1350,snapshot:{product_name:'测试牛奶',sku_name:'950 ml',image_url:'/milk.jpg'}}]}
    },
    createOrder:async token=>{calls.push(['order',token]);return {order_sn:'order-1'}},
    retryOrder:async()=>{calls.push('recover');return {order_sn:'original-order'}},
  }
  const deps = {ref,computed,resolveCheckoutAddress,packagePrice,commerce:api,storageContext:()=>scope,
    defineProps:()=>({route:{conversation:'request',offer:'receipt'}}),
    onMounted:fn=>hooks.mount=fn,onShow:fn=>hooks.show=fn,onUnmounted:fn=>hooks.unmount=fn,
    request:async input=>{calls.push(input.method||'GET');if(!input.method&&readError)throw readError;return {data:input.method==='POST'?{package:{package_sn:'package',package_version:1,status:'available'}}:readData||{request_id:'request',offers:[{...offer}]}}},
    openAddressPicker:args=>{picker=args},uni:{navigateTo:args=>calls.push(['navigate',args.url]),navigateBack:()=>calls.push('back'),reLaunch:args=>calls.push(['relaunch',args.url])}}
  const script=readFileSync(new URL('../src/components/ConversationPackagePurchase.vue',import.meta.url),'utf8')
    .match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
  const page=new Function('deps',`const {${Object.keys(deps).join(',')}}=deps;${script};return {load,checkout,selectSlot,chooseAddress,closeCheckout,submit,products,quote,address,slots,error,retryLabel,canSubmit,checkoutOpen,pending,busy,sourceUnavailable,returnToChat}`)(deps)
  return {...page,api,offer,addresses,calls,hooks,failRead:error=>{readError=error},respondWith:data=>{readData=data},selectAddress:id=>picker.onSelected(id),switchAccount:()=>{scope='B'}}
}

test('进入采购自动读取地址、配送时段和报价，只有确认时才创建订单',async()=>{
  const p=mount();await p.load();assert.equal(p.calls.includes('POST'),false)
  await p.checkout()
  assert.equal(p.products.value[0].name,'测试牛奶');assert.equal(p.quote.value.payable_amount_cent,1850)
  assert.equal(p.canSubmit.value,true);assert.equal(p.calls.some(c=>c[0]==='order'),false)
  await p.submit();assert.deepEqual(p.calls.find(c=>c[0]==='order'),['order','quote'])
})

test('配送响应异常仍保留商品，禁止下单，重试后自动恢复报价',async()=>{
  const p=mount();await p.load();const slots=p.api.slots
  p.api.slots=async()=>{throw Object.assign(new Error('商城返回异常'),{code:'INVALID_RESPONSE'})}
  await p.checkout()
  assert.equal(p.products.value.length,1);assert.equal(p.products.value[0].priceCents,1350)
  assert.equal(p.quote.value,null);assert.equal(p.canSubmit.value,false)
  assert.equal(p.retryLabel.value,'重新获取配送信息');assert.match(p.error.value,/配送信息读取失败/)
  assert.equal(p.calls.some(c=>c[0]==='quote'),false)
  p.api.slots=slots;await p.load();assert.equal(p.canSubmit.value,true)
  assert.equal(p.calls.filter(c=>c==='POST').length,1)
})

test('报价失败保留已选商品和配送信息，重试不会重复创建采购包',async()=>{
  const p=mount();await p.load();const quote=p.api.quoteRecommendation
  p.api.quoteRecommendation=async()=>{throw Object.assign(new Error('bad response'),{code:'INVALID_RESPONSE'})}
  await p.checkout();assert.equal(p.retryLabel.value,'重新核价');assert.equal(p.products.value.length,1)
  assert.equal(p.slots.value.length,2);assert.equal(p.canSubmit.value,false)
  p.api.quoteRecommendation=quote;await p.load();assert.equal(p.canSubmit.value,true)
  assert.equal(p.calls.filter(c=>c==='POST').length,1)
})

test('更换地址返回和选择配送时段后都自动重新核价',async()=>{
  const p=mount();await p.load();await p.checkout()
  p.chooseAddress();p.selectAddress('2');assert.equal(p.quote.value,null)
  await p.hooks.show();assert.deepEqual(p.calls.filter(c=>c[0]==='quote').at(-1),['quote',2,10])
  await p.selectSlot(20);assert.deepEqual(p.calls.filter(c=>c[0]==='quote').at(-1),['quote',2,20])
})

test('没有地址或没有配送时段时保留商品，不调用报价和下单',async()=>{
  const p=mount();await p.load();p.addresses.length=0;await p.checkout()
  assert.equal(p.products.value.length,1);assert.equal(p.address.value,null);assert.equal(p.canSubmit.value,false)
  p.addresses.push({id:3,isDefault:true});p.api.slots=async()=>({supported:false,items:[],message:'该地区暂不配送'})
  await p.checkout();assert.match(p.error.value,/不配送/);assert.equal(p.calls.some(c=>c[0]==='quote'),false)
  await p.submit();assert.equal(p.calls.some(c=>c[0]==='order'),false)
})

test('不完整或过期报价不能开启确认下单',async()=>{
  for(const result of [{checkout_token:'q',expires_at:new Date(Date.now()-1000).toISOString()},
    {checkout_token:'q',expires_at:new Date(Date.now()+60000).toISOString(),items:[],goods_amount_cent:1350,shipping_fee_cent:500,payable_amount_cent:1850}]){
    const p=mount();await p.load();p.api.quoteRecommendation=async()=>result;await p.checkout();await p.submit()
    assert.equal(p.canSubmit.value,false);assert.equal(p.quote.value,null);assert.equal(p.calls.some(c=>c[0]==='order'),false)
  }
})

test('地址在配送范围内但没有时段时，不能把支持配送当作成功或错误原因',async()=>{
  const p=mount();await p.load()
  p.api.slots=async()=>({supported:true,message:'当前地址支持配送',items:[]})
  await p.checkout()
  assert.match(p.error.value,/暂无可用配送时段/);assert.equal(p.products.value.length,1)
  assert.equal(p.canSubmit.value,false);assert.equal(p.calls.some(c=>c[0]==='quote'),false)
})

test('切换账号后旧报价不能回填，页面重新进入清除旧数据',async()=>{
  const p=mount();await p.load();let release
  const quote=p.api.quoteRecommendation
  p.api.quoteRecommendation=(...args)=>new Promise(resolve=>{release=async()=>resolve(await quote(...args))})
  const work=p.checkout();while(!release)await new Promise(resolve=>setImmediate(resolve))
  p.switchAccount();await release();await work;assert.equal(p.quote.value,null)
  await p.load();assert.equal(p.checkoutOpen.value,false);assert.equal(p.address.value,null)
})

test('不确定订单结果走原订单恢复，不再次报价或新建订单',async()=>{
  const p=mount();await p.load();p.api.pendingOrder=()=>({key:'pending'});await p.checkout()
  assert.equal(p.pending.value,true);assert.equal(p.calls.includes('POST'),false)
  await p.submit(true);assert.equal(p.calls.includes('recover'),true);assert.equal(p.calls.some(c=>c[0]==='order'),false)
})

test('临时刷新失败保留商品，但撤权后清除商品和配送资料',async()=>{
  const p=mount();await p.load();await p.checkout()
  p.failRead(Object.assign(new Error('网络暂不可用'),{code:'NETWORK_ERROR'}));await p.load()
  assert.equal(p.products.value.length,1);assert.equal(p.canSubmit.value,false);assert.equal(p.quote.value,null)
  p.failRead(Object.assign(new Error('无权读取'),{code:403}));await p.load()
  assert.equal(p.products.value.length,0);assert.equal(p.address.value,null);assert.equal(p.slots.value.length,0)
})

test('旧推荐不再返回时清除采购状态并提供返回咨询，不误报对话归属',async()=>{
  const p=mount();await p.load();await p.checkout()
  p.respondWith({request_id:'request',offers:[]});await p.load()
  assert.equal(p.sourceUnavailable.value,true);assert.match(p.error.value,/已失效|已变化/)
  assert.doesNotMatch(p.error.value,/不属于当前对话/)
  assert.equal(p.products.value.length,0);assert.equal(p.address.value,null)
  assert.equal(p.canSubmit.value,false);assert.equal(p.checkoutOpen.value,false)
  p.returnToChat();assert.equal(p.calls.at(-1),'back')
})

test('相邻请求的响应不能被当前购买页采纳',async()=>{
  const p=mount();p.respondWith({request_id:'another-request',offers:[p.offer]});await p.load()
  assert.equal(p.products.value.length,0);assert.equal(p.canSubmit.value,false)
  assert.equal(p.sourceUnavailable.value,true)
})

test('网络故障保留重试，恢复后可重新进入采购',async()=>{
  const p=mount();p.failRead(new Error('网络暂不可用'));await p.load()
  assert.equal(p.sourceUnavailable.value,false)
  p.failRead(null);await p.load();await p.checkout()
  assert.equal(p.canSubmit.value,true);assert.equal(p.sourceUnavailable.value,false)
})
