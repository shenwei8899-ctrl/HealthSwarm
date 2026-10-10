import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { setImmediate } from 'node:timers'
import { computed, effectScope, nextTick, reactive, ref, watch } from 'vue'
import * as Vue from 'vue'
import { parse, compileScript, compileTemplate } from 'vue/compiler-sfc'
import { nutrientLabels } from '../src/utils/healthVision.js'

const source = await readFile(
  new URL('../src/components/health/HealthProfessionalProfile.vue', import.meta.url),
  'utf8'
)
const script = source
  .match(/<script setup>([\s\S]*?)<\/script>/)[1]
  .replace(/^import[\s\S]*?from ['"][^'"]+['"]\s*\n/gm, '')
const member = (id = 'health-a', scopes = ['profile_view', 'profile_edit']) => ({ id, scopes })
const current = (version = 2) => ({
  status: 'ready',
  version,
  next_version: version + 1,
  payload: { conditions: { state: 'unknown', codes: [] } },
  attestation: { attested_by: '合成专业确认人', valid_until: '2027-01-01T00:00:00+08:00' }
})
const weight = (id = 'weight-a', version = 6) => ({
  record_id: id,
  version,
  weight_kg: '62.5',
  unit: 'kg',
  measured_at: '2026-10-08T00:00:00Z',
  source: 'manual'
})
const formalSource = {
  family_id: 'family-a',
  source_member_id: 'formal-a',
  confirmed_version: 8
}
const context = (id = 'health-a', version = 2, extra = {}) => ({
  member_id: id,
  current_profile: current(version),
  formal_source: {
    status: 'ready',
    reason: null,
    family_profile_source: formalSource,
    profile: { height_cm: 168 },
    allowed_fields: ['height_cm']
  },
  weight_candidates: {
    status: 'ready',
    reason: null,
    items: [weight()],
    total: 1,
    limit: 20,
    offset: 0
  },
  ...extra
})
const metadata = {
  source_ref: '合成专业资料',
  source_version: 'source-1',
  authority_ref: '合成确认依据',
  attested_by: '合成确认人',
  attested_at: '2026-10-08T00:00:00+08:00',
  valid_until: '2027-01-01T00:00:00+08:00'
}
const unknownPayload = () =>
  Object.fromEntries(
    [
      'conditions',
      'allergies',
      'intolerances',
      'avoidances',
      'doctor_requirements',
      'preferences'
    ].map((key) => [key, { state: 'unknown', codes: [] }])
  )
const deferred = () => {
  let resolve, reject
  const promise = new Promise((finish, fail) => {
    resolve = finish
    reject = fail
  })
  return { promise, resolve, reject }
}
const settle = async () => {
  await nextTick()
  await new Promise(setImmediate)
}

/** 执行实际组件脚本及Vue watcher，不复制被测状态逻辑。 */
function panel(api = {}, options = {}) {
  const props = reactive({ member: member(), disabled: false, ...options.props })
  const user = reactive({
    uid: 'synthetic-user',
    token: 'synthetic-token',
    isLoggedIn: true,
    isAdmin: true,
    ...options.user
  })
  const events = []
  const scope = effectScope()
  let cleanup
  const factory = new Function(
    'computed',
    'onMounted',
    'onBeforeUnmount',
    'reactive',
    'ref',
    'watch',
    'useUserStore',
    'api',
    'nutrientLabels',
    'defineProps',
    'defineEmits',
    `${script}\nreturn { context, currentProfile, selectedWeight, confirmed, payloadText, metadata, ruleCode, rule, targets, pendingImport, loading, saving, calculating, error, targetError, success, sourceConflict, canRead, canImport, formal, weights, weight, busy, formLocked, sourceReady, canSubmit, reload, insertUnknownTemplate, submitImport, calculateTargets, openPlans, reasonText }`
  )
  const state = scope.run(() =>
    factory(
      computed,
      () => {},
      (fn) => {
        cleanup = fn
      },
      reactive,
      ref,
      watch,
      () => user,
      {
        profileImportContext: async (id) => context(id),
        professionalProfile: async () => current(),
        approvedQualityRules: async () => ({ status: 'ready', version: 7 }),
        personalTargets: async () => ({
          status: 'not_ready',
          reason: 'selected_weight_measurement_required'
        }),
        ...api
      },
      nutrientLabels,
      () => props,
      () =>
        (...args) =>
          events.push(args)
    )
  )
  return {
    ...state,
    props,
    user,
    events,
    dispose: () => {
      cleanup()
      scope.stop()
    }
  }
}

