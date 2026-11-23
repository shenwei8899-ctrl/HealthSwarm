import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { computed, reactive, ref } from 'vue'

function overview(errorCode = 'consent_required') {
  const calls = [], hooks = {}
  const state = reactive({ status: 'error', errorCode, error: '请确认用途', plans: [], busy: false })
  const deps = {
    ref, computed, reactive, request() {}, getSession: () => ({ householdId: 'family' }), sessionRevision: () => 1,
    startMemberAnalysis() {}, exclusivePlanState: () => state,
    createExclusivePlanClient: () => ({ open: async () => calls.push('open'), act: async action => calls.push(action), stop: () => calls.push('stop') }),
    createPlanConsent: () => ({ load: async () => calls.push('load'), accept: async () => { calls.push('accept'); return true }, stop: () => calls.push('consent-stop') }),
    onShow: fn => { hooks.show = fn }, onHide: fn => { hooks.hide = fn }, onUnload: fn => { hooks.unload = fn },
  }
  const source = readFileSync(new URL('../src/components/CloudExclusivePlans.vue', import.meta.url), 'utf8')
  const script = source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  const page = new Function('deps', `const {${Object.keys(deps)}}=deps;${script};return {open,startPlan,active,detail,cardAction}`)(deps)
  return { ...page, calls, hooks, source, state }
}

for (const code of ['consent_required', 'daily_member_consent_required', 'daily_member_sources_unavailable']) {
  test(`family plans do not create a per-member consent form after ${code}`, async () => {
    const page = overview(code)
    page.active.value = true
    await page.open()
    assert.deepEqual(page.calls, ['open'])
    assert.doesNotMatch(page.source, /@click="confirmConsent"|member\.checked|已验证监护人/)
    await page.startPlan()
    assert.deepEqual(page.calls, ['open', 'ensure'])
    page.hooks.hide()
    assert.equal(page.active.value, false)
    assert.equal(page.calls.at(-1), 'stop')
  })
}

test('leaving a plan overview before its read finishes cannot load a consent form', async () => {
  const page = overview()
  await page.open()
  assert.deepEqual(page.calls, ['open'])
})

for (const status of ['empty','stale']) test(`${status} plans can start from a tier card without the extra explanation panel`,async()=>{
 const p=overview();p.state.status=status;p.state.error='';p.active.value=true
 assert.equal(p.cardAction.value,'生成计划')
 await p.detail({tier_code:'economy'})
 assert.deepEqual(p.calls,['ensure'])
 assert.doesNotMatch(p.source,/原计划依据已变化|确认后将准备|还没有专属计划/)
 p.hooks.hide();await p.detail({tier_code:'economy'});assert.equal(p.calls.length,2)
})

for (const code of ['daily_member_sources_unavailable','daily_profile_source_unavailable','profile_coding_unavailable']) test(`${code} is an error, never a generation task`,()=>{
 const p=overview(code)
 assert.equal(p.cardAction.value,'待重试')
})

test('only an acknowledged generating group without a read error displays generating',()=>{
 const p=overview();p.state.status='generating';p.state.error='';p.state.group={group_id:'saved-task'}
 assert.equal(p.cardAction.value,'正在生成')
 p.state.error='暂时无法读取任务';assert.equal(p.cardAction.value,'待重试')
 p.state.error='';p.state.group=null;assert.notEqual(p.cardAction.value,'正在生成')
})
