<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { healthVisionApi as api } from '@/apis/health_vision_api'
import NutritionSourcePicker from './NutritionSourcePicker.vue'

const code = ref('')
const current = ref(null)
const payload = ref('')
const confirmed = ref(false)
const busy = ref(false)
const error = ref('')
const success = ref('')
const pending = ref(null)
const revokeOpen = ref(false)
const revokeTarget = ref(null)
const metadata = reactive({
  source_ref: '',
  source_version: '',
  authority_ref: '',
  attested_by: '',
  attested_at: '',
  valid_until: ''
})
const labels = {
  source_ref: '来源原件 / 出处',
  source_version: '来源版本',
  authority_ref: '专业批准依据',
  attested_by: '实际批准人',
  attested_at: '批准时间（含时区）',
  valid_until: '有效截止时间（含时区）'
}
const availabilityReasons = {
  not_delivered: '尚未登记批准版本',
  revoked: '批准版本已撤回',
  expired: '批准版本已过期',
  integrity_mismatch: '批准内容无法核对',
  future_attestation: '批准时间尚未生效',
  knowledge_source_changed: '来源原件已变化或不可用，请重新核对'
}
const locked = computed(() => busy.value || !!pending.value)
let sequence = 0
let disposed = false

/** 查询最终版本后才允许追加，历史版本不可覆盖。 */
async function read() {
  if (!code.value.trim() || busy.value) return
  const ticket = ++sequence
  busy.value = true
  error.value = ''
  success.value = ''
  current.value = null
  try {
    const result = await api.approvedQualityRules(code.value.trim())
    if (!disposed && ticket === sequence) current.value = result
  } catch {
    if (!disposed && ticket === sequence) error.value = '读取规则失败，请重试。'
  } finally {
    if (!disposed && ticket === sequence) busy.value = false
  }
}

/** 重试保留完全相同的批准版本，未知结果不能换内容再次提交。 */
async function publish() {
  if (busy.value || !current.value || (!pending.value && !confirmed.value)) return
  error.value = ''
  success.value = ''
  if (!pending.value) {
    try {
      pending.value = {
        ...metadata,
        rule_code: code.value.trim(),
        version: current.value.next_version,
        status: 'approved',
        payload: JSON.parse(payload.value)
      }
    } catch {
      error.value = '规则内容不是有效 JSON，请核对专业方提供的文件。'
      return
    }
  }
  busy.value = true
  const ticket = ++sequence
  try {
    const receipt = await api.importQualityRules(pending.value)
    if (!Number.isInteger(receipt?.version) || receipt.version < pending.value.version) {
      throw new Error('unverified_receipt')
    }
    if (disposed || ticket !== sequence) return
    const result = await api.approvedQualityRules(pending.value.rule_code)
    if (disposed || ticket !== sequence) return
    if (!Number.isInteger(result?.version) || result.version < pending.value.version) {
      throw new Error('unverified_readback')
    }
    current.value = result
    pending.value = null
    confirmed.value = false
    success.value = '规则已登记并回读。是否可用以当前来源、有效期及批准范围为准。'
  } catch (cause) {
    if (disposed || ticket !== sequence) return
    if (cause?.status && cause.status < 500) {
      pending.value = null
      if (cause.status === 409) current.value = null
      error.value =
        cause.status === 409
          ? '版本或来源已变化，请重新读取并核对。'
          : '导入被拒绝，请核对权限、字段和批准依据。'
    } else error.value = '导入结果尚未确认；请重试原请求，内容已锁定保留。'
  } finally {
    if (!disposed && ticket === sequence) busy.value = false
  }
}

