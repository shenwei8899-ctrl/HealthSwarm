import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { ref, computed } from 'vue'
import { createFamilyCardTransition, restrictionProgress, memberHealthSummary } from '../src/utils/family-card-transition.js'

const people = () => [{ id: 'self', name: '我', weight: 58, goals: ['饮食均衡'] }, { id: 'mother', name: '妈妈', weight: 56 }, { id: 'father', name: '爸爸', weight: 70 }]
function fixture() {
 const timers = [], views = [], selected = []
 const controller = createFamilyCardTransition({ changed: value => views.push(value), settled: id => selected.push(id), schedule: (fn, delay) => { const item = { fn, delay }; timers.push(item); return item }, cancel: item => { item.cancelled = true } })
 controller.reset(people(), 'account-a/family-a', 'self')
 return { controller, timers, views, selected, get current() { return controller.current() } }
}
test('a transition preserves both member snapshots until completion', () => {
 const f = fixture(); f.controller.select('mother')
 assert.equal(f.current.from.name, '我'); assert.equal(f.current.from.weight, 58)
 assert.equal(f.current.to.name, '妈妈'); assert.equal(f.current.to.weight, 56)
 assert.equal(f.current.busy, true); assert.deepEqual(f.selected, [])
 f.controller.finish(f.current.ticket)
 assert.equal(f.current.from, null); assert.equal(f.current.to.id, 'mother'); assert.deepEqual(f.selected, ['mother'])
})
test('external changes cannot rewrite a card partway through its animation', () => {
 const f = fixture(), members = people(); f.controller.reset(members, 'same', 'self'); f.controller.select('mother')
 members[0].name = '已修改'; members[0].goals.push('新目标'); members[1].weight = 90
 assert.equal(f.current.from.name, '我'); assert.deepEqual(f.current.from.goals, ['饮食均衡']); assert.equal(f.current.to.weight, 56)
})
test('rapid choices keep only the latest pending destination', () => {
 const f = fixture(); f.controller.select('mother'); const ticket = f.current.ticket
 f.controller.select('self'); f.controller.select('father'); f.controller.finish(ticket)
 assert.equal(f.current.from.id, 'mother'); assert.equal(f.current.to.id, 'father'); assert.equal(f.current.busy, true)
 assert.deepEqual(f.selected, ['mother']); f.controller.finish(f.current.ticket); assert.deepEqual(f.selected, ['mother', 'father'])
})
test('choosing the active destination again cancels an older queued choice', () => {
 const f = fixture(); f.controller.select('mother'); f.controller.select('father'); f.controller.select('mother'); f.controller.finish(f.current.ticket)
 assert.equal(f.current.busy, false); assert.equal(f.current.to.id, 'mother')
})
test('a late completion from the previous animation cannot finish a queued animation', () => {
 const f = fixture(); f.controller.select('mother'); const old = f.current.ticket
 f.controller.select('father'); f.controller.finish(old)
 assert.equal(f.controller.finish(old), false); assert.equal(f.current.busy, true); assert.equal(f.current.to.id, 'father')
})
test('resetting the family clears both private layers and rejects old timers', () => {
 const f = fixture(); f.controller.select('mother'); const old = f.current.ticket
 f.controller.reset([{ id: 'other', name: '另一家庭' }], 'family-b', 'missing')
 f.timers[0].fn(); assert.equal(f.controller.finish(old, 'account-a/family-a'), false)
 assert.equal(f.current.from, null); assert.equal(f.current.to.name, '另一家庭'); assert.deepEqual(f.selected, [])
})
test('disposing while hidden clears health snapshots and invalidates callbacks', () => {
 const f = fixture(); f.controller.select('mother'); f.controller.dispose(); f.timers[0].fn()
 assert.equal(f.current.from, null); assert.equal(f.current.to, null); assert.equal(f.current.busy, false); assert.deepEqual(f.selected, [])
})
test('missing animation-end still settles exactly once via fallback', () => {
 const f = fixture(); f.controller.select('mother'); const ticket = f.current.ticket
 assert.ok(f.timers[0].delay > 1100); f.timers[0].fn(); f.controller.finish(ticket)
 assert.deepEqual(f.selected, ['mother']); assert.equal(f.current.busy, false)
})
test('same-member, unknown-member, empty and removed preferred member stay valid', () => {
 const f = fixture(); assert.equal(f.controller.select('self'), false); assert.equal(f.controller.select('removed'), false)
 f.controller.reset([], 'empty', 'self'); assert.equal(f.current.to, null); assert.equal(f.controller.select('self'), false)
 f.controller.reset(people().slice(1), 'same', 'removed'); assert.equal(f.current.to.id, 'mother')
})
test('switch direction follows member order in both directions', () => {
 const f = fixture(); f.controller.select('father'); assert.equal(f.current.direction, 1); f.controller.finish(f.current.ticket)
 f.controller.select('self'); assert.equal(f.current.direction, -1)
})
test('unknown and incomplete restrictions never become a no-restrictions claim', () => {
 assert.deepEqual(restrictionProgress({}), { confirmed: 0, pending: 4 })
 assert.deepEqual(restrictionProgress({ allergyStatus: 'none', intoleranceStatus: 'set', intolerances: [], avoidanceStatus: 'set', avoidances: ['坚果'], doctorStatus: 'set', clinicianGuidance: ' ' }), { confirmed: 2, pending: 2 })
 assert.deepEqual(restrictionProgress({ allergyStatus: 'none', intoleranceStatus: 'none', avoidanceStatus: 'none', doctorStatus: 'none' }), { confirmed: 4, pending: 0 })
 assert.equal(memberHealthSummary({}), '基础健康信息待补充'); assert.equal(memberHealthSummary({ healthStatus: 'set', conditions: ['其他'] }), '其他情况待补充')
})

