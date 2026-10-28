import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { ref, computed } from 'vue'
import * as model from '../src/services/address-model.js'
import { createCommerceClient } from '../src/services/commerce-client.js'
import { newMealCommerceState, createMealCommerceController } from '../src/services/meal-commerce-state.js'

const sample = { id: '1', version: 3, name: '示例收货人', phone: '13800000000', region: '湖南省 长沙市 岳麓区', area_id: 'a1', detail: '示例小区 1 栋 101 室', isDefault: true, label: '家' }
const regions = [{ id: 'p1', pid: 0, level: 1, name: '湖南省' }, { id: 'c1', pid: 'p1', level: 2, name: '长沙市' }, { id: 'a1', pid: 'c1', level: 3, name: '岳麓区' }, { id: 2, pid: 0, level: 1, name: '四川省' }, { id: 20, pid: 2, level: 2, name: '成都市' }, { id: 200, pid: 20, level: 3, name: '武侯区' }]

function formFixture({ entry = null, capabilities = { default_address: true, address_labels: true }, saveImpl } = {}) {
  let scope = 'account-A', busy = ref(false), error = ref(''), invalidator, backHandler
  const emitted = [], emitBackStates = [], calls = [], modals = []
  const api = {
    book: async () => { calls.push(['book']); return { items: entry ? [structuredClone(entry)] : [], capabilities } },
    areas: async () => regions,
    save: async payload => { calls.push(['save', structuredClone(payload)]); return saveImpl ? saveImpl(payload) : { ...payload, id: payload.id || 'new-1', version: 4 } },
    remove: async id => { calls.push(['delete', id]); return { items: [] } },
  }
  const deps = {
    ref, computed, defineProps: () => ({ addressId: entry?.id || '', mode: 'manage' }), defineEmits: () => (...args) => { emitted.push(args); emitBackStates.push(backHandler?.()) },
    onMounted() {}, onShow() {}, onBackPress(fn) { backHandler = fn }, addressApi: api, ...model,
    storageContext: () => scope, addressBack: () => calls.push(['back']),
    uni: { showToast: () => {}, pageScrollTo: () => {}, showModal: args => modals.push(args) },
    useCommercePage(clear) {
      invalidator = clear
      return { busy, error, run: async work => {
        if (busy.value) return
        const owner = scope; busy.value = true; error.value = ''
        try { await work(() => owner === scope) } catch (e) { if (owner === scope) error.value = e.message }
        finally { if (owner === scope) busy.value = false }
      } }
    },
  }
  const source = fs.readFileSync(new URL('../src/components/AddressForm.vue', import.meta.url), 'utf8').split('<script setup>')[1].split('</script>')[0].replace(/^import .+$/gm, '')
  const component = new Function(...Object.keys(deps), source + '\nreturn {form,fields,load,save,remove,back,error,loaded,pending,saved,conflict,indices,chooseRegion,columnChange,loadRegions}')(...Object.values(deps))
  return { ...component, calls, emitted, emitBackStates, modals, setScope(next) { scope = next; invalidator(); busy.value = false }, api }
}

