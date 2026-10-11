import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { setImmediate } from 'node:timers'
import { computed, effectScope, nextTick, reactive, ref, watch } from 'vue'
import * as Vue from 'vue'
import { compileTemplate } from 'vue/compiler-sfc'
import { renderToString } from 'vue/server-renderer'
import * as helpers from '../src/utils/healthVision.js'

const source = await readFile(new URL('../src/views/HealthVisionView.vue', import.meta.url), 'utf8')
const script = source.match(/<script setup>([\s\S]*?)<\/script>/)[1]
  .replace(/^import[\s\S]*?from ['"][^'"]+['"]\s*\n/gm, '')
const tick = async () => {
  await nextTick()
  await new Promise(setImmediate)
}
const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
const memberList = () => ['a', 'b'].map((id) => ({
  id, scopes: ['report_view', 'diet_edit', 'profile_edit', 'report_upload', 'ai_use']
}))
const page = (id, kind, jobsOffset = 0, draftsOffset = 0) => ({
  jobs: [{ task_id: `${id}-${kind}-job-${jobsOffset}`, kind, execution_status: 'success', created_at: '2026-10-11T00:00:00Z' }],
  drafts: [{ id: `${id}-${kind}-draft-${draftsOffset}`, kind, review_status: 'pending_confirmation', version: 1, created_at: '2026-10-11T00:00:00Z' }],
  jobs_next_offset: jobsOffset < 40 ? jobsOffset + 20 : null,
  drafts_next_offset: draftsOffset < 40 ? draftsOffset + 20 : null
})
const draft = (extra = {}) => ({
  id: 'selected-a', member_id: 'a', kind: 'report', version: 1,
  review_status: 'pending_confirmation', payload: { fields: [], pages: [], excluded_pages: [] }, ...extra
})

/** 执行真实页面脚本，并把生命周期与轮询回调暴露给确定性测试。 */
async function workbench(overrides = {}) {
  const members = memberList()
  const mounted = [], unmounted = [], timers = [], cleared = [], errors = [], modals = [], calls = []
  const user = reactive({ isAdmin: false, uid: 'synthetic-actor' })
  const document = { visibilityState: 'visible' }
  const scope = effectScope()
  const configuration = { policy_version: 'test', report: { available: true, processor: 'synthetic' }, meal: { available: true, processor: 'synthetic' } }
  const factory = new Function(
    'ref', 'computed', 'watch', 'onMounted', 'onBeforeUnmount', 'useUserStore', 'useRouter', 'api',
    'message', 'Modal', 'document', 'window', 'setInterval', 'clearInterval', ...Object.keys(helpers),
    `${script}\nreturn { memberId, members, member, records, tab, activeTab, purpose, canReadVision, config, busy, confirming, jobs, drafts, scopedJobs, scopedDrafts, jobsOffset, draftsOffset, jobsNextOffset, draftsNextOffset, jobsPage, draftsPage, visionLoading, visionBackground, visionError, readVisionPage, turnVisionPage, refresh, perform, selected, editable, changed, excludeReportPages, addResult, canReprocessReport, dirty, calculation, reviewed, cloudConsent, files, uploads, manualDraft, startRecognition, openDraft, saveDraft, confirmDraft, reprocessReportPage, statusLabels, reviewLabels }`
  )
  const state = scope.run(() => factory(
    ref, computed, watch, (fn) => mounted.push(fn), (fn) => unmounted.push(fn), () => user,
    () => ({ push: async () => {} }),
    {
      configuration: async () => configuration,
      members: async () => members,
      records: async () => [],
      visionPage: async (id, kind, jobsLimit, jobsOffset, draftsLimit, draftsOffset) => {
        calls.push([id, kind, jobsLimit, jobsOffset, draftsLimit, draftsOffset])
        return page(id, kind, jobsOffset, draftsOffset)
      },
      ...overrides
    },
    { error: (value) => errors.push(value), warning: () => {}, success: () => {} },
    { confirm: (options) => { modals.push(options); return { destroy() {} } } },
    document, { confirm: () => true },
    (callback, period) => { timers.push({ callback, period }); return timers.length },
    (id) => cleared.push(id), ...Object.values(helpers)
  ))
  state.members.value = members
  state.config.value = configuration
  state.memberId.value = 'a'
  await tick()
  return {
    ...state, calls, user, document, timers, cleared, errors, modals,
    mount: async () => { await mounted[0](); await tick() },
    dispose: () => { unmounted.forEach((fn) => fn()); scope.stop() }
  }
}

