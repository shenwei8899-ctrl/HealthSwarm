import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { setImmediate } from 'node:timers'
import { computed, effectScope, nextTick, reactive, ref, watch } from 'vue'
import { profileLabels, profileStatus } from '../src/utils/familyArchives.js'

const source = await readFile(
  new URL('../src/components/health/HealthFamilyProfile.vue', import.meta.url),
  'utf8'
)
const script = source
  .match(/<script setup>([\s\S]*?)<\/script>/)[1]
  .replace(/^import[\s\S]*?from ['"][^'"]+['"]\s*\n/gm, '')
const selfMember = (id = 'health-a', extra = {}) => ({
  id,
  display_name: '合成本人',
  relationship_label: '本人',
  is_owner: true,
  scopes: ['profile_view', 'profile_edit', 'ai_use'],
  ...extra
})
const linked = (id = 'health-a') => ({
  member_id: id,
  family_id: `family-${id}`,
  source_member_id: `source-${id}`,
  scope: 'self_confirmed_profile'
})
const availableProfile = (version = 2, extra = {}) => ({
  status: 'ready',
  code: 'self_confirmed_profile',
  profile_available: true,
  confirmed_version: version,
  unknown_fields: ['medical_history'],
  nutrition_safety_ready: false,
  full_health_profile_available: false,
  profile: { medical_history: '不应保存到组件状态的合成正文' },
  ...extra
})
const family = (id, members = []) => ({ id, name: `合成家庭 ${id}`, members })
const formalMember = (id, extra = {}) => ({
  id,
  name: `合成本人 ${id}`,
  is_self: true,
  claimed: true,
  allowed_fields: ['height_cm'],
  version: 2,
  confirmed: true,
  ready: true,
  missing_fields: [],
  profile: { medical_history: '不应保存到来源或候选状态的合成正文' },
  ...extra
})
const notLinked = (id) => ({ member_id: id, source_member_id: null })
const notReady = { status: 'not_ready', code: 'profile_not_linked', profile_available: false }
const nextRequests = async () => {
  await nextTick()
  await new Promise(setImmediate)
}
const deferred = () => {
  let resolve, reject
  const promise = new Promise((finish, fail) => {
    resolve = finish
    reject = fail
  })
  return { promise, resolve, reject }
}

/** 执行真实 SFC 与 Vue watcher，生命周期清理也使用组件的真实回调。 */
function panel(api = {}, familyApi = {}, options = {}) {
  const props = reactive({ member: selfMember(), disabled: false, ...options.props })
  const user = reactive({ uid: 'synthetic-user', token: 'synthetic-session', isLoggedIn: true })
  const events = []
  const routes = []
  const scope = effectScope()
  let cleanup
  const factory = new Function(
    'computed',
    'onMounted',
    'onBeforeUnmount',
    'ref',
    'watch',
    'useRouter',
    'useUserStore',
    'api',
    'familyApi',
    'profileLabels',
    'profileStatus',
    'defineProps',
    'defineEmits',
    `${script}\nreturn { link, profile, source, candidates, selectedKey, confirmedIdentity, loading, saving, error, success, isSelf, canRead, canEdit, linked, selected, busy, ready, statusLabel, missing, reload, associate, openArchives, consult }`
  )
  const state = scope.run(() =>
    factory(
      computed,
      () => {},
      (fn) => {
        cleanup = fn
      },
      ref,
      watch,
      () => ({ push: (route) => routes.push(route) }),
      () => user,
      { familyProfileLink: async (id) => notLinked(id), familyProfile: async () => notReady, ...api },
      { list: async () => [], ...familyApi },
      profileLabels,
      profileStatus,
      () => props,
      () => (...args) => events.push(args)
    )
  )
  return {
    ...state,
    props,
    user,
    events,
    routes,
    dispose: () => {
      cleanup()
      scope.stop()
    }
  }
}

const candidateFamilies = {
  list: async () => [{ id: 'family-a' }],
  get: async () => family('family-a', [formalMember('self-a')])
}
const readyApis = {
  familyProfileLink: async (id) => linked(id),
  familyProfile: async () => availableProfile()
}
const linkedFamily = {
  get: async (id) => family(id, [formalMember(id.replace('family-', 'source-'))])
}

