import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import * as Vue from 'vue'
import { parse, compileTemplate } from 'vue/compiler-sfc'
import { publishedDietAnalysisResult } from '../src/utils/healthDietAnalysisResult.js'
import * as healthHelpers from '../src/utils/healthVision.js'
import { getMessageRunId } from '../src/utils/messageDebug.js'

const sources = Object.fromEntries(
  await Promise.all(
    [
      ['result', '../src/components/health/HealthDietAnalysisResult.vue'],
      ['message', '../src/components/AgentMessageComponent.vue'],
      ['chat', '../src/components/AgentChatComponent.vue'],
      ['list', '../src/components/ThreadMessageList.vue'],
      ['layout', '../src/layouts/AppLayout.vue'],
      ['parser', '../src/utils/healthDietAnalysisResult.js']
    ].map(async ([key, path]) => [key, await readFile(new URL(path, import.meta.url), 'utf8')])
  )
)

const completedRun = { run_id: 'run-old', request_id: 'request-old', status: 'completed' }
const clone = (value) => JSON.parse(JSON.stringify(value))
const persistedMessage = (result) => ({
  id: 91,
  type: 'ai',
  message_type: 'text',
  run_id: 'run-old',
  request_id: 'request-old',
  content: JSON.stringify(result)
})
const published = (
  result,
  message = {},
  run = {},
  agent = 'health-diet-analyst',
  processing = false
) =>
  publishedDietAnalysisResult(
    { ...persistedMessage(result), ...message },
    { ...completedRun, ...run },
    agent,
    processing
  )

/** 独立明确的服务器事实样本，不从前端计算生成期望值。 */
function singleMeal() {
  return {
    result_type: 'diet_analysis',
    status: 'completed',
    scope: 'confirmed_single_meal',
    meal_type: 'lunch',
    eaten_at: '2026-10-09T04:00:00Z',
    records: [{ record_id: 'private-meal-id', source_version: 3 }],
    items: [
      { item_id: 'private-food-id', name: '合成炒鸡蛋', eaten_grams: '0' },
      { item_id: 'private-food-unknown', name: '合成米饭', eaten_grams: null }
    ],
    nutrition: {
      totals: {
        energy_kcal: '120',
        protein_g: 0,
        fat_g: '5',
        carbohydrate_g: '20',
        sodium_mg: null
      },
      estimated: false
    },
    coverage: { recorded_items: 2, calculated_items: 1, known_nutrients: 4, supported_nutrients: 5 }
  }
}

function periodFacts() {
  return {
    result_type: 'diet_analysis',
    status: 'completed',
    scope: 'confirmed_period',
    window: {
      start_date: '2026-10-03',
      end_date: '2026-10-09',
      period_days: 7,
      timezone: 'Asia/Shanghai'
    },
    records: [{ record_id: 'private-meal-id', source_version: 3 }],
    days: [{ date: '2026-10-09', record_ids: ['private-meal-id'] }],
    nutrition: {
      totals: {
        energy_kcal: {
          recorded_total: '200',
          known_sum: '200',
          known_records: 2,
          missing_records: 0
        },
        protein_g: { recorded_total: '0', known_sum: '0', known_records: 2, missing_records: 0 },
        fat_g: { recorded_total: null, known_sum: null, known_records: 0, missing_records: 2 },
        carbohydrate_g: {
          recorded_total: '50',
          known_sum: '50',
          known_records: 2,
          missing_records: 0
        },
        sodium_mg: { recorded_total: null, known_sum: '0', known_records: 1, missing_records: 1 }
      },
      estimated: true
    },
    coverage: {
      days_with_records: 1,
      record_count: 2,
      excluded_invalidated_records: 1,
      dates_without_records: [
        '2026-10-03',
        '2026-10-04',
        '2026-10-05',
        '2026-10-06',
        '2026-10-07',
        '2026-10-08'
      ]
    },
    feedback: { count: 1, nutrition_recalculated: false },
    trend: { status: 'rules_not_ready', direction: null }
  }
}

