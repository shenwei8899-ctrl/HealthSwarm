import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { parse, compileScript } from 'vue/compiler-sfc'
import * as vue from 'vue'
import * as fields from '../../src/utils/familyArchives.js'

// 执行正式 SFC 的 setup 与 Vue watcher，API 延迟仅控制外部响应顺序。
function panel(
  name,
  initialProps,
  familyApi,
  user = vue.reactive({ uid: 'owner', isAdmin: false })
) {
  const source = readFileSync(
    new URL(`../../src/components/family/${name}.vue`, import.meta.url),
    'utf8'
  )
  const { descriptor } = parse(source)
  const script = compileScript(descriptor, { id: name })
    .content.replace(/^import[\s\S]*?from\s*['"][^'"]+['"];?\s*$/gm, '')
    .replace('export default', 'return')
  const cleanups = [],
    downloads = [],
    emitted = []
  const sandbox = {
    computed: vue.computed,
    reactive: vue.reactive,
    ref: vue.ref,
    watch: vue.watch,
    ...fields,
    familyApi,
    useUserStore: () => user,
    Plus: null,
    FamilyChart: null,
    FamilyStructuredField: null,
    FamilyGuardianPanel: null,
    useRouter: () => ({ push() {} }),
    message: { success() {}, error() {}, info() {} },
    onBeforeUnmount: (callback) => cleanups.push(callback),
    downloadFamilyJson: (...args) => downloads.push(args)
  }
  const component = new Function(...Object.keys(sandbox), script)(...Object.values(sandbox))
  const props = vue.reactive(initialProps),
    scope = vue.effectScope()
  const state = scope.run(() =>
    component.setup(props, { expose() {}, emit: (...args) => emitted.push(args) })
  )
  return {
    props,
    state,
    downloads,
    emitted,
    close() {
      cleanups.forEach((callback) => callback())
      scope.stop()
    }
  }
}

function deferred() {
  let resolve
  const promise = new Promise((done) => {
    resolve = done
  })
  return { promise, resolve }
}
function member(overrides = {}) {
  return {
    id: 'synthetic-member',
    name: '合成成员',
    version: 1,
    is_self: true,
    is_active: true,
    allowed_fields: ['goal', 'weight'],
    editable_fields: ['goal', 'weight'],
    profile: { goal: '旧目标' },
    ...overrides
  }
}
const emptyMeasurements = { items: [], trend: [], total: 0 }

test('正式档案面板：同成员刷新保留草稿和起始版本，冲突拒写，失权清理草稿', async () => {
  let writes = 0
  const p = panel(
    'FamilyProfilePanel',
    { familyId: 'f', member: member() },
    {
      updateProfile: async () => {
        writes++
      }
    }
  )
  try {
    p.state.openEditor()
    p.state.draft.goal = '未保存目标'
    p.props.member = member({ version: 2, profile: { goal: '远端新目标' } })
    await vue.nextTick()
    assert.equal(p.state.editing.value, true)
    assert.equal(p.state.draft.goal, '未保存目标')
    assert.equal(p.state.baseVersion.value, 1)
    await p.state.save()
    assert.equal(writes, 0)
    p.props.member = member({ allowed_fields: [], editable_fields: [], profile: {} })
    await vue.nextTick()
    assert.equal(p.state.editing.value, false)
    assert.equal('goal' in p.state.draft, false)
    assert.equal('goal' in p.state.original.value, false)
  } finally {
    p.close()
  }
})

test('正式历史面板：乱序分页只展示最后所选页，失权后的迟到响应不得回填', async () => {
  const pending = []
  const p = panel(
    'FamilyProfilePanel',
    { familyId: 'f', member: member() },
    {
      history: () => {
        const request = deferred()
        pending.push(request)
        return request.promise
      }
    }
  )
  try {
    const second = p.state.showHistory(2),
      third = p.state.showHistory(3)
    pending[1].resolve({ items: [{ version: 3 }], total: 80 })
    await third
    pending[0].resolve({ items: [{ version: 2 }], total: 80 })
    await second
    assert.equal(p.state.historyPage.value, 3)
    assert.deepEqual(p.state.history.value, [{ version: 3 }])
    const late = p.state.showHistory(4)
    p.props.member = member({ allowed_fields: [], editable_fields: [], profile: {} })
    await vue.nextTick()
    pending[2].resolve({ items: [{ profile: { goal: '撤权资料' } }], total: 80 })
    await late
    assert.equal(p.state.historyOpen.value, false)
    assert.deepEqual(p.state.history.value, [])
  } finally {
    p.close()
  }
})

