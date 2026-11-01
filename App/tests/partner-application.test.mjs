import test from 'node:test'
import assert from 'node:assert/strict'
import { createPartnerApplication, partnerPolicyVersion } from '../src/services/partner-application.js'
import { createCommerceClient } from '../src/services/commerce-client.js'
import { readFileSync } from 'node:fs'
import { ref, computed } from 'vue'

function fixture(send = async () => ({})) {
  let account = 'A', count = 0
  const calls = []
  const draft = createPartnerApplication({ client: { submitPartnerApplication: async (payload, key) => { calls.push({ payload, key }); return send(payload, key) } }, context: () => account, newId: () => 'submission-' + ++count })
  Object.assign(draft.state.form, { type: 'supplier', company: '  个人申请人  ', name: ' 联系人 ', phone: '13800000000', areaId: '3', region: '测试省 测试市 测试区', note: '提供本地合作资源', consent: true })
  return { draft, calls, switchAccount: () => { account = 'B' } }
}

for (const type of ['supplier', 'channel', 'distributor']) test(`partner intake accepts a personal ${type} without qualification uploads`, async () => {
  const { draft, calls } = fixture()
  draft.state.form.type = type
  await draft.submit()
  assert.equal(draft.state.saved, true)
  assert.equal(calls[0].payload.company_name, '个人申请人')
  assert.equal(calls[0].payload.partner_type, type)
  assert.equal(calls[0].payload.privacy_consent_version, partnerPolicyVersion)
  assert.equal(calls[0].payload.contact_wechat, '')
  assert.equal(calls[0].payload.qualification_files, undefined)
  assert.equal(draft.state.form.phone, '')
  await draft.submit(); assert.equal(calls.length, 1)
})

for (const [field, value] of [['type', ''], ['type', 'other'], ['company', '  '], ['name', '  '], ['phone', '123'], ['note', '  '], ['note', '字'.repeat(501)], ['areaId', ''], ['consent', false]]) test(`partner intake validates ${field} before any request`, async () => {
  const { draft, calls } = fixture()
  draft.state.form[field] = value
  await draft.submit()
  assert.equal(calls.length, 0); assert.equal(draft.state.saved, false); assert.ok(draft.state.error)
})

test('partner failure retains inputs and reuses submission key until the payload changes', async () => {
  const f = fixture(async () => { throw new Error('synthetic network failure') })
  await f.draft.submit(); await f.draft.submit()
  assert.equal(f.calls[0].key, f.calls[1].key)
  assert.equal(f.draft.state.form.phone, '13800000000')
  f.draft.state.form.note = '另一项合作意向'
  await f.draft.submit(); assert.notEqual(f.calls[1].key, f.calls[2].key)
})

for (const reason of ['account', 'unload']) test(`partner ${reason} invalidates late success and removes contact data`, async () => {
  let finish
  const f = fixture(() => new Promise(resolve => { finish = resolve }))
  const pending = f.draft.submit()
  await f.draft.submit(); assert.equal(f.calls.length, 1)
  if (reason === 'account') f.switchAccount()
  else f.draft.dispose()
  finish({}); await pending
  assert.equal(f.draft.state.saved, false); assert.equal(f.draft.state.form.phone, '')
  await f.draft.submit(); assert.equal(f.calls.length, 1)
})

function commerceFixture(handler) {
  const storage = new Map(), calls = []
  const client = createCommerceClient({ baseUrl: '/commerce-api', allowProxy: true, authMode: 'agent',
    parent: { read: () => ({ accountId: '17', token: 'synthetic-agent-token' }), scope: () => 'synthetic-account', storageScope: () => '17' },
    storage: { get: key => storage.get(key), set: (key, value) => storage.set(key, value) }, randomKey: () => 'key',
    transport: async options => { calls.push(options); return options.url.endsWith('/exchange')
      ? { statusCode: 200, data: { code: 0, data: { agent_account_id: '17', user: { id: 7, token: 'synthetic-mall-token' } } } }
      : handler(options) },
  })
  return { client, calls }
}
const response = data => ({ statusCode: 200, data: { code: 0, data } })
test('partner uses mall identity, a validated capability and the same write key', async () => {
  const f = commerceFixture(o => o.method === 'POST' ? response({ application_sn: 'supplierapply_synthetic_001', submitted_at: 1, policy_version: partnerPolicyVersion }) : response({ policy_version: partnerPolicyVersion }))
  await f.client.submitPartnerApplication({ privacy_consent_version: partnerPolicyVersion }, 'submission-key')
  const post = f.calls.find(o => o.url.endsWith('/supplier-applications'))
  assert.equal(post.header.token, 'synthetic-mall-token'); assert.equal(post.header.Authorization, undefined)
  assert.equal(post.header['Idempotency-Key'], 'submission-key')
})
test('an old backend cannot receive an incomplete new partner form', async () => {
  const f = commerceFixture(() => ({ statusCode: 404, data: { code: 404, message: 'not found' } }))
  await assert.rejects(f.client.submitPartnerApplication({ privacy_consent_version: partnerPolicyVersion }, 'key'), e => e.code === 'PARTNER_NOT_READY')
  assert.equal(f.calls.filter(o => o.url.endsWith('/supplier-applications')).length, 0)
})
test('HTTP success without a committed intake receipt never confirms the submission', async () => {
  const f = commerceFixture(o => response(o.method === 'POST' ? { application_sn: 'old_response' } : { policy_version: partnerPolicyVersion }))
  await assert.rejects(f.client.submitPartnerApplication({ privacy_consent_version: partnerPolicyVersion }, 'key'), e => e.code === 'INVALID_RESPONSE')
})

test('partner route is admitted for logged-in applicants without requiring a health profile', () => {
  const source = readFileSync(new URL('../src/services/navigation.js', import.meta.url), 'utf8').replace(/^import .*$/gm, '').replace(/export /g, '')
  const routes = new Function('isMockMode', 'isCommerceEnabled', source + ';return {canOpenPage,protectedDestination}')(false, true)
  assert.equal(routes.canOpenPage('/pages/supplier/index'), true)
  for (const entry of ['/pages/chat/index', '/pages/onboarding/index', '/pages/onboarding/preparing']) assert.equal(routes.protectedDestination('/pages/supplier/index', entry), '/pages/supplier/index')
  assert.equal(routes.protectedDestination('/pages/supplier/index', '/pages/index/index'), '/pages/index/index')
  assert.equal(routes.protectedDestination('/pages/supplier/index', '/pages/invite/index?token=pending'), '/pages/invite/index?token=pending')
})

test('the actual My page opens the partner form and keeps other unavailable services guarded', () => {
  const source = readFileSync(new URL('../src/components/CloudMyProfile.vue', import.meta.url), 'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  const routes = [], modals = []
  const deps = { ref, computed, onMounted: () => {}, onShow: () => {}, onHide: () => {}, isCommerceEnabled: true,
    uni: { navigateTo: value => routes.push(value.url), showModal: value => modals.push(value.title) } }
  const page = new Function('deps', `const {${Object.keys(deps)}}=deps;${source};return {go,serviceItems}`)(deps)
  assert.ok(page.serviceItems.every(Boolean))
  page.go(page.serviceItems.find(item => item.url === '/pages/supplier/index').url)
  assert.deepEqual(routes, ['/pages/supplier/index']); assert.equal(modals.length, 0)
  page.go('devices'); assert.deepEqual(modals, ['健康设备'])
})