function feedbackReceipt() {
  return {
    result_type: 'meal_feedback',
    status: 'saved',
    scope: 'single_meal_feedback',
    records: [{ record_id: 'private-meal-id', source_version: 3 }],
    feedback: {
      feedback_id: 'private-feedback-id',
      status: 'active',
      version: 4,
      details: { consumption: 'half', tags: ['too_salty'], comment: '合成反馈：实际只吃了一半' },
      source_type: 'user_self_report'
    },
    source_run_id: 'run-old',
    nutrition_recalculated: false
  }
}

/** 实际编译 Vue 模板，组件名作为可观察 VNode，不创建第二套展示逻辑。 */
function renderer(template, filename) {
  const compiled = compileTemplate({
    source: template,
    filename,
    id: filename,
    compilerOptions: { mode: 'function' }
  })
  assert.deepEqual(compiled.errors, [])
  return new Function('Vue', compiled.code)({ ...Vue, resolveComponent: (name) => name })
}

function children(node) {
  if (!node || typeof node !== 'object') return []
  return Array.isArray(node.children)
    ? node.children
    : typeof node.children?.default === 'function'
      ? node.children.default()
      : []
}

function nodes(node, type) {
  return !node || typeof node !== 'object'
    ? []
    : [
        ...(node.type === type ? [node] : []),
        ...children(node).flatMap((child) => nodes(child, type))
      ]
}

function textOf(node) {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (!node || typeof node !== 'object') return ''
  if (typeof node.children === 'string' && node.type !== Vue.Comment) return node.children
  return children(node).map(textOf).join(' ')
}

function visibleText(node) {
  return textOf(node).replace(/\s+/g, ' ').trim()
}

const resultDescriptor = parse(sources.result).descriptor
const resultRender = renderer(resultDescriptor.template.content, 'HealthDietAnalysisResult.vue')
const resultScript = resultDescriptor.scriptSetup.content.replace(/^import[^\n]+\n/gm, '')
const resultState = new Function(
  'computed',
  'defineProps',
  ...Object.keys(healthHelpers),
  `${resultScript}\nreturn {feedbackResult,period,questions,datesWithoutRecords,title,rows,consumptionLabels,tagLabels,count,mealTime}`
)

function renderResult(result) {
  const state = resultState(Vue.computed, () => ({ result }), ...Object.values(healthHelpers))
  return resultRender(Vue.proxyRefs({ ...state, ...healthHelpers, result }), [])
}

test('仅同一已完成 Run 的持久化饮食分析正文进入卡片，历史完成无临时流状态仍能识别', () => {
  for (const result of [singleMeal(), periodFacts(), feedbackReceipt()]) {
    assert.deepEqual(published(result), result)
  }
  const message = persistedMessage(singleMeal())
  assert.equal(message.status, undefined)
  assert.ok(publishedDietAnalysisResult(message, completedRun, 'health-diet-analyst'))
  const decimalPortion = singleMeal()
  decimalPortion.items[0].eaten_grams = '0E-12'
  assert.deepEqual(published(decimalPortion), decimalPortion)
  for (const status of ['running', 'failed', 'queued', 'interrupted', 'cancelled', undefined]) {
    assert.equal(published(singleMeal(), {}, { status }), null, String(status))
  }
  for (const [messageOverride, runOverride] of [
    [{ run_id: 'other-run' }, {}],
    [{ request_id: 'other-request' }, {}],
    [{ request_id: '' }, { request_id: '' }],
    [{ run_id: '' }, { run_id: '' }],
    [{ id: 'stream-message-id' }, {}],
    [{ id: 0 }, {}],
    [{ type: 'human' }, {}],
    [{ message_type: 'health_tool_audit' }, {}],
    [{ error_type: 'failed' }, {}],
    [{ extra_metadata: { error_type: 'source_invalidated' } }, {}],
    [{ isStoppedByUser: true }, {}]
  ]) {
    assert.equal(published(singleMeal(), messageOverride, runOverride), null)
  }
  assert.equal(published(singleMeal(), {}, {}, 'health-meal-planner'), null)
  assert.equal(published(singleMeal(), {}, {}, ''), null)
  assert.equal(published(singleMeal(), {}, {}, 'health-diet-analyst', true), null)
  assert.equal(
    publishedDietAnalysisResult(persistedMessage(singleMeal()), null, 'health-diet-analyst'),
    null
  )
})