/** 编译实际双列表模板，核对按钮事件、页码、加载与空页投影。 */
async function listView(state) {
  const start = source.indexOf('<div class="history-grid">')
  const end = source.indexOf('<section v-if="selected"', start)
  const compiled = compileTemplate({ source: source.slice(start, end), filename: 'HealthVisionView.vue', id: 'vision-pages', compilerOptions: { mode: 'function' } })
  assert.deepEqual(compiled.errors, [])
  const buttons = [], empty = [], alerts = []
  const app = Vue.createSSRApp({ setup: () => state, render: new Function('Vue', compiled.code)(Vue) })
  app.component('AButton', {
    props: ['disabled'],
    setup: (props, { attrs, slots }) => {
      const label = slots.default().map((item) => item.children).join('').trim()
      buttons.push({ label, disabled: props.disabled, click: attrs.onClick })
      return () => Vue.h('button', { disabled: props.disabled }, label)
    }
  })
  app.component('AEmpty', { props: ['description'], setup: (props) => { empty.push(props.description); return () => Vue.h('p', props.description) } })
  app.component('AAlert', {
    props: ['type', 'message'],
    setup: (props, { slots }) => { alerts.push(props); return () => Vue.h('div', [props.message, ...(slots.action?.() || [])]) }
  })
  app.component('ASpin', { props: ['tip'], setup: (props) => () => Vue.h('p', props.tip) })
  app.component('AProgress', { setup: () => () => Vue.h('progress') })
  const html = await renderToString(app)
  return { html, buttons, paging: buttons.filter((item) => ['上一页', '下一页'].includes(item.label)), empty, alerts }
}

/** 从真实父页绑定读取复核输入的只读状态。 */
async function reviewInput(state) {
  const fragment = source.match(/<ReportReview[\s\S]*?\/>/)[0].replace(/\s+v-if="[^"]*"/, '')
  const compiled = compileTemplate({ source: fragment, filename: 'HealthVisionView.vue', id: 'vision-poll-editor', compilerOptions: { mode: 'function' } })
  assert.deepEqual(compiled.errors, [])
  let readonly
  const app = Vue.createSSRApp({ setup: () => state, render: new Function('Vue', compiled.code)(Vue) })
  app.component('ReportReview', {
    props: ['payload', 'readonly'],
    setup: (props) => {
      readonly = props.readonly
      return () => Vue.h('input', { disabled: props.readonly, value: props.payload.fields[0].name })
    }
  })
  return { html: await renderToString(app), get readonly() { return readonly } }
}

test('分页API发送种类与两个独立窗口，默认值保留零，旧vision接口不变', async () => {
  const apiSource = (await readFile(new URL('../src/apis/health_vision_api.js', import.meta.url), 'utf8'))
    .replace(/^import.*\r?\n/, '').replace('export const healthVisionApi', 'const healthVisionApi')
  const noop = () => {}
  const api = new Function('apiGet', 'apiPost', 'apiPut', 'apiDelete', 'apiRequest', 'buildQuery', `${apiSource}\nreturn healthVisionApi`)(
    (path) => path, noop, noop, noop, noop, (values) => new URLSearchParams(values).toString()
  )
  assert.equal(api.list('a'), '/api/health/v1/members/a/vision')
  for (const [args, expected] of [
    [['a', 'report'], { kind: 'report', jobs_limit: '20', jobs_offset: '0', drafts_limit: '20', drafts_offset: '0' }],
    [['a', 'meal', 50, 40, 10, 20], { kind: 'meal', jobs_limit: '50', jobs_offset: '40', drafts_limit: '10', drafts_offset: '20' }]
  ]) {
    const url = new URL(api.visionPage(...args), 'http://synthetic.invalid')
    assert.equal(url.pathname, '/api/health/v1/members/a/vision/page')
    assert.deepEqual(Object.fromEntries(url.searchParams), expected)
  }
})