function prepare(state, payload = { ...unknownPayload(), weight_kg: '62.5' }) {
  Object.assign(state.metadata, metadata)
  state.payloadText.value = JSON.stringify(payload)
  state.selectedWeight.value = 'weight-a:6'
  state.confirmed.value = true
}

test('普通档案查看授权只读取专业投影，不请求管理员上下文或原始数据', async () => {
  for (const options of [
    { user: { isAdmin: false } },
    { props: { member: member('health-a', ['profile_view']) } }
  ]) {
    const calls = []
    const state = panel(
      {
        professionalProfile: async (id) => {
          calls.push(['current', id])
          return current()
        },
        profileImportContext: async () => {
          calls.push(['private-context'])
          return context()
        }
      },
      options
    )
    await state.reload()
    assert.deepEqual(calls, [['current', 'health-a']])
    assert.equal(state.context.value, null)
    assert.equal(state.canImport.value, false)
    state.dispose()
  }
  const calls = []
  const denied = panel(
    {
      professionalProfile: async () => calls.push('read'),
      profileImportContext: async () => calls.push('context')
    },
    {
      props: { member: member('health-a', ['profile_edit']) }
    }
  )
  await denied.reload()
  await denied.submitImport()
  assert.deepEqual(calls, [])
  assert.equal(denied.canRead.value, false)
  denied.dispose()
})

test('来源和体重按服务分页回读，不自动选择最新记录或确认时间', async () => {
  const calls = []
  const state = panel({
    profileImportContext: async (...args) => {
      calls.push(args)
      return context()
    }
  })
  await state.reload(20)
  assert.deepEqual(calls, [['health-a', 20, 20]])
  assert.equal(state.currentProfile.value.next_version, 3)
  assert.deepEqual(state.formal.value.profile, { height_cm: 168 })
  assert.equal(state.selectedWeight.value, '')
  assert.equal(state.confirmed.value, false)
  assert.equal(state.metadata.attested_at, '')
  assert.equal(state.payloadText.value, '')
  state.insertUnknownTemplate()
  assert.deepEqual(JSON.parse(state.payloadText.value), unknownPayload())
  assert.equal(JSON.parse(state.payloadText.value).weight_kg, undefined)
  assert.equal(state.metadata.valid_until, '')
  state.dispose()
})

test('主动选择及专业依据修改即撤回确认，不匹配体重和未知模板不发写请求', async () => {
  const writes = []
  const state = panel({ importProfessionalProfile: async (...args) => writes.push(args) })
  await state.reload()
  prepare(state)
  state.selectedWeight.value = ''
  assert.equal(state.confirmed.value, false)
  await state.submitImport()
  assert.deepEqual(writes, [])
  state.confirmed.value = true
  await state.submitImport()
  assert.match(state.error.value, /主动选择/)
  prepare(state, { ...unknownPayload(), weight_kg: 63 })
  await state.submitImport()
  assert.match(state.error.value, /不一致/)
  assert.equal(JSON.parse(state.payloadText.value).weight_kg, 63)
  assert.equal(state.pendingImport.value, null)
  assert.deepEqual(writes, [])
  prepare(state)
  state.metadata.source_version = 'source-2'
  assert.equal(state.confirmed.value, false)
  state.dispose()
})

