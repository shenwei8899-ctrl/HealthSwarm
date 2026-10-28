import { request } from './request.js'
import { sessionRevision } from './session.js'

const uuid = /^[0-9a-f]{8}-[0-9a-f-]{27}$/i
const conversationUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
const conversationPageSize = 20
const sameId = (left, right) => typeof left === 'string' && typeof right === 'string' && left.toLowerCase() === right.toLowerCase()
const validBusinessDate = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) &&
  !Number.isNaN(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value

export function conversationTitle(value, maxLength = 36) {
  const text = typeof value === 'string' ? value.replace(/[\u0000-\u001f\u007f]/g, ' ').replace(/\s+/g, ' ').trim() : ''
  if (!text) return '新对话'
  const length = Number.isInteger(maxLength) && maxLength > 0 && maxLength <= 120 ? maxLength : 36
  const characters = Array.from(text)
  return characters.length > length ? characters.slice(0, length).join('') + '…' : text
}

export function conversationSummary(messages) {
  const first = Array.isArray(messages) && messages.find(message => message?.role === 'user' &&
    (typeof message.text === 'string' && message.text.trim() || message.image))
  return first ? conversationTitle(typeof first.text === 'string' && first.text.trim() || '[图片]') : '新对话'
}

export async function readConversations(memberId, offset = 0, send = request) {
  if (!conversationUuid.test(memberId || '')) throw new Error('请先选择本人的健康资料')
  if (!Number.isSafeInteger(offset) || offset < 0 || offset > Number.MAX_SAFE_INTEGER - conversationPageSize) {
    throw new Error('对话分页位置无效，请重新读取')
  }
  const revision = sessionRevision()
  const { data } = await send({ path: `/api/health/v1/members/${memberId}/consultations?limit=${conversationPageSize}&offset=${offset}` })
  if (revision !== sessionRevision()) throw new Error('账号已变化，请重新读取对话')
  const items = data?.items
  if (!Array.isArray(items) || items.length > conversationPageSize || typeof data.has_more !== 'boolean' ||
      items.some(row => !row || !conversationUuid.test(row.thread_id || '') || !sameId(row.member_id, memberId) ||
        row.agent_slug !== 'health-consultation' || !(row.business_date === null || validBusinessDate(row.business_date)) ||
        typeof row.created_at !== 'string' || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(row.created_at) ||
        !validBusinessDate(row.created_at.slice(0, 10)) || !Number.isFinite(Date.parse(row.created_at))) ||
      new Set(items.map(row => row.thread_id.toLowerCase())).size !== items.length ||
      (data.has_more ? !items.length || data.next_offset !== offset + items.length : data.next_offset !== null)) {
    throw new Error('对话目录返回不完整，请重新读取')
  }
  return {
    items: items.map(row => ({ thread_id: row.thread_id, member_id: row.member_id, agent_slug: row.agent_slug,
      business_date: row.business_date, created_at: row.created_at })),
    hasMore: data.has_more, nextOffset: data.next_offset,
  }
}
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
  if (data?.thread?.id !== undefined && !sameId(data.thread.id, threadId)) throw new Error('返回的对话与当前选择不一致，请重新读取')
  const metadata = data?.thread
  const thread = metadata && typeof metadata === 'object' && !Array.isArray(metadata) ? {
    id: threadId,
    title: typeof metadata.title === 'string' ? conversationTitle(metadata.title, 120) : '',
    agentId: typeof (metadata.agent_id ?? metadata.agentId) === 'string' ? (metadata.agent_id ?? metadata.agentId).slice(0, 120) : '',
  } : null
  return {messages:chatMessages(data),runs:Array.isArray(data.runs)?data.runs:[],thread}
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
