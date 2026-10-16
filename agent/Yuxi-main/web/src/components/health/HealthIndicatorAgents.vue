<script setup>
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import HealthIndicatorReview from './HealthIndicatorReview.vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { healthVisionApi as api } from '@/apis/health_vision_api'

const props = defineProps({
  memberId: { type: String, required: true },
  scopes: { type: Array, required: true },
  configuration: { type: Object, required: true },
  disabled: { type: Boolean, default: false }
})
const router = useRouter()
const userStore = useUserStore()
const roles = [
  {
    task: 'blood_glucose_review',
    slug: 'health-blood-glucose',
    name: '血糖记录助手',
    detail: '回顾血糖记录，追问测量条件和缺失资料，解释审核知识。'
  },
  {
    task: 'blood_lipids_review',
    slug: 'health-blood-lipids',
    name: '血脂记录助手',
    detail: '回顾同条血脂四项记录，追问缺失资料，解释审核知识。'
  },
  {
    task: 'blood_pressure_review',
    slug: 'health-blood-pressure',
    name: '血压记录助手',
    detail: '回顾成对血压记录，追问测量资料，解释审核知识。'
  }
]
const indicatorSelection = ref(null)
const selectedTask = ref(roles[0].task)
const consent = ref(false)
const working = ref(false)
const loading = ref(false)
const capabilities = ref(null)
const error = ref('')
const attempt = ref(null)
let epoch = 0
let readSequence = 0
let disposed = false
const role = computed(() => roles.find((item) => item.task === selectedTask.value))
const service = computed(() => props.configuration.consultation || {})
const capability = computed(() =>
  capabilities.value?.tasks.find((item) => item.task_type === selectedTask.value)
)
const canRead = computed(
  () =>
    !!props.memberId && ['ai_use', 'profile_view'].every((scope) => props.scopes.includes(scope))
)
const canUse = computed(
  () =>
    canRead.value &&
    service.value.available &&
    !loading.value &&
    (capability.value?.status === 'available' ||
      capability.value?.reason_code === 'consent_required')
)
const canEnter = computed(() => canUse.value && consent.value && !working.value && !props.disabled)
const reason = computed(() => {
  if (!canRead.value) return '请选择本人，并核对 AI 使用和档案查看授权。'
  if (!service.value.available) return service.value.reason || '咨询模型尚未批准，请核对服务配置。'
  return (
    {
      missing_scopes: '成员授权已变化，请刷新成员信息。',
      self_member_required: '指标助手仅处理本人实测记录，请选择本人。',
      agent_unavailable: '所选指标助手尚未启用。',
      skill_unavailable: '所选指标助手的资料读取能力尚未就绪。',
      configuration_unavailable: '模型或处理政策尚未就绪，请核对服务配置。',
      consent_required: '请核对下方数据范围，单独同意本次云处理。'
    }[capability.value?.reason_code] ||
    (!capability.value ? '尚未取得指标助手状态，请刷新后重试。' : '')
  )
})

/** 身份、成员、授权及模型政策共同固定当前入口上下文。 */
function contextKey() {
  return `${userStore.uid}|${props.memberId}|${props.scopes.join('|')}|${service.value.available}|${service.value.model}|${service.value.processor}|${props.configuration.policy_version}`
}

/** 切换任务或上下文撤销旧同意与迟到导航。 */
function reset() {
  epoch++
  consent.value = false
  attempt.value = null
  working.value = false
  error.value = ''
}

/** 成员能力由真实接口读取，不从前端角色列表推测已就绪。 */
async function refreshCapabilities() {
  const ticket = ++readSequence
  const context = contextKey()
  const current = () => !disposed && ticket === readSequence && context === contextKey()
  capabilities.value = null
  if (!canRead.value) {
    loading.value = false
    return
  }
  loading.value = true
  error.value = ''
  try {
    const result = await api.memberCapabilities(props.memberId)
    if (!current()) return
    if (result.member_id !== props.memberId) throw Error('成员能力绑定不一致，请刷新后重试。')
    capabilities.value = result
  } catch (exc) {
    if (current()) error.value = exc.message
  } finally {
    if (current()) loading.value = false
  }
}

