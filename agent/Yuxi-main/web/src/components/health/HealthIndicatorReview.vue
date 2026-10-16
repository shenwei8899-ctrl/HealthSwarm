<script setup>
import { ref, watch, onBeforeUnmount } from 'vue'
import { healthVisionApi as api } from '@/apis/health_vision_api'
import { useUserStore } from '@/stores/user'

const props = defineProps({ memberId: String, kind: String, allowed: Boolean })
const emit = defineEmits(['selection'])
const user = useUserStore()
const today = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Shanghai',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit'
}).format(new Date())
const start = ref(today),
  end = ref(today),
  report = ref(null),
  selected = ref([]),
  error = ref(''),
  busy = ref(false)
let epoch = 0
const conditions = {
  fasting: '空腹',
  after_meal_2h: '餐后2小时',
  random: '随机',
  same_observation: '同条测量'
}
const fields = {
  glucose: '血糖',
  systolic: '收缩压',
  diastolic: '舒张压',
  tc: '总胆固醇',
  tg: '甘油三酯',
  hdl: '高密度脂蛋白',
  ldl: '低密度脂蛋白'
}

/** 日期与身份变化清除旧事实和会话选择。 */
function reset() {
  epoch++
  report.value = null
  selected.value = []
  busy.value = false
  error.value = ''
  emit('selection', null)
}
/** 统计与记录选择均由服务端按当前版本重新核对。 */
async function read(onlySelected = false) {
  if (busy.value || !props.allowed) return
  const refs = onlySelected
    ? selected.value
        .map((id) => report.value.records.find((row) => row.record_id === id))
        .map((row) => ({ record_id: row.record_id, version: row.version }))
    : []
  const selection = { start_date: start.value, end_date: end.value, records: refs }
  if (onlySelected && !refs.length) return
  const ticket = ++epoch
  busy.value = true
  error.value = ''
  report.value = null
  emit('selection', null)
  try {
    const result = await api.indicatorReview(props.memberId, props.kind, selection)
    if (ticket !== epoch) return
    report.value = result
    selected.value = []
    emit('selection', result.selection)
  } catch (exc) {
    if (ticket === epoch) error.value = exc.message
  } finally {
    if (ticket === epoch) busy.value = false
  }
}
watch(() => [props.memberId, props.kind, props.allowed, user.uid, start.value, end.value], reset, {
  flush: 'sync'
})
onBeforeUnmount(reset)
</script>
<template>
  <section class="fact-review">
    <h3>实测记录回顾</h3>
    <p>按北京时间选择最多366天。这里只统计原始记录；血糖按测量条件分别统计，不作诊断。</p>
    <div class="controls">
      <label>开始日期 <input v-model="start" type="date" /></label>
      <label>结束日期 <input v-model="end" type="date" /></label>
      <a-button :disabled="busy || !allowed" @click="read()">读取记录与统计</a-button>
    </div>
    <a-spin v-if="busy" tip="正在读取实测记录" />
    <a-alert v-if="error" :message="error" type="error" show-icon />
    <template v-if="report">
      <p>
        范围内 {{ report.total }} 条，本次回顾 {{ report.records.length }} 条<span
          v-if="report.truncated"
          >；已截断，请缩短范围或选择记录</span
        >。
      </p>
      <a-empty v-if="!report.records.length" description="所选范围没有可用实测记录" />
      <div class="records">
        <label v-for="record in report.records" :key="record.record_id" class="record">
          <input v-model="selected" type="checkbox" :value="record.record_id" />
          <span
            >{{
              new Date(record.measured_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })
            }}
            · {{ conditions[record.condition] || '同条测量' }} · v{{ record.version }}</span
          >
          <span v-for="(name, key) in fields" :key="key"
            ><template v-if="record[key] !== undefined"
              >{{ name }} {{ record[key] }} {{ record.unit }}
            </template></span
          >
          <small>来源：{{ record.source }}</small>
        </label>
      </div>
      <a-button
        v-if="report.records.length"
        :disabled="!selected.length || busy"
        @click="read(true)"
        >仅回顾勾选记录</a-button
      >
      <div v-for="group in report.review.groups" :key="group.condition" class="summary">
        <strong>{{ conditions[group.condition] }}</strong>
        <p v-for="(value, key) in group.statistics" :key="key">
          {{ fields[key] || key }}：{{ value.count }} 次 · 均值 {{ value.mean }} · 最低
          {{ value.minimum }} · 最高 {{ value.maximum }} {{ report.records[0]?.unit }}
        </p>
      </div>
      <p v-for="question in report.review.questions" :key="question">{{ question }}</p>
      <small>统计仅覆盖本次返回记录。审核知识解释尚未请求，暂无引用；不产生个体化建议。</small>
    </template>
  </section>
</template>
<style scoped>
.fact-review {
  border: 1px solid var(--gray-200);
  border-radius: 10px;
  padding: 16px;
  margin: 16px 0;
  color: var(--gray-1000);
  background: var(--gray-0);
}
.controls {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}
.controls label {
  display: flex;
  gap: 8px;
  align-items: center;
}
input {
  color: var(--gray-1000);
  background: var(--gray-0);
  border: 1px solid var(--gray-300);
  border-radius: 4px;
  padding: 5px;
  max-width: 100%;
}
.records {
  max-height: 350px;
  overflow: auto;
  margin: 12px 0;
}
.record {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding: 10px 0;
  border-bottom: 1px solid var(--gray-150);
}
.summary {
  margin-top: 14px;
}
p,
small {
  overflow-wrap: anywhere;
  color: var(--gray-600);
}
</style>
