import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import process from 'node:process'
import { setImmediate } from 'node:timers'
import { computed, effectScope, nextTick, reactive, ref, watch } from 'vue'
import * as Vue from 'vue'
import { parse, compileTemplate } from 'vue/compiler-sfc'
import { renderToString } from 'vue/server-renderer'
import { mealLabels, nutrientLabels, nutrientText } from '../src/utils/healthVision.js'

const source = await readFile(
  process.env.HEALTH_MEAL_PLANS_TEST_SOURCE ||
    new URL('../src/components/health/HealthMealPlans.vue', import.meta.url),
  'utf8'
)
const script = source
  .match(/<script setup>([\s\S]*?)<\/script>/)[1]
  .replace(/^import[\s\S]*?from ['"][^'"]+['"]\s*\n/gm, '')
const snapshot = (extra = {}) => ({
  member_id: 'a',
  status: 'draft',
  preview_id: 'preview-a',
  plan_date: '2026-10-06',
  meals: [],
  ...extra
})

function panel(api = {}, agentApi = {}) {
  const props = reactive({
    memberId: 'a',
    members: [],
    scopes: ['diet_edit', 'report_view', 'ai_use'],
    configuration: {
      policy_version: 'policy-a',
      meal_plan: { available: true, processor: 'approved' }
    }
  })
  const scope = effectScope()
  const events = []
  let cleanup
  const factory = new Function(
    'ref',
    'computed',
    'watch',
    'onMounted',
    'onBeforeUnmount',
    'defineProps',
    'defineEmits',
    'useRouter',
    'api',
    'agentApi',
    `${script}\nreturn { reload, loadRecipes, selectPlan, makePreview, save, openSwap, submitSwap, closeSwap, generate, checkGeneration, stopGeneration, preview, current, historyVersion, saveAttempt, swapAttempt, swap, plans, error, working, polling, generation, generationStatus, consent, date, notes, meals, questions, recipes, recipesError, displayed, displayedIsFamily, currentIsFamily, canPreview, canGenerate, approval, approvalLoading, approvalError, approvalLabels, invalidationLabels, openProfile, safeBusy, safeSaved, safeInvalidated, locked }`
  )
  const state = scope.run(() =>
    factory(
      ref,
      computed,
      watch,
      () => {},
      (fn) => {
        cleanup = fn
      },
      () => props,
      () =>
        (...args) =>
          events.push(args),
      () => ({ push: () => {} }),
      {
        mealPlanApproval: async (plan_id, version) => ({
          plan_id,
          version,
          available: false,
          professional_review: 'not_reviewed'
        }),
        ...api
      },
      agentApi
    )
  )
  return {
    props,
    events,
    ...state,
    dispose: () => {
      cleanup()
      scope.stop()
    }
  }
}
const empty = { mealPlans: async () => ({ plans: [], truncated: false }) }

test('家庭详情按成员投影识别，不把家庭原计划交给单成员普通换菜', async () => {
  let writes = 0
  const state = panel({
    ...empty,
    swapMealPlan: async () => { writes++ },
    mealPlan: async () => snapshot({ plan_id: 'family-a', version: 1,
      scope: 'family_recipe_draft', members: { a: { meals: [] }, b: { meals: [] } } })
  })
  await state.selectPlan('family-a')
  assert.equal(state.currentIsFamily.value, true)
  assert.equal(state.displayedIsFamily.value, true)
  state.openSwap('breakfast', { dish_index: 0, name: '家庭早餐' })
  assert.equal(state.swap.value, null)
  state.swap.value = { replacement: { recipe_version_id: 'recipe' }, reason: 'stale manual swap' }
  await state.submitSwap()
  assert.equal(writes, 0)
  state.historyVersion.value = { snapshot: snapshot() }
  assert.equal(state.displayedIsFamily.value, false)
  assert.equal(state.currentIsFamily.value, true)
  state.dispose()
})

test('家庭任一成员授权发生变化时同步清除家庭详情与历史，丢弃旧详情读取', async () => {
  let release
  let reads = 0
  const state = panel({
    ...empty,
    mealPlan: async () => {
      reads++
      if (reads === 2) return new Promise((resolve) => { release = resolve })
      return snapshot({ plan_id: 'family-a', version: 1, members: { a: {}, b: {} } })
    }
  })
  state.props.members = [{ id: 'a', scopes: ['diet_edit'] }, { id: 'b', scopes: ['diet_edit'] }]
  await state.selectPlan('family-a')
  state.historyVersion.value = { version: 1, snapshot: state.current.value }
  const late = state.selectPlan('family-a')
  state.props.members[1].scopes = []
  assert.equal(state.current.value, null)
  assert.equal(state.historyVersion.value, null)
  release(snapshot({ plan_id: 'family-a', version: 1, members: { a: {}, b: {} } }))
  await late
  assert.equal(state.displayed.value, null)
  state.dispose()
})

