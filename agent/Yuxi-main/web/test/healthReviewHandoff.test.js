import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { setImmediate } from 'node:timers/promises'
import { computed, effectScope, nextTick, reactive, ref, watch } from 'vue'
import { nutrientLabels, nutrientText } from '../src/utils/healthVision.js'
import * as Vue from 'vue'
import { compileTemplate } from 'vue/compiler-sfc'
import { handoffSourceRequestId } from '../src/utils/healthHandoff.js'

const sources = Object.fromEntries(
  await Promise.all(
    ['HealthProfessionalReview', 'HealthAgentHandoff'].map(async (name) => [
      name,
      await readFile(new URL(`../src/components/health/${name}.vue`, import.meta.url), 'utf8')
    ])
  )
)

test('handoff entry only renders for complete persisted records, never follow-up questions or feedback', async () => {
  const source = await readFile(
    new URL('../src/components/AgentMessageComponent.vue', import.meta.url),
    'utf8'
  )
  const compiled = compileTemplate({
    source: source.match(/<HealthAgentHandoff[\s\S]*?\/>/)[0],
    filename: 'AgentMessageComponent.vue',
    id: 'handoff-test',
    compilerOptions: { mode: 'function' }
  })
  assert.deepEqual(compiled.errors, [])
  const render = new Function('Vue', compiled.code)({ ...Vue, resolveComponent: (name) => name })
  const base = {
    isProcessing: false,
    displayError: false,
    agentSlug: 'health-blood-glucose',
    message: {
      id: 1,
      type: 'ai',
      message_type: 'text',
      delivery_status: 'complete',
      run_id: 'run',
      request_id: 'request'
    },
    run: { run_id: 'run', request_id: 'request', status: 'completed' },
    dietAnalysisResult: null
  }
  const shown = (value) =>
    render(
      {
        handoffRequestId: handoffSourceRequestId(
          { ...value.message, content: JSON.stringify(value.dietAnalysisResult) },
          value.run,
          value.agentSlug,
          value.isProcessing,
          value.displayError
        )
      },
      []
    ).type === 'HealthAgentHandoff'
  assert.ok(shown(base))
  for (const message of [
    { id: 'live' },
    { delivery_status: 'streaming' },
    { message_type: 'audit' },
    { isStoppedByUser: true },
    { tool_calls: [{}] },
    { request_id: 'other' },
    { run_id: 'other' }
  ])
    assert.equal(shown({ ...base, message: { ...base.message, ...message } }), false)
  for (const result of [
    null,
    { result_type: 'diet_analysis', status: 'needs_input' },
    { result_type: 'meal_feedback', status: 'saved' }
  ])
    assert.equal(
      shown({ ...base, agentSlug: 'health-diet-analyst', dietAnalysisResult: result }),
      false
    )
  assert.ok(
    shown({
      ...base,
      agentSlug: 'health-diet-analyst',
      dietAnalysisResult: {
        result_type: 'diet_analysis',
        status: 'completed',
        current_personal_targets: { status: 'ready' }
      }
    })
  )
})
const settle = async () => {
  await nextTick()
  await setImmediate()
}
const deferred = () => {
  let resolve
  const promise = new Promise((r) => {
    resolve = r
  })
  return { promise, resolve }
}
const handoff = {
  member_id: 'm',
  target_agent: 'health-consultation',
  target_purpose: 'consultation',
  source_hash: 'a'.repeat(64),
  summary: { records: [] }
}
const config = {
  policy_version: 'synthetic-v1',
  consultation: { available: true, processor: 'synthetic' }
}

function component(name, overrides = {}, options = {}) {
  const props = reactive({
    memberId: 'm',
    requestId: 'r',
    scopes: ['profile_view', 'diet_edit'],
    ...options.props
  })
  const user = reactive({ uid: 'synthetic-user' })
  const scope = effectScope()
  let cleanup
  const calls = []
  const api = {
    professionalReviews: async () => ({
      items: [{ review_id: 'case', status: 'draft' }],
      next_offset: null
    }),
    mealPlans: async () => ({ plans: [{ plan_id: 'p', version: 4 }] }),
    handoffPreview: async () => handoff,
    configuration: async () => config,
    consent: async () => {},
    ...overrides
  }
  const names =
    name === 'HealthProfessionalReview'
      ? 'rows, plans, planId, ruleCode, detail, reason, evidence, confirmed, attempt, error, plansError, inbox, load, open, check, perform, executeAttempt'
      : 'open, preview, attempt, error, agreed, working, prepare, confirm, close, indicatorText, totalText, window'
  const script = sources[name]
    .match(/<script setup>([\s\S]*?)<\/script>/)[1]
    .replace(/^import[\s\S]*?from ['"][^'"]+['"]\s*\n/gm, '')
  const factory = new Function(
    'computed',
    'onBeforeUnmount',
    'ref',
    'watch',
    'useUserStore',
    'api',
    'useRouter',
    'nutrientLabels',
    'nutrientText',
    'defineProps',
    'defineEmits',
    `${script}\nreturn {${names}}`
  )
  const state = scope.run(() =>
    factory(
      computed,
      (fn) => {
        cleanup = fn
      },
      ref,
      watch,
      () => user,
      api,
      () => ({ push: async (route) => calls.push(route) }),
      nutrientLabels,
      nutrientText,
      () => props,
      () => () => {}
    )
  )
  return {
    ...state,
    props,
    user,
    calls,
    dispose: () => {
      cleanup?.()
      scope.stop()
    }
  }
}

