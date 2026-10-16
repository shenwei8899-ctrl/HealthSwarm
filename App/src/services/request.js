import { apiBaseUrl } from './config.js'
import { getSession, clearSession, sessionRevision } from './session.js'
import { storageContext } from './storage.js'
// Paths and response mapping belong to the agreed backend adapters. Never retry writes automatically.
export function request({ path, method = 'GET', data, headers = {}, timeout = 15000, authenticated = true }) {
  let sameOrigin = false
  // #ifdef H5
  sameOrigin = typeof window !== 'undefined' && apiBaseUrl === ''
  // #endif
  if ((!sameOrigin && !/^https:\/\//.test(apiBaseUrl)) || !path?.startsWith('/') || path.startsWith('//')) {
    return Promise.reject(Object.assign(new Error('服务暂不可用，请稍后重试'), { code: 'API_NOT_CONFIGURED' }))
  }
  const session = getSession(), scope = storageContext(), revision = sessionRevision()
  const header = Object.fromEntries(Object.entries(headers).filter(([name]) => name.toLowerCase() !== 'authorization'))
  if (authenticated && session?.token) header.Authorization = 'Bearer ' + session.token
  return new Promise((resolve, reject) => {
    uni.request({ url: apiBaseUrl.replace(/\/$/, '') + path, method, data, timeout,
      header,
      success(response) {
        if (scope !== storageContext() || revision !== sessionRevision()) return reject(Object.assign(new Error('账号已切换，请重新操作'), { code: 'SESSION_CHANGED' }))
        const traceId = response.data?.trace_id || response.header?.['x-request-id'] || response.header?.['X-Request-Id']
        if (authenticated && response.statusCode === 401) clearSession()
        if (response.statusCode < 200 || response.statusCode >= 300) {
          const detail = response.data?.detail
          const message = response.data?.message || (typeof detail === 'string' ? detail : detail?.message) || (response.statusCode === 401 ? '登录已过期，请重新登录' : '请求未完成，请重试')
          reject(Object.assign(new Error(message), { code: response.statusCode, businessCode: response.data?.code || detail?.code, traceId, retryable: response.data?.retryable === true }))
        } else resolve({ data: response.data, traceId })
      },
      fail(error) {
        if (scope !== storageContext() || revision !== sessionRevision()) return reject(Object.assign(new Error('账号已切换，请重新操作'), { code: 'SESSION_CHANGED' }))
        reject(Object.assign(new Error(/timeout/i.test(error.errMsg || '') ? '请求超时，请重试' : '网络暂不可用，请重试'), { code: 'NETWORK_ERROR' }))
      },
    })
  })
}
