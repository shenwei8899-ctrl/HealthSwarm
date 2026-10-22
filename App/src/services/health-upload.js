import { apiBaseUrl, allowLocalHealthApi } from './config.js'
import { getSession, clearSession, sessionRevision } from './session.js'
import { storageContext } from './storage.js'

/** 上传与原图读取沿用业务请求的 HTTPS、H5同源及显式回环联调边界。 */
export function healthImageApiReady(baseUrl = apiBaseUrl, local = allowLocalHealthApi) {
  return (typeof window !== 'undefined' && baseUrl === '') || /^https:\/\//.test(baseUrl) ||
    (local && /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(baseUrl))
}

/** 私有照片沿用业务登录；设备路径只交给上传接口。 */
export function uploadMealPhoto(memberId, filePath) {
  if (!healthImageApiReady() || !memberId || !filePath) return Promise.reject(new Error('上传服务或照片未准备好'))
  const scope = storageContext(), revision = sessionRevision(), session = getSession()
  return new Promise((resolve, reject) => uni.uploadFile({
    url: apiBaseUrl.replace(/\/$/, '') + '/api/health/v1/uploads', filePath, name: 'file', timeout: 60000,
    formData: { member_id: memberId, purpose: 'meal' }, header: { Authorization: 'Bearer ' + (session?.token || '') },
    success(response) {
      if (scope !== storageContext() || revision !== sessionRevision()) return reject(Object.assign(new Error('账号已切换'), { code: 'SESSION_CHANGED' }))
      if (response.statusCode === 401) clearSession()
      let data
      try { data = typeof response.data === 'string' ? JSON.parse(response.data) : response.data }
      catch { return reject(new Error('上传响应无法读取，请重新选择照片；尚未提交识别或记餐')) }
      if (response.statusCode < 200 || response.statusCode >= 300) return reject(Object.assign(new Error(data?.message || data?.detail?.message || '照片上传失败'), { code: response.statusCode }))
      if (!data?.upload_id || data.purpose !== 'meal') return reject(new Error('照片上传回执无效'))
      resolve(data)
    },
    fail() { reject(Object.assign(new Error('上传结果未知，请重新选择照片；尚未提交识别或记餐'), { code: 'NETWORK_ERROR' })) },
  }))
}

/** 原图通过鉴权接口下载到临时路径，不公开带凭据的图片链接。 */
export function previewMealPhoto(uploadId, pageIndex) {
  if (!healthImageApiReady()) return Promise.reject(new Error('图片服务未配置'))
  const scope = storageContext(), revision = sessionRevision(), session = getSession()
  return new Promise((resolve, reject) => uni.downloadFile({
    url: apiBaseUrl.replace(/\/$/, '') + '/api/health/v1/uploads/' + encodeURIComponent(uploadId) + '/preview' + (Number.isInteger(pageIndex)?'?page_index='+pageIndex:''),
    header: { Authorization: 'Bearer ' + (session?.token || '') },
    success(response) {
      if (scope !== storageContext() || revision !== sessionRevision()) return reject(new Error('账号已切换，原图已隐藏'))
      if(response.statusCode===401)clearSession()
      if (response.statusCode !== 200) return reject(Object.assign(new Error('原图已失效或当前无权查看'),{code:response.statusCode}))
      resolve(response.tempFilePath)
    }, fail() { reject(new Error('原图读取失败，请重试')) },
  }))
}
