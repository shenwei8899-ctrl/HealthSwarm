import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { computed, effectScope, nextTick, reactive, ref, watch } from 'vue'

const source = await readFile(
  new URL('../src/components/health/HealthMemoryDaily.vue', import.meta.url),
  'utf8'
)
const script = source
  .match(/<script setup>([\s\S]*?)<\/script>/)[1]
  .replace(/^import[\s\S]*?from ['"][^'"]+['"]\s*\n/gm, '')

/** 执行实际页面状态，观察迟到响应及请求重放，避免复制实现。 */
function panel(api) {
  const props = reactive({
    memberId: 'member-a',
    scopes: ['ai_use', 'profile_edit', 'report_view', 'diet_edit']
  })
  const scope = effectScope()
  const factory = new Function(
    'ref',
    'computed',
    'watch',
    'onMounted',
    'onBeforeUnmount',
    'defineProps',
    'useRouter',
    'api',
    `${script}\nreturn { memories, days, reload, edit, editAttempt, openEdit, saveEdit, working, error, canRead, selectedThread, summary, showSummary }`
  )
  const state = scope.run(() =>
    factory(
      ref,
      computed,
      watch,
      () => {},
      () => {},
      () => props,
      () => ({ push() {} }),
      api
    )
  )
  return { props, ...state, dispose: () => scope.stop() }
}

test('切换成员时旧请求不能填入新成员记忆或日期列表', async () => {
  let finishOld
  const state = panel({
    memberMemory: (id) =>
      id === 'member-a'
        ? new Promise((resolve) => {
            finishOld = resolve
          })
        : Promise.resolve({ memories: [] }),
    dailyHistory: async (id) => ({ days: [{ thread_id: id }], next_before: null })
  })
  const old = state.reload()
  state.props.memberId = 'member-b'
  await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  finishOld({ memories: [{ content: '不得展示的旧成员内容' }] })
  await old
  assert.deepEqual(state.memories.value, [])
  assert.equal(state.days.value[0].thread_id, 'member-b')
  state.props.scopes = []
  await nextTick()
  assert.equal(state.canRead.value, false)
  assert.deepEqual(state.days.value, [])
  state.dispose()
})

test('保存未知响应后重试相同内容和版本，成功再回读服务器结果', async () => {
  const requests = []
  const state = panel({
    memberMemory: async () => ({
      memories: [{ memory_id: 'fact', version: 2, content: '服务器确认内容' }]
    }),
    dailyHistory: async () => ({ days: [] }),
    editMemory: async (id, data) => {
      requests.push({ id, data: { ...data } })
      if (requests.length === 1) throw new Error('synthetic unknown response')
    }
  })
  state.openEdit({ memory_id: 'fact', version: 1, content: '本次编辑', kind: 'preference' })
  await state.saveEdit()
  assert.equal(state.working.value, false)
  assert.ok(state.editAttempt.value.client_request_id)
  state.edit.value.content = '未知响应后不能改变已提交正文'
  await state.saveEdit()
  assert.deepEqual(requests[0], requests[1])
  assert.equal(state.memories.value[0].version, 2)
  assert.equal(state.memories.value[0].content, '服务器确认内容')
  assert.equal(state.edit.value, null)
  state.dispose()
})

test('旧日期摘要迟到不能覆盖新日期选择', async () => {
  let finishOld
  const state = panel({
    dailySummary: (id) =>
      id === 'older'
        ? new Promise((resolve) => {
            finishOld = resolve
          })
        : Promise.resolve({ date: '2026-10-06', status: 'day_open' })
  })
  const old = state.showSummary('older')
  await state.showSummary('newer')
  finishOld({ date: '2026-10-05', status: 'ready' })
  await old
  assert.equal(state.selectedThread.value, 'newer')
  assert.equal(state.summary.value.date, '2026-10-06')
  state.dispose()
})
