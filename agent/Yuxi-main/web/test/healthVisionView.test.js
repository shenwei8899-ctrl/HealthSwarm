import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { setImmediate } from 'node:timers'
import { ref, computed, watch, effectScope, nextTick } from 'vue'
import * as Vue from 'vue'
import { parse, compileScript, compileTemplate } from 'vue/compiler-sfc'
import * as helpers from '../src/utils/healthVision.js'

const source = await readFile(new URL('../src/views/HealthVisionView.vue', import.meta.url), 'utf8')

test('专业目标与餐单失效入口通过实际组件事件切换同一成员分区', () => {
  const state = workbench({})
  const context = { memberId: 'member-a', member: { id: 'member-a', scopes: [] }, config: {}, busy: false, confirming: false }
  Object.defineProperty(context, 'activeTab', {
    get: () => state.activeTab.value,
    set: (value) => { state.activeTab.value = value }
  })
  for (const [component, event, expected] of [
    ['HealthProfessionalProfile', 'onPlans', 'plans'],
    ['HealthMealPlans', 'onProfile', 'profile']
  ]) {
    const fragment = source.match(new RegExp(`<${component}[\\s\\S]*?\\/>`))[0]
      .replace(/\s+v-else-if="[^"]*"/, '')
    const compiled = compileTemplate({ source: fragment, filename: 'HealthVisionView.vue', id: component, compilerOptions: { mode: 'function' } })
    assert.deepEqual(compiled.errors, [])
    const render = new Function('Vue', compiled.code)(Vue)
    const vnode = render(context, [])
    vnode.props[event]()
    assert.equal(state.tab.value, expected)
    assert.equal(vnode.props.member?.id || vnode.props['member-id'], 'member-a')
  }
  state.dispose()
})
const script = source
  .match(/<script setup>([\s\S]*?)<\/script>/)[1]
  .replace(/^import[\s\S]*?from ['"][^'"]+['"]\s*\n/gm, '')

/** 执行真实页面脚本及 Vue 状态，不另写一套业务流程作为 oracle。 */
function workbench(api, options = {}) {
  const scope = effectScope()
  const noop = () => {}
  const unmount = []
  const factory = new Function(
    'ref',
    'computed',
    'watch',
    'onMounted',
    'onBeforeUnmount',
    'useUserStore',
    'useRouter',
    'api',
    'message',
    'Modal',
    ...Object.keys(helpers),
    `${script}\nreturn { tab, activeTab, memberId, busy, selected, manualDraft, calculation, dirty, perform, changed, confirming, confirmDraft, reviewed, excludeReportPages, members, config, cloudConsent, reprocessRequest, reprocessReportPage, canReprocessReport, files, uploads, prepareReport, reportRotation, deskewAngle, preparedPreview, preparedPreviewOpen, showPreparedPage, clearPreparedPreview, startRecognition, selectFiles, consultationOpen, consultationConsent, consultationMode, consultationError, consultationSourceInvalidated, consultationRequest, openConsultation, canConsult, enterConsultation, retryJob: typeof retryJob === 'function' ? retryJob : undefined }`
  )
  const state = scope.run(() =>
    factory(
      ref,
      computed,
      watch,
      noop,
      (fn) => unmount.push(fn),
      () => ({ isAdmin: true }),
      () => ({ push: api.navigate || noop }),
      { list: async () => ({ jobs: [], drafts: [] }), records: async () => [], ...api },
      { error: noop, warning: noop, success: noop },
      { confirm: options.confirm || noop },
      ...Object.values(helpers)
    )
  )
  return {
    ...state,
    dispose: () => {
      unmount.forEach((fn) => fn())
      scope.stop()
    }
  }
}

/** 独立给定当前成员与已审批模型事实，避免测试自动生成期望请求。 */
async function consultationWorkbench(overrides) {
  const state = workbench(overrides)
  state.memberId.value = 'member-a'
  state.members.value = [{ id: 'member-a', scopes: ['ai_use', 'report_view', 'diet_edit'] }]
  state.config.value = {
    policy_version: 'policy-test',
    consultation: { available: true, processor: 'test-provider' }
  }
  await nextTick()
  await new Promise(setImmediate)
  return state
}

