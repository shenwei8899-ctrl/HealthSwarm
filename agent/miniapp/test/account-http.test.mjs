import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createNutritionClient } from '../src/services/nutrition-client.js'

const enabled = process.env.HEALTH_MINIAPP_HTTP_ACCEPTANCE === 'true'
const apiBase = 'http://127.0.0.1:15484/api'
const fixtureDirectory = process.env.MINIAPP_ACCOUNT_FIXTURE_DIR
  ?? fileURLToPath(new URL('../../.tmp/miniapp-account-20261009/', import.meta.url))
const storageKey = 'healthswarm.nutrition.session'

/** 原生fetch只适配uni.request协议，状态与错误处理仍使用正式客户端。 */
function nativeRequest(options) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), options.timeout ?? 20000)
  const headers = options.header ?? {}
  const body = options.data === undefined ? undefined
    : typeof options.data === 'string' ? options.data : JSON.stringify(options.data)
  fetch(options.url, {
    method: options.method ?? 'GET',
    headers,
    body,
    signal: controller.signal,
  }).then(async (response) => {
    const data = await response.json()
    options.success({ statusCode: response.status, data })
  }).catch((error) => options.fail(error)).finally(() => clearTimeout(timeout))
  return { abort: () => controller.abort() }
}

function memoryStorage() {
  const values = new Map()
  return {
    getStorageSync: (key) => structuredClone(values.get(key)),
    setStorageSync: (key, value) => values.set(key, structuredClone(value)),
    removeStorageSync: (key) => values.delete(key),
  }
}

function client(storage = memoryStorage()) {
  return createNutritionClient({ request: nativeRequest, storage, apiBase })
}

async function businessRequest(session, path, { method = 'GET', data } = {}) {
  const response = await fetch(apiBase + path, {
    method,
    headers: { Authorization: `Bearer ${session.access_token}`, 'Content-Type': 'application/json' },
    body: data === undefined ? undefined : JSON.stringify(data),
    signal: AbortSignal.timeout(20000),
  })
  return { status: response.status, data: await response.json() }
}