test('无效、部分和错误 JSON 保持原消息渲染，不把模型片段认作业务结果', () => {
  for (const content of [
    '{"result_type":',
    '普通说明',
    '[]',
    'null',
    '1',
    '{"result_type":"diet_analysis"}'
  ]) {
    assert.equal(published(singleMeal(), { content }), null)
  }
  const malformed = [
    { ...singleMeal(), result_type: 'meal_plan' },
    { ...singleMeal(), status: 'error' },
    { ...singleMeal(), scope: 'clinical_assessment' },
    { ...singleMeal(), nutrition: { totals: {} } },
    { ...singleMeal(), nutrition: { totals: [] } },
    { ...singleMeal(), coverage: {} },
    { ...singleMeal(), items: [{ name: '缺少确认份量' }] },
    { ...periodFacts(), window: { ...periodFacts().window, period_days: 2 } },
    { ...periodFacts(), window: { ...periodFacts().window, timezone: 'UTC' } },
    { ...periodFacts(), coverage: { ...periodFacts().coverage, record_count: -1 } },
    { ...feedbackReceipt(), nutrition_recalculated: true },
    { ...feedbackReceipt(), feedback: { ...feedbackReceipt().feedback, status: 'revoked' } },
    { ...feedbackReceipt(), feedback: { ...feedbackReceipt().feedback, details: { tags: [] } } }
  ]
  const wrongPeriodValues = periodFacts()
  delete wrongPeriodValues.nutrition.totals.sodium_mg.missing_records
  malformed.push(wrongPeriodValues)
  for (const result of malformed) assert.equal(published(result), null, JSON.stringify(result))
})

test('单餐模板显示实际菜名和确认值，零、未知份量和钠缺失分开显示，不曝光内部 ID', () => {
  const result = singleMeal()
  const before = clone(result)
  const tree = renderResult(result)
  const text = visibleText(tree)
  assert.match(text, /这餐饮食分析/)
  assert.match(text, /午餐/)
  assert.match(text, /2 项已确认食物，1 项纳入原计算；4 \/ 5 项营养值已知/)
  assert.match(text, /合成炒鸡蛋 · 食用份量 0 g/)
  assert.match(text, /合成米饭 · 食用份量 未知/)
  const rows = nodes(nodes(tree, 'tbody')[0], 'tr')
  assert.equal(visibleText(rows.find((row) => row.key === 'energy_kcal')), '能量 120 kcal')
  assert.equal(visibleText(rows.find((row) => row.key === 'protein_g')), '蛋白质 0 g')
  assert.equal(visibleText(rows.find((row) => row.key === 'sodium_mg')), '钠 未知')
  assert.doesNotMatch(text, /private-meal-id|private-food-id|source_version|record_id/)
  assert.match(text, /这里不判断疾病适用性或营养是否达标/)
  assert.deepEqual(result, before)
})

