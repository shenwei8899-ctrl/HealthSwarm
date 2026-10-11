import { serviceMode } from './config.js'
const key = () => 'fn-session-v2:' + serviceMode
export function getSession() { const session=uni.getStorageSync(key());return session?JSON.parse(JSON.stringify(session)):null }
export function setSession(session) {
  if (!session?.accountId || (serviceMode==='mock'&&!session?.householdId)) throw new Error('会话缺少账号或家庭信息')
  if(serviceMode==='api'&&session.isDemo)throw new Error('真实环境不能使用测试会话')
  uni.setStorageSync(key(), JSON.parse(JSON.stringify({...session,clientRevision:Date.now()+'-'+Math.random().toString(36).slice(2)})))
}
export function clearSession() { uni.setStorageSync(key(), null) }

export function sessionRevision(){return getSession()?.clientRevision||'guest'}