test('咨询同意说明披露体重、血压、血糖和同条血脂四项的实测范围、单位与发送字段', () => {
  const { descriptor } = parse(source)
  const disclosure = descriptor.template.content.match(/<p>\s*咨询会将[\s\S]*?<\/p>/)[0]
  const compiled = compileTemplate({
    source: disclosure,
    filename: 'HealthVisionView.vue',
    id: 'measurement-consent-test',
    compilerOptions: { mode: 'function' }
  })
  assert.deepEqual(compiled.errors, [])
  const render = new Function('Vue', compiled.code)(Vue)
  const text = render({}, []).children
  assert.match(text, /实测体重、血压、血糖、血脂四项发送给已审批模型/)
  assert.match(text, /实测与档案确认版本分开/)
  assert.match(text, /体重、血压、血糖、血脂各仅包含近30个北京时间自然日最多20条记录/)
  assert.match(text, /体重保留原值与kg/)
  assert.match(text, /血压保留成对收缩压、舒张压与mmHg/)
  assert.match(text, /血糖保留原值、mmol\/L及空腹、餐后2小时或随机的测量条件/)
  assert.match(text, /血脂保留同条总胆固醇、甘油三酯、高密度脂蛋白、低密度脂蛋白原值与mmol\/L/)
  assert.match(text, /均含测量时间、来源、记录ID和版本/)
  assert.match(text, /实测备注、血压和血脂测量条件及更正历史不发送/)
  assert.match(text, /营养安全评估与21天控糖仍未就绪/)
})

test('新建咨询必须明确同意，未知响应重试复用同一幂等键，成功后换键', async () => {
  const requests = [],
    routes = [],
    consents = []
  const state = await consultationWorkbench({
    consent: async (id, data) => consents.push({ id, data }),
    createConsultation: async (id, data) => {
      requests.push({ id, data })
      if (requests.length === 1) throw new Error('synthetic unknown response')
      return { member_id: id, agent_slug: 'health-consultation', thread_id: 'new-thread' }
    },
    createDailyConsultation: async () => assert.fail('新建不能调用每日入口'),
    navigate: async (route) => routes.push(route)
  })
  state.openConsultation('new')
  await state.enterConsultation()
  assert.equal(requests.length, 0)
  state.consultationConsent.value = true
  await state.enterConsultation()
  assert.equal(state.consultationError.value, 'synthetic unknown response')
  await state.enterConsultation()
  assert.deepEqual(requests[0], requests[1])
  assert.match(requests[0].data.client_request_id, /^[0-9a-f-]{36}$/)
  assert.equal(consents[0].data.purpose, 'consultation')
  assert.equal(state.consultationRequest.value, null)
  assert.equal(routes.length, 1)
  state.openConsultation('new')
  assert.equal(state.consultationConsent.value, false)
  state.consultationConsent.value = true
  await state.enterConsultation()
  assert.notEqual(requests[2].data.client_request_id, requests[0].data.client_request_id)
  state.dispose()
})

test('新建未知响应后切换每日入口，再回新建重试仍使用原幂等键', async () => {
  const requests = [],
    routes = []
  let daily = 0
  const state = await consultationWorkbench({
    consent: async () => {},
    createConsultation: async (id, data) => {
      requests.push({ id, data })
      if (requests.length === 1) throw new Error('synthetic unknown response')
      return { member_id: id, agent_slug: 'health-consultation', thread_id: 'recovered-thread' }
    },
    createDailyConsultation: async () => {
      daily++
      throw Object.assign(new Error('请求已失效'), { status: 410 })
    },
    navigate: async (route) => routes.push(route)
  })
  state.openConsultation('new')
  state.consultationConsent.value = true
  await state.enterConsultation()
  const original = state.consultationRequest.value.client_request_id
  state.openConsultation()
  assert.equal(state.consultationRequest.value?.client_request_id, original)
  assert.equal(state.consultationConsent.value, false)
  state.consultationConsent.value = true
  await state.enterConsultation()
  assert.equal(daily, 1)
  assert.equal(state.consultationRequest.value?.client_request_id, original)
  state.openConsultation('new')
  assert.equal(state.consultationRequest.value?.client_request_id, original)
  await state.enterConsultation()
  assert.equal(requests.length, 1)
  state.consultationConsent.value = true
  await state.enterConsultation()
  assert.deepEqual(requests[0], requests[1])
  assert.equal(state.consultationRequest.value, null)
  assert.deepEqual(routes, [
    { name: 'AgentCompWithThreadId', params: { thread_id: 'recovered-thread' } }
  ])
  state.dispose()
})