test('家庭和个人当前／历史模板分支传完整成员，不在历史上挂操作面板', async () => {
  const descriptor = parse(source).descriptor
  const start = descriptor.template.content.indexOf('<HealthFamilyMealPlanSnapshot')
  const end = descriptor.template.content.indexOf('<template v-if="current?.revisions"', start)
  const compiled = compileTemplate({ source: descriptor.template.content.slice(start, end),
    filename: 'HealthMealPlans.vue', id: 'family-routing', compilerOptions: { mode: 'function' } })
  assert.deepEqual(compiled.errors, [])
  const render = new Function('Vue', compiled.code)(Vue)
  for (const [family, historical] of [[true, false], [true, true], [false, false], [false, true]]) {
    const calls = []
    const members = [{ id: 'a', scopes: ['diet_edit'] }, { id: 'b', scopes: ['diet_edit'] }]
    const current = snapshot({ plan_id: 'family-a', version: 1 })
    const app = Vue.createSSRApp({ render, setup: () => ({
      displayedIsFamily: family, currentIsFamily: family, displayed: current, current,
      historyVersion: historical ? { version: 1 } : null, memberId: 'a', members,
      scopes: ['diet_edit'], configuration: {}, locked: false, working: false,
      polling: false, saveAttempt: null, generation: null,
      safeSaved: () => {}, safeInvalidated: () => {}, openSwap: () => {}
    }) })
    for (const name of ['HealthFamilyMealPlanSnapshot', 'HealthMealPlanSnapshot',
      'HealthFamilyMealPlanner', 'HealthSafeMealPlanner']) {
      app.component(name, {
        props: ['snapshot', 'members', 'plan', 'disabled', 'editable'],
        setup: (props) => {
          calls.push(name)
          if (name.startsWith('HealthFamily')) assert.deepEqual(props.members, members)
          if (name.endsWith('Planner')) assert.equal(props.disabled, false)
          return () => Vue.h('p', name)
        }
      })
    }
    await renderToString(app)
    assert.deepEqual(calls, [
      family ? 'HealthFamilyMealPlanSnapshot' : 'HealthMealPlanSnapshot',
      ...(historical ? [] : [family ? 'HealthFamilyMealPlanner' : 'HealthSafeMealPlanner'])
    ])
  }
})

test('AI改餐保存后重读实际餐单和专业审核状态，不继承提交前批准', async () => {
  let version = 3
  const state = panel({
    mealPlans: async () => ({ plans: [snapshot({ plan_id: 'plan-a', version })] }),
    mealPlan: async () => snapshot({ plan_id: 'plan-a', version, notice: '来自实际业务回读' }),
    mealPlanApproval: async (plan_id, selectedVersion) => ({
      plan_id,
      version: selectedVersion,
      available: selectedVersion === 3,
      professional_review: selectedVersion === 3 ? 'approved' : 'not_reviewed'
    })
  })
  await state.selectPlan('plan-a')
  assert.equal(state.approval.value.available, true)
  version = 4
  state.safeBusy.value = true
  await state.safeSaved({ plan_id: 'plan-a', version: 4, notice: '不能作为页面回读事实' })
  assert.equal(state.safeBusy.value, false)
  assert.equal(state.current.value.version, 4)
  assert.equal(state.current.value.notice, '来自实际业务回读')
  assert.equal(state.approval.value.version, 4)
  assert.equal(state.approval.value.available, false)
  assert.equal(state.approval.value.professional_review, 'not_reviewed')
  assert.equal(state.plans.value[0].version, 4)
  state.dispose()
})

test('AI预览失效后回读当前餐单并保留失效原因，原草稿不继承旧专业状态', async () => {
  const state = panel({
    mealPlan: async () => snapshot({ plan_id: 'plan-a', version: 4 }),
    mealPlanApproval: async (plan_id, version) => ({
      plan_id,
      version,
      available: false,
      professional_review: 'invalidated',
      invalidation_reason: 'rules_changed'
    })
  })
  await state.selectPlan('plan-a')
  state.safeBusy.value = true
  await state.safeInvalidated('菜谱来源已变化，旧预览已失效')
  assert.equal(state.safeBusy.value, false)
  assert.equal(state.current.value.version, 4)
  assert.equal(state.approval.value.invalidation_reason, 'rules_changed')
  assert.match(state.error.value, /旧预览已失效/)
  state.dispose()
})

