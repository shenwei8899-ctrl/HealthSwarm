import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import * as Vue from 'vue'
import { parse, compileTemplate } from 'vue/compiler-sfc'

const view = await readFile(new URL('../src/views/HealthVisionView.vue', import.meta.url), 'utf8')
const feedback = await readFile(
  new URL('../src/components/health/HealthFeedbackConversation.vue', import.meta.url),
  'utf8'
)

/** 执行实际模板事件，而非按字符串判断组件已接入。 */
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

/** 保留默认插槽内的组件及动态条件节点。 */
function nodes(node, type) {
  if (!node || typeof node !== 'object') return []
  const children = Array.isArray(node.children)
    ? node.children
    : typeof node.children?.default === 'function'
      ? node.children.default()
      : []
  return [...(node.type === type ? [node] : []), ...children.flatMap((child) => nodes(child, type))]
}

test('健康识图页饮食分析分区传同一成员授权、当前配置及已确认记录', () => {
  const block = view.slice(view.indexOf('const tabs ='), view.indexOf('const editable ='))
  const tabs = new Function('computed', 'userStore', `${block}\nreturn tabs`)(Vue.computed, {
    isAdmin: false
  })
  assert.ok(tabs.value.some((tab) => tab.key === 'analysis' && tab.label === '饮食分析'))
  const context = {
    memberId: 'member-a',
    member: { scopes: ['diet_edit', 'ai_use'] },
    config: { diet_analysis: { available: true } },
    records: { meal: [{ id: 'meal-a', source_version: 3 }] },
    busy: false,
    confirming: false
  }
  const fragment = view
    .match(/<HealthDietAnalysis[\s\S]*?\/>/)[0]
    .replace(/\s+v-else-if="[^"]*"/, '')
  const vnode = renderer(fragment, 'HealthVisionView.vue')(context, [])
  assert.equal(vnode.type, 'HealthDietAnalysis')
  assert.equal(vnode.props['member-id'], 'member-a')
  assert.deepEqual(vnode.props.scopes, ['diet_edit', 'ai_use'])
  assert.equal(vnode.props.records, context.records.meal)
  assert.equal(vnode.props.configuration, context.config)
  context.memberId = 'member-b'
  context.member = { scopes: [] }
  context.records.meal = []
  const changed = renderer(fragment, 'HealthVisionView.vue')(context, [])
  assert.equal(changed.props['member-id'], 'member-b')
  assert.deepEqual(changed.props.scopes, [])
  assert.deepEqual(changed.props.records, [])
  assert.notEqual(changed.key, vnode.key)
})

test('已确认饮食记录保留手动反馈并装配同一餐的独立反馈对话', () => {
  const context = {
    memberId: 'member-a',
    member: { scopes: ['diet_edit', 'ai_use'] },
    config: {},
    record: { id: 'meal-a', source_version: 3 },
    busy: false,
    confirming: false
  }
  const fragment = `${view.match(/<HealthMealFeedback[\s\S]*?\/>/)[0]}${view.match(/<HealthFeedbackConversation[\s\S]*?\/>/)[0]}`
  const tree = renderer(fragment, 'HealthVisionView.vue')(context, [])
  assert.equal(nodes(tree, 'HealthMealFeedback')[0].props.record, context.record)
  const entry = nodes(tree, 'HealthFeedbackConversation')[0]
  assert.equal(entry.props.record, context.record)
  assert.equal(entry.props['member-id'], 'member-a')
  assert.deepEqual(entry.props.scopes, context.member.scopes)
  assert.equal(entry.props.configuration, context.config)
})

test('反馈对话按钮打开专属模式，提交中阻止关闭，关闭后销毁旧同意和私有状态', () => {
  const { descriptor } = parse(feedback)
  const script = descriptor.scriptSetup.content.replace(/^import[^\n]+\n/gm, '')
  const state = new Function('ref', 'defineProps', `${script}\nreturn {open,working}`)(
    Vue.ref,
    () => {}
  )
  const props = {
    memberId: 'member-a',
    scopes: ['diet_edit', 'ai_use'],
    configuration: {},
    record: { id: 'meal-a', source_version: 3 },
    disabled: false
  }
  const context = Vue.proxyRefs({ ...props, ...state })
  const render = renderer(descriptor.template.content, 'HealthFeedbackConversation.vue')
  assert.equal(nodes(render(context, []), 'HealthDietAnalysis').length, 0)
  nodes(render(context, []), 'a-button')[0].props.onClick()
  assert.equal(state.open.value, true)
  const child = nodes(render(context, []), 'HealthDietAnalysis')[0]
  assert.equal(child.props.record.id, 'meal-a')
  assert.equal(child.props['member-id'], 'member-a')
  assert.ok(Object.hasOwn(child.props, 'feedback'))
  child.props.onBusy(true)
  const modal = nodes(render(context, []), 'a-modal')[0]
  assert.equal(modal.props['mask-closable'], false)
  assert.equal(modal.props.closable, false)
  assert.equal(modal.props['destroy-on-close'], true)
  child.props.onBusy(false)
  modal.props['onUpdate:open'](false)
  assert.equal(nodes(render(context, []), 'HealthDietAnalysis').length, 0)
})
