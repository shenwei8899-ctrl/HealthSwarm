export function processingDisclosure() {
  return {
    title: '同意使用档案提供饮食咨询？',
    description: '为提供饮食咨询，需要将档案中的健康情况、饮食偏好及限制发送给 AI 服务进行分析。',
    content: '将使用档案中的健康情况、饮食偏好及限制，为你提供饮食咨询。相关资料会发送给 AI 服务进行分析。是否同意？',
  }
}

export function processingPolicyKey(config = {}) {
  return JSON.stringify([config.policy_version, config.consultation?.processor,
    config.consultation?.available])
}
