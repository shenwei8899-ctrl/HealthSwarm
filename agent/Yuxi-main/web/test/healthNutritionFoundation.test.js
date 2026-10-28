import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import * as Vue from 'vue'
import { parse, compileTemplate } from 'vue/compiler-sfc'

const components = {}
for (const name of ['HealthRulesAdmin', 'NutritionSourcePicker', 'HealthNutritionReadiness']) {
  const source = await readFile(
    new URL(`../src/components/health/${name}.vue`, import.meta.url),
    'utf8'
  )
  const { descriptor } = parse(source)
  components[name] = descriptor.scriptSetup.content.replace(/^import[^\n]+\n/gm, '')
  assert.deepEqual(
    compileTemplate({ source: descriptor.template.content, filename: name, id: name }).errors,
    []
  )
}
const deferred = () => {
  let resolve, reject
  const promise = new Promise((done, fail) => {
    resolve = done
    reject = fail
  })
  return { promise, resolve, reject }
}

/** 执行实际组件脚本和 watcher，保留网络结果的先后顺序。 */
function panel(name, api = {}, options = {}) {
  const props = Vue.reactive(options.props || {})
  const events = []
  const cleanup = []
  const scope = Vue.effectScope()
  const names = {
    HealthRulesAdmin:
      'code,current,payload,metadata,confirmed,pending,busy,error,success,read,publish,revoke,revokeOpen,revokeTarget,selectRevokeTarget',
    NutritionSourcePicker:
      'kb,query,files,offset,hasMore,loading,error,selected,search,choose,loadDatabases',
    HealthNutritionReadiness: 'result,busy,error,check'
  }
  const bindings = {
    ...Vue,
    onBeforeUnmount: (fn) => cleanup.push(fn),
    defineProps: () => props,
    defineEmits:
      () =>
      (...args) =>
        events.push(args),
    api,
    healthVisionApi: api,
    databaseApi: options.databaseApi,
    documentApi: options.documentApi
  }
  const state = scope.run(() =>
    new Function(...Object.keys(bindings), `${components[name]}\nreturn {${names[name]}}`)(
      ...Object.values(bindings)
    )
  )
  return {
    ...state,
    props,
    events,
    dispose() {
      cleanup.forEach((fn) => fn())
      scope.stop()
    }
  }
}

test('知识库搜索分页按接口回读，禁用后迟到选择不能回填', async () => {
  const chosen = deferred()
  const calls = []
  const state = panel(
    'NutritionSourcePicker',
    { nutritionSource: () => chosen.promise },
    {
      props: { disabled: false },
      documentApi: {
        searchDocuments: async (kb, params) => {
          calls.push([kb, params])
          return {
            files: [{ file_id: 'file-a', filename: '原件' }, { is_folder: true }],
            has_more: true
          }
        }
      }
    }
  )
  state.kb.value = 'kb-a'
  state.query.value = '原件'
  await Vue.nextTick()
  await state.search(20)
  assert.deepEqual(calls, [['kb-a', { query: '原件', offset: 20, limit: 20 }]])
  assert.equal(state.files.value.length, 1)
  assert.equal(state.offset.value, 20)
  const running = state.choose(state.files.value[0])
  state.props.disabled = true
  await Vue.nextTick()
  chosen.resolve({ source_ref: 'knowledge://stale', filename: '迟到原件' })
  await running
  assert.deepEqual(state.events, [])
  assert.equal(state.loading.value, false)
  state.dispose()
})

test('切换成员或规则后，迟到准备结果和错误不回填', async () => {
  for (const field of ['memberId', 'ruleCode', 'disabled']) {
    const request = deferred()
    const state = panel(
      'HealthNutritionReadiness',
      { nutritionReadiness: () => request.promise },
      {
        props: { memberId: 'member-a', ruleCode: 'rules-a', disabled: false }
      }
    )
    const running = state.check()
    state.props[field] = field === 'disabled' ? true : 'changed'
    await Vue.nextTick()
    request.resolve({ personal_targets: { status: 'ready' } })
    await running
    assert.equal(state.result.value, null)
    assert.equal(state.busy.value, false)
    state.dispose()
  }
})

