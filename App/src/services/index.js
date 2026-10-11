import { isMockMode } from './config.js'
import { mockService } from './mock.js'
import { wechatAuth } from './wechat-auth.js'
const adapters = Object.assign(Object.create(null), { login: binding => wechatAuth.login(binding) })
export function registerApiAdapters(implementations) { Object.assign(adapters, implementations) }
export function callApiAdapter(method, ...args) {
  if (typeof adapters[method] !== 'function') return Promise.reject(Object.assign(new Error('服务暂不可用，请稍后重试'), { code: 'ADAPTER_NOT_READY' }))
  return adapters[method](...args)
}
// Explicit adapters prevent an unconfigured API environment from falling back to demo transactions.
export const service = new Proxy({}, {
  get(_, method) { return isMockMode ? mockService[method] : (...args) => callApiAdapter(method, ...args) },
})
