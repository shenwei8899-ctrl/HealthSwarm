import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import * as Vue from 'vue'
import { parse, compileTemplate } from 'vue/compiler-sfc'

const source = await readFile(
  new URL('../src/components/health/HealthNutritionImport.vue', import.meta.url),
  'utf8'
)
const { descriptor } = parse(source)
const script = descriptor.scriptSetup.content.replace(/^import[^\n]+\n/gm, '')
const compiled = compileTemplate({
  source: descriptor.template.content,
  filename: 'HealthNutritionImport.vue',
  id: 'nutrition-import-test',
  compilerOptions: { mode: 'function' }
})
assert.deepEqual(compiled.errors, [])
const render = new Function('Vue', compiled.code)({ ...Vue, resolveComponent: (name) => name })

function deferred() {
  let resolve, reject
  const promise = new Promise((done, fail) => {
    resolve = done
    reject = fail
  })
  return { promise, resolve, reject }
}

function batch(id = 'batch-a') {
  return {
    id,
    kind: 'food',
    summary: { total: 1, invalid: 0, pending_review: 1 },
    published_count: 0,
    items: [
      {
        row: 1,
        status: 'pending_review',
        issues: [{ field: 'license', code: 'metadata_required' }],
        candidate: { name: '合成食品', source: '合成来源文件名', nutrients: { protein_g: '10' } }
      }
    ],
    knowledge_sources: [
      { source_id: 'source-a', filename: '合成来源文件名', content: '每100克蛋白质10克。' }
    ],
    evidence: [{ row: 1, proofs: [{ field: 'nutrients.protein_g', quote: '每100克蛋白质10克。' }] }]
  }
}

/** 执行实际脚本与模板，身份切换使用真实 watcher。 */
function panel(api = {}) {
  const user = Vue.reactive({ uid: 'admin-a' })
  const cleanup = []
  const scope = Vue.effectScope()
  const bindings = {
    ...Vue,
    onBeforeUnmount: (fn) => cleanup.push(fn),
    useUserStore: () => user,
    api
  }
  const state = scope.run(() =>
    new Function(
      ...Object.keys(bindings),
      `${script}\nreturn { kind, text, report, busy, error, pending, knowledgeQuery, knowledgeTask,
        knowledgePending, prepare, prepareKnowledge, pollKnowledge, locked, batchId, loadBatch,
        editCandidates, candidateJson, evidenceReport }`
    )(...Object.values(bindings))
  )
  return {
    ...state,
    user,
    template: () => render(Vue.proxyRefs(state), []),
    dispose() {
      cleanup.forEach((fn) => fn())
      scope.stop()
    }
  }
}

function nodes(node, type) {
  if (!node || typeof node !== 'object') return []
  return [
    ...(node.type === type ? [node] : []),
    ...(Array.isArray(node.children) ? node.children.flatMap((child) => nodes(child, type)) : [])
  ]
}

test('旧账号提取请求迟到响应不能回填任务、报告或错误', async () => {
  for (const rejected of [false, true]) {
    const request = deferred()
    let polls = 0
    const state = panel({
      prepareKnowledgeNutrition: () => request.promise,
      knowledgeNutritionStatus: async () => {
        polls++
        return { status: 'success', report: batch() }
      }
    })
    state.knowledgeQuery.value = '合成食品'
    const running = state.prepareKnowledge()
    state.user.uid = 'admin-b'
    await Vue.nextTick()
    if (rejected) request.reject(new Error('旧账号错误'))
    else request.resolve({ task_id: 'old-task', status: 'pending' })
    await running
    assert.equal(state.knowledgeTask.value, null)
    assert.equal(state.report.value, null)
    assert.equal(state.error.value, '')
    assert.equal(state.knowledgePending.value, null)
    assert.equal(state.busy.value, false)
    assert.equal(polls, 0)
    state.dispose()
  }
})

test('按批次ID恢复原报告、候选正文及来源证据，读取失败可重试', async () => {
  const calls = []
  const saved = batch()
  const state = panel({
    nutritionImport: async (id) => {
      calls.push(id)
      if (calls.length === 1) throw new Error('读取暂时失败')
      return saved
    }
  })
  state.batchId.value = ' batch-a '
  await state.loadBatch()
  assert.equal(state.report.value, null)
  assert.equal(state.error.value, '读取暂时失败')
  assert.equal(state.busy.value, false)
  await state.loadBatch()
  assert.deepEqual(calls, ['batch-a', 'batch-a'])
  assert.deepEqual(Vue.toRaw(state.report.value), saved)
  assert.deepEqual(
    JSON.parse(state.candidateJson.value),
    saved.items.map((row) => row.candidate)
  )
  assert.deepEqual(Vue.toRaw(state.evidenceReport.value).evidence, saved.evidence)
  assert.equal(state.error.value, '')
  state.dispose()
})