for (const status of [403, 404]) {
  test(`AI改餐明确撤权${status}立即清理所有私有数据，不重新读取健康资料`, async () => {
    let reads = 0
    const state = panel({
      mealPlan: async () => {
        reads++
        return snapshot({ plan_id: 'plan-a', version: 3 })
      }
    })
    await state.selectPlan('plan-a')
    state.plans.value = [state.current.value]
    state.historyVersion.value = { version: 1, snapshot: snapshot() }
    state.preview.value = snapshot()
    state.safeBusy.value = true
    await state.safeInvalidated('授权已撤回，旧预览已清除', status)
    assert.equal(reads, 1)
    assert.equal(state.safeBusy.value, false)
    assert.equal(state.current.value, null)
    assert.equal(state.approval.value, null)
    assert.equal(state.preview.value, null)
    assert.equal(state.historyVersion.value, null)
    assert.deepEqual(state.plans.value, [])
    assert.match(state.error.value, /授权已撤回/)
    state.dispose()
  })
}

test('安全改餐执行期间锁定父页面切换与普通换菜，不把自己的busy回传为disabled', async () => {
  let read = 0
  const state = panel({
    mealPlan: async () => {
      read++
      return snapshot({ plan_id: 'plan-a', version: 3 })
    }
  })
  await state.selectPlan('plan-a')
  state.safeBusy.value = true
  assert.equal(state.locked.value, true)
  await state.selectPlan('plan-b')
  state.openSwap('lunch', { dish_index: 0, name: '鸡蛋炒饭' })
  state.openProfile()
  assert.equal(read, 1)
  assert.equal(state.swap.value, null)
  assert.deepEqual(state.events, [])
  const template = parse(source).descriptor.template.content.match(
    /<HealthSafeMealPlanner[\s\S]*?\/>/
  )[0]
  const compiled = compileTemplate({
    source: template,
    filename: 'HealthMealPlans.vue',
    id: 'safe-busy-test',
    compilerOptions: { mode: 'function' }
  })
  assert.deepEqual(compiled.errors, [])
  const received = []
  const app = Vue.createSSRApp({
    render: new Function('Vue', compiled.code)(Vue),
    setup: () => ({
      memberId: 'a',
      current: state.current.value,
      currentIsFamily: false,
      historyVersion: null,
      scopes: state.props.scopes,
      configuration: state.props.configuration,
      working: false,
      polling: false,
      saveAttempt: null,
      generation: null,
      safeBusy: true,
      safeSaved: state.safeSaved,
      safeInvalidated: state.safeInvalidated
    })
  })
  app.component('HealthSafeMealPlanner', {
    props: ['disabled'],
    setup: (props) => {
      received.push(props.disabled)
      return () => Vue.h('div')
    }
  })
  await renderToString(app)
  assert.deepEqual(received, [false])
  state.dispose()
})

test('切换成员和授权立即清空旧数据，迟到列表与预览均丢弃', async () => {
  let finishList, finishPreview
  const state = panel({
    mealPlans: () =>
      new Promise((r) => {
        finishList = r
      }),
    previewMealPlan: () =>
      new Promise((r) => {
        finishPreview = r
      })
  })
  state.meals.value.forEach((meal) => {
    meal.dishes[0].recipe_version_id = 'recipe'
  })
  await nextTick()
  const list = state.reload(),
    preview = state.makePreview()
  state.props.scopes = []
  await nextTick()
  finishList({ plans: [snapshot()], truncated: false })
  finishPreview(snapshot())
  await Promise.all([list, preview])
  assert.deepEqual(state.plans.value, [])
  assert.equal(state.preview.value, null)
  assert.equal(state.canPreview.value, false)
  state.dispose()
})

test('当前餐单专业来源失效由服务器回读，历史快照不继承当前批准', async () => {
  const requests = []
  const state = panel({
    ...empty,
    mealPlan: async () =>
      snapshot({
        plan_id: 'plan-a',
        version: 4,
        revisions: [{ version: 1, snapshot: snapshot({ personalized: true }) }]
      }),
    mealPlanApproval: async (id, version) => {
      requests.push([id, version])
      return {
        plan_id: id,
        version,
        available: false,
        professional_review: 'invalidated',
        invalidation_reason: 'weight_measurement_changed'
      }
    }
  })
  await state.selectPlan('plan-a')
  assert.deepEqual(requests, [['plan-a', 4]])
  assert.equal(state.approval.value.professional_review, 'invalidated')
  state.historyVersion.value = state.current.value.revisions[0]
  assert.equal(state.displayed.value.personalized, true)
  assert.equal(state.approval.value.available, false)
  assert.equal(state.approval.value.version, 4)
  const { descriptor } = parse(source)
  const block = descriptor.template.content.match(
    /<div v-if="current" class="approval-state">[\s\S]*?<\/div>/
  )[0]
  const compiled = compileTemplate({
    source: block,
    filename: 'HealthMealPlans.vue',
    id: 'approval-state-test',
    compilerOptions: { mode: 'function' }
  })
  assert.deepEqual(compiled.errors, [])
  const render = new Function('Vue', compiled.code)(Vue)
  const vnode = render(
    {
      current: state.current.value,
      approvalLoading: false,
      approvalError: '',
      approval: state.approval.value,
      approvalLabels: state.approvalLabels,
      invalidationLabels: state.invalidationLabels,
      historyVersion: state.historyVersion.value,
      locked: false,
      openProfile: state.openProfile
    },
    []
  )
  const alert = vnode.children.find((child) => child.props?.message)
  assert.equal(alert.props.message, '当前版本的专业审核已失效')
  assert.match(
    alert.props.description,
    /所选体重记录已更正或作废.*核对体重.*专业确认、计算目标和检查餐单/
  )
  vnode.children.find((child) => child.props?.onClick).props.onClick()
  assert.deepEqual(state.events, [['profile']])
  state.dispose()
})

