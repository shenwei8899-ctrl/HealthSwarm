<script setup>
import { computed, onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useUserStore } from '@/stores/user'
import { healthVisionApi as api } from '@/apis/health_vision_api'
import { nutrientLabels } from '@/utils/healthVision'

const props = defineProps({
  member: { type: Object, default: null },
  disabled: { type: Boolean, default: false }
})
const emit = defineEmits(['plans'])
const user = useUserStore()
const context = ref(null)
const currentProfile = ref(null)
const selectedWeight = ref('')
const confirmed = ref(false)
const payloadText = ref('')
const metadata = reactive({
  source_ref: '',
  source_version: '',
  authority_ref: '',
  attested_by: '',
  attested_at: '',
  valid_until: ''
})
const ruleCode = ref('')
const rule = ref(null)
const targets = ref(null)
const pendingImport = ref(null)
const loading = ref(false)
const saving = ref(false)
const calculating = ref(false)
const error = ref('')
const targetError = ref('')
const success = ref('')
const sourceConflict = ref(false)
const canRead = computed(
  () => user.isLoggedIn && !!props.member?.id && props.member.scopes?.includes('profile_view')
)
const canImport = computed(
  () => canRead.value && user.isAdmin && props.member.scopes?.includes('profile_edit')
)
const formal = computed(() => context.value?.formal_source)
const weights = computed(() => context.value?.weight_candidates)
const weight = computed(() =>
  weights.value?.items?.find((item) => `${item.record_id}:${item.version}` === selectedWeight.value)
)
const busy = computed(() => loading.value || saving.value || props.disabled)
const formLocked = computed(() => busy.value || !!pendingImport.value)
const sourceReady = computed(
  () => formal.value?.status === 'ready' && !!formal.value.family_profile_source
)
const canSubmit = computed(
  () =>
    canImport.value && sourceReady.value && !sourceConflict.value && confirmed.value && !busy.value
)
const formalLabels = {
  sex: '原始性别',
  birth_date: '出生日期',
  height_cm: '身高（cm）',
  activity_level: '原始活动描述',
  goal: '原始健康目标'
}
const reasons = {
  not_delivered: '尚未导入专业确认版本',
  revoked: '专业确认版本已撤回',
  expired: '专业确认版本已过期',
  integrity_mismatch: '专业确认内容无法核对',
  future_attestation: '专业确认时间尚未生效',
  family_profile_unconfirmed: '正式档案当前版本尚未由本人确认',
  family_profile_source_changed: '本人正式档案来源已变化，请重新专业确认',
  family_profile_source_unmapped: '专业确认版本尚未绑定本人正式档案，请重新专业确认',
  family_profile_source_unavailable: '本人正式档案当前不可用，请核对本人确认和授权',
  family_profile_access_required: '当前账号没有本人正式档案访问权，请取得授权后刷新',
  family_profile_fields_required: '当前账号缺少正式档案必需字段的查看权，请核对字段授权',
  family_profile_incomplete: '本人正式档案需要补充，请补充并由本人确认后刷新',
  weight_access_required: '当前账号没有原始体重记录查看权，请取得体重字段授权后刷新',
  weight_missing: '暂无可用的本人实测体重记录，请在家庭档案记录体重后刷新',
  weight_measurement_source_changed: '所选体重记录已变化，请重新选择并专业确认',
  weight_measurement_source_unavailable: '所选体重记录当前不可用，请核对记录和授权',
  profile_not_linked: '尚未关联本人正式档案',
  profile_unconfirmed: '正式档案当前版本待本人确认',
  profile_incomplete: '正式档案需要补充',
  confirmed_profile_or_approved_rules_required: '需要当前有效的专业档案和批准规则',
  personal_target_formula_not_approved: '该规则尚无匹配的批准目标公式',
  confirmed_population_age_and_sex_required: '人群、年龄或性别专业确认信息不完整',
  unsupported_population: '当前人群不在批准规则适用范围内',
  confirmed_conditions_and_requirements_required: '疾病及医嘱信息需要明确专业确认',
  confirmed_approved_activity_required: '活动编码未确认或不在批准公式内',
  selected_weight_measurement_required: '目标计算需要明确选定的本人实测体重版本',
  confirmed_formula_input_required: '批准公式所需的专业确认参数不完整',
  formula_result_outside_supported_range: '公式结果超出支持范围，需要专业复核',
  doctor_requirement_rule_not_approved: '医嘱未匹配批准规则，需要专业复核',
  approved_target_ranges_conflict: '批准目标范围存在冲突，需要专业复核'
}
let epoch = 0
let readSequence = 0
let targetSequence = 0
let disposed = false