test('正式指标面板：刷新保留录入草稿，失权取消在途导出并清理展示', async () => {
  const exported = deferred()
  const p = panel(
    'FamilyMetricsPanel',
    { familyId: 'f', member: member(), revision: 0 },
    {
      measurements: async () => emptyMeasurements,
      exportMeasurements: () => exported.promise
    }
  )
  try {
    await vue.nextTick()
    p.state.openNew()
    p.state.draft.values.weight = 61
    p.props.member = member({ version: 2 })
    p.props.revision++
    await vue.nextTick()
    assert.equal(p.state.dialogOpen.value, true)
    assert.equal(p.state.draft.values.weight, 61)
    const late = p.state.exportRecords()
    p.props.member = member({ allowed_fields: [], editable_fields: [], profile: {} })
    await vue.nextTick()
    exported.resolve({ items: [{ values: { weight: 61 } }], total: 1 })
    await late
    assert.equal(p.downloads.length, 0)
    assert.equal(p.state.dialogOpen.value, false)
    assert.deepEqual(p.state.draft.values, {})
    assert.deepEqual(p.state.records.value, [])
  } finally {
    p.close()
  }
})

test('正式指标面板：最后一个指标撤权，即使kind不变，迟到读取也不能回填', async () => {
  const read = deferred()
  const p = panel(
    'FamilyMetricsPanel',
    { familyId: 'f', member: member(), revision: 0 },
    { measurements: () => read.promise }
  )
  try {
    p.props.member = member({ allowed_fields: [], editable_fields: [], profile: {} })
    await vue.nextTick()
    read.resolve({ items: [{ values: { weight: 61 } }], trend: [], total: 1 })
    await vue.nextTick()
    assert.equal(p.state.kind.value, 'weight')
    assert.deepEqual(p.state.records.value, [])
    assert.equal(p.state.loading.value, false)
  } finally {
    p.close()
  }
})

test('正式授权面板：撤销邀请后迟到生成响应不重新展示失效代码', async () => {
  const invitation = deferred(),
    invited = member({ claimed: false, is_self: false })
  const p = panel(
    'FamilyAuthorizationPanel',
    { family: { id: 'f', members: [invited], is_owner: true } },
    {
      invite: () => invitation.promise,
      revokeInvitation: async () => ({ revoked: true })
    }
  )
  try {
    const pending = p.state.invite(invited)
    await p.state.revokeInvite(invited)
    invitation.resolve({ code: 'synthetic-revoked-code' })
    await pending
    assert.equal(p.state.inviteOpen.value, false)
    assert.equal(p.state.invitation.value, null)
  } finally {
    p.close()
  }
})

test('家庭设置：真实响应式设置可编辑，保留原版本，失权后清理在途状态', async () => {
  const write = deferred(),
    calls = []
  const p = panel(
    'FamilySettingsPanel',
    {
      family: { id: 'f', name: '家庭', version: 1, is_owner: true, settings: { cook: '原做饭人' } }
    },
    {
      updateFamily: (...args) => {
        calls.push(args)
        return write.promise
      }
    }
  )
  try {
    p.state.openEditor()
    p.state.draft.cook = '新做饭人'
    assert.equal(p.props.family.settings.cook, '原做饭人')
    p.props.family = { ...p.props.family, version: 2, settings: { cook: '远端做饭人' } }
    await vue.nextTick()
    const saving = p.state.save()
    assert.equal(calls[0][1].expected_version, 1)
    p.props.family = { ...p.props.family, is_owner: false }
    await vue.nextTick()
    write.resolve({ version: 3 })
    await saving
    assert.equal(p.state.editing.value, false)
    assert.deepEqual(Object.keys(p.state.draft), [])
    assert.deepEqual(p.emitted, [])
  } finally {
    p.close()
  }
})

test('结构化编辑：修改响应式列表不改变原档案，未知与明确无分别提交', () => {
  const p = panel(
    'FamilyStructuredField',
    { fieldKey: 'medication_records', modelValue: [{ description: '原记录', dose: null }] },
    {}
  )
  try {
    p.state.update(0, 'dose', '自述剂量')
    assert.equal(p.props.modelValue[0].dose, null)
    assert.equal(p.emitted[0][1][0].dose, '自述剂量')
    p.state.setState('none')
    p.state.setState('unknown')
    assert.deepEqual(p.emitted[1][1], [])
    assert.equal(p.emitted[2][1], null)
  } finally {
    p.close()
  }
})

test('监护审核：按真实管理员权限加载，失权后迟到队列不可回填', async () => {
  const read = deferred(),
    user = vue.reactive({ uid: 'reviewer', isAdmin: true })
  const p = panel(
    'FamilyGuardianPanel',
    { family: { id: 'f', members: [] } },
    { guardianRequests: () => read.promise },
    user
  )
  try {
    assert.equal(p.state.isAdmin.value, true)
    user.isAdmin = false
    await vue.nextTick()
    read.resolve([{ member_name: '不再可见的申请' }])
    await vue.nextTick()
    await vue.nextTick()
    assert.equal(p.state.isAdmin.value, false)
    assert.deepEqual(p.state.requests.value, [])
  } finally {
    p.close()
  }
})
