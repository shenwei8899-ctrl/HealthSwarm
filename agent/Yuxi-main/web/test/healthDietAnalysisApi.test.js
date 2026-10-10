import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'

const source = (
  await readFile(new URL('../src/apis/health_vision_api.js', import.meta.url), 'utf8')
)
  .replace(/^import.*\n/gm, '')
  .replace('export const healthVisionApi', 'const healthVisionApi')

test('分析与选餐反馈使用认证API边界，绑定传当前确认版本且保持幂等键', async () => {
  const calls = []
  const api = new Function(
    'apiGet',
    'apiPost',
    'apiPut',
    'apiDelete',
    'apiRequest',
    'buildQuery',
    `${source}\nreturn healthVisionApi`
  )(
    () => {},
    async (...args) => calls.push(args),
    () => {},
    () => {},
    () => {},
    () => ''
  )
  await api.createDietAnalyst('member-a', { client_request_id: 'analysis-binding' })
  await api.createFeedbackConversation('meal-a', {
    client_request_id: 'feedback-binding',
    source_version: 3
  })
  await api.dietAnalysis('member-a', { record_id: 'meal-a', source_version: 3 })
  await api.dietPeriodAnalysis('member-a', { period_days: 30, end_date: '2026-10-09' })
  assert.deepEqual(calls, [
    [
      '/api/health/v1/members/member-a/diet-analyst',
      { client_request_id: 'analysis-binding' },
      { headers: { 'Idempotency-Key': 'analysis-binding' } }
    ],
    [
      '/api/health/v1/diet-logs/meal-a/feedback-conversation',
      { client_request_id: 'feedback-binding', source_version: 3 },
      { headers: { 'Idempotency-Key': 'feedback-binding' } }
    ],
    ['/api/health/v1/members/member-a/diet-analysis', { record_id: 'meal-a', source_version: 3 }],
    [
      '/api/health/v1/members/member-a/diet-period-analysis',
      { period_days: 30, end_date: '2026-10-09' }
    ]
  ])
})
