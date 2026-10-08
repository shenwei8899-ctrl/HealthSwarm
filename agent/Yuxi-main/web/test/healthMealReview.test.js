import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { ref, watch, effectScope, nextTick, reactive } from 'vue'
import { setImmediate } from 'node:timers'
import { newMealItem } from '../src/utils/healthVision.js'

const source = await readFile(
  new URL('../src/components/health/MealReview.vue', import.meta.url),
  'utf8'
)
const script = source
  .match(/<script setup>([\s\S]*?)<\/script>/)[1]
  .replace(/^import[\s\S]*?from ['"][^'"]+['"]\s*\n/gm, '')

/** 执行真实组件 Vue 状态与事件，不复制另一套表单逻辑。 */
function editor(item, api = {}) {
  const scope = effectScope()
  const props = reactive({ payload: { items: [item] }, readonly: false })
  const events = []
  const revoked = []
  const created = []
  let unmount
  const factory = new Function(
    'ref',
    'watch',
    'onMounted',
    'onBeforeUnmount',
    'defineProps',
    'defineEmits',
    'healthVisionApi',
    'message',
    'URL',
    `${script}\nreturn { references, changeKind, selectMapping, selectPortion, addAdjustment, removeAdjustment, mappingKind, showLocation, closePreview, preview, previewOpen, previewError, previewLoading, selectedLocation }`
  )
  const state = scope.run(() =>
    factory(
      ref,
      watch,
      () => {},
      (callback) => {
        unmount = callback
      },
      () => props,
      () => (name) => events.push(name),
      { portions: async () => [], ...api },
      { error: () => {} },
      {
        createObjectURL: (blob) => {
          created.push(blob)
          return `blob:${blob}`
        },
        revokeObjectURL: (url) => revoked.push(url)
      }
    )
  )
  return {
    ...state,
    props,
    events,
    revoked,
    created,
    dispose: () => {
      unmount()
      scope.stop()
    }
  }
}

test('照片标记按服务器绑定序号加载；较早响应不能覆盖后选照片', async () => {
  let resolveFirst
  const requests = []
  const state = editor(newMealItem(), {
    preview: (id, page) => {
      requests.push([id, page])
      return id === 'first'
        ? new Promise((resolve) => {
            resolveFirst = resolve
          })
        : Promise.resolve('second')
    }
  })
  state.props.payload.photos = [
    { image_index: 0, upload_id: 'first', upload_page_index: 0 },
    { image_index: 1, upload_id: 'second', upload_page_index: 0 }
  ]
  const first = state.showLocation({ image_index: 0, bbox: [0.1, 0.2, 0.8, 0.9] })
  await state.showLocation({ image_index: 1, bbox: [0.2, 0.1, 0.7, 0.8] })
  resolveFirst('first')
  await first
  assert.deepEqual(requests, [
    ['first', 0],
    ['second', 0]
  ])
  assert.equal(state.preview.value, 'blob:second')
  assert.equal(state.selectedLocation.value.image_index, 1)
  assert.deepEqual(state.created, ['second'])
  assert.deepEqual(state.events, [])
  state.dispose()
  assert.deepEqual(state.revoked, ['blob:second'])
})

test('关闭或卸载作废迟到私有图片；预览失败清空旧图片并允许重试', async () => {
  for (const close of ['closePreview', 'dispose']) {
    let resolveImage
    const state = editor(newMealItem(), {
      preview: () =>
        new Promise((resolve) => {
          resolveImage = resolve
        })
    })
    state.props.payload.photos = [{ image_index: 0, upload_id: 'first', upload_page_index: 0 }]
    const pending = state.showLocation({ image_index: 0, bbox: [0, 0, 1, 1] })
    state[close]()
    resolveImage('late')
    await pending
    assert.equal(state.previewOpen.value, false)
    assert.equal(state.preview.value, '')
    assert.deepEqual(state.created, [])
    if (close !== 'dispose') state.dispose()
  }
  let fail = false
  const state = editor(newMealItem(), {
    preview: async () => {
      if (fail) throw new Error('源文件不可用')
      return 'first'
    }
  })
  state.props.payload.photos = [{ image_index: 0, upload_id: 'first', upload_page_index: 0 }]
  const location = { image_index: 0, bbox: [0, 0, 1, 1] }
  await state.showLocation(location)
  fail = true
  await state.showLocation(location)
  assert.equal(state.preview.value, '')
  assert.equal(state.previewError.value, '源文件不可用')
  assert.equal(state.previewLoading.value, false)
  assert.deepEqual(state.revoked, ['blob:first'])
  fail = false
  await state.showLocation(location)
  assert.equal(state.preview.value, 'blob:first')
  assert.equal(state.previewError.value, '')
  state.dispose()
})

