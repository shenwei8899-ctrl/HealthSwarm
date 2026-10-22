<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { healthVisionApi as api } from '@/apis/health_vision_api'
import { nutrientLabels, nutrientText } from '@/utils/healthVision'

const props = defineProps({ requestId: { type: String, required: true } })
const router = useRouter(),
  user = useUserStore()
const open = ref(false),
  loading = ref(false),
  working = ref(false),
  agreed = ref(false)
const preview = ref(null),
  configuration = ref(null),
  error = ref(''),
  attempt = ref(null)
let epoch = 0,
  disposed = false
const current = (ticket) => !disposed && ticket === epoch
const targetName = computed(() =>
  preview.value?.target_agent === 'health-meal-planner' ? '基础配餐师' : '营养咨询'
)
const config = computed(() => configuration.value?.[preview.value?.target_purpose])
const window = computed(() => preview.value?.summary.window || preview.value?.summary.period)
const canConfirm = computed(
  () => preview.value && config.value?.available && agreed.value && !working.value
)

function clear() {
  epoch++
  open.value = false
  preview.value = null
  configuration.value = null
  error.value = ''
  agreed.value = false
  attempt.value = null
  loading.value = false
  working.value = false
}

/** 打开只读预览，取消不会创建会话或提交模型请求。 */
async function prepare() {
  if (working.value || attempt.value) {
    open.value = true
    return
  }
  clear()
  open.value = true
  loading.value = true
  const ticket = epoch
  try {
    const [data, config] = await Promise.all([
      api.handoffPreview(props.requestId),
      api.configuration()
    ])
    if (!current(ticket)) return
    preview.value = data
    configuration.value = config
  } catch (err) {
    if (current(ticket)) error.value = err.message
  } finally {
    if (current(ticket)) loading.value = false
  }
}

/** 未确认响应期间保留同一幂等请求，禁止关闭后发起重复交接。 */
function close() {
  if (!working.value && !attempt.value) clear()
}

function indicatorText(row) {
  if (row.glucose !== undefined) return `${row.glucose ?? '未知'} ${row.unit}`
  if (row.systolic !== undefined)
    return `${row.systolic ?? '未知'}/${row.diastolic ?? '未知'} ${row.unit}`
  return (
    ['tc', 'tg', 'hdl', 'ldl']
      .map((key) => `${key.toUpperCase()} ${row[key] ?? '未知'}`)
      .join('；') + ` ${row.unit}`
  )
}

function totalText(value, unit) {
  if (!value || typeof value !== 'object') return nutrientText(value, unit)
  return `${nutrientText(value.recorded_total, unit)}；已知部分 ${nutrientText(value.known_sum, unit)}（${value.known_records} 条已知，${value.missing_records} 条缺失）`
}

/** 同意限于目标用途，重试保留原键与来源摘要。 */
async function confirm() {
  if (!canConfirm.value) return
  if (!attempt.value)
    attempt.value = {
      client_request_id: crypto.randomUUID(),
      source_hash: preview.value.source_hash,
      confirmed: true
    }
  const ticket = epoch,
    source = preview.value,
    pending = attempt.value
  working.value = true
  error.value = ''
  try {
    await api.consent(source.member_id, {
      purpose: source.target_purpose,
      accepted: true,
      processor: config.value.processor,
      policy_version: configuration.value.policy_version
    })
    if (!current(ticket)) return
    const result = await api.confirmHandoff(props.requestId, pending)
    if (!current(ticket)) return
    if (
      result.member_id !== source.member_id ||
      result.agent_slug !== source.target_agent ||
      !result.thread_id
    )
      throw Error('交接结果与确认对象不一致，请重新核对。')
    await router.push({
      name: 'AgentCompWithThreadId',
      params: { thread_id: result.thread_id }
    })
    if (current(ticket)) clear()
  } catch (err) {
    if (current(ticket)) {
      error.value = err.message
      if ([401, 403, 404, 409, 410, 422].includes(err.status)) {
        preview.value = null
        agreed.value = false
        attempt.value = null
      }
    }
  } finally {
    if (current(ticket)) working.value = false
  }
}
watch(() => [user.uid, props.requestId], clear)
onBeforeUnmount(() => {
  disposed = true
  epoch++
})
</script>

<template>
  <div class="handoff-entry">
    <a-button size="small" @click="prepare">转交其他助手</a-button>
    <a-modal
      :open="open"
      title="核对交接资料"
      :footer="null"
      :mask-closable="false"
      :closable="!working && !attempt"
      :keyboard="!working && !attempt"
      @cancel="close"
    >
      <a-spin :spinning="loading">
        <a-alert v-if="error" type="error" show-icon :message="error" />
        <a-alert
          v-if="attempt && !working"
          type="warning"
          message="交接结果尚未确认，请重试原交接。"
        />
        <template v-if="preview">
          <p>
            将为当前成员创建独立的<strong>{{ targetName }}</strong
            >会话。确认后由你继续提问。
          </p>
          <p>{{ preview.summary.notice }}</p>
          <p v-if="window">范围：{{ window.start_date }} 至 {{ window.end_date }}（北京时间）</p>
          <ul class="handoff-records">
            <li v-for="row in preview.summary.records || []" :key="row.record_id">
              <template v-if="row.measured_at"
                >{{ row.measured_at }} · {{ indicatorText(row) }}</template
              >
              <span v-else>已确认饮食记录</span> · 第 {{ row.version || row.source_version }} 版
              <details>
                <summary>核对本条事实</summary>
                <pre>{{ JSON.stringify(row, null, 2) }}</pre>
              </details>
            </li>
          </ul>
          <p v-if="preview.summary.truncated">范围内记录较多，本次只交接列出的记录。</p>
          <div v-if="preview.summary.nutrition?.totals">
            <p v-for="([label, unit], key) in nutrientLabels" :key="key">
              {{ label }}：{{ totalText(preview.summary.nutrition.totals[key], unit) }}
            </p>
          </div>
          <p v-if="preview.summary.nutrition?.estimated">营养包含估算值。</p>
          <details v-if="preview.summary.coverage">
            <summary>记录覆盖范围与缺项</summary>
            <pre>{{ JSON.stringify(preview.summary.coverage, null, 2) }}</pre>
          </details>
          <a-alert
            v-if="!config?.available"
            type="info"
            :message="config?.reason || '目标用途尚未配置，暂不可交接。'"
          />
          <template v-else>
            <p>处理方：{{ config.processor }}；政策版本：{{ configuration.policy_version }}</p>
            <a-checkbox v-model:checked="agreed" :disabled="working || !!attempt"
              >已核对上述资料，并同意在目标用途中处理必要成员数据。</a-checkbox
            >
            <a-button type="primary" :disabled="!canConfirm" :loading="working" @click="confirm">{{
              attempt ? '重试原交接' : '确认并进入'
            }}</a-button>
          </template>
        </template>
        <a-button v-if="error && !preview" :disabled="working" @click="prepare"
          >重新读取来源</a-button
        >
      </a-spin>
    </a-modal>
  </div>
</template>

<style scoped>
.handoff-entry {
  margin-top: 12px;
}
.handoff-records {
  max-height: 280px;
  overflow: auto;
  padding-left: 20px;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: var(--gray-25);
  padding: 8px;
}
.ant-btn {
  margin: 12px 0;
}
</style>
