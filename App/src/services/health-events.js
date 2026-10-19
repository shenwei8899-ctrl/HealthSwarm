import { apiBaseUrl } from './config.js'
import { getSession, sessionRevision } from './session.js'

/** 增量解析SSE，只向调用方交付事件身份；正文始终从权威结果接口读取。 */
export function createHealthEventParser(onEvent) {
  let buffer = '', bytes = []
  return chunk => {
    if (typeof chunk === 'string') buffer += chunk
    else {
      for (const value of new Uint8Array(chunk)) bytes.push(value)
      if (bytes.length > 1024 * 1024) throw new Error('事件片段过大')
      let index = 0
      while (index < bytes.length) {
        const first = bytes[index], count = first < 128 ? 1 : first < 224 ? 2 : first < 240 ? 3 : 4
        if (index + count > bytes.length) break
        let code = first & (count === 1 ? 127 : (1 << (7 - count)) - 1)
        for (let i = 1; i < count; i++) code = (code << 6) | (bytes[index + i] & 63)
        buffer += String.fromCodePoint(code); index += count
      }
      bytes = bytes.slice(index)
    }
    buffer = buffer.replace(/\r\n/g, '\n')
    if (buffer.length > 1024 * 1024) throw new Error('事件片段过大')
    let boundary
    while ((boundary = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2)
      let id = '', type = 'message'; const data = []
      for (const line of block.split('\n')) {
        if (line.startsWith('id:')) id = line.slice(3).trim()
        if (line.startsWith('event:')) type = line.slice(6).trim()
        if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
      }
      if (!data.length) continue
      let value
      try { value = JSON.parse(data.join('\n')) } catch { continue }
      if (!value || typeof value !== 'object') continue
      onEvent({ id: /^\d+-\d+$/.test(id) ? id : '', type, runId: value.run_id, requestId: value.request_id })
    }
  }
}

/** 原生分块请求和H5流式读取共用游标，断流由任务查询兜底。 */
export function subscribeHealthEvents({ requestId, runId, cursor = '0-0', onEvent, onEnd = () => {}, onError = () => {} }) {
  if (typeof uni === 'undefined') return () => {}
  if (!getSession()?.token) return () => {}
  const rev = sessionRevision(), token = getSession().token
  const sameOrigin = typeof window !== 'undefined' && apiBaseUrl === ''
  if (!sameOrigin && !/^https:\/\//.test(apiBaseUrl)) return () => {}
  const path = runId ? `/api/agent/runs/${encodeURIComponent(runId)}/events?verbose=false&after_seq=${encodeURIComponent(cursor)}` : `/api/agent/requests/${encodeURIComponent(requestId)}/events`
  const url = apiBaseUrl.replace(/\/$/, '') + path
  let closed = false, abort = () => {}
  const current = () => !closed && sessionRevision() === rev
  const parse = createHealthEventParser(event => { if (current()) onEvent(event) })
  const failed = error => { if (current()) onError(error) }
  const ended = () => { if (current()) onEnd() }
  if (typeof window !== 'undefined' && typeof fetch === 'function' && typeof AbortController === 'function') {
    const controller = new AbortController(); abort = () => controller.abort()
    void (async () => {
      try {
        const response = await fetch(url, { headers: { Authorization: 'Bearer ' + token, Accept: 'text/event-stream' }, signal: controller.signal, cache: 'no-store' })
        if (!response.ok) throw Object.assign(new Error('事件连接不可用'), { code: response.status })
        if (!response.body?.getReader) throw new Error('当前环境不支持事件流')
        const reader = response.body.getReader()
        while (current()) { const { value, done } = await reader.read(); if (done) break; parse(value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength)) }
        ended()
      } catch (error) { if (error.name !== 'AbortError') failed(error) }
    })()
  } else if (typeof uni !== 'undefined' && typeof uni.request === 'function') {
    const task = uni.request({ url, method: 'GET', enableChunked: true, responseType: 'arraybuffer', timeout: 60000,
      header: { Authorization: 'Bearer ' + token, Accept: 'text/event-stream' },
      success(response) { if (response.statusCode >= 400) failed({ code: response.statusCode }); else ended() },
      fail: failed,
    })
    task?.onChunkReceived?.(event => { if (current()) { try { parse(event.data) } catch (error) { abort(); failed(error) } } })
    abort = () => task?.abort?.()
    if (!task?.onChunkReceived) { abort(); failed(new Error('当前环境使用任务查询恢复')) }
  }
  return () => { closed = true; abort() }
}
