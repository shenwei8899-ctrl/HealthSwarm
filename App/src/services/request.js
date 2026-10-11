import { apiBaseUrl } from './config.js'
import { getSession, clearSession } from './session.js'
import { storageContext as storageScope } from './storage.js'
// Paths and response mapping belong to the agreed backend adapters. Never retry writes automatically.
export function request({ path, method = 'GET', data, timeout = 15000, authenticated = true }) {
  if (!/^https:\/\//.test(apiBaseUrl) || !path?.startsWith('/') || path.startsWith('//')) {
    return Promise.reject(Object.assign(new Error('服务暂不可用，请稍后重试'), { code: 'API_NOT_CONFIGURED' }))
  }
  const session = getSession(), scope = storageScope()
  return new Promise((resolve, reject) => {
    uni.request({ url: apiBaseUrl.replace(/\/$/, '') + path, method, data, timeout,
      header: authenticated && session?.token ? { Authorization: 'Bearer ' + session.token } : {},
      success(response) {
        if (scope !== storageScope()) return reject(Object.assign(new Error('账号已切换，请重新操作'), { code: 'SESSION_CHANGED' }))
        const traceId = response.header?.['x-request-id'] || response.header?.['X-Request-Id']
        if (authenticated && response.statusCode === 401) clearSession()
        if (response.statusCode < 200 || response.statusCode >= 300) {
          const detail = response.data?.detail
          const message = typeof detail === 'string' ? detail : typeof detail?.message === 'string' ? detail.message : response.statusCode === 401 ? '登录已过期，请重新登录' : '请求未完成，请重试'
          reject(Object.assign(new Error(message), { code: response.statusCode, businessCode: detail?.code, traceId }))
        } else resolve({ data: response.data, traceId })
      },
      fail(error) { reject(Object.assign(new Error(/timeout/i.test(error.errMsg || '') ? '请求超时，请重试' : '网络暂不可用，请重试'), { code: 'NETWORK_ERROR' })) },
    })
  })
}