test('恢复候选期间切换账号或卸载隔离迟到结果与错误', async () => {
  for (const change of ['user', 'dispose']) {
    for (const rejected of [false, true]) {
      const request = deferred()
      const state = panel({ nutritionImport: () => request.promise })
      state.batchId.value = 'batch-a'
      const running = state.loadBatch()
      if (change === 'user') {
        state.user.uid = 'admin-b'
        await Vue.nextTick()
      } else state.dispose()
      if (rejected) request.reject(new Error('旧批次错误'))
      else request.resolve(batch())
      await running
      assert.equal(state.report.value, null)
      assert.equal(state.error.value, '')
      assert.equal(state.batchId.value, '')
      assert.equal(state.busy.value, false)
      if (change === 'user') state.dispose()
    }
  }
})

test('候选带入编辑后创建新校验批次，原证据保留且不调用发布接口', async () => {
  const calls = []
  const saved = batch()
  const revised = { ...batch('batch-b'), knowledge_sources: undefined, evidence: undefined }
  const api = new Proxy(
    {
      nutritionImport: async () => saved,
      prepareNutritionImport: async (value) => {
        calls.push(structuredClone(Vue.toRaw(value)))
        return revised
      }
    },
    { get: (target, name) => target[name] || (() => assert.fail(`不应调用 ${String(name)}`)) }
  )
  const state = panel(api)
  state.batchId.value = saved.id
  await state.loadBatch()
  state.editCandidates()
  assert.equal(state.pending.value, null)
  const rows = JSON.parse(state.text.value)
  rows[0].license = '待人工核对的授权材料'
  state.text.value = JSON.stringify(rows)
  await state.prepare()
  assert.equal(calls.length, 1)
  assert.equal(calls[0].kind, 'food')
  assert.deepEqual(calls[0].rows, rows)
  assert.ok(calls[0].client_request_id)
  assert.equal(state.report.value.id, 'batch-b')
  assert.deepEqual(Vue.toRaw(state.evidenceReport.value).evidence, saved.evidence)
  assert.equal(state.report.value.published_count, 0)
  assert.equal(state.pending.value, null)
  state.editCandidates()
  await state.prepare()
  assert.equal(calls.length, 2)
  assert.notEqual(calls[0].client_request_id, calls[1].client_request_id)
  state.dispose()
})

test('校验结果未知时恢复与带入操作不能覆盖冻结请求，重试保留原内容', async () => {
  const calls = []
  let reads = 0
  const state = panel({
    nutritionImport: async () => {
      reads++
      return batch()
    },
    prepareNutritionImport: async (value) => {
      calls.push(structuredClone(Vue.toRaw(value)))
      if (calls.length === 1) throw new Error('网络断开')
      return batch('batch-b')
    }
  })
  state.text.value = JSON.stringify([{ name: '原候选' }])
  await state.prepare()
  const frozen = structuredClone(Vue.toRaw(state.pending.value))
  state.report.value = batch()
  state.batchId.value = 'batch-a'
  await state.loadBatch()
  state.editCandidates()
  assert.equal(reads, 0)
  assert.deepEqual(Vue.toRaw(state.pending.value), frozen)
  state.text.value = JSON.stringify([{ name: '不能替换原请求' }])
  state.kind.value = 'recipe'
  await state.prepare()
  assert.deepEqual(calls, [frozen, frozen])
  assert.equal(state.pending.value, null)
  state.dispose()
})

test('提取结果未知时锁定类型及其他候选操作，重试保持主题与类型', async () => {
  const calls = []
  const state = panel({
    prepareKnowledgeNutrition: async (value) => {
      calls.push(structuredClone(Vue.toRaw(value)))
      if (calls.length === 1) throw new Error('网络断开')
      return { task_id: 'task-a', status: 'pending' }
    },
    knowledgeNutritionStatus: async () => ({
      task_id: 'task-a',
      status: 'success',
      report: batch()
    }),
    nutritionImport: () => assert.fail('冻结提取期间不能读取其他批次'),
    prepareNutritionImport: () => assert.fail('冻结提取期间不能提交其他候选')
  })
  state.knowledgeQuery.value = '原主题'
  await state.prepareKnowledge()
  assert.equal(nodes(state.template(), 'a-select')[0].props.disabled, true)
  assert.equal(nodes(state.template(), 'a-textarea')[0].props.disabled, true)
  state.report.value = batch()
  state.text.value = '[{"name":"其他候选"}]'
  state.batchId.value = 'batch-a'
  await state.loadBatch()
  await state.prepare()
  state.editCandidates()
  assert.equal(state.text.value, '[{"name":"其他候选"}]')
  state.kind.value = 'recipe'
  state.knowledgeQuery.value = '新主题'
  await state.prepareKnowledge()
  assert.deepEqual(calls[0], calls[1])
  assert.equal(state.knowledgePending.value, null)
  assert.equal(state.report.value.id, 'batch-a')
  state.dispose()
})

test('候选校验请求在账号切换后不回填报告或遗留冻结请求', async () => {
  const request = deferred()
  const state = panel({ prepareNutritionImport: () => request.promise })
  state.text.value = '[{"name":"合成候选"}]'
  const running = state.prepare()
  state.user.uid = 'admin-b'
  await Vue.nextTick()
  request.resolve(batch())
  await running
  assert.equal(state.report.value, null)
  assert.equal(state.pending.value, null)
  assert.equal(state.text.value, '')
  assert.equal(state.busy.value, false)
  state.dispose()
})
