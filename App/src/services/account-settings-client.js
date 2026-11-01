// 账号资料与产品反馈共用登录边界，页面只持有图片临时路径。
export function createAccountSettingsClient({ send, upload, session, baseUrl = '' }) {
  const identity = () => { const s = session(); return s?.accountId + ':' + s?.token + ':' + s?.clientRevision }
  const check = value => { if (value !== identity()) throw Object.assign(new Error('账号已切换，请重新操作'), { code: 'SESSION_CHANGED' }) }
  function avatarUrl(value) {
    if (!value) return ''
    if (typeof value !== 'string') throw new Error('头像地址无效')
    if (value.startsWith('/minio/public/')) return baseUrl.replace(/\/$/, '') + value
    if (/^https:\/\//.test(value)) return value
    throw new Error('头像地址不可用')
  }
  async function profile() {
    const own = identity(), result = (await send({ path: '/api/auth/me' })).data
    check(own)
    if (String(result?.id) !== String(session()?.accountId)) throw new Error('账号资料不一致')
    return { avatar: avatarUrl(result.avatar), nickname: typeof result.username === 'string' ? result.username : '' }
  }
  return {
    profile,
    async avatar() { return (await profile()).avatar },
    async saveNickname(value) {
      const nickname = value.trim()
      if (Array.from(nickname).length < 2 || Array.from(nickname).length > 20 || !/^[一-龥a-zA-Z0-9_]+$/.test(nickname)) throw new Error('昵称需为2–20个字符，支持中文、英文、数字和下划线')
      const own = identity(), result = (await send({ path: '/api/auth/profile', method: 'PUT', data: { username: nickname } })).data
      check(own)
      if (String(result?.id) !== String(session()?.accountId)) throw new Error('账号资料不一致')
      if (result.username !== nickname) throw new Error('昵称保存结果未确认，请重新读取')
      return result.username
    },
    async saveAvatar(filePath) {
      const own = identity(), result = await upload('/api/auth/upload-avatar', filePath)
      check(own)
      if (result?.success !== true || !result.avatar_url) throw new Error('头像保存结果未确认，请重新读取')
      return avatarUrl(result.avatar_url)
    },
    async image(id, slot, filePath) {
      const own = identity(), result = await upload(`/api/product-feedback/${id}/images/${slot}`, filePath)
      check(own)
      if (!/^[0-9a-f-]{36}$/i.test(result?.upload_id || '') || result.slot !== slot) throw new Error('图片上传结果未确认，请重试')
      return result.upload_id
    },
    async submit(id, content, imageIds) {
      const own = identity(), result = (await send({ path: '/api/product-feedback', method: 'POST', data: { id, content, image_ids: imageIds } })).data
      check(own)
      if (result?.id !== id || result.status !== 'submitted' || !result.submitted_at) throw new Error('反馈保存结果未确认，请重试')
      return result
    },
  }
}
