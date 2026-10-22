import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { ref, reactive, computed, nextTick, watch, effectScope } from 'vue'
import { newMember, normalizeMember, normalizeProfile } from '../src/utils/profile.js'
import { dataWarnings } from '../src/utils/health.js'
import * as health from '../src/utils/health.js'
import { onboardingIssue } from '../src/utils/onboarding-validation.js'

function completeMember(id = 'self') {
  return { ...newMember(0), id, name: id, relation: id === 'self' ? '本人' : '家人', birthDate: '1995-01-01',
    healthStatus: 'none', goals: ['饮食均衡'], tastePreferences: ['不限口味'], cuisines: ['不限菜系'],
    allergyStatus: 'none', intoleranceStatus: 'none', avoidanceStatus: 'none', doctorStatus: 'none' }
}

function page(members = [completeMember()], extras = {}) {
  const storage = new Map([['family-profile-v2', true]]), calls = { saves: [], redirects: [], toasts: [] }
  const profile = normalizeProfile({ householdId: 'synthetic-family', familyVersion: 1, usageMode: '家庭使用', members,
    defaultDiners: [members[0].id], goals: [], tastes: [] })
  const deps = { ref, computed, nextTick, watch, newMember, normalizeMember, normalizeProfile, dataWarnings, onboardingIssue,
    isMockMode: false, getProfile: () => structuredClone(profile), saveProfile() {}, backHome() {}, sessionRevision: () => 1, storageScope: () => '',
    scopedStorage: { getStorageSync: key => storage.get(key), setStorageSync: (key, value) => storage.set(key, value) },
    onLoad() {}, onShow() {}, onUnload() {}, loadCloudProfile: async () => profile, readCloudReportStatus: async () => 'empty',
    saveCloudProfile: async value => { calls.saves.push(JSON.parse(JSON.stringify(value))); return { ...value, onboarded: true } },
    uni: { getStorageSync: key => storage.get(key), setStorageSync: (key, value) => storage.set(key, structuredClone(value)), pageScrollTo() {}, showToast: value => calls.toasts.push(value.title),
      showModal() { throw new Error('Required fields must not be bypassable through a warning modal') },
      reLaunch: value => calls.redirects.push(value.url) }, ...extras }
  const script = readFileSync(new URL('../src/pages/onboarding/index.vue', import.meta.url), 'utf8')
    .match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  const scope = effectScope()
  const value = scope.run(() => new Function('deps', `const {${Object.keys(deps).join(',')}}=deps;${script};return {profile,step,current,cloudLoaded,cloudLoading,cloudError,cloudErrorCode,recoverCloud,preserveProgress,next,mode,selectMember,readCloud};`)(deps))
  value.cloudLoaded.value = true; value.cloudLoading.value = false
  return { ...value, calls, storage, dispose: () => scope.stop() }
}

const missing = [
  ['出生日期', m => m.birthDate = '', 0],
  ['已知基础病', m => m.healthStatus = 'unknown', 1],
  ['口味偏好', m => m.tastePreferences = [], 1],
  ['菜系偏好', m => m.cuisines = [], 1],
  ['饮食目标', m => m.goals = [], 1],
  ['食物过敏', m => m.allergyStatus = 'unknown', 2],
  ['食物不耐受', m => m.intoleranceStatus = 'unknown', 2],
  ['饮食忌口', m => m.avoidanceStatus = 'unknown', 2],
  ['医生饮食要求', m => m.doctorStatus = 'unknown', 2],
]
for (const [label, mutate, step] of missing) {
  test(`formal final save rejects missing ${label} and opens its step`, async () => {
    const member = completeMember(); mutate(member)
    const p = page([member]); p.step.value = 2; p.next(); await nextTick()
    assert.equal(p.calls.saves.length, 0); assert.equal(p.calls.redirects.length, 0)
    assert.equal(p.step.value, step); assert.ok(p.calls.toasts.some(text => text.includes(label)))
    assert.notEqual(p.storage.get('frontend-onboarded-v1'), true); p.dispose()
  })
}

test('a complete explicit no-restriction profile can finish without height weight or sex', async () => {
  const p = page(); p.next(); assert.equal(p.step.value, 1)
  p.next(); assert.equal(p.step.value, 2); p.next(); await nextTick()
  assert.equal(p.calls.saves.length, 1); assert.deepEqual(p.calls.redirects, ['/pages/chat/index?from=onboarding'])
  assert.equal(p.calls.saves[0].members[0].height, ''); p.dispose()
})