test('未知新建请求重试明确410后，显式新建入口和重新同意才使用新键', async () => {
  const requests = [],
    consents = [],
    routes = []
  const state = await consultationWorkbench({
    consent: async (id, data) => consents.push({ id, data }),
    createConsultation: async (id, data) => {
      requests.push({ id, data })
      if (requests.length === 1) throw new Error('synthetic unknown response')
      if (requests.length === 2) throw Object.assign(new Error('请求已失效'), { status: 410 })
      return { member_id: id, agent_slug: 'health-consultation', thread_id: 'fresh-profile-thread' }
    },
    createDailyConsultation: async () => assert.fail('新建恢复不能调用每日入口'),
    navigate: async (route) => routes.push(route)
  })
  state.openConsultation('new')
  state.consultationConsent.value = true
  await state.enterConsultation()
  const original = state.consultationRequest.value.client_request_id
  assert.equal(state.consultationSourceInvalidated.value, false)
  await state.enterConsultation()
  assert.deepEqual(requests[0], requests[1])
  assert.equal(state.consultationRequest.value, null)
  assert.equal(state.consultationSourceInvalidated.value, true)
  assert.equal(state.consultationConsent.value, false)
  assert.deepEqual(routes, [])
  state.consultationConsent.value = true
  await state.enterConsultation()
  assert.equal(requests.length, 2)
  assert.equal(consents.length, 2)

  const { descriptor } = parse(source)
  const bindings = compileScript(descriptor, { id: 'consultation-recovery-test' }).bindings
  const alert = descriptor.template.content.match(
    /<a-alert v-if="consultationError"[\s\S]*?<\/a-alert>/
  )[0]
  const compiled = compileTemplate({
    source: alert,
    filename: 'HealthVisionView.vue',
    id: 'consultation-recovery-test',
    compilerOptions: { bindingMetadata: bindings, mode: 'function' }
  })
  assert.deepEqual(compiled.errors, [])
  const render = new Function('Vue', compiled.code)(Vue)
  const vnode = render(
    {},
    [],
    {},
    {
      ...state,
      consultationError: state.consultationError.value,
      consultationSourceInvalidated: true,
      consultationMode: 'new',
      busy: false
    }
  )
  assert.equal(typeof vnode.children.action, 'function')
  vnode.children.action()[0].props.onClick()
  assert.equal(state.consultationMode.value, 'new')
  assert.equal(state.consultationSourceInvalidated.value, false)
  assert.equal(state.consultationConsent.value, false)
  await state.enterConsultation()
  assert.equal(requests.length, 2)
  state.consultationConsent.value = true
  await state.enterConsultation()
  assert.notEqual(requests[2].data.client_request_id, original)
  assert.equal(consents.length, 3)
  assert.deepEqual(consents[2], {
    id: 'member-a',
    data: {
      purpose: 'consultation',
      accepted: true,
      processor: 'test-provider',
      policy_version: 'policy-test'
    }
  })
  assert.equal(state.consultationRequest.value, null)
  assert.deepEqual(routes, [
    { name: 'AgentCompWithThreadId', params: { thread_id: 'fresh-profile-thread' } }
  ])
  state.dispose()
})

test('每日咨询来源失效保留提示，只有用户明确新建才创建新线程', async () => {
  let fresh = 0
  const state = await consultationWorkbench({
    consent: async () => {},
    createDailyConsultation: async () => {
      throw Object.assign(new Error('请求已失效'), { status: 410 })
    },
    createConsultation: async (id) => {
      fresh++
      return { member_id: id, agent_slug: 'health-consultation', thread_id: 'replacement-thread' }
    }
  })
  state.openConsultation()
  state.consultationConsent.value = true
  await state.enterConsultation()
  assert.equal(fresh, 0)
  assert.equal(state.consultationOpen.value, true)
  assert.equal(state.consultationSourceInvalidated.value, true)
  assert.match(state.consultationError.value, /资料已变化.*新建咨询/)
  state.openConsultation('new')
  await state.enterConsultation()
  assert.equal(fresh, 0)
  state.consultationConsent.value = true
  await state.enterConsultation()
  assert.equal(fresh, 1)
  state.dispose()
})

