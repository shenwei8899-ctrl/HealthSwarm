// 仅决定对话页的展示状态，不创建会话、不请求或生成餐单。
export function chatPresentation({route = {}, hasMessages = false, hasSavedArrangement = false, loading = false, newConversation = false, preparedThreadId = '', currentThreadId = ''}) {
  const separateThread = !!preparedThreadId && !!currentThreadId && preparedThreadId !== currentThreadId
  const initialResults = hasSavedArrangement && !newConversation && !separateThread && (!!route.preparation || route.from === 'onboarding')
  return {initialResults, welcome: !hasMessages && !initialResults && !(loading && currentThreadId)}
}