test('payload trims contact/address, retains edit version and excludes presentation fields', () => {
  const payload = model.addressPayload({ ...sample, name: ' 示例 ', detail: ' 一栋 ', selected: true, uiError: 'x' })
  assert.equal(payload.name, '示例'); assert.equal(payload.detail, '一栋'); assert.equal(payload.version, 3)
  assert.equal(payload.selected, undefined); assert.equal(payload.uiError, undefined)
})
test('validation rejects empty contact, invalid phones, missing region and whitespace details', () => {
  assert.deepEqual(Object.keys(model.addressErrors(model.addressPayload({ name: ' ', phone: '123', detail: ' ' }))), ['name', 'phone', 'region', 'detail'])
  assert.deepEqual(model.addressErrors(model.addressPayload(sample)), {})
})
test('region recovery normalizes mixed numeric and string IDs', () => {
  assert.deepEqual(model.regionIndices(regions, '200'), [1, 0, 0])
  assert.equal(model.regionColumns(regions, [1, 0, 0])[2][0].name, '武侯区')
})
test('purchase selection has precedence over default; a deleted selection is not silently replaced', () => {
  const items = [sample, { ...sample, id: '2', isDefault: false }]
  assert.equal(model.resolveCheckoutAddress(items, '2').id, '2')
  assert.equal(model.resolveCheckoutAddress(items).id, '1')
  assert.equal(model.resolveCheckoutAddress(items, 'deleted'), null)
})
test('saving a new address uses the returned receipt without a second list request', async () => {
  const f = formFixture(); await f.load(); Object.assign(f.form.value, sample, { id: undefined })
  await f.save(); await f.save()
  assert.equal(f.calls.filter(call => call[0] === 'book').length, 1)
  assert.equal(f.calls.filter(call => call[0] === 'save').length, 1)
  assert.equal(f.emitted[0][0], 'saved'); assert.equal(f.emitted[0][1].id, 'new-1')
  assert.equal(f.emitBackStates[0], false, 'successful save must permit navigation while run() is finishing')
})
test('field validation prevents network writes and keeps typed values', async () => {
  const f = formFixture(); await f.load(); f.form.value.name = '保留姓名'; await f.save()
  assert.equal(f.form.value.name, '保留姓名'); assert.ok(f.fields.value.phone)
  assert.equal(f.calls.some(call => call[0] === 'save'), false)
})
test('legacy address APIs receive no unsupported preference fields', async () => {
  const f = formFixture({ capabilities: {} }); await f.load(); Object.assign(f.form.value, sample, { id: undefined })
  await f.save(); const payload = f.calls.find(call => call[0] === 'save')[1]
  assert.equal(Object.hasOwn(payload, 'isDefault'), false); assert.equal(Object.hasOwn(payload, 'label'), false)
})
test('unknown network result retries the identical payload and blocks creating a new request', async () => {
  let attempts = 0
  const f = formFixture({ saveImpl: payload => { if (++attempts === 1) throw Object.assign(new Error('结果未知'), { code: 'NETWORK_ERROR' }); return { ...payload, id: 'same-write' } } })
  await f.load(); Object.assign(f.form.value, sample, { id: undefined }); await f.save()
  assert.ok(f.pending.value); f.form.value.detail = 'different draft'; await f.save()
  const writes = f.calls.filter(call => call[0] === 'save'); assert.equal(writes.length, 2, JSON.stringify({ attempts, fields: f.fields.value, error: f.error.value, pending: f.pending.value, form: f.form.value })); assert.deepEqual(writes[0][1], writes[1][1])
  assert.equal(f.emitted.length, 1, JSON.stringify({ attempts, fields: f.fields.value, error: f.error.value, pending: f.pending.value }))
  assert.equal(f.emitted[0][1].id, 'same-write')
})
test('optimistic version conflict keeps the draft and requires explicit reload', async () => {
  const f = formFixture({ entry: sample, saveImpl: () => { throw Object.assign(new Error('版本冲突'), { code: 40906 }) } })
  await f.load(); f.form.value.detail = '待保留门牌号'; await f.save(); await f.save()
  assert.equal(f.conflict.value, true); assert.equal(f.form.value.detail, '待保留门牌号')
  assert.equal(f.calls.filter(call => call[0] === 'save').length, 1); assert.equal(f.emitted.length, 0)
})
test('delete requires confirmation and returns only after a successful server delete', async () => {
  const f = formFixture({ entry: sample }); await f.load(); f.remove()
  assert.equal(f.calls.some(call => call[0] === 'delete'), false)
  f.modals[0].success({ confirm: false }); assert.equal(f.emitted.length, 0)
  f.remove(); f.modals[1].success({ confirm: true }); await new Promise(resolve => setImmediate(resolve))
  assert.deepEqual(f.calls.find(call => call[0] === 'delete'), ['delete', '1'])
  assert.deepEqual(f.emitted[0], ['removed', { id: '1' }])
})
test('an account switch discards a late save receipt', async () => {
  let finish
  const f = formFixture({ saveImpl: () => new Promise(resolve => { finish = resolve }) })
  await f.load(); Object.assign(f.form.value, sample, { id: undefined }); const pending = f.save()
  f.setScope('account-B'); finish({ ...sample, id: 'late' }); await pending
  assert.equal(f.emitted.length, 0); assert.equal(f.loaded.value, false)
})
test('each address event channel only updates its own purchase and ignores old accounts', () => {
  let scope = 'A'; const navigations = [], picks = []
  const source = fs.readFileSync(new URL('../src/services/address-navigation.js', import.meta.url), 'utf8').replace(/^import .+$/gm, '').replace(/export /g, '')
  const { openAddressPicker } = new Function('storageContext', 'uni', source + '\nreturn {openAddressPicker}')(() => scope, { navigateTo: opts => navigations.push(opts) })
  openAddressPicker({ selectedId: '1', onSelected: id => picks.push(['meal', id]) })
  openAddressPicker({ selectedId: '2', onSelected: id => picks.push(['plan', id]) })
  navigations[0].events.addressSelected({ id: '3' }); assert.deepEqual(picks, [['meal', '3']])
  scope = 'B'; navigations[1].events.addressSelected({ id: '4' }); assert.equal(picks.length, 1)
})
test('default and delete client methods retain authenticated idempotent mutation behavior', async () => {
  const data = new Map(), calls = []; let key = 0
  const client = createCommerceClient({ baseUrl: 'https://example.test', parent: { scope: () => 'A', read: () => ({}) }, storage: { get: k => data.get(k), set: (k, v) => data.set(k, v) }, randomKey: () => 'key-' + ++key,
    transport: async request => { calls.push(request); return { statusCode: 200, data: { code: 0, data: {} } } } })
  data.set('fn-commerce-v1:https%3A%2F%2Fexample.test:A', { session: { token: 'synthetic', scope: 'A' } })
  await client.setDefaultAddress('a/b'); await client.deleteAddress('a/b')
  assert.equal(calls[0].method, 'PUT'); assert.ok(calls[0].url.endsWith('/addresses/a%2Fb/default'))
  assert.equal(calls[1].method, 'DELETE'); assert.ok(calls[1].url.endsWith('/addresses/a%2Fb'))
  assert.ok(calls.every(call => call.header.token === 'synthetic' && call.header['Idempotency-Key']))
})