test('本人身份及档案查看授权不满足时不读取私有数据或关联', async () => {
  for (const member of [
    null,
    selfMember('health-a', { is_owner: false }),
    selfMember('health-a', { relationship_label: '母亲' }),
    selfMember('health-a', { scopes: ['profile_edit', 'ai_use'] })
  ]) {
    const calls = []
    const state = panel(
      {
        familyProfileLink: async () => calls.push('read'),
        familyProfile: async () => calls.push('profile'),
        linkFamilyProfile: async () => calls.push('write')
      },
      { list: async () => calls.push('families') },
      { props: { member } }
    )
    await state.reload()
    state.candidates.value = [{ key: 'chosen', familyId: 'family-a', sourceId: 'self-a' }]
    state.selectedKey.value = 'chosen'
    state.confirmedIdentity.value = true
    await state.associate()
    assert.equal(state.canRead.value, false)
    assert.equal(state.canEdit.value, false)
    assert.deepEqual(calls, [])
    state.dispose()
  }
})

test('只有查看授权时可回读未关联状态，编辑入口不读取候选也不写入', async () => {
  const calls = []
  const state = panel(
    {
      familyProfileLink: async (id) => {
        calls.push('link')
        return notLinked(id)
      },
      familyProfile: async () => {
        calls.push('profile')
        return notReady
      },
      linkFamilyProfile: async () => calls.push('write')
    },
    { list: async () => calls.push('families') },
    { props: { member: selfMember('health-a', { scopes: ['profile_view'] }) } }
  )
  await state.reload()
  await state.associate()
  assert.equal(state.canRead.value, true)
  assert.equal(state.canEdit.value, false)
  assert.equal(state.statusLabel.value, '尚未关联')
  assert.deepEqual(state.candidates.value, [])
  assert.deepEqual(calls, ['link', 'profile'])
  state.dispose()
})

test('候选仅来自各家庭的本人认领成员，主动换选择立即取消身份确认', async () => {
  const state = panel({}, {
    list: async () => [{ id: 'family-a' }, { id: 'family-b' }],
    get: async (id) => family(id, [
      formalMember(`self-${id}`),
      formalMember(`other-${id}`, { is_self: false, name: `合成本人 self-${id}` })
    ])
  })
  await state.reload()
  assert.deepEqual(state.candidates.value.map((item) => item.key), [
    'family-a:self-family-a',
    'family-b:self-family-b'
  ])
  assert.equal(state.selectedKey.value, '')
  assert.equal(state.confirmedIdentity.value, false)
  assert.equal(state.candidates.value.some((item) => 'profile' in item), false)
  state.selectedKey.value = state.candidates.value[0].key
  state.confirmedIdentity.value = true
  state.selectedKey.value = state.candidates.value[1].key
  assert.equal(state.confirmedIdentity.value, false)
  state.dispose()
})

test('明确选择及同一身份确认才关联，成功提示等待服务事实回读', async () => {
  let serverLinked = false
  const requests = []
  const reads = []
  const state = panel({
    familyProfileLink: async (id) => {
      reads.push('link')
      return serverLinked
        ? { member_id: id, family_id: 'family-a', source_member_id: 'self-a' }
        : notLinked(id)
    },
    familyProfile: async () => {
      reads.push('profile')
      return serverLinked ? availableProfile(7) : notReady
    },
    linkFamilyProfile: async (id, payload) => {
      requests.push({ id, payload })
      serverLinked = true
      return { confirmed_version: 999 }
    },
    consent: async () => requests.push('unexpected-model-consent')
  }, candidateFamilies)
  await state.reload()
  state.confirmedIdentity.value = true
  await state.associate()
  assert.deepEqual(requests, [])
  state.selectedKey.value = state.candidates.value[0].key
  await state.associate()
  assert.deepEqual(requests, [])
  state.confirmedIdentity.value = true
  state.props.disabled = true
  await state.associate()
  assert.deepEqual(requests, [])
  state.props.disabled = false
  await state.associate()
  assert.deepEqual(requests, [{
    id: 'health-a',
    payload: { family_id: 'family-a', source_member_id: 'self-a', confirmed_identity: true }
  }])
  assert.deepEqual(reads, ['link', 'profile', 'link', 'profile'])
  assert.equal(state.profile.value.confirmed_version, 7)
  assert.equal(state.ready.value, true)
  assert.match(state.success.value, /已关联.*重新核对/)
  assert.deepEqual(state.candidates.value, [])
  assert.equal(state.confirmedIdentity.value, false)
  state.dispose()
})

