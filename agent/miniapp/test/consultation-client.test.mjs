import test from 'node:test'
import assert from 'node:assert/strict'
import { createNutritionClient } from '../src/services/nutrition-client.js'

const MEMBER = 'ed553e56-75ad-4edb-8081-939d94335b2a'
const THREAD = '3328c92f-9400-4b3f-aab9-29d9701329a8'
const KEY = '09841d93-1acb-461a-8c67-7b1561eae15a'
const RUN = '0aab8c42-a6d4-4431-a002-9e1572322b47'

/** 独立捕获真实uni.request协议参数，响应由测试主动交付。 */
async function connected() {
  const calls = [], values = new Map()
  const client = createNutritionClient({
    request(options) { calls.push(options) },
    storage: {
      getStorageSync: key => values.get(key),
      setStorageSync: (key, value) => values.set(key, structuredClone(value)),
      removeStorageSync: key => values.delete(key),
    },
  })
  const login = client.login('synthetic-user', 'synthetic-password')
  calls[0].success({ statusCode: 200, data: { access_token: 'synthetic-token', uid: 'synthetic-user', username: '合成账号' } })
  await login
  return { client, calls, values }
}

test('咨询所有读接口沿用认证与预算，历史分页只使用服务端日期', async () => {
  const { client, calls, values } = await connected()
  const cases = [
    [() => client.readConsultationConfiguration(), '/api/health/v1/configuration'],
    [() => client.listDailyConversations(MEMBER), `/api/health/v1/members/${MEMBER}/daily-conversations`],
    [() => client.listDailyConversations(MEMBER, '2026-10-09'), `/api/health/v1/members/${MEMBER}/daily-conversations?before=2026-10-09`],
    [() => client.listMemberConsultations(MEMBER, { limit: 20, offset: 20 }), `/api/health/v1/members/${MEMBER}/consultations?limit=20&offset=20`],
    [() => client.readThreadHistory(THREAD), `/api/chat/thread/${THREAD}/history`],
    [() => client.readAgentRequest(KEY), `/api/agent/requests/${KEY}`],
    [() => client.readAgentRun(RUN), `/api/agent/runs/${RUN}`],
    [() => client.readAgentRunResult(RUN), `/api/agent/runs/${RUN}/result`],
    [() => client.readThreadActiveRun(THREAD), `/api/agent/thread/${THREAD}/active_run`],
  ]
  for (const [read, url] of cases) {
    const pending = read(), call = calls.at(-1)
    assert.equal(call.url, url)
    assert.equal(call.method, 'GET')
    assert.equal(call.timeout, 15000)
    assert.equal(call.header.Authorization, 'Bearer synthetic-token')
    call.success({ statusCode: 200, data: { contract: url } })
    assert.deepEqual(await pending, { contract: url })
  }
  assert.deepEqual([...values.keys()], ['healthswarm.nutrition.session'])
  assert.equal(JSON.stringify([...values.values()]).includes('contract'), false)
  await assert.rejects(client.listMemberConsultations(MEMBER, { limit: 51 }), { code: 'invalid_pagination' })
  await assert.rejects(client.listMemberConsultations(MEMBER, { offset: -1 }), { code: 'invalid_pagination' })
})

test('用途同意要求明确布尔值，固定consultation用途及政策白名单', async () => {
  const { client, calls } = await connected()
  const count = calls.length
  for (const data of [{}, { accepted: 'true', processor: 'synthetic', policy_version: 'policy' }, { accepted: true, processor: '', policy_version: 'policy' }]) {
    await assert.rejects(client.setConsultationConsent(MEMBER, data), { code: 'consent_required' })
  }
  assert.equal(calls.length, count)
  for (const accepted of [true, false]) {
    const pending = client.setConsultationConsent(MEMBER, { accepted, processor: 'synthetic-processor', policy_version: 'synthetic-v1', purpose: 'meal_plan', model: 'ignored', uid: 'ignored' })
    const call = calls.at(-1)
    assert.equal(call.url, `/api/health/v1/members/${MEMBER}/processing-consents`)
    assert.equal(call.method, 'POST')
    assert.deepEqual(call.data, { accepted, purpose: 'consultation', processor: 'synthetic-processor', policy_version: 'synthetic-v1' })
    call.success({ statusCode: 200, data: { accepted } })
    assert.deepEqual(await pending, { accepted })
  }
})