test('导入完整包仅绑定真实来源和主动选定版本，成功回读与目标未就绪分别显示', async () => {
  const writes = [],
    reads = [],
    targetReads = []
  let imported = false
  const state = panel({
    profileImportContext: async (id) => {
      reads.push(id)
      return context(id, imported ? 3 : 2)
    },
    importProfessionalProfile: async (id, body) => {
      writes.push([id, body])
      imported = true
      return current(3)
    },
    personalTargets: async (id, body) => {
      targetReads.push([id, body])
      return { status: 'not_ready', reason: 'confirmed_conditions_and_requirements_required' }
    }
  })
  await state.reload()
  prepare(state)
  state.ruleCode.value = 'approved.test'
  await state.submitImport()
  assert.deepEqual(writes, [
    [
      'health-a',
      {
        ...metadata,
        version: 3,
        status: 'confirmed',
        payload: { ...unknownPayload(), weight_kg: '62.5' },
        family_profile_source: formalSource,
        weight_measurement_source: { record_id: 'weight-a', version: 6 }
      }
    ]
  ])
  assert.deepEqual(reads, ['health-a', 'health-a'])
  assert.deepEqual(targetReads, [
    ['health-a', { profile_version: 3, rule_code: 'approved.test', rule_version: 7 }]
  ])
  assert.match(state.success.value, /版本 3 已导入/)
  assert.equal(state.currentProfile.value.version, 3)
  assert.equal(state.targets.value.status, 'not_ready')
  assert.equal(state.pendingImport.value, null)
  assert.equal(state.confirmed.value, false)
  assert.equal(state.error.value, '')
  state.dispose()
})

test('未知HTTP导入响应冻结同版本整包，即使刷新看到更高版本也不释放原请求', async () => {
  const writes = []
  let imported = false
  const state = panel({
    profileImportContext: async (id) => context(id, imported ? 4 : 2),
    importProfessionalProfile: async (id, body) => {
      writes.push(JSON.parse(JSON.stringify(body)))
      imported = true
      if (writes.length === 1) throw Error('synthetic response lost')
      return current(4)
    }
  })
  await state.reload()
  prepare(state)
  await state.submitImport()
  assert.ok(state.pendingImport.value)
  assert.equal(state.success.value, '')
  assert.equal(state.formLocked.value, true)
  await state.reload()
  assert.equal(state.currentProfile.value.next_version, 5)
  assert.ok(state.pendingImport.value)
  state.payloadText.value = JSON.stringify({ ...unknownPayload(), weight_kg: '99' })
  state.metadata.attested_by = '不应重建请求的合成值'
  await state.submitImport()
  assert.deepEqual(writes[1], writes[0])
  assert.equal(writes[1].version, 3)
  assert.equal(writes[1].payload.weight_kg, '62.5')
  assert.equal(state.pendingImport.value, null)
  assert.match(state.success.value, /版本 3 的导入回执已确认.*版本为 4/)
  state.dispose()
})

test('已明确成功的导入回执遇到回读断线只需刷新，不伪装未知写入或重复提交', async () => {
  let imported = false
  const state = panel({
    profileImportContext: async (id) => {
      if (imported) throw Error('synthetic readback disconnected')
      return context(id)
    },
    importProfessionalProfile: async () => {
      imported = true
      return current(3)
    }
  })
  await state.reload()
  prepare(state)
  await state.submitImport()
  assert.equal(state.pendingImport.value, null)
  assert.equal(state.success.value, '')
  assert.equal(state.formLocked.value, false)
  assert.match(state.error.value, /导入回执已确认.*读取失败/)
  state.dispose()
})

test('明确成功回执和回读3到4并发更新分别展示原包版本与当前来源', async () => {
  let imported = false
  const writes = [],
    requests = []
  const state = panel({
    profileImportContext: async (id) => context(id, imported ? 4 : 2),
    importProfessionalProfile: async (id, body) => {
      writes.push(body.version)
      imported = true
      return current(4)
    },
    personalTargets: async (id, body) => {
      requests.push(body)
      return { status: 'not_ready', reason: 'personal_target_formula_not_approved' }
    }
  })
  await state.reload()
  prepare(state)
  state.ruleCode.value = 'approved-rule'
  await state.submitImport()
  assert.deepEqual(writes, [3])
  assert.equal(state.currentProfile.value.version, 4)
  assert.equal(state.pendingImport.value, null)
  assert.match(state.success.value, /版本 3 的导入回执已确认.*版本为 4.*核对当前来源/)
  assert.deepEqual(requests, [{ profile_version: 4, rule_code: 'approved-rule', rule_version: 7 }])
  state.dispose()
})

