<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { healthVisionApi as api } from '@/apis/health_vision_api'
import { agentApi } from '@/apis/agent_api'
import { mealLabels, nutrientLabels, nutrientText } from '@/utils/healthVision'
import HealthFamilyMealPlanSnapshot from './HealthFamilyMealPlanSnapshot.vue'

const props = defineProps({
  memberId: { type: String, required: true },
  members: { type: Array, required: true },
  configuration: { type: Object, required: true },
  plan: { type: Object, required: true },
  disabled: { type: Boolean, default: false }
})
const emit = defineEmits(['saved', 'invalidated', 'busy'])
const ruleCode = ref('')
const operation = ref('swap')
const slot = ref('')
const notes = ref('')
const extraMembers = ref([])
const consents = ref({})
const profiles = ref({})
const rules = ref(null)
const attempt = ref(null)
const preview = ref(null)
const candidateId = ref('')
const confirmation = ref(null)
const working = ref(false)
const polling = ref(false)
const error = ref('')
const status = ref('')
const questions = ref([])
let epoch = 0
let disposed = false
let timer
const originalIds = computed(() => Object.keys(props.plan.members || {}).sort())
const selectedIds = computed(() =>
  [
    ...new Set([
      ...originalIds.value,
      ...(operation.value === 'participation' ? extraMembers.value : [])
    ])
  ].sort()
)
function memberName(id) {
  return props.members.find((member) => member.id === id)?.display_name || '所选成员'
}
function authorized(id) {
  const member = props.members.find((item) => item.id === id)
  return ['diet_edit', 'profile_view', 'ai_use'].every((scope) => member?.scopes?.includes(scope))
}
const canUse = computed(
  () =>
    !props.disabled &&
    props.plan.member_id === props.memberId &&
    originalIds.value.length > 0 &&
    originalIds.value.includes(props.memberId) &&
    selectedIds.value.every(authorized)
)
const busy = computed(
  () => working.value || polling.value || !!attempt.value || !!confirmation.value
)
const extraOptions = computed(() =>
  props.members
    .filter((member) => !originalIds.value.includes(member.id) && authorized(member.id))
    .map((member) => ({ value: member.id, label: member.display_name }))
)
const slots = computed(() => {
  const found = new Map()
  for (const person of Object.values(props.plan.members || {})) {
    for (const meal of person.meals || []) {
      for (const dish of meal.dishes || []) {
        if (
          Number.isInteger(dish.family_dish_index) &&
          ['breakfast', 'lunch', 'dinner'].includes(meal.meal_type)
        ) {
          const value = `${meal.meal_type}:${dish.family_dish_index}`
          found.set(value, {
            value,
            label: `${mealLabels[meal.meal_type]} · 第${dish.family_dish_index + 1}道 · ${dish.name}`
          })
        }
      }
    }
  }
  return [...found.values()]
})
const allConsented = computed(() => selectedIds.value.every((id) => consents.value[id] === true))
const sourcesReady = computed(
  () =>
    rules.value?.status === 'ready' &&
    Number.isInteger(rules.value.version) &&
    selectedIds.value.every(
      (id) => profiles.value[id]?.status === 'ready' && Number.isInteger(profiles.value[id].version)
    )
)
const canGenerate = computed(
  () =>
    canUse.value &&
    !!props.configuration.meal_plan?.available &&
    allConsented.value &&
    sourcesReady.value &&
    !!ruleCode.value.trim() &&
    (operation.value !== 'swap' || slots.value.some((item) => item.value === slot.value)) &&
    (operation.value !== 'participation' || !!notes.value.trim())
)
const selectedCandidate = computed(() =>
  preview.value?.operation === 'swap'
    ? preview.value.result.candidates?.find((item) => item.recipe_version_id === candidateId.value)
    : null
)
const previewSnapshot = computed(
  () =>
    selectedCandidate.value?.plan_snapshot ||
    (preview.value?.operation !== 'swap' ? preview.value?.result.plan_snapshot : null)
)
const canConfirm = computed(
  () =>
    canUse.value &&
    allConsented.value &&
    !working.value &&
    !polling.value &&
    !attempt.value &&
    preview.value?.result.status === 'ready' &&
    !!previewSnapshot.value &&
    (preview.value.operation === 'swap'
      ? !!selectedCandidate.value
      : !!preview.value.result.preview_hash)
)
const reasons = {
  no_eligible_candidates: '当前批准规则下没有全体成员均合格的换菜候选。',
  no_eligible_dish_candidates: '当前菜位没有全体成员均合格的候选。',
  no_eligible_plan: '当前候选组合无法通过逐人检查，请交由专业人员核对。',
  search_limit_reached: '本次组合搜索已达上限，请交由专业人员核对。',
  confirmed_profiles_or_approved_rules_required: '请补充全部参与者的有效专业档案和批准规则。',
  swap_rules_not_approved: '换菜规则尚未批准，请补充专业审核。',
  complete_profiles_and_coverage_rules_required: '专业档案或餐次覆盖规则不完整，请补充批准来源。',
  known_supported_member_portions_required: '个人计划份量缺少可核验的数据，请明确各人份量。',
  member_quality_not_passed: '参与或份量调整未通过逐人检查，原餐单保留。'
}
function live(ticket) {
  return !disposed && epoch === ticket && canUse.value
}
function reset(clearSources = true) {
  epoch++
  clearTimeout(timer)
  attempt.value = null
  preview.value = null
  candidateId.value = ''
  confirmation.value = null
  working.value = false
  polling.value = false
  questions.value = []
  status.value = ''
  error.value = ''
  if (clearSources) {
    profiles.value = {}
    rules.value = null
    consents.value = {}
  }
}
function handleFailure(exc) {
  if ([403, 404, 409, 410].includes(exc.status)) {
    reset()
    error.value = [403, 404].includes(exc.status)
      ? '成员授权或处理同意已变化，已清除家庭预览，请重新核对全体成员。'
      : '餐单、成员范围或专业来源已变化，旧预览已失效，请刷新后重新生成。'
    emit('invalidated', error.value, exc.status)
  } else if ([422, 503].includes(exc.status)) {
    reset()
    error.value =
      exc.status === 503
        ? '家庭配餐服务或专业依赖未就绪，请核对配置与全体批准来源。'
        : '请求内容无法核验，请重新核对成员、餐次和明确份量。'
  } else error.value = '操作结果未确认。请恢复状态或重试原请求。'
}
function handleRequestFailure(exc) {
  if (exc.status === 404)
    error.value = '请求或运行尚未确认，请恢复状态或重试原生成请求；当前未确认取消。'
  else if (exc.status >= 500 && exc.status <= 599)
    error.value = '请求结果未确认，已保留原请求。请恢复状态或重试原生成请求。'
  else handleFailure(exc)
}
async function loadSources() {
  if (!canUse.value || busy.value || !ruleCode.value.trim()) return
  reset()
  const ticket = epoch,
    ids = [...selectedIds.value],
    code = ruleCode.value.trim()
  working.value = true
  try {
    const [entries, rule] = await Promise.all([
      Promise.all(ids.map(async (id) => [id, await api.professionalProfile(id)])),
      api.approvedQualityRules(code)
    ])
    if (!live(ticket)) return
    profiles.value = Object.fromEntries(entries)
    rules.value = rule
    status.value = sourcesReady.value
      ? `已核对 ${ids.length} 位成员的专业档案及规则版本 ${rule.version}。`
      : '全体专业来源尚未就绪，请补充有效档案和批准规则。'
  } catch (exc) {
    if (live(ticket)) handleFailure(exc)
  } finally {
    if (live(ticket)) working.value = false
  }
}
function sameIds(actual, expected) {
  return (
    Array.isArray(actual) &&
    actual.length === expected.length &&
    [...actual].sort().every((id, index) => id === expected[index])
  )
}
function sameSelection(actual, expected) {
  return (
    actual &&
    ['plan_id', 'version', 'rule_code', 'rule_version'].every(
      (key) => actual[key] === expected[key]
    ) &&
    sameIds(
      Object.keys(actual.profile_versions || {}),
      Object.keys(expected.profile_versions).sort()
    ) &&
    Object.entries(expected.profile_versions).every(
      ([id, version]) => actual.profile_versions[id] === version
    )
  )
}
function sourcesMatch(result, pending) {
  const s = result.sources,
    selected = pending.selection
  const ids =
    pending.operation === 'participation'
      ? Object.keys(result.plan_snapshot?.members || {}).sort()
      : pending.original_ids
  return (
    ids.length > 0 &&
    ids.includes(props.memberId) &&
    ids.every((id) => pending.member_ids.includes(id)) &&
    s?.plan?.id === selected.plan_id &&
    s.plan.version === selected.version &&
    s.rules?.rule_code === selected.rule_code &&
    s.rules.version === selected.rule_version &&
    sameIds(Object.keys(s.profiles || {}), ids) &&
    ids.every((id) => s.profiles[id].version === selected.profile_versions[id]) &&
    (result.status !== 'ready' ||
      (s.rules.status === 'ready' && ids.every((id) => s.profiles[id].status === 'ready')))
  )
}
/** 家庭服务预览的参与集合须与可见快照一致，确认只复制已有逐菜分配。 */
function participationMatches(result, pending) {
  const meals = result.plan_spec?.meals
  if (
    result.plan_spec?.kind !== 'family' ||
    !Array.isArray(meals) ||
    meals.length !== 3 ||
    !sameIds(
      meals.map((meal) => meal.meal_type),
      ['breakfast', 'dinner', 'lunch']
    )
  )
    return false
  const allocated = new Set()
  for (const meal of meals) {
    if (
      !Array.isArray(meal.participant_ids) ||
      !meal.participant_ids.length ||
      !Array.isArray(meal.dishes) ||
      !meal.dishes.length
    )
      return false
    const participants = new Set()
    for (const dish of meal.dishes) {
      if (!Array.isArray(dish.member_portions) || !dish.member_portions.length) return false
      for (const portion of dish.member_portions) {
        if (!pending.member_ids.includes(portion.member_id)) return false
        participants.add(portion.member_id)
        allocated.add(portion.member_id)
      }
    }
    if (!sameIds(meal.participant_ids, [...participants].sort())) return false
  }
  return sameIds(Object.keys(result.plan_snapshot?.members || {}), [...allocated].sort())
}
/** 完成Run必须带有效JSON回执；HTTP200错误或空输出不保留旧预览。 */
function runOutput(run) {
  try {
    if (run.error || typeof run.output !== 'string' || !run.output.trim())
      throw Error('missing output')
    const value = JSON.parse(run.output)
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw Error('invalid output')
    return value
  } catch {
    throw Object.assign(Error('receipt invalidated'), { status: 410 })
  }
}
async function generate() {
  if (!canUse.value || working.value || polling.value || confirmation.value) return
  if (!attempt.value) {
    if (!canGenerate.value) return
    reset(false)
    const [meal_type, index] = slot.value.split(':')
    const query =
      operation.value === 'swap'
        ? `请为当前家庭餐单的${mealLabels[meal_type]}第${Number(index) + 1}道共同菜提供安全换菜候选。`
        : operation.value === 'regeneration'
          ? '请为当前家庭餐单重新生成安全三餐预览。'
          : '请调整当前家庭餐单的参加成员和份量。'
    attempt.value = {
      selection: {
        plan_id: props.plan.plan_id,
        version: props.plan.version,
        rule_code: ruleCode.value.trim(),
        rule_version: rules.value.version,
        profile_versions: Object.fromEntries(
          selectedIds.value.map((id) => [id, profiles.value[id].version])
        )
      },
      operation: operation.value,
      meal_type,
      dish_index: Number(index),
      member_ids: [...selectedIds.value],
      original_ids: [...originalIds.value],
      binding_id: crypto.randomUUID(),
      request_id: crypto.randomUUID(),
      thread_id: null,
      processor: props.configuration.meal_plan.processor,
      policy_version: props.configuration.policy_version,
      query:
        `${query}\n已选定处理范围：${selectedIds.value.map((id) => `${memberName(id)}（ID:${id}）`).join('、')}` +
        (notes.value.trim() ? `\n补充要求：${notes.value.trim()}` : '')
    }
  }
  const ticket = epoch,
    pending = attempt.value
  working.value = true
  error.value = ''
  status.value = '正在提交家庭配餐请求…'
  let requesting = false,
    bindingSent = false
  try {
    if (!pending.thread_id) {
      for (const id of pending.member_ids) {
        await api.consent(id, {
          purpose: 'meal_plan',
          accepted: true,
          processor: pending.processor,
          policy_version: pending.policy_version
        })
        if (!live(ticket)) return
      }
      bindingSent = true
      const binding = await api.createFamilyMealPlanner(props.memberId, {
        ...pending.selection,
        client_request_id: pending.binding_id
      })
      if (!live(ticket)) return
      if (
        binding.member_id !== props.memberId ||
        binding.agent_slug !== 'health-meal-planner' ||
        !binding.thread_id ||
        !sameSelection(binding.family_selection, pending.selection)
      )
        throw Error('binding mismatch')
      pending.thread_id = binding.thread_id
    }
    requesting = true
    await agentApi.createAgentRun({
      agent_slug: 'health-meal-planner',
      thread_id: pending.thread_id,
      query: pending.query,
      meta: { request_id: pending.request_id }
    })
    if (!live(ticket)) return
    working.value = false
    await poll()
  } catch (exc) {
    if (live(ticket)) {
      if (requesting || (bindingSent && exc.status >= 500 && exc.status <= 599))
        handleRequestFailure(exc)
      else handleFailure(exc)
    }
  } finally {
    if (live(ticket)) working.value = false
  }
}
async function poll() {
  const pending = attempt.value
  if (!canUse.value || !pending?.thread_id || working.value || polling.value) return
  const ticket = epoch
  clearTimeout(timer)
  polling.value = true
  error.value = ''
  try {
    const { request } = await agentApi.getRequest(pending.request_id)
    if (!live(ticket)) return
    if (request.request_id !== pending.request_id || request.thread_id !== pending.thread_id)
      throw Error('request mismatch')
    if (['failed', 'cancelled', 'rejected'].includes(request.status)) {
      attempt.value = null
      status.value = '本次请求未完成，可重新生成。'
      return
    }
    if (request.dispatched_run_id) {
      const run = await agentApi.getAgentRunResult(request.dispatched_run_id)
      if (!live(ticket)) return
      if (run.error) throw Object.assign(Error('run unavailable'), { status: 410 })
      if (
        run.agent_run_id !== request.dispatched_run_id ||
        run.request_id !== pending.request_id ||
        run.thread_id !== pending.thread_id ||
        run.agent_slug !== 'health-meal-planner'
      )
        throw Error('run mismatch')
      if (run.status === 'completed') {
        const output = runOutput(run)
        if (
          output.scope !== 'family_saved_plan' ||
          output.member_id !== props.memberId ||
          !sameIds(output.member_ids, pending.member_ids)
        )
          throw Error('output mismatch')
        if (output.status === 'needs_input' && Array.isArray(output.questions)) {
          questions.value = output.questions.filter((q) => typeof q === 'string')
          status.value = '需要补充信息，请核对后重新生成。'
        } else {
          const r = output.result
          if (
            !output.preview_id ||
            output.operation !== pending.operation ||
            !r ||
            !sourcesMatch(r, pending) ||
            (pending.operation === 'participation' && !participationMatches(r, pending)) ||
            (pending.operation === 'swap' &&
              (r.meal_type !== pending.meal_type ||
                r.dish_index !== pending.dish_index ||
                !Array.isArray(r.candidates)))
          )
            throw Error('preview mismatch')
          preview.value = {
            ...output,
            selection: pending.selection,
            authority: {
              run_id: run.agent_run_id,
              request_id: run.request_id,
              thread_id: run.thread_id
            }
          }
          candidateId.value = ''
          status.value = '已生成家庭预览。请逐人核对参加餐次和份量，明确确认后保存。'
        }
        attempt.value = null
        return
      }
      if (['failed', 'cancelled', 'interrupted'].includes(run.status)) {
        attempt.value = null
        status.value = '本次运行未完成，可重新生成。'
        return
      }
    }
    status.value = '家庭配餐处理中…'
    timer = setTimeout(() => void poll(), 2000)
  } catch (exc) {
    if (live(ticket)) handleRequestFailure(exc)
  } finally {
    if (live(ticket)) polling.value = false
  }
}
async function confirm() {
  if (!canUse.value || working.value || polling.value || (!confirmation.value && !canConfirm.value))
    return
  const ticket = epoch,
    p = preview.value
  let pending = confirmation.value
  if (!pending) {
    const { plan_id, profile_versions, ...selection } = p.selection
    const data = {
      ...selection,
      profile_versions: Object.fromEntries(
        Object.keys(p.result.sources.profiles).map((id) => [id, profile_versions[id]])
      ),
      client_request_id: crypto.randomUUID(),
      ...(p.operation === 'swap'
        ? {
            meal_type: p.result.meal_type,
            dish_index: p.result.dish_index,
            recipe_version_id: selectedCandidate.value.recipe_version_id
          }
        : { preview_hash: p.result.preview_hash })
    }
    if (p.operation === 'participation') {
      data.allocations = p.result.plan_spec.meals.map((meal) => ({
        meal_type: meal.meal_type,
        participant_ids: [...meal.participant_ids],
        dishes: meal.dishes.map((dish, dish_index) => ({
          dish_index,
          member_portions: JSON.parse(JSON.stringify(dish.member_portions))
        }))
      }))
      data.reason = '用户明确确认家庭参与成员与计划份量调整'
    }
    pending = { plan_id, operation: p.operation, data }
  }
  working.value = true
  error.value = ''
  let callingBusiness = false
  try {
    // 首次写入前重验同Run全量回执；未知业务写入按原包原键恢复。
    if (!confirmation.value) {
      const run = await agentApi.getAgentRunResult(p.authority.run_id)
      if (!live(ticket)) return
      const latest = run.status === 'completed' ? runOutput(run) : null
      if (
        run.agent_run_id !== p.authority.run_id ||
        run.request_id !== p.authority.request_id ||
        run.thread_id !== p.authority.thread_id ||
        run.agent_slug !== 'health-meal-planner' ||
        latest?.preview_id !== p.preview_id ||
        latest.scope !== p.scope ||
        latest.member_id !== props.memberId ||
        !sameIds(latest.member_ids, p.member_ids) ||
        latest.operation !== p.operation ||
        JSON.stringify(latest.result) !== JSON.stringify(p.result)
      )
        throw Object.assign(Error('preview invalidated'), { status: 410 })
      confirmation.value = pending
    }
    const method =
      pending.operation === 'swap'
        ? api.familySafeSwapMealPlan
        : pending.operation === 'regeneration'
          ? api.familySafeRegenerateMealPlan
          : api.familyParticipationMealPlan
    callingBusiness = true
    const result = await method(pending.plan_id, pending.data)
    if (!live(ticket)) return
    if (
      result.plan_id !== pending.plan_id ||
      result.member_id !== props.memberId ||
      !result.members ||
      result.applied_version !== pending.data.version + 1 ||
      result.version < result.applied_version
    )
      throw Error('confirmation mismatch')
    reset()
    status.value = `已保存家庭版本 ${result.applied_version}，请重新进行专业审核；采用确认需另行完成。`
    emit('saved', result)
  } catch (exc) {
    if (live(ticket)) {
      // 业务写入的5xx不能证明未提交；同Run读取失败仍由依赖错误清理。
      if (callingBusiness && exc.status >= 500 && exc.status <= 599)
        error.value = '确认结果未收到，已保留原确认内容与请求。请重试原确认请求以恢复保存结果。'
      else handleFailure(exc)
    }
  } finally {
    if (live(ticket)) working.value = false
  }
}
async function cancel() {
  if (working.value || confirmation.value) return
  epoch++
  clearTimeout(timer)
  polling.value = false
  const pending = attempt.value,
    ticket = epoch
  working.value = true
  try {
    if (pending?.thread_id) {
      try {
        await agentApi.cancelRequest(pending.request_id)
      } catch (exc) {
        if (exc.status !== 409) throw exc
        const { request } = await agentApi.getRequest(pending.request_id)
        if (!live(ticket)) return
        if (request.thread_id !== pending.thread_id || request.request_id !== pending.request_id)
          throw Error('cancel mismatch', { cause: exc })
        if (request.dispatched_run_id) await agentApi.cancelAgentRun(request.dispatched_run_id)
      }
    }
    if (live(ticket)) reset(false)
  } catch (exc) {
    if (live(ticket)) handleRequestFailure(exc)
  } finally {
    if (live(ticket)) working.value = false
  }
}
watch(busy, (value) => emit('busy', value), { flush: 'sync' })
watch(
  () => [
    props.memberId,
    JSON.stringify(props.plan),
    props.members
      .map((member) => `${member.id}:${member.scopes?.join(',')}:${member.display_name}`)
      .join('|'),
    props.configuration.policy_version,
    props.configuration.meal_plan?.processor,
    props.configuration.meal_plan?.model,
    props.configuration.meal_plan?.available,
    props.disabled
  ],
  () => {
    reset()
    ruleCode.value = ''
    slot.value = ''
    notes.value = ''
    extraMembers.value = []
  },
  { flush: 'sync' }
)
watch(
  () => selectedIds.value.join(','),
  () => reset(),
  { flush: 'sync' }
)
watch(ruleCode, () => reset(), { flush: 'sync' })
watch(
  [operation, slot, notes],
  () => {
    if (!busy.value) reset(false)
  },
  { flush: 'sync' }
)
watch(
  () => allConsented.value,
  (value) => {
    if (!value) reset(false)
  },
  { flush: 'sync' }
)
onBeforeUnmount(() => {
  reset()
  disposed = true
})
</script>

