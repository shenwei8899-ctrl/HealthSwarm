import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { computed, effectScope, nextTick, reactive, ref, watch } from 'vue'

const source = await readFile(
  new URL('../src/components/health/HealthMealFeedback.vue', import.meta.url),
  'utf8'
)
const script = source
  .match(/<script setup>([\s\S]*?)<\/script>/)[1]
  .replace(/^import[\s\S]*?from ['"][^'"]+['"]\s*\n/gm, '')

function panel(api) {
  const props = reactive({ record: { id: 'record-a', snapshot: { meal: { meal_type: 'lunch' } } } })
  const scope = effectScope()
  let cleanup
  const factory = new Function(
    'ref',
    'computed',
    'watch',
    'onBeforeUnmount',
    'defineProps',
    'api',
    `${script}\nreturn { reload, save, revoke, form, current, revisions, canSave, error, working, attempt, revokeAttempt }`
  )
  const state = scope.run(() =>
    factory(
      ref,
      computed,
      watch,
      (fn) => {
        cleanup = fn
      },
      () => props,
      api
    )
  )
  return {
    props,
    ...state,
    dispose: () => {
      cleanup()
      scope.stop()
    }
  }
}

test('切换餐次拒绝迟到反馈及修订', async () => {
  let finish
  const state = panel({
    mealFeedback: () =>
      new Promise((resolve) => {
        finish = resolve
      })
  })
  const old = state.reload()
  state.props.record.id = 'record-b'
  await nextTick()
  finish({
    feedback: { version: 3, status: 'active', details: { tags: [], comment: '旧餐反馈' } },
    revisions: [1]
  })
  await old
  assert.equal(state.current.value, null)
  assert.deepEqual(state.revisions.value, [])
  assert.equal(state.canSave.value, false)
  state.dispose()
})

test('未知保存结果重试同一请求，成功回读真实版本', async () => {
  const requests = []
  let saved = false
  const state = panel({
    mealFeedback: async () => ({
      feedback: saved
        ? {
            version: 1,
            status: 'active',
            details: { tags: [], comment: '服务器内容', consumption: 'half' }
          }
        : null,
      revisions: []
    }),
    saveMealFeedback: async (id, data) => {
      requests.push({ id, ...JSON.parse(JSON.stringify(data)) })
      if (requests.length === 1) throw Error('unknown')
      saved = true
    }
  })
  await state.reload()
  state.form.value.comment = '这顿偏咸'
  await state.save()
  assert.ok(state.attempt.value.client_request_id)
  state.form.value.comment = '不应替换已提交原文'
  await state.save()
  assert.deepEqual(requests[0], requests[1])
  assert.equal(state.current.value.version, 1)
  assert.equal(state.form.value.comment, '服务器内容')
  assert.equal(state.attempt.value, null)
  state.dispose()
})

test('撤回未知响应使用相同版本和请求重试，结果重新读取', async () => {
  const requests = []
  let revoked = false
  const state = panel({
    mealFeedback: async () => ({
      feedback: {
        version: revoked ? 2 : 1,
        status: revoked ? 'revoked' : 'active',
        details: revoked ? null : { tags: [], comment: '单餐反馈', consumption: 'unknown' }
      },
      revisions: []
    }),
    revokeMealFeedback: async (id, data) => {
      requests.push({ id, ...data })
      if (requests.length === 1) throw Error('unknown')
      revoked = true
    }
  })
  await state.reload()
  await state.revoke()
  assert.ok(state.revokeAttempt.value)
  await state.revoke()
  assert.deepEqual(requests[0], requests[1])
  assert.equal(state.current.value.status, 'revoked')
  assert.equal(state.form.value.comment, '')
  assert.equal(state.canSave.value, false)
  state.dispose()
})

test('读取失败不允许猜测版本写入，卸载后旧响应失效', async () => {
  let finish
  const state = panel({
    mealFeedback: () =>
      new Promise((resolve) => {
        finish = resolve
      })
  })
  const loading = state.reload()
  state.form.value.comment = '草稿'
  assert.equal(state.canSave.value, false)
  state.dispose()
  finish({ feedback: { version: 9 }, revisions: [] })
  await loading
  assert.equal(state.current.value, null)
})
