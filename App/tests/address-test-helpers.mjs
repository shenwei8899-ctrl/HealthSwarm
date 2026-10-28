import { readFileSync } from 'node:fs'
export { resolveCheckoutAddress } from '../src/services/address-model.js'
// Exercise the real channel helper with each harness's isolated scope and native API.
export function addressNavigation(storageContext, uni) {
  const code = readFileSync(new URL('../src/services/address-navigation.js', import.meta.url), 'utf8').replace(/^import .+$/gm, '').replace(/export /g, '')
  return new Function('storageContext', 'uni', code + '\nreturn {openAddressPicker}') (storageContext, uni)
}
