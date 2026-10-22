import test from 'node:test'
import assert from 'node:assert/strict'
import { createHealthVisionClient, visionState } from '../src/services/health-vision-client.js'
import { createHealthPlanClient, healthPlanState } from '../src/services/health-plan-client.js'
import { createHealthEventParser } from '../src/services/health-events.js'
import { mealInput } from '../src/services/health-meal-input.js'
import { uploadHealthFile } from '../src/services/request.js'

const member = '11111111-1111-4111-8111-111111111111', record = '22222222-2222-4222-8222-222222222222'
const other = '33333333-3333-4333-8333-333333333333'
const meal = { meal_type: 'lunch', eaten_at: '2026-10-16T12:00:00+08:00', items: [{ item_id: record, name: '合成食物', grams: '100', share_ratio: '1', locations: [] }] }
function setupVision(override = () => {}) {
  const state = visionState(), calls = [], stored = new Map(); let revision = 1, sequence = 0, uploads = 0
  const draft = { id: record, member_id: member, kind: 'meal', version: 1, review_status: 'pending', payload: meal }
  const client = createHealthVisionClient({ state, revision: () => revision, newId: () => `request-${++sequence}`,
    storage: { getStorageSync: key => stored.get(key), setStorageSync: (key, value) => stored.set(key, structuredClone(value)) },
    upload: async options => { uploads++; return { upload_id: 'uploaded-photo', purpose: options.purpose, status: 'ready' } },
    send: async options => {
      calls.push(structuredClone(options)); const result = await override(options); if (result) return result
      if (options.path.endsWith('/members')) return { data: [{ id: member, scopes: ['diet_edit', 'report_view'] }] }
      if (options.path.endsWith('/configuration')) return { data: { meal: { available: true, processor: 'approved-processor' }, policy_version: 'approved-policy' } }
      if (options.path.endsWith('/processing-consents')) return { data: { accepted: true } }
      if (options.path.includes('/vision/page')) return { data: { jobs: [], drafts: [], jobs_next_offset: null, drafts_next_offset: null } }
      if (options.path.endsWith('/meal-drafts/' + record)) return { data: structuredClone(draft) }
      if (options.path.endsWith('/calculate')) return { data: { calculation_id: 'calculation', draft_version: 1, complete: true, totals: { energy_kcal: '100' } } }
      if (options.path.includes('/diet-logs/page?')) return {data:{records:[{id:record,source_version:1,snapshot:{meal}}],next_offset:null}}
      throw new Error('unexpected: ' + options.path)
    } })
  return { state, client, calls, stored, uploads: () => uploads, switchAccount() { revision++ } }
}

test('meal form preserves unknowns and source evidence instead of supplying zero nutrition', () => {
  const value = mealInput({ ...meal, items: [{ ...meal.items[0], grams: '', share_ratio: '' }] })
  assert.equal(value.items[0].grams, null); assert.equal(value.items[0].share_ratio, null)
  assert.deepEqual(value.items[0].locations, []); assert.equal(value.nutrition, undefined)
})

test('uploaded files are reused and an uncertain task resumes the exact key after reopen', async () => {
  let attempts = 0
  const h = setupVision(options => {
    if (options.path.endsWith('/meal-photo-tasks')) {
      if (++attempts === 1) throw Object.assign(new Error('timeout'), { code: 'NETWORK_ERROR' })
      return { data: { task_id: 'photo-task', execution_status: 'pending' } }
    }
  })
  await h.client.open(member, 'meal'); await h.client.acceptConsent()
  const files = [{ path: 'local-photo', size: 100 }]
  await h.client.recognize(files, meal)
  assert.equal(h.uploads(), 1); assert.ok(h.state.pending)
  h.client.discard(); await h.client.open(member, 'meal'); await h.client.retryPending()
  assert.deepEqual(h.calls.filter(row => row.path.endsWith('/meal-photo-tasks'))[0], h.calls.filter(row => row.path.endsWith('/meal-photo-tasks'))[1])
  assert.equal(h.uploads(), 1); assert.equal(h.state.pending, null)
})

