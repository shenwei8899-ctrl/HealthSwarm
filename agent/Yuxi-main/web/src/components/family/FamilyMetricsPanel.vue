<template>
  <section>
    <div class="section-heading">
      <div>
        <h2>{{ member.name }}的健康指标</h2>
        <p class="muted">实测记录 · 单位与测量条件分别保留</p>
      </div>
      <a-button v-if="available.length" type="primary" class="lucide-icon-btn" @click="openNew"
        ><Plus :size="16" />记录指标</a-button
      >
    </div>
    <a-empty v-if="!available.length" description="当前没有健康指标访问权限，请由成员本人授权。" />
    <template v-else>
      <div class="metric-toolbar">
        <a-select
          v-model:value="kind"
          aria-label="选择健康指标"
          :options="available"
          style="min-width: 145px"
        />
        <a-select
          v-model:value="days"
          aria-label="选择统计期间"
          :options="periods"
          style="width: 115px"
        />
        <a-select
          v-if="kind === 'blood_glucose'"
          v-model:value="condition"
          aria-label="选择血糖测量条件"
          :options="Object.entries(conditionLabels).map(([value, label]) => ({ value, label }))"
          style="width: 130px"
        />
        <span class="muted">时间均按北京时间显示</span>
      </div>
      <a-alert v-if="error" type="error" :message="error" show-icon
        ><template #action><a-button @click="load">重试</a-button></template></a-alert
      >
      <a-spin :spinning="loading">
        <p v-if="loading" class="muted">正在加载指标记录…</p>
        <template v-if="!error && !loading">
          <div class="measurement-summary">
            <div>
              <span class="muted">期间记录</span
              ><strong>{{ filtered.length }}<small> 条</small></strong>
            </div>
            <div>
              <span class="muted">最近实测</span><strong>{{ latestValue }}</strong>
            </div>
            <div>
              <span class="muted">测量时间</span>
              <p>{{ formatTime(filtered[0]?.measured_at) }}</p>
            </div>
          </div>
          <FamilyChart
            v-if="filtered.length"
            :dates="dates"
            :series="series"
            :unit="definition.unit"
            :label="member.name + '的' + definition.label + '趋势，仅展示实测数据'"
          />
          <a-empty v-else description="所选期间尚无此类记录，可以手动记录实测值。" />
          <p class="muted chart-note">
            趋势显示每日最近一次实测，缺失日期保留空白；下表保留全部已查询记录。
          </p>
          <a-alert
            v-if="truncated"
            type="warning"
            message="当前最多展示1000条记录，请缩短查询期间；统计概览仍按全部有效记录计算。"
          />
          <div class="table-scroll">
            <table class="family-table">
              <thead>
                <tr>
                  <th>测量时间</th>
                  <th>实测值</th>
                  <th>测量条件</th>
                  <th>来源</th>
                  <th>版本</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="record in filtered" :key="record.id">
                  <td>{{ formatTime(record.measured_at) }}</td>
                  <td>{{ recordValue(record) }}</td>
                  <td>{{ conditionLabels[record.condition] || '—' }}</td>
                  <td>{{ sourceLabels[record.source] || record.source }}</td>
                  <td>v{{ record.version }}</td>
                  <td><a-button type="link" @click="openCorrection(record)">更正</a-button></td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </a-spin>
    </template>
    <a-modal
      v-model:open="dialogOpen"
      :title="correcting ? '更正测量记录' : '记录健康指标'"
      :confirm-loading="saving"
      @ok="save"
    >
      <a-form layout="vertical" :model="draft" name="family-measurement">
        <a-form-item label="健康指标">{{ definition.label }} · {{ definition.unit }}</a-form-item>
        <a-form-item
          v-for="(label, key) in definition.fields"
          :name="['values', key]"
          :key="key"
          :label="label + '（' + definition.unit + '）'"
          required
        >
          <a-input-number
            v-model:value="draft.values[key]"
            :min="0.01"
            :step="kind === 'blood_pressure' ? 1 : 0.1"
            style="width: 100%"
          />
        </a-form-item>
        <a-form-item name="measured_at" label="测量时间（北京时间）" required
          ><a-input
            v-model:value="draft.measured_at"
            type="datetime-local"
            :disabled="!!correcting"
        /></a-form-item>
        <a-form-item v-if="kind === 'blood_glucose'" name="condition" label="测量条件" required>
          <a-select
            v-model:value="draft.condition"
            :disabled="!!correcting"
            :options="Object.entries(conditionLabels).map(([value, label]) => ({ value, label }))"
          />
        </a-form-item>
        <a-form-item name="source" label="数据来源"
          ><a-select
            v-model:value="draft.source"
            :disabled="!!correcting"
            :options="Object.entries(sourceLabels).map(([value, label]) => ({ value, label }))"
        /></a-form-item>
        <a-form-item name="note" :label="correcting ? '更正说明（必填）' : '备注'"
          ><a-textarea v-model:value="draft.note" :rows="2" :maxlength="1000"
        /></a-form-item>
      </a-form>
      <p v-if="correcting" class="muted">更正保留旧值和版本，原测量时间与来源保持不变。</p>
      <a-alert v-if="saveError" type="error" :message="saveError" show-icon />
    </a-modal>
    <details
      v-for="record in filtered.filter((row) => row.previous.length)"
      :key="record.id"
      class="correction-history"
    >
      <summary>{{ formatTime(record.measured_at) }}的更正历史</summary>
      <p v-for="old in record.previous" :key="old.version">
        v{{ old.version }}：{{ recordValue({ values: old.values }) }} ·
        {{ formatTime(old.corrected_at) }}
      </p>
    </details>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { Plus } from '@lucide/vue'
