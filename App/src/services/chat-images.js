import { callApiAdapter } from './index.js'
import { storageContext } from './storage.js'

const unavailable = () => Object.assign(new Error('图片已保留，AI 看图服务暂不可用，请稍后重试'), { code: 'IMAGE_CHAT_NOT_READY' })

// Store a durable local copy before a photo becomes part of the chat history.
export async function persistChatImage(image) {
  if (!image?.path) throw new Error('没有可用的图片，请重新选择')
  let localPath
  // #ifdef H5
  if (typeof window !== 'undefined' && typeof FileReader !== 'undefined') {
    const response = await fetch(image.path)
    if (!response.ok) throw new Error('图片读取失败，请重新选择')
    const blob = await response.blob()
    if (blob.size > 2 * 1024 * 1024) throw new Error('图片较大，请选择小于 2MB 的照片')
    localPath = await new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result)
      reader.onerror = () => reject(new Error('图片保存失败，请重试'))
      reader.readAsDataURL(blob)
    })
  }
  // #endif
  if (!localPath) {
    localPath = await new Promise((resolve, reject) => {
      if (typeof uni.saveFile !== 'function') { reject(new Error('图片保存暂不可用，请重试')); return }
      uni.saveFile({ tempFilePath: image.path,
        success: result => result.savedFilePath ? resolve(result.savedFilePath) : reject(new Error('图片保存失败，请重试')),
        fail: () => reject(new Error('图片保存失败，请检查存储空间后重试')),
      })
    })
  }
  return { localPath, source: image.source || 'album' }
}

export function previewChatImage(image) {
  const path = image?.localPath || image?.path
  if (path) uni.previewImage({ current: path, urls: [path] })
}

// The backend team supplies these adapters; never send a device path to a model.
// clientMessageId must be used to deduplicate an upload and its subsequent reply.
export async function sendChatImage(message, { isCurrent = () => true } = {}) {
  const scope = storageContext()
  const check = () => {
    if (scope !== storageContext() || !isCurrent()) throw Object.assign(new Error('本次请求已取消'), { code: 'STALE_CHAT_REQUEST' })
  }
  try {
    check()
    if (!message.image.remoteId) {
      const uploaded = await callApiAdapter('uploadChatImage', { filePath: message.image.localPath, clientMessageId: message.id })
      check()
      if (!uploaded?.id || typeof uploaded.id !== 'string') throw new Error('图片上传结果不完整，请重试')
      message.image.remoteId = uploaded.id
    }
    const reply = await callApiAdapter('chatWithImage', {
      clientMessageId: message.id, text: message.text, images: [{ id: message.image.remoteId }],
    })
    check()
    if (typeof reply?.text !== 'string' || !reply.text.trim()) throw new Error('回复未完成，请重试')
    return { text: reply.text }
  } catch (error) {
    if (error.code === 'ADAPTER_NOT_READY') throw unavailable()
    throw error
  }
}