test('切换食谱与食品必须清掉旧规格和油糖替换，并触发预览失效', () => {
  const item = newMealItem()
  Object.assign(item, {
    food_id: 'food-old',
    portion_reference_id: 'portion-old',
    portion_count: 2,
    adjustments: [{ role: 'oil', mode: 'replace' }]
  })
  const state = editor(item)
  state.changeKind(item, 'recipe')
  assert.equal(state.mappingKind(item), 'recipe')
  assert.equal(item.food_id, null)
  assert.equal(item.recipe_version_id, null)
  assert.equal(item.portion_reference_id, null)
  assert.equal(item.portion_count, null)
  assert.deepEqual(item.adjustments, [])
  assert.deepEqual(state.events, ['changed'])
  state.dispose()
})

test('选碗勺参考不默认数量且不能冒充实际称重，清空规格仍不补默认量', () => {
  const item = newMealItem()
  Object.assign(item, {
    food_id: 'food',
    grams: 300,
    portion_source: 'weighed',
    portion_reference_id: 'portion',
    portion_count: 1
  })
  const state = editor(item)
  state.selectPortion(item)
  assert.equal(item.grams, null)
  assert.equal(item.portion_count, null)
  assert.equal(item.portion_source, 'estimated')
  item.portion_reference_id = undefined
  state.selectPortion(item)
  assert.equal(item.portion_reference_id, null)
  assert.equal(item.grams, null)
  assert.equal(state.events.length, 2)
  state.dispose()
})

test('份量请求晚到只写对应版本缓存，不能串用到新映射', async () => {
  let resolveOld
  const item = newMealItem()
  item.food_id = 'old'
  const state = editor(item, {
    portions: (mapping) =>
      mapping.food_id === 'old'
        ? new Promise((resolve) => {
            resolveOld = resolve
          })
        : Promise.resolve([{ id: 'new-portion' }])
  })
  state.props.payload.items[0].food_id = 'new'
  await nextTick()
  await new Promise(setImmediate)
  resolveOld([{ id: 'old-portion' }])
  await new Promise(setImmediate)
  assert.equal(state.references.value.new[0].id, 'new-portion')
  assert.equal(state.references.value.old[0].id, 'old-portion')
  assert.equal(item.portion_reference_id, null)
  state.dispose()
})

test('追加与移除油糖均撤销旧预览，新增调整不默认重量或食品', () => {
  const item = newMealItem()
  const state = editor(item)
  state.addAdjustment(item, 'oil')
  assert.deepEqual(item.adjustments, [{ role: 'oil', mode: 'append', food_id: null, grams: null }])
  state.removeAdjustment(item, 0)
  assert.deepEqual(item.adjustments, [])
  assert.deepEqual(state.events, ['changed', 'changed'])
  state.dispose()
})

test('食谱发布入口远程查询的旧响应不能覆盖新查询', async () => {
  const adminSource = await readFile(
    new URL('../src/components/health/RecipePortionAdmin.vue', import.meta.url),
    'utf8'
  )
  const adminScript = adminSource
    .match(/<script setup>([\s\S]*?)<\/script>/)[1]
    .replace(/^import[\s\S]*?from ['"][^'"]+['"]\s*\n/gm, '')
  let resolveOld
  const scope = effectScope()
  const factory = new Function(
    'ref',
    'reactive',
    'watch',
    'onMounted',
    'defineProps',
    'defineEmits',
    'healthVisionApi',
    'message',
    `${adminScript}\nreturn { foods, recipes, loadVersions }`
  )
  const state = scope.run(() =>
    factory(
      ref,
      reactive,
      watch,
      () => {},
      () => ({ foodCount: 0 }),
      () => () => {},
      {
        foods: (query) =>
          query === 'old'
            ? new Promise((resolve) => {
                resolveOld = resolve
              })
            : Promise.resolve([{ id: 'new-food' }]),
        recipes: async (query) => [{ id: `${query}-recipe` }]
      },
      { error: () => {} }
    )
  )
  const pending = state.loadVersions('old')
  await state.loadVersions('new')
  resolveOld([{ id: 'old-food' }])
  await pending
  assert.equal(state.foods.value[0].id, 'new-food')
  assert.equal(state.recipes.value[0].id, 'new-recipe')
  scope.stop()
})
