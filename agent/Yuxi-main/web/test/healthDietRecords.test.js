import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { setImmediate } from 'node:timers'
import { computed, effectScope, reactive, ref, watch, nextTick } from 'vue'

const source = await readFile(
  new URL('../src/components/health/HealthDietRecords.vue', import.meta.url),
  'utf8'
)
const script = source
  .match(/<script setup>([\s\S]*?)<\/script>/)[1]
  .replace(/^import[^\n]+\n/gm, '')
function panel(dietLogPage) {
  const props = reactive({
    memberId: 'a',
    scopes: ['diet_edit'],
    configuration: {},
    refreshKey: {},
    disabled: false
  })
  const scope = effectScope()
  let cleanup
  const state = scope.run(() =>
    new Function(
      'ref',
      'computed',
      'watch',
      'onBeforeUnmount',
      'defineProps',
      'api',
      `${script}\nreturn {records,offset,nextOffset,loading,error,readPage,reload,previousPage,nextPage,pageNumber}`
    )(
      ref,
      computed,
      watch,
      (fn) => {
        cleanup = fn
      },
      () => props,
      { dietLogPage }
    )
  )
  return {
    ...state,
    props,
    dispose: () => {
      cleanup()
      scope.stop()
    }
  }
}
const tick = async () => {
  await nextTick()
  await new Promise((r) => setImmediate(r))
}
const deferred = () => {
  let resolve
  const promise = new Promise((r) => {
    resolve = r
  })
  return { promise, resolve }
}

test('第一页、空中间页及末页使用服务端位置，前后翻页和刷新有明确边界', async () => {
  const calls = []
  const p = panel(async (id, limit, offset) => {
    calls.push([id, limit, offset])
    return {
      records: offset === 20 ? [] : [{ id: String(offset) }],
      next_offset: offset < 40 ? offset + 20 : null
    }
  })
  await tick()
  await p.previousPage()
  await p.nextPage()
  assert.equal(p.offset.value, 20)
  assert.deepEqual(p.records.value, [])
  assert.equal(p.nextOffset.value, 40)
  await p.nextPage()
  assert.equal(p.pageNumber.value, 3)
  assert.equal(p.nextOffset.value, null)
  await p.nextPage()
  assert.equal(calls.length, 3)
  await p.previousPage()
  await p.reload()
  assert.deepEqual(
    calls.map((v) => v[2]),
    [0, 20, 40, 20, 0]
  )
  p.dispose()
})

test('切换成员、撤回授权及卸载均丢弃迟到数据并立即清除私有页', async () => {
  const responses = []
  const p = panel(() => {
    const r = deferred()
    responses.push(r)
    return r.promise
  })
  assert.equal(p.loading.value, true)
  p.props.memberId = 'b'
  await nextTick()
  responses[0].resolve({ records: [{ id: 'a-private' }], next_offset: 20 })
  await tick()
  assert.deepEqual(p.records.value, [])
  assert.equal(p.loading.value, true)
  p.props.scopes = []
  await nextTick()
  responses[1].resolve({ records: [{ id: 'b-private' }], next_offset: 20 })
  await tick()
  assert.deepEqual(p.records.value, [])
  assert.equal(p.loading.value, false)
  p.props.scopes = ['diet_edit']
  await nextTick()
  p.dispose()
  responses[2].resolve({ records: [{ id: 'after-unmount' }], next_offset: 20 })
  await tick()
  assert.deepEqual(p.records.value, [])
})

test('晚到翻页响应不会覆盖刷新；失败清空内容且重试原页', async () => {
  const responses = []
  const p = panel(() => {
    const r = deferred()
    responses.push(r)
    return r.promise
  })
  const refresh = p.reload()
  responses[1].resolve({ records: [{ id: 'fresh' }], next_offset: 20 })
  await refresh
  responses[0].resolve({ records: [{ id: 'stale' }], next_offset: null })
  await tick()
  assert.deepEqual(p.records.value, [{ id: 'fresh' }])
  let fail = true
  p.dispose()
  const q = panel(async () => {
    if (fail) throw Object.assign(new Error(), { status: 404 })
    return { records: [{ id: 'retry' }], next_offset: null }
  })
  await tick()
  assert.match(q.error.value, /授权已变化/)
  assert.deepEqual(q.records.value, [])
  assert.equal(q.loading.value, false)
  fail = false
  await q.readPage(q.offset.value)
  assert.equal(q.error.value, '')
  assert.deepEqual(q.records.value, [{ id: 'retry' }])
  q.dispose()
})

test('父页轮询更新其他状态不会清除当前页或重新读取', async () => {
  let calls = 0
  const p = panel(async () => {
    calls++
    return { records: [{ id: 'kept' }], next_offset: 20 }
  })
  await tick()
  p.props.refreshKey = { meal: [] }
  p.props.configuration = { changed: true }
  await tick()
  assert.equal(calls, 1)
  assert.deepEqual(p.records.value, [{ id: 'kept' }])
  p.dispose()
})
