import { apiBaseUrl } from './config.js'
import { getSession, clearSession, sessionRevision } from './session.js'
import { request } from './request.js'
import { healthImageApiReady } from './health-upload.js'
import { createAccountSettingsClient } from './account-settings-client.js'

function upload(path, filePath) {
  if (!healthImageApiReady() || !getSession()?.token) return Promise.reject(new Error('请先登录后重试'))
  const account = getSession(), revision = sessionRevision()
  return new Promise((resolve, reject) => uni.uploadFile({
    url: apiBaseUrl.replace(/\/$/, '') + path, filePath, name: 'file', timeout: 60000,
    header: { Authorization: 'Bearer ' + account.token },
    success(response) {
      if (revision !== sessionRevision()) return reject(Object.assign(new Error('账号已切换'), { code: 'SESSION_CHANGED' }))
      if (response.statusCode === 401) clearSession()
      let data
      try { data = typeof response.data === 'string' ? JSON.parse(response.data) : response.data }
      catch { return reject(new Error('上传响应无法读取，请重试')) }
      if (response.statusCode < 200 || response.statusCode >= 300) return reject(new Error(typeof data?.detail === 'string' ? data.detail : '图片上传失败，请重试'))
      resolve(data)
    },
    fail() { reject(new Error('上传结果未确认，请重试')) },
  }))
}
let assetBaseUrl = apiBaseUrl
// #ifdef H5
// uni-image 会给根相对地址附加 H5 base，账号图片使用完整同源地址。
if (!assetBaseUrl && typeof window !== 'undefined') assetBaseUrl = window.location.origin
// #endif
export const accountSettings = createAccountSettingsClient({ send: request, upload, session: getSession, baseUrl: assetBaseUrl })