test('周期模板保留服务器窗口、记录覆盖和缺失日期，已知之和不冒充完整摄入', () => {
  const result = periodFacts()
  const tree = renderResult(result)
  const text = visibleText(tree)
  assert.match(text, /2026-10-03 至 2026-10-09 · 7 个北京时间自然日/)
  assert.match(text, /1 天有记录，共 2 条有效确认记录。1 条失效来源已排除/)
  assert.match(
    text,
    /未记录日期（6 天）：2026-10-03、2026-10-04、2026-10-05、2026-10-06、2026-10-07、2026-10-08/
  )
  assert.match(text, /未记录不代表未进食/)
  const rows = nodes(nodes(tree, 'tbody')[0], 'tr')
  assert.equal(visibleText(rows.find((row) => row.key === 'sodium_mg')), '钠 未知 0 mg 1 / 1')
  assert.equal(visibleText(rows.find((row) => row.key === 'fat_g')), '脂肪 未知 未知 0 / 2')
  assert.equal(visibleText(rows.find((row) => row.key === 'protein_g')), '蛋白质 0 g 0 g 2 / 0')
  assert.match(text, /不能代表缺失记录或未记录天数的摄入/)
  assert.match(text, /餐后反馈 1 条，属于用户自述；不会按吃完程度重算营养/)
  assert.doesNotMatch(text, /private-meal-id|record_ids|rules_not_ready/)
  const unknownDates = clone(result)
  delete unknownDates.coverage.dates_without_records
  assert.ok(published(unknownDates))
  assert.match(visibleText(renderResult(unknownDates)), /未记录日期（未知 天）：未知/)
  const noMissingDates = clone(result)
  noMissingDates.coverage.dates_without_records = []
  assert.match(visibleText(renderResult(noMissingDates)), /未记录日期（0 天）：无/)
})

test('空周期保留未知营养和真实零条数，引导确认记录，不能把未记录推断为未进食', () => {
  const result = periodFacts()
  result.coverage.days_with_records = 0
  result.coverage.record_count = 0
  result.coverage.excluded_invalidated_records = 0
  for (const value of Object.values(result.nutrition.totals)) {
    Object.assign(value, {
      recorded_total: null,
      known_sum: null,
      known_records: 0,
      missing_records: 0
    })
  }
  const tree = renderResult(result)
  const text = visibleText(tree)
  assert.match(text, /0 天有记录，共 0 条有效确认记录。0 条失效来源已排除/)
  assert.match(text, /范围内暂无有效已确认饮食/)
  const rows = nodes(nodes(tree, 'tbody')[0], 'tr')
  assert.equal(visibleText(rows.find((row) => row.key === 'sodium_mg')), '钠 未知 未知 0 / 0')
})

test('保存反馈显示服务器收据与自述，不按吃完程度缩放或增添营养计算', () => {
  const result = feedbackReceipt()
  const before = clone(result)
  const tree = renderResult(result)
  const text = visibleText(tree)
  assert.match(text, /这餐反馈已保存/)
  assert.match(text, /已保存版本 4/)
  assert.match(text, /吃完程度（自述） 一半/)
  assert.match(text, /这餐的体验 偏咸/)
  assert.match(text, /实际只吃了一半/)
  assert.match(text, /反馈是用户自述，原饮食记录和营养计算保持不变/)
  assert.match(text, /已确认记录 → 餐后反馈/)
  assert.equal(nodes(tree, 'table').length, 0)
  assert.doesNotMatch(text, /kcal|private-feedback-id|private-meal-id|run-old/)
  assert.deepEqual(result, before)
})

test('有效追问显示原问题并进入原会话补充，无结果值时不展示统计或保存成功', () => {
  for (const [type, scope] of [
    ['diet_analysis', 'confirmed_single_meal'],
    ['meal_feedback', 'single_meal_feedback']
  ]) {
    const result = {
      result_type: type,
      status: 'needs_input',
      scope,
      questions: ['希望分析哪一餐？', '请补充确认记录。'],
      ...(type === 'meal_feedback' ? { nutrition_recalculated: false } : {})
    }
    assert.deepEqual(published(result), result)
    const tree = renderResult(result)
    const text = visibleText(tree)
    assert.match(text, /请补充信息/)
    assert.match(text, /希望分析哪一餐？/)
    assert.match(text, /请在下方消息框补充这些信息/)
    assert.equal(nodes(tree, 'table').length, 0)
    assert.doesNotMatch(text, /已保存版本|kcal|确认记录总和/)
    assert.equal(published({ ...result, questions: [''] }), null)
    assert.equal(published({ ...result, scope: 'unknown' }), null)
  }
})

