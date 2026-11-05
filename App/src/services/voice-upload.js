import { apiBaseUrl, allowLocalHealthApi } from './config.js'
import { getSession, clearSession, sessionRevision } from './session.js'
import { storageContext } from './storage.js'

export function uploadVoice(audio) {
  const local = allowLocalHealthApi && /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(apiBaseUrl)
  let sameOrigin = false
  // #ifdef H5
  sameOrigin = typeof window !== 'undefined' && apiBaseUrl === ''
  // #endif
  if (!/^https:\/\//.test(apiBaseUrl) && !local && !sameOrigin) return Promise.reject(new Error('语音上传服务尚未配置'))
  const session = getSession(), scope = storageContext(), revision = sessionRevision()
  if (!session?.token) return Promise.reject(new Error('请先登录后使用语音输入'))
  if (!audio.filePath || !audio.clientRequestId) return Promise.reject(new Error('录音文件未准备好，请重新录音'))
  return new Promise((resolve, reject) => {
    let settled = false, task
    const current = () => scope === storageContext() && revision === sessionRevision()
    const finish = (error, result) => {
      if (settled) return
      settled = true
      error ? reject(error) : resolve(result)
    }
    task = uni.uploadFile({
      url: apiBaseUrl.replace(/\/$/, '') + '/api/health/v1/voice/transcriptions',
      filePath: audio.filePath, name: 'file', timeout: 45000,
      header: { Authorization: 'Bearer ' + session.token, 'Idempotency-Key': audio.clientRequestId },
      formData: { client_request_id: audio.clientRequestId, format: audio.format, sample_rate: audio.sampleRate, channels: audio.numberOfChannels },
      success(response) {
        if (settled) return
        if (!current()) return finish(new Error('账号已切换，请重新录音'))
        if (response.statusCode === 401) clearSession()
        let data
        try { data = typeof response.data === 'string' ? JSON.parse(response.data) : response.data }
        catch { return finish(new Error('语音识别响应无法读取，可重试识别')) }
        if (response.statusCode < 200 || response.statusCode >= 300) {
          const detail = data?.detail
          return finish(Object.assign(new Error(data?.message || detail?.message || (typeof detail === 'string' && detail) || '语音识别失败，可重试识别'), { code: data?.code || detail?.code || response.statusCode }))
        }
        if (data?.client_request_id !== audio.clientRequestId || typeof data.text !== 'string' || !data.text.trim()) return finish(new Error('语音识别回执无效，请重试'))
        finish(null, { text: data.text.trim() })
      },
      fail() { finish(new Error(current() ? '语音上传未完成，请检查网络后重试' : '账号已切换，请重新录音')) },
    })
    audio.onCancelReady?.(() => {
      if (settled) return
      finish(Object.assign(new Error('已取消语音识别'), { code: 'VOICE_CANCELLED' }))
      task?.abort?.()
    })
  })
}