test('新咨询错成员响应不得导航', async () => {
  const state = await consultationWorkbench({
    consent: async () => {},
    createConsultation: async () => ({
      member_id: 'member-b',
      agent_slug: 'health-consultation',
      thread_id: 'wrong-thread'
    }),
    navigate: async () => assert.fail('错成员不能导航')
  })
  state.openConsultation('new')
  state.consultationConsent.value = true
  await state.enterConsultation()
  assert.match(state.consultationError.value, /绑定不一致/)
  assert.equal(state.consultationOpen.value, true)
  state.dispose()
})

test('切换成员和卸载后，新咨询迟到错误不写回旧提示或导航', async () => {
  for (const change of ['member', 'unmount']) {
    let rejectBinding
    const state = await consultationWorkbench({
      consent: async () => {},
      createConsultation: () =>
        new Promise((_, reject) => {
          rejectBinding = reject
        }),
      navigate: async () => assert.fail('迟到响应不能导航')
    })
    state.openConsultation('new')
    state.consultationConsent.value = true
    const operation = state.enterConsultation()
    await new Promise(setImmediate)
    assert.ok(state.consultationRequest.value)
    state.consultationError.value = '上一轮资料已变化'
    state.consultationSourceInvalidated.value = true
    if (change === 'member') {
      state.memberId.value = 'member-b'
      await nextTick()
    } else state.dispose()
    assert.equal(state.consultationOpen.value, false)
    assert.equal(state.consultationConsent.value, false)
    assert.equal(state.consultationRequest.value, null)
    assert.equal(state.consultationMode.value, 'daily')
    assert.equal(state.consultationError.value, '')
    assert.equal(state.consultationSourceInvalidated.value, false)
    rejectBinding(Object.assign(new Error('old private error'), { status: 410 }))
    await operation
    assert.equal(state.consultationError.value, '')
    assert.equal(state.consultationSourceInvalidated.value, false)
    if (change === 'member') state.dispose()
  }
})

test('实际重试按钮模板不依赖组件 crypto，发送 UUID 后刷新任务', async () => {
  const requests = []
  const refreshed = []
  const state = workbench({
    retry: async (...args) => requests.push(args),
    list: async (id) => {
      refreshed.push(id)
      return { jobs: [], drafts: [] }
    }
  })
  state.memberId.value = 'synthetic-member'
  await nextTick()
  await new Promise(setImmediate)
  refreshed.length = 0
  const { descriptor } = parse(source)
  const bindings = compileScript(descriptor, { id: 'retry-test' }).bindings
  const button = descriptor.template.content.match(
    /<a-button\s+v-if="\['failed', 'cancelled'\][\s\S]*?<\/a-button\s*>/
  )[0]
  const compiled = compileTemplate({
    source: button,
    filename: 'HealthVisionView.vue',
    id: 'retry-test',
    compilerOptions: { bindingMetadata: bindings, mode: 'function' }
  })
  assert.deepEqual(compiled.errors, [])
  const render = new Function('Vue', compiled.code)(Vue)
  const job = { task_id: 'synthetic-failed-task', execution_status: 'failed' }
  const vnode = render({ job }, [], {}, { ...state, busy: false })
  await vnode.props.onClick()
  assert.equal(requests.length, 1)
  assert.equal(requests[0][0], job.task_id)
  assert.match(
    requests[0][1].client_request_id,
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/
  )
  assert.equal(state.busy.value, false)
  assert.deepEqual(refreshed, ['synthetic-member'])
  state.dispose()
})

test('识别重试未知响应与回读失败均复用父任务请求键，确认后才释放', async () => {
  const requests = []
  let failRead = false
  const state = workbench({
    retry: async (id, data) => {
      requests.push({ id, key: data.client_request_id })
      if (requests.length === 1) throw new Error('synthetic lost response')
      failRead = requests.length === 2
      return { task_id: 'same-retry-task' }
    },
    list: async () => {
      if (failRead) throw new Error('synthetic list unavailable')
      return { jobs: [], drafts: [] }
    }
  })
  state.memberId.value = 'member-a'
  await nextTick()
  await new Promise(setImmediate)
  const job = { task_id: 'failed-parent', execution_status: 'failed' }
  await state.retryJob(job)
  state.tab.value = 'meal'
  await nextTick()
  state.tab.value = 'report'
  state.memberId.value = 'member-b'
  await nextTick()
  await new Promise(setImmediate)
  state.memberId.value = 'member-a'
  await nextTick()
  await new Promise(setImmediate)
  await state.retryJob(job)
  await state.retryJob(job)
  assert.equal(requests.length, 3)
  assert.equal(new Set(requests.map((request) => request.key)).size, 1)
  await state.retryJob(job)
  assert.notEqual(requests[3].key, requests[0].key)
  state.dispose()
})