test('真实消息组件只切换有发布证据的正文，错 Run 或部分 JSON 保留既有 Markdown', () => {
  const props = Vue.reactive({
    message: persistedMessage(singleMeal()),
    run: clone(completedRun),
    agentSlug: 'health-diet-analyst',
    isProcessing: false
  })
  const block = sources.message.slice(
    sources.message.indexOf('const dietAnalysisResult ='),
    sources.message.indexOf('</script>')
  )
  const state = new Function(
    'computed',
    'publishedDietAnalysisResult',
    'props',
    `${block}\nreturn dietAnalysisResult`
  )(Vue.computed, publishedDietAnalysisResult, props)
  const fragment = sources.message.match(
    /<HealthDietAnalysisResult[\s\S]*?<\/MarkdownPreview>|<HealthDietAnalysisResult[\s\S]*?code-copy[\s\S]*?\/>/
  )[0]
  const render = renderer(fragment, 'AgentMessageComponent.vue')
  const renderOwner = () =>
    render(
      Vue.proxyRefs({
        dietAnalysisResult: state,
        message: props.message,
        parsedData: { content: props.message.content }
      }),
      []
    )
  assert.equal(nodes(renderOwner(), 'HealthDietAnalysisResult').length, 1)
  assert.equal(nodes(renderOwner(), 'MarkdownPreview').length, 0)
  for (const result of [singleMeal(), periodFacts()]) {
    const withTargets = {
      ...result,
      current_personal_targets: {
        scope: 'current_personal_targets',
        status: 'ready',
        energy_kcal: '1800.00',
        bounds: { protein_g: { min: '60.00', max: '90.00' } },
        units: { energy_kcal: 'kcal', protein_g: 'g' },
        sources: { profile_version: 3, rule_version: 'synthetic-approved-v1' },
        source_hash: 'synthetic-target-source',
        professional_review: 'not_a_professional_decision',
        applied_to_record_window: false
      }
    }
    props.message = persistedMessage(withTargets)
    assert.equal(published(withTargets), null)
    assert.equal(nodes(renderOwner(), 'HealthDietAnalysisResult').length, 0)
    assert.equal(nodes(renderOwner(), 'MarkdownPreview')[0].props.content, props.message.content)
    assert.deepEqual(
      JSON.parse(nodes(renderOwner(), 'MarkdownPreview')[0].props.content).current_personal_targets,
      withTargets.current_personal_targets
    )
  }
  props.message = persistedMessage(singleMeal())
  props.run.status = 'running'
  assert.equal(nodes(renderOwner(), 'HealthDietAnalysisResult').length, 0)
  assert.equal(nodes(renderOwner(), 'MarkdownPreview')[0].props.content, props.message.content)
  props.run.status = 'completed'
  props.run.run_id = 'wrong-run'
  assert.equal(nodes(renderOwner(), 'HealthDietAnalysisResult').length, 0)
  props.run.run_id = 'run-old'
  props.message.content = '{"result_type":"diet_analysis"'
  assert.equal(nodes(renderOwner(), 'MarkdownPreview')[0].props.content, props.message.content)
  props.message = persistedMessage(feedbackReceipt())
  assert.equal(nodes(renderOwner(), 'HealthDietAnalysisResult')[0].props.result.feedback.version, 4)
  props.agentSlug = 'base'
  assert.equal(nodes(renderOwner(), 'HealthDietAnalysisResult').length, 0)
})