/** 账号、成员或授权改变后清空全部私有内容与未确认请求。 */
function reset() {
  context.value = null
  currentProfile.value = null
  selectedWeight.value = ''
  confirmed.value = false
  payloadText.value = ''
  Object.keys(metadata).forEach((key) => (metadata[key] = ''))
  ruleCode.value = ''
  rule.value = null
  targets.value = null
  pendingImport.value = null
  loading.value = false
  saving.value = false
  calculating.value = false
  error.value = ''
  targetError.value = ''
  success.value = ''
  sourceConflict.value = false
}

/** 只有当前账号和成员仍有授权时接受异步结果。 */
function active(ticket) {
  return !disposed && ticket === epoch && canRead.value
}

/** 业务原因以用户可采取的下一步展示，未知原因不猜测临床含义。 */
function reasonText(reason, ruleSource = false) {
  if (
    ruleSource &&
    ['not_delivered', 'revoked', 'expired', 'integrity_mismatch', 'future_attestation'].includes(
      reason
    )
  )
    return {
      not_delivered: '尚无该代码的批准规则版本，请向专业方核对规则代码',
      revoked: '批准规则版本已撤回，请核对当前可用规则',
      expired: '批准规则版本已过期，请核对当前可用规则',
      integrity_mismatch: '批准规则内容无法核对，请联系专业内容方',
      future_attestation: '批准规则确认时间尚未生效'
    }[reason]
  return reasons[reason] || '当前来源不可用，请核对本人确认、记录和访问授权后刷新。'
}

/** 已拒绝的请求与结果未知的写入使用不同恢复提示。 */
function failure(cause, writing = false) {
  if (cause?.status === 403) return '当前权限不足，请核对成员授权与管理员资格后刷新。'
  if (cause?.status === 404) return '来源不存在或当前不可访问，请核对档案和授权后刷新。'
  if ([409, 410].includes(cause?.status))
    return '档案、体重或规则版本已变化，请刷新来源后重新确认。'
  if (cause?.status === 422) return '专业确认内容或依据格式无效，请核对字段、版本及带时区的时间。'
  return writing
    ? '导入结果尚未确认，请重试原导入请求或刷新核对。原请求内容已保留。'
    : '读取失败，请刷新重试。'
}

/** 导入上下文只在管理员及两个成员权限同时满足时读取。 */
async function reload(offset = 0) {
  if (saving.value || props.disabled) return null
  return readCurrent(offset)
}

/** 刷新来源清除选择和旧目标，但保留未知导入的不可变整包。 */
async function readCurrent(offset = 0) {
  const ticket = epoch,
    sequence = ++readSequence
  targetSequence++
  context.value = null
  currentProfile.value = null
  selectedWeight.value = ''
  confirmed.value = false
  rule.value = null
  targets.value = null
  calculating.value = false
  error.value = ''
  targetError.value = ''
  success.value = ''
  loading.value = true
  if (!canRead.value) {
    loading.value = false
    return null
  }
  try {
    if (canImport.value) {
      const result = await api.profileImportContext(props.member.id, 20, offset)
      if (!active(ticket) || sequence !== readSequence) return null
      if (result.member_id !== props.member.id) throw Error('member mismatch')
      context.value = result
      currentProfile.value = result.current_profile
    } else {
      const result = await api.professionalProfile(props.member.id)
      if (!active(ticket) || sequence !== readSequence) return null
      currentProfile.value = result
    }
    sourceConflict.value = false
    return currentProfile.value
  } catch (cause) {
    if (active(ticket) && sequence === readSequence) {
      const message = failure(cause)
      if ([403, 404].includes(cause?.status)) reset()
      error.value = message
    }
    return null
  } finally {
    if (active(ticket) && sequence === readSequence) loading.value = false
  }
}

/** 未知不等于明确无；模板只列必需的未知状态，不提供临床参数。 */
function insertUnknownTemplate() {
  if (formLocked.value || payloadText.value.trim()) return
  payloadText.value = JSON.stringify(
    Object.fromEntries(
      [
        'conditions',
        'allergies',
        'intolerances',
        'avoidances',
        'doctor_requirements',
        'preferences'
      ].map((key) => [key, { state: 'unknown', codes: [] }])
    ),
    null,
    2
  )
}