test('HTTP200缺少可核对版本或回执版本低于原包时不得释放原请求', async () => {
  for (const receipt of [{ status: 'ready' }, current(2)]) {
    const state = panel({ importProfessionalProfile: async () => receipt })
    await state.reload()
    prepare(state)
    await state.submitImport()
    assert.equal(state.pendingImport.value.version, 3)
    assert.equal(state.success.value, '')
    assert.match(state.error.value, /缺少可核对的版本/)
    state.dispose()
  }
})

test('明确版本冲突清除旧来源并要求刷新，格式拒绝允许修订而不当作未知成功', async () => {
  for (const status of [409, 422, 403]) {
    const state = panel({
      importProfessionalProfile: async () => {
        throw { status }
      }
    })
    await state.reload()
    prepare(state)
    await state.submitImport()
    assert.equal(state.pendingImport.value, null)
    assert.equal(state.success.value, '')
    assert.equal(state.confirmed.value, false)
    if (status === 409) {
      assert.equal(state.sourceConflict.value, true)
      assert.equal(state.context.value, null)
      assert.equal(state.canSubmit.value, false)
      await state.reload()
      assert.equal(state.sourceConflict.value, false)
    } else if (status === 403) {
      assert.equal(state.context.value, null)
      assert.equal(state.currentProfile.value, null)
      assert.equal(state.payloadText.value, '')
    } else {
      assert.match(state.error.value, /格式无效/)
      assert.ok(state.context.value)
    }
    state.dispose()
  }
})

test('导入回读被明确拒绝授权时清空原包及私有表单，保留拒绝原因', async () => {
  let imported = false
  const state = panel({
    profileImportContext: async () => {
      if (imported) throw { status: 403 }
      return context()
    },
    importProfessionalProfile: async () => {
      imported = true
      return current(3)
    }
  })
  await state.reload()
  prepare(state)
  await state.submitImport()
  assert.equal(state.currentProfile.value, null)
  assert.equal(state.context.value, null)
  assert.equal(state.payloadText.value, '')
  assert.equal(state.metadata.attested_by, '')
  assert.equal(state.pendingImport.value, null)
  assert.equal(state.success.value, '')
  assert.match(state.error.value, /权限不足/)
  assert.doesNotMatch(state.error.value, /结果尚未确认/)
  state.dispose()
})

test('成员切换、权限撤回、账号切换和卸载均丢弃迟到来源及私有错误', async () => {
  for (const phase of ['member', 'scope', 'account', 'unmount']) {
    for (const outcome of ['resolve', 'reject']) {
      const late = deferred()
      const state = panel({ profileImportContext: () => late.promise })
      const reading = state.reload()
      if (phase === 'member') state.props.member = member('health-b', [])
      if (phase === 'scope') state.props.member.scopes = []
      if (phase === 'account') {
        state.user.token = ''
        state.user.isLoggedIn = false
      }
      if (phase === 'unmount') state.dispose()
      if (outcome === 'resolve') late.resolve(context())
      else late.reject(Error('synthetic private error'))
      await reading
      assert.equal(state.context.value, null)
      assert.equal(state.currentProfile.value, null)
      assert.equal(state.error.value, '')
      assert.equal(state.loading.value, false)
      if (phase !== 'unmount') state.dispose()
    }
  }
})

test('写入或回读途中切换成员和卸载不能恢复旧请求、显示成功或继续读旧成员', async () => {
  for (const phase of ['write', 'readback']) {
    for (const outcome of ['member', 'unmount']) {
      const late = deferred()
      const reads = []
      let submitting = false
      const state = panel({
        profileImportContext: async (id) => {
          reads.push(id)
          if (submitting && phase === 'readback') return late.promise
          return context(id)
        },
        importProfessionalProfile: async () => {
          submitting = true
          if (phase === 'write') return late.promise
          return current(3)
        }
      })
      await state.reload()
      prepare(state)
      const writing = state.submitImport()
      await settle()
      if (outcome === 'member') state.props.member = member('health-b', [])
      else state.dispose()
      late.resolve(phase === 'write' ? current(3) : context('health-a', 3))
      await writing
      assert.equal(state.pendingImport.value, null)
      assert.equal(state.payloadText.value, '')
      assert.equal(state.currentProfile.value, null)
      assert.equal(state.success.value, '')
      assert.deepEqual(reads, phase === 'write' ? ['health-a'] : ['health-a', 'health-a'])
      if (outcome === 'member') state.dispose()
    }
  }
})

