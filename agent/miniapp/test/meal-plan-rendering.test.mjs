import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createSSRApp } from 'vue'
import { parse, compileScript } from 'vue/compiler-sfc'
import { renderToString } from 'vue/server-renderer'

// 执行真实组件模板，独立检查用户看见的计划数据与缺失值文案。
async function component(name) {
  const source = await readFile(new URL(`../src/components/${name}.vue`, import.meta.url), 'utf8')
  const { descriptor } = parse(source, { templateParseOptions: { isCustomElement: tag => ['view', 'text', 'input', 'picker'].includes(tag) } })
  const compiled = compileScript(descriptor, { id: name, inlineTemplate: true, genDefaultAs: '__component',
    templateOptions: { compilerOptions: { isCustomElement: tag => ['view', 'text', 'input', 'picker'].includes(tag) } } })
  const module = compiled.content.replace(/from ["']vue["']/g, `from ${JSON.stringify(import.meta.resolve('vue'))}`)
  return (await import(`data:text/javascript;base64,${Buffer.from(module + '\nexport default __component').toString('base64')}`)).default
}
const Snapshot = await component('MealPlanSnapshot')
const DishEditor = await component('MealDishEditor')
const nutrients = { energy_kcal: '700.00', protein_g: '25.00', fat_g: '0.00', carbohydrate_g: '99.00', sodium_mg: null }

test('实际餐单模板显示具体菜名原料和服务端数值，零与缺失分别显示', async () => {
  const snapshot = { plan_date: '2026-10-10', meals: [{ meal_type: 'breakfast', dishes: [{ dish_index: 0,
    name: '燕麦豆浆', planned_grams: '50.00', ingredients: [{ name: '燕麦', planned_grams: '12.50' }],
    nutrition: nutrients }], nutrition: { totals: nutrients } }], nutrition: { totals: nutrients, complete: false } }
  const html = await renderToString(createSSRApp(Snapshot, { snapshot }))
  for (const text of ['燕麦豆浆', '燕麦', '50.00 g', '12.50 g', '700.00 kcal', '0.00 g', '未确定', '未确定项没有按零计算', '不代表实际摄入']) {
    assert.ok(html.includes(text), `应显示 ${text}`)
  }
  assert.ok(!html.includes('null mg') && !html.includes('0 mg'))
})

test('实际模板不把未知计划份量显示成零或自行补量', async () => {
  const unknown = Object.fromEntries(Object.keys(nutrients).map(key => [key, null]))
  const snapshot = { plan_date: '2026-10-10', meals: [{ meal_type: 'dinner', dishes: [{ dish_index: 0,
    name: '蔬菜晚餐', planned_grams: null, ingredients: [{ name: '南瓜', planned_grams: null }],
    nutrition: unknown }], nutrition: { totals: unknown } }], nutrition: { totals: unknown, complete: false } }
  const html = await renderToString(createSSRApp(Snapshot, { snapshot }))
  assert.ok(html.includes('计划份量尚未确定') && html.includes('未确定'))
  assert.ok(!html.includes('0 g') && !html.includes('100 g') && !html.includes('已正式采用'))
})

test('实际模板把服务端科学记数展开为可读文本并保留小数精度', async () => {
  const source = { ...nutrients, energy_kcal: '7E+2', fat_g: '0E+3' }
  const snapshot = { plan_date: '2026-10-10', meals: [{ meal_type: 'breakfast', dishes: [{ dish_index: 0,
    name: '燕麦早餐', planned_grams: '5E+1', ingredients: [{ name: '燕麦', planned_grams: '1.25E+1' },
      { name: '调味料', planned_grams: '2.500E-1' }], nutrition: source }], nutrition: { totals: source } }],
    nutrition: { totals: source, complete: false } }
  const html = await renderToString(createSSRApp(Snapshot, { snapshot }))
  for (const text of ['50 g', '12.5 g', '0.2500 g', '700 kcal', '0 g', '未确定']) assert.ok(html.includes(text), text)
  assert.ok(!html.includes('E+') && !html.includes('E-'))
})

test('实际菜谱编辑模板不默认克数，明确显示选中版本离开搜索结果', async () => {
  const dish = { recipe_version_id: '', portion_mode: 'unknown', grams: '', portion_reference_id: '', portion_count: '' }
  const empty = await renderToString(createSSRApp(DishEditor, { dish, recipes: [], portions: [] }))
  assert.ok(empty.includes('请选择已发布菜谱') && empty.includes('未知'))
  const filtered = await renderToString(createSSRApp(DishEditor, { dish: { ...dish, recipe_version_id: 'selected-version' }, recipes: [], portions: [] }))
  assert.ok(filtered.includes('已选版本不在当前搜索结果'))
})
