import { serviceMode } from './config.js'
import { getSession,sessionRevision } from './session.js'
export function storageScope() {
  const session = getSession()
  return `fn:v2:${serviceMode}:${encodeURIComponent(session?.accountId || 'guest')}:${encodeURIComponent(session?.householdId || (serviceMode === 'api' ? 'unassigned' : 'preview'))}:`
}
export const scopedStorage = {
  getStorageSync(key) { const value=uni.getStorageSync(storageScope()+key);return value===undefined?undefined:JSON.parse(JSON.stringify(value)) },
  setStorageSync(key, value) { uni.setStorageSync(storageScope() + key, JSON.parse(JSON.stringify(value))) },
  getStorageInfoSync() {
    const prefix = storageScope()
    return { keys: (uni.getStorageInfoSync().keys || []).filter(key => key.startsWith(prefix)).map(key => key.slice(prefix.length)) }
  },
}

export function storageContext(){return storageScope()+'session:'+sessionRevision()}
