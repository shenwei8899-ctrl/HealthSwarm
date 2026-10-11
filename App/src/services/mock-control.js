import { requireMock } from './config.js'
import { storageContext as storageScope } from './storage.js'
const failures = new Map()
// Tests can inject one failure without exposing development controls in product menus.
export function failNextMock(operation, message = '网络暂不可用，请重试') { failures.set(operation, message) }
export async function mockDelay(operation, duration = 180) {
  requireMock()
  const scope = storageScope()
  const failure = failures.get(operation)
  failures.delete(operation)
  await new Promise(resolve => setTimeout(resolve, duration))
  if (scope !== storageScope()) throw Object.assign(new Error('账号已切换，请重新操作'), { code: 'SESSION_CHANGED' })
  if (failure) throw new Error(failure)
}
