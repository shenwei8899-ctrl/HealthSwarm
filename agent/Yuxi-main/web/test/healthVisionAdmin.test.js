import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import * as Vue from 'vue'
import { parse, compileTemplate } from 'vue/compiler-sfc'
import { nutrientLabels } from '../src/utils/healthVision.js'

const source = await readFile(
  new URL('../src/components/health/HealthVisionAdmin.vue', import.meta.url),
  'utf8'
)
const { descriptor } = parse(source)
const script = descriptor.scriptSetup.content.replace(/^import[^\n]+\n/gm, '')
const compiled = compileTemplate({
  source: descriptor.template.content,
  filename: 'HealthVisionAdmin.vue',
  id: 'health-admin-test',
  compilerOptions: { mode: 'function' }
})
assert.deepEqual(compiled.errors, [])
const render = new Function('Vue', compiled.code)({ ...Vue, resolveComponent: (name) => name })

/** 独立给定七项已有配置，采购模型未就绪时也须保留。 */
function configuration() {
  return {
    report: { model: 'synthetic:report-fixed' },
    meal: { model: 'synthetic:qwen3-vl-flash-2026-01-22' },
    consultation: { model: 'synthetic:consultation-fixed' },
    meal_plan: { model: 'synthetic:planner-fixed' },
    diet_analysis: { model: 'synthetic:analyst-fixed' },
    quality_review: { model: 'synthetic:quality-fixed' },
    purchase: { model: 'synthetic:purchase-fixed', available: false, reason: '合成供应商未就绪' },
    policy_version: 'synthetic-policy-v1',
    model_options: [],
    food_count: 0
  }
}

/** 执行实际 SFC 与模板，将选择事件送回真实响应式状态。 */
function admin(api = {}) {
  const props = Vue.reactive({ configuration: configuration() })
  const scope = Vue.effectScope()
  const events = []
  const state = scope.run(() =>
    new Function(
      'computed',
      'reactive',
      'ref',
      'watch',
      'inject',
      'defineProps',
      'defineEmits',
      'healthVisionApi',
      'message',
      'nutrientLabels',
      `${script}\nreturn { settings, busy, saveConfiguration, food, openSettings, consultation, consultationNextStep }`
    )(
      Vue.computed,
      Vue.reactive,
      Vue.ref,
      Vue.watch,
      () => null,
      () => props,
      () => (event) => events.push(event),
      api,
      { success() {}, error() {}, warning() {} },
      nutrientLabels
    )
  )
  return {
    ...state,
    props,
    events,
    template: () => render(Vue.proxyRefs({ ...state, configuration: props.configuration }), []),
    dispose: () => scope.stop()
  }
}

/** 遍历实际模板 VNode，包括 v-for 生成的 Fragment。 */
function nodes(node, type) {
  if (!node || typeof node !== 'object') return []
  return [
    ...(node.type === type ? [node] : []),
    ...(Array.isArray(node.children) ? node.children.flatMap((child) => nodes(child, type)) : [])
  ]
}

test('保存其他服务配置保留已有未就绪采购模型并要求管理员重新批准', async () => {
  const requests = []
  const state = admin({
    configure: async (value) => requests.push(structuredClone(Vue.toRaw(value)))
  })
  assert.equal(state.settings.cloud_processing_reviewed, false)
  state.settings.quality_review_model = 'synthetic:quality-v2'
  state.settings.cloud_processing_reviewed = true
  await state.saveConfiguration()
  assert.deepEqual(requests, [
    {
      report_model: 'synthetic:report-fixed',
      meal_model: 'synthetic:qwen3-vl-flash-2026-01-22',
      consultation_model: 'synthetic:consultation-fixed',
      meal_plan_model: 'synthetic:planner-fixed',
      diet_analysis_model: 'synthetic:analyst-fixed',
      quality_review_model: 'synthetic:quality-v2',
      purchase_model: 'synthetic:purchase-fixed',
      policy_version: 'synthetic-policy-v1',
      cloud_processing_reviewed: true
    }
  ])
  assert.deepEqual(state.events, ['saved'])
  assert.equal(state.busy.value, false)
  state.dispose()
})

test('实际模板显示七个选择项，清空配餐仅停用配餐服务', async () => {
  const requests = []
  const state = admin({
    configure: async (value) => requests.push(structuredClone(Vue.toRaw(value)))
  })
  const selectors = nodes(state.template(), 'a-select')
  assert.equal(selectors.length, 7)
  assert.deepEqual(
    selectors.map((node) => node.props.value),
    [
      'synthetic:report-fixed',
      'synthetic:qwen3-vl-flash-2026-01-22',
      'synthetic:consultation-fixed',
      'synthetic:planner-fixed',
      'synthetic:analyst-fixed',
      'synthetic:quality-fixed',
      'synthetic:purchase-fixed'
    ]
  )
  selectors[3].props['onUpdate:value'](undefined)
  selectors[3].props.onChange(undefined)
  state.settings.cloud_processing_reviewed = true
  await state.saveConfiguration()
  assert.equal(requests[0].meal_plan_model, '')
  assert.equal(requests[0].diet_analysis_model, 'synthetic:analyst-fixed')
  assert.equal(requests[0].quality_review_model, 'synthetic:quality-fixed')
  assert.equal(requests[0].consultation_model, 'synthetic:consultation-fixed')
  assert.equal(requests[0].purchase_model, 'synthetic:purchase-fixed')
  state.dispose()
})

