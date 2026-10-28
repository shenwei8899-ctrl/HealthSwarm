import { storageContext } from './storage.js'
// Each event channel belongs to its opener. Purchases do not share address state.
export function openAddressPicker({ selectedId = '', onSelected, onCancel } = {}) {
  const owner = storageContext()
  uni.navigateTo({
    url: '/pages/address/index?mode=select&selectedId=' + encodeURIComponent(selectedId || ''),
    events: { addressSelected(result) { if (owner === storageContext() && result?.id) onSelected?.(String(result.id)) } },
    fail() { if (owner === storageContext()) onCancel?.() },
  })
}
export function openAddressEditor({ id = '', mode = 'manage', onSaved, onRemoved } = {}) {
  const owner = storageContext()
  uni.navigateTo({
    url: '/pages/address/edit?mode=' + (mode === 'select' ? 'select' : 'manage') + (id ? '&id=' + encodeURIComponent(id) : ''),
    events: {
      addressSaved(result) { if (owner === storageContext() && result?.id) onSaved?.(result) },
      addressRemoved(result) { if (owner === storageContext()) onRemoved?.(result) },
    },
  })
}
export function openerChannel(instance) { return instance?.proxy?.getOpenerEventChannel?.() || instance?.proxy?.$scope?.getOpenerEventChannel?.() }
export function addressBack(delta = 1) { uni.navigateBack({ delta: typeof delta === 'number' ? delta : 1, fail: () => uni.reLaunch({ url: '/pages/my/index' }) }) }
