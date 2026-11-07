import test from 'node:test'
import assert from 'node:assert/strict'
import { parseMultiDayMealIntent } from '../src/utils/chat-meal-intent.js'

const today = '2026-11-07'

test('一周三餐明确进入连续七天，明天开始时日期顺延', () => {
  assert.deepEqual(parseMultiDayMealIntent('安排一个星期的三餐', today), { dayCount: 7, startDate: today, requiresProfileReview: false })
  assert.deepEqual(parseMultiDayMealIntent('规划明天起七天三餐', today), { dayCount: 7, startDate: '2026-11-08', requiresProfileReview: false })
  assert.deepEqual(parseMultiDayMealIntent('制定三天的完整餐单', today), { dayCount: 3, startDate: today, requiresProfileReview: false })
})

test('新忌口和指定单人成员先核对档案，不传给默认家庭生成', () => {
  for (const text of ['安排一周三餐，少盐', '安排一周三餐，不加花生', '给我安排一个星期的三餐', '只给我安排七天三餐', '给爸爸安排一周三餐', '我想要一周的完整三餐计划', '安排一周完整三餐']) {
    assert.equal(parseMultiDayMealIntent(text, today)?.requiresProfileReview, true, text)
  }
})

test('科普、取消、单日及不能确定起始日的请求不启动多日生成', () => {
  for (const text of [
    '介绍一周三餐的原则', '不要安排一周三餐', '明天吃什么',
    '给我安排下周一日三餐', '给我安排昨天开始七天三餐',
    '安排八天三餐',
  ]) assert.equal(parseMultiDayMealIntent(text, today), null, text)
})