async function rulesPanel(api = {}) {
  const state = panel('HealthRulesAdmin', api)
  state.code.value = 'synthetic-rules'
  await Vue.nextTick()
  state.current.value = { version: 1, next_version: 2 }
  state.payload.value = '{"synthetic":true}'
  state.metadata.source_ref = 'synthetic:approved-source'
  await Vue.nextTick()
  state.confirmed.value = true
  return state
}

test('规则请求结果未知时保留原整包，重试不得换版本或内容', async () => {
  const calls = []
  let tries = 0
  const state = await rulesPanel({
    importQualityRules: async (value) => {
      calls.push(structuredClone(Vue.toRaw(value)))
      if (tries++ === 0) throw new Error('network')
      return { version: 2 }
    },
    approvedQualityRules: async () => ({ version: 2, next_version: 3 })
  })
  await state.publish()
  assert.equal(state.pending.value.version, 2)
  state.payload.value = '{"synthetic":"changed"}'
  state.metadata.source_ref = 'synthetic:changed'
  await state.publish()
  assert.deepEqual(calls[0], calls[1])
  assert.equal(state.pending.value, null)
  assert.equal(state.current.value.version, 2)
  assert.equal(state.confirmed.value, false)
  state.dispose()
})

test('缺少导入回执或回读版本时不能宣称登记成功', async () => {
  for (const receipt of [{}, { version: 1 }]) {
    const state = await rulesPanel({ importQualityRules: async () => receipt })
    await state.publish()
    assert.equal(state.pending.value.version, 2)
    assert.equal(state.success.value, '')
    state.dispose()
  }
  const state = await rulesPanel({
    importQualityRules: async () => ({ version: 2 }),
    approvedQualityRules: async () => ({ version: 1, next_version: 2 })
  })
  await state.publish()
  assert.equal(state.pending.value.version, 2)
  assert.equal(state.success.value, '')
  state.dispose()
})

test('明确规则冲突允许修订，卸载后的写响应不能继续回读', async () => {
  const rejected = await rulesPanel({
    importQualityRules: async () => {
      throw { status: 409 }
    }
  })
  await rejected.publish()
  assert.equal(rejected.pending.value, null)
  assert.equal(rejected.current.value, null)
  assert.match(rejected.error.value, /重新读取/)
  rejected.dispose()
  const request = deferred()
  let reads = 0
  const state = await rulesPanel({
    importQualityRules: () => request.promise,
    approvedQualityRules: async () => {
      reads++
      return { version: 2 }
    }
  })
  const running = state.publish()
  state.dispose()
  request.resolve({ version: 2 })
  await running
  assert.equal(reads, 0)
  assert.equal(state.success.value, '')
})

test('撤回绑定确认时的规则及版本，切换代码撤销旧确认', async () => {
  const calls = []
  const state = await rulesPanel({
    revokeQualityRules: async (...args) => calls.push(args),
    approvedQualityRules: async () => ({ version: 1, next_version: 2, reason: 'revoked' })
  })
  state.selectRevokeTarget(true)
  state.code.value = 'other-rules'
  await Vue.nextTick()
  state.current.value = { version: 4, next_version: 5 }
  await state.revoke()
  assert.deepEqual(calls, [])
  state.selectRevokeTarget(true)
  await state.revoke()
  assert.deepEqual(calls, [['other-rules', 4]])
  state.dispose()
})

test('规则内容或批准依据修改后须重新确认', async () => {
  const calls = []
  const state = await rulesPanel({ importQualityRules: async (value) => calls.push(value) })
  state.metadata.authority_ref = 'synthetic:new-approval'
  await Vue.nextTick()
  assert.equal(state.confirmed.value, false)
  await state.publish()
  assert.deepEqual(calls, [])
  state.dispose()
})