test('任务与草稿按钮独立移动位置，前后边界及显式刷新回首页', async () => {
  const state = await workbench()
  let view = await listView(state)
  assert.deepEqual(view.paging.map((item) => item.disabled), [true, false, true, false])
  await view.paging[1].click()
  assert.deepEqual(state.calls.at(-1), ['a', 'report', 20, 20, 20, 0])
  view = await listView(state)
  assert.match(view.html, /第 2 页 · 1 条/)
  await view.paging[3].click()
  assert.deepEqual(state.calls.at(-1), ['a', 'report', 20, 20, 20, 20])
  await state.turnVisionPage('jobs', true)
  assert.deepEqual(state.calls.at(-1), ['a', 'report', 20, 40, 20, 20])
  view = await listView(state)
  assert.equal(view.paging[1].disabled, true)
  const count = state.calls.length
  await state.turnVisionPage('jobs', true)
  assert.equal(state.calls.length, count)
  await state.turnVisionPage('jobs', false)
  assert.deepEqual(state.calls.at(-1), ['a', 'report', 20, 20, 20, 20])
  await state.refresh(true)
  assert.deepEqual(state.calls.at(-1), ['a', 'report', 20, 0, 20, 0])
  for (const lock of ['busy', 'confirming', 'visionLoading']) {
    state[lock].value = true
    const before = state.calls.length
    view = await listView(state)
    assert.equal(view.paging.every((button) => button.disabled), true)
    await state.turnVisionPage('drafts', true)
    assert.equal(state.calls.length, before)
    state[lock].value = false
  }
  state.dispose()
})

test('两个空中间页仍按服务端next前进，末页空态可以返回', async () => {
  const state = await workbench({ visionPage: async (id, kind, _jl, jo, _dl, d) => ({ ...page(id, kind, jo, d), jobs: [], drafts: [] }) })
  await state.readVisionPage(20, 20)
  let view = await listView(state)
  assert.deepEqual(view.empty, ['本页来源已失效，可继续查看下一页', '本页来源已失效，可继续查看下一页'])
  assert.deepEqual(view.paging.map((item) => item.disabled), [false, false, false, false])
  await view.paging[1].click()
  await state.turnVisionPage('drafts', true)
  assert.equal(state.jobsPage.value, 3)
  assert.equal(state.draftsPage.value, 3)
  view = await listView(state)
  assert.deepEqual(view.paging.map((item) => item.disabled), [false, true, false, true])
  assert.match(view.empty[0], /可返回上一页/)
  assert.match(view.empty[1], /可返回上一页/)
  state.dispose()
})

test('翻页等待清旧页，失败保留目标位置，两个面板可重试原双页', async () => {
  let pending = null
  const calls = []
  const state = await workbench({ visionPage: async (id, kind, jl, jo, dl, d) => {
    calls.push([jo, d])
    return pending ? pending.promise : page(id, kind, jo, d)
  } })
  pending = deferred()
  const reading = state.readVisionPage(20, 40)
  assert.deepEqual(state.jobs.value, [])
  assert.deepEqual(state.drafts.value, [])
  let view = await listView(state)
  assert.match(view.html, /正在读取识别任务/)
  assert.match(view.html, /正在读取复核草稿/)
  assert.equal(view.paging.every((button) => button.disabled), true)
  pending.reject(Object.assign(new Error('synthetic failure'), { status: 500 }))
  await reading
  assert.equal(state.visionLoading.value, false)
  assert.deepEqual([state.jobsOffset.value, state.draftsOffset.value], [20, 40])
  view = await listView(state)
  assert.equal(view.alerts.length, 2)
  pending = null
  await view.buttons.find((button) => button.label === '重试本页').click()
  assert.deepEqual(calls.at(-1), [20, 40])
  assert.equal(state.visionError.value, '')
  assert.equal(state.jobs.value[0].task_id, 'a-report-job-20')
  state.dispose()
})

