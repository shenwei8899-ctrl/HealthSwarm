import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { ref } from 'vue'
import { canUseLocalBusinessLogin, canUseH5TestBusinessLogin } from '../src/services/local-login-policy.js'
import { createBusinessAuthClient } from '../src/services/business-auth-client.js'
import { createEntryResolver } from '../src/services/entry-routing.js'

const local = { VITE_LOCAL_BUSINESS_LOGIN: '1', VITE_SERVICE_MODE: 'api',
  VITE_ALLOW_LOCAL_HEALTH_API: '1', VITE_API_BASE_URL: 'http://127.0.0.1:15050' }

test('H5 test login is opt-in, same-origin and unavailable to mini-program or another site', () => {
  const env = { VITE_H5_TEST_LOGIN: '1', VITE_SERVICE_MODE: 'api', VITE_API_BASE_URL: '',
    VITE_H5_TEST_ORIGIN: 'http://8.136.134.29' }
  const runtime = { h5: true, origin: 'http://8.136.134.29' }
  assert.equal(canUseH5TestBusinessLogin(env, runtime), true)
  for (const change of [{ h5: false }, { origin: '' }, { origin: 'http://8.136.134.29:8080' },
    { origin: 'https://8.136.134.29' }, { origin: 'http://8.136.134.29.evil.test' }]) {
    assert.equal(canUseH5TestBusinessLogin(env, { ...runtime, ...change }), false)
  }
  for (const change of [{ VITE_H5_TEST_LOGIN: undefined }, { VITE_H5_TEST_LOGIN: '0' },
    { VITE_SERVICE_MODE: 'mock' }, { VITE_API_BASE_URL: 'https://elsewhere.test' },
    { VITE_API_BASE_URL: 'http://127.0.0.1:15050' }, { VITE_API_BASE_URL: undefined },
    { VITE_H5_TEST_ORIGIN: undefined }]) {
    assert.equal(canUseH5TestBusinessLogin({ ...env, ...change }, runtime), false)
  }
  for (const origin of ['null', 'file://', 'http://example.com/path', 'http://user:pass@example.com', 'http://example.com/']) {
    assert.equal(canUseH5TestBusinessLogin({ ...env, VITE_H5_TEST_ORIGIN: origin }, { h5: true, origin }), false)
  }
  assert.equal(canUseLocalBusinessLogin({ ...env, VITE_LOCAL_BUSINESS_LOGIN: '1' }, { platform: 'devtools' }), false)
  assert.equal(canUseH5TestBusinessLogin({ ...env, VITE_H5_TEST_ORIGIN: 'https://test.example.com' },
    { h5: true, origin: 'https://test.example.com' }), true)
})
test('business login requires explicit local configuration and Developer Tools or localhost', () => {
  assert.equal(canUseLocalBusinessLogin(local, { platform: 'devtools' }), true)
  assert.equal(canUseLocalBusinessLogin(local, { hostname: 'localhost' }), true)
  for (const runtime of [{ platform: 'ios' }, { platform: 'android' }, { hostname: 'example.com' }, {}]) {
    assert.equal(canUseLocalBusinessLogin(local, runtime), false)
  }
  for (const change of [{ VITE_LOCAL_BUSINESS_LOGIN: '0' }, { VITE_LOCAL_BUSINESS_LOGIN: undefined },
    { VITE_API_BASE_URL: 'https://api.example.com' }, { VITE_API_BASE_URL: 'http://127.0.0.1.evil.test' },
    { VITE_SERVICE_MODE: 'mock' }, { VITE_ALLOW_LOCAL_HEALTH_API: '0' }]) {
    assert.equal(canUseLocalBusinessLogin({ ...local, ...change }, { platform: 'devtools' }), false)
  }
})

function harness(send) {
  let stored = null, revision = 0
  const session = { read: () => stored, revision: () => revision,
    clear: () => { stored = null; revision++ },
    save(value, options = {}) {
      if (!options.preserveRevision || !stored || ['accountId', 'token', 'householdId', 'authSource'].some(key => stored[key] !== value[key])) revision++
      stored = structuredClone(value)
    } }
  const calls = []
  const auth = createBusinessAuthClient({ session, send: async options => {
    calls.push(options)
    return { data: await send(options) }
  } })
  return { session, auth, calls }
}
const answer = options => options.path === '/api/auth/token' ? { user_id: 25, access_token: 'verified-business-token' }
  : options.path === '/api/auth/me' ? { id: 25, username: '联调用户' } : [{ id: 'own-family', name: '测试家庭', is_owner: true }]