test('刷新显示当前确认、待确认及缺失字段，私有正文不进入组件状态', async () => {
  let current = availableProfile(3)
  let sourceVersion = 3
  const state = panel({
    ...readyApis,
    familyProfile: async () => current
  }, {
    get: async (id) => family(id, [
      formalMember('source-health-a', { version: sourceVersion, missing_fields: ['birth_date'] })
    ])
  })
  await state.reload()
  assert.equal(state.statusLabel.value, '当前档案已确认')
  assert.equal(state.profile.value.confirmed_version, 3)
  assert.equal(state.profile.value.nutrition_safety_ready, false)
  assert.equal('profile' in state.profile.value, false)
  assert.equal('profile' in state.source.value, false)
  current = { ...notReady, code: 'profile_unconfirmed', confirmed_version: null }
  sourceVersion = 4
  await state.reload()
  assert.equal(state.statusLabel.value, '当前版本待本人确认')
  assert.equal(state.source.value.version, 4)
  assert.equal(state.profile.value.confirmed_version, null)
  assert.equal(state.ready.value, false)
  assert.deepEqual(state.missing.value, ['birth_date'])
  current = { ...notReady, code: 'profile_incomplete', missing_fields: ['height_cm'] }
  await state.reload()
  assert.equal(state.statusLabel.value, '档案待补充')
  assert.deepEqual(state.missing.value, ['height_cm'])
  state.dispose()
})

test('已有来源不能改绑，咨询只发出显式事件且遵守禁用和AI授权', async () => {
  const writes = []
  const state = panel({
    ...readyApis,
    linkFamilyProfile: async (...args) => writes.push(args),
    consent: async (...args) => writes.push(args)
  }, linkedFamily)
  await state.reload()
  state.candidates.value = [{ key: 'other', familyId: 'family-b', sourceId: 'self-b' }]
  state.selectedKey.value = 'other'
  state.confirmedIdentity.value = true
  await state.associate()
  assert.deepEqual(writes, [])
  state.props.disabled = true
  state.consult()
  state.openArchives()
  assert.deepEqual(state.events, [])
  assert.deepEqual(state.routes, [])
  state.props.disabled = false
  state.consult()
  state.openArchives()
  assert.deepEqual(state.events, [['consult']])
  assert.deepEqual(state.routes, [{ name: 'family', query: { tab: 'profiles' } }])
  state.props.member.scopes = ['profile_view', 'profile_edit']
  await nextRequests()
  state.consult()
  assert.deepEqual(state.events, [['consult']])
  assert.deepEqual(writes, [])
  state.dispose()
})

test('读取失败清除旧状态及正文，退出登录或撤回权限立即隔离私有数据', async () => {
  for (const status of [403, 404, 409]) {
    let failure = false
    const state = panel({
      ...readyApis,
      familyProfile: async () => {
        if (failure) throw Object.assign(Error('不得回显的合成错误正文'), { status })
        return availableProfile()
      }
    }, linkedFamily)
    await state.reload()
    assert.equal(state.ready.value, true)
    failure = true
    await state.reload()
    assert.equal(state.profile.value, null)
    assert.equal(state.source.value, null)
    assert.deepEqual(state.candidates.value, [])
    assert.equal(state.ready.value, false)
    assert.match(state.error.value, status === 403 ? /权限/ : status === 404 ? /不可访问/ : /不能改绑/)
    assert.equal(state.error.value.includes('合成错误正文'), false)
    state.dispose()
  }
  for (const revoke of [
    (state) => { state.user.token = ''; state.user.isLoggedIn = false; state.user.uid = '' },
    (state) => { state.props.member.scopes = [] }
  ]) {
    const state = panel(readyApis, linkedFamily)
    await state.reload()
    revoke(state)
    assert.equal(state.profile.value, null)
    assert.equal(state.source.value, null)
    assert.equal(state.link.value, null)
    assert.equal(state.success.value, '')
    await nextRequests()
    assert.equal(state.profile.value, null)
    assert.equal(state.error.value, '')
    state.dispose()
  }
})

