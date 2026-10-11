import test from 'node:test'
import assert from 'node:assert/strict'
import { createWechatAuthClient, projectLogin } from '../src/services/wechat-auth-client.js'
import { selfMember, basicProfileInput } from '../src/services/family-onboarding.js'
import { readFileSync } from 'node:fs'
import { ref, computed } from 'vue'

const context = { account: { id: 17, name: '合成用户' }, families: [] }
const loginResult = { ...context, access_token: 'synthetic-token', expires_at: Date.now() / 1000 + 300, session_key: 'must-not-store', openid: 'must-not-store' }
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

function accountPage(overrides = {}) {
  let stored = { accountId: '17', token: 'synthetic-token', householdId: 'own' }, revision = 0
  const profile = { sex: 'female', birth_date: '1996-01-01', height_cm: 165, activity_level: 'light', goal: '规律饮食' }
  const own = { id: 'self', is_self: true, is_active: true, version: 2, confirmed: false, ready: false, profile }
  const family = { id: 'own', members: [own] }, calls = [], redirects = []
  let hide, show
  globalThis.uni = { reLaunch: options => redirects.push(options.url) }
  const deps = { ref, computed, selfMember, basicProfileInput, getSession: () => stored, sessionRevision: () => String(revision),
    wechatAuth: { restore: async () => { revision++; return { ...stored, families: [{ id: 'own', name: '合成家庭' }] } }, cancelPending() {}, logout() { stored = null; revision++ } },
    request: async options => { calls.push(options); return { data: family } },
    onShow: callback => { show = callback }, onHide: callback => { hide = callback }, onUnload() {}, ...overrides }
  const source = readFileSync(new URL('../src/pages/account/index.vue', import.meta.url), 'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  const page = new Function('deps', `const {${Object.keys(deps).join(',')}} = deps;\n${source}\nreturn { member, form, account, busy, uncertain, error, unsaved, save, confirm, load, createFamily, familyName }`)(deps)
  return { ...page, show: () => show(), hide: () => hide(), calls, redirects, family, expire: () => { stored = null; revision++ } }
}

test('actual account page confirms only the saved version and sends only own basic fields', async () => {
  const page = accountPage(); await page.show(); page.form.value.goal = '新目标'
  await page.confirm(); assert.equal(page.calls.length, 1)
  await page.save(); const saved = page.calls.find(call => call.method === 'PUT')
  assert.equal(saved.data.expected_version, 2); assert.equal(saved.data.profile.goal, '新目标')
  assert.equal(saved.path, '/api/family/own/members/self')
  await page.confirm(); assert.equal(page.calls.find(call => call.method === 'POST').data.expected_version, 2)
})

test('unknown family write blocks repeat writes until a fresh server read', async () => {
  let writes = 0; const page = accountPage({ request: async options => {
    if (options.method) { writes++; throw Object.assign(new Error('timeout'), { code: 'NETWORK_ERROR' }) }
    return { data: { id: 'own', members: [] } }
  } })
  await page.show(); page.familyName.value = '合成家庭'; await page.createFamily()
  assert.equal(page.uncertain.value, true); assert.equal(page.busy.value, false)
  await page.createFamily(); assert.equal(writes, 1)
  await page.load(); assert.equal(page.uncertain.value, false)
})

test('hiding the account page prevents late private profile data from returning', async () => {
  let release; const page = accountPage({ request: () => new Promise(resolve => { release = resolve }) })
  const pending = page.show(); await new Promise(resolve => setImmediate(resolve)); page.hide()
  release({ data: page.family }); await pending
  assert.equal(page.member.value, null); assert.deepEqual(page.form.value, {}); assert.equal(page.account.value, null)
})

test('write 401 clears private account state even after transport changes the session revision', async () => {
  let page; page = accountPage({ request: async options => {
    if (options.method) { page.expire(); throw Object.assign(new Error('expired'), { code: 401 }) }
    return { data: page.family }
  } })
  await page.show(); await page.save()
  assert.equal(page.member.value, null); assert.equal(page.account.value, null); assert.equal(page.busy.value, false)
  assert.deepEqual(page.redirects, ['/pages/index/index'])
})

test('registered launch route remains the welcome page', () => {
  const pages = JSON.parse(readFileSync(new URL('../src/pages.json', import.meta.url), 'utf8'))
  assert.equal(pages.pages[0].path, 'pages/index/index')
})

test('closing and reopening binding form preserves access without retaining its password', async () => {
  const deps = { ref, onShow() {}, onHide() {}, onUnload() {}, isMockMode: false, getSession: () => null,
    wechatAuth: { cancelPending() {} }, mockService: { login: async () => { throw Object.assign(new Error('请绑定账号'), { businessCode: 'WECHAT_ACCOUNT_UNBOUND' }) } } }
  globalThis.uni = { showToast() {} }
  const source = readFileSync(new URL('../src/pages/index/index.vue', import.meta.url), 'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  const page = new Function('deps', `const {${Object.keys(deps).join(',')}} = deps;\n${source}\nreturn { continueLogin, start, closeLoginSheet, loginOpen, password, needsBinding }`)(deps)
  await page.continueLogin(); assert.equal(page.loginOpen.value, true)
  page.password.value = 'synthetic-password'; page.closeLoginSheet()
  assert.equal(page.password.value, ''); assert.equal(page.loginOpen.value, false)
  page.start(); assert.equal(page.loginOpen.value, true)
})
