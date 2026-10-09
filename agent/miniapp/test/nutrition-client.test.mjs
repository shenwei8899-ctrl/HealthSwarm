import test from 'node:test'
import assert from 'node:assert/strict'
import { createNutritionClient } from '../src/services/nutrition-client.js'
import { resolveNutritionApiBase } from '../src/services/runtime.js'

const KEY = 'healthswarm.nutrition.session'
const ACCOUNT_A = { access_token: 'synthetic-token-a', uid: 'member-a', username: '合成用户甲' }
const ACCOUNT_B = { access_token: 'synthetic-token-b', uid: 'member-b', username: '合成用户乙' }
const FAMILY_ID = 'f83238db-a80d-4ac3-8a13-20fa4a65d0fb'
const SOURCE_ID = '337e6e58-270d-45ac-ad36-42c6f8f65d2c'
const HEALTH_ID = '2014b514-9024-4439-99b3-4cb49e14a006'

/** 手动投递协议响应，使网络顺序独立于客户端实现。 */
function harness(stored) {
  const values = new Map(stored ? [[KEY, structuredClone(stored)]] : [])
  const requests = []
  const storage = {
    getStorageSync: (key) => structuredClone(values.get(key)),
    setStorageSync: (key, value) => values.set(key, structuredClone(value)),
    removeStorageSync: (key) => values.delete(key),
  }
  const client = createNutritionClient({ request: (options) => requests.push(options), storage })
  const reply = (index, statusCode, data) => requests[index].success({ statusCode, data })
  return { client, requests, values, reply }
}

async function signIn(state, account = ACCOUNT_A) {
  const result = state.client.login(account.uid, 'synthetic-password')
  state.reply(state.requests.length - 1, 200, account)
  return result
}

test('密码表单正确编码，只持久化服务端最小账号投影', async () => {
  const state = harness()
  const result = state.client.login('  member+测试@example.cn  ', 'a&b= c+中文')
  assert.equal(state.requests[0].url, '/api/auth/token')
  assert.equal(state.requests[0].method, 'POST')
  assert.equal(state.requests[0].timeout, 15000)
  assert.equal(state.requests[0].header['Content-Type'], 'application/x-www-form-urlencoded')
  assert.equal(state.requests[0].header.Authorization, undefined)
  assert.equal(state.requests[0].data, 'username=member%2B%E6%B5%8B%E8%AF%95%40example.cn&password=a%26b%3D%20c%2B%E4%B8%AD%E6%96%87')
  state.reply(0, 200, { ...ACCOUNT_A, user_id: 7, phone_number: 'synthetic', family: { secret: 'not-stored' } })
  assert.deepEqual(await result, ACCOUNT_A)
  assert.deepEqual(state.values.get(KEY), ACCOUNT_A)
  const copied = state.client.getSession()
  copied.uid = 'tampered'
  assert.deepEqual(state.client.getSession(), ACCOUNT_A)
  assert.equal(JSON.stringify([...state.values]).includes('a&b='), false)
})

test('恢复会话经me验证，返回最新显示名；存储凭据不提前开放业务', async () => {
  const state = harness(ACCOUNT_A)
  assert.equal(state.client.getSession(), null)
  await assert.rejects(state.client.listFamilies(), { code: 'login_required' })
  const result = state.client.restoreSession()
  assert.equal(state.requests[0].url, '/api/auth/me')
  assert.equal(state.requests[0].header.Authorization, 'Bearer synthetic-token-a')
  assert.equal(state.client.getSession(), null)
  state.reply(0, 200, { uid: ACCOUNT_A.uid, username: '合成显示名更新', role: 'user' })
  assert.deepEqual(await result, { ...ACCOUNT_A, username: '合成显示名更新' })
  assert.deepEqual(state.values.get(KEY), { ...ACCOUNT_A, username: '合成显示名更新' })
})

test('恢复的身份变化和无效存储均不能成为登录会话', async () => {
  const state = harness(ACCOUNT_A)
  const result = state.client.restoreSession()
  state.reply(0, 200, { uid: ACCOUNT_B.uid, username: ACCOUNT_B.username })
  await assert.rejects(result, { status: 401, code: 'session_identity_changed' })
  assert.equal(state.client.getSession(), null)
  assert.equal(state.values.has(KEY), false)
  const corrupted = harness({ access_token: 'synthetic', family_id: FAMILY_ID })
  assert.equal(await corrupted.client.restoreSession(), null)
  assert.equal(corrupted.values.has(KEY), false)
})