test('未明确规则代码不计算，实际版本输入不含临床参数，目标来源独立显示', async () => {
  const rules = [],
    requests = []
  const state = panel({
    approvedQualityRules: async (code) => {
      rules.push(code)
      return { status: 'ready', version: 11 }
    },
    personalTargets: async (id, data) => {
      requests.push([id, data])
      return {
        status: 'ready',
        energy_kcal: '1900',
        bounds: { protein_g: { minimum: '50', maximum: '80' } },
        units: { protein_g: 'g' },
        sources: { profile: { version: 2 }, rules: { version: 11 } }
      }
    }
  })
  await state.reload()
  await state.calculateTargets()
  assert.deepEqual(rules, [])
  state.ruleCode.value = 'professional:adult'
  await state.calculateTargets()
  assert.deepEqual(rules, ['professional:adult'])
  assert.deepEqual(requests, [
    ['health-a', { profile_version: 2, rule_code: 'professional:adult', rule_version: 11 }]
  ])
  assert.equal(state.targets.value.sources.rules.version, 11)
  state.openPlans()
  assert.deepEqual(state.events, [['plans']])
  state.ruleCode.value = 'another-rule'
  assert.equal(state.targets.value, null)
  state.openPlans()
  assert.deepEqual(state.events, [['plans']])
  state.dispose()
})

test('规则和目标迟到响应不能回填改变后的来源，权限拒绝清空旧私有投影', async () => {
  const late = deferred()
  const state = panel({ approvedQualityRules: () => late.promise })
  await state.reload()
  state.ruleCode.value = 'old-rule'
  const reading = state.calculateTargets()
  state.ruleCode.value = 'new-rule'
  late.resolve({ status: 'ready', version: 7 })
  await reading
  assert.equal(state.rule.value, null)
  assert.equal(state.targets.value, null)
  assert.equal(state.calculating.value, false)
  state.dispose()
  const denied = panel({
    personalTargets: async () => {
      throw { status: 403 }
    }
  })
  await denied.reload()
  prepare(denied)
  denied.ruleCode.value = 'approved-rule'
  await denied.calculateTargets()
  assert.equal(denied.currentProfile.value, null)
  assert.equal(denied.context.value, null)
  assert.equal(denied.payloadText.value, '')
  assert.match(denied.targetError.value, /权限不足/)
  denied.dispose()
})

test('真实模板编译包含显式版本选择、同一人确认及独立目标状态', () => {
  const { descriptor } = parse(source)
  const bindings = compileScript(descriptor, { id: 'professional-profile-test' }).bindings
  const compiled = compileTemplate({
    source: descriptor.template.content,
    filename: 'HealthProfessionalProfile.vue',
    id: 'professional-profile-test',
    compilerOptions: { bindingMetadata: bindings }
  })
  assert.deepEqual(compiled.errors, [])
  const select = descriptor.template.content.match(
    /<a-select\s[\s\S]*?aria-label="选择本人实测体重记录版本"[\s\S]*?\/>/
  )[0]
  const selector = compileTemplate({
    source: select,
    filename: 'HealthProfessionalProfile.vue',
    id: 'weight-selector-test',
    compilerOptions: { mode: 'function' }
  })
  assert.deepEqual(selector.errors, [])
  const render = new Function('Vue', selector.code)(Vue)
  const vnode = render(
    {
      selectedWeight: '',
      formLocked: false,
      weights: context().weight_candidates
    },
    []
  )
  assert.equal(vnode.props.value, '')
  assert.equal(vnode.props.disabled, false)
  assert.equal(vnode.props.options[0].value, 'weight-a:6')
  assert.match(vnode.props.options[0].label, /62.5 kg.*版本 6/)
})