test('当前批准与生成时未审核快照在真实模板中明确区分，历史内容保持原样', async () => {
  const notice = '专业规则未接入'
  const historical = snapshot({ version: 1, notice, professional_review: 'not_reviewed' })
  const state = panel({
    ...empty,
    mealPlan: async () =>
      snapshot({
        plan_id: 'plan-a',
        version: 2,
        notice,
        professional_review: 'not_reviewed',
        revisions: [{ version: 1, snapshot: historical }]
      }),
    mealPlanApproval: async (plan_id, version) => ({ plan_id, version, available: true })
  })
  await state.selectPlan('plan-a')
  const { descriptor } = parse(source)
  const start = descriptor.template.content.indexOf('<section v-if="displayed"')
  const end = descriptor.template.content.indexOf('<template v-if="current?.revisions"', start)
  const snapshotSource = await readFile(
    new URL('../src/components/health/HealthMealPlanSnapshot.vue', import.meta.url),
    'utf8'
  )
  const { descriptor: snapshotDescriptor } = parse(snapshotSource)
  const compileRender = (template, filename) => {
    const compiled = compileTemplate({
      source: template,
      filename,
      id: 'snapshot-status-test',
      compilerOptions: { mode: 'function' }
    })
    assert.deepEqual(compiled.errors, [])
    return new Function('Vue', compiled.code)(Vue)
  }
  const render = compileRender(
    `${descriptor.template.content.slice(start, end)}</section>`,
    'HealthMealPlans.vue'
  )
  const snapshotRender = compileRender(
    snapshotDescriptor.template.content,
    'HealthMealPlanSnapshot.vue'
  )
  for (const historyVersion of [null, state.current.value.revisions[0]]) {
    state.historyVersion.value = historyVersion
    const displayed = state.displayed.value
    const app = Vue.createSSRApp({
      render,
      setup: () => ({
        memberId: state.props.memberId,
        scopes: state.props.scopes,
        configuration: state.props.configuration,
        working: false,
        polling: false,
        saveAttempt: null,
        generation: null,
        safeSaved: state.safeSaved,
        safeInvalidated: state.safeInvalidated,
        current: state.current.value,
        displayed,
        displayedIsFamily: false,
        currentIsFamily: false,
        members: state.props.members,
        historyVersion,
        approval: state.approval.value,
        approvalLoading: false,
        approvalError: '',
        approvalLabels: state.approvalLabels,
        invalidationLabels: state.invalidationLabels,
        locked: false,
        preview: null,
        openProfile: state.openProfile,
        openSwap: state.openSwap
      })
    })
    app.component('AAlert', {
      props: ['message', 'description'],
      setup: (props) => () => Vue.h('p', [props.message, props.description])
    })
    for (const name of ['AButton', 'ATag'])
      app.component(name, {
        setup:
          (_, { slots }) =>
          () =>
            Vue.h('span', slots.default?.())
      })
    app.component('HealthMealPlanSnapshot', {
      props: { snapshot: Object, editable: Boolean, ruleChecked: Boolean },
      render: snapshotRender,
      setup: (props) => {
        assert.strictEqual(props.snapshot, displayed)
        return { mealLabels, nutrientLabels, nutrientText }
      }
    })
    app.component('HealthSafeMealPlanner', { render: () => Vue.h('div') })
    app.component('HealthFamilyMealPlanner', { render: () => Vue.h('div') })
    app.component('HealthFamilyMealPlanSnapshot', { render: () => Vue.h('div') })
    const html = await renderToString(app)
    assert.match(html, /当前版本 2 已专业批准[\s\S]*生成时快照/)
    assert.match(
      html,
      /下方状态为生成时记录；当前专业审核以上方服务端回读为准。[\s\S]*未个体适配[\s\S]*未专业审核/
    )
    assert.match(html, /专业规则未接入/)
    assert.equal(displayed.professional_review, 'not_reviewed')
    if (historyVersion) assert.match(html, /历史版本 1/)
  }
  assert.equal(state.approval.value.available, true)
  state.dispose()
})