test('识别重试的迟到成员列表不释放未知父任务键', async () => {
  const requests = []
  let readStarted,
    finishRead,
    deferRead = false
  const reading = new Promise((resolve) => {
    readStarted = resolve
  })
  const state = workbench({
    retry: async (id, data) => {
      requests.push(data.client_request_id)
      return { task_id: 'same-child' }
    },
    list: async () => {
      if (deferRead) {
        deferRead = false
        readStarted()
        return new Promise((resolve) => {
          finishRead = resolve
        })
      }
      return { jobs: [], drafts: [] }
    }
  })
  state.memberId.value = 'member-a'
  await nextTick()
  await new Promise(setImmediate)
  deferRead = true
  const job = { task_id: 'failed-parent', execution_status: 'failed' }
  const retrying = state.retryJob(job)
  await reading
  state.memberId.value = 'member-b'
  await nextTick()
  finishRead({ jobs: [], drafts: [] })
  await retrying
  state.memberId.value = 'member-a'
  await nextTick()
  await new Promise(setImmediate)
  await state.retryJob(job)
  assert.equal(requests.length, 2)
  assert.equal(requests[0], requests[1])
  state.dispose()
})

test('确认弹窗锁定成员选择，成员变化或卸载后不提交与回填旧草稿', async () => {
  const { descriptor } = parse(source)
  const selector = descriptor.template.content.match(
    /<a-select\s+v-model:value="memberId"[\s\S]*?<\/a-select\s*>/
  )[0]
  const compiled = compileTemplate({
    source: selector,
    filename: 'HealthVisionView.vue',
    id: 'confirm-member',
    compilerOptions: { mode: 'function' }
  })
  assert.deepEqual(compiled.errors, [])
  const render = new Function('Vue', compiled.code)(Vue)
  for (const confirming of [false, true]) {
    const vnode = render({ memberId: 'member-a', members: [], busy: false, confirming }, [])
    assert.equal(vnode.props.disabled, confirming)
  }
  for (const phase of ['before', 'after-confirm', 'after-read', 'unmount', 'unchanged']) {
    let modal, releaseConfirm, releaseRead
    const calls = []
    const state = workbench(
      {
        confirm: async (...args) => {
          calls.push(['confirm', ...args])
          if (phase === 'after-confirm')
            await new Promise((resolve) => {
              releaseConfirm = resolve
            })
        },
        draft: async () => {
          calls.push(['read'])
          if (phase === 'after-read')
            await new Promise((resolve) => {
              releaseRead = resolve
            })
          return {
            id: 'draft-a',
            member_id: 'member-a',
            kind: 'report',
            version: 2,
            review_status: 'confirmed'
          }
        }
      },
      {
        confirm: (options) => {
          modal = options
          return { destroy() {} }
        }
      }
    )
    state.memberId.value = 'member-a'
    await nextTick()
    await new Promise(setImmediate)
    state.selected.value = {
      id: 'draft-a',
      member_id: 'member-a',
      kind: 'report',
      version: 1,
      payload: { pages: [] }
    }
    state.reviewed.value = true
    state.confirmDraft()
    assert.equal(state.confirming.value, true)
    if (phase === 'before') state.memberId.value = 'member-b'
    if (phase === 'unmount') state.dispose()
    const operation = modal.onOk()
    await new Promise(setImmediate)
    if (phase === 'after-confirm' || phase === 'after-read') {
      state.memberId.value = 'member-b'
      await nextTick()
      if (phase === 'after-confirm') releaseConfirm()
      else releaseRead()
    }
    await operation
    if (phase === 'before' || phase === 'unmount') assert.deepEqual(calls, [])
    if (phase === 'after-confirm') assert.equal(calls.length, 1)
    if (phase === 'after-read') assert.equal(calls.length, 2)
    if (phase === 'unchanged') {
      assert.equal(state.memberId.value, 'member-a')
      assert.equal(state.selected.value.member_id, 'member-a')
      assert.equal(state.selected.value.version, 2)
    } else if (phase !== 'unmount') assert.equal(state.selected.value, null)
    if (phase !== 'unmount') state.dispose()
  }
})