test('最新读取胜过旧请求的迟到成功及失败', async () => {
  for (const outcome of ['resolve', 'reject']) {
    let pending = null
    const state = await workbench({ visionPage: async (id, kind, jl, jo, dl, d) => pending ? pending.promise : page(id, kind, jo, d) })
    pending = deferred()
    const stale = pending
    const old = state.readVisionPage(20, 20)
    pending = null
    await state.readVisionPage(40, 0)
    if (outcome === 'resolve') stale.resolve(page('late-private', 'report', 20, 20))
    else stale.reject(Object.assign(new Error('late denial'), { status: 404 }))
    await old
    assert.equal(state.jobs.value[0].task_id, 'a-report-job-40')
    assert.deepEqual([state.jobsOffset.value, state.draftsOffset.value], [40, 0])
    assert.equal(state.visionError.value, '')
    assert.equal(state.visionLoading.value, false)
    state.dispose()
  }
})

test('成员、用途、撤权、操作者及卸载变化丢弃迟到列表成功和失败', async () => {
  for (const change of ['member', 'purpose', 'scope', 'actor', 'unmount']) {
    for (const outcome of ['resolve', 'reject']) {
      let pending = null
      const state = await workbench({ visionPage: async (id, kind, jl, jo, dl, d) => pending ? pending.promise : page(id, kind, jo, d) })
      state.selected.value = draft()
      pending = deferred()
      const stale = pending
      const reading = state.readVisionPage(20, 20)
      pending = null
      if (change === 'member') state.memberId.value = 'b'
      if (change === 'purpose') state.tab.value = 'meal'
      if (change === 'scope') state.members.value[0].scopes = ['diet_edit']
      if (change === 'actor') state.user.uid = 'another-synthetic-actor'
      if (change === 'unmount') state.dispose()
      await tick()
      assert.equal(state.selected.value, null)
      assert.deepEqual([state.jobsOffset.value, state.draftsOffset.value], change === 'unmount' ? [20, 20] : [0, 0])
      if (outcome === 'resolve') stale.resolve(page('late-private', 'report', 20, 20))
      else stale.reject(Object.assign(new Error('late denial'), { status: 403 }))
      await reading
      assert.equal(state.jobs.value.some((job) => job.task_id.includes('late-private')), false)
      assert.equal(state.visionError.value, '')
      assert.equal(state.visionLoading.value, false)
      if (change === 'scope' || change === 'unmount') assert.deepEqual(state.jobs.value, [])
      if (change !== 'unmount') state.dispose()
    }
  }
})