test('confirmation survives reopen without repeating the non-idempotent draft patch', async () => {
  let attempts = 0
  const h = setupVision(options => {
    if (options.path.endsWith('/confirm')) {
      if (++attempts === 1) throw Object.assign(new Error('lost response'), { code: 503 })
      return { data: { confirmation_id: 'receipt', target_ids: [record], review_status: 'confirmed' } }
    }
  })
  await h.client.open(member, 'meal'); await h.client.draft({ id: record }); await h.client.calculate(); await h.client.confirm(false)
  assert.ok(h.state.pending)
  h.client.discard(); await h.client.open(member, 'meal'); await h.client.retryPending()
  assert.deepEqual(h.calls.filter(row => row.path.endsWith('/confirm'))[0], h.calls.filter(row => row.path.endsWith('/confirm'))[1])
  assert.equal(h.state.confirmation.target_ids[0], record)
  assert.equal(h.calls.some(row => row.method === 'PATCH'), false)
})

test('confirmation is not shown as saved until the exact formal record has been reread',async()=>{
  let reads=0,posts=0
  const h=setupVision(options=>{
    if(options.path.endsWith('/confirm')){posts++;return {data:{confirmation_id:'receipt',target_ids:[record],review_status:'confirmed'}}}
    if(options.path.includes('/diet-logs/page?')){if(++reads===1)throw Object.assign(new Error('read lost'),{code:'NETWORK_ERROR'});return {data:{records:[{id:record,source_version:1}],next_offset:null}}}
  })
  await h.client.open(member,'meal');await h.client.draft({id:record});await h.client.calculate();await h.client.confirm(false)
  assert.equal(h.state.confirmation,null);assert.equal(h.state.pending.operation,'read')
  h.client.discard();await h.client.open(member,'meal');await h.client.retryPending()
  assert.equal(posts,1);assert.equal(h.state.records[0].id,record);assert.equal(h.state.confirmation.confirmation_id,'receipt')
})

test('report page retry freezes the draft version, selected failed page and request key',async()=>{
  let attempts=0
  const h=setupVision(options=>{
    if(options.path.endsWith('/report-extractions/'+record))return {data:{id:record,member_id:member,kind:'report',version:4,review_status:'pending_confirmation',payload:{fields:[],pages:[{page_index:1,status:'failed'}]}}}
    if(options.path.endsWith('/report-page-tasks')){if(++attempts===1)throw Object.assign(new Error('lost response'),{code:'NETWORK_ERROR'});return {data:{task_id:'retry-task'}}}
  })
  await h.client.open(member,'report');await h.client.draft({id:record});await h.client.reprocessPages([1])
  const first=h.calls.find(row=>row.path.endsWith('/report-page-tasks'));assert.equal(first.headers['If-Match'],'"4"');assert.deepEqual(first.data.page_indices,[1])
  await h.client.retryPending();assert.deepEqual(h.calls.filter(row=>row.path.endsWith('/report-page-tasks')),[first,first])
})

test('configured image limit rejects an oversized picture before upload or task creation',async()=>{
  const h=setupVision(options=>options.path.endsWith('/configuration')?{data:{meal:{available:true,processor:'processor'},policy_version:'policy',limits:{image_mb:2,meal_images:3}}}:null)
  await h.client.open(member,'meal');await h.client.acceptConsent();await h.client.recognize([{name:'picture.jpg',path:'photo',size:3*1024*1024}])
  assert.equal(h.uploads(),0);assert.match(h.state.error,/2MiB/);assert.equal(h.calls.some(row=>row.path.endsWith('/meal-photo-tasks')),false)
})

test('unknown draft patch blocks confirmation until the current candidate is reread', async () => {
  const h = setupVision(options => { if (options.method === 'PATCH') throw Object.assign(new Error('timeout'), { code: 'NETWORK_ERROR' }) })
  await h.client.open(member, 'meal'); await h.client.draft({ id: record }); await h.client.calculate()
  await h.client.saveDraft(meal, '核对原值'); await h.client.confirm(true)
  assert.equal(h.state.blocked, true); assert.equal(h.state.calculation, null)
  assert.equal(h.calls.some(row => row.path.endsWith('/confirm')), false)
  await h.client.draft({ id: record }); assert.equal(h.state.blocked, false)
})

test('private source loss clears draft and receipt while a late account response is ignored', async () => {
  let denied = false
  const h = setupVision(options => { if (options.path.includes('/meal-drafts/') && denied) throw Object.assign(new Error('denied'), { code: 410 }) })
  await h.client.open(member, 'meal'); await h.client.draft({ id: record }); denied = true
  await h.client.draft({ id: record }); assert.equal(h.state.draft, null); assert.equal(h.state.memberId, '')
  let release
  const slow = setupVision(options => options.path.endsWith('/meal-drafts/' + record) ? new Promise(resolve => { release = resolve }) : null)
  await slow.client.open(member, 'meal'); const waiting = slow.client.draft({ id: record })
  await new Promise(resolve => setImmediate(resolve)); slow.switchAccount()
  release({ data: { id: record, member_id: member, kind: 'meal', version: 1, payload: meal } }); await waiting
  assert.equal(slow.state.draft, null); assert.equal(slow.state.members.length, 0)
})

