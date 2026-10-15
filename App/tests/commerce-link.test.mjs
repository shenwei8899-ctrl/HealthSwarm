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
