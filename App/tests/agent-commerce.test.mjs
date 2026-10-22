import test from 'node:test'
import assert from 'node:assert/strict'
import { createCommerceClient } from '../src/services/commerce-client.js'

function setup(handler) {
  let identity = { token: 'agent-A', accountId: '42' }, scope = 'A', count = 0
  const data = new Map(), calls = []
  const client = createCommerceClient({
    authMode: 'agent', baseUrl: 'https://shop.example.test',
    parent: { read: () => identity, scope: () => scope },
    storage: { get: k => data.get(k), set: (k,v) => data.set(k,v) },
    randomKey: () => 'revision-' + ++count,
    transport: async o => { calls.push(o); return handler(o) },
  })
  return { client, calls, switch: () => { identity = { token: 'agent-B', accountId: '43' }; scope = 'B' }, renew: () => { identity = { ...identity, token: 'renewed' } } }
}
const response = (account = '42') => ({ statusCode:200, data:{ code:0, data:{ user:{id:7,token:'member-7'},agent_account_id:account } } })

test('Agent exchange sends only the current bearer and silently reuses its member', async () => {
  const f = setup(() => response())
  await f.client.exchange()
  assert.equal(f.calls[0].header.Authorization, 'Bearer agent-A')
  assert.deepEqual(f.calls[0].data, {})
  assert.equal(f.client.session().userId, '7')
  assert.equal(f.client.session().agentAccountId, '42')
})

test('parallel first requests share one exchange', async () => {
  const f = setup(o => o.url.endsWith('/session/exchange') ? response() : {statusCode:200,data:{code:0,data:{items:[]}}})
  await Promise.all([f.client.cart(),f.client.cart()])
  assert.equal(f.calls.filter(o => o.url.endsWith('/session/exchange')).length,1)
  assert.equal(f.calls.at(-1).header.token,'member-7')
})
test('unbound identity is shown without creating or silently switching members', async () => {
  const f = setup(() => ({statusCode:409,data:{code:40940,message:'请选择关联会员'}}))
  await assert.rejects(f.client.cart(), e => e.code === 40940)
  assert.equal(f.client.session(),null)
  assert.deepEqual(f.calls[0].data,{})
})
test('a mismatched verified Agent account cannot establish a member session', async () => {
  const f = setup(() => response('43'))
  await assert.rejects(f.client.exchange(), e => e.code === 'INVALID_IDENTITY')
  assert.equal(f.client.session(),null)
})
for (const change of ['switch','renew']) test('late exchange after '+change+' cannot save a session', async () => {
  let resolve
  const f = setup(() => new Promise(r => {resolve=r}))
  const pending = f.client.exchange()
  f[change](); resolve(response())
  await assert.rejects(pending, e => e.code === 'SESSION_CHANGED')
  assert.equal(f.client.session(),null)
})
test('explicit member credentials and create-member prompts cannot create another login path', async () => {
  const f = setup(() => response())
  for (const value of [{create_member:true}, {account:'legacy',password:'synthetic'}])
    await assert.rejects(f.client.exchange(value), e => e.code === 'AUTOMATIC_IDENTITY_REQUIRED')
  assert.equal(f.calls.length,0)
})