test('unavailable model does not block manual candidates or invoke recognition', async () => {
  const h = setupVision(options => {
    if (options.path.endsWith('/configuration')) return { data: { meal: { available: false } } }
    if (options.path.endsWith('/manual-drafts')) return { data: { id: record } }
  })
  await h.client.open(member, 'meal'); await h.client.manual()
  assert.equal(h.state.draft.id, record)
  assert.equal(h.calls.some(row => row.path.endsWith('/meal-photo-tasks')), false)
  assert.equal(h.calls.some(row => row.path.endsWith('/processing-consents')), false)
})

function setupPlan(override = () => {}) {
  const state = healthPlanState(), stored = new Map(), calls = []; let version = 1, revision = 1
  const plan = () => ({ plan_id: record, member_id: member, version, plan_date: '2026-10-16', meals: [] })
  const approval = () => ({ plan_id: record, version, available: true, review_id: 'review', sources: { profiles: { [member]: { version: 4 } } } })
  const client = createHealthPlanClient({ state, revision: () => revision, newId: () => 'frozen-request',
    storage: { getStorageSync: key => stored.get(key), setStorageSync: (key, value) => stored.set(key, structuredClone(value)) },
    send: async options => {
      calls.push(structuredClone(options)); const result = await override(options); if (result) return result
      if (options.path.endsWith('/members')) return { data: [{ id: member, scopes: ['diet_edit'] }] }
      if (options.path.includes('/meal-plans?')) return { data: { plans: [plan()], next_offset: null } }
      if (options.path.endsWith('/meal-plans/' + record)) return { data: plan() }
      if (options.path.includes('/approval-state?')) return { data: approval() }
      if (options.path.includes('/adopted-plan?')) return { data: { member_id: member, plan_date: '2026-10-16', status: 'not_adopted', plan: null } }
      if (options.path.endsWith('/adopt')) return { data: { adoption_id: 'adoption', plan_id: record, current: true, status: 'active' } }
      throw Error('unexpected: ' + options.path)
    } })
  return { state, client, calls, nextVersion() { version++ }, switchAccount() { revision++ } }
}

test('adoption freezes server approval and profile versions, unknown response recovers one action', async () => {
  let attempts = 0
  const h = setupPlan(options => {
    if (options.path.endsWith('/adopt')) {
      if (++attempts === 1) throw Object.assign(new Error('timeout'), { code: 'NETWORK_ERROR' })
      return { data: { adoption_id: 'adoption', plan_id: record, current: true, status: 'active' } }
    }
  })
  await h.client.open(member); await h.client.detail({ plan_id: record }); await h.client.adopt()
  assert.ok(h.state.pending)
  h.client.discard(); await h.client.open(member); await h.client.retry()
  const writes = h.calls.filter(row => row.path.endsWith('/adopt'))
  assert.deepEqual(writes[0], writes[1]); assert.deepEqual(writes[0].data.profile_versions, { [member]: 4 })
  assert.equal(writes[0].data.review_id, 'review'); assert.equal(h.state.pending, null)
})

test('changed plan version requires another explicit confirmation, with no adoption write', async () => {
  const h = setupPlan()
  await h.client.open(member); await h.client.detail({ plan_id: record }); h.nextVersion(); await h.client.adopt()
  assert.equal(h.state.plan.version, 2); assert.equal(h.calls.some(row => row.path.endsWith('/adopt')), false)
  assert.match(h.state.error, /重新核对/)
})

test('overlapping adoption requires explicit replacement and passes the exact old version', async () => {
  const old = { adoption_id: other, plan_id: 'previous', plan_version: 1, version: 3, current: true, status: 'active' }
  const h = setupPlan(options => options.path.includes('/adopted-plan?') ? { data: { member_id: member, plan_date: '2026-10-16', status: 'ready', plan: old } } : null)
  await h.client.open(member); await h.client.detail({ plan_id: record }); await h.client.adopt(false)
  assert.equal(h.calls.some(row => row.path.endsWith('/adopt')), false)
  await h.client.adopt(true)
  assert.deepEqual(h.calls.find(row => row.path.endsWith('/adopt')).data.replaces_adoptions, { [other]: 3 })
})