test('切换成员后迟到的关联或档案读取及错误不能覆盖新成员', async () => {
  for (const stage of ['link', 'profile']) {
    for (const outcome of ['success', 'error']) {
      const oldResponse = deferred()
      const state = panel({
        familyProfileLink: async (id) => id === 'health-a' && stage === 'link'
          ? oldResponse.promise
          : linked(id),
        familyProfile: async (id) => id === 'health-a' && stage === 'profile'
          ? oldResponse.promise
          : availableProfile(8)
      }, linkedFamily)
      const oldRead = state.reload()
      await nextRequests()
      state.props.member = selfMember('health-b')
      await nextRequests()
      if (outcome === 'error') oldResponse.reject(Object.assign(Error('旧成员私有错误'), { status: 404 }))
      else oldResponse.resolve(stage === 'link' ? linked('health-a') : availableProfile(2))
      await oldRead
      assert.equal(state.link.value.member_id, 'health-b')
      assert.equal(state.source.value.name, '合成本人 source-health-b')
      assert.equal(state.profile.value.confirmed_version, 8)
      assert.equal('profile' in state.profile.value, false)
      assert.equal(state.error.value, '')
      assert.equal(state.success.value, '')
      assert.equal(state.loading.value, false)
      assert.deepEqual(state.events, [])
      assert.deepEqual(state.routes, [])
      state.dispose()
    }
  }
})

test('关联提交途中切换成员，迟到成功不回读旧成员，迟到错误不污染当前成员', async () => {
  for (const outcome of ['success', 'error']) {
    const oldWrite = deferred()
    const reads = []
    const state = panel({
      familyProfileLink: async (id) => {
        reads.push(id)
        return id === 'health-a' ? notLinked(id) : linked(id)
      },
      familyProfile: async (id) => id === 'health-a' ? notReady : availableProfile(8),
      linkFamilyProfile: () => oldWrite.promise
    }, {
      ...candidateFamilies,
      get: async (id) => id === 'family-a'
        ? family(id, [formalMember('self-a')])
        : linkedFamily.get(id)
    })
    await state.reload()
    state.selectedKey.value = state.candidates.value[0].key
    state.confirmedIdentity.value = true
    const pending = state.associate()
    assert.equal(state.saving.value, true)
    state.props.member = selfMember('health-b')
    await nextRequests()
    if (outcome === 'error') oldWrite.reject(Object.assign(Error('旧成员私有错误'), { status: 409 }))
    else oldWrite.resolve({ member_id: 'health-a' })
    await pending
    assert.deepEqual(reads, ['health-a', 'health-b'])
    assert.equal(state.link.value.member_id, 'health-b')
    assert.equal(state.profile.value.confirmed_version, 8)
    assert.equal(state.error.value, '')
    assert.equal(state.success.value, '')
    assert.equal(state.confirmedIdentity.value, false)
    assert.equal(state.saving.value, false)
    state.dispose()
  }
})

test('组件卸载后迟到读取和写入的成功或失败均不恢复私有状态或导航', async () => {
  for (const stage of ['read', 'write']) {
    for (const outcome of ['success', 'error']) {
      const lateResponse = deferred()
      let deferRead = false
      const state = panel({
        familyProfile: () => deferRead ? lateResponse.promise : Promise.resolve(notReady),
        linkFamilyProfile: () => lateResponse.promise
      }, candidateFamilies)
      await state.reload()
      let pending
      if (stage === 'read') {
        deferRead = true
        pending = state.reload()
        await nextRequests()
      } else {
        state.selectedKey.value = state.candidates.value[0].key
        state.confirmedIdentity.value = true
        pending = state.associate()
      }
      state.dispose()
      if (outcome === 'error') lateResponse.reject(Object.assign(Error('已卸载成员私有错误'), { status: 404 }))
      else lateResponse.resolve(availableProfile(9))
      await pending
      state.consult()
      state.openArchives()
      assert.equal(state.link.value, null)
      assert.equal(state.profile.value, null)
      assert.equal(state.source.value, null)
      assert.deepEqual(state.candidates.value, [])
      assert.equal(state.selectedKey.value, '')
      assert.equal(state.confirmedIdentity.value, false)
      assert.equal(state.error.value, '')
      assert.equal(state.success.value, '')
      assert.deepEqual(state.events, [])
      assert.deepEqual(state.routes, [])
    }
  }
})