/** 撤回使用已回读的确定版本，确认框避免误撤回。 */
async function revoke() {
  const target = revokeTarget.value
  if (
    locked.value ||
    !target ||
    target.code !== code.value.trim() ||
    target.version !== current.value?.version
  )
    return
  busy.value = true
  error.value = ''
  success.value = ''
  const ticket = ++sequence
  try {
    await api.revokeQualityRules(target.code, target.version)
    const result = await api.approvedQualityRules(target.code)
    if (!disposed && ticket === sequence) {
      current.value = result
      success.value = '规则版本已撤回并回读。'
    }
  } catch {
    if (!disposed && ticket === sequence) error.value = '撤回结果未确认，请重新读取当前版本。'
  } finally {
    if (!disposed && ticket === sequence) busy.value = false
  }
}
function selectRevokeTarget(open) {
  revokeTarget.value = open
    ? { code: code.value.trim(), version: current.value?.version }
    : revokeTarget.value
}
watch([metadata, payload], () => {
  confirmed.value = false
})
watch(code, () => {
  sequence++
  current.value = null
  confirmed.value = false
  success.value = ''
  error.value = ''
  revokeOpen.value = false
  revokeTarget.value = null
})
onBeforeUnmount(() => {
  disposed = true
  sequence++
})
</script>

<template>
  <section class="rules-admin">
    <h2>专业批准规则</h2>
    <p>
      登记专业内容方实际批准的版本，包含适用人群、营养范围、目标公式及菜谱分类。知识库文献本身不等于专业批准。
    </p>
    <label>规则代码<a-input v-model:value="code" :disabled="locked" :maxlength="80" /></label>
    <a-button :loading="busy" :disabled="locked || !code.trim()" @click="read"
      >读取当前规则</a-button
    >
    <a-alert v-if="error" type="error" :message="error" show-icon />
    <a-alert v-if="success" type="success" :message="success" show-icon />
    <template v-if="current">
      <p role="status">
        当前版本：{{ current.version || '尚无' }} ·
        {{ current.status === 'ready' ? '来源有效' : '当前不可用'
        }}<span v-if="current.reason">（{{ availabilityReasons[current.reason] || '批准资料需要重新核对' }}）</span>
      </p>
      <details v-if="current.payload">
        <summary>查看当前规则与批准依据</summary>
        <pre>{{
          JSON.stringify({ payload: current.payload, attestation: current.attestation }, null, 2)
        }}</pre>
      </details>
      <div class="grid">
        <label v-for="(label, key) in labels" :key="key"
          >{{ label }}<a-input v-model:value="metadata[key]" :disabled="locked" :maxlength="500"
        /></label>
      </div>
      <NutritionSourcePicker :disabled="locked" @selected="metadata.source_ref = $event" />
      <label
        >专业规则内容（QualityRules JSON）<a-textarea
          v-model:value="payload"
          :disabled="locked"
          :rows="12"
          placeholder="粘贴专业方核对的规则内容，不自动补入医学参数"
      /></label>
      <a-checkbox v-model:checked="confirmed" :disabled="locked"
        >已核对实际批准人、依据、有效期与适用范围</a-checkbox
      >
      <div class="actions">
        <a-button
          type="primary"
          :loading="busy"
          :disabled="!confirmed || !payload.trim()"
          @click="publish"
          >{{ pending ? '重试原导入请求' : `登记版本 ${current.next_version}` }}</a-button
        >
        <a-popconfirm
          v-model:open="revokeOpen"
          :title="`确认撤回 ${revokeTarget?.code || code} 的版本 ${revokeTarget?.version || current.version}？依赖它的方案需要重新核对。`"
          @open-change="selectRevokeTarget"
          @confirm="revoke"
        >
          <a-button danger :disabled="locked || !current.version || current.reason === 'revoked'"
            >撤回当前版本</a-button
          >
        </a-popconfirm>
      </div>
    </template>
  </section>
</template>

<style scoped>
.rules-admin {
  padding: 20px;
  margin-bottom: 18px;
  border: 1px solid var(--gray-200);
  border-radius: 12px;
  background: var(--gray-0);
}
label {
  display: grid;
  gap: 6px;
  margin: 12px 0;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(260px, 100%), 1fr));
  gap: 12px;
}
.actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 14px;
}
pre {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
p {
  color: var(--color-text-secondary);
}
</style>