/** 明确同意后创建独立线程，未知响应重试复用原幂等键。 */
async function enter() {
  if (!canEnter.value) return
  if (!attempt.value)
    attempt.value = {
      client_request_id: crypto.randomUUID(),
      task_type: role.value.task,
      selection: indicatorSelection.value
    }
  const pending = attempt.value
  const chosen = role.value
  const id = props.memberId
  const ticket = epoch
  const current = () => !disposed && ticket === epoch && canUse.value
  working.value = true
  error.value = ''
  try {
    await api.consent(id, {
      purpose: 'consultation',
      accepted: true,
      processor: service.value.processor,
      policy_version: props.configuration.policy_version
    })
    if (!current()) return
    const result = await api.createTaskEntry(id, pending)
    if (!current()) return
    if (
      result.member_id !== id ||
      result.task_type !== chosen.task ||
      result.client_request_id !== pending.client_request_id
    )
      throw Error('指标助手绑定不一致，请刷新后重试。')
    if (result.entry_status !== 'ready') {
      error.value =
        result.entry_status === 'needs_input'
          ? result.questions.join('；') || '请补充所需资料后重试。'
          : '指标助手运行服务尚未就绪，请稍后重试。'
      return
    }
    if (
      result.agent_slug !== chosen.slug ||
      !result.thread_id ||
      result.request_submit_url !== api.agentRunSubmitUrl
    )
      throw Error('指标助手会话绑定不一致，请刷新后重试。')
    await router.push({ name: 'AgentCompWithThreadId', params: { thread_id: result.thread_id } })
  } catch (exc) {
    if (!current()) return
    if ([401, 403, 404, 409, 410, 422].includes(exc.status)) {
      reset()
      error.value = [401, 403, 404].includes(exc.status)
        ? '成员授权或用途同意已变化，请重新核对。'
        : [409, 410].includes(exc.status)
          ? '资料版本或处理政策已变化，请刷新后重新进入。'
          : exc.message
    } else error.value = exc.message || '请求结果尚未确认，可重试原请求。'
  } finally {
    if (ticket === epoch) working.value = false
  }
}

watch(selectedTask, reset, { flush: 'sync' })
watch(
  contextKey,
  () => {
    reset()
    void refreshCapabilities()
  },
  { immediate: true, flush: 'sync' }
)
onBeforeUnmount(() => {
  disposed = true
  readSequence++
  reset()
})
</script>

<template>
  <section class="indicator-agents">
    <h2>指标助手</h2>
    <p class="hint">
      分别回顾血糖、血脂、血压记录，补充资料并解释审核知识。每次进入独立会话，在对话中提出问题。
    </p>
    <a-form layout="vertical">
      <a-form-item label="选择指标助手">
        <a-select
          v-model:value="selectedTask"
          :options="roles.map((item) => ({ value: item.task, label: item.name }))"
          :disabled="working || disabled"
        />
      </a-form-item>
      <p>{{ role.detail }}</p>
      <HealthIndicatorReview
        :member-id="memberId"
        :kind="selectedTask.replace('_review', '')"
        :allowed="scopes.includes('profile_view')"
        @selection="
          (value) => {
            reset()
            indicatorSelection = value
          }
        "
      />
      <a-alert v-if="loading" type="info" message="正在核对所选成员的助手状态…" show-icon />
      <a-alert v-else-if="reason" type="info" :message="reason" show-icon />
      <a-alert v-if="error" type="error" :message="error" show-icon />
      <p class="hint">
        将问题、当前对话历史、所选类别的授权实测记录及审核知识发送给已审批模型。{{
          indicatorSelection
            ? '实测使用上方已读取的固定日期及记录选择，最多100条。'
            : '未选择范围时，实测仅包含近30个北京时间自然日最多20条记录。'
        }}
        保留原值、单位、测量时间、来源、记录ID和版本；血糖保留 mmol/L
        及空腹、餐后2小时或随机的测量条件， 血压保留成对收缩压、舒张压及
        mmHg，血脂保留同条总胆固醇、甘油三酯、高密度脂蛋白、低密度脂蛋白及 mmol/L。 处理方：{{
          service.processor || '尚未批准'
        }}；政策：{{ configuration.policy_version || '尚未批准' }}。
      </p>
      <a-checkbox v-model:checked="consent" :disabled="!canUse || working || disabled">
        我已获得该成员授权，单独同意本次指标记录回顾用途的云处理。
      </a-checkbox>
      <div class="actions">
        <a-button type="primary" :loading="working" :disabled="!canEnter" @click="enter">{{
          attempt ? '重试原请求' : `同意并进入${role.name}`
        }}</a-button>
        <a-button :disabled="working || disabled || loading" @click="refreshCapabilities"
          >刷新助手状态</a-button
        >
      </div>
    </a-form>
  </section>
</template>

<style scoped lang="less">
.indicator-agents {
  padding: 20px;
  border: 1px solid var(--gray-150);
  border-radius: 8px;
  background: var(--gray-0);
  color: var(--color-text);
  h2 {
    margin: 0 0 16px;
    font-size: 17px;
  }
  :deep(.ant-alert) {
    margin-bottom: 16px;
  }
  :deep(.ant-select) {
    max-width: 480px;
    width: 100%;
  }
}
.hint {
  color: var(--color-text-secondary);
  line-height: 1.7;
  font-size: 13px;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}
</style>
