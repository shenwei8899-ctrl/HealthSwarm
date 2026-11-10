import { serviceMode } from './config.js'
const key = () => 'fn-session-v2:' + serviceMode
export function getSession() { const session=uni.getStorageSync(key());return session?JSON.parse(JSON.stringify(session)):null }
export function setSession(session, { preserveRevision = false } = {}) {
  if (!session?.accountId || (serviceMode==='mock'&&!session?.householdId)) throw new Error('会话缺少账号或家庭信息')
  if(serviceMode==='api'&&session.isDemo)throw new Error('真实环境不能使用测试会话')
  const previous = getSession()
  const sameIdentity = preserveRevision && previous && ['accountId','token','householdId','authSource'].every(field => previous[field] === session[field])
  uni.setStorageSync(key(), JSON.parse(JSON.stringify({...session,clientRevision:sameIdentity ? previous.clientRevision : Date.now()+'-'+Math.random().toString(36).slice(2)})))
}
export function clearSession() {
  const session = getSession()
  if (session) try {
    const snapshotKey = `fn:v2:${serviceMode}:${encodeURIComponent(session.accountId || 'guest')}:${encodeURIComponent(session.householdId || (serviceMode === 'api' ? 'unassigned' : 'preview'))}:today-menu:snapshot-v1`
    uni.setStorageSync(snapshotKey, null)
  } catch (_) {}
  uni.setStorageSync(key(), null)
}

export function sessionRevision(){return getSession()?.clientRevision||'guest'}