test('成员接口严格使用Yuxi Bearer和独立ID，关联必须明确确认', async () => {
  const state = harness()
  await signIn(state)
  const calls = [
    [() => state.client.listFamilies(), '/api/family', [{ id: FAMILY_ID }]],
    [() => state.client.getFamily(FAMILY_ID), `/api/family/${FAMILY_ID}`, { id: FAMILY_ID, members: [{ id: SOURCE_ID, is_self: true }] }],
    [() => state.client.listHealthMembers(), '/api/health/v1/members', [{ id: HEALTH_ID }]],
    [() => state.client.readProfileLink(HEALTH_ID), `/api/health/v1/members/${HEALTH_ID}/family-profile-link`, { member_id: HEALTH_ID, source_member_id: null }],
    [() => state.client.readFamilyProfile(HEALTH_ID), `/api/health/v1/members/${HEALTH_ID}/family-profile`, { status: 'not_ready', reason: 'family_profile_incomplete' }],
  ]
  for (const [invoke, url, response] of calls) {
    const result = invoke()
    const index = state.requests.length - 1
    assert.equal(state.requests[index].url, url)
    assert.equal(state.requests[index].header.Authorization, 'Bearer synthetic-token-a')
    state.reply(index, 200, response)
    assert.deepEqual(await result, response)
    assert.deepEqual(state.values.get(KEY), ACCOUNT_A)
  }
  await assert.rejects(state.client.linkProfile(HEALTH_ID, { family_id: FAMILY_ID, source_member_id: SOURCE_ID }), {
    status: 422, code: 'identity_confirmation_required',
  })
  const intent = { family_id: FAMILY_ID, source_member_id: SOURCE_ID, confirmed_identity: true }
  const result = state.client.linkProfile(HEALTH_ID, { ...intent, ignored: 'not-sent' })
  const index = state.requests.length - 1
  assert.equal(state.requests[index].url, `/api/health/v1/members/${HEALTH_ID}/family-profile-link`)
  assert.equal(state.requests[index].method, 'POST')
  assert.equal(state.requests[index].header.Authorization, 'Bearer synthetic-token-a')
  assert.deepEqual(state.requests[index].data, intent)
  state.reply(index, 200, { member_id: HEALTH_ID, ...intent })
  assert.deepEqual(await result, { member_id: HEALTH_ID, ...intent })
  assert.deepEqual(state.values.get(KEY), ACCOUNT_A)
})

test('404权限错误、409关联冲突和429限速保留服务端错误，不伪造成功', async () => {
  const state = harness()
  await signIn(state)
  const cases = [
    [404, { detail: { error: 'not_found', message: '资源不存在或无权访问' } }, 'not_found', '资源不存在或无权访问'],
    [409, { detail: { code: 'profile_link_conflict', message: '已关联的成员不能改绑' } }, 'profile_link_conflict', '已关联的成员不能改绑'],
    [429, { detail: '请稍后再试' }, 'http_429', '请稍后再试'],
    [404, { detail: '资源不存在或无权访问', code: 'not_found', message: '资源不存在或无权访问', trace_id: 'synthetic-trace' }, 'not_found', '资源不存在或无权访问'],
  ]
  for (const [status, body, code, message] of cases) {
    const result = state.client.readProfileLink(HEALTH_ID)
    state.reply(state.requests.length - 1, status, body)
    await assert.rejects(result, { status, code, message })
    assert.deepEqual(state.client.getSession(), ACCOUNT_A)
  }
})

test('当前401立即清理会话并通知页面，随后业务拒绝访问', async () => {
  const state = harness()
  const events = []
  const unsubscribe = state.client.subscribeSession((session, revision) => events.push({ session, revision }))
  await signIn(state)
  const result = state.client.listFamilies()
  state.reply(state.requests.length - 1, 401, { detail: '令牌已过期' })
  await assert.rejects(result, { status: 401, message: '令牌已过期' })
  assert.equal(state.client.getSession(), null)
  assert.equal(state.values.has(KEY), false)
  assert.deepEqual(events.at(-1), { session: null, revision: state.client.sessionRevision })
  await assert.rejects(state.client.listHealthMembers(), { code: 'login_required' })
  unsubscribe()
  const last = events.at(-1)
  state.client.logout()
  assert.equal(events.at(-1), last)
})

test('退出后晚到登录和成员结果不能恢复或返回旧身份', async () => {
  const state = harness()
  const login = state.client.login('member-a', 'synthetic-password')
  const rejectedLogin = assert.rejects(login, { code: 'stale_session' })
  state.client.logout()
  state.reply(0, 200, ACCOUNT_A)
  await rejectedLogin
  assert.equal(state.client.getSession(), null)
  assert.equal(state.values.has(KEY), false)
  await signIn(state)
  const members = state.client.listHealthMembers()
  const memberIndex = state.requests.length - 1
  const rejectedMembers = assert.rejects(members, { code: 'stale_session' })
  state.client.logout()
  state.reply(memberIndex, 200, [{ id: HEALTH_ID }])
  await rejectedMembers
  assert.equal(state.client.getSession(), null)
})