test('重载服务端配置更新角色模型且重置审批', async () => {
  const state = admin()
  state.settings.cloud_processing_reviewed = true
  state.props.configuration = {
    ...configuration(),
    meal_plan: { model: 'synthetic:planner-v2' },
    purchase: { model: 'synthetic:purchase-v2', available: false }
  }
  await Vue.nextTick()
  assert.equal(state.settings.meal_plan_model, 'synthetic:planner-v2')
  assert.equal(state.settings.purchase_model, 'synthetic:purchase-v2')
  assert.equal(state.settings.cloud_processing_reviewed, false)
  state.dispose()
})

test('管理员明确清空采购选择仅停用采购模型', async () => {
  const requests = []
  const state = admin({
    configure: async (value) => requests.push(structuredClone(Vue.toRaw(value)))
  })
  const selector = nodes(state.template(), 'a-select')[6]
  selector.props['onUpdate:value'](undefined)
  selector.props.onChange(undefined)
  state.settings.cloud_processing_reviewed = true
  await state.saveConfiguration()
  assert.equal(requests[0].purchase_model, '')
  assert.equal(requests[0].meal_plan_model, 'synthetic:planner-fixed')
  assert.equal(requests[0].quality_review_model, 'synthetic:quality-fixed')
  state.dispose()
})

test('配置保存失败不发出已保存事件并释放忙碌状态', async () => {
  const state = admin({
    configure: async () => {
      throw new Error('synthetic rejected configuration')
    }
  })
  await state.saveConfiguration()
  assert.deepEqual(state.events, [])
  assert.equal(state.busy.value, false)
  state.dispose()
})

test('本地填写政策与模型和勾选审批不改变服务端未就绪状态', async () => {
  const state = admin({
    configure: async () => {
      throw new Error('save rejected')
    }
  })
  state.props.configuration = {
    ...configuration(),
    policy_version: '',
    consultation: {
      available: false,
      model: '',
      reason_code: 'policy_not_approved',
      reason: '尚未审批云处理政策'
    }
  }
  await Vue.nextTick()
  state.settings.policy_version = 'local-unsaved-v1'
  state.settings.consultation_model = 'synthetic:local-model'
  state.settings.cloud_processing_reviewed = true
  await state.saveConfiguration()
  const alert = nodes(state.template(), 'a-alert')[0]
  assert.equal(alert.props.type, 'warning')
  assert.equal(alert.props.message, '咨询服务配置尚未就绪')
  assert.match(alert.props.description, /尚未审批云处理政策/)
  assert.match(alert.props.description, /负责人确认实际数据处理政策/)
  const saved = nodes(state.template(), 'dd').map((node) => node.children)
  assert.deepEqual(saved, ['未选择', '未登记'])
  assert.deepEqual(state.events, [])
  state.dispose()
})

test('服务端重载可用状态后仍提示成员授权和实际问答验收', async () => {
  const state = admin()
  state.props.configuration = {
    ...configuration(),
    consultation: {
      available: true,
      model: 'synthetic:consultation-v2',
      processor: 'synthetic-processor'
    }
  }
  await Vue.nextTick()
  const alert = nodes(state.template(), 'a-alert')[0]
  assert.equal(alert.props.type, 'info')
  assert.match(alert.props.message, /成员授权与问答效果需另行验收/)
  assert.match(alert.props.description, /AI 读取授权和本次咨询用途同意/)
  assert.deepEqual(
    nodes(state.template(), 'dd').map((node) => node.children),
    ['synthetic:consultation-v2', 'synthetic-policy-v1']
  )
  assert.equal(state.settings.cloud_processing_reviewed, false)
  assert.deepEqual(state.events, [])
  state.dispose()
})

test('未配置模型和处理方变化分别提供实际恢复路径', async () => {
  const state = admin()
  for (const [reason_code, expected] of [
    ['model_unavailable', /启用带有效凭据的模型供应商/],
    ['processor_approval_changed', /重新取得成员用途同意/],
    ['future_reason', /请管理员核对下方模型与政策配置/]
  ]) {
    state.props.configuration = {
      ...configuration(),
      consultation: { available: false, reason_code, reason: '服务端实际原因' }
    }
    await Vue.nextTick()
    const alert = nodes(state.template(), 'a-alert')[0]
    assert.equal(alert.props.type, 'warning')
    assert.match(alert.props.description, /服务端实际原因/)
    assert.match(alert.props.description, expected)
  }
  state.dispose()
})

test('缺失咨询配置仍显示未就绪且不发起配置写入', async () => {
  const state = admin({ configure: () => assert.fail('只读展示不应写入') })
  state.props.configuration = { ...configuration(), consultation: undefined }
  await Vue.nextTick()
  const alert = nodes(state.template(), 'a-alert')[0]
  assert.equal(alert.props.type, 'warning')
  assert.match(alert.props.description, /尚未取得可用的咨询配置/)
  assert.deepEqual(state.events, [])
  state.dispose()
})
