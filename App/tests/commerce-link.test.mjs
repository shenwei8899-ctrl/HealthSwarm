import test from 'node:test'
import assert from 'node:assert/strict'
import { createCommerceClient, orderView } from '../src/services/commerce-client.js'

function fixture(handler = () => ({ statusCode: 200, data: { code: 0, data: {} } })) {
  const values = new Map(), calls = []
  let scope = 'family-A', count = 0
  const client = createCommerceClient({
    baseUrl: 'http://127.0.0.1:18081', authMode: 'member',
    parent: { read: () => null, scope: () => scope, storageScope: () => scope },
    storage: { get: k => values.get(k), set: (k, v) => values.set(k, v) },
    randomKey: () => 'key-' + ++count,
    transport: async options => { calls.push(options); return handler(options) },
  })
  return { client, calls, switchScope: () => { scope = 'family-B' } }
}
const loginResponse = (id = 1) => ({ statusCode: 200, data: { code: 0, data: { user: { id, token: 'token-' + id } } } })

function unified(handler) {
  let account = { accountId: '17', token: 'agent-17' }, revision = 1, key = 0
  const storage = new Map(), calls = []
  const client = createCommerceClient({ baseUrl: '/commerce-api', allowProxy: true, authMode: 'agent',
    parent: { read: () => account, scope: () => account.accountId + ':' + revision, storageScope: () => account.accountId },
    storage: { get: k => storage.get(k), set: (k, v) => storage.set(k, v) }, randomKey: () => 'intent-' + (++key),
    transport: async o => { calls.push(o); return handler(o) } })
  return { client, calls, change: () => { account = { accountId: '18', token: 'agent-18' }; revision++ }, refresh: () => { revision++ } }
}
const exchangeResponse = id => ({ statusCode: 200, data: { code: 0, data: { agent_account_id: id, user: { id: 7, token: 'mall-token' } } } })
test('unified login exchanges only the Agent bearer, deduplicates parallel requests and uses mall tokens for cart', async () => {
  const f = unified(o => o.url.endsWith('/exchange') ? exchangeResponse('17') : { statusCode: 200, data: { code: 0, data: { items: [] } } })
  await Promise.all([f.client.cart(), f.client.addresses()])
  assert.equal(f.calls.filter(o => o.url.endsWith('/exchange')).length, 1)
  assert.deepEqual(f.calls[0].data, {})
  assert.equal(f.calls[0].header.Authorization, 'Bearer agent-17')
  assert.equal(f.calls[1].header.token, 'mall-token')
  assert.equal(f.calls[1].header.Authorization, undefined)
  f.refresh(); assert.equal(f.client.session(), null); await f.client.connect()
  assert.equal(f.calls.filter(o => o.url.endsWith('/exchange')).length, 2)
})
test('unmapped unified identity retries automatic exchange without prompting for account details', async () => {
  let ready=false
  const f = unified(() => ready ? exchangeResponse('17') : { statusCode: 503, data: { code: 50301, message: 'not ready' } })
  await assert.rejects(f.client.connect(), e => e.code === 50301)
  assert.equal(f.client.session(),null)
  ready=true
  await f.client.connect()
  assert.equal(f.client.session().userId,'7')
  assert.deepEqual(f.calls.map(c=>c.data),[{},{}])
})

test('unified exchange rejects wrong identity and account changes while pending', async () => {
  const wrong = unified(() => exchangeResponse('18'))
  await assert.rejects(wrong.client.connect(), e => e.code === 'INVALID_IDENTITY')
  assert.equal(wrong.client.session(), null)
  let release
  const f = unified(() => new Promise(r => { release = r }))
  const pending = f.client.connect(); await Promise.resolve(); f.change(); release(exchangeResponse('17'))
  await assert.rejects(pending, e => e.code === 'SESSION_CHANGED'); assert.equal(f.client.session(), null)
})

test('expired mall session is exchanged again through Agent before restoring protected pages', async () => {
  let exchanges = 0, reads = 0
  const f = unified(o => {
    if (o.url.endsWith('/exchange')) { exchanges++; return exchangeResponse('17') }
    reads++
    return reads === 1 ? {statusCode:401,data:{code:40100}} : {statusCode:200,data:{code:0,data:{user:{id:7}}}}
  })
  await f.client.connect()
  assert.equal((await f.client.restore()).userId, '7')
  assert.equal(exchanges, 2); assert.equal(reads, 2)
})
test('unified cart and order writes are never automatically retried after authentication expiry', async () => {
  for (const operation of [c => c.add('sku', 1), c => c.createOrder('checkout')]) {
    const f = unified(o => o.url.endsWith('/exchange') ? exchangeResponse('17') : {statusCode:401,data:{code:40100}})
    await assert.rejects(operation(f.client), e => e.code === 401)
    assert.equal(f.calls.length, 2); assert.equal(f.client.session(), null)
  }
})