test('迟到专业审核状态不能覆盖另一成员，失败或错版本不能伪装批准', async () => {
  let finish
  const state = panel({
    ...empty,
    mealPlan: async () => snapshot({ plan_id: 'plan-a', version: 2 }),
    mealPlanApproval: () =>
      new Promise((resolve) => {
        finish = resolve
      })
  })
  const reading = state.selectPlan('plan-a')
  await new Promise(setImmediate)
  state.props.memberId = 'b'
  await nextTick()
  finish({ plan_id: 'plan-a', version: 2, available: true })
  await reading
  assert.equal(state.approval.value, null)
  assert.equal(state.approvalError.value, '')
  assert.equal(state.approvalLoading.value, false)
  state.dispose()
  for (const response of [
    new Error('synthetic disconnected'),
    { plan_id: 'plan-a', version: 1, available: true }
  ]) {
    const failed = panel({
      ...empty,
      mealPlan: async () => snapshot({ plan_id: 'plan-a', version: 2 }),
      mealPlanApproval: async () => {
        if (response instanceof Error) throw response
        return response
      }
    })
    await failed.selectPlan('plan-a')
    assert.equal(failed.current.value.version, 2)
    assert.equal(failed.approval.value, null)
    assert.match(failed.approvalError.value, /未能核对/)
    failed.dispose()
  }
})

test('实际专业审核 pending_review 状态在真实模板中显示待审核而不冒充批准', async () => {
  const state = panel({
    ...empty,
    mealPlan: async () => snapshot({ plan_id: 'plan-a', version: 2 }),
    mealPlanApproval: async (plan_id, version) => ({
      plan_id,
      version,
      available: false,
      professional_review: 'pending_review'
    })
  })
  await state.selectPlan('plan-a')
  const { descriptor } = parse(source)
  const block = descriptor.template.content.match(
    /<div v-if="current" class="approval-state">[\s\S]*?<\/div>/
  )[0]
  const compiled = compileTemplate({
    source: block,
    filename: 'HealthMealPlans.vue',
    id: 'pending-review-state-test',
    compilerOptions: { mode: 'function' }
  })
  assert.deepEqual(compiled.errors, [])
  const render = new Function('Vue', compiled.code)(Vue)
  const vnode = render(
    {
      current: state.current.value,
      approvalLoading: false,
      approvalError: '',
      approval: state.approval.value,
      approvalLabels: state.approvalLabels,
      invalidationLabels: state.invalidationLabels,
      historyVersion: null,
      locked: false,
      openProfile: state.openProfile
    },
    []
  )
  const alert = vnode.children.find((child) => child.props?.message)
  assert.equal(alert.props.message, '当前版本正在等待专业审核')
  assert.equal(alert.props.type, 'warning')
  assert.equal(state.approval.value.available, false)
  state.dispose()
})

test('刷新餐单重新核对当前审核，服务端撤权后迟到批准不恢复旧状态', async () => {
  let count = 0,
    finish
  const state = panel({
    ...empty,
    mealPlan: async () => snapshot({ plan_id: 'plan-a', version: 2 }),
    mealPlanApproval: async (plan_id, version) => ({
      plan_id,
      version,
      available: ++count === 1,
      professional_review: count === 1 ? undefined : 'invalidated'
    })
  })
  await state.selectPlan('plan-a')
  assert.equal(state.approval.value.available, true)
  await state.reload()
  assert.equal(state.approval.value.professional_review, 'invalidated')
  state.dispose()
  for (const status of [403, 404]) {
    const denied = panel({
      mealPlans: async () => {
        throw { status }
      },
      mealPlan: async () => snapshot({ plan_id: 'plan-a', version: 2 }),
      mealPlanApproval: () =>
        new Promise((resolve) => {
          finish = resolve
        })
    })
    const reading = denied.selectPlan('plan-a')
    await new Promise(setImmediate)
    denied.historyVersion.value = { version: 1, snapshot: snapshot() }
    denied.approval.value = { plan_id: 'plan-a', version: 2, available: true }
    await denied.reload()
    finish({ plan_id: 'plan-a', version: 2, available: true })
    await reading
    assert.equal(denied.current.value, null)
    assert.equal(denied.historyVersion.value, null)
    assert.equal(denied.approval.value, null)
    assert.equal(denied.approvalLoading.value, false)
    assert.equal(denied.working.value, false)
    denied.dispose()
  }
})

test('手动预览由服务器计算；改日期或计划量后旧预览失效', async () => {
  let sent
  const state = panel({
    ...empty,
    previewMealPlan: async (member, data) => {
      sent = data
      return snapshot({ nutrition: { totals: { energy_kcal: null } } })
    }
  })
  state.meals.value.forEach((meal) => {
    meal.dishes[0].recipe_version_id = 'recipe'
    meal.dishes[0].grams = null
  })
  await nextTick()
  await state.makePreview()
  assert.equal(sent.meals.length, 3)
  assert.equal('nutrition' in sent, false)
  assert.equal(state.displayed.value.nutrition.totals.energy_kcal, null)
  state.meals.value[0].dishes[0].grams = 150
  await nextTick()
  assert.equal(state.preview.value, null)
  state.dispose()
})