test('business token reaches the real entry decision and repeated foreground reads preserve request scope', async () => {
  const h = harness(answer)
  await h.auth.login('test-user', 'private&password')
  const resolve = createEntryResolver({ auth: h.auth, session: h.session.read,
    readProfile: async () => ({ householdId: 'own-family', onboarded: true }) })
  assert.equal(await resolve(), '/pages/chat/index')
  const revision = h.session.revision()
  await Promise.all([h.auth.restore(), h.auth.restore()])
  assert.equal(h.session.revision(), revision)
  assert.equal(h.session.read().authSource, 'business')
  assert.equal(h.session.read().isDemo, false)
  assert.equal(h.session.read().password, undefined)
  assert.equal(h.calls.some(call => call.path.includes('/wechat/')), false)
  assert.equal(h.calls[0].data, 'username=test-user&password=private%26password')
  await assert.rejects(h.auth.selectFamily('someone-elses-family'))
  assert.equal(h.session.read().householdId, 'own-family')
})

test('new business user goes to onboarding; wrong credentials and late responses never create a session', async () => {
  const empty = harness(options => options.path === '/api/family' ? [] : answer(options))
  await empty.auth.login('test-user', 'password')
  assert.equal(await createEntryResolver({ auth: empty.auth, session: empty.session.read, readProfile: () => assert.fail() })(), '/pages/onboarding/index')
  const wrong = harness(() => { throw Object.assign(new Error('账号或密码错误'), { code: 401 }) })
  await assert.rejects(wrong.auth.login('test-user', 'wrong-password'))
  assert.equal(wrong.session.read(), null)
  let release
  const late = harness(() => new Promise(resolve => { release = resolve }))
  const pending = late.auth.login('test-user', 'password')
  late.auth.logout(); release({ user_id: 25, access_token: 'late-token' })
  await assert.rejects(pending, error => error.code === 'SESSION_CHANGED')
  assert.equal(late.session.read(), null)
})

test('local welcome submits credentials, clears password and enters the server-selected page', async () => {
  const calls = [], redirects = []
  const deps = { ref, onShow() {}, onHide() {}, onUnload() {}, isMockMode: false, canUseBusinessLogin: true, isCommerceEnabled: false, phoneBindingDemo: false,
    getSession: () => null, wechatAuth: { cancelPending() {} },
    service: { login: async data => calls.push(data) }, resolveAppEntry: async () => '/pages/onboarding/index' }
  globalThis.uni = { reLaunch: options => { redirects.push(options.url); options.success?.({errMsg:'reLaunch:ok'}) } }
  const source = readFileSync(new URL('../src/pages/index/index.vue', import.meta.url), 'utf8')
  const code = source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  const page = new Function('deps', `const {${Object.keys(deps)}}=deps;${code};return {start,continueLogin,identifier,password,loginOpen}`)(deps)
  page.start(); assert.equal(page.loginOpen.value, true)
  page.identifier.value = 'test-user'; page.password.value = 'secret'
  await page.continueLogin()
  assert.deepEqual(calls, [{ identifier: 'test-user', password: 'secret' }])
  assert.equal(page.password.value, '')
  assert.deepEqual(redirects, ['/pages/onboarding/index'])
})

test('H5 test login accepts only explicitly listed IP and HTTPS origins', () => {
  const env = { VITE_H5_TEST_LOGIN: '1', VITE_SERVICE_MODE: 'api', VITE_API_BASE_URL: '',
    VITE_H5_TEST_ORIGINS: 'http://8.136.134.29, https://h5.example.test' }
  for (const origin of ['http://8.136.134.29', 'https://h5.example.test']) {
    assert.equal(canUseH5TestBusinessLogin(env, { h5: true, origin }), true)
    assert.equal(canUseH5TestBusinessLogin(env, { h5: false, origin }), false)
    assert.equal(canUseH5TestBusinessLogin({ ...env, VITE_H5_TEST_LOGIN: '0' }, { h5: true, origin }), false)
  }
  for (const origin of ['https://unlisted.test', 'http://8.136.134.29:8080', 'https://h5.example.test.evil.test', 'http://h5.example.test']) {
    assert.equal(canUseH5TestBusinessLogin(env, { h5: true, origin }), false)
  }
})

test('an H5 test origin list cannot accept paths, credentials, or a non-web origin', () => {
  for (const origin of ['file://', 'null', 'https://test.example/path', 'https://user:pass@test.example', 'https://test.example/']) {
    assert.equal(canUseH5TestBusinessLogin({ VITE_H5_TEST_LOGIN: '1', VITE_SERVICE_MODE: 'api', VITE_API_BASE_URL: '',
      VITE_H5_TEST_ORIGINS: origin }, { h5: true, origin }), false)
  }
})