/** 只附上真实来源版本，专业确认的体重值必须与主动选择的记录相同。 */
function importBody() {
  const payload = JSON.parse(payloadText.value)
  if (!payload || typeof payload !== 'object' || Array.isArray(payload))
    throw Error('专业确认内容须为 JSON 对象。')
  if (!Object.values(metadata).every((value) => value.trim()))
    throw Error('请填写完整的专业确认依据与带时区的确认时间、有效期。')
  if (
    !Number.isSafeInteger(currentProfile.value?.next_version) ||
    currentProfile.value.next_version < 1
  )
    throw Error('当前导入版本不可用，请刷新来源。')
  if (payload.weight_kg !== undefined && payload.weight_kg !== null) {
    if (!weight.value) throw Error('专业确认内容含体重，请主动选择对应的本人实测记录版本。')
    const confirmedWeight = Number(payload.weight_kg)
    if (
      !['number', 'string'].includes(typeof payload.weight_kg) ||
      !Number.isFinite(confirmedWeight) ||
      confirmedWeight <= 0 ||
      confirmedWeight !== Number(weight.value.weight_kg)
    )
      throw Error('专业确认体重与所选记录不一致。请核对原始依据，页面不会自动替换专业数值。')
  } else if (weight.value) {
    throw Error('已选择体重记录，请在专业确认内容中提供与该记录一致的 weight_kg，或清除选择。')
  }
  return {
    ...Object.fromEntries(Object.entries(metadata).map(([key, value]) => [key, value.trim()])),
    version: currentProfile.value.next_version,
    status: 'confirmed',
    payload,
    family_profile_source: { ...formal.value.family_profile_source },
    ...(weight.value
      ? {
          weight_measurement_source: {
            record_id: weight.value.record_id,
            version: weight.value.version
          }
        }
      : {})
  }
}

/** 未知响应冻结原包；明确成功回执与回读的较新当前版本分别展示。 */
async function submitImport() {
  if (busy.value || !canImport.value || (!pendingImport.value && !canSubmit.value)) return
  const ticket = epoch
  error.value = ''
  success.value = ''
  if (!pendingImport.value) {
    try {
      pendingImport.value = importBody()
    } catch (cause) {
      error.value =
        cause instanceof SyntaxError ? '专业确认内容不是有效 JSON，请核对后再提交。' : cause.message
      return
    }
  }
  const body = pendingImport.value
  saving.value = true
  try {
    const receipt = await api.importProfessionalProfile(
      props.member.id,
      JSON.parse(JSON.stringify(body))
    )
    if (!active(ticket)) return
    if (!Number.isSafeInteger(receipt?.version) || receipt.version < body.version) {
      error.value = '导入响应缺少可核对的版本，原请求已保留。请重试原请求或刷新核对。'
      return
    }
    pendingImport.value = null
    const current = await readCurrent()
    if (!active(ticket)) return
    if (!current) {
      error.value = `导入回执已确认。${error.value || '当前状态读取失败，请刷新核对。'}`
      return
    }
    if (!Number.isSafeInteger(current.version) || current.version < body.version) {
      error.value = '原版本导入回执已确认，当前来源与回执不一致，请刷新核对。'
      return
    }
    success.value =
      current.version === body.version
        ? `专业确认版本 ${body.version} 已导入，当前状态已回读。`
        : `专业确认版本 ${body.version} 的导入回执已确认；当前服务端版本为 ${current.version}，请核对当前来源。`
    if (ruleCode.value.trim()) await calculateTargets()
  } catch (cause) {
    if (active(ticket)) {
      error.value = failure(cause, true)
      if (cause?.status >= 400 && cause.status < 500 && cause.status !== 408) {
        pendingImport.value = null
        confirmed.value = false
        if ([409, 410].includes(cause.status)) {
          sourceConflict.value = true
          context.value = null
          currentProfile.value = null
          targets.value = null
          rule.value = null
        }
        if ([403, 404].includes(cause.status)) {
          const message = error.value
          reset()
          error.value = message
        }
      }
    }
  } finally {
    if (active(ticket)) saving.value = false
  }
}