test('当前403或404撤销列表及私有草稿，旧列表和详情不能重新展示', async () => {
  for (const status of [403, 404]) {
    let mode = 'normal'
    const oldList = deferred(), oldDetail = deferred()
    const state = await workbench({
      visionPage: async (id, kind, jl, jo, dl, d) => {
        if (mode === 'old') return oldList.promise
        if (mode === 'denied') throw Object.assign(new Error('synthetic denied'), { status })
        return page(id, kind, jo, d)
      },
      draft: async () => oldDetail.promise
    })
    state.selected.value = draft()
    state.calculation.value = { calculation_id: 'private-calculation' }
    state.reviewed.value = true
    mode = 'old'
    const reading = state.readVisionPage(20, 20)
    const opening = state.openDraft('older-draft')
    mode = 'denied'
    await state.readVisionPage(40, 40)
    assert.equal(state.selected.value, null)
    assert.equal(state.calculation.value, null)
    assert.equal(state.reviewed.value, false)
    assert.deepEqual(state.jobs.value, [])
    assert.deepEqual(state.drafts.value, [])
    assert.equal(state.jobsNextOffset.value, null)
    assert.equal(state.draftsNextOffset.value, null)
    assert.match(state.visionError.value, /授权或来源已变化/)
    oldList.resolve(page('late-private', 'report', 20, 20))
    oldDetail.resolve(draft({ id: 'late-private' }))
    await Promise.all([reading, opening])
    assert.equal(state.selected.value, null)
    assert.deepEqual(state.jobs.value, [])
    assert.equal(state.visionLoading.value, false)
    state.dispose()
  }
})

test('操作者切换及404清除所有用途记录，迟到响应和分析入口不能保留旧饮食', async () => {
  const oldPage = deferred(), newPage = deferred()
  let mode = 'normal'
  const state = await workbench({ visionPage: async (id, kind, jl, jo, dl, d) => {
    if (mode === 'old') return oldPage.promise
    if (mode === 'new') return newPage.promise
    return page(id, kind, jo, d)
  } })
  state.records.value = { report: [{ id: 'old-private-report' }], meal: [{ id: 'old-private-meal' }] }
  mode = 'old'
  const reading = state.readVisionPage(20, 20)
  mode = 'new'
  state.user.uid = 'another-synthetic-actor'
  await nextTick()
  assert.deepEqual(state.records.value, { report: [], meal: [] })
  newPage.reject(Object.assign(new Error('synthetic authorization revoked'), { status: 404 }))
  await tick()
  oldPage.resolve(page('old-private', 'report', 20, 20))
  await reading
  assert.deepEqual(state.records.value, { report: [], meal: [] })
  state.tab.value = 'analysis'
  await tick()
  assert.equal(state.purpose.value, 'report')
  const fragment = source.match(/<HealthDietAnalysis[\s\S]*?\/>/)[0].replace(/\s+v-else-if="[^"]*"/, '')
  const compiled = compileTemplate({ source: fragment, filename: 'HealthVisionView.vue', id: 'vision-private-analysis', compilerOptions: { mode: 'function' } })
  assert.deepEqual(compiled.errors, [])
  let analysisRecords
  const app = Vue.createSSRApp({ setup: () => state, render: new Function('Vue', compiled.code)(Vue) })
  app.component('HealthDietAnalysis', {
    props: ['records'],
    setup: (props) => { analysisRecords = props.records; return () => Vue.h('div') }
  })
  await renderToString(app)
  assert.deepEqual(analysisRecords, [])
  state.dispose()
})

test('饮食用途当前拒绝同时清除此前报告记录，不能保留另一用途私有结果', async () => {
  for (const status of [403, 404]) {
    let denied = false
    const state = await workbench({ visionPage: async (id, kind, jl, jo, dl, d) => {
      if (denied) throw Object.assign(new Error('synthetic denied'), { status })
      return page(id, kind, jo, d)
    } })
    state.tab.value = 'meal'
    await tick()
    state.records.value = { report: [{ id: 'old-private-report' }], meal: [{ id: 'old-private-meal' }] }
    denied = true
    await state.readVisionPage(20, 20)
    assert.deepEqual(state.records.value, { report: [], meal: [] })
    assert.match(state.visionError.value, /授权或来源已变化/)
    state.dispose()
  }
})

