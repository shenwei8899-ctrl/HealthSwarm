const env = import.meta.env || {}
export const serviceMode = env.VITE_SERVICE_MODE === 'api' ? 'api' : 'mock'
export const isMockMode = serviceMode === 'mock'
export const apiBaseUrl = env.VITE_API_BASE_URL || ''
export function requireMock() {
  if (!isMockMode) throw Object.assign(new Error('服务暂不可用，请稍后重试'), { code: 'ADAPTER_NOT_READY' })
}

export const isCommerceEnabled = env.VITE_COMMERCE_MODE === "api"
export const commerceApiBaseUrl = env.VITE_COMMERCE_API_BASE_URL || ""
