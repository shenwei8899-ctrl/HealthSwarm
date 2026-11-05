/** 仅展示稳定业务错误，未知错误不透出供应商原文。 */
export function reportRecognitionError(code) {
  return ({
    provider_quota_exhausted: '报告识别额度已用完，请额度恢复后再试，或手动录入指标。',
    budget_price_unavailable: '报告识别计费配置尚未就绪，请联系管理员，或手动录入指标。',
    budget_exceeded: '报告识别预算不足或待核账，请联系管理员，或手动录入指标。',
    provider_not_configured: '报告识别服务尚未配置，请联系管理员。',
    provider_unavailable: '报告识别服务暂不可用，请稍后重试或手动录入。',
    parser_contract_invalid: '报告表格未能整理为可核对结果，请对照原图手动录入。',
    provider_timeout: '报告识别超时，请稍后重试或手动录入。',
  })[code] || '本次识别未完成，请重试或手动录入。'
}