test('咨询未启用或无 AI 授权时不能同意和创建会话', async () => {
  let calls = 0
  const state = workbench({
    consent: async () => calls++,
    createDailyConsultation: async () => calls++
  })
  state.memberId.value = 'member-a'
  state.members.value = [{ id: 'member-a', scopes: ['ai_use', 'report_view', 'diet_edit'] }]
  await nextTick()
  await new Promise(setImmediate)
  state.consultationConsent.value = true
  state.config.value = { consultation: { available: false } }
  await state.enterConsultation()
  assert.equal(calls, 0)
  state.config.value.consultation.available = true
  state.members.value[0].scopes = []
  await state.enterConsultation()
  assert.equal(calls, 0)
  state.dispose()
})

test('咨询使用单独用途同意，未知响应重试复用每日入口再导航绑定会话', async () => {
  const consents = [],
    requests = [],
    routes = []
  const state = workbench({
    consent: async (id, payload) => consents.push({ id, payload }),
    createDailyConsultation: async (id, payload) => {
      requests.push({ id, payload })
      if (requests.length === 1) throw new Error('synthetic unknown response')
      return { member_id: id, thread_id: 'bound-thread-a', agent_slug: 'health-consultation' }
    },
    navigate: async (route) => routes.push(route)
  })
  state.memberId.value = 'member-a'
  state.members.value = [{ id: 'member-a', scopes: ['ai_use', 'report_view', 'diet_edit'] }]
  state.config.value = {
    policy_version: 'policy-test',
    consultation: { available: true, processor: 'test-provider' }
  }
  await nextTick()
  await new Promise(setImmediate)
  state.consultationConsent.value = true
  await state.enterConsultation()
  await state.enterConsultation()
  assert.equal(requests.length, 2)
  assert.deepEqual(requests[0], requests[1])
  assert.equal(consents[0].payload.purpose, 'consultation')
  assert.equal(consents[0].id, 'member-a')
  assert.deepEqual(routes, [
    { name: 'AgentCompWithThreadId', params: { thread_id: 'bound-thread-a' } }
  ])
  state.dispose()
})

test('咨询绑定迟到响应不能导航已切换的成员', async () => {
  let resolveBinding
  const routes = []
  const state = workbench({
    consent: async () => {},
    createDailyConsultation: () =>
      new Promise((resolve) => {
        resolveBinding = resolve
      }),
    navigate: async (route) => routes.push(route)
  })
  state.memberId.value = 'member-a'
  state.members.value = [
    { id: 'member-a', scopes: ['ai_use', 'report_view', 'diet_edit'] },
    { id: 'member-b', scopes: ['ai_use', 'report_view', 'diet_edit'] }
  ]
  state.config.value = {
    policy_version: 'policy-test',
    consultation: { available: true, processor: 'test-provider' }
  }
  await nextTick()
  await new Promise(setImmediate)
  state.consultationConsent.value = true
  const operation = state.enterConsultation()
  await new Promise(setImmediate)
  state.memberId.value = 'member-b'
  await nextTick()
  resolveBinding({
    member_id: 'member-a',
    thread_id: 'bound-thread-a',
    agent_slug: 'health-consultation'
  })
  await operation
  assert.equal(routes.length, 0)
  assert.equal(state.consultationConsent.value, false)
  state.dispose()
})

test('人工录入响应等待时禁止切换用途，不能回填到错误页面', async () => {
  let resolveDraft
  const state = workbench({
    manual: () =>
      new Promise((resolve) => {
        resolveDraft = resolve
      })
  })
  state.memberId.value = 'synthetic-member'
  await nextTick()
  await new Promise(setImmediate)
  const operation = state.manualDraft()
  assert.equal(state.busy.value, true)
  state.activeTab.value = 'meal'
  assert.equal(state.tab.value, 'report')
  resolveDraft({ id: 'synthetic-draft', kind: 'report', payload: {}, version: 1 })
  await operation
  assert.equal(state.selected.value.kind, state.tab.value)
  state.activeTab.value = 'meal'
  await nextTick()
  assert.equal(state.tab.value, 'meal')
  assert.equal(state.selected.value, null)
  state.dispose()
})

test('确认弹窗打开时不能切换用途，修订即撤销已有计算', () => {
  const state = workbench({})
  state.confirming.value = true
  state.activeTab.value = 'meal'
  assert.equal(state.tab.value, 'report')
  state.calculation.value = { calculation_id: 'old' }
  state.changed()
  assert.equal(state.calculation.value, null)
  assert.equal(state.dirty.value, true)
  state.dispose()
})