/** 规则代码由用户明确提供，两个实际版本只来自服务端回读。 */
async function calculateTargets() {
  if (
    !canRead.value ||
    loading.value ||
    props.disabled ||
    calculating.value ||
    !currentProfile.value
  )
    return
  const code = ruleCode.value.trim()
  if (!/^[a-zA-Z0-9_.:-]{1,80}$/.test(code)) {
    targetError.value = '请填写专业方提供的批准规则代码。'
    return
  }
  const ticket = epoch,
    sequence = ++targetSequence,
    profileVersion = currentProfile.value.version
  calculating.value = true
  rule.value = null
  targets.value = null
  targetError.value = ''
  try {
    const currentRule = await api.approvedQualityRules(code)
    if (!active(ticket) || sequence !== targetSequence) return
    rule.value = currentRule
    if (!Number.isSafeInteger(profileVersion) || !Number.isSafeInteger(currentRule.version)) return
    const result = await api.personalTargets(props.member.id, {
      profile_version: profileVersion,
      rule_code: code,
      rule_version: currentRule.version
    })
    if (active(ticket) && sequence === targetSequence) targets.value = result
  } catch (cause) {
    if (active(ticket) && sequence === targetSequence) {
      targetError.value = failure(cause)
      if ([403, 404].includes(cause?.status)) {
        const message = targetError.value
        reset()
        targetError.value = message
      }
    }
  } finally {
    if (active(ticket) && sequence === targetSequence) calculating.value = false
  }
}

/** 只在当前有效目标下提供同一成员的餐单入口。 */
function openPlans() {
  if (active(epoch) && !busy.value && !pendingImport.value && targets.value?.status === 'ready')
    emit('plans')
}

watch(
  () => [selectedWeight.value, payloadText.value, ...Object.values(metadata)],
  () => {
    confirmed.value = false
  },
  { flush: 'sync' }
)
watch(
  ruleCode,
  () => {
    targetSequence++
    calculating.value = false
    rule.value = null
    targets.value = null
    targetError.value = ''
  },
  { flush: 'sync' }
)
watch(
  () => [
    user.uid,
    user.token,
    user.isLoggedIn,
    user.isAdmin,
    props.member?.id,
    props.member?.scopes?.join(',')
  ],
  () => {
    epoch++
    reset()
    void readCurrent()
  },
  { flush: 'sync' }
)
onMounted(() => readCurrent())
onBeforeUnmount(() => {
  disposed = true
  epoch++
  reset()
})
</script>