test('新建咨询幂等键与正文一致，每日重入只携带成员路径', async () => {
  const { client, calls } = await connected()
  for (let attempt = 0; attempt < 2; attempt++) {
    const pending = client.createConsultation(MEMBER, { client_request_id: KEY, member_id: 'foreign', model_spec: 'ignored', agent_slug: 'arbitrary' })
    const call = calls.at(-1)
    assert.equal(call.url, `/api/health/v1/members/${MEMBER}/consultations`)
    assert.equal(call.header['Idempotency-Key'], KEY)
    assert.deepEqual(call.data, { client_request_id: KEY })
    call.success({ statusCode: 201, data: { thread_id: THREAD, member_id: MEMBER, agent_slug: 'health-consultation' } })
    assert.equal((await pending).thread_id, THREAD)
  }
  const daily = client.createDailyConsultation(MEMBER)
  assert.equal(calls.at(-1).url, `/api/health/v1/members/${MEMBER}/daily-consultations`)
  assert.equal(calls.at(-1).data, undefined)
  assert.equal(calls.at(-1).header['Idempotency-Key'], undefined)
  calls.at(-1).success({ statusCode: 200, data: { thread_id: THREAD } })
  await daily
})

test('提交仅固定角色、线程、问题与请求键，未知响应原包可重发', async () => {
  const { client, calls } = await connected()
  await assert.rejects(client.submitConsultationRequest(THREAD, { query: '  ', request_id: KEY }), { code: 'question_required' })
  const input = { query: '请解释我的已确认记录。', request_id: KEY, agent_slug: 'other', model_spec: 'ignored', tools: ['ignored'], member_id: 'foreign' }
  const expected = { query: input.query, agent_slug: 'health-consultation', thread_id: THREAD, meta: { request_id: KEY } }
  const first = client.submitConsultationRequest(THREAD, input)
  assert.deepEqual(calls.at(-1).data, expected)
  calls.at(-1).fail({ errMsg: 'synthetic response lost' })
  await assert.rejects(first, { code: 'network_error' })
  const retry = client.submitConsultationRequest(THREAD, input)
  assert.deepEqual(calls.at(-1).data, expected)
  calls.at(-1).success({ statusCode: 200, data: { request_id: KEY, run_id: RUN, status: 'dispatched' } })
  assert.equal((await retry).run_id, RUN)
})

test('当前403/410保持业务错误，退出后的咨询结果与旧401不进入新账号', async () => {
  const { client, calls } = await connected()
  for (const [status, code] of [[403, 'processing_consent_required'], [410, 'consultation_source_invalidated']]) {
    const pending = client.readAgentRunResult(RUN)
    calls.at(-1).success({ statusCode: status, data: { code, message: '合成业务拒绝' } })
    await assert.rejects(pending, { status, code })
    assert.equal(client.getSession().uid, 'synthetic-user')
  }
  const pending = client.readAgentRunResult(RUN), old = calls.at(-1)
  const rejected = assert.rejects(pending, { code: 'stale_session' })
  client.logout()
  const login = client.login('synthetic-b', 'synthetic-password')
  calls.at(-1).success({ statusCode: 200, data: { access_token: 'synthetic-b-token', uid: 'synthetic-b', username: '合成乙' } })
  await login
  old.success({ statusCode: 401, data: { message: '旧账号过期' } })
  await rejected
  assert.equal(client.getSession().uid, 'synthetic-b')
})