test('响应与await续体之间退出或切账号，不能再次持久化旧会话', async () => {
  const state = harness()
  const login = state.client.login('member-a', 'synthetic-password')
  const rejectedLogin = assert.rejects(login, { code: 'stale_session' })
  state.reply(0, 200, ACCOUNT_A)
  state.client.logout()
  await rejectedLogin
  assert.equal(state.client.getSession(), null)
  assert.equal(state.values.has(KEY), false)

  const restored = harness(ACCOUNT_A)
  const restore = restored.client.restoreSession()
  const rejectedRestore = assert.rejects(restore, { code: 'stale_session' })
  restored.reply(0, 200, ACCOUNT_A)
  const newLogin = restored.client.login('member-b', 'synthetic-password')
  restored.reply(1, 200, ACCOUNT_B)
  await rejectedRestore
  assert.deepEqual(await newLogin, ACCOUNT_B)
  assert.deepEqual(restored.client.getSession(), ACCOUNT_B)
  assert.deepEqual(restored.values.get(KEY), ACCOUNT_B)
})

test('切账号后旧401不能清新会话；晚到的旧登录不能覆盖新身份', async () => {
  const state = harness()
  await signIn(state)
  const old = state.client.listFamilies()
  const oldIndex = state.requests.length - 1
  const rejectedOld = assert.rejects(old, { code: 'stale_session' })
  const firstLogin = state.client.login('member-a', 'synthetic-password')
  const firstIndex = state.requests.length - 1
  const rejectedFirst = assert.rejects(firstLogin, { code: 'stale_session' })
  await signIn(state, ACCOUNT_B)
  state.reply(oldIndex, 401, { detail: '令牌已过期' })
  state.reply(firstIndex, 200, ACCOUNT_A)
  await Promise.all([rejectedOld, rejectedFirst])
  assert.deepEqual(state.client.getSession(), ACCOUNT_B)
  assert.deepEqual(state.values.get(KEY), ACCOUNT_B)
})

test('退出后晚到恢复不能复活会话，网络失败仍是失败并可重新验证', async () => {
  const state = harness(ACCOUNT_A)
  const restore = state.client.restoreSession()
  const rejectedRestore = assert.rejects(restore, { code: 'stale_session' })
  state.client.logout()
  state.reply(0, 200, ACCOUNT_A)
  await rejectedRestore
  assert.equal(state.client.getSession(), null)
  assert.equal(state.values.has(KEY), false)
  const retry = harness(ACCOUNT_A)
  const offline = retry.client.restoreSession()
  retry.requests[0].fail({ errMsg: 'request:fail synthetic transport error' })
  await assert.rejects(offline, { status: 0, code: 'network_error' })
  assert.equal(retry.client.getSession(), null)
  assert.deepEqual(retry.values.get(KEY), ACCOUNT_A)
  const verified = retry.client.restoreSession()
  retry.reply(1, 200, ACCOUNT_A)
  assert.deepEqual(await verified, ACCOUNT_A)
})

test('错误密码和不完整登录响应不留下会话；业务路径ID编码', async () => {
  const state = harness()
  const invalid = state.client.login('member-a', 'wrong-password')
  state.reply(0, 401, { detail: '登录标识或密码错误' })
  await assert.rejects(invalid, { status: 401, code: 'http_401', message: '登录标识或密码错误' })
  const incomplete = state.client.login('member-a', 'synthetic-password')
  state.reply(1, 200, { uid: 'member-a', username: '甲' })
  await assert.rejects(incomplete, { code: 'invalid_response' })
  assert.equal(state.client.getSession(), null)
  assert.equal(state.values.has(KEY), false)
  await signIn(state)
  const result = state.client.getFamily('foreign/../../health')
  assert.equal(state.requests.at(-1).url, '/api/family/foreign%2F..%2F..%2Fhealth')
  state.reply(state.requests.length - 1, 404, { detail: '家庭不存在或不可访问' })
  await assert.rejects(result, { status: 404 })
})

test('H5使用同源API；微信缺配置或非HTTPS明确拒绝', () => {
  assert.equal(resolveNutritionApiBase('h5', 'https://ignored.example/api'), '/api')
  assert.equal(resolveNutritionApiBase('mp-weixin', 'https://nutrition.example/api/'), 'https://nutrition.example/api')
  assert.throws(() => resolveNutritionApiBase('mp-weixin', ''), { code: 'api_not_configured' })
  for (const value of ['http://nutrition.example/api', '/api', 'https://user:pass@example/api', 'https://example/api?secret=x']) {
    assert.throws(() => resolveNutritionApiBase('mp-weixin', value), { code: 'api_requires_https' })
  }
})

test('传输异常和无效回调协议不留下登录会话', async () => {
  const state = harness()
  const malformed = state.client.login('member-a', 'synthetic-password')
  state.requests[0].success(null)
  await assert.rejects(malformed, { status: 0, code: 'invalid_response' })
  assert.equal(state.client.getSession(), null)
  assert.equal(state.values.has(KEY), false)
  const client = createNutritionClient({
    request() { throw new Error('synthetic request adapter failure') },
    storage: { getStorageSync() {}, setStorageSync() {}, removeStorageSync() {} },
  })
  await assert.rejects(client.login('member-a', 'synthetic-password'), { status: 0, code: 'network_error' })
  assert.equal(client.getSession(), null)
})