test('隔离槽位真实账号、成员和显式关联HTTP验收', { skip: !enabled }, async (t) => {
  const evidencePath = resolve(fixtureDirectory, 'http-verification.json')
  await writeFile(evidencePath, JSON.stringify({ passed: false, status: 'running', checks: [] }, null, 2))
  const metadata = JSON.parse(await readFile(resolve(fixtureDirectory, 'metadata.json'), 'utf8'))
  const credentials = JSON.parse(await readFile(resolve(fixtureDirectory, 'credentials.secret.json'), 'utf8'))
  assert.equal(metadata.cleaned, false)
  assert.equal(metadata.baseline.database, 'health_consultation_e2e')
  assert.equal(metadata.baseline.links.length, 0)
  assert.ok(Object.values(metadata.accounts).every(({ uid }) => uid.startsWith('miniapp_test_')))
  const primaryId = metadata.health_members.primary
  const source = { ...metadata.families.owner, confirmed_identity: true }
  const storage = memoryStorage()
  let owner = client(storage)
  const results = []
  const check = async (name, action) => {
    let passed = false
    await t.test(name, async () => {
      await action()
      passed = true
    })
    results.push({ name, passed })
  }

  await check('错误密码被真实认证服务拒绝且不产生会话', async () => {
    await assert.rejects(owner.login(credentials.owner.identifier, 'synthetic-deliberately-wrong-password'), { status: 401 })
    assert.equal(owner.getSession(), null)
    assert.equal(storage.getStorageSync(storageKey), undefined)
  })

  await check('现有账号密码登录与me回读为同一普通账号', async () => {
    const session = await owner.login(credentials.owner.identifier, credentials.owner.password)
    assert.equal(session.uid, metadata.accounts.owner.uid)
    assert.ok(session.access_token)
    const read = await businessRequest(session, '/auth/me')
    assert.equal(read.status, 200)
    assert.equal(read.data.uid, metadata.accounts.owner.uid)
    assert.equal(read.data.role, 'user')
    assert.equal(read.data.department_id, metadata.department_id)
    assert.equal(Object.hasOwn(storage.getStorageSync(storageKey), 'password'), false)
  })

  await check('家庭详情与健康对象使用各自真实UUID并保持原授权范围', async () => {
    const families = await owner.listFamilies()
    assert.equal(families.length, 1)
    assert.equal(families[0].id, source.family_id)
    const family = await owner.getFamily(source.family_id)
    const ownSources = family.members.filter((member) => member.is_self)
    assert.equal(ownSources.length, 1)
    assert.equal(ownSources[0].id, source.source_member_id)
    assert.equal(ownSources[0].confirmed, true)
    const members = await owner.listHealthMembers()
    assert.deepEqual(members.map(({ id }) => id).sort(), [primaryId, metadata.health_members.conflict].sort())
    assert.ok(members.every(({ is_owner, relationship_label }) => is_owner && relationship_label === '本人'))
    assert.notEqual(primaryId, source.source_member_id)
  })

  await check('未关联对象回读明确未就绪状态，不自动建档或猜测姓名', async () => {
    const existing = await owner.readProfileLink(primaryId)
    assert.equal(existing.member_id, primaryId)
    assert.equal(existing.source_member_id, null)
    const profile = await owner.readFamilyProfile(primaryId)
    assert.equal(profile.status, 'not_ready')
    assert.equal(profile.profile, null)
  })

  await check('未明确确认在客户端与真实HTTP服务均拒绝', async () => {
    await assert.rejects(owner.linkProfile(primaryId, { ...source, confirmed_identity: false }), { status: 422 })
    const read = await businessRequest(owner.getSession(), `/health/v1/members/${primaryId}/family-profile-link`, {
      method: 'POST', data: { ...source, confirmed_identity: false },
    })
    assert.equal(read.status, 422)
    assert.equal((await owner.readProfileLink(primaryId)).source_member_id, null)
  })

  await check('他人家庭来源与他人健康对象均被当前授权边界拒绝', async () => {
    await assert.rejects(owner.linkProfile(primaryId, { ...metadata.families.other, confirmed_identity: true }), { status: 404 })
    await assert.rejects(owner.linkProfile(metadata.health_members.foreign, source), { status: 404 })
    await assert.rejects(owner.getFamily(metadata.families.other.family_id), { status: 404 })
    await assert.rejects(owner.readProfileLink(metadata.health_members.foreign), { status: 404 })
  })

  await check('本人明确关联后重复调用与重新加载均回读同一持久来源', async () => {
    const linked = await owner.linkProfile(primaryId, source)
    assert.equal(linked.member_id, primaryId)
    assert.equal(linked.source_member_id, source.source_member_id)
    assert.equal(linked.family_id, source.family_id)
    const repeated = await owner.linkProfile(primaryId, source)
    assert.deepEqual(repeated, linked)
    owner = client(storage)
    assert.equal(owner.getSession(), null)
    const restored = await owner.restoreSession()
    assert.equal(restored.uid, metadata.accounts.owner.uid)
    const persisted = await owner.readProfileLink(primaryId)
    assert.deepEqual(persisted, linked)
    const profile = await owner.readFamilyProfile(primaryId)
    assert.equal(profile.status, 'ready')
    assert.equal(profile.confirmed_version, 2)
    assert.equal(profile.source.source_member_id, source.source_member_id)
    assert.ok(profile.unsupported.includes('approved_personal_targets'))
  })

  await check('同一家庭来源关联第二健康对象因唯一身份冲突拒绝', async () => {
    await assert.rejects(owner.linkProfile(metadata.health_members.conflict, source), { status: 409, code: 'profile_link_conflict' })
    assert.equal((await owner.readProfileLink(metadata.health_members.conflict)).source_member_id, null)
  })

  await check('本人撤回profile_view后既有映射与档案立即拒绝，恢复仅还原原scope', async () => {
    const original = metadata.baseline.grants.find((grant) => grant.member_id === primaryId)
    const path = `/health/v1/members/${primaryId}/grants`
    try {
      const withdrawn = await businessRequest(owner.getSession(), path, {
        method: 'PUT', data: { actor_uid: metadata.accounts.owner.uid, scopes: ['profile_edit'] },
      })
      assert.equal(withdrawn.status, 200)
      await assert.rejects(owner.readProfileLink(primaryId), { status: 404 })
      await assert.rejects(owner.readFamilyProfile(primaryId), { status: 404 })
    } finally {
      const restored = await businessRequest(owner.getSession(), path, {
        method: 'PUT', data: { actor_uid: metadata.accounts.owner.uid, scopes: original.scopes },
      })
      assert.equal(restored.status, 200)
    }
    assert.equal((await owner.readProfileLink(primaryId)).source_member_id, source.source_member_id)
  })

  await check('无部门账号真实登录后业务与me均报告前置条件不足', async () => {
    const noDepartment = client()
    const signed = await noDepartment.login(credentials.no_department.identifier, credentials.no_department.password)
    assert.equal(signed.uid, metadata.accounts.no_department.uid)
    await assert.rejects(noDepartment.listFamilies(), { status: 400 })
    await assert.rejects(noDepartment.listHealthMembers(), { status: 400 })
    await assert.rejects(noDepartment.restoreSession(), { status: 400 })
    assert.equal(noDepartment.getSession(), null)
    noDepartment.logout()
  })

  await check('切换账号只读取新身份家庭与成员，退出清除持久会话', async () => {
    await owner.login(credentials.other.identifier, credentials.other.password)
    assert.equal(owner.getSession().uid, metadata.accounts.other.uid)
    const families = await owner.listFamilies()
    assert.equal(families.length, 1)
    assert.equal(families[0].id, metadata.families.other.family_id)
    const members = await owner.listHealthMembers()
    assert.deepEqual(members.map(({ id }) => id), [metadata.health_members.foreign])
    await assert.rejects(owner.readProfileLink(primaryId), { status: 404 })
    owner.logout()
    assert.equal(owner.getSession(), null)
    assert.equal(storage.getStorageSync(storageKey), undefined)
    await assert.rejects(owner.listFamilies(), { status: 401, code: 'login_required' })
  })

  await check('过期或伪造持久Token经真实me拒绝并清空客户端会话', async () => {
    storage.setStorageSync(storageKey, { uid: metadata.accounts.owner.uid, username: metadata.accounts.owner.uid, access_token: 'synthetic-invalid-token' })
    const expired = client(storage)
    await assert.rejects(expired.restoreSession(), { status: 401 })
    assert.equal(expired.getSession(), null)
    assert.equal(storage.getStorageSync(storageKey), undefined)
  })

  await writeFile(evidencePath, JSON.stringify({
    fixture_id: metadata.fixture_id,
    passed: results.every(({ passed }) => passed),
    status: results.every(({ passed }) => passed) ? 'passed' : 'failed',
    api_base: apiBase,
    checks: results,
    requires_independent_pg_verification: true,
    browser_account: 'other',
    not_run: ['WeChat developer tools or physical device', 'Public HTTPS deployment', 'Cloud models'],
  }, null, 2))
})