<template>
  <section class="professional-profile">
    <div class="heading">
      <div>
        <h2>专业档案与个人营养目标</h2>
        <p class="muted">专业确认内容与本人原始档案、实测体重分别保留来源版本。</p>
      </div>
      <a-button v-if="canRead" :loading="loading" :disabled="saving || disabled" @click="reload()">
        刷新专业来源
      </a-button>
    </div>
    <a-alert
      v-if="!canRead"
      type="info"
      show-icon
      message="查看专业档案需要当前成员的档案查看授权。"
    />
    <template v-else>
      <a-alert v-if="error" type="error" show-icon :message="error" />
      <a-alert v-if="success" type="success" show-icon :message="success" />
      <a-spin :spinning="loading">
        <template v-if="currentProfile">
          <p v-if="currentProfile.status === 'ready'" role="status">
            当前专业确认版本 {{ currentProfile.version }} 可用
          </p>
          <a-alert v-else type="warning" show-icon :message="reasonText(currentProfile.reason)" />
          <p v-if="currentProfile.attestation" class="muted">
            专业确认人：{{ currentProfile.attestation.attested_by }} · 有效期至
            {{ currentProfile.attestation.valid_until }}
          </p>
          <p v-if="currentProfile.attestation?.family_profile_source" class="muted">
            绑定本人正式档案确认版本
            {{ currentProfile.attestation.family_profile_source.confirmed_version }}
          </p>
          <p v-if="currentProfile.attestation?.weight_measurement_source" class="muted">
            绑定实测体重版本 {{ currentProfile.attestation.weight_measurement_source.version }} ·
            {{ currentProfile.attestation.weight_measurement_source.measured_at }}
          </p>
          <details v-if="currentProfile.status === 'ready' && currentProfile.payload">
            <summary>查看当前专业确认内容</summary>
            <pre>{{ JSON.stringify(currentProfile.payload, null, 2) }}</pre>
          </details>
        </template>
        <a-alert
          v-if="!canImport"
          type="info"
          show-icon
          message="专业确认版本由具备成员档案查看、编辑授权的管理员导入。管理员身份不会自动授予原始档案或测量记录权限。"
        />
        <template v-else-if="context">
          <div class="source-block">
            <h3>本人正式来源</h3>
            <p v-if="sourceReady">
              本人已确认的正式档案版本 {{ formal.family_profile_source.confirmed_version }}
            </p>
            <a-alert v-else type="warning" show-icon :message="reasonText(formal?.reason)" />
            <dl v-if="formal?.profile" class="formal-fields">
              <template v-for="(value, key) in formal.profile" :key="key">
                <dt>{{ formalLabels[key] || '原始档案字段' }}</dt>
                <dd>{{ value === null || value === '' ? '未填写' : value }}</dd>
              </template>
            </dl>
            <p class="muted">
              这里只展示当前账号有权读取的原始字段；原始描述不会自动变为临床编码。
            </p>
          </div>
          <a-form v-if="sourceReady" layout="vertical" class="import-form">
            <h3>导入专业确认版本 {{ currentProfile?.next_version }}</h3>
            <a-form-item label="本人实测体重记录版本">
              <a-select
                v-model:value="selectedWeight"
                :disabled="formLocked || weights?.status !== 'ready'"
                :options="
                  (weights?.items || []).map((item) => ({
                    value: `${item.record_id}:${item.version}`,
                    label: `${item.measured_at} · ${item.weight_kg} ${item.unit} · 版本 ${item.version} · ${item.source}`
                  }))
                "
                allow-clear
                placeholder="请主动选择专业确认所依据的实测记录"
                aria-label="选择本人实测体重记录版本"
              />
              <p class="muted">
                不会自动选择最新记录或替换专业确认体重。未使用体重时可不选；含 weight_kg
                的专业内容必须与所选记录一致。
              </p>
            </a-form-item>
            <a-alert
              v-if="weights?.status !== 'ready'"
              type="warning"
              show-icon
              :message="reasonText(weights?.reason)"
            />
            <a-empty
              v-else-if="!weights.items.length"
              description="暂无当前可用的本人实测体重记录。请先在家庭档案记录体重，再刷新。"
            />
            <div v-if="weights?.total > weights?.limit" class="actions">
              <span class="muted"
                >第 {{ Math.floor(weights.offset / weights.limit) + 1 }} 页 · 共
                {{ weights.total }} 条</span
              >
              <a-button
                :disabled="formLocked || weights.offset === 0"
                @click="reload(weights.offset - weights.limit)"
                >上一页</a-button
              >
              <a-button
                :disabled="formLocked || weights.offset + weights.limit >= weights.total"
                @click="reload(weights.offset + weights.limit)"
                >下一页</a-button
              >
            </div>
            <div class="metadata-fields">
              <a-form-item label="专业内容来源"
                ><a-input
                  v-model:value="metadata.source_ref"
                  :disabled="formLocked"
                  :maxlength="500"
                  aria-label="专业内容来源"
              /></a-form-item>
              <a-form-item label="专业内容来源版本"
                ><a-input
                  v-model:value="metadata.source_version"
                  :disabled="formLocked"
                  :maxlength="80"
                  aria-label="专业内容来源版本"
              /></a-form-item>
              <a-form-item label="专业确认依据"
                ><a-input
                  v-model:value="metadata.authority_ref"
                  :disabled="formLocked"
                  :maxlength="500"
                  aria-label="专业确认依据"
              /></a-form-item>
              <a-form-item label="专业确认人"
                ><a-input
                  v-model:value="metadata.attested_by"
                  :disabled="formLocked"
                  :maxlength="100"
                  aria-label="专业确认人"
              /></a-form-item>
              <a-form-item label="专业确认时间（含时区）"
                ><a-input
                  v-model:value="metadata.attested_at"
                  :disabled="formLocked"
                  placeholder="填写依据中的 ISO 时间及其时区"
                  aria-label="专业确认时间（含时区）"
              /></a-form-item>
              <a-form-item label="专业确认有效期至（含时区）"
                ><a-input
                  v-model:value="metadata.valid_until"
                  :disabled="formLocked"
                  placeholder="填写专业方提供的有效期及其时区"
                  aria-label="专业确认有效期至（含时区）"
              /></a-form-item>
            </div>
            <a-form-item label="专业确认内容（JSON）">
              <a-textarea
                v-model:value="payloadText"
                :disabled="formLocked"
                :rows="10"
                aria-label="专业确认内容 JSON"
              />
              <a-button
                size="small"
                :disabled="formLocked || !!payloadText.trim()"
                @click="insertUnknownTemplate"
                >载入未知字段模板</a-button
              >
              <p class="muted">
                填写专业方已确认的投影内容。未知状态可保留
                unknown；不从原始描述推断疾病、活动编码或公式参数。
              </p>
            </a-form-item>
            <a-checkbox v-model:checked="confirmed" :disabled="formLocked">
              我已核对专业确认依据、本人正式档案来源及所选体重版本，确认本次内容对应同一人
            </a-checkbox>
            <div class="actions">
              <a-button
                type="primary"
                :loading="saving"
                :disabled="pendingImport ? busy : !canSubmit"
                @click="submitImport"
              >
                {{ pendingImport ? '重试原导入请求' : '确认并导入专业版本' }}
              </a-button>
            </div>
          </a-form>
        </template>
        <div v-if="pendingImport && !sourceReady" class="actions">
          <a-button :loading="saving" :disabled="busy || !canImport" @click="submitImport"
            >重试原导入请求</a-button
          >
        </div>
      </a-spin>
      <section class="target-block">
        <h3>当前个人营养目标</h3>
        <p class="muted">
          明确填写专业方提供的批准规则代码，使用当前服务版本计算。导入完成后，目标仍可能需要补充或专业复核。
        </p>
        <a-form layout="vertical">
          <a-form-item label="批准规则代码">
            <a-input
              v-model:value="ruleCode"
              :disabled="busy || calculating"
              :maxlength="80"
              aria-label="批准规则代码"
            />
          </a-form-item>
          <a-button
            :loading="calculating"
            :disabled="busy || calculating || !currentProfile || !ruleCode.trim()"
            @click="calculateTargets"
            >读取规则并计算当前目标</a-button
          >
        </a-form>
        <a-alert v-if="targetError" type="error" show-icon :message="targetError" />
        <a-alert
          v-if="rule && rule.status !== 'ready'"
          type="warning"
          show-icon
          :message="reasonText(rule.reason, true)"
        />
        <p v-if="rule?.version" class="muted">
          批准规则版本 {{ rule.version }} · 专业档案版本 {{ currentProfile?.version || '尚无' }}
        </p>
        <template v-if="targets">
          <a-alert
            v-if="targets.status !== 'ready'"
            type="warning"
            show-icon
            :message="reasonText(targets.reason)"
          />
          <template v-else>
            <p role="status">当前目标已计算：能量 {{ targets.energy_kcal }} kcal / 日</p>
            <dl class="target-values">
              <template v-for="(bounds, key) in targets.bounds" :key="key">
                <dt>{{ nutrientLabels[key]?.[0] || key }}</dt>
                <dd>{{ bounds.minimum }}–{{ bounds.maximum }} {{ targets.units?.[key] }} / 日</dd>
              </template>
            </dl>
            <p class="muted">
              计算依据：专业档案版本 {{ targets.sources?.profile?.version }} · 批准规则版本
              {{ targets.sources?.rules?.version }}。目标计算不代表餐单已经专业批准。
            </p>
            <a-button :disabled="busy || !!pendingImport" @click="openPlans">前往餐单草稿</a-button>
          </template>
        </template>
      </section>
    </template>
  </section>