for (const status of [403, 404]) {
  for (const operation of ['preview', 'save', 'swap', 'generated-plan', 'generated-questions']) {
    test(`餐单读取撤权 ${status} 后丢弃迟到 ${operation}，不恢复私有内容或继续回读`, async () => {
      let finish,
        listReads = 0,
        detailReads = 0
      const lateSnapshot = snapshot({ plan_id: 'saved', version: 2 })
      const delayed = () =>
        new Promise((resolve) => {
          finish = resolve
        })
      const state = panel(
        {
          mealPlans: async () => {
            if (++listReads === 1) throw { status }
            return { plans: [], truncated: false }
          },
          mealPlan: async () => {
            detailReads++
            return lateSnapshot
          },
          previewMealPlan: delayed,
          saveMealPlan: delayed,
          swapMealPlan: delayed,
          recipes: async () => []
        },
        {
          getRequest: async () => ({
            request: { request_id: 'request', thread_id: 'bound', dispatched_run_id: 'run-a' }
          }),
          getAgentRunResult: delayed
        }
      )
      let pending
      try {
        if (operation === 'preview') {
          state.meals.value.forEach((meal) => {
            meal.dishes[0].recipe_version_id = 'recipe'
          })
          await nextTick()
          pending = state.makePreview()
        } else if (operation === 'save') {
          state.preview.value = snapshot()
          pending = state.save()
        } else if (operation === 'swap') {
          state.current.value = lateSnapshot
          state.openSwap('lunch', { dish_index: 0, name: '旧菜' })
          state.swap.value.replacement.recipe_version_id = 'new-recipe'
          state.swap.value.reason = '换口味'
          pending = state.submitSwap()
        } else {
          state.generation.value = { request_id: 'request', thread_id: 'bound' }
          pending = state.checkGeneration()
        }
        await new Promise(setImmediate)
        assert.equal(typeof finish, 'function')
        state.historyVersion.value = { version: 1, snapshot: snapshot() }
        await state.reload()
        finish(
          operation.startsWith('generated-')
            ? {
                status: 'completed',
                agent_slug: 'health-meal-planner',
                thread_id: 'bound',
                agent_run_id: 'run-a',
                request_id: 'request',
                output: JSON.stringify(
                  operation === 'generated-questions'
                    ? { status: 'needs_input', questions: ['旧成员的私人要求'] }
                    : lateSnapshot
                )
              }
            : lateSnapshot
        )
        await pending
        assert.equal(state.displayed.value, null, '撤权后迟到结果不能恢复餐单快照')
        assert.deepEqual(state.questions.value, [], '撤权后迟到结果不能恢复私人补充问题')
        assert.equal(detailReads, 0, '撤权后旧写入回执不能继续读取详情')
        assert.equal(listReads, 1, '撤权后旧写入回执不能继续读取列表')
        assert.equal(state.current.value, null)
        assert.equal(state.preview.value, null)
        assert.equal(state.historyVersion.value, null)
        assert.equal(state.approval.value, null)
        assert.equal(state.saveAttempt.value, null)
        assert.equal(state.swapAttempt.value, null)
        assert.equal(state.generation.value, null)
        assert.equal(state.working.value, false)
        assert.equal(state.polling.value, false)
      } finally {
        state.dispose()
      }
    })
  }

  test(`专业审核回读撤权 ${status} 清空当前和历史餐单，普通网络失败不作撤权处理`, async () => {
    let rejectApproval
    const state = panel({
      ...empty,
      mealPlan: async () => snapshot({ plan_id: 'saved', version: 2 }),
      mealPlanApproval: () =>
        new Promise((_, reject) => {
          rejectApproval = reject
        })
    })
    try {
      const pending = state.selectPlan('saved')
      await new Promise(setImmediate)
      state.historyVersion.value = { version: 1, snapshot: snapshot() }
      state.preview.value = snapshot()
      state.plans.value = [snapshot({ plan_id: 'saved', version: 2 })]
      rejectApproval({ status })
      await pending
      assert.equal(state.displayed.value, null, '审核读取明确撤权后旧餐单不能继续展示')
      assert.equal(state.current.value, null)
      assert.equal(state.historyVersion.value, null)
      assert.equal(state.preview.value, null)
      assert.deepEqual(state.plans.value, [])
      assert.equal(state.approval.value, null)
      assert.equal(state.approvalLoading.value, false)
      assert.equal(state.working.value, false)
      assert.match(state.error.value, /授权|无权/)
    } finally {
      state.dispose()
    }
  })
}