for (const mutate of [
  m => { m.healthStatus = 'set'; m.conditions = [] },
  m => { m.healthStatus = 'set'; m.conditions = ['其他']; m.otherCondition = '  ' },
  m => { m.allergyStatus = 'set'; m.allergies = [] },
  m => { m.intoleranceStatus = 'set'; m.intolerances = ['  '] },
  m => { m.avoidanceStatus = 'set'; m.avoidances = [] },
  m => { m.doctorStatus = 'set'; m.clinicianGuidance = '  ' },
  m => m.birthDate = '2099-01-01',
  m => m.birthDate = '1995-02-30',
  m => m.goals = ['其他'],
]) {
  test(`specific details and valid birthday are required: ${mutate.toString()}`, async () => {
    const member = completeMember(); mutate(member)
    const p = page([member]); p.step.value = 2; p.next(); await nextTick()
    assert.equal(p.calls.saves.length, 0); assert.ok(p.calls.toasts.length); p.dispose()
  })
}

test('personal mode cannot hide an incomplete retained member at final submission', async () => {
  const relative = completeMember('relative'); relative.cuisines = []
  const p = page([completeMember(), relative]); p.mode('个人使用'); p.step.value = 2; p.next(); await nextTick()
  assert.equal(p.calls.saves.length, 0); assert.equal(p.current.value.id, 'relative')
  assert.equal(p.profile.value.usageMode, '家庭使用'); assert.equal(p.step.value, 1); p.dispose()
})

test('a restored last-step draft rechecks earlier required fields', async () => {
  const p = page(); p.step.value = 2; p.profile.value.members[0].birthDate = ''
  p.next(); await nextTick(); assert.equal(p.calls.saves.length, 0); assert.equal(p.step.value, 0); p.dispose()
})

test('onboarding conflict recovery rereads current versions and requires a new explicit save', async () => {
  let reads=0
  const fresh=normalizeProfile({householdId:'synthetic-family',familyVersion:2,usageMode:'个人使用',members:[{...completeMember(),version:2}],defaultDiners:['self']})
  const p=page([completeMember()],{loadCloudProfile:async()=>{reads++;return fresh},saveCloudProfile:async()=>{throw Object.assign(new Error('档案已更新'),{code:409})}})
  p.step.value=2;p.next();await nextTick()
  p.recoverCloud();await new Promise(resolve=>setImmediate(resolve))
  assert.equal(reads,1);assert.equal(p.profile.value.familyVersion,2)
  assert.equal(p.calls.redirects.length,0);assert.match(p.cloudError.value,/重新|核对/)
  p.dispose()
})

test('onboarding authorization loss hides the form while preserving edits in the original scope',async()=>{
  const p=page([completeMember()],{saveCloudProfile:async()=>{throw Object.assign(new Error('用途授权已变化'),{code:403})}})
  p.step.value=2;p.profile.value.members[0].name='尚未保存的合成内容';p.next();await nextTick()
  assert.equal(p.cloudLoaded.value,false);assert.deepEqual(p.profile.value.members,[])
  assert.equal(p.storage.get('frontend-onboarding-progress-v1').profile.members[0].name,'尚未保存的合成内容')
  assert.equal(p.calls.redirects.length,0);p.dispose()
})

test('an earlier onboarding read cannot replace a newer family snapshot',async()=>{
  let resolveOld,reads=0
  const fresh=normalizeProfile({householdId:'synthetic-family',familyVersion:3,members:[completeMember()],defaultDiners:['self']})
  const p=page([completeMember()],{loadCloudProfile:()=>++reads===1?new Promise(resolve=>resolveOld=resolve):Promise.resolve(fresh)})
  const old=p.readCloud();await p.readCloud()
  resolveOld({...fresh,familyVersion:1});await old
  assert.equal(p.profile.value.familyVersion,3);p.dispose()
})

test('a completed save from an old session cannot mark the new account onboarded or navigate',async()=>{
  let revision=1,resolveSave
  const p=page([completeMember()],{sessionRevision:()=>revision,saveCloudProfile:()=>new Promise(resolve=>resolveSave=resolve)})
  p.step.value=2;p.next();revision=2;resolveSave({...p.profile.value,onboarded:true});await nextTick()
  assert.equal(p.cloudLoaded.value,false);assert.equal(p.storage.has('frontend-onboarded-v1'),false)
  assert.equal(p.calls.redirects.length,0);p.dispose()
})

