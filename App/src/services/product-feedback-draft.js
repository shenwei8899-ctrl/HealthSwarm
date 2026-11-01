export function createFeedbackDraft({ client, newId, context, reactive = value => value }) {
  const state = reactive({ content: '', images: [], busy: false, error: '', saved: false, receipt: null })
  const own = context()
  let active = true, fingerprint = '', requestId = '', uploaded = []
  function current() {
    if (!active || own !== context()) throw Object.assign(new Error('账号或页面已变化，请重新填写'), { code: 'SESSION_CHANGED' })
  }
  return {
    state,
    dispose() { active = false },
    async submit() {
      if (state.busy || state.saved) return
      state.error = ''
      try {
        current()
        const content = state.content.trim()
        if (!content || Array.from(content).length > 200) throw new Error('请填写1至200字的反馈内容')
        if (state.images.length > 3 || state.images.some(image => image.size > 5 * 1024 * 1024)) throw new Error('最多添加3张图片，每张不超过5MB')
        const next = JSON.stringify([content, state.images.map(image => image.path)])
        if (fingerprint !== next) { fingerprint = next; requestId = newId(); uploaded = [] }
        state.busy = true
        for (let index = 0; index < state.images.length; index++) {
          current()
          if (!uploaded[index]) uploaded[index] = await client.image(requestId, index, state.images[index].path)
          current()
        }
        const result = await client.submit(requestId, content, uploaded)
        current(); state.receipt = result; state.saved = true
      } catch (error) {
        if (active) state.error = error.message || '提交失败，请重试'
      } finally { state.busy = false }
    },
  }
}