import { message } from 'ant-design-vue'
import { familyApi } from '@/apis/family_api'
import FamilyChart from './FamilyChart.vue'
import {
  metricDefinitions,
  conditionLabels,
  buildMetricSeries,
  shanghaiDate,
  formatTime
} from '@/utils/familyArchives'

const props = defineProps({
  familyId: { type: String, required: true },
  member: { type: Object, required: true },
  revision: { type: Number, default: 0 }
})
const emit = defineEmits(['changed'])
const available = computed(() =>
  Object.entries(metricDefinitions)
    .filter(([key]) => props.member.allowed_fields.includes(key))
    .map(([value, item]) => ({ value, label: item.label }))
)
const kind = ref(available.value[0]?.value || 'weight'),
  days = ref(30),
  condition = ref('fasting')
const periods = [
  { value: 7, label: '近7天' },
  { value: 30, label: '近30天' },
  { value: 90, label: '近90天' }
]
const definition = computed(() => metricDefinitions[kind.value])
const records = ref([]),
  loading = ref(false),
  error = ref(''),
  truncated = ref(false)
const dialogOpen = ref(false),
  saving = ref(false),
  saveError = ref(''),
  correcting = ref(null)
const draft = reactive({
  values: {},
  measured_at: '',
  source: 'manual',
  condition: '',
  note: '',
  id: ''
})
const sourceLabels = {
  manual: '本人/照护人手动录入',
  device: '设备实测后录入',
  report: '检验报告录入'
}
let generation = 0
const filtered = computed(() =>
  records.value.filter((row) => kind.value !== 'blood_glucose' || row.condition === condition.value)
)
const dates = computed(() => {
  const anchor = new Date(shanghaiDate(Date.now()) + 'T00:00:00Z')
  return Array.from({ length: days.value }, (_, index) =>
    new Date(anchor.getTime() - (days.value - index - 1) * 86400000).toISOString().slice(0, 10)
  )
})
const series = computed(() =>
  Object.entries(definition.value.fields).map(([key, name]) => ({
    name,
    data: buildMetricSeries(filtered.value, key, dates.value)
  }))
)
const latestValue = computed(() => (filtered.value[0] ? recordValue(filtered.value[0]) : '未记录'))
function recordValue(record) {
  return (
    Object.entries(definition.value.fields)
      .map(([key, label]) =>
        Object.keys(definition.value.fields).length > 1
          ? label + ' ' + record.values[key]
          : record.values[key]
      )
      .join(' / ') +
    ' ' +
    definition.value.unit
  )
}
async function load() {
  const current = ++generation
  records.value = []
  error.value = ''
  if (!available.value.some((option) => option.value === kind.value)) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const result = await familyApi.measurements(props.familyId, props.member.id, {
      kind: kind.value,
      days: days.value
    })
    if (current === generation) {
      records.value = result.items
      truncated.value = result.truncated
    }
  } catch (cause) {
    if (current === generation) error.value = cause.message
  } finally {
    if (current === generation) loading.value = false
  }
}
watch(
  () => [props.familyId, props.member, kind.value, days.value],
  () => {
    if (!available.value.some((item) => item.value === kind.value))
      kind.value = available.value[0]?.value || 'weight'
    dialogOpen.value = false
    draft.values = {}
    draft.note = ''
    correcting.value = null
    load()
  },
  { immediate: true }
)
watch(() => props.revision, load)
onBeforeUnmount(() => {
  generation++
  records.value = []
  draft.values = {}
  draft.note = ''
  correcting.value = null
})
function openNew() {
  correcting.value = null
  draft.id = crypto.randomUUID()
  draft.values = Object.fromEntries(Object.keys(definition.value.fields).map((key) => [key, null]))
  draft.measured_at = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  })
    .format(new Date())
    .replace(' ', 'T')
  draft.source = 'manual'
  draft.condition = condition.value
  draft.note = ''
  saveError.value = ''
  dialogOpen.value = true
}
function openCorrection(record) {
  correcting.value = record
  draft.values = { ...record.values }
  draft.measured_at = new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  })
    .format(new Date(record.measured_at))
    .replace(' ', 'T')
  draft.source = record.source
  draft.condition = record.condition
  draft.note = ''
  saveError.value = ''
  dialogOpen.value = true
}
async function save() {
  if (Object.values(draft.values).some((value) => !Number.isFinite(value) || value <= 0)) {
    saveError.value = '请填写完整的实测正数'
    return
  }
  if (!draft.measured_at || (correcting.value && !draft.note.trim())) {
    saveError.value = '请填写测量时间或更正说明'
    return
  }
  saving.value = true
  try {
    if (correcting.value)
      await familyApi.correctMeasurement(props.familyId, props.member.id, correcting.value.id, {
        expected_version: correcting.value.version,
        values: draft.values,
        note: draft.note
      })
    else
      await familyApi.addMeasurement(props.familyId, props.member.id, {
        id: draft.id,
        kind: kind.value,
        values: draft.values,
        measured_at: new Date(draft.measured_at + '+08:00').toISOString(),
        source: draft.source,
        condition: kind.value === 'blood_glucose' ? draft.condition : '',
        note: draft.note
      })
    dialogOpen.value = false
    message.success('记录已保存')
    await load()
    emit('changed')
  } catch (cause) {
    saveError.value = cause.message
  } finally {
    saving.value = false
  }
}
</script>

<style scoped lang="less">
.metric-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin: 20px 0;
}
.measurement-summary {
  display: flex;
  gap: 48px;
  margin: 24px 0;
  > div {
    min-width: 100px;
  }
  strong {
    display: block;
    font-size: 22px;
    margin-top: 4px;
    font-weight: 600;
  }
  small {
    font-size: 14px;
  }
}
.chart-note {
  margin: 12px 0;
}
.correction-history {
  border-top: 1px solid var(--gray-150);
  margin-top: 16px;
  padding: 12px 0;
  summary {
    cursor: pointer;
  }
}
@media (max-width: 600px) {
  .measurement-summary {
    flex-wrap: wrap;
    gap: 20px;
  }
}
</style>