function component(file, member, exposed) {
  const calls = { toasts: [], saved: 0 }
  const deps = { ...health, ref, computed, isMockMode: true,
    defineProps: () => ({ member, readOnly: false }), defineEmits: () => () => calls.saved++,
    uni: { showToast: value => calls.toasts.push(value.title) } }
  const script = readFileSync(new URL('../src/components/' + file, import.meta.url), 'utf8')
    .match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  return { ...new Function('deps', `const {${Object.keys(deps).join(',')}}=deps;${script};return {${exposed}};`)(deps), calls }
}

test('lost login keeps onboarding edits in the original account scope and offers reauthentication', async () => {
  let prefix = 'account-a:family-a:'
  const p = page([completeMember()], { storageScope: () => prefix,
    saveCloudProfile: async () => { throw Object.assign(new Error('登录状态已失效，填写内容已保留'), { code: 401 }) } })
  prefix = 'guest:unassigned:'
  p.step.value = 2
  p.profile.value.members[0].name = '尚未提交的填写内容'
  p.next()
  await nextTick()
  assert.equal(p.cloudErrorCode.value, 401)
  assert.match(p.cloudError.value, /内容已保留/)
  const saved = p.storage.get('account-a:family-a:frontend-onboarding-progress-v1')
  assert.equal(saved.profile.members[0].name, '尚未提交的填写内容')
  assert.equal(p.storage.has('guest:unassigned:frontend-onboarding-progress-v1'), false)
  p.recoverCloud()
  assert.deepEqual(p.calls.redirects, ['/pages/index/index'])
  assert.equal(p.storage.get('account-a:family-a:frontend-onboarding-progress-v1').step, 2)
  p.dispose()
})

function cloudSaver(initialSession, onRequest = () => assert.fail('must not send a request')) {
  let session = initialSession, revision = 1
  const values = new Map(), requests = []
  const deps = { getSession: () => session, sessionRevision: () => revision,
    scopedStorage: { getStorageSync: key => values.get(key), setStorageSync: (key, value) => values.set(key, value) },
    newHealthRequestId: () => 'original-idempotency-key', request: async options => { requests.push(options); return onRequest(options, () => { session = null; revision++ }) } }
  const source = readFileSync(new URL('../src/services/cloud-profile.js', import.meta.url), 'utf8').replace(/^import .*$/gm, '').replace(/export /g, '')
  const methods = new Function('deps', `const {${Object.keys(deps)}}=deps;${source};return {save:saveCloudProfile,input:cloudProfileInput}`)(deps)
  return { ...methods, values, requests }
}

test('profile saving rejects a missing login or changed household before preparing a write', async () => {
  const profile = { householdId: 'family-a', members: [], defaultDiners: [] }
  for (const session of [null, { accountId: '25', householdId: 'family-a' }]) {
    const h = cloudSaver(session)
    await assert.rejects(h.save(profile), error => error.code === 401 && /重新登录/.test(error.message))
    assert.equal(h.requests.length, 0)
    assert.equal(h.values.size, 0)
  }
  const changed = cloudSaver({ token: 'verified', accountId: '25', householdId: 'family-b' })
  await assert.rejects(changed.save(profile), error => error.code === 'SESSION_CHANGED')
  assert.equal(changed.requests.length, 0)
})

test('a save 401 keeps its authentication error and original recovery receipt after the transport clears login', async () => {
  const h = cloudSaver({ token: 'expired', accountId: '25', householdId: 'family-a' }, (options, clear) => {
    clear()
    throw Object.assign(new Error('登录已过期，请重新登录'), { code: 401 })
  })
  await assert.rejects(h.save({ householdId: 'family-a', members: [], defaultDiners: [] }), error => error.code === 401)
  assert.equal(h.requests.length, 1)
  assert.equal(h.values.get('cloud-onboarding-pending').data.client_request_id, 'original-idempotency-key')
})

test('household onboarding uses the server default scope while self editing remains explicitly restricted', () => {
  const h = cloudSaver(null)
  const profile = { householdId: 'family-a', familyVersion: 1, usageMode: '家庭使用',
    members: [completeMember('self'), completeMember('relative')], defaultDiners: ['self', 'relative'] }
  const owner = h.input(profile, 'original-request-id')
  assert.equal(Object.hasOwn(owner, 'scope'), false)
  assert.equal(owner.members.length, 2)
  const self = h.input({ ...profile, isOwner: false, selfMemberId: 'self' }, 'own-request-id')
  assert.equal(self.scope, 'self')
  assert.deepEqual(self.members.map(member => member.client_ref), ['self'])
  assert.deepEqual(self.default_diners, ['self'])
})