test('打开草稿的迟到成功与错误不能回填另一成员、用途或已卸载页面', async () => {
  for (const change of ['member', 'purpose', 'unmount']) {
    for (const outcome of ['resolve', 'reject']) {
      const pending = deferred()
      const state = await workbench({ draft: async () => pending.promise })
      const opening = state.openDraft('old-draft')
      if (change === 'member') state.memberId.value = 'b'
      if (change === 'purpose') state.tab.value = 'meal'
      if (change === 'unmount') state.dispose()
      await tick()
      if (outcome === 'resolve') pending.resolve(draft({ id: 'late-private' }))
      else pending.reject(Object.assign(new Error('late denial'), { status: 403 }))
      await opening
      assert.equal(state.selected.value, null)
      assert.deepEqual(state.errors, [])
      if (change !== 'unmount') state.dispose()
    }
  }
})

test('可见授权历史页无活动任务仍3秒轮询，保留双页和草稿编辑及计算', async () => {
  let detailReads = 0
  const state = await workbench({ draft: async () => { detailReads++; return draft() } })
  await state.mount()
  assert.equal(state.timers[0].period, 3000)
  await state.readVisionPage(20, 40)
  const selected = draft({ payload: { fields: [{ name: '尚未保存的合成修改' }], pages: [], excluded_pages: [] } })
  state.selected.value = selected
  state.dirty.value = true
  state.calculation.value = { calculation_id: 'kept-calculation' }
  state.reviewed.value = true
  const count = state.calls.length
  state.timers[0].callback()
  await tick()
  assert.equal(state.calls.length, count + 1)
  assert.deepEqual(state.calls.at(-1), ['a', 'report', 20, 20, 20, 40])
  assert.deepEqual(state.selected.value, selected)
  assert.equal(state.dirty.value, true)
  assert.equal(state.calculation.value.calculation_id, 'kept-calculation')
  assert.equal(state.reviewed.value, true)
  assert.equal(detailReads, 0)
  state.busy.value = true
  state.timers[0].callback()
  state.busy.value = false
  state.confirming.value = true
  state.timers[0].callback()
  state.confirming.value = false
  state.document.visibilityState = 'hidden'
  state.timers[0].callback()
  state.document.visibilityState = 'visible'
  state.tab.value = 'profile'
  await tick()
  state.timers[0].callback()
  assert.equal(state.calls.length, count + 1)
  state.dispose()
  assert.deepEqual(state.cleared, [1])
})

test('后台轮询等待时保留当前行且不锁复核输入，连续修改不会被响应覆盖', async () => {
  let pending = null
  const state = await workbench({ visionPage: async (id, kind, jl, jo, dl, d) => pending ? pending.promise : page(id, kind, jo, d) })
  await state.mount()
  await state.readVisionPage(20, 40)
  state.selected.value = draft({ payload: { fields: [{ name: '合成编辑一' }], pages: [], excluded_pages: [] } })
  state.dirty.value = true
  state.calculation.value = { calculation_id: 'kept-calculation' }
  state.reviewed.value = true
  const oldJobs = state.jobs.value, oldDrafts = state.drafts.value
  assert.equal((await reviewInput(state)).readonly, false)
  pending = deferred()
  state.timers[0].callback()
  assert.equal(state.busy.value, false)
  assert.equal(state.visionLoading.value, true)
  assert.equal(state.visionBackground.value, true)
  assert.equal(state.jobs.value, oldJobs)
  assert.equal(state.drafts.value, oldDrafts)
  const waiting = await listView(state)
  assert.doesNotMatch(waiting.html, /正在读取识别任务|正在读取复核草稿/)
  const editor = await reviewInput(state)
  assert.equal(editor.readonly, false)
  assert.doesNotMatch(editor.html, /disabled/)
  state.selected.value.payload.fields[0].name = '合成编辑二'
  state.timers[0].callback()
  pending.resolve(page('a', 'report', 20, 40))
  await tick()
  assert.equal(state.busy.value, false)
  assert.equal(state.visionLoading.value, false)
  assert.equal(state.selected.value.payload.fields[0].name, '合成编辑二')
  assert.equal(state.dirty.value, true)
  assert.equal(state.calculation.value.calculation_id, 'kept-calculation')
  assert.equal(state.reviewed.value, true)
  assert.equal((await reviewInput(state)).readonly, false)
  assert.deepEqual([state.jobsOffset.value, state.draftsOffset.value], [20, 40])
  state.dispose()
})

