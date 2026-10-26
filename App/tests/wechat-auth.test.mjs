import test from 'node:test'
import assert from 'node:assert/strict'
import { createWechatAuthClient, projectLogin } from '../src/services/wechat-auth-client.js'
import { selfMember, basicProfileInput } from '../src/services/family-onboarding.js'
import { readFileSync } from 'node:fs'
import { ref, computed } from 'vue'

const context = { wechat_authenticated: true, account: { id: 17, name: '合成用户' }, families: [] }
const loginResult = { ...context, access_token: 'synthetic-token', expires_at: Date.now() / 1000 + 300, session_key: 'must-not-store', openid: 'must-not-store' }

test('local password login validates the real Agent session before saving and does not retain credentials', async () => {
  const h = harness({ isWechat: false, allowPasswordLogin: true })
  h.replies.push({ access_token: 'agent-token', user_id: 17 }, context)
  await h.client.passwordLogin({ identifier: ' user ', password: 'a&b' })
  assert.equal(h.calls[0].data, 'username=user&password=a%26b')
  assert.equal(h.calls[1].authenticationToken, 'agent-token')
  assert.equal(h.session.read().accountId, '17')
  assert.equal(h.session.read().password, undefined)
})
test('password login is disabled by default and cannot be used on WeChat', async () => {
  for (const options of [{ isWechat: false }, { isWechat: true, allowPasswordLogin: true }]) {
    const h = harness(options)
    await assert.rejects(h.client.passwordLogin({ identifier: 'user', password: 'secret' }), e => e.code === 'PASSWORD_LOGIN_DISABLED')
    assert.equal(h.calls.length, 0)
  }
})
test('password login rejects context mismatch, unavailable context and late account changes', async () => {
  for (const reply of [{ account: { id: 18 }, families: [] }, new Error('unavailable')]) {
    const h = harness({ isWechat: false, allowPasswordLogin: true })
    h.replies.push({ access_token: 'agent-token', user_id: 17 }, reply)
    await assert.rejects(h.client.passwordLogin({ identifier: 'user', password: 'secret' }))
    assert.equal(h.session.read(), null)
  }
  let release
  const h = harness({ isWechat: false, allowPasswordLogin: true, send: async r => r.path.endsWith('/token') ? { data: { access_token: 'agent-token', user_id: 17 } } : new Promise(resolve => { release = resolve }) })
  const pending = h.client.passwordLogin({ identifier: 'user', password: 'secret' })
  await new Promise(resolve => setImmediate(resolve)); h.client.logout(); release({ data: context })
  await assert.rejects(pending, e => e.code === 'SESSION_CHANGED'); assert.equal(h.session.read(), null)
})
function harness(options = {}) {
  let stored = null, revision = 0, codes = 0
  const calls = [], replies = []
  const session = { read: () => stored, save: value => { stored = structuredClone(value); revision++ }, clear: () => { stored = null; revision++ }, revision: () => String(revision) }
  const client = createWechatAuthClient({ session, isWechat: true, appId: 'wx1234567890abcdef',
    getCode: async () => 'fresh-code-' + (++codes),
    send: async request => { calls.push(request); const reply = replies.shift(); if (reply instanceof Error) throw reply; return { data: reply ?? (request.path.endsWith('/config') ? { available: true, appid: 'wx1234567890abcdef' } : request.path.endsWith('/login') ? loginResult : context) } }, ...options })
  return { client, session, calls, replies, codes: () => codes }
}
test('new WeChat users store business identity without requiring a household or storing WeChat secrets', async () => {
  const h = harness(); const result = await h.client.login()
  assert.equal(result.accountId, '17'); assert.equal(result.householdId, null)
  assert.equal(h.session.read().token, 'synthetic-token'); assert.equal(h.session.read().session_key, undefined); assert.equal(h.session.read().openid, undefined)
  assert.deepEqual(h.calls[1].data, { code: 'fresh-code-1' }); assert.equal(h.calls[1].authenticated, false)
})
test('H5, missing AppID and backend AppID mismatch never request a WeChat code', async () => {
  for (const options of [{ isWechat: false }, { appId: '' }]) {
    const h = harness(options); await assert.rejects(h.client.login()); assert.equal(h.codes(), 0); assert.equal(h.session.read(), null)
  }
  const h = harness(); h.replies.push({ available: true, appid: 'wx0000000000000000' })
  await assert.rejects(h.client.login(), e => e.code === 'WECHAT_NOT_CONFIGURED'); assert.equal(h.codes(), 0)
})
test('unconfigured backend does not fall back to a demo identity', async () => {
  const h = harness(); h.replies.push({ available: false }); await assert.rejects(h.client.login()); assert.equal(h.codes(), 0); assert.equal(h.session.read(), null)
})
test('explicit retry obtains a fresh WeChat code and never persists binding passwords', async () => {
  const h = harness(); h.replies.push({ available: true, appid: 'wx1234567890abcdef' }, new Error('response lost'))
  await assert.rejects(h.client.login({ identifier: 'synthetic-user', password: 'synthetic-password' }))
  assert.equal(h.session.read(), null); await h.client.login({ identifier: 'synthetic-user', password: 'synthetic-password' })
  assert.equal(h.calls[3].data.code, 'fresh-code-2'); assert.equal(h.session.read().password, undefined)
})
test('logout while credential exchange is pending prevents a late session from being restored', async () => {
  let release; const h = harness({ getCode: () => new Promise(resolve => { release = resolve }) })
  const pending = h.client.login(); await new Promise(resolve => setImmediate(resolve)); h.client.logout(); release('late-code')
  await assert.rejects(pending, e => e.code === 'SESSION_CHANGED'); assert.equal(h.session.read(), null); assert.equal(h.calls.length, 1)
})
test('account changes during POST do not overwrite the newer account', async () => {
  let release; const h = harness({ send: async request => request.path.endsWith('/config') ? { data: { available: true, appid: 'wx1234567890abcdef' } } : new Promise(resolve => { release = resolve }) })
  const pending = h.client.login(); await new Promise(resolve => setImmediate(resolve)); h.session.save({ accountId: 'new-account', token: 'new-token' }); release({ data: loginResult })
  await assert.rejects(pending, e => e.code === 'SESSION_CHANGED'); assert.equal(h.session.read().token, 'new-token')
})
test('restoring a revoked household removes its selection and reads no local onboarding flag', async () => {
  const h = harness(); h.session.save({ accountId: '17', token: 'synthetic-token', householdId: 'revoked' })
  const result = await h.client.restore(); assert.equal(result.householdId, null); assert.deepEqual(result.families, [])
})
test('session identity mismatch clears credentials and cannot select another account family', async () => {
  const h = harness(); h.session.save({ accountId: '18', token: 'synthetic-token' })
  await assert.rejects(h.client.restore(), e => e.code === 'SESSION_IDENTITY_CHANGED'); assert.equal(h.session.read(), null)
})
test('transient session validation failure preserves credentials for explicit retry', async () => {
  const h = harness(); h.session.save({ accountId: '17', token: 'synthetic-token' }); h.replies.push(new Error('timeout'))
  await assert.rejects(h.client.restore()); assert.equal(h.session.read().token, 'synthetic-token')
})
test('family selection only accepts the server current authorized list', async () => {
  const h = harness(); h.session.save({ accountId: '17', token: 'synthetic-token' })
  h.replies.push({ ...context, families: [{ id: 'own', name: '合成家庭', is_owner: true, onboarding_required: true }] })
  assert.equal((await h.client.selectFamily('own')).householdId, 'own')
  await assert.rejects(h.client.selectFamily('stranger')); assert.equal(h.session.read().householdId, null)
})
test('invalid login envelopes never become sessions', () => {
  for (const data of [{ ...loginResult, access_token: '' }, { ...loginResult, expires_at: 1 }, { ...loginResult, account: { id: '17' } }, { ...loginResult, families: [{}] }]) assert.throws(() => projectLogin(data))
})
test('onboarding projects only the current user basic fields and keeps unknowns unknown', () => {
  const member = selfMember({ id: 'family', members: [{ id: 'other', is_self: false, profile: { medications: 'private' } }, { id: 'self', is_self: true, is_active: true, version: 2, ready: false, profile: { sex: 'female', medications: 'private' } }] })
  assert.equal(member.id, 'self'); assert.equal(member.profile.medications, undefined); assert.equal(member.profile.height_cm, null)
  assert.deepEqual(basicProfileInput({}), { sex: null, birth_date: null, height_cm: null, activity_level: null, goal: null })
  assert.throws(() => basicProfileInput({ height_cm: 'NaN' })); assert.throws(() => basicProfileInput({ height_cm: '0' }))
})

test('registered launch route remains the welcome page', () => {
  const pages = JSON.parse(readFileSync(new URL('../src/pages.json', import.meta.url), 'utf8'))
  assert.equal(pages.pages[0].path, 'pages/index/index')
})

test('formal welcome has only WeChat entry and displays automatic registration errors without a binding form', async () => {
  const deps = { ref, onShow() {}, onHide() {}, onUnload() {}, isMockMode: false, canUseBusinessLogin: false, isCommerceEnabled: false, getSession: () => null,
    wechatAuth: { cancelPending() {} }, service: { login: async () => { throw new Error('微信注册配置尚未就绪') } } }
  globalThis.uni = { showToast() {} }
  const source = readFileSync(new URL('../src/pages/index/index.vue', import.meta.url), 'utf8')
  const code = source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  const page = new Function('deps', `const {${Object.keys(deps)}}=deps;${code};return {continueLogin,loginOpen,loginError}`)(deps)
  await page.continueLogin()
  assert.equal(page.loginOpen.value, false)
  assert.match(page.loginError.value, /配置尚未就绪/)
  assert.match(source, /v-if="loginOpen && canUseBusinessLogin"/)
  assert.doesNotMatch(source, /CommerceMemberEntry|商城账号登录/)
})
