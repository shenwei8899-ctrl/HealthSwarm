import { request } from './request.js'
import { sessionRevision } from './session.js'

const uuid = /^[0-9a-f]{8}-[0-9a-f-]{27}$/i
export function chatText(content) {
  if (typeof content === 'string') return content
  return Array.isArray(content) ? content.filter(item => item.type === 'text').map(item => item.text || '').join('\n') : ''
}
export function chatMessages(value) {
  if (!Array.isArray(value?.history)) throw new Error('对话返回不完整，请重新读取')
  return value.history.flatMap(item => {
    const role = ({ human: 'user', user: 'user', ai: 'assistant', assistant: 'assistant' })[item.type || item.role]
    if (!role) return []
    const images = (item.image_contents || (item.image_content ? [item.image_content] : [])).filter(path => typeof path === 'string' && /^data:image\//.test(path))
    let text=chatText(item.content),business=null
    if(role==='assistant'&&text.trim().startsWith('{')){
      try{const data=JSON.parse(text)
        if((data.result_type==='needs_input'||data.status==='needs_input')&&Array.isArray(data.questions))text=data.questions.join('\n')
        else if(data.result_type==='meal_feedback'&&data.feedback?.details?.comment)text=data.feedback.details.comment
        else if(data.preview_id&&Array.isArray(data.meals)){business={type:'business',kind:'meal_plan_preview',data};text='餐单预览已返回，请核对菜品与份量。'}
        else if(data.result_type==='diet_analysis'&&Array.isArray(data.findings)){business={type:'business',kind:'diet_analysis',data};text='已保存饮食的回顾。'}
      }catch{}
    }
    const purchaseRequestId = role === 'assistant' && /\[食材包:[A-Za-z0-9_-]{100,4096}\]/.test(text) ? item.request_id || item.extra_metadata?.request_id || '' : ''
    if (role === 'assistant') text = text.replace(/\[食材包:[A-Za-z0-9_-]{100,4096}\]/g, '').trim()
    return [{ id: String(item.id), role, text, business, purchaseRequestId, createdAt: item.created_at,
      requestId: item.request_id || item.extra_metadata?.request_id || '', status: item.delivery_status || 'saved',
      ...(images.length ? { image: { localPath: images[0] } } : {}) }]
  })
}
export async function readChatDays(memberId, before = '', send = request) {
  if (!uuid.test(memberId || '')) throw new Error('请先选择本人的健康资料')
  const revision = sessionRevision()
  const { data } = await send({ path: `/api/health/v1/members/${memberId}/daily-conversations${before ? '?before=' + encodeURIComponent(before) : ''}` })
  if (revision !== sessionRevision()) throw new Error('账号已变化，请重新读取对话')
  if (!Array.isArray(data.days)) throw new Error('历史记录返回不完整，请重试')
  return { days: data.days.filter(row => /^\d{4}-\d{2}-\d{2}$/.test(row.date) && uuid.test(row.thread_id)), nextBefore: data.next_before || '' }
}
export async function readChatMessages(threadId, send = request) {
  return (await readChatSnapshot(threadId,send)).messages
}
export async function readChatSnapshot(threadId, send = request) {
  if (!uuid.test(threadId || '')) throw new Error('请选择有效的对话')
  const revision = sessionRevision()
  const { data } = await send({ path: `/api/chat/thread/${threadId}/history` })
  if (revision !== sessionRevision()) throw new Error('账号已变化，请重新读取对话')
  return {messages:chatMessages(data),runs:Array.isArray(data.runs)?data.runs:[]}
}

// The chat Run API accepts image content. This never creates a meal draft/log.
export async function chatImageContent(image) {
  const path = image?.localPath || image?.path
  if (!path) throw new Error('请先选择照片')
  if (/^data:image\/(jpeg|png|webp);base64,/.test(path)) return path
  if (typeof window !== 'undefined') {
    const response = await fetch(path)
    if (!response.ok) throw new Error('照片读取失败，请重新选择')
    const blob = await response.blob()
    if (blob.size > 2 * 1024 * 1024) throw new Error('请使用小于2MB的照片')
    return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = () => reject(new Error('照片读取失败')); reader.readAsDataURL(blob) })
  }
  return new Promise((resolve, reject) => uni.getFileSystemManager().readFile({ filePath: path, encoding: 'base64',
    success(result) {
      if (result.data.length > 3 * 1024 * 1024) return reject(new Error('请使用小于2MB的照片'))
      const mime = /\.png$/i.test(path) ? 'png' : /\.webp$/i.test(path) ? 'webp' : 'jpeg'
      resolve(`data:image/${mime};base64,${result.data}`)
    }, fail() { reject(new Error('照片读取失败，请重新选择')) } }))
}