test('unapproved plan and expired authorization cannot cause an adoption write', async () => {
  const h = setupPlan(options => options.path.includes('/approval-state?') ? { data: { plan_id: record, version: 1, available: false, professional_review: 'returned' } } : null)
  await h.client.open(member); await h.client.detail({ plan_id: record }); await h.client.adopt()
  assert.equal(h.calls.some(row => row.path.endsWith('/adopt')), false)
  const lost = setupPlan(options => options.path.includes('/approval-state?') ? Promise.reject(Object.assign(new Error('revoked'), { code: 403 })) : null)
  await lost.client.open(member); await lost.client.detail({ plan_id: record })
  assert.equal(lost.state.plan, null); assert.equal(lost.state.members.length, 0)
})

test('an explicitly selected unavailable member never falls back to another member', async () => {
  const v = setupVision(); await v.client.open(other, 'meal')
  assert.equal(v.state.memberId, ''); assert.equal(v.calls.some(row => row.path.includes('/vision/page')), false)
  const p = setupPlan(); await p.client.open(other)
  assert.equal(p.state.memberId, ''); assert.equal(p.calls.some(row => row.path.includes('/meal-plans?')), false)
})

test('upload rejects oversize content before transport and authenticates only the current session', async () => {
  const data = new Map(), calls = []; globalThis.window = {}
  globalThis.uni = { getStorageSync: key => data.get(key), setStorageSync: (key, value) => data.set(key, value),
    uploadFile(options) { calls.push(options); options.success({ statusCode: 201, data: JSON.stringify({ upload_id: record, purpose: 'meal', status: 'ready' }) }); return {} } }
  data.set('fn-session-v2:mock', { accountId: 'test', householdId: 'test-household', token: 'synthetic-token', clientRevision: 'one' })
  try {
    await assert.rejects(uploadHealthFile({ filePath: 'local', memberId: member, purpose: 'meal', size: 11*1024*1024 }), /10MiB/)
    await assert.rejects(uploadHealthFile({ filePath: 'report.pdf', memberId: member, purpose: 'report', size: 21*1024*1024 }), /20MiB/)
    assert.equal(calls.length, 0)
    await uploadHealthFile({ filePath: 'local', memberId: member, purpose: 'meal', size: 100 })
    assert.equal(calls[0].header.Authorization, 'Bearer synthetic-token')
    assert.deepEqual(calls[0].formData, { member_id: member, purpose: 'meal' })
  } finally { delete globalThis.window; delete globalThis.uni }
})

test('upload cancellation survives a synchronous native abort failure and ignores late progress', async () => {
  const data = new Map(); let cancel, callbacks, progress, updates = 0
  globalThis.window = {}
  globalThis.uni = { getStorageSync: key => data.get(key), setStorageSync: (key, value) => data.set(key, value),
    uploadFile(options) { callbacks = options; return { abort() { options.fail({ errMsg: 'abort' }) }, onProgressUpdate(fn) { progress = fn } } } }
  data.set('fn-session-v2:mock', { accountId: 'test', householdId: 'test-household', token: 'synthetic-token', clientRevision: 'cancel' })
  try {
    const pending = uploadHealthFile({ filePath: 'local', memberId: member, purpose: 'meal', onCancelReady: fn => { cancel = fn }, onProgress: () => updates++ })
    cancel(); progress({ progress: 99 }); callbacks.success({ statusCode: 201, data: { upload_id: record, purpose: 'meal', status: 'ready' } })
    await assert.rejects(pending, error => error.code === 'UPLOAD_CANCELLED')
    assert.equal(updates, 0)
  } finally { delete globalThis.window; delete globalThis.uni }
})

test('SSE split UTF8 frames retain cursor identity but cannot expose model candidate text', () => {
  const events = [], parse = createHealthEventParser(event => events.push(event))
  const raw = new TextEncoder().encode('id: 12-1\nevent: message\ndata: {"run_id":"run","text":"不得展示的候选正文"}\n\nid: 13-0\nevent: end\ndata: {"run_id":"run"}\n\n')
  for (let i = 0; i < raw.length; i += 3) parse(raw.slice(i, i + 3).buffer)
  assert.deepEqual(events.map(row => row.id), ['12-1', '13-0'])
  assert.equal(JSON.stringify(events).includes('候选正文'), false)
})
