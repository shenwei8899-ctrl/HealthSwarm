import { createNutritionClient, NutritionClientError } from './nutrition-client.js'

/** 微信目标必须配置实际 HTTPS API 地址；H5 沿用同源代理。 */
export function resolveNutritionApiBase(platform, configuredBase) {
  if (platform === 'h5') return '/api'
  if (typeof configuredBase !== 'string' || !configuredBase.trim()) {
    throw new NutritionClientError(0, 'api_not_configured', '未配置营养服务地址，请设置 VITE_HEALTH_API_BASE')
  }
  const base = configuredBase.trim().replace(/\/+$/, '')
  if (!/^https:\/\/[a-z\d](?:[a-z\d.-]*[a-z\d])?(?::\d{1,5})?(?:\/[^\s?#]*)?$/i.test(base)) {
    throw new NutritionClientError(0, 'api_requires_https', '微信营养服务地址必须是有效 HTTPS 地址')
  }
  return base
}

let platform = 'h5'
// #ifdef MP-WEIXIN
platform = 'mp-weixin'
// #endif

let apiBase = '/api'
let configurationError = null
try {
  apiBase = resolveNutritionApiBase(platform, import.meta.env?.VITE_HEALTH_API_BASE)
} catch (error) {
  configurationError = error
}

export const client = createNutritionClient({
  apiBase,
  request(options) {
    if (configurationError) {
      options.fail(configurationError)
      return
    }
    return uni.request(options)
  },
  storage: {
    getStorageSync: (key) => uni.getStorageSync(key),
    setStorageSync: (key, value) => uni.setStorageSync(key, value),
    removeStorageSync: (key) => uni.removeStorageSync(key),
  },
})
