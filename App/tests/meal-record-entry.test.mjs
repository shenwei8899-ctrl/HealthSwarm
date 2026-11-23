import {createMealPhotoClient,photoState} from '../src/services/meal-photo-client.js'
import test from 'node:test'
import assert from 'node:assert/strict'
import { mealRecordEntry, captureUiKey, mealTime, sortMealRecords } from '../src/services/meal-record-entry.js'
const recipe = '11111111-1111-4111-8111-111111111111'
const target = { familyId: 'family', date: '2026-11-20', kind: 'formal', sourceId: 'saved', version: 1, mealType: 'dinner' }

test('dish entry carries one candidate and a reliable recipe version, without planned intake', () => {
 const entry = mealRecordEntry(target, { dish_key: 'egg', name: '番茄炒蛋', recipe_version_id: recipe,
  grams: 300, kcal: 600, nutrition: { energy_kcal: 600 }, memberNotes: [{ grams: 200 }] }, '/cover.png')
 assert.deepEqual(entry.dishes, [{ name: '番茄炒蛋', recipe_version_id: recipe,
  grams: null, portion_source: 'unknown', portion_confirmed: false }])
 assert.equal(entry.cover, '/cover.png')
 assert.notEqual(captureUiKey(entry.key), captureUiKey())
 assert.notEqual(entry.key, mealRecordEntry({ ...target, version: 2 }, { dish_key: 'egg', name: '番茄炒蛋' }).key)
})

test('unverified reference recipes remain unknown instead of borrowing planned nutrition', () => {
 const entry = mealRecordEntry({ ...target, kind: 'reference' }, { name: '番茄炒蛋', recipe_version_id: recipe })
 assert.equal(entry.dishes[0].recipe_version_id, null)
})

test('actual meal times use Beijing time across midnight and offsets', () => {
 assert.equal(mealTime('2026-11-20T16:30:00Z'), '00:30')
 assert.equal(mealTime('2026-11-21T18:30:00+08:00'), '18:30')
 assert.equal(mealTime('invalid'), '时间未知')
})

test('records sort by actual eating time without mutating API results or collapsing meals', () => {
 const record = (id, time) => ({ id, snapshot: { meal: { eaten_at: time } } })
 const original = [record('late', '2026-11-21T20:00:00+08:00'), record('early', '2026-11-21T18:30:00+08:00')]
 assert.deepEqual(sortMealRecords(original).map(r => r.id), ['early', 'late'])
 assert.equal(original[0].id, 'late')
})

test('photo checkpoints from distinct entries cannot reset each other or the existing photo page',()=>{
 const cache=new Map(),storage={getStorageSync:k=>cache.get(k),setStorageSync:(k,v)=>cache.set(k,v)}
 for(const key of ['', 'dish-A', 'dish-B']){
  const state=photoState();state.memberId='self'
  const client=createMealPhotoClient({state,storage,namespace:()=>key,revision:()=>1})
  assert.equal(client.resetSelection(),true)
 }
 assert.equal(cache.size,3)
 assert.ok(cache.has('meal-photo-flow:self'))
 assert.ok(cache.has('meal-photo-flow:dish-A:self'))
 assert.ok(cache.has('meal-photo-flow:dish-B:self'))
})
