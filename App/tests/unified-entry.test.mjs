import test from 'node:test'
import assert from 'node:assert/strict'
import { createBusinessAuthClient } from '../src/services/business-auth-client.js'
import { createCommerceClient } from '../src/services/commerce-client.js'

function directMember() {
  let family = null, scope = 'guest', expired = false, rejected = false, release
  const values = new Map(), calls = []
  let delay = false, revision = 0
  const client = createCommerceClient({ baseUrl: 'http://127.0.0.1:15050', authMode: 'agent',
    parent: { read: () => family, scope: () => scope },
    storage: { get: key => values.get(key), set: (key, value) => values.set(key, value) },
    randomKey: () => 'member-' + (++revision),
    transport: async options => {
      calls.push(options)
      if (delay) await new Promise(resolve => { release = resolve })
      if (rejected || expired) return { statusCode: 401, data: { code: 40100, message: '账号或密码错误' } }
      const data = options.url.endsWith('/session/login') ? { user: { id: 23, token: 'synthetic-member-token' } }
        : options.url.endsWith('/session') ? { user: { id: 23 } } : { items: [] }
      return { statusCode: 200, data: { code: 0, data } }
    } })
  return { client, calls, family: () => family, values,
    expire: () => { expired = true }, reject: () => { rejected = true },
    delay: () => { delay = true }, release: () => release(),
    switchFamily: () => { family = { accountId: '17', token: 'agent-token' }; scope = 'family-17' } }
}

test('homepage member login works without AppID or Agent login and restores the same member cart', async () => {
  const h = directMember()
  await h.client.loginMember({ account: ' member ', password: 'synthetic-password' })
  assert.equal(h.family(), null)
  assert.equal(h.client.isMemberLogin(), true)
  assert.equal(h.client.session().userId, '23')
  assert.equal(h.client.session().agentAccountId, undefined)
  assert.deepEqual(h.calls[0].data, { account: 'member', password: 'synthetic-password' })
  assert.match(h.calls[0].url, /\/session\/login$/)
  await h.client.restore(); await h.client.cart()
  assert.equal(h.calls.at(-1).header.token, 'synthetic-member-token')
  assert.equal(h.calls.some(call => call.url.endsWith('/exchange')), false)
  assert.equal(JSON.stringify([...h.values]).includes('synthetic-password'), false)
  h.expire()
  await assert.rejects(h.client.restore(), error => Number(error.code) === 401)
  assert.equal(h.client.session(), null)
  assert.equal(h.client.isMemberLogin(), true)
  await assert.rejects(h.client.cart(), error => Number(error.code) === 401)
  assert.equal(h.calls.some(call => call.url.endsWith('/exchange')), false)
})

test('failed or cancelled homepage login never creates a commerce session', async () => {
  const bad = directMember(); bad.reject()
  await assert.rejects(bad.client.loginMember({ account: 'member', password: 'bad' }))
  assert.equal(bad.client.session(), null)
  assert.equal(bad.family(), null)
  const pending = directMember(); pending.delay()
  const login = pending.client.loginMember({ account: 'member', password: 'synthetic-password' })
  pending.client.cancelLogin(); pending.release()
  await assert.rejects(login, error => error.code === 'SESSION_CHANGED')
  assert.equal(pending.client.session(), null)
  assert.equal(pending.client.isMemberLogin(), false)
})

test('entering a family account cannot reuse a directly authenticated member session', async () => {
  const h = directMember()
  await h.client.loginMember({ account: 'member', password: 'synthetic-password' })
  h.switchFamily()
  assert.equal(h.client.session(), null)
  assert.equal(h.client.isMemberLogin(), false)
})

function clients() {
  let stored = null, revision = 0, intent = 0
  const values = new Map(), exchanges = [], reads = []
  const session = {
    read: () => stored,
    save: value => { stored = value; revision++ },
    clear: () => { stored = null; revision++ },
    revision: () => revision,
  }
  const business = createBusinessAuthClient({ session, send: async options => {
    reads.push(options)
    if (options.path === '/api/auth/token') return { data: { user_id: 17, access_token: 'synthetic-agent-17' } }
    if (options.path === '/api/auth/me') return { data: { id: 17, username: 'synthetic' } }
    return { data: [{ id: 'family-1', name: '合成家庭', is_owner: true }] }
  } })
  const commerce = createCommerceClient({ baseUrl: '/commerce-api', allowProxy: true, authMode: 'agent',
    parent: { read: session.read, scope: () => stored?.accountId + ':' + revision },
    storage: { get: key => values.get(key), set: (key, value) => values.set(key, value) },
    randomKey: () => 'synthetic-intent-' + (++intent),
    transport: async options => {
      exchanges.push(options)
      return { statusCode: 200, data: { code: 0, data: options.url.endsWith('/exchange')
        ? { agent_account_id: '17', user: { id: 23, token: 'synthetic-mall-23' } }
        : { items: [] } } }
    } })
  return { business, commerce, session, exchanges, reads }
}

test('existing family login opens the unified cart without requesting another password', async () => {
  const h = clients()
  await h.business.login('synthetic', 'synthetic-password')
  await h.business.selectFamily('family-1')
  await h.commerce.cart()
  assert.equal(h.session.read().householdId, 'family-1')
  assert.equal(h.exchanges[0].header.Authorization, 'Bearer synthetic-agent-17')
  assert.deepEqual(h.exchanges[0].data, {})
  assert.equal(h.exchanges[1].header.token, 'synthetic-mall-23')
  assert.equal(h.reads.filter(row => row.path === '/api/auth/token').length, 1)
  assert.equal(JSON.stringify(h.session.read()).includes('synthetic-password'), false)
  assert.equal(h.commerce.session().userId, '23')
})

test('logging out of the family account invalidates access to its linked cart', async () => {
  const h = clients()
  await h.business.login('synthetic', 'synthetic-password')
  await h.commerce.cart()
  h.business.cancelPending(); h.session.clear()
  assert.equal(h.commerce.session(), null)
  const before = h.exchanges.length
  await assert.rejects(h.commerce.cart(), error => Number(error.code) === 401)
  assert.equal(h.exchanges.length, before)
})