test('报告页排除由父页面保存并撤销复核确认', () => {
  const state = workbench({})
  state.selected.value = { kind: 'report', payload: { excluded_pages: [] } }
  state.excludeReportPages([1])
  assert.deepEqual(state.selected.value.payload.excluded_pages, [1])
  assert.equal(state.dirty.value, true)
  state.dispose()
})

test('食品搜索使用后端 q 参数，不忽略含特殊字符的中文查询', async () => {
  const apiSource = (
    await readFile(new URL('../src/apis/health_vision_api.js', import.meta.url), 'utf8')
  )
    .replace(/^import.*\n/, '')
    .replace('export const healthVisionApi', 'const healthVisionApi')
  const noop = () => {}
  const api = new Function(
    'apiGet',
    'apiPost',
    'apiPut',
    'apiDelete',
    'apiRequest',
    'buildQuery',
    `${apiSource}\nreturn healthVisionApi`
  )(
    (path) => path,
    noop,
    noop,
    noop,
    noop,
    (values) => new URLSearchParams(values).toString()
  )
  const url = new URL(api.foods('米饭 & 食谱'), 'http://synthetic.invalid')
  assert.equal(url.searchParams.get('q'), '米饭 & 食谱')
  assert.equal(url.searchParams.get('query'), null)
})

test('失败页请求等待未知响应时保留幂等键，未保存或未同意不能提交', async () => {
  const requests = []
  const consents = []
  const state = workbench({
    consent: async (id, data) => consents.push({ id, data }),
    reprocessReport: async (data) => {
      requests.push(JSON.parse(JSON.stringify(data)))
      if (requests.length === 1) throw new Error('合成网络中断，响应未知')
      return { task_id: 'synthetic-task' }
    }
  })
  state.members.value = [
    { id: 'member-1', scopes: ['report_view', 'profile_edit', 'report_upload', 'ai_use'] }
  ]
  state.memberId.value = 'member-1'
  await nextTick()
  await new Promise(setImmediate)
  state.selected.value = {
    id: 'draft-1',
    member_id: 'member-1',
    kind: 'report',
    version: 2,
    review_status: 'pending_confirmation'
  }
  state.config.value = {
    report: { available: true, processor: 'synthetic' },
    policy_version: 'test-1'
  }
  await state.reprocessReportPage(1)
  assert.equal(requests.length, 0)
  state.cloudConsent.value = true
  state.dirty.value = true
  await state.reprocessReportPage(1)
  assert.equal(requests.length, 0)
  state.dirty.value = false
  await state.reprocessReportPage(1)
  assert.equal(requests.length, 1)
  assert.equal(state.reprocessRequest.value.client_request_id, requests[0].client_request_id)
  await state.reprocessReportPage(1)
  assert.deepEqual(requests[1], requests[0])
  assert.deepEqual(Object.keys(requests[0]).sort(), [
    'client_request_id',
    'draft_id',
    'page_indices',
    'version'
  ])
  assert.deepEqual(requests[0].page_indices, [1])
  assert.equal(requests[0].version, 2)
  assert.deepEqual(consents[0], {
    id: 'member-1',
    data: { purpose: 'report', accepted: true, processor: 'synthetic', policy_version: 'test-1' }
  })
  assert.equal(state.reprocessRequest.value, null)
  state.selected.value.review_status = 'confirmed'
  assert.equal(state.canReprocessReport.value, false)
  state.dispose()
})

test('单页重识别 API 同时发送版本和幂等头，不附带私有文件地址', async () => {
  const apiSource = (
    await readFile(new URL('../src/apis/health_vision_api.js', import.meta.url), 'utf8')
  )
    .replace(/^import.*\n/, '')
    .replace('export const healthVisionApi', 'const healthVisionApi')
  const noop = () => {}
  const api = new Function(
    'apiGet',
    'apiPost',
    'apiPut',
    'apiDelete',
    'apiRequest',
    'buildQuery',
    `${apiSource}\nreturn healthVisionApi`
  )(noop, (path, body, options) => ({ path, body, options }), noop, noop, noop, noop)
  const data = {
    draft_id: 'draft-1',
    version: 2,
    page_indices: [1],
    client_request_id: 'request-1'
  }
  assert.deepEqual(api.reprocessReport(data), {
    path: '/api/health/v1/report-page-tasks',
    body: data,
    options: { headers: { 'Idempotency-Key': 'request-1', 'If-Match': '"2"' } }
  })
})