test('保存响应丢失重试原回执与幂等键，回读当前版本及历史', async () => {
  const requests = []
  const state = panel({
    ...empty,
    saveMealPlan: async (member, data) => {
      requests.push(JSON.parse(JSON.stringify(data)))
      if (requests.length === 1) throw Error('response lost')
      return snapshot({ plan_id: 'saved', version: 1 })
    },
    mealPlan: async () =>
      snapshot({ plan_id: 'saved', version: 2, revisions: [{ version: 1 }, { version: 2 }] })
  })
  state.preview.value = snapshot()
  await state.save()
  assert.ok(state.saveAttempt.value)
  await state.save()
  assert.deepEqual(requests[0], requests[1])
  assert.equal(state.current.value.version, 2)
  assert.equal(state.current.value.revisions.length, 2)
  assert.equal(state.preview.value, null)
  state.dispose()
})

test('换菜网络重试冻结菜谱、理由和版本；409移除旧详情直到重新读取', async () => {
  const requests = []
  const state = panel({
    ...empty,
    recipes: async () => [],
    swapMealPlan: async (id, data) => {
      requests.push(JSON.parse(JSON.stringify(data)))
      if (requests.length === 1) throw Error('response lost')
      throw Object.assign(Error('conflict'), { status: 409 })
    }
  })
  state.current.value = snapshot({ plan_id: 'saved', version: 4 })
  state.openSwap('lunch', { dish_index: 0, name: '旧菜' })
  state.swap.value.replacement.recipe_version_id = 'new-recipe'
  state.swap.value.reason = '换口味'
  await state.submitSwap()
  state.swap.value.reason = '不应覆盖原请求'
  await state.submitSwap()
  assert.deepEqual(requests[0], requests[1])
  assert.equal(requests[0].version, 4)
  assert.equal(state.current.value, null)
  assert.match(state.error.value, /版本/)
  state.dispose()
})

test('历史选择显示旧快照；乱序详情不能覆盖当前选择', async () => {
  let finish
  const state = panel({
    mealPlan: () =>
      new Promise((r) => {
        finish = r
      }),
    ...empty
  })
  const read = state.selectPlan('saved')
  state.props.memberId = 'b'
  await nextTick()
  finish(snapshot({ plan_id: 'saved', version: 3 }))
  await read
  assert.equal(state.current.value, null)
  state.current.value = snapshot({ version: 2 })
  state.historyVersion.value = { version: 1, snapshot: snapshot({ plan_date: '2026-10-01' }) }
  assert.equal(state.displayed.value.plan_date, '2026-10-01')
  state.dispose()
})

test('生成绑定响应迟到不能向旧成员提交 Run', async () => {
  let finish,
    count = 0
  const state = panel(
    {
      ...empty,
      consent: async () => {},
      createMealPlanner: () =>
        new Promise((r) => {
          finish = r
        })
    },
    {
      createAgentRun: async () => {
        count++
      }
    }
  )
  state.consent.value = true
  const run = state.generate()
  await new Promise((r) => setImmediate(r))
  state.props.memberId = 'b'
  await nextTick()
  finish({ member_id: 'a', agent_slug: 'health-meal-planner', thread_id: 'old' })
  await run
  assert.equal(count, 0)
  assert.equal(state.generation.value, null)
  state.dispose()
})

test('生成提交响应未知可重试原正文，完成结果只认同 Run 回执', async () => {
  const submitted = [],
    consents = []
  const state = panel(
    {
      ...empty,
      consent: async (id, data) => {
        consents.push(data)
      },
      createMealPlanner: async () => ({
        member_id: 'a',
        agent_slug: 'health-meal-planner',
        thread_id: 'bound'
      })
    },
    {
      createAgentRun: async (data) => {
        submitted.push(JSON.parse(JSON.stringify(data)))
        if (submitted.length === 1) throw Error('lost')
      },
      getRequest: async (id) => ({
        request: { request_id: id, thread_id: 'bound', dispatched_run_id: 'run-a' }
      }),
      getAgentRunResult: async () => ({
        status: 'completed',
        agent_slug: 'health-meal-planner',
        thread_id: 'bound',
        agent_run_id: 'run-a',
        request_id: submitted[0].meta.request_id,
        output: JSON.stringify(snapshot())
      })
    }
  )
  state.consent.value = true
  state.notes.value = '清淡'
  await state.generate()
  state.notes.value = '不应改写原请求'
  await state.generate()
  assert.deepEqual(submitted[0], submitted[1])
  assert.equal(consents[0].purpose, 'meal_plan')
  assert.equal(state.preview.value.preview_id, 'preview-a')
  assert.equal(state.generation.value, null)
  assert.equal(state.saveAttempt.value, null)
  state.dispose()
})

