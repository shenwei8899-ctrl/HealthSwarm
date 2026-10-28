import { canUseLocalBusinessLogin, canUseH5TestBusinessLogin } from './local-login-policy.js'
const env = import.meta.env || {}
export const serviceMode = env.VITE_SERVICE_MODE === 'api' ? 'api' : 'mock'
export const isMockMode = serviceMode === 'mock'
export const apiBaseUrl = env.VITE_API_BASE_URL || ''
// 仅显式本机联调允许回环HTTP；公网与真机仍要求HTTPS。
export const allowLocalHealthApi = env.VITE_ALLOW_LOCAL_HEALTH_API === '1'
export function requireMock() {
  if (!isMockMode) throw Object.assign(new Error('服务暂不可用，请稍后重试'), { code: 'ADAPTER_NOT_READY' })
}

export const isCommerceEnabled = !isMockMode && env.VITE_COMMERCE_MODE === "api"
export const commerceApiBaseUrl = env.VITE_COMMERCE_API_BASE_URL || ""
export const phoneBindingDemo = isCommerceEnabled && env.VITE_PHONE_BINDING_DEMO === '1'
export const wechatAppId = env.VITE_WECHAT_APPID || ''

let h5 = false
// #ifdef H5
h5 = true
// #endif
export const allowSameOriginApi = h5 && !isMockMode && apiBaseUrl === ''
// 正式客户端不开放业务密码登录。
export const canUsePasswordLogin = false

let platform = '', hostname = '', origin = ''
// #ifdef MP-WEIXIN
if (typeof uni !== 'undefined' && uni.getDeviceInfo) platform = uni.getDeviceInfo().platform
// #endif
// #ifdef H5
if (typeof location !== 'undefined') { hostname = location.hostname; origin = location.origin }
// #endif
export const canUseH5TestLogin = canUseH5TestBusinessLogin(env, { h5, origin })
export const canUseBusinessLogin = canUseLocalBusinessLogin(env, { platform, hostname }) || canUseH5TestLogin
