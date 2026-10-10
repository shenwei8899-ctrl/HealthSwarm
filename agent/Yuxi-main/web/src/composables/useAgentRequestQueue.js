import { agentApi } from '@/apis'
import { processRunSseResponse } from '@/composables/useAgentRunStream'
import { IDLE_QUEUE_SNAPSHOT } from '@/composables/useAgentThreadState'
import { handleChatError } from '@/utils/errorHandler'

export function useAgentRequestQueue({
  getThreadState,
  resetOnGoingConv,
  startRunStream,
  onStreamError
}) {
  const removeRequestFromQueue = (ts, requestId) => {
    if (!ts || !ts.queuedRequests) return
    ts.queuedRequests = ts.queuedRequests.filter((r) => r.request_id !== requestId)
  }

  const stopRequestStream = (threadId, requestId) => {
    const ts = getThreadState(threadId)
    const entry = ts?.requestStreams?.[requestId]
    if (!entry) return
    entry.controller?.abort()
    delete ts.requestStreams[requestId]
  }

  const stopAllRequestStreams = (threadId) => {
    const ts = getThreadState(threadId)
    if (!ts?.requestStreams) return
    for (const rid of Object.keys(ts.requestStreams)) {
      stopRequestStream(threadId, rid)
    }
  }

  const cancelRequest = async (threadId, requestId) => {
    const ts = getThreadState(threadId)
    if (!ts || !requestId) return false
    if (
      ts.queuedRequests?.some(
        (request) => request.request_id === requestId && request.status === 'sending'
      )
    )
      return false
    try {
      await agentApi.cancelRequest(requestId)
      stopRequestStream(threadId, requestId)
      removeRequestFromQueue(ts, requestId)
      if (ts.onGoingConv?.msgChunks) {
        delete ts.onGoingConv.msgChunks[requestId]
      }
      return true
    } catch (error) {
      if (error?.name !== 'AbortError') {
        handleChatError(error, 'cancel')
      }
      return false
    }
  }

  /** 仅接收同线程、同队列投影发起的快照，避免迟到读复活已派发请求。 */
  const syncQueuedRequests = async (threadId, agentSlug) => {
    const ts = getThreadState(threadId)
    if (!ts) return
    const queuedAtRead = ts.queuedRequests
    try {
      const resp = await agentApi.listThreadQueuedRequests(threadId, agentSlug)
      if (getThreadState(threadId) !== ts || ts.queuedRequests !== queuedAtRead) return
      const requests = resp?.requests || []
      const knownIds = new Set(requests.map((request) => request.request_id))
      ts.queuedRequests = [
        ...requests.map((request) => {
          const localMessage = ts.queuedRequests?.find(
            (item) => item.request_id === request.request_id
          )?.message
          // 队列接口只投影状态与文字，本地用户消息随队列项保留到派发或取消。
          return localMessage ? { ...request, message: localMessage } : request
        }),
        ...(ts.queuedRequests || []).filter(
          (request) => request.status === 'sending' && !knownIds.has(request.request_id)
        )
      ]
      ts.queueSnapshot = resp?.queue || { ...IDLE_QUEUE_SNAPSHOT }
    } catch (e) {
      console.warn('Failed to sync queued requests:', e)
    }
  }

  /** 为已接入请求建立订阅，在队列快照移除已派发项前接住本地消息。 */
  const subscribeQueuedRequests = (threadId) => {
    for (const request of getThreadState(threadId)?.queuedRequests || []) {
      if (request?.request_id && request.status !== 'sending') {
        void startRequestStream(threadId, request.request_id)
      }
    }
  }

  /** 同步前保留本地请求，同步后订阅服务端新增项。 */
  const resumeQueuedRequests = async (threadId, agentSlug) => {
    if (!threadId || !agentSlug) return
    subscribeQueuedRequests(threadId)
    await syncQueuedRequests(threadId, agentSlug)
    subscribeQueuedRequests(threadId)
  }

  /** 断流后查询同 Request，有限退避重连；恢复过程不重新提交正文。 */
  const startRequestStream = async (threadId, requestId) => {
    if (!threadId || !requestId) return
    const ts = getThreadState(threadId)
    if (!ts) return

    ts.requestStreams = ts.requestStreams || {}
    const message = ts.queuedRequests?.find((request) => request.request_id === requestId)?.message
    if (ts.requestStreams[requestId]) {
      ts.requestStreams[requestId].message ||= message
      return
    }

    const controller = new AbortController()
    ts.requestStreams[requestId] = { controller, position: 0, status: 'queued', message, reconnectTimer: null }
    const entry = ts.requestStreams[requestId]
    /** 仅当前订阅可处理恢复读取，停止或替换后忽略迟到结果。 */
    const isCurrent = () =>
      !controller.signal.aborted && getThreadState(threadId)?.requestStreams?.[requestId] === entry
    let failures = 0
    let handoffPromise = null
    let handoffFailed = false

    /** 不同 Run 交接先读当前事实；合法前驱结束或重连不阻止下一请求接管。 */
    const handoffRun = async (data) => {
      const tsInner = getThreadState(threadId)
      if (!isCurrent() || !data.run_id || entry.status === 'dispatched') return
      entry.status = 'dispatched'
      if (tsInner.activeRunId && tsInner.activeRunId !== data.run_id) {
        const activeRunAtRead = tsInner.activeRunId
        const { run } = await agentApi.getAgentRun(data.run_id)
        if (!isCurrent()) return
        if (
          run?.id !== data.run_id ||
          run.conversation_thread_id !== threadId ||
          run.request_id !== requestId
        ) {
          throw Object.assign(new Error('请求派发的运行来源不一致，请重新读取会话'), {
            code: 'run_handoff_source_mismatch'
          })
        }
        if (
          tsInner.activeRunId &&
          tsInner.activeRunId !== activeRunAtRead &&
          tsInner.activeRunId !== data.run_id
        ) {
          removeRequestFromQueue(tsInner, requestId)
          stopRequestStream(threadId, requestId)
          return
        }
        if (!['pending', 'running'].includes(run.status)) {
          removeRequestFromQueue(tsInner, requestId)
          stopRequestStream(threadId, requestId)
          if (tsInner.onGoingConv?.msgChunks) delete tsInner.onGoingConv.msgChunks[requestId]
          return
        }
      }
      const request = tsInner.queuedRequests?.find((item) => item.request_id === requestId)
      const requestMessages =
        tsInner.onGoingConv?.msgChunks?.[requestId] ||
        (entry.message ? [entry.message] : null) ||
        (request
          ? [
              {
                id: request.input_message_id || requestId,
                type: 'human',
                request_id: requestId,
                content: request.content,
                created_at: request.created_at
              }
            ]
          : null)
      removeRequestFromQueue(tsInner, requestId)
      stopRequestStream(threadId, requestId)

      // 旧 Run 尚未 finalize 时保留已渲染内容；startRunStream 会 flush 并中止旧订阅。
      // 若旧 Run 已 finalize，则其 history 刷新已在途，可以清理残留的 ongoing 状态。
      if (!tsInner.activeRunId) {
        resetOnGoingConv(threadId, { preserveRequestStreams: true })
      }
      if (requestMessages && tsInner.onGoingConv?.msgChunks) {
        tsInner.onGoingConv.msgChunks[requestId] = requestMessages
      }
      tsInner.pendingRequestId = requestId
      // 重复派发同 Run 时保留存活订阅，已停止时沿已消费游标恢复。
      const isSameRun = tsInner.activeRunId === data.run_id
      if (
        isSameRun &&
        tsInner.runStreamAbortController &&
        !tsInner.runStreamAbortController.signal.aborted
      ) {
        return
      }
      void startRunStream(
        threadId,
        data.run_id,
        isSameRun ? tsInner.runLastSeq || '0-0' : '0-0',
        { requestId }
      )
    }

    const handleEvent = (event, data) => {
      // 一次性取 ts/entry，避免每个分支重复 getThreadState 触发响应式追踪。
      const tsInner = getThreadState(threadId)
      const innerEntry = tsInner?.requestStreams?.[requestId]
      if (controller.signal.aborted || innerEntry !== entry) return

      if (event === 'queued' && data) {
        failures = 0
        entry.position = data.position || entry.position
        const queuedRequest = tsInner.queuedRequests?.find((r) => r.request_id === requestId)
        if (queuedRequest) queuedRequest.queue_position = entry.position
      } else if (event === 'run_created' && data) {
        if (!handoffFailed) {
          handoffPromise ||= handoffRun(data).catch((error) => {
            if (!isCurrent() || error?.name === 'AbortError') return
            if (
              [401, 403, 404, 409, 410].includes(error?.status) ||
              error?.code === 'run_handoff_source_mismatch'
            ) {
              handleEvent('error')
              handleChatError(error, 'stream')
              return
            }
            // 临时查询失败沿已有退避重读同 Request，不在同轮重复交接或提交正文。
            entry.status = 'queued'
            handoffFailed = true
            handoffPromise = null
          })
        }
      } else if (['cancelled', 'rejected', 'failed', 'error'].includes(event)) {
        entry.status = event
        // Request 终态不能清理同线程正在执行的另一 Run。
        if (!tsInner.activeRunId && tsInner.pendingRequestId === requestId) {
          tsInner.isStreaming = false
          tsInner.replyLoadingVisible = false
          tsInner.pendingRequestId = null
        }
        if (tsInner.onGoingConv?.msgChunks) delete tsInner.onGoingConv.msgChunks[requestId]
        removeRequestFromQueue(tsInner, requestId)
        stopRequestStream(threadId, requestId)
        if (typeof onStreamError === 'function') {
          onStreamError(threadId, requestId, event)
        }
      }
    }

    try {
      while (isCurrent()) {
        handoffFailed = false
        try {
          const response = await agentApi.streamRequestEvents(requestId, { signal: controller.signal })
          if (!isCurrent()) return
          if (!response.ok) {
            throw Object.assign(new Error(`Request SSE response not ok: ${response.status}`), {
              status: response.status
            })
          }
          await processRunSseResponse(response, handleEvent)
          if (handoffPromise) await handoffPromise
        } catch (error) {
          if (!isCurrent() || error?.name === 'AbortError') return
          if ([401, 403, 404, 409, 410].includes(error?.status)) {
            handleEvent('error')
            handleChatError(error, 'stream')
            return
          }
        }
        if (!isCurrent()) return
        failures += 1

        // 订阅断线窗口中可能已派发或结束，以 PostgreSQL 当前事实完成交接。
        try {
          if (!handoffFailed) {
            const { request } = await agentApi.getRequest(requestId)
            if (!isCurrent()) return
            if (request?.request_id !== requestId || request.thread_id !== threadId) {
              handleEvent('error')
              handleChatError(new Error('请求恢复来源不一致，请重新读取会话'), 'stream')
              return
            }
            if (request.status === 'dispatched' && request.dispatched_run_id) {
              handleEvent('run_created', { run_id: request.dispatched_run_id })
              await handoffPromise
            } else if (['cancelled', 'rejected', 'failed'].includes(request.status)) {
              handleEvent(request.status)
            }
          }
        } catch (error) {
          if (!isCurrent() || error?.name === 'AbortError') return
          if ([401, 403, 404, 409, 410].includes(error?.status)) {
            handleEvent('error')
            handleChatError(error, 'stream')
            return
          }
        }
        if (!isCurrent()) return
        if (failures >= 6) {
          handleChatError(new Error('请求进度连接已中断，请重新进入会话恢复原请求'), 'stream')
          return
        }

        await new Promise((resolve) => {
          const finish = () => {
            clearTimeout(entry.reconnectTimer)
            entry.reconnectTimer = null
            controller.signal.removeEventListener('abort', finish)
            resolve()
          }
          entry.reconnectTimer = setTimeout(finish, Math.min(500 * 2 ** (failures - 1), 5000))
          controller.signal.addEventListener('abort', finish, { once: true })
        })
      }
    } finally {
      const tsFinal = getThreadState(threadId)
      if (tsFinal?.requestStreams?.[requestId]?.controller === controller) {
        delete tsFinal.requestStreams[requestId]
      }
    }
  }

  const continueQueue = async (threadId, agentSlug) => {
    const ts = getThreadState(threadId)
    if (!ts || !threadId || !agentSlug || ts.continueQueueInFlight) return false

    ts.continueQueueInFlight = true
    subscribeQueuedRequests(threadId)
    try {
      const response = await agentApi.continueThreadQueue(threadId, agentSlug)
      await syncQueuedRequests(threadId, agentSlug)
      if (response?.request_id) {
        void startRequestStream(threadId, response.request_id)
      }
      return true
    } catch (error) {
      handleChatError(error, 'continue_queue')
      return false
    } finally {
      ts.continueQueueInFlight = false
    }
  }

  const steerRequest = async (threadId, agentSlug, requestId) => {
    const ts = getThreadState(threadId)
    if (!ts || !threadId || !agentSlug || !requestId) return false

    void startRequestStream(threadId, requestId)
    try {
      await agentApi.steerRequest(requestId)
      await syncQueuedRequests(threadId, agentSlug)
      void startRequestStream(threadId, requestId)
      return true
    } catch (error) {
      handleChatError(error, 'steer')
      return false
    }
  }

  return {
    startRequestStream,
    stopAllRequestStreams,
    cancelRequest,
    syncQueuedRequests,
    resumeQueuedRequests,
    continueQueue,
    steerRequest
  }
}
