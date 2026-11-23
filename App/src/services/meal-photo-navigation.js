import { scopedStorage } from './storage.js'
import { newHealthRequestId } from './health-request-id.js'
import { captureUiKey } from './meal-record-entry.js'

/** 页面交接只传不透明标识；原页隐藏后不再覆盖同一份草稿。 */
export function createMealPhotoNavigation(storage = scopedStorage, newId = newHealthRequestId) {
  const key = token => 'meal-photo-navigation:' + token
  return {
    read(token) {
      if (typeof token !== 'string' || !/^[\w-]{1,80}$/.test(token)) return null
      const entry = storage.getStorageSync(key(token))
      return entry?.key && storage.getStorageSync(captureUiKey(entry.key)) ? entry : null
    },
    open(entry, ui, navigate) {
      const token = newId()
      storage.setStorageSync(captureUiKey(entry.key), ui)
      storage.setStorageSync(key(token), entry)
      navigate({ url: '/pages/scan/index?captureNavigation=' + token })
    },
  }
}
export const mealPhotoNavigation = createMealPhotoNavigation()