test('未完成、跨 Run 和其他成员结果不能发布为页面餐单', async () => {
  for (const mode of ['pending', 'foreign-run', 'foreign-member']) {
    const state = panel(empty, {
      getRequest: async () => ({
        request: { request_id: 'request', thread_id: 'bound', dispatched_run_id: 'run-a' }
      }),
      getAgentRunResult: async () => ({
        status: mode === 'pending' ? 'running' : 'completed',
        agent_slug: 'health-meal-planner',
        thread_id: 'bound',
        agent_run_id: mode === 'foreign-run' ? 'other' : 'run-a',
        request_id: 'request',
        output: JSON.stringify(snapshot({ member_id: mode === 'foreign-member' ? 'b' : 'a' }))
      })
    })
    state.generation.value = { request_id: 'request', thread_id: 'bound' }
    await state.checkGeneration()
    assert.equal(state.preview.value, null)
    state.dispose()
  }
})

test('配餐师补充问题显示原文，未启用服务禁止调用模型', async () => {
  const state = panel(empty, {
    getRequest: async () => ({
      request: { request_id: 'request', thread_id: 'bound', dispatched_run_id: 'run-a' }
    }),
    getAgentRunResult: async () => ({
      status: 'completed',
      agent_slug: 'health-meal-planner',
      thread_id: 'bound',
      agent_run_id: 'run-a',
      request_id: 'request',
      output: JSON.stringify({ status: 'needs_input', questions: ['请补充用餐意图'] })
    })
  })
  state.generation.value = { request_id: 'request', thread_id: 'bound' }
  await state.checkGeneration()
  assert.deepEqual(state.questions.value, ['请补充用餐意图'])
  assert.equal(state.preview.value, null)
  state.props.configuration.meal_plan.available = false
  assert.equal(state.canGenerate.value, false)
  state.dispose()
})

test('取消响应未知仍保留恢复入口，成功后才能重新生成', async () => {
  let calls = 0
  const state = panel(empty, {
    cancelRequest: async () => {
      if (++calls === 1) throw Error('lost')
      return { status: 'cancel_requested' }
    }
  })
  state.generation.value = { request_id: 'request', thread_id: 'bound' }
  await state.stopGeneration()
  assert.ok(state.generation.value)
  await state.stopGeneration()
  assert.equal(state.generation.value, null)
  state.dispose()
})

test('已经派发的请求取消对应 Run；未知提交尚不存在时不能假定已取消', async () => {
  const cancelled = []
  const state = panel(empty, {
    cancelRequest: async () => {
      throw Object.assign(Error('dispatched'), { status: 409 })
    },
    getRequest: async () => ({ request: { thread_id: 'bound', dispatched_run_id: 'run-a' } }),
    cancelAgentRun: async (id) => {
      cancelled.push(id)
    }
  })
  state.generation.value = { request_id: 'request', thread_id: 'bound' }
  await state.stopGeneration()
  assert.deepEqual(cancelled, ['run-a'])
  assert.equal(state.generation.value, null)
  state.dispose()
  const unknown = panel(empty, {
    cancelRequest: async () => {
      throw Object.assign(Error('not committed'), { status: 404 })
    }
  })
  unknown.generation.value = { request_id: 'request', thread_id: 'bound' }
  await unknown.stopGeneration()
  assert.ok(unknown.generation.value)
  unknown.dispose()
})

test('刷新发现权限撤回，清除此前餐单和历史快照', async () => {
  const state = panel({
    mealPlans: async () => {
      throw Object.assign(Error('revoked'), { status: 403 })
    }
  })
  state.current.value = snapshot({ plan_id: 'saved', version: 1 })
  state.historyVersion.value = { snapshot: snapshot() }
  await state.reload()
  assert.equal(state.current.value, null)
  assert.equal(state.displayed.value, null)
  assert.match(state.error.value, /授权/)
  state.dispose()
})

test('健康 API 在真实方法边界携带餐单幂等与版本头', async () => {
  const text = await readFile(new URL('../src/apis/health_vision_api.js', import.meta.url), 'utf8')
  const calls = []
  const fn =
    (method) =>
    (...args) => {
      calls.push({ method, args })
    }
  const factory = new Function(
    'apiGet',
    'apiPost',
    'apiPut',
    'apiDelete',
    'apiRequest',
    'buildQuery',
    `${text.replace(/^import.*\r?\n/, '').replace('export const', 'const')}\nreturn healthVisionApi`
  )
  const api = factory(fn('GET'), fn('POST'), fn('PUT'), fn('DELETE'), fn('REQUEST'), () => '')
  api.saveMealPlan('member', { preview_id: 'preview', client_request_id: 'key' })
  api.swapMealPlan('plan', { version: 3, client_request_id: 'swap' })
  assert.equal(calls[0].args[0], '/api/health/v1/members/member/meal-plans')
  assert.equal(calls[0].args[2].headers['Idempotency-Key'], 'key')
  assert.equal(calls[1].args[2].headers['If-Match'], '"3"')
  assert.equal(calls[1].args[2].headers['Idempotency-Key'], 'swap')
})