test('a malformed address receipt retains the original idempotency key for retry', async () => {
  const data = new Map(), calls = []; let key = 0
  const client = createCommerceClient({ baseUrl: 'https://example.test', parent: { scope: () => 'A', read: () => ({}) }, storage: { get: k => data.get(k), set: (k, v) => data.set(k, v) }, randomKey: () => 'key-' + ++key,
    transport: async request => { calls.push(request); return { statusCode: 200, data: { code: 0, data: calls.length === 1 ? {} : { id: 'saved-once' } } } } })
  data.set('fn-commerce-v1:https%3A%2F%2Fexample.test:A', { session: { token: 'synthetic', scope: 'A' } })
  await assert.rejects(client.saveAddress(model.addressPayload(sample)), error => error.code === 'NETWORK_ERROR')
  assert.equal((await client.saveAddress(model.addressPayload(sample))).id, 'saved-once')
  assert.equal(calls[0].header['Idempotency-Key'], calls[1].header['Idempotency-Key'])
})

test('meal reload keeps the selected non-default address and rechecks delivery against it', async () => {
  const state = newMealCommerceState(), calls = []
  const menu = { available: true, package_sn: 'meal', package_version: 1, items: [], ingredient_requirements: [] }
  const api = { meal: async () => menu, cart: async () => ({ items: [] }), addresses: async () => [sample, { ...sample, id: '2', isDefault: false }], slots: async id => { calls.push(id); return { supported: true, items: [{ id: 'slot', available: true }] } }, pendingOrder: () => null }
  const controller = createMealCommerceController({ state, api, scope: () => 'A', context: () => ({ enabled: true, meal: 'lunch', members: [] }) })
  state.preferredAddressId = '2'; await controller.load(); await controller.load()
  assert.equal(state.address.id, '2'); assert.deepEqual(calls, ['2', '2'])
  api.addresses = async () => [sample]; await controller.load()
  assert.equal(state.address, null); assert.equal(state.quote, null)
  controller.dispose()
})