test('health and restriction controls offer only two explicit states without choosing a default', () => {
  const member = reactive(newMember(0))
  const healthFields = component('OnboardingHealthFields.vue', member, 'healthStates')
  const fields = component('MemberFields.vue', member, 'states')
  assert.deepEqual(healthFields.healthStates.map(value => value.value), ['none', 'set'])
  assert.deepEqual(fields.states.map(value => value.v), ['none', 'set'])
  assert.equal(member.healthStatus, 'unknown'); assert.equal(member.doctorStatus, 'unknown')
})

test('restriction editor requires an explicit state and rejects an empty doctor instruction', () => {
  const member = reactive(newMember(0))
  const p = component('MemberFields.vue', member, 'open,draft,save,editor')
  p.open('doctor'); p.save(); assert.equal(p.editor.value, 'doctor'); assert.equal(p.calls.saved, 0)
  p.draft.value.doctorStatus = 'set'; p.draft.value.clinicianGuidance = '  '
  p.save(); assert.equal(p.editor.value, 'doctor'); assert.equal(p.calls.saved, 0)
  p.draft.value.clinicianGuidance = '合成测试：少盐'; p.save()
  assert.equal(p.editor.value, ''); assert.equal(member.clinicianGuidance, '合成测试：少盐'); assert.equal(p.calls.saved, 1)
})

test('restriction selections remain drafts until saved and cancellation keeps the previous answer', () => {
  for (const [type, cfg] of Object.entries(health.restrictionFields)) {
    const member = reactive(normalizeMember(newMember(0)))
    const p = component('MemberFields.vue', member, 'open,draft,save,editor,toggle')
    const initialStatus = member[cfg.status]
    p.open(type)
    p.draft.value[cfg.status] = 'none'
    assert.equal(member[cfg.status], initialStatus)
    p.save()
    assert.equal(member[cfg.status], 'none')
    assert.equal(p.editor.value, '')
    p.open(type)
    p.draft.value[cfg.status] = 'set'
    p.toggle(p.draft.value[cfg.field], cfg.items[0])
    assert.equal(member[cfg.status], 'none')
    assert.deepEqual([...member[cfg.field]], [])
    p.save()
    assert.equal(member[cfg.status], 'set')
    assert.deepEqual([...member[cfg.field]], [cfg.items[0]])
    p.open(type)
    p.toggle(p.draft.value[cfg.field], cfg.items[1])
    p.editor.value = ''
    p.open(type)
    assert.deepEqual([...p.draft.value[cfg.field]], [cfg.items[0]])
    assert.equal(p.calls.saved, 2)
  }
})

test('other health goals stay unchanged on cancellation and only selected draft values are saved', () => {
  const member = reactive(completeMember())
  const original = [...member.goals]
  const p = component('OnboardingHealthFields.vue', member, 'openExtras,draft,editor,toggle,saveExtras')
  p.openExtras('goals')
  p.toggle(p.draft.value, '补充蛋白质')
  assert.deepEqual([...member.goals], original)
  p.editor.value = ''
  p.openExtras('goals')
  assert.deepEqual([...p.draft.value], [])
  p.toggle(p.draft.value, '补充蛋白质')
  p.saveExtras()
  assert.deepEqual([...member.goals], [...original, '补充蛋白质'])
  assert.equal(p.editor.value, '')
})

test('independent cuisine and taste selectors preserve each others answers', () => {
  const member = reactive(completeMember())
  const p = component('OnboardingHealthFields.vue', member, 'openExtras,draft,custom,saveExtras,toggle')
  p.openExtras('cuisines'); p.custom.value = '合成自定义菜系'; p.saveExtras()
  assert.deepEqual([...member.cuisines], ['合成自定义菜系'])
  assert.deepEqual([...member.tastePreferences], ['不限口味'])
  p.openExtras('tastePreferences'); p.custom.value = '合成自定义口味'; p.saveExtras()
  assert.deepEqual([...member.cuisines], ['合成自定义菜系'])
  assert.deepEqual([...member.tastePreferences], ['合成自定义口味'])
  p.toggle(member.cuisines, '不限菜系'); assert.deepEqual([...member.cuisines], ['不限菜系'])
  p.toggle(member.cuisines, '粤菜'); assert.deepEqual([...member.cuisines], ['粤菜'])
})