<template>
  <section class="family-planner" aria-label="AI 家庭改餐">
    <h3>AI 家庭改餐</h3>
    <p class="muted">
      基于当前家庭版本 {{ plan.version }} 逐人预览。保存新版本后，原专业批准和采用状态失效。
    </p>
    <a-alert
      v-if="!canUse"
      type="info"
      message="请核对全部选定成员的饮食编辑、专业档案查看和 AI 使用授权。"
    />
    <template v-else>
      <div class="controls">
        <div>
          <label for="family-operation">改餐方式</label>
          <a-select
            id="family-operation"
            v-model:value="operation"
            :disabled="busy"
            :options="[
              { value: 'swap', label: 'AI 共同换菜' },
              { value: 'regeneration', label: '家庭三餐重新生成' },
              { value: 'participation', label: '调整参加成员与份量' }
            ]"
          />
        </div>
        <div v-if="operation === 'swap'">
          <label for="family-slot">需要更换的共同菜品</label>
          <a-select
            id="family-slot"
            v-model:value="slot"
            :options="slots"
            :disabled="busy"
            placeholder="选择家庭三餐中的一道共同菜"
          />
        </div>
        <div v-if="operation === 'participation'">
          <label for="family-extra-members">明确拟加入的成员</label>
          <a-select
            id="family-extra-members"
            v-model:value="extraMembers"
            mode="multiple"
            :options="extraOptions"
            :disabled="busy"
            placeholder="仅需加入新成员时选择"
          />
        </div>
      </div>
      <p class="muted">原参与者全部纳入本次核对；参加餐次和个人份量以最后展示的逐人预览为准。</p>
      <a-textarea
        v-model:value="notes"
        :disabled="busy"
        :rows="3"
        :maxlength="1500"
        aria-label="家庭改餐补充要求"
        placeholder="例如：将某成员早餐这道菜调整为55克，其他成员与份量保留；新增成员请明确餐次及个人份量"
      />
      <label for="family-rule-code">批准规则代码</label>
      <div class="actions">
        <a-input
          id="family-rule-code"
          v-model:value="ruleCode"
          :disabled="busy"
          :maxlength="80"
          placeholder="填写专业人员提供的已批准规则代码"
        />
        <a-button
          :disabled="busy || !ruleCode.trim()"
          :loading="working && !attempt && !confirmation"
          @click="loadSources"
          >核对全体专业来源</a-button
        >
      </div>
      <a-alert v-if="error" type="error" show-icon :message="error" />
      <p v-if="status" class="muted" role="status">{{ status }}</p>
      <a-alert
        v-if="!configuration.meal_plan?.available"
        type="info"
        :message="configuration.meal_plan?.reason || '配餐模型尚未启用，请核对服务配置。'"
      />
      <p class="muted">
        处理方：{{ configuration.meal_plan?.processor || '未配置' }} · 政策：{{
          configuration.policy_version || '未审批'
        }}
      </p>
      <div class="member-consents">
        <div v-for="id in selectedIds" :key="id">
          <p class="muted">
            {{ memberName(id) }} ·
            {{
              profiles[id]?.status === 'ready'
                ? `专业档案版本 ${profiles[id].version}`
                : '专业档案尚未就绪'
            }}
          </p>
          <a-checkbox v-model:checked="consents[id]" :disabled="busy"
            >同意为 {{ memberName(id) }} 使用上述配餐服务处理本次餐单与必要专业来源</a-checkbox
          >
        </div>
      </div>
      <div class="actions">
        <a-button type="primary" :disabled="!canGenerate || busy" @click="generate"
          >生成家庭预览</a-button
        >
        <template v-if="attempt">
          <a-button :disabled="working || polling" @click="generate">重试原生成请求</a-button>
          <a-button :disabled="working || polling || !attempt.thread_id" @click="poll"
            >恢复生成状态</a-button
          >
          <a-button :disabled="working" @click="cancel">停止本次请求</a-button>
        </template>
      </div>
      <ul v-if="questions.length">
        <li v-for="question in questions" :key="question">{{ question }}</li>
      </ul>
      <section v-if="preview" class="preview">
        <h4>家庭改餐预览 · 尚未保存</h4>
        <a-alert
          v-if="
            preview.result.status !== 'ready' ||
            (preview.operation === 'swap' && !preview.result.candidates.length)
          "
          type="warning"
          :message="
            reasons[preview.result.reason] ||
            '当前专业来源或规则尚不能提供合格家庭预览，请核对后重新生成。'
          "
        />
        <template v-if="preview.operation === 'swap' && preview.result.candidates.length">
          <label for="family-candidate">选择共同换菜候选</label>
          <a-select
            id="family-candidate"
            v-model:value="candidateId"
            :disabled="busy"
            placeholder="选择后逐人核对份量与营养变化"
            :options="
              preview.result.candidates.map((candidate) => ({
                value: candidate.recipe_version_id,
                label: candidate.name
              }))
            "
          />
          <div v-if="selectedCandidate" class="changes">
            <h4>所选共同菜的逐人营养变化（新菜 − 原菜）</h4>
            <div
              v-for="(difference, id) in selectedCandidate.member_nutrition_differences"
              :key="id"
            >
              <strong>{{ memberName(id) }}</strong>
              <p v-for="([label, unit], code) in nutrientLabels" :key="code">
                {{ label }}：{{ nutrientText(difference[code], unit) }}
              </p>
            </div>
          </div>
        </template>
        <template v-if="previewSnapshot">
          <div class="changes">
            <h4>逐人所列餐次计划合计：原餐单 → 预览</h4>
            <div v-for="(person, id) in previewSnapshot.members" :key="id">
              <strong>{{ memberName(id) }}</strong>
              <p v-for="([label, unit], code) in nutrientLabels" :key="code">
                {{ label }}：{{
                  nutrientText(plan.members?.[id]?.nutrition?.totals?.[code], unit)
                }}
                → {{ nutrientText(person.nutrition?.totals?.[code], unit) }}
              </p>
            </div>
          </div>
          <p v-if="preview.operation === 'participation'" class="muted">
            请核对下方每位成员实际参加的餐次与每道菜的个人计划份量。未列出的原成员不再参与本次餐单。
          </p>
          <HealthFamilyMealPlanSnapshot
            :snapshot="previewSnapshot"
            :members="members"
            rule-checked
          />
          <p class="muted">
            程序按批准规则逐人检查，此预览尚未形成专业审核决定。确认后保存新版本，原批准与采用状态将失效。
          </p>
          <a-button
            type="primary"
            :loading="working && !!confirmation"
            :disabled="!canConfirm && !confirmation"
            @click="confirm"
            >{{ confirmation ? '重试原确认请求' : '确认保存家庭新版本' }}</a-button
          >
        </template>
      </section>
    </template>
  </section>
</template>

<style scoped>
.family-planner {
  display: grid;
  gap: 12px;
  border-top: 1px solid var(--gray-150);
  padding-top: 16px;
  min-width: 0;
}
h3,
h4,
p {
  margin: 0;
}
.muted {
  color: var(--color-text-secondary);
  font-size: 13px;
  overflow-wrap: anywhere;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.actions .ant-input {
  flex: 1 1 220px;
  min-width: 0;
}
.controls {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.controls > div,
.preview,
.member-consents,
.member-consents > div,
.changes {
  display: grid;
  gap: 8px;
  min-width: 0;
}
.ant-select {
  width: 100%;
}
.preview {
  padding: 12px;
  border: 1px solid var(--gray-150);
  border-radius: 8px;
}
.changes {
  overflow-wrap: anywhere;
}
@media (max-width: 600px) {
  .controls {
    grid-template-columns: 1fr;
  }
}
</style>
