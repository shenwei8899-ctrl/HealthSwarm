import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { ref, reactive } from 'vue'

const source = await readFile(
  new URL('../src/components/health/ReportReview.vue', import.meta.url),
  'utf8'
)
const script = source
  .match(/<script setup>([\s\S]*?)<\/script>/)[1]
  .replace(/^import[\s\S]*?from ['"][^'"]+['"]\s*\n/gm, '')

/** 执行真实组件脚本，不复制另一套页面排除算法。 */
function editor(readonly = false) {
  const props = reactive({
    payload: { pages: [], fields: [], excluded_pages: [2] },
    readonly,
    confirmed: false,
    canReprocess: false
  })
  const events = []
  const state = new Function(
    'ref',
    'onBeforeUnmount',
    'defineProps',
    'defineEmits',
    'healthVisionApi',
    'message',
    `${script}\nreturn { togglePage, pageLabel, reprocessPage }`
  )(
    ref,
    () => {},
    () => props,
    () => (event, indices) => events.push({ event, indices }),
    {},
    {}
  )
  return { ...state, props, events }
}

test('明确排除/恢复原页，不重复排除且保留其他页选择', () => {
  const state = editor()
  const page = { page_index: 1, status: 'failed' }
  state.togglePage(page, true)
  state.togglePage(page, true)
  assert.deepEqual(state.events[0], { event: 'excluded-pages', indices: [1, 2] })
  assert.deepEqual(state.events[1], { event: 'excluded-pages', indices: [1, 2] })
  state.togglePage(page, false)
  assert.deepEqual(state.props.payload.excluded_pages, [2])
  assert.deepEqual(state.events[2], { event: 'excluded-pages', indices: [2] })
})

test('确认快照 readonly 不能改变排除页', () => {
  const state = editor(true)
  state.togglePage({ page_index: 1 }, true)
  assert.deepEqual(state.props.payload.excluded_pages, [2])
  assert.deepEqual(state.events, [])
})

test('单页重识别仅在已保存、同意且可编辑时发出原全局页号', () => {
  const state = editor()
  const page = { page_index: 1, status: 'failed' }
  state.reprocessPage(page)
  assert.deepEqual(state.events, [])
  state.props.canReprocess = true
  state.props.readonly = true
  state.reprocessPage(page)
  assert.deepEqual(state.events, [])
  state.props.readonly = false
  state.reprocessPage(page)
  assert.deepEqual(state.events, [{ event: 'reprocess-page', indices: 1 }])
})

test('排除和确认快照文案与识别状态分别投影，加载只读不冒充已确认', () => {
  const state = editor(true)
  assert.equal(state.pageLabel({ page_index: 0, status: 'ready' }), '识别成功 · 待核对')
  assert.equal(state.pageLabel({ page_index: 1, status: 'failed' }), '未识别成功 · 需处理')
  assert.equal(state.pageLabel({ page_index: 2, status: 'failed' }), '未识别成功 · 已明确排除')
  state.props.confirmed = true
  assert.equal(state.pageLabel({ page_index: 0, status: 'ready' }), '识别成功 · 已确认快照')
  assert.equal(state.pageLabel({ page_index: 2, status: 'failed' }), '未识别成功 · 已明确排除')
})