test('后台刷新失败清除当前行，保留页码和未保存草稿并提供重试', async () => {
  let pending = null
  const state = await workbench({ visionPage: async (id, kind, jl, jo, dl, d) => pending ? pending.promise : page(id, kind, jo, d) })
  await state.mount()
  await state.readVisionPage(20, 40)
  state.selected.value = draft()
  state.dirty.value = true
  pending = deferred()
  state.timers[0].callback()
  pending.reject(Object.assign(new Error('synthetic network failure'), { status: 500 }))
  await tick()
  assert.deepEqual(state.jobs.value, [])
  assert.deepEqual(state.drafts.value, [])
  assert.deepEqual([state.jobsOffset.value, state.draftsOffset.value], [20, 40])
  assert.equal(state.selected.value.id, 'selected-a')
  assert.equal(state.dirty.value, true)
  assert.equal(state.busy.value, false)
  assert.equal(state.visionLoading.value, false)
  const view = await listView(state)
  assert.equal(view.alerts.length, 2)
  assert.equal(view.buttons.filter((button) => button.label === '重试本页').length, 2)
  state.dispose()
})

test('人工草稿和新建识别任务成功均回双侧首页，草稿仍显式复核', async () => {
  const created = []
  const state = await workbench({
    manual: async () => draft({ id: 'new-manual' }),
    consent: async () => {},
    createTask: async (kind, request) => { created.push({ kind, request }); return { task_id: 'new-task' } }
  })
  await state.readVisionPage(20, 40)
  await state.manualDraft()
  assert.deepEqual(state.calls.at(-1), ['a', 'report', 20, 0, 20, 0])
  assert.equal(state.selected.value.id, 'new-manual')
  await state.readVisionPage(40, 20)
  state.files.value = [new File(['synthetic-only'], 'synthetic.png', { type: 'image/png' })]
  state.uploads.value = [{ upload_id: 'prepared-synthetic-upload', page_count: 1 }]
  state.cloudConsent.value = true
  await state.startRecognition()
  assert.equal(created.length, 1)
  assert.equal(created[0].kind, 'report')
  assert.deepEqual(created[0].request.upload_ids, ['prepared-synthetic-upload'])
  assert.deepEqual(state.calls.at(-1), ['a', 'report', 20, 0, 20, 0])
  assert.equal(state.selected.value.id, 'new-manual')
  state.dispose()
})

test('保存、重识别和确认后的列表回读保留位置及对应草稿版本', async () => {
  const state = await workbench({
    patch: async () => draft({ version: 2 }),
    consent: async () => {},
    reprocessReport: async () => ({ task_id: 'reprocess-synthetic' }),
    confirm: async () => {},
    draft: async () => draft({ version: 3, review_status: 'confirmed' })
  })
  await state.readVisionPage(20, 40)
  state.selected.value = draft()
  state.dirty.value = true
  await state.saveDraft()
  assert.equal(state.selected.value.version, 2)
  assert.equal(state.dirty.value, false)
  assert.deepEqual(state.calls.at(-1), ['a', 'report', 20, 20, 20, 40])
  state.cloudConsent.value = true
  await state.reprocessReportPage(0)
  assert.equal(state.selected.value.version, 2)
  assert.deepEqual(state.calls.at(-1), ['a', 'report', 20, 20, 20, 40])
  state.reviewed.value = true
  state.confirmDraft()
  await state.modals.at(-1).onOk()
  assert.equal(state.selected.value.version, 3)
  assert.equal(state.selected.value.review_status, 'confirmed')
  assert.deepEqual(state.calls.at(-1), ['a', 'report', 20, 20, 20, 40])
  state.dispose()
})
