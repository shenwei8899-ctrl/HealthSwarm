<script setup>
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { healthVisionApi as api } from '@/apis/health_vision_api'
import { agentApi } from '@/apis/agent_api'
import { mealLabels } from '@/utils/healthVision'

const props = defineProps({
  memberId: { type: String, required: true },
  scopes: { type: Array, required: true },
  configuration: { type: Object, required: true },
  records: { type: Array, default: () => [] },
  record: { type: Object, default: null },
  feedback: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false }
})
const emit = defineEmits(['busy'])
const router = useRouter()
const userStore = useUserStore()
const scope = ref('period')
const periodDays = ref(1)
const endDate = ref(beijingToday())
const recordId = ref('')
const comment = ref('')
const consent = ref(false)
const working = ref(false)
const error = ref('')
const attempt = ref(null)
let epoch = 0
let disposed = false
const service = computed(() => props.configuration.diet_analysis || {})
const modelName = computed(
  () =>
    props.configuration.model_options?.find((model) => model.spec === service.value.model)?.name ||
    '管理员批准的饮食分析服务'
)
const canRead = computed(() => !!props.memberId && props.scopes.includes('diet_edit'))
const canUse = computed(
  () =>
    canRead.value && props.scopes.includes('ai_use') && !!service.value.available && !props.disabled
)
const selectedRecord = computed(() =>
  props.feedback ? props.record : props.records.find((record) => record.id === recordId.value)
)
const validRecord = computed(
  () =>
    !!selectedRecord.value?.id &&
    Number.isInteger(selectedRecord.value.source_version) &&
    selectedRecord.value.source_version > 0
)
const canEnter = computed(
  () =>
    canUse.value &&
    consent.value &&
    !working.value &&
    (props.feedback
      ? validRecord.value && !!comment.value.trim()
      : scope.value === 'meal'
        ? validRecord.value
        : [1, 7, 30].includes(periodDays.value) &&
          /^\d{4}-\d{2}-\d{2}$/.test(endDate.value) &&
          endDate.value <= beijingToday())
)
const recordOptions = computed(() =>
  props.records.map((record) => ({
    value: record.id,
    label: recordLabel(record),
    disabled: !Number.isInteger(record.source_version) || record.source_version < 1
  }))
)

/** 日期选择按业务使用的北京时间自然日。 */
function beijingToday() {
  const parts = new Intl.DateTimeFormat('en', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).formatToParts(new Date())
  return ['year', 'month', 'day']
    .map((key) => parts.find((part) => part.type === key).value)
    .join('-')
}

/** 菜名与进食时间帮助用户区分真实已确认餐次。 */
function recordLabel(record) {
  const meal = record?.snapshot?.meal || {}
  const names = (meal.items || [])
    .filter((item) => !item.excluded)
    .map((item) => item.name)
    .join('、')
  return `${mealLabels[meal.meal_type] || '餐次'} · ${meal.eaten_at ? new Date(meal.eaten_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '时间未知'}${names ? ` · ${names}` : ''}`
}

/** 选择、身份或授权变化立即撤销本地同意与迟到导航。 */
function reset() {
  epoch++
  attempt.value = null
  consent.value = false
  working.value = false
  error.value = ''
}

/** 不同成员、用途和处理政策的响应不可复用。 */
function live(ticket) {
  return !disposed && epoch === ticket && canUse.value
}

/** 普通分析先用无模型接口核对来源，反馈来源另由绑定服务校验。 */
async function validateSelection(pending) {
  if (props.feedback) return
  const result = pending.selection.record_id
    ? await api.dietAnalysis(props.memberId, pending.selection)
    : await api.dietPeriodAnalysis(props.memberId, pending.selection)
  if (result.member_id !== props.memberId || result.result_type !== 'diet_analysis')
    throw Error('分析来源绑定不一致，请刷新后重试。')
  if (pending.selection.record_id) {
    if (
      result.records?.length !== 1 ||
      result.records[0].record_id !== pending.selection.record_id ||
      result.records[0].source_version !== pending.selection.source_version
    )
      throw Error('确认餐次版本不一致，请刷新记录。')
  } else if (
    result.window?.period_days !== pending.selection.period_days ||
    result.window.end_date !== pending.selection.end_date ||
    result.window.timezone !== 'Asia/Shanghai'
  )
    throw Error('分析日期范围不一致，请重新选择。')
}

