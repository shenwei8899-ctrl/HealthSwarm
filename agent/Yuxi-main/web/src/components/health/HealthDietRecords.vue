<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { healthVisionApi as api } from '@/apis/health_vision_api'
import { mealLabels, nutrientLabels, nutrientText } from '@/utils/healthVision'
import HealthMealFeedback from './HealthMealFeedback.vue'
import HealthFeedbackConversation from './HealthFeedbackConversation.vue'

const props = defineProps({
  memberId: { type: String, default: '' },
  scopes: { type: Array, default: () => [] },
  configuration: { type: Object, required: true },
  disabled: { type: Boolean, default: false }
})
const canRead = computed(() => !!props.memberId && props.scopes.includes('diet_edit'))
const records = ref([])
const offset = ref(0)
const nextOffset = ref(null)
const loading = ref(false)
const error = ref('')
const pageSize = 20
const pageNumber = computed(() => Math.floor(offset.value / pageSize) + 1)
let sequence = 0
let disposed = false

/** 翻页先清除旧数据；只接收当前成员、授权与最新请求的响应。 */
async function readPage(targetOffset) {
  const ticket = ++sequence
  records.value = []
  nextOffset.value = null
  error.value = ''
  offset.value = targetOffset
  if (!canRead.value || disposed) {
    loading.value = false
    return
  }
  const id = props.memberId
  const current = () => !disposed && ticket === sequence && id === props.memberId && canRead.value
  loading.value = true
  try {
    const result = await api.dietLogPage(id, pageSize, targetOffset)
    if (!current()) return
    records.value = result.records
    nextOffset.value = result.next_offset
  } catch (exc) {
    if (!current()) return
    error.value =
      exc.status === 404
        ? '成员不存在或饮食记录授权已变化，请重新核对授权。'
        : '读取饮食记录失败，请重试。'
  } finally {
    if (current()) loading.value = false
  }
}

/** 刷新回到最新记录；上一页和下一页只在已读取页上移动。 */
function reload() {
  return readPage(0)
}
function previousPage() {
  if (loading.value || props.disabled || error.value || offset.value === 0) return
  return readPage(Math.max(0, offset.value - pageSize))
}
function nextPage() {
  if (loading.value || props.disabled || error.value || nextOffset.value === null) return
  return readPage(nextOffset.value)
}

watch(() => [props.memberId, canRead.value], reload, { immediate: true })
onBeforeUnmount(() => {
  disposed = true
  sequence++
  records.value = []
})
</script>

<template>
  <section class="panel diet-records">
    <h2>已确认饮食日记</h2>
    <p class="page-help">按确认入库时间从新到旧，每页最多20条；失效来源不展示。</p>
    <a-alert v-if="!canRead" type="warning" message="当前成员没有饮食记录授权" show-icon />
    <template v-else>
      <div class="paging" aria-label="饮食记录分页">
        <a-button :disabled="loading || disabled" @click="reload">刷新到第一页</a-button>
        <a-button :disabled="loading || disabled || !!error || offset === 0" @click="previousPage"
          >上一页</a-button
        >
        <span aria-live="polite">第 {{ pageNumber }} 页 · {{ records.length }} 条</span>
        <a-button
          :disabled="loading || disabled || !!error || nextOffset === null"
          @click="nextPage"
          >下一页</a-button
        >
      </div>
      <a-spin v-if="loading" tip="正在读取饮食记录" />
      <a-alert v-else-if="error" type="error" :message="error" show-icon>
        <template #action
          ><a-button :disabled="disabled" @click="readPage(offset)">重试本页</a-button></template
        >
      </a-alert>
      <a-empty
        v-else-if="!records.length"
        :description="
          nextOffset === null
            ? '本页没有可展示的已确认饮食记录'
            : '本页来源已失效，可继续查看下一页'
        "
      />
      <div v-for="record in records" :key="record.id" class="record">
        <strong
          >{{ mealLabels[record.snapshot.meal.meal_type] }} ·
          {{ new Date(record.snapshot.meal.eaten_at).toLocaleString() }}</strong
        >
        <a-tag v-if="record.snapshot.nutrition.estimated" color="orange">估算</a-tag>
        <p v-for="([label, unit], key) in nutrientLabels" :key="key">
          {{ label }}：{{ nutrientText(record.snapshot.nutrition.totals[key], unit) }}
        </p>
        <small>计算版本：{{ record.snapshot.nutrition.calculation_version }}</small>
        <HealthMealFeedback :record="record" />
        <HealthFeedbackConversation
          :key="`feedback-${memberId}-${record.id}`"
          :member-id="memberId"
          :scopes="scopes"
          :configuration="configuration"
          :record="record"
          :disabled="disabled"
        />
      </div>
    </template>
  </section>
</template>

<style scoped>
.diet-records {
  border: 1px solid var(--gray-200);
  border-radius: 12px;
  padding: 24px;
  background: var(--gray-0);
  min-width: 0;
}
h2 {
  font-size: 17px;
  margin-bottom: 12px;
}
.page-help {
  color: var(--gray-600);
}
.paging {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin: 16px 0;
}
.record {
  padding: 16px 0;
  border-bottom: 1px solid var(--gray-200);
  overflow-wrap: anywhere;
}
.record p {
  margin: 6px 0;
}
small {
  color: var(--gray-600);
}
@media (max-width: 600px) {
  .diet-records {
    padding: 14px;
  }
}
</style>