test('workbench consumes real plans response and checks selected saved version', async () => {
  const writes = []
  const p = component('HealthProfessionalReview', {
    checkMealPlan: async (id, body) => {
      writes.push({ id, body })
      return { check_id: 'check' }
    },
    qualityCheck: async () => ({ review: { review_id: 'new' } }),
    reviewWorkbench: async () => ({ review: { review_id: 'new' } })
  })
  try {
    await settle()
    assert.equal(p.plans.value.length, 1)
    p.planId.value = 'p'
    await p.check()
    assert.equal(writes.length, 0)
    // Rule choice remains explicit, so no accidental check without the supplied code.
    assert.equal(p.rows.value[0].review_id, 'case')
    p.ruleCode.value = 'synthetic-approved-rule'
    await p.check()
    assert.equal(writes.length, 1)
    assert.equal(writes[0].id, 'p')
    assert.equal(writes[0].body.version, 4)
    assert.equal(writes[0].body.rule_code, 'synthetic-approved-rule')
    assert.equal(p.detail.value.review.review_id, 'new')
  } finally {
    p.dispose()
  }
})

test('unavailable meal choices do not hide currently authorized applications', async () => {
  const p = component('HealthProfessionalReview', {
    mealPlans: async () => {
      throw Object.assign(Error('revoked family'), { status: 404 })
    }
  })
  try {
    await settle()
    assert.equal(p.rows.value.length, 1)
    assert.equal(p.plans.value.length, 0)
    assert.match(p.plansError.value, /继续处理/)
  } finally {
    p.dispose()
  }
})

test('workbench ignores late details after switching member and retries identical action', async () => {
  const delayed = deferred(),
    writes = []
  let fail = true
  const p = component('HealthProfessionalReview', {
    reviewWorkbench: async (id) =>
      id === 'late' ? delayed.promise : { review: { review_id: 'case', version: 4 } },
    reviewAction: async (id, kind, body) => {
      writes.push({ id, kind, body })
      if (fail) throw Error('lost response')
    }
  })
  try {
    await settle()
    const pending = p.open('late')
    p.props.memberId = 'new'
    await settle()
    delayed.resolve({ private: 'old member' })
    await pending
    assert.equal(p.detail.value, null)
    await p.open('case')
    p.reason.value = '合成说明'
    p.evidence.value = 'synthetic://evidence'
    p.confirmed.value = true
    await p.perform('submit')
    assert.ok(p.attempt.value)
    fail = false
    await p.executeAttempt()
    assert.deepEqual(writes[0], writes[1])
    assert.equal(p.attempt.value, null)
  } finally {
    p.dispose()
  }
})

test('handoff preview and cancel create no consent or conversation', async () => {
  let writes = 0
  const p = component('HealthAgentHandoff', {
    consent: async () => writes++,
    confirmHandoff: async () => writes++
  })
  try {
    await p.prepare()
    p.close()
    assert.equal(writes, 0)
    assert.equal(p.open.value, false)
  } finally {
    p.dispose()
  }
})

test('lost handoff response cannot be closed or replaced and replays same key', async () => {
  const writes = []
  let fail = true
  const p = component('HealthAgentHandoff', {
    confirmHandoff: async (id, body) => {
      writes.push({ id, body })
      if (fail) throw Error('lost response')
      return { member_id: 'm', agent_slug: 'health-consultation', thread_id: 'target' }
    }
  })
  try {
    await p.prepare()
    p.agreed.value = true
    await p.confirm()
    const key = p.attempt.value.client_request_id
    p.close()
    assert.equal(p.open.value, true)
    await p.prepare()
    assert.equal(p.attempt.value.client_request_id, key)
    fail = false
    await p.confirm()
    assert.deepEqual(writes[0], writes[1])
    assert.equal(p.calls.length, 1)
    assert.deepEqual(p.calls[0], { name: 'AgentCompWithThreadId', params: { thread_id: 'target' } })
    assert.equal(p.open.value, false)
  } finally {
    p.dispose()
  }
})

test('handoff ignores late old identity preview and handles withdrawn source', async () => {
  const delayed = deferred()
  const p = component('HealthAgentHandoff', {
    handoffPreview: () => delayed.promise,
    confirmHandoff: async () => {
      throw Object.assign(Error('changed'), { status: 410 })
    }
  })
  try {
    const pending = p.prepare()
    p.user.uid = 'new'
    await settle()
    delayed.resolve(handoff)
    await pending
    assert.equal(p.preview.value, null)
    await p.prepare()
    p.agreed.value = true
    await p.confirm()
    assert.equal(p.preview.value, null)
    assert.equal(p.attempt.value, null)
    assert.equal(p.calls.length, 0)
  } finally {
    p.dispose()
  }
})

test('blood lipids and period nutrition retain all values and unknowns', () => {
  const p = component('HealthAgentHandoff')
  try {
    assert.equal(
      p.indicatorText({ tc: 4.8, tg: 1.2, hdl: 1.3, ldl: 2.6, unit: 'mmol/L' }),
      'TC 4.8；TG 1.2；HDL 1.3；LDL 2.6 mmol/L'
    )
    assert.match(
      p.totalText(
        { recorded_total: null, known_sum: '300', known_records: 1, missing_records: 2 },
        'kcal'
      ),
      /已知部分 300 kcal（1 条已知，2 条缺失）/
    )
    p.preview.value = { summary: { window: { start_date: '2026-10-01', end_date: '2026-10-07' } } }
    assert.equal(p.window.value.start_date, '2026-10-01')
  } finally {
    p.dispose()
  }
})