/** 冻结幂等键和原文；绑定完成后才提交既有 Request/Run 主链路。 */
async function enter() {
  if (!canEnter.value) return
  if (!attempt.value) {
    const selected = selectedRecord.value
    const selection =
      props.feedback || scope.value === 'meal'
        ? { record_id: selected.id, source_version: selected.source_version }
        : { period_days: periodDays.value, end_date: endDate.value }
    attempt.value = {
      binding_id: crypto.randomUUID(),
      request_id: crypto.randomUUID(),
      thread_id: null,
      processor: service.value.processor,
      policy_version: props.configuration.policy_version,
      selection,
      query: props.feedback
        ? `记录这餐反馈：${comment.value.trim()}`
        : selection.record_id
          ? `请分析已确认餐次：record_id=${selection.record_id}，source_version=${selection.source_version}。请沿用该确认记录的营养计算事实。`
          : `请分析截至${selection.end_date}的${selection.period_days}个北京时间自然日的已确认饮食记录：period_days=${selection.period_days}，end_date=${selection.end_date}。缺失和未记录天数保持未知。`
    }
  }
  const pending = attempt.value
  const ticket = epoch
  working.value = true
  error.value = ''
  try {
    if (!pending.thread_id) {
      await validateSelection(pending)
      if (!live(ticket)) return
      await api.consent(props.memberId, {
        purpose: 'diet_analysis',
        accepted: true,
        processor: pending.processor,
        policy_version: pending.policy_version
      })
      if (!live(ticket)) return
      const binding = props.feedback
        ? await api.createFeedbackConversation(pending.selection.record_id, {
            client_request_id: pending.binding_id,
            source_version: pending.selection.source_version
          })
        : await api.createDietAnalyst(props.memberId, { client_request_id: pending.binding_id })
      if (!live(ticket)) return
      if (
        binding.member_id !== props.memberId ||
        binding.agent_slug !== 'health-diet-analyst' ||
        !binding.thread_id ||
        (props.feedback
          ? binding.feedback_selection?.record_id !== pending.selection.record_id ||
            binding.feedback_selection.source_version !== pending.selection.source_version
          : binding.feedback_selection != null)
      )
        throw Error('分析会话绑定不一致，请刷新后重试。')
      pending.thread_id = binding.thread_id
    }
    await agentApi.createAgentRun({
      agent_slug: 'health-diet-analyst',
      thread_id: pending.thread_id,
      query: pending.query,
      meta: { request_id: pending.request_id }
    })
    if (!live(ticket)) return
    await openConversation()
  } catch (exc) {
    if (!live(ticket)) return
    if ([401, 403, 404, 409, 410, 422, 503].includes(exc.status)) {
      reset()
      error.value = [401, 403, 404].includes(exc.status)
        ? '成员授权或用途同意已变化，请重新核对。'
        : [409, 410].includes(exc.status)
          ? '饮食来源、确认版本或处理政策已变化，请刷新记录后重新选择。'
          : exc.status === 503
            ? '饮食分析服务当前未就绪，请核对服务配置。'
            : exc.message
    } else
      error.value = '请求结果尚未确认，已保留原请求。可重试相同请求，或进入已创建的会话恢复状态。'
  } finally {
    if (ticket === epoch) working.value = false
  }
}

/** 对话页负责既有排队、Run SSE、恢复与当前权威结果展示。 */
async function openConversation() {
  if (!attempt.value?.thread_id || !canUse.value || disposed) return
  await router.push({
    name: 'AgentCompWithThreadId',
    params: { thread_id: attempt.value.thread_id }
  })
}

watch(working, (value) => emit('busy', value), { flush: 'sync' })
watch(
  [
    () => props.memberId,
    () => props.scopes.join('|'),
    () => userStore.uid,
    () =>
      `${service.value.available}|${service.value.processor}|${props.configuration.policy_version}`,
    () => props.feedback,
    () => `${props.record?.id}|${props.record?.source_version}`,
    () => props.records.map((record) => `${record.id}:${record.source_version}`).join('|'),
    scope,
    periodDays,
    endDate,
    recordId
  ],
  reset,
  { flush: 'sync' }
)
watch(
  () => props.memberId,
  () => {
    recordId.value = ''
    comment.value = ''
  },
  { flush: 'sync' }
)
watch(
  () => `${props.record?.id}|${props.record?.source_version}`,
  () => {
    comment.value = ''
  },
  { flush: 'sync' }
)
onBeforeUnmount(() => {
  disposed = true
  reset()
})
</script>