function paymentFixture(reply, getCode = async () => 'fresh-wechat-code') {
  let scope = 'agent-A', count = 0, charges = 0
  const calls = [], values = new Map()
  const client = createCommerceClient({ baseUrl:'/commerce-api', allowProxy:true, authMode:'agent', appId:'wx1234567890abcdef',
    parent:{read:()=>({accountId:'17',token:'agent-token'}),scope:()=>scope},
    storage:{get:k=>values.get(k),set:(k,v)=>values.set(k,structuredClone(v))}, randomKey:()=> 'pay-intent-' + (++count),
    getWechatCode:getCode, pay:async()=>{charges++},
    transport:async o=>{calls.push(o); if(o.url.endsWith('/exchange')) return exchangeResponse('17'); return reply(o)} })
  return {client,calls,values,charges:()=>charges,change:()=>{scope='agent-B'}}
}
test('unified payment verifies a fresh code with both sessions before prepay and never persists the code', async () => {
  const f = paymentFixture(o => ({statusCode:200,data:{code:0,data:o.url.endsWith('/wechat-payment-identity') ? {linked:true,app_id:'wx1234567890abcdef'} : o.url.endsWith('/payments/wechat') ? {payment_params:{package:'synthetic-prepay'}} : {status:'unpaid'}}}))
  const result = await f.client.payOrder('test-order')
  assert.equal(result.status,'unpaid'); assert.equal(f.charges(),1)
  assert.equal(f.calls[1].url,'/commerce-api/api/v1/commerce/session/wechat-payment-identity')
  assert.deepEqual(f.calls[1].data,{code:'fresh-wechat-code'})
  assert.equal(f.calls[1].header.Authorization,'Bearer agent-token'); assert.equal(f.calls[1].header.token,'mall-token')
  assert.equal(f.calls[1].header['Idempotency-Key'],undefined)
  assert.ok(f.calls[2].url.endsWith('/payments/wechat'))
  assert.equal(JSON.stringify([...f.values.values()]).includes('fresh-wechat-code'),false)
})
test('identity failure or wrong AppID never reaches prepay or native payment', async () => {
  for (const response of [{statusCode:409,data:{code:40943,message:'wrong account'}}, {statusCode:200,data:{code:0,data:{linked:true,app_id:'wx0000000000000000'}}}, {statusCode:503,data:{code:50301,message:'not configured'}}]) {
    const f = paymentFixture(()=>response)
    await assert.rejects(f.client.payOrder('test-order'))
    assert.equal(f.charges(),0); assert.equal(f.calls.length,2)
  }
})
test('empty and oversized WeChat codes never reach the identity or payment endpoints', async () => {
  for (const code of ['', 'x'.repeat(257)]) {
    const f = paymentFixture(()=>{throw new Error('must not send code')},async()=>code)
    await assert.rejects(f.client.payOrder('test-order'), e=>e.code==='INVALID_WECHAT_CODE')
    assert.equal(f.calls.length,1); assert.equal(f.charges(),0)
  }
})
test('account switches and fresh-code retries cannot reuse a payment identity from another scope', async () => {
  let release, f
  f = paymentFixture(()=>{throw new Error('must not reach identity')},()=>new Promise(resolve=>{release=resolve}))
  const pending = f.client.payOrder('test-order'); await new Promise(resolve=>setImmediate(resolve)); f.change(); release('late-code')
  await assert.rejects(pending,e=>e.code==='SESSION_CHANGED'); assert.equal(f.calls.length,1); assert.equal(f.charges(),0)
  let codes=0
  const retry=paymentFixture(()=>({statusCode:400,data:{code:40012,message:'expired code'}}),async()=> 'ephemeral-' + (++codes))
  await assert.rejects(retry.client.payOrder('test-order')); await assert.rejects(retry.client.payOrder('test-order'))
  assert.equal(codes,2); assert.ok(retry.client.session()); assert.equal(retry.charges(),0)
  assert.equal(JSON.stringify([...retry.values.values()]).includes('ephemeral-'),false)
})