test('plan refresh retains a valid delivery slot and date, and removes an unavailable date', async () => {
  let available = true
  const events = [], deps = {
    ref, computed, onMounted() {}, onShow() {}, defineProps: () => ({ sn: 'plan', version: 1 }), defineEmits: () => (...args) => events.push(args),
    resolveCheckoutAddress: model.resolveCheckoutAddress, openAddressPicker() {},
    commerce: { addresses: async () => [sample], slots: async () => ({ supported: true, items: [{ id: 'slot', available: true }] }), planDates: async () => ({ items: available ? [{ delivery_date: '2026-11-01', first_meal_date: '2026-11-02' }] : [] }) },
    useCommercePage: () => ({ busy: ref(false), error: ref(''), run: work => work(() => true) }),
  }
  const code = fs.readFileSync(new URL('../src/components/PlanDeliveryPicker.vue', import.meta.url), 'utf8').split('<script setup>')[1].split('</script>')[0].replace(/^import .+$/gm, '')
  const p = new Function(...Object.keys(deps), code + '\nreturn {load,selectDate,date,slot}')(...Object.values(deps))
  await p.load(); p.selectDate({ detail: { value: 1 } }); await p.load()
  assert.equal(p.date.value.delivery_date, '2026-11-01'); assert.equal(p.slot.value.id, 'slot')
  assert.equal(events.at(-1)[1].first_delivery_date, '2026-11-01')
  available = false; await p.load(); assert.equal(p.date.value, undefined); assert.equal(events.at(-1)[1], null)
})

test('choosing an address emits its ID and never calls default/save APIs', async () => {
  const events = [], writes = []
  const deps = {
    ref, onMounted() {}, onShow() {}, defineProps: () => ({ mode: 'select', selectedId: '1' }), defineEmits: () => (...args) => events.push(args),
    addressApi: { book: async () => ({ items: [sample] }), setDefault: () => writes.push('default'), save: () => writes.push('save') },
    addressText: model.addressText, addressBack() {}, openAddressEditor() {}, uni: {},
    useCommercePage: () => ({ busy: ref(false), error: ref(''), run: work => work(() => true) }),
  }
  const code = fs.readFileSync(new URL('../src/components/CommerceAddresses.vue', import.meta.url), 'utf8').split('<script setup>')[1].split('</script>')[0].replace(/^import .+$/gm, '')
  const p = new Function(...Object.keys(deps), code + '\nreturn {load,choose}')(...Object.values(deps))
  await p.load(); p.choose(sample)
  assert.deepEqual(events, [['select', '1']]); assert.deepEqual(writes, [])
})

test('save-and-use relays to the original opener even while the editor is the active page', () => {
  let load, currentChannel
  const purchaseEvents = [], editorEvents = [], navigations = []
  currentChannel = { emit: (...args) => purchaseEvents.push(args) }
  const deps = {
    ref, getCurrentInstance: () => ({}), onLoad: fn => { load = fn }, onUnload() {},
    storageContext: () => 'A', openerChannel: () => currentChannel,
    addressBack: () => navigations.push('back'), isMockMode: true,
  }
  const code = fs.readFileSync(new URL('../src/pages/address/index.vue', import.meta.url), 'utf8').split('<script setup>')[1].split('</script>')[0].replace(/^import .+$/gm, '')
  const p = new Function(...Object.keys(deps), code + '\nreturn {select}')(...Object.values(deps))
  load({ mode: 'select' })
  currentChannel = { emit: (...args) => editorEvents.push(args) }
  p.select('chosen-id', true)
  assert.deepEqual(purchaseEvents, [['addressSelected', { id: 'chosen-id' }]])
  assert.deepEqual(editorEvents, []); assert.deepEqual(navigations, [])
})
