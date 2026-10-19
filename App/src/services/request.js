import { apiBaseUrl, allowLocalHealthApi } from './config.js'
import { getSession, clearSession, sessionRevision } from './session.js'
import { storageContext } from './storage.js'
// Paths and response mapping belong to the agreed backend adapters. Never retry writes automatically.
export function request({ path, method = 'GET', data, headers = {}, timeout = 15000, authenticated = true, authenticationToken }) {
  let sameOrigin = false
  // #ifdef H5
  sameOrigin = typeof window !== 'undefined' && apiBaseUrl === ''
  // #endif
  const localApi = allowLocalHealthApi && /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(apiBaseUrl)
  if ((!sameOrigin && !localApi && !/^https:\/\//.test(apiBaseUrl)) || !path?.startsWith('/') || path.startsWith('//')) {
    return Promise.reject(Object.assign(new Error('服务暂不可用，请稍后重试'), { code: 'API_NOT_CONFIGURED' }))
  }
  const session = getSession(), scope = storageContext(), revision = sessionRevision()
  const header = Object.fromEntries(Object.entries(headers).filter(([name]) => name.toLowerCase() !== 'authorization'))
  if (authenticated && session?.token) header.Authorization = 'Bearer ' + session.token
  if (!authenticated && authenticationToken) header.Authorization = 'Bearer ' + authenticationToken
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

/** 仅向健康文件入口上传；鉴权与迟到响应规则和普通请求一致。 */
export function uploadHealthFile({ filePath, memberId, purpose, size, onProgress = () => {}, onCancelReady = () => {} }) {
  if (!filePath || !memberId || !['report', 'meal'].includes(purpose)) return Promise.reject(new Error('请先选择成员与文件'))
  if (Number(size) > 20 * 1024 * 1024) return Promise.reject(new Error('文件不能超过20MB'))
  const sameOrigin = typeof window !== 'undefined' && apiBaseUrl === ''
  const localApi = allowLocalHealthApi && /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(apiBaseUrl)
  if (!sameOrigin && !localApi && !/^https:\/\//.test(apiBaseUrl)) return Promise.reject(Object.assign(new Error('上传服务尚未配置'), { code: 'API_NOT_CONFIGURED' }))
  const scope = storageContext(), revision = sessionRevision(), session = getSession()
  if (!session?.token) return Promise.reject(Object.assign(new Error('请先登录'), { code: 401 }))
  return new Promise((resolve, reject) => {
    let cancelled = false
    const current = () => scope === storageContext() && revision === sessionRevision()
    const task = uni.uploadFile({ url: apiBaseUrl.replace(/\/$/, '') + '/api/health/v1/uploads', filePath, name: 'file',
      formData: { member_id: memberId, purpose }, header: { Authorization: 'Bearer ' + session.token }, timeout: 60000,
      success(response) {
        if (cancelled) return
        if (!current()) return reject(Object.assign(new Error('账号已切换'), { code: 'SESSION_CHANGED' }))
        let data
        try { data = typeof response.data === 'string' ? JSON.parse(response.data) : response.data }
        catch { return reject(Object.assign(new Error('上传响应无法读取，请重新读取任务状态'), { code: 'UPLOAD_RESPONSE_INVALID' })) }
        if (response.statusCode === 401) clearSession()
        if (response.statusCode < 200 || response.statusCode >= 300) return reject(Object.assign(new Error(data?.message || data?.detail || '上传失败'), { code: response.statusCode, businessCode: data?.code, traceId: data?.trace_id }))
        if (!data?.upload_id || data.purpose !== purpose || data.status !== 'ready') return reject(new Error('上传回执与当前用途不一致'))
        resolve(data)
      },
      fail() { if (!cancelled) reject(Object.assign(new Error(current() ? '上传结果未确认，请重试上传；尚未创建识别任务' : '账号已切换'), { code: current() ? 'NETWORK_ERROR' : 'SESSION_CHANGED' })) },
    })
    onCancelReady(() => {
      cancelled = true; task?.abort?.()
      reject(Object.assign(new Error('已取消上传，尚未创建识别任务。'), { code: 'UPLOAD_CANCELLED' }))
    })
    task?.onProgressUpdate?.(event => { if (!cancelled && current()) onProgress(event.progress) })
  })
}