test('member login uses real commerce credentials without Agent or demo identity', async () => {
  const f = fixture(o => o.url.endsWith('/session/login') ? loginResponse() : { statusCode:200, data:{code:0,data:{items:[]}} })
  await assert.rejects(f.client.cart(), e => e.code === 401)
  await f.client.login({ account:'member', password:'password' })
  await f.client.cart()
  assert.equal(f.calls[0].url, 'http://127.0.0.1:18081/api/v1/commerce/session/login')
  assert.equal(f.calls[1].header.token, 'token-1')
  assert.equal(f.calls.some(o => o.url.endsWith('/session/exchange')), false)
})
test('failed login never creates a local session', async () => {
  const f = fixture(() => ({statusCode:401,data:{code:40100,message:'账号或密码错误'}}))
  await assert.rejects(f.client.login({account:'bad',password:'bad'}))
  assert.equal(f.client.session(), null)
})
test('catalog failure never falls back to demonstration products', async () => {
  const f = fixture(() => { throw new Error('offline') })
  await assert.rejects(f.client.products(), e => e.code === 'NETWORK_ERROR')
})
test('late responses cannot expose a previous family account', async () => {
  let release
  const f = fixture(() => new Promise(r => { release = r }))
  const pending = f.client.products(); await Promise.resolve()
  f.switchScope(); release({statusCode:200,data:{code:0,data:{items:['private']}}})
  await assert.rejects(pending, e => e.code === 'SESSION_CHANGED')
})
test('unknown order retries retain the original key across relogin', async () => {
  let failed = true
  const f = fixture(o => {
    if (o.url.endsWith('/session/login')) return loginResponse()
    if (o.url.endsWith('/orders') && failed) throw new Error('lost response')
    return {statusCode:200,data:{code:0,data:{order_sn:'ORDER-1'}}}
  })
  await f.client.login({account:'member',password:'pass'})
  await assert.rejects(f.client.createOrder('quote'), e => e.code === 'NETWORK_ERROR')
  const original = f.calls.at(-1).header['Idempotency-Key']
  await f.client.login({account:'member',password:'pass'})
  assert.deepEqual(f.client.pendingOrder(), {checkout_token:'quote'})
  failed = false; await f.client.retryOrder()
  assert.equal(f.calls.at(-1).header['Idempotency-Key'], original)
  assert.equal(f.client.pendingOrder(), null)
})
test('old requests cannot complete after a commerce account switch', async () => {
  let release, member = 1
  const f = fixture(o => o.url.endsWith('/session/login') ? loginResponse(member) : new Promise(r => {release=r}))
  await f.client.login({account:'A',password:'pass'})
  const pending = f.client.cart(); await Promise.resolve(); await Promise.resolve()
  member = 2; await f.client.login({account:'B',password:'pass'})
  release({statusCode:200,data:{code:0,data:{items:['A private']}}})
  await assert.rejects(pending, e => e.code === 'SESSION_CHANGED')
  assert.equal(f.client.session().userId, '2')
})
test('expired commerce token leaves the family session independent', async () => {
  const f = fixture(o => o.url.endsWith('/session/login') ? loginResponse() : {statusCode:401,data:{code:40100}})
  await f.client.login({account:'A',password:'pass'})
  await assert.rejects(f.client.cart(), e => e.code === 401)
  assert.equal(f.client.session(), null)
})
test('aftersales submits exactly one selected item using the existing backend contract', async () => {
  const f = fixture(o => o.url.endsWith('/session/login') ? loginResponse() : {statusCode:200,data:{code:0,data:{aftersale_sn:'AF-1'}}})
  await f.client.login({account:'A',password:'pass'})
  await assert.rejects(f.client.submitAfterSale({items:[{},{}]}), e => e.code === 'INVALID_AFTERSALE')
  const result = await f.client.submitAfterSale({order_sn:'O-1',type:'refund_only',items:[{order_item_id:7,quantity:1}]})
  assert.equal(result.items[0].aftersale_sn, 'AF-1')
  assert.deepEqual(f.calls.at(-1).data, {order_sn:'O-1',type:'refund_only',order_item_id:7,quantity:1})
})
test('persisted order actions and price snapshots drive order display', () => {
  const view = orderView({order:{order_sn:'O-1',saleamount:'12.34',paystate:0,orderstate:0},extension:{payment_status:'unpaid',address_snapshot:{detail:'old'}},allowed_actions:['pay','cancel'],items:[{order_goods_id:7,quantity:2,unit_price_cent:617,sku_snapshot:{product_name:'Real product'}}]})
  assert.equal(view.totalCents,1234); assert.equal(view.isDemo,false)
  assert.deepEqual(view.allowedActions,['pay','cancel']); assert.equal(view.items[0].name,'Real product')
})