function overview() {
 const hooks = {}, pending = [], options = [], navigations = []
 let context = 'account-a/family-a/revision-1'
 const code = readFileSync(new URL('../src/components/CloudFamilyOverview.vue', import.meta.url), 'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
 const dependencies = { ref, computed, onMounted: fn => { hooks.mounted = fn }, onUnmounted: fn => { hooks.unmounted = fn }, onShow: fn => { hooks.show = fn }, onHide: fn => { hooks.hide = fn }, onBackPress(){}, storageContext: () => context, getSession: () => ({ householdId: 'family-a' }), uni: { navigateTo: value => navigations.push(value) }, loadCloudProfile: value => { options.push(value); return new Promise((resolve, reject) => pending.push({ resolve, reject })) } }
 const exposed = new Function('deps', `const {${Object.keys(dependencies)}}=deps;${code};return {load,select,detail,profile,profileContext,selectedId,error,sheetId,sheetSection,updateSaved}`)(dependencies)
 const data = () => ({ householdId: 'family-a', selfMemberId: 'self', isOwner: true, members: people() })
 return { ...exposed, hooks, pending, options, navigations, data, changeContext: value => { context = value } }
}
test('returning to the same family restores selection after reading fresh facts', async () => {
 const f = overview(); const first = f.load(); f.pending[0].resolve(f.data()); await first
 f.select('mother'); f.hooks.hide(); assert.equal(f.profile.value, null)
 const next = f.load(); const data = f.data(); data.members[1].weight = 57; f.pending[1].resolve(data); await next
 assert.equal(f.selectedId.value, 'mother'); assert.equal(f.profile.value.members[1].weight, 57)
 assert.deepEqual(f.options, [{ openConsultation: false, readConfiguration: false }, { openConsultation: false, readConfiguration: false }])
})
test('a removed selected member falls back to the available self after return', async () => {
 const f = overview(); const a = f.load(); f.pending[0].resolve(f.data()); await a; f.select('mother'); f.hooks.hide()
 const b = f.load(); const data = f.data(); data.members = [data.members[0]]; f.pending[1].resolve(data); await b
 assert.equal(f.selectedId.value, 'self')
})
test('late success after hiding cannot restore private card data', async () => {
 const f = overview(); const p = f.load(); f.hooks.hide(); f.pending[0].resolve(f.data()); await p
 assert.equal(f.profile.value, null)
})
test('a changed account revision blocks both late data and stale detail entry', async () => {
 const f = overview(); const p = f.load(); f.changeContext('account-b/family-a/revision-2'); f.pending[0].resolve(f.data()); await p
 assert.equal(f.profile.value, null); assert.match(f.error.value, /账号或家庭已变化/); f.detail({ id: 'self' }); assert.deepEqual(f.navigations, [])
})
test('read failure permits retry without fabricating member cards', async () => {
 const f = overview(); const p = f.load(); f.pending[0].reject(new Error('请求超时，请重试')); await p
 assert.equal(f.profile.value, null); assert.match(f.error.value, /请求超时/)
 const retry = f.load(); f.pending[1].resolve(f.data()); await retry; assert.equal(f.profile.value.members.length, 3); assert.equal(f.error.value, '')
})
test('summary links open the requested member and category in a sheet without navigating', async () => {
 const f = overview(); const p = f.load(); f.pending[0].resolve(f.data()); await p
 f.detail(f.data().members[1], 'restrictions')
 assert.equal(f.sheetId.value,'mother');assert.equal(f.sheetSection.value,'restrictions');assert.equal(f.navigations.length,0)
})
