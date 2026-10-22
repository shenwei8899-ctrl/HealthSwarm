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

function accountPage(overrides = {}) {
  let stored = { accountId: '17', token: 'synthetic-token', householdId: 'own' }, revision = 0
  const profile = { sex: 'female', birth_date: '1996-01-01', height_cm: 165, activity_level: 'light', goal: '规律饮食' }
  const own = { id: 'self', is_self: true, is_active: true, version: 2, confirmed: false, ready: false, profile }
  const family = { id: 'own', members: [own] }, calls = [], redirects = [], navigation = []
  let hide, show
  globalThis.uni = { reLaunch: options => redirects.push(options.url), navigateTo: options => navigation.push(options.url) }
  const deps = { ref, computed, selfMember, basicProfileInput, getSession: () => stored, sessionRevision: () => String(revision),
    wechatAuth: { restore: async () => { revision++; return { ...stored, families: [{ id: 'own', name: '合成家庭' }] } }, cancelPending() {}, logout() { stored = null; revision++ } },
    request: async options => { calls.push(options); return { data: family } },
    onMounted() {}, onShow: callback => { show = callback }, onHide: callback => { hide = callback }, onUnload() {}, ...overrides }
  const source = readFileSync(new URL('../src/components/SelfAccountDetails.vue', import.meta.url), 'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  const page = new Function('deps', `const {${Object.keys(deps).join(',')}} = deps;\n${source}\nreturn { member, form, account, busy, uncertain, error, unsaved, save, confirm, load, createFamily, familyName, healthMembers, selectedHealthId, healthLink, healthError, healthUncertain, healthDiagnostics, healthEntries, healthEntryText, openHealthTask, readHealthMembers, selectHealthMember, readHealthDiagnostics, createHealthMember, linkSelfProfile }`)(deps)
  return { ...page, show: () => show(), hide: () => hide(), calls, redirects, navigation, family, expire: () => { stored = null; revision++ } }
}

test('actual self-profile panel confirms only the saved version and sends only own basic fields', async () => {
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

test('health member link requires explicit selection and re-reads the confirmed self IDs', async () => {
  const id = '11111111-1111-4111-8111-111111111111'
  const calls = []; let linked = false
  const page = accountPage({ request: async options => {
    calls.push(options)
    if (options.path === '/api/health/v1/members') return { data: [{ id, display_name: '本人', relationship_label: '本人', is_owner: true }] }
    if (options.path.endsWith('/family-profile-link')) {
      if (options.method === 'POST') { linked = true; return { data: { member_id: id, family_id: 'own', source_member_id: 'self' } } }
      return { data: linked ? { member_id: id, family_id: 'own', source_member_id: 'self' } : { member_id: id, source_member_id: null } }
    }
    return { data: { id: 'own', members: [{ id: 'self', is_self: true, is_active: true, version: 2, confirmed: true, ready: true, profile: {} }] } }
  } })
  await page.show(); await page.readHealthMembers()
  assert.equal(calls.some(call => call.method === 'POST'), false)
  assert.equal(page.selectedHealthId.value, '')
  await page.selectHealthMember(id); await page.linkSelfProfile()
  assert.deepEqual(calls.find(call => call.method === 'POST').data, { family_id: 'own', source_member_id: 'self', confirmed_identity: true })
  assert.equal(page.healthLink.value.source_member_id, 'self')
})

test('unknown health member creation blocks another create until members are read', async () => {
  let writes = 0
  const page = accountPage({ request: async options => {
    if (options.path === '/api/health/v1/members' && options.method === 'POST') {
      writes++; throw Object.assign(new Error('timeout'), { code: 'NETWORK_ERROR' })
    }
    if (options.path === '/api/health/v1/members') return { data: [] }
    return { data: { id: 'own', members: [{ id: 'self', is_self: true, is_active: true, version: 2, confirmed: true, ready: true, profile: {} }] } }
  } })
  await page.show(); await page.createHealthMember(); await page.createHealthMember()
  assert.equal(writes, 1); assert.equal(page.healthUncertain.value, true)
  await page.readHealthMembers(); assert.equal(page.healthUncertain.value, false)
})

test('health status uses both server diagnostics and never treats basic ready as task readiness', async () => {
  const id = '11111111-1111-4111-8111-111111111111'
  const page = accountPage({ request: async options => {
    if (options.path === '/api/health/v1/members') return { data: [{ id, display_name: '本人', relationship_label: '本人', is_owner: true }] }
    if (options.path.endsWith('/capabilities')) return { data: { member_id: id, tasks: [{ task_type: 'consultation', status: 'needs_input' }] } }
    if (options.path.endsWith('/readiness')) return { data: { capabilities: { member_id: id }, entries: [
      { entry_type: 'consultation', status: 'needs_input', reason_code: 'consent_required' },
      { entry_type: 'blood_glucose_review', status: 'available' },
      { entry_type: 'glucose_plan', status: 'unavailable', reason_code: 'external_contract_required' },
    ] } }
    if (options.path.endsWith('/family-profile-link')) return { data: { member_id: id, source_member_id: null } }
    return { data: { id: 'own', members: [{ id: 'self', is_self: true, is_active: true, version: 2, confirmed: true, ready: true, profile: {} }] } }
  } })
  await page.show(); assert.equal(page.healthDiagnostics.value, null)
  await page.readHealthMembers(); await page.selectHealthMember(id); await page.readHealthDiagnostics()
  assert.deepEqual(page.healthEntries.value.map(entry => [entry.entry_type, entry.status]), [
    ['consultation', 'needs_input'], ['blood_glucose_review', 'available'], ['glucose_plan', 'unavailable'],
  ])
  assert.match(page.healthEntryText(page.healthEntries.value[0]), /数据处理同意/)
  assert.match(page.healthEntryText(page.healthEntries.value[2]), /功能尚未开放/)
  assert.match(page.healthEntryText({ status: 'unavailable', reason_code: 'dependency_not_ready', missing_dependencies: ['worker'] }), /服务暂不可用/)
  assert.match(page.healthEntryText({ status: 'unavailable', reason_code: 'dependency_not_ready', missing_dependencies: ['nutrition'] }), /专业资料未就绪/)
})

test('health status rejects a diagnostic response for another member', async () => {
  const id = '11111111-1111-4111-8111-111111111111'
  const page = accountPage({ request: async options => {
    if (options.path === '/api/health/v1/members') return { data: [{ id, display_name: '本人', relationship_label: '本人', is_owner: true }] }
    if (options.path.endsWith('/capabilities')) return { data: { member_id: id } }
    if (options.path.endsWith('/readiness')) return { data: { capabilities: { member_id: 'other' }, entries: [] } }
    if (options.path.endsWith('/family-profile-link')) return { data: { member_id: id, source_member_id: null } }
    return { data: { id: 'own', members: [{ id: 'self', is_self: true, is_active: true, version: 2, confirmed: true, ready: true, profile: {} }] } }
  } })
  await page.show(); await page.readHealthMembers(); await page.selectHealthMember(id); await page.readHealthDiagnostics()
  assert.equal(page.healthDiagnostics.value, null)
  assert.match(page.healthError.value, /成员诊断不一致/)
})

test('incomplete basic profile does not hide an authorized education task', async () => {
  const id = '11111111-1111-4111-8111-111111111111'
  const page = accountPage({ request: async options => {
    if (options.path === '/api/health/v1/members') return { data: [{ id, display_name: '本人', is_owner: true }] }
    if (options.path.endsWith('/capabilities')) return { data: { member_id: id } }
    if (options.path.endsWith('/readiness')) return { data: { capabilities: { member_id: id }, entries: [
      { entry_type: 'consultation', status: 'available' }, { entry_type: 'glucose_plan', status: 'unavailable' },
    ] } }
    if (options.path.endsWith('/family-profile-link')) return { data: { member_id: id, source_member_id: null } }
    return { data: page.family }
  } })
  await page.show()
  assert.equal(page.member.value.ready, false)
  await page.readHealthMembers(); await page.selectHealthMember(id); await page.readHealthDiagnostics()
  page.openHealthTask(page.healthEntries.value[0]); page.openHealthTask(page.healthEntries.value[1])
  assert.deepEqual(page.navigation, [`/pages/chat/agent?memberId=${id}&taskType=consultation`])
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

test('formal welcome has only WeChat entry and displays automatic registration errors without a binding form', async () => {
  const deps = { ref, onShow() {}, onHide() {}, onUnload() {}, isMockMode: false, canUseBusinessLogin: false, getSession: () => null,
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

test('self-profile mount and show share restoration without invalidating their own session', async () => {
  const page=accountPage()
  await Promise.all([page.show(),page.show()])
  assert.equal(page.calls.filter(call=>call.path==='/api/family/own').length,1)
  assert.equal(page.error.value,'')
  assert.equal(page.member.value.id,'self')
})
