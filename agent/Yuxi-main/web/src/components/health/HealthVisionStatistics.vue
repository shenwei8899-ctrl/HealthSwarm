<script setup>
import { ref, watch, onBeforeUnmount } from 'vue'
import { healthVisionApi as api } from '@/apis/health_vision_api'

const props = defineProps({
  memberId: { type: String, default: '' },
  kind: { type: String, required: true },
  allowed: { type: Boolean, default: false }
})
const expanded = ref(false)
const summary = ref(null)
const loading = ref(false)
const error = ref('')
let sequence = 0
let disposed = false
const states = {
  pending: '排队',
  running: '运行',
  success: '执行成功',
  failed: '失败',
  cancelled: '取消'
}
const portions = { unknown: '未知', estimated: '估算', weighed: '称重', manual: '手动克数' }

/** 刷新清除旧值；迟到响应不能覆盖另一成员、用途或授权状态。 */
async function load() {
  const attempt = ++sequence
  summary.value = null
  error.value = ''
  loading.value = false
  if (!props.memberId || !props.allowed) return
  const memberId = props.memberId
  const kind = props.kind
  const current = () =>
    !disposed &&
    attempt === sequence &&
    props.allowed &&
    props.memberId === memberId &&
    props.kind === kind
  loading.value = true
  try {
    const result = await api.statistics(memberId, kind)
    if (current()) summary.value = result
  } catch (cause) {
    if (current()) error.value = cause.message || '统计暂不可用'
  } finally {
    if (!disposed && attempt === sequence) loading.value = false
  }
}

function toggle(event) {
  expanded.value = event.target.open
  if (expanded.value && !summary.value && !loading.value) void load()
}

watch(
  () => [props.memberId, props.kind, props.allowed],
  () => {
    sequence++
    expanded.value = false
    summary.value = null
    loading.value = false
    error.value = ''
  }
)
onBeforeUnmount(() => {
  disposed = true
  sequence++
})
const seconds = (value) => (value == null ? '暂无样本' : `${value} 秒`)
const rate = (value) => (value == null ? '暂无样本' : `${value}%`)
</script>

<template>
  <details class="vision-statistics" :open="expanded" @toggle="toggle">
    <summary>查看当前成员的{{ kind === 'report' ? '报告' : '饮食' }}运行统计</summary>
    <div class="statistics-body" aria-live="polite">
      <p v-if="!allowed || !memberId">请先选择具有本用途查看权限的成员。</p>
      <a-spin v-else-if="loading" tip="读取统计中" />
      <template v-else>
        <div class="statistics-heading">
          <span>近 30 天 · 仅当前仍可访问的数据</span>
          <a-button size="small" @click="load">刷新统计</a-button>
        </div>
        <a-alert v-if="error" type="error" :message="error" show-icon />
        <template v-else-if="summary">
          <p v-if="!summary.tasks.sample_count && !summary.reviews.confirmed_drafts">
            暂无任务或已确认复核样本。
          </p>
          <p>
            任务 {{ summary.tasks.sample_count }} 次：
            <span v-for="(count, state) in summary.tasks.states" :key="state"
              >{{ states[state] || state }} {{ count }} 次；</span
            >
            <span v-if="summary.tasks.partial_report_count"
              >其中 {{ summary.tasks.partial_report_count }} 次报告仅部分页面完成。</span
            >
          </p>
          <div class="timing-grid">
            <div>
              <h3>排队耗时</h3>
              <p>
                中位数 {{ seconds(summary.tasks.queue.p50_seconds) }} · P95
                {{ seconds(summary.tasks.queue.p95_seconds) }}
              </p>
              <small>有开始时间的 {{ summary.tasks.queue.sample_count }} 次任务</small>
            </div>
            <div>
              <h3>执行耗时</h3>
              <p>
                中位数 {{ seconds(summary.tasks.execution.p50_seconds) }} · P95
                {{ seconds(summary.tasks.execution.p95_seconds) }}
              </p>
              <small>有完整时间点的 {{ summary.tasks.execution.sample_count }} 次终态任务</small>
            </div>
          </div>
          <p>
            失败原因：<template v-if="Object.keys(summary.tasks.failure_codes).length"
              ><span v-for="(count, code) in summary.tasks.failure_codes" :key="code"
                >{{ code }} {{ count }} 次；</span
              ></template
            ><span v-else>暂无失败样本</span>
          </p>
          <p>
            {{ kind === 'report' ? '报告字段修改比例' : '菜品名称修改比例' }}：{{
              rate(summary.reviews.modification_rate_percent)
            }}（修改 {{ summary.reviews.modified_items }} / 原始
            {{ summary.reviews.original_items }} 项）。
          </p>
          <p>
            已确认 {{ summary.reviews.confirmed_drafts }} 份，其中模型草稿
            {{ summary.reviews.model_drafts }} 份；模型原始项排除
            {{ summary.reviews.excluded_items }} 项，人工新增 {{ summary.reviews.added_items }} 项。
          </p>
          <template v-if="kind === 'meal'">
            <p>
              营养数据不完整：{{ rate(summary.nutrition.incomplete_rate_percent) }}（{{
                summary.nutrition.incomplete_count
              }}
              / {{ summary.nutrition.sample_count }} 份已确认日记）。
            </p>
            <p>
              份量来源：<span
                v-for="(count, source) in summary.nutrition.portion_sources"
                :key="source"
                >{{ portions[source] || source }} {{ count }} 项；</span
              ><span v-if="!Object.keys(summary.nutrition.portion_sources).length">暂无样本</span>
            </p>
          </template>
          <p class="statistics-note">
            任务按创建时间、复核按确认时间统计。P95
            为最近秩百分位；未知或异常耗时不记为零。仅比较已确认模型原始项{{
              kind === 'report'
                ? '的名称、代码、结果、单位和参考范围，日期及空腹补充不计修改'
                : '的名称，食品映射及填写份量不计修改'
            }}。修改比例与执行成功均不是识别准确率。
          </p>
          <p class="statistics-note">费用：未知。{{ summary.cost.reason }}。</p>
        </template>
      </template>
    </div>
  </details>
</template>

<style scoped lang="less">
.vision-statistics {
  margin-bottom: 24px;
  border: 1px solid var(--gray-150);
  border-radius: 8px;
  background: var(--gray-0);
  color: var(--color-text);
  summary {
    cursor: pointer;
    padding: 16px 20px;
    font-weight: 600;
  }
  summary:focus-visible {
    outline: 2px solid var(--main-color);
    outline-offset: 2px;
  }
}
.statistics-body {
  padding: 0 20px 20px;
  p {
    margin: 12px 0;
    overflow-wrap: anywhere;
  }
}
.statistics-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.timing-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  h3 {
    font-size: 14px;
    margin: 12px 0 0;
  }
}
.statistics-note,
small {
  color: var(--color-text-secondary);
  font-size: 12px;
  line-height: 1.6;
}
@media (max-width: 640px) {
  .timing-grid {
    grid-template-columns: 1fr;
  }
  .statistics-heading {
    flex-wrap: wrap;
  }
}
</style>