<template>
  <section class="analysis-entry" :class="{ 'feedback-entry': feedback }">
    <h2 v-if="!feedback">饮食分析</h2>
    <p class="hint">
      {{
        feedback
          ? '这次对话固定关联下面这一餐。明确提交后，Agent 将记录你的餐后自述，可在餐后反馈中核对或撤回。'
          : '选择已确认饮食的分析范围，再进入饮食分析师对话。统计沿用确认记录，缺失值和未记录天数保持未知。'
      }}
    </p>
    <a-alert v-if="!canRead" type="info" message="请先选择具有饮食记录访问授权的成员。" show-icon />
    <a-alert
      v-else-if="!scopes.includes('ai_use')"
      type="warning"
      message="当前成员尚未授权云 AI 处理，请先核对成员授权。"
      show-icon
    />
    <a-alert
      v-else-if="!service.available"
      type="warning"
      :message="`饮食分析未启用：${service.reason || '尚未配置饮食分析模型'}。请在服务与食品数据中核对配置。`"
      show-icon
    />
    <a-alert v-if="error" type="error" :message="error" show-icon />
    <a-form v-if="canRead" layout="vertical">
      <template v-if="feedback">
        <p class="selected-meal">{{ recordLabel(record) }}</p>
        <a-alert
          v-if="!validRecord"
          type="warning"
          message="这餐缺少可核验的确认版本，请刷新已确认记录。"
          show-icon
        />
        <a-form-item label="记录这餐的反馈">
          <a-textarea
            v-model:value="comment"
            :maxlength="493"
            :rows="3"
            :disabled="working || !!attempt || disabled"
            placeholder="例如：吃完程度：一半；口味：偏咸；自述：饭量比较大"
          />
          <p class="hint">吃完程度为自述，反馈保存不会改写原饮食记录或重新计算营养。</p>
        </a-form-item>
      </template>
      <template v-else>
        <a-form-item label="分析范围">
          <a-radio-group v-model:value="scope" :disabled="working || !!attempt || disabled">
            <a-radio-button value="period">按日期统计</a-radio-button>
            <a-radio-button value="meal">选择一餐</a-radio-button>
          </a-radio-group>
        </a-form-item>
        <div v-if="scope === 'period'" class="date-fields">
          <a-form-item label="统计天数">
            <a-select
              v-model:value="periodDays"
              :disabled="working || !!attempt || disabled"
              :options="[1, 7, 30].map((value) => ({ value, label: `${value} 天` }))"
            />
          </a-form-item>
          <a-form-item label="结束日期（北京时间）">
            <input
              v-model="endDate"
              type="date"
              :max="beijingToday()"
              :disabled="working || !!attempt || disabled"
            />
          </a-form-item>
        </div>
        <a-form-item v-else label="已确认餐次">
          <a-empty
            v-if="!records.length"
            description="还没有已确认饮食，请先复核饮食照片或人工录入并确认。"
          />
          <a-select
            v-else
            v-model:value="recordId"
            :disabled="working || !!attempt || disabled"
            :options="recordOptions"
            placeholder="选择要分析的一餐"
          />
        </a-form-item>
      </template>
      <a-checkbox v-model:checked="consent" :disabled="working || !!attempt || !canUse">
        我已获得该成员授权，同意本次将问题、必要的已确认饮食和餐后反馈发送给云端饮食分析服务（{{
          modelName
        }}；政策 {{ configuration.policy_version || '尚未批准' }}）。
      </a-checkbox>
      <p class="hint">
        此同意用于饮食分析，与识图、营养咨询和配餐分别核对。分析中的追问请在对话中补充；个人目标和专业规则未就绪时，仅说明记录事实。
      </p>
      <div class="actions">
        <a-button type="primary" :loading="working" :disabled="!canEnter" @click="enter">{{
          attempt ? '重试原请求' : feedback ? '同意并记录反馈' : '同意并开始分析'
        }}</a-button>
        <a-button v-if="attempt?.thread_id" :disabled="working || !canUse" @click="openConversation"
          >进入会话恢复状态</a-button
        >
      </div>
    </a-form>
  </section>
</template>

<style scoped lang="less">
.analysis-entry {
  padding: 20px;
  border: 1px solid var(--gray-200);
  border-radius: 12px;
  background: var(--gray-0);
  h2 {
    margin: 0 0 16px;
    font-size: 17px;
    color: var(--gray-1000);
  }
  :deep(.ant-alert) {
    margin-bottom: 16px;
  }
}
.feedback-entry {
  padding: 0;
  border: 0;
}
.hint {
  color: var(--gray-600);
  line-height: 1.7;
  font-size: 13px;
}
.selected-meal {
  color: var(--gray-1000);
  overflow-wrap: anywhere;
}
.date-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  max-width: 640px;
}
input[type='date'] {
  padding: 5px 10px;
  min-height: 32px;
  width: 100%;
  border: 1px solid var(--gray-200);
  border-radius: 6px;
  color: var(--gray-1000);
  background: var(--gray-0);
}
.actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
@media (max-width: 600px) {
  .analysis-entry {
    padding: 14px;
  }
  .feedback-entry {
    padding: 0;
  }
  .date-fields {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
  }
}
</style>
