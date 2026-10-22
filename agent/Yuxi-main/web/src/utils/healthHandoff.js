/** 交接入口只挂在同一已完成任务的持久化事实正文上，来源有效性由服务端复验。 */
export function handoffSourceRequestId(
  message,
  run,
  agentSlug,
  isProcessing = false,
  hasError = false
) {
  if (
    isProcessing ||
    hasError ||
    message?.type !== 'ai' ||
    !Number.isInteger(message.id) ||
    message.id < 1 ||
    message.message_type !== 'text' ||
    message.delivery_status !== 'complete' ||
    message.isStoppedByUser ||
    message.tool_calls?.length ||
    run?.status !== 'completed' ||
    !message.run_id ||
    run.run_id !== message.run_id ||
    !message.request_id ||
    run.request_id !== message.request_id ||
    ![
      'health-blood-glucose',
      'health-blood-lipids',
      'health-blood-pressure',
      'health-diet-analyst'
    ].includes(agentSlug)
  )
    return null
  if (agentSlug === 'health-diet-analyst') {
    let result
    try {
      result = JSON.parse(message.content)
    } catch {
      return null
    }
    // 显式个人目标可随原分析展示，交接服务只取事实，不复制目标和模型建议。
    if (result?.result_type !== 'diet_analysis' || result.status !== 'completed') return null
  }
  return message.request_id
}