</template>

<style scoped lang="less">
.professional-profile {
  padding: 24px;
  border: 1px solid var(--gray-150);
  border-radius: 8px;
  background: var(--gray-0);
  color: var(--color-text);
  min-width: 0;
}
.heading,
.actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.heading {
  margin-bottom: 16px;
}
h2 {
  margin: 0;
  font-size: 18px;
}
h3 {
  margin: 0 0 12px;
  font-size: 16px;
}
.muted {
  color: var(--color-text-secondary);
  font-size: 13px;
  line-height: 1.6;
}
p,
dd {
  overflow-wrap: anywhere;
}
.actions {
  justify-content: flex-start;
  margin: 12px 0;
}
.source-block,
.target-block,
.import-form {
  margin-top: 24px;
}
.metadata-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 16px;
}
.formal-fields,
.target-values {
  display: grid;
  grid-template-columns: minmax(100px, auto) minmax(0, 1fr);
  gap: 8px 16px;
  dd {
    margin: 0;
  }
}
.target-block {
  border-top: 1px solid var(--gray-150);
  padding-top: 24px;
}
.target-block :deep(.ant-form) {
  max-width: 640px;
}
.professional-profile > :deep(.ant-alert),
.target-block > :deep(.ant-alert) {
  margin: 12px 0;
}
details {
  margin: 12px 0;
}
summary {
  cursor: pointer;
}
pre {
  max-height: 320px;
  overflow: auto;
  padding: 12px;
  background: var(--gray-10);
  border-radius: 6px;
}
@media (max-width: 768px) {
  .professional-profile {
    padding: 16px;
  }
  .metadata-fields {
    grid-template-columns: 1fr;
  }
}
</style>
