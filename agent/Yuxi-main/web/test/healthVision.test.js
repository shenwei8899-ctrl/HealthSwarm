import { test } from 'node:test'
import assert from 'node:assert/strict'
import { newReportField, newMealItem, nutrientText, localDateTime } from '../src/utils/healthVision.js'

test('人工记录不伪造模型来源或默认份量', () => {
  const report = newReportField()
  assert.equal(report.source, 'manual')
  assert.equal(report.evidence, null)
  assert.equal(report.value_numeric, null)
  assert.notEqual(report.field_id, newReportField().field_id)
  const meal = newMealItem()
  assert.equal(meal.grams, null)
  assert.equal(meal.share_ratio, null)
  assert.equal(meal.food_id, null)
  assert.equal(meal.portion_source, 'unknown')
})

test('未知营养不是零，零可明确显示', () => {
  assert.equal(nutrientText(null, 'g'), '未知')
  assert.equal(nutrientText(undefined, 'g'), '未知')
  assert.equal(nutrientText('0.00', 'g'), '0.00 g')
})

test('人工就餐时间适用于本地 datetime 输入', () => {
  assert.match(localDateTime(), /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
})
