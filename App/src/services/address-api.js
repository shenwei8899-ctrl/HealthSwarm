import { commerce } from './commerce.js'
import { isMockMode } from './config.js'
import { mockService } from './mock.js'
import { scopedStorage } from './storage.js'
const demoKey = 'frontend-addresses-v1'
export const addressApi = {
  async book() {
    if (!isMockMode) return commerce.addressBook()
    return { items: await mockService.addresses(), capabilities: { default_address: true, address_labels: true } }
  },
  async areas() {
    if (!isMockMode) return commerce.areas()
    return [
      { id: 'p1', level: 1, pid: 0, name: '湖南省' }, { id: 'c1', level: 2, pid: 'p1', name: '长沙市' }, { id: 'a1', level: 3, pid: 'c1', name: '岳麓区' },
      { id: 'p2', level: 1, pid: 0, name: '四川省' }, { id: 'c2', level: 2, pid: 'p2', name: '成都市' }, { id: 'a2', level: 3, pid: 'c2', name: '武侯区' },
    ]
  },
  async save(data) {
    if (!isMockMode) return commerce.saveAddress(data)
    const list = await mockService.addresses(), old = list.find(item => String(item.id) === String(data.id))
    if (data.id && !old) throw new Error('地址不存在，请返回重新选择')
    if (old && Number(data.version) !== Number(old.version || 1)) throw Object.assign(new Error('地址已更新，请重新读取'), { code: 40906 })
    const saved = { ...data, id: old?.id || 'addr-' + Date.now(), version: Number(old?.version || 0) + 1, isDefault: !list.length || Boolean(data.isDefault), isDemo: true }
    const next = list.filter(item => String(item.id) !== String(saved.id)).map(item => saved.isDefault ? { ...item, isDefault: false } : item)
    next.push(saved); scopedStorage.setStorageSync(demoKey, next)
    return saved
  },
  async setDefault(id) {
    if (!isMockMode) return commerce.setDefaultAddress(id)
    const items = await mockService.addresses()
    if (!items.some(item => String(item.id) === String(id))) throw new Error('地址不存在，请刷新后重试')
    const next = items.map(item => ({ ...item, isDefault: String(item.id) === String(id) }))
    scopedStorage.setStorageSync(demoKey, next); return next.find(item => item.isDefault)
  },
  async remove(id) {
    if (!isMockMode) return commerce.deleteAddress(id)
    const items = (await mockService.addresses()).filter(item => String(item.id) !== String(id))
    if (items.length && !items.some(item => item.isDefault)) items[0].isDefault = true
    scopedStorage.setStorageSync(demoKey, items); return { items }
  },
}