test('主会话和线程消息列表实际装配按每条消息匹配 Run，历史续跑分组不借用别的完成状态', () => {
  const own = clone(completedRun)
  const child = { run_id: 'run-child', request_id: 'request-child', status: 'failed' }
  const threadRuns = Vue.ref({ 'thread-health': [own, child] })
  const currentChatId = Vue.ref('thread-health')
  const block = sources.chat.slice(
    sources.chat.indexOf('const currentThreadRuns ='),
    sources.chat.indexOf('const currentThreadHasHistory =')
  )
  const getMessageRun = new Function(
    'computed',
    'threadRuns',
    'currentChatId',
    'getMessageRunId',
    `${block}\nreturn getMessageRun`
  )(Vue.computed, threadRuns, currentChatId, getMessageRunId)
  const context = {
    displayItem: { type: 'message', message: persistedMessage(periodFacts()) },
    row: { conv: { run: child } },
    conv: { run: child },
    currentThread: { agent_id: 'health-diet-analyst' },
    currentAgentId: 'base',
    agentSlug: 'health-diet-analyst',
    runs: threadRuns.value['thread-health'],
    getMessageRun,
    isDisplayMessageProcessing: () => false,
    showMsgRefs: () => false,
    mentionConfig: {},
    retryMessage: () => {}
  }
  const chatFragment = sources.chat.match(
    /<AgentMessageComponent[\s\S]*?<\/AgentMessageComponent>/
  )[0]
  const listFragment = sources.list.match(/<AgentMessageComponent[\s\S]*?\/>/)[0]
  for (const [fragment, file] of [
    [chatFragment, 'AgentChatComponent.vue'],
    [listFragment, 'ThreadMessageList.vue']
  ]) {
    const render = renderer(fragment, file)
    const vnode = render(context, [])
    assert.equal(vnode.props['agent-slug'], 'health-diet-analyst')
    assert.equal(vnode.props.run.run_id, own.run_id)
    assert.equal(vnode.props.run.status, 'completed')
    assert.equal(vnode.props.message, context.displayItem.message)
    assert.ok(
      publishedDietAnalysisResult(
        vnode.props.message,
        vnode.props.run,
        vnode.props['agent-slug'],
        vnode.props['is-processing']
      )
    )
    context.displayItem.message = { ...persistedMessage(periodFacts()), run_id: 'missing-run' }
    const missing = render(context, [])
    assert.equal(missing.props.run, null)
    assert.equal(
      publishedDietAnalysisResult(
        missing.props.message,
        missing.props.run,
        missing.props['agent-slug']
      ),
      null
    )
    context.displayItem.message = persistedMessage(periodFacts())
  }
  currentChatId.value = 'other-thread'
  assert.equal(getMessageRun(context.displayItem.message), null)
})

test('假完成状态负控确实能击穿来源 oracle，移除 completed guard 时测试会失败', () => {
  const mutated = sources.parser.replace("    run.status !== 'completed' ||", '')
  assert.notEqual(mutated, sources.parser)
  const unsafe = new Function(
    `${mutated.replace('export function', 'function')}\nreturn publishedDietAnalysisResult`
  )()
  const oracle = (parseResult) =>
    assert.equal(
      parseResult(
        persistedMessage(singleMeal()),
        { ...completedRun, status: 'failed' },
        'health-diet-analyst'
      ),
      null
    )
  oracle(publishedDietAnalysisResult)
  assert.throws(() => oracle(unsafe), { code: 'ERR_ASSERTION' })
})

test('公共窄屏宽度例外仅装配到健康后台与聊天路由，不扩展到其他后台', () => {
  const fragment = parse(sources.layout).descriptor.template.content.split('<button')[0] + '</div>'
  const render = renderer(fragment, 'AppLayout.vue')
  for (const name of ['HealthVision', 'AgentMain']) {
    const vnode = render({ sidebarCollapsed: true, route: { matched: [{ name }] } }, [])
    assert.match(vnode.props.class, /health-agent-layout/)
  }
  for (const name of ['agent-manage', 'workspace', 'family', 'settings']) {
    const vnode = render({ sidebarCollapsed: true, route: { matched: [{ name }] } }, [])
    assert.doesNotMatch(vnode.props.class, /health-agent-layout/)
  }
})