test('云服务关闭时可上传旋转报告并私有预览，识别复用固定处理副本', async () => {
  const forms = [],
    tasks = [],
    consents = []
  const state = workbench({
    upload: async (form) => {
      forms.push(form)
      return { upload_id: 'upload-1', page_count: 1 }
    },
    preview: async (id, page) => {
      assert.equal(id, 'upload-1')
      assert.equal(page, 0)
      return new Blob(['synthetic-only'], { type: 'image/png' })
    },
    consent: async (...args) => consents.push(args),
    createTask: async (...args) => tasks.push(args)
  })
  state.memberId.value = 'member-1'
  await nextTick()
  await new Promise(setImmediate)
  state.files.value = [new File(['synthetic-only'], 'synthetic.png', { type: 'image/png' })]
  state.config.value = { report: { available: false } }
  state.reportRotation.value = 90
  state.deskewAngle.value = -2.5
  await state.prepareReport()
  assert.equal(forms.length, 1)
  assert.equal(forms[0].get('member_id'), 'member-1')
  assert.equal(forms[0].get('purpose'), 'report')
  assert.equal(forms[0].get('rotation'), '90')
  assert.equal(forms[0].get('deskew_angle'), '-2.5')
  assert.equal(forms[0].get('file').name, 'synthetic.png')
  assert.equal(state.preparedPreviewOpen.value, true)
  assert.match(state.preparedPreview.value, /^blob:/)
  assert.equal(consents.length, 0)
  assert.equal(tasks.length, 0)
  state.config.value = {
    report: { available: true, processor: 'synthetic' },
    policy_version: 'test-1'
  }
  state.cloudConsent.value = true
  await state.startRecognition()
  assert.equal(forms.length, 1)
  assert.deepEqual(tasks[0][1].upload_ids, ['upload-1'])
  assert.equal(consents.length, 1)
  assert.equal(state.preparedPreview.value, '')
  assert.equal(state.preparedPreviewOpen.value, false)
  state.dispose()
})

test('成员切换后的迟到预览不展示私有图片', async () => {
  let finish
  const state = workbench({
    preview: () =>
      new Promise((resolve) => {
        finish = resolve
      })
  })
  state.memberId.value = 'member-1'
  await nextTick()
  await new Promise(setImmediate)
  const pending = state.showPreparedPage({ upload_id: 'upload-1' }, 0)
  state.memberId.value = 'member-2'
  await nextTick()
  finish(new Blob(['synthetic-only']))
  await pending
  assert.equal(state.preparedPreview.value, '')
  assert.equal(state.preparedPreviewOpen.value, false)
  state.dispose()
})

test('选择文件后清空原生 input，允许再次选择同一文件重新调整角度', () => {
  const state = workbench({})
  const file = new File(['synthetic-only'], 'synthetic.png', { type: 'image/png' })
  const target = { files: [file], value: 'synthetic.png' }
  state.uploads.value = [{ upload_id: 'old-upload', page_count: 1 }]
  state.selectFiles({ target })
  assert.equal(target.value, '')
  assert.equal(state.files.value[0].name, 'synthetic.png')
  assert.deepEqual(state.uploads.value, [])
  state.dispose()
})

test('迟到上传只清理本次未绑定文件，不回填到另一成员或提交云任务', async () => {
  let finish
  const removed = [],
    previews = [],
    tasks = []
  const state = workbench({
    upload: () =>
      new Promise((resolve) => {
        finish = resolve
      }),
    removeUpload: async (id) => removed.push(id),
    preview: async (...args) => previews.push(args),
    createTask: async (...args) => tasks.push(args)
  })
  state.memberId.value = 'member-1'
  await nextTick()
  await new Promise(setImmediate)
  state.files.value = [new File(['synthetic-only'], 'synthetic.png', { type: 'image/png' })]
  const pending = state.prepareReport()
  state.memberId.value = 'member-2'
  await nextTick()
  finish({ upload_id: 'upload-1', page_count: 1 })
  await pending
  assert.deepEqual(removed, ['upload-1'])
  assert.deepEqual(state.uploads.value, [])
  assert.equal(previews.length, 0)
  assert.equal(tasks.length, 0)
  state.dispose()
})
