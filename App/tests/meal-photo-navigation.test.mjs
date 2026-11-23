import test from 'node:test'
import assert from 'node:assert/strict'
import { createMealPhotoNavigation } from '../src/services/meal-photo-navigation.js'
import { captureUiKey } from '../src/services/meal-record-entry.js'

test('opaque navigation persists one scoped editor and carries no personal fields in URL',()=>{
 let account='A',url
 const cache=new Map(),copy=v=>v==null?v:structuredClone(v)
 const storage={getStorageSync:k=>copy(cache.get(account+k)),setStorageSync:(k,v)=>cache.set(account+k,copy(v))}
 const nav=createMealPhotoNavigation(storage,()=> 'opaque-token')
 const entry={key:'dish-entry',dishes:[{name:'土豆蒸菜'}],sourceContext:{family_id:'family'}}
 const ui={people:[{memberId:'self',grams:'125'}],time:'18:25'}
 nav.open(entry,ui,o=>url=o.url)
 assert.equal(url,'/pages/scan/index?captureNavigation=opaque-token')
 assert.deepEqual(nav.read('opaque-token'),entry)
 assert.deepEqual(storage.getStorageSync(captureUiKey(entry.key)),ui)
 account='B';assert.equal(nav.read('opaque-token'),null)
 account='A';storage.setStorageSync(captureUiKey(entry.key),null);assert.equal(nav.read('opaque-token'),null)
 assert.equal(nav.read('../invalid'),null)
})
