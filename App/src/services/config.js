const env = import.meta.env || {}
export const serviceMode = env.VITE_SERVICE_MODE === 'api' ? 'api' : 'mock'
export const isMockMode = serviceMode === 'mock'
export const apiBaseUrl = env.VITE_API_BASE_URL || ''
// 仅显式本机联调允许回环HTTP；公网与真机仍要求HTTPS。
export const allowLocalHealthApi = env.VITE_ALLOW_LOCAL_HEALTH_API === '1'
export function requireMock() {
  if (!isMockMode) throw Object.assign(new Error('服务暂不可用，请稍后重试'), { code: 'ADAPTER_NOT_READY' })
}

export const isCommerceEnabled = env.VITE_COMMERCE_MODE === "api"
export const commerceApiBaseUrl = env.VITE_COMMERCE_API_BASE_URL || ""

let h5 = false
// #ifdef H5
h5 = true
// #endif
export const allowSameOriginApi = h5 && !isMockMode && apiBaseUrl === ''
// Existing Agent credentials can be used only in an explicitly enabled H5 development build.
export const canUsePasswordLogin = h5 && !isMockMode && env.DEV === true && env.VITE_H5_PASSWORD_LOGIN === 'true'

// 保留线上 H5 已有业务账号登录，商城仍通过同一 Agent 会话关联。
export const canUseBusinessLogin = h5 && !isMockMode
