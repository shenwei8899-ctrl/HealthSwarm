import assert from 'node:assert/strict'
import test from 'node:test'
import { buildMetricSeries, profileChanges, profileStatus } from '../../src/utils/familyArchives.js'

test('未授权字段不进入档案提交，空值保留为未知', () => {
  assert.deepEqual(profileChanges({ height_cm: null, medical_history: 'private' }, ['height_cm']), {
    height_cm: null
  })
})
test('个人指标按上海日期分组，缺失保留 null，保留每日最近实测', () => {
  const records = [
    { measured_at: '2026-10-01T23:50:00Z', values: { weight: 60 } },
    { measured_at: '2026-10-02T01:00:00Z', values: { weight: 61 } }
  ]
  const series = buildMetricSeries(records, 'weight', ['2026-10-01', '2026-10-02', '2026-10-03'])
  assert.deepEqual(series, [null, 61, null])
})
test('待授权、待补充、待确认和就绪是不同状态', () => {
  assert.equal(profileStatus({ allowed_fields: [], claimed: false }), '待本人认领')
  assert.equal(profileStatus({ allowed_fields: [], claimed: true }), '待授权')
  assert.equal(
    profileStatus({ claimed: true, allowed_fields: ['height_cm'], missing_fields: ['height_cm'] }),
    '待补充'
  )
  assert.equal(
    profileStatus({
      claimed: true,
      allowed_fields: ['height_cm'],
      missing_fields: [],
      confirmed: false
    }),
    '待本人确认'
  )
  assert.equal(
    profileStatus({
      claimed: true,
      allowed_fields: ['height_cm'],
      missing_fields: [],
      ready: true
    }),
    '档案就绪'
  )
})
