<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { healthVisionApi as api } from '@/apis/health_vision_api'
import { agentApi } from '@/apis/agent_api'
import { mealLabels, nutrientLabels, nutrientText } from '@/utils/healthVision'
import HealthMealPlanSnapshot from './HealthMealPlanSnapshot.vue'

const props = defineProps({
  memberId: { type: String, required: true },
  scopes: { type: Array, required: true },
  configuration: { type: Object, required: true },
  plan: { type: Object, required: true },
  disabled: { type: Boolean, default: false }
})
const emit = defineEmits(['saved', 'invalidated', 'busy'])
const ruleCode = ref('')
const consent = ref(false)
const operation = ref('swap')
const slot = ref('')
const notes = ref('')
const profile = ref(null)
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
const canUse = computed(
  () =>
    !props.disabled &&
    props.plan?.member_id === props.memberId &&
    !props.plan?.kind?.startsWith('family') &&
    !props.plan?.members &&
    ['diet_edit', 'profile_view', 'ai_use'].every((scope) => props.scopes.includes(scope))
)
const busy = computed(
  () => working.value || polling.value || !!attempt.value || !!confirmation.value
)
const slots = computed(() =>
  (props.plan.meals || []).flatMap((meal) =>
    ['breakfast', 'lunch', 'dinner'].includes(meal.meal_type)
      ? meal.dishes.map((dish) => ({
          value: `${meal.meal_type}:${dish.dish_index}`,
          label: `${mealLabels[meal.meal_type]} · ${dish.name}`
        }))
      : []
  )
)
const canGenerate = computed(
  () =>
    canUse.value &&
    !!props.configuration.meal_plan?.available &&
    !!consent.value &&
    profile.value?.status === 'ready' &&
    rules.value?.status === 'ready' &&
    Number.isInteger(profile.value.version) &&
    Number.isInteger(rules.value.version) &&
    !!ruleCode.value.trim() &&
    (operation.value === 'regeneration' || slots.value.some((s) => s.value === slot.value))
)
const selectedCandidate = computed(() =>
  preview.value?.operation === 'swap'
    ? preview.value.result.candidates?.find((item) => item.recipe_version_id === candidateId.value)
    : null
)
const previewSnapshot = computed(
  () =>
    selectedCandidate.value?.plan_snapshot ||
    (preview.value?.operation === 'regeneration' ? preview.value.result.plan_snapshot : null)
)
const canConfirm = computed(
  () =>
    canUse.value &&
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
  no_eligible_candidates: '当前批准规则下没有合格换菜候选，请核对规则或选择其他菜品。',
  no_eligible_dish_candidates: '当前批准目录无法为所有菜位提供合格候选。',
  no_eligible_combination: '当前候选组合无法通过全天检查，请核对目标与规则。',
  no_eligible_plan: '当前候选组合无法通过全天检查，请核对目标与规则。',
  search_budget_exhausted: '本次组合搜索已达上限，请交由专业人员核对。',
  search_limit_reached: '本次组合搜索已达上限，请交由专业人员核对。',
  confirmed_profile_or_approved_rules_required: '请先补充有效专业档案和批准规则。',
  complete_profile_and_daily_rules_required: '专业档案或全天规则不完整，请前往档案与目标补充。',
  swap_rules_not_approved: '换菜规则尚未批准，请补充专业审核。',
  current_recipe_classification_not_approved: '原菜谱分类尚未批准，请核对专业菜谱目录。',
  known_supported_portion_required: '当前菜品缺少可核验的计划份量，请先补充份量。'
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
    profile.value = null
    rules.value = null
    consent.value = false
  }
}
function handleFailure(exc) {
  if ([403, 404, 409, 410].includes(exc.status)) {
    reset()
    error.value = [403, 404].includes(exc.status)
      ? '成员授权或处理同意已变化，已清除预览，请重新核对授权。'
      : '餐单、档案、规则或菜谱来源已变化，旧预览已失效，请刷新后重新生成。'
    emit('invalidated', error.value, exc.status)
  } else if (exc.status === 503) {
    reset()
    error.value = '配餐服务或专业依赖当前未就绪，请核对服务配置与批准来源。'
  } else error.value = '操作结果未确认。请恢复状态或重试原请求。'
}
function handleRequestFailure(exc) {
  if (exc.status === 404) {
    error.value = '请求或运行尚未确认，请恢复状态或重试原生成请求；当前未确认取消。'
  } else if (exc.status >= 500 && exc.status <= 599) {
    error.value = '请求结果未确认，已保留原请求。请恢复状态或重试原生成请求。'
  } else handleFailure(exc)
}
async function loadSources() {
  if (!canUse.value || busy.value || !ruleCode.value.trim()) return
  reset()
  const ticket = epoch,
    code = ruleCode.value.trim()
  working.value = true
  try {
    const [p, r] = await Promise.all([
      api.professionalProfile(props.memberId),
      api.approvedQualityRules(code)
    ])
    if (!live(ticket)) return
    profile.value = p
    rules.value = r
    status.value =
      p.status === 'ready' && r.status === 'ready'
        ? `已核对专业档案版本 ${p.version}、规则版本 ${r.version}。`
        : '专业来源尚未就绪，请在档案与目标中补充有效档案和批准规则。'
  } catch (exc) {
    if (live(ticket)) handleFailure(exc)
  } finally {
    if (live(ticket)) working.value = false
  }
}
function sameSelection(actual, expected) {
  return (
    actual &&
    ['plan_id', 'version', 'rule_code', 'rule_version', 'profile_version'].every(
      (key) => actual[key] === expected[key]
    )
  )
}
function sourcesMatch(result, selected) {
  const s = result.sources
  return (
    s?.plan?.id === selected.plan_id &&
    s.plan.version === selected.version &&
    s.rules?.rule_code === selected.rule_code &&
    s.rules.version === selected.rule_version &&
    s.profiles?.[props.memberId]?.version === selected.profile_version &&
    Object.keys(s.profiles).length === 1 &&
    (result.status !== 'ready' ||
      (s.rules.status === 'ready' && s.profiles[props.memberId].status === 'ready'))
  )
}
async function generate() {
  if (!canUse.value || working.value || polling.value || confirmation.value) return
  if (!attempt.value) {
    if (!canGenerate.value) return
    reset(false)
    const [meal_type, index] = slot.value.split(':')
    const selected = {
      plan_id: props.plan.plan_id,
      version: props.plan.version,
      rule_code: ruleCode.value.trim(),
      rule_version: rules.value.version,
      profile_version: profile.value.version
    }
    const query =
      operation.value === 'swap'
        ? `请为当前餐单的${mealLabels[meal_type]}第${Number(index) + 1}道菜提供安全换菜候选。`
        : '请为当前餐单重新生成安全三餐预览。'
    attempt.value = {
      selection: selected,
      operation: operation.value,
      meal_type,
      dish_index: Number(index),
      binding_id: crypto.randomUUID(),
      request_id: crypto.randomUUID(),
      thread_id: null,
      processor: props.configuration.meal_plan.processor,
      policy_version: props.configuration.policy_version,
      query: query + (notes.value.trim() ? `\n补充要求：${notes.value.trim()}` : '')
    }
  }
  const ticket = epoch,
    pending = attempt.value
  working.value = true
  error.value = ''
  status.value = '正在提交安全配餐请求…'
  let requesting = false,
    bindingSent = false
  try {
    if (!pending.thread_id) {
      await api.consent(props.memberId, {
        purpose: 'meal_plan',
        accepted: true,
        processor: pending.processor,
        policy_version: pending.policy_version
      })
      if (!live(ticket)) return
      bindingSent = true
      const binding = await api.createSafeMealPlanner(props.memberId, {
        ...pending.selection,
        client_request_id: pending.binding_id
      })
      if (!live(ticket)) return
      if (
        binding.member_id !== props.memberId ||
        binding.agent_slug !== 'health-meal-planner' ||
        !binding.thread_id ||
        !sameSelection(binding.safe_selection, pending.selection)
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
      if (
        run.agent_run_id !== request.dispatched_run_id ||
        run.request_id !== pending.request_id ||
        run.thread_id !== pending.thread_id ||
        run.agent_slug !== 'health-meal-planner'
      )
        throw Error('run mismatch')
      if (run.status === 'completed') {
        const output = JSON.parse(run.output)
        if (output.scope !== 'single_member_saved_plan' || output.member_id !== props.memberId)
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
            !sourcesMatch(r, pending.selection) ||
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
          status.value = '已生成预览。请选择并明确确认后保存新版本。'
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
    status.value = '安全配餐处理中…'
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
  if (!confirmation.value) {
    const { plan_id, ...selection } = p.selection
    pending = {
      plan_id,
      operation: p.operation,
      data: {
        ...selection,
        client_request_id: crypto.randomUUID(),
        ...(p.operation === 'swap'
          ? {
              meal_type: p.result.meal_type,
              dish_index: p.result.dish_index,
              recipe_version_id: selectedCandidate.value.recipe_version_id
            }
          : { preview_hash: p.result.preview_hash })
      }
    }
  }
  working.value = true
  error.value = ''
  let callingBusiness = false
  try {
    // 首次写入前重验AI回执。未知写入响应保留原包，后续按业务幂等收据恢复。
    if (!confirmation.value) {
      const run = await agentApi.getAgentRunResult(p.authority.run_id)
      if (!live(ticket)) return
      const latest = run.status === 'completed' ? JSON.parse(run.output) : null
      if (
        run.agent_run_id !== p.authority.run_id ||
        run.request_id !== p.authority.request_id ||
        run.thread_id !== p.authority.thread_id ||
        run.agent_slug !== 'health-meal-planner' ||
        latest?.preview_id !== p.preview_id ||
        latest.scope !== p.scope ||
        latest.member_id !== props.memberId ||
        latest.operation !== p.operation ||
        JSON.stringify(latest.result) !== JSON.stringify(p.result)
      ) {
        throw Object.assign(Error('preview invalidated'), { status: 410 })
      }
      confirmation.value = pending
    }
    const method = pending.operation === 'swap' ? api.safeSwapMealPlan : api.safeRegenerateMealPlan
    callingBusiness = true
    const result = await method(pending.plan_id, pending.data)
    if (!live(ticket)) return
    if (
      result.plan_id !== pending.plan_id ||
      result.member_id !== props.memberId ||
      result.applied_version !== pending.data.version + 1 ||
      result.version < result.applied_version
    )
      throw Error('confirmation mismatch')
    reset()
    status.value = `已保存版本 ${result.applied_version}，请重新进行专业审核；采用确认需另行完成。`
    emit('saved', result)
  } catch (exc) {
    if (live(ticket)) {
      // 写入5xx不能证明未提交；首次Run重读失败仍按依赖错误处理。
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
    props.plan.plan_id,
    props.plan.version,
    props.scopes.join(','),
    props.configuration.policy_version,
    props.configuration.meal_plan?.processor,
    props.configuration.meal_plan?.available,
    props.disabled
  ],
  () => {
    reset()
    ruleCode.value = ''
    slot.value = ''
    notes.value = ''
  },
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
onBeforeUnmount(() => {
  reset()
  disposed = true
})
</script>

<template>
  <section class="safe-planner" aria-label="AI 安全改餐">
    <h3>AI 安全改餐</h3>
    <p class="muted">
      基于当前餐单版本 {{ plan.version }} 及专业来源预览；确认后保存新版本，需重新专业审核。
    </p>
    <a-alert
      v-if="!canUse"
      type="info"
      message="安全改餐需要本人餐单及饮食编辑、专业档案查看和 AI 使用授权。"
    />
    <template v-else>
      <label for="safe-rule-code">批准规则代码</label>
      <div class="actions">
        <a-input
          id="safe-rule-code"
          v-model:value="ruleCode"
          :disabled="busy"
          :maxlength="100"
          placeholder="填写专业人员提供的已批准规则代码"
        />
        <a-button
          :disabled="busy || !ruleCode.trim()"
          :loading="working && !attempt && !confirmation"
          @click="loadSources"
          >核对专业来源</a-button
        >
      </div>
      <a-alert v-if="error" type="error" show-icon :message="error" />
      <p v-if="status" class="muted" role="status">{{ status }}</p>
      <a-alert
        v-if="!configuration.meal_plan?.available"
        type="info"
        :message="configuration.meal_plan?.reason || '配餐模型尚未启用，请先核对服务配置。'"
      />
      <div class="controls">
        <div>
          <label for="safe-operation">改餐方式</label
          ><a-select
            id="safe-operation"
            v-model:value="operation"
            :disabled="busy"
            :options="[
              { value: 'swap', label: 'AI 换菜' },
              { value: 'regeneration', label: '整餐重新生成' }
            ]"
          />
        </div>
        <div v-if="operation === 'swap'">
          <label for="safe-slot">需要更换的菜品</label
          ><a-select
            id="safe-slot"
            v-model:value="slot"
            :options="slots"
            :disabled="busy"
            placeholder="选择三餐中的一道菜"
          />
        </div>
      </div>
      <a-textarea
        v-model:value="notes"
        :disabled="busy"
        :rows="2"
        :maxlength="1500"
        placeholder="补充改餐要求；疾病、过敏和营养目标以专业来源为准"
        aria-label="安全改餐补充要求"
      />
      <p class="muted">
        处理方：{{ configuration.meal_plan?.processor || '未配置' }} · 政策：{{
          configuration.policy_version || '未审批'
        }}
      </p>
      <a-checkbox v-model:checked="consent" :disabled="busy"
        >同意将本次餐单与必要专业来源交由上述配餐服务处理</a-checkbox
      >
      <div class="actions">
        <a-button type="primary" :disabled="!canGenerate || busy" @click="generate"
          >生成安全预览</a-button
        >
        <template v-if="attempt"
          ><a-button :disabled="working || polling" @click="generate">重试原生成请求</a-button
          ><a-button :disabled="working || polling || !attempt.thread_id" @click="poll"
            >恢复生成状态</a-button
          ><a-button :disabled="working" @click="cancel">停止本次请求</a-button></template
        >
      </div>
      <ul v-if="questions.length">
        <li v-for="question in questions" :key="question">{{ question }}</li>
      </ul>
      <section v-if="preview" class="preview">
        <h4>改餐预览 · 尚未保存</h4>
        <a-alert
          v-if="
            preview.result.status !== 'ready' ||
            (preview.operation === 'swap' && !preview.result.candidates.length)
          "
          type="warning"
          :message="
            reasons[preview.result.reason] ||
            '当前专业来源或规则尚不能提供合格预览，请核对后重新生成。'
          "
        />
        <template v-if="preview.operation === 'swap' && preview.result.candidates.length">
          <label for="safe-candidate">选择换菜候选</label>
          <a-select
            id="safe-candidate"
            v-model:value="candidateId"
            :disabled="busy"
            placeholder="选择后查看三餐变化"
            :options="
              preview.result.candidates.map((c) => ({
                value: c.recipe_version_id,
                label: `${c.name} · ${c.planned_grams} g`
              }))
            "
          />
          <div v-if="selectedCandidate" class="nutrition-changes">
            <h4>所选菜品营养变化（新菜 − 原菜）</h4>
            <p v-for="(label, code) in nutrientLabels" :key="code">
              {{ label[0] }}：{{
                nutrientText(selectedCandidate.nutrition_difference?.[code], label[1])
              }}
            </p>
          </div>
        </template>
        <template v-if="previewSnapshot">
          <div class="nutrition-changes">
            <h4>全天营养：原餐单 → 预览</h4>
            <p v-for="(label, code) in nutrientLabels" :key="code">
              {{ label[0] }}：{{ nutrientText(plan.nutrition?.totals?.[code], label[1]) }} →
              {{ nutrientText(previewSnapshot.nutrition?.totals?.[code], label[1]) }}
            </p>
          </div>
          <HealthMealPlanSnapshot :snapshot="previewSnapshot" rule-checked />
          <p class="muted">
            程序按批准规则完成检查；此预览尚未形成专业审核决定。保存后原批准与采用状态将失效。
          </p>
          <a-button
            type="primary"
            :loading="working && !!confirmation"
            :disabled="!canConfirm && !confirmation"
            @click="confirm"
            >{{ confirmation ? '重试原确认请求' : '确认保存新版本' }}</a-button
          >
        </template>
      </section>
    </template>
  </section>
</template>

<style scoped>
.safe-planner {
  display: grid;
  gap: 12px;
  border-top: 1px solid var(--color-border);
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
.preview {
  display: grid;
  gap: 8px;
  min-width: 0;
}
.ant-select {
  width: 100%;
}
.preview {
  padding: 12px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
}
.nutrition-changes {
  display: grid;
  gap: 4px;
  overflow-wrap: anywhere;
}
@media (max-width: 600px) {
  .controls {
    grid-template-columns: 1fr;
  }
}
</style>
