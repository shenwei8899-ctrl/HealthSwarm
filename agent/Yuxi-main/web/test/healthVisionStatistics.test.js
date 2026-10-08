import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { ref, watch, reactive, effectScope, nextTick } from 'vue'

const source = await readFile(
  new URL('../src/components/health/HealthVisionStatistics.vue', import.meta.url),
  'utf8'
)
const script = source
  .match(/<script setup>([\s\S]*?)<\/script>/)[1]
  .replace(/^import[^\n]+\n/gm, '')

function statistics(api, changes = {}) {
  const props = reactive({ memberId: 'member-a', kind: 'report', allowed: true, ...changes })
  const scope = effectScope()
  let unmount
  const factory = new Function(
    'ref',
    'watch',
    'onBeforeUnmount',
    'defineProps',
    'api',
    `${script}\nreturn { load, toggle, summary, loading, error, expanded, seconds, rate }`
  )
  const state = scope.run(() =>
    factory(
      ref,
      watch,
      (fn) => {
        unmount = fn
      },
      () => props,
      api
    )
  )
  return {
    ...state,
    props,
    dispose: () => {
      unmount()
      scope.stop()
    }
  }
}

test('统计按需读取，零样本不显示零秒或零费用', async () => {
  const calls = []
  const state = statistics({
    statistics: async (...args) => {
      calls.push(args)
      return { kind: 'report', sample: 0 }
    }
  })
  assert.equal(calls.length, 0)
  await state.load()
  assert.deepEqual(calls, [['member-a', 'report']])
  assert.equal(state.loading.value, false)
  assert.equal(state.seconds(null), '暂无样本')
  assert.equal(state.rate(null), '暂无样本')
  assert.equal(state.seconds(0), '0 秒')
  state.dispose()
})

for (const [key, value] of [
  ['memberId', 'member-b'],
  ['kind', 'meal'],
  ['allowed', false]
]) {
  test(`统计 ${key} 变化清空并拒绝迟到响应`, async () => {
    let resolve
    const state = statistics({
      statistics: () =>
        new Promise((r) => {
          resolve = r
        })
    })
    state.expanded.value = true
    const pending = state.load()
    assert.equal(state.loading.value, true)
    state.props[key] = value
    resolve({ private: 'member-a-data' })
    await pending
    await nextTick()
    assert.equal(state.summary.value, null)
    assert.equal(state.loading.value, false)
    assert.equal(state.expanded.value, false)
    state.dispose()
  })
}

test('刷新失败清空旧私有摘要并给出可恢复错误', async () => {
  const state = statistics({
    statistics: async () => {
      throw new Error('权限已撤回')
    }
  })
  state.summary.value = { private: 'old' }
  await state.load()
  assert.equal(state.summary.value, null)
  assert.equal(state.error.value, '权限已撤回')
  assert.equal(state.loading.value, false)
  state.dispose()
})

test('没有成员或用途权限不发起请求，卸载后拒绝回填', async () => {
  let calls = 0
  let resolve
  const state = statistics(
    {
      statistics: () => {
        calls++
        return new Promise((r) => {
          resolve = r
        })
      }
    },
    { allowed: false }
  )
  await state.load()
  state.props.allowed = true
  state.props.memberId = ''
  await nextTick()
  await state.load()
  assert.equal(calls, 0)
  state.props.memberId = 'member-a'
  await nextTick()
  const pending = state.load()
  state.dispose()
  resolve({ private: 'late' })
  await pending
  assert.equal(state.summary.value, null)
})

test('模板说明口径与未知费用，不把执行成功称作准确率', () => {
  assert.match(source, /修改比例与执行成功均不是识别准确率/)
  assert.match(source, /费用：未知/)
  assert.match(source, /summary\.reviews\.original_items/)
  assert.match(source, /summary\.tasks\.queue\.sample_count/)
})
