import { request } from './request.js'

export function replyMessageId(value) {
  if (typeof value !== 'number' && (typeof value !== 'string' || !/^[1-9]\d*$/.test(value))) return null
  const id = Number(value)
  return Number.isSafeInteger(id) && id > 0 ? id : null
}

// Read before writing: the existing API allows one immutable vote per answer.
// An uncertain write is read back, never automatically posted a second time.
export async function saveReplyFeedback(messageId, rating, { send = request, isCurrent = () => true } = {}) {
  const id = replyMessageId(messageId)
  if (!id || !['like', 'dislike'].includes(rating)) throw new Error('这条回复暂不支持评价')
  const path = `/api/chat/message/${id}/feedback`
  const current = () => { if (!isCurrent()) throw new Error('对话已变化，请重新操作') }
  const read = async () => {
    const { data } = await send({ path }); current()
    if (data?.has_feedback === false && data.feedback === null) return null
    if (data?.has_feedback === true && replyMessageId(data.feedback?.id) && ['like', 'dislike'].includes(data.feedback.rating)) return data.feedback.rating
    throw new Error('评价状态无法核对，请稍后重试')
  }
  current()
  const existing = await read()
  if (existing) return existing
  try {
    const { data } = await send({ path, method: 'POST', data: { rating } }); current()
    if (!replyMessageId(data?.id) || data.message_id !== id || data.rating !== rating) throw new Error('评价回执无法核对')
    return rating
  } catch (error) {
    current()
    if (Number(error.code) === 409 || error.code === 'NETWORK_ERROR' || !error.code) {
      const confirmed = await read()
      if (confirmed) return confirmed
      throw new Error('评价结果尚未确认，请稍后点选重新核对')
    }
    throw error
  }
}
