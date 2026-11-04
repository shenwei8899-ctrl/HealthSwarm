import test from 'node:test'
import assert from 'node:assert/strict'
import { reportRecognitionError } from '../src/services/report-recognition-error.js'

test('报告额度耗尽与网络、计费配置问题分别提示，不暴露未知错误', () => {
  assert.match(reportRecognitionError('provider_quota_exhausted'), /额度已用完.*手动录入/)
  assert.match(reportRecognitionError('budget_price_unavailable'), /计费配置尚未就绪/)
  assert.doesNotMatch(reportRecognitionError('provider_unavailable'), /额度已用完/)
  assert.equal(reportRecognitionError('private-provider-message'), '本次识别未完成，请重试或手动录入。')
})