test('目标实际模板保留零值、单位和版本，未就绪只显示下一步原因', () => {
  const { descriptor } = parse(source)
  const targetBlock = descriptor.template.content.match(
    /<section class="target-block">[\s\S]*?<\/section>/
  )[0]
  const compiled = compileTemplate({
    source: targetBlock,
    filename: 'HealthProfessionalProfile.vue',
    id: 'target-status-test',
    compilerOptions: { mode: 'function' }
  })
  assert.deepEqual(compiled.errors, [])
  const render = new Function('Vue', compiled.code)(Vue)
  const state = panel()
  const textOf = (vnode) => {
    if (typeof vnode === 'string') return vnode
    if (!vnode || typeof vnode !== 'object') return ''
    const children = Array.isArray(vnode.children)
      ? vnode.children
      : typeof vnode.children === 'object' && vnode.children?.default
        ? vnode.children.default()
        : [vnode.children]
    return [vnode.props?.message, ...children.map(textOf)].filter(Boolean).join(' ')
  }
  const context = {
    busy: false,
    calculating: false,
    currentProfile: current(),
    ruleCode: 'approved-rule',
    rule: { status: 'ready', version: 7 },
    targetError: '',
    reasonText: state.reasonText,
    nutrientLabels,
    calculateTargets: () => {},
    openPlans: () => {}
  }
  context.targets = {
    status: 'ready',
    energy_kcal: '1900',
    bounds: { protein_g: { minimum: '0', maximum: '80' } },
    units: { protein_g: 'g' },
    sources: { profile: { version: 2 }, rules: { version: 7 } }
  }
  const readyText = textOf(render(context, []))
  assert.match(readyText, /1900.*kcal/)
  assert.match(readyText, /0–80.*g/)
  assert.match(readyText, /蛋白质.*0–80/)
  assert.doesNotMatch(readyText, /\[\s*"[^"]+"\s*,\s*"[^"]+"\s*\]/)
  assert.match(readyText, /专业档案版本 2.*批准规则版本 7/)
  context.targets = { status: 'not_ready', reason: 'selected_weight_measurement_required' }
  const unavailableText = textOf(render(context, []))
  assert.match(unavailableText, /明确选定的本人实测体重版本/)
  assert.doesNotMatch(unavailableText, /当前目标已计算/)
  state.dispose()
})

test('API封装忠实发送分页、原导入整包和目标版本，规则代码按路径编码', async () => {
  const text = await readFile(new URL('../src/apis/health_vision_api.js', import.meta.url), 'utf8')
  const noop = () => {}
  const api = new Function(
    'apiGet',
    'apiPost',
    'apiPut',
    'apiDelete',
    'apiRequest',
    'buildQuery',
    `${text.replace(/^import.*\r?\n/, '').replace('export const', 'const')}\nreturn healthVisionApi`
  )(
    (path) => path,
    (path, body, options) => ({ path, body, options }),
    noop,
    noop,
    noop,
    (data) => new URLSearchParams(data).toString()
  )
  assert.equal(
    api.profileImportContext('a', 20, 40),
    '/api/health/v1/members/a/profile-import-context?limit=20&offset=40'
  )
  assert.equal(
    api.professionalProfile('a'),
    '/api/health/v1/members/a/external-profile-versions/current'
  )
  assert.equal(api.approvedQualityRules('rule:a'), '/api/health/v1/approved-quality-rules/rule%3Aa')
  const body = { version: 3, payload: unknownPayload() }
  assert.deepEqual(api.importProfessionalProfile('a', body), {
    path: '/api/health/v1/members/a/external-profile-versions',
    body,
    options: undefined
  })
  const versions = { profile_version: 3, rule_code: 'rule:a', rule_version: 2 }
  assert.deepEqual(api.personalTargets('a', versions), {
    path: '/api/health/v1/members/a/nutrition-targets',
    body: versions,
    options: undefined
  })
  assert.equal(api.mealPlanApproval('p', 6), '/api/health/v1/meal-plans/p/approval-state?version=6')
})
