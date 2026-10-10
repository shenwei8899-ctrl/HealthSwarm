<script setup>
import { computed } from 'vue'
import { mealLabels, nutrientLabels, nutrientText } from '@/utils/healthVision'

const props = defineProps({ result: { type: Object, required: true } })
const feedbackResult = computed(() => props.result.result_type === 'meal_feedback')
const period = computed(() => props.result.scope === 'confirmed_period')
const questions = computed(() => props.result.status === 'needs_input')
const datesWithoutRecords = computed(() => {
  const dates = props.result.coverage?.dates_without_records
  return Array.isArray(dates) && dates.every((date) => typeof date === 'string') ? dates : null
})
const title = computed(() =>
  questions.value
    ? '请补充信息'
    : feedbackResult.value
      ? '这餐反馈已保存'
      : period.value
        ? '已确认饮食统计'
        : '这餐饮食分析'
)
const rows = computed(() =>
  Object.entries(nutrientLabels).map(([code, [label, unit]]) => ({
    code,
    label,
    unit,
    value: props.result.nutrition?.totals?.[code]
  }))
)
const consumptionLabels = {
  unknown: '未填写',
  all: '全部吃完',
  most: '大部分',
  half: '一半',
  little: '少量',
  none: '未吃'
}
const tagLabels = {
  too_salty: '偏咸',
  too_oily: '偏油',
  too_sweet: '偏甜',
  too_spicy: '偏辣',
  portion_large: '份量多',
  portion_small: '份量少',
  discomfort: '餐后不适'
}

/** 覆盖条数保留零，缺失条数不猜测。 */
function count(value) {
  return Number.isInteger(value) && value >= 0 ? value : '未知'
}

/** 只格式化服务器已有时间，不从消息时间推断进食时间。 */
function mealTime(value) {
  return value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' }) : '时间未知'
}
</script>

<template>
  <section class="diet-analysis-result">
    <h3>{{ title }}</h3>
    <template v-if="questions">
      <ul class="questions">
        <li v-for="question in result.questions" :key="question">{{ question }}</li>
      </ul>
      <p class="hint">
        请在下方消息框补充这些信息。{{
          feedbackResult
            ? '反馈仍关联原选定餐次，以服务器保存收据为准。'
            : '信息不足时仅追问，不补写缺失营养值。'
        }}
      </p>
    </template>
    <template v-else-if="feedbackResult">
      <p>这次反馈关联原选定的一餐，已保存版本 {{ result.feedback.version }}。</p>
      <dl class="feedback-details">
        <dt>吃完程度（自述）</dt>
        <dd>{{ consumptionLabels[result.feedback.details.consumption] || '未知' }}</dd>
        <dt>这餐的体验</dt>
        <dd>
          {{
            result.feedback.details.tags.map((tag) => tagLabels[tag] || '未识别标签').join('、') ||
            '未填写标签'
          }}
        </dd>
        <dt>补充说明</dt>
        <dd>{{ result.feedback.details.comment || '无补充说明' }}</dd>
      </dl>
      <p class="hint">
        反馈是用户自述，原饮食记录和营养计算保持不变。可在“已确认记录 → 餐后反馈”核对或撤回。
      </p>
    </template>
    <template v-else>
      <p v-if="period">
        {{ result.window.start_date }} 至 {{ result.window.end_date }} ·
        {{ result.window.period_days }} 个北京时间自然日
      </p>
      <p v-else>
        {{ mealLabels[result.meal_type] || '已确认餐次' }} · {{ mealTime(result.eaten_at) }}
      </p>
      <p v-if="period">
        {{ count(result.coverage.days_with_records) }} 天有记录，共
        {{ count(result.coverage.record_count) }} 条有效确认记录。{{
          count(result.coverage.excluded_invalidated_records)
        }}
        条失效来源已排除。
      </p>
      <p v-else>
        共 {{ count(result.coverage.recorded_items) }} 项已确认食物，{{
          count(result.coverage.calculated_items)
        }}
        项纳入原计算；{{ count(result.coverage.known_nutrients) }} /
        {{ count(result.coverage.supported_nutrients) }} 项营养值已知。
      </p>
      <p v-if="period" class="unrecorded-dates">
        未记录日期（{{ datesWithoutRecords ? datesWithoutRecords.length : '未知' }} 天）：{{
          datesWithoutRecords ? datesWithoutRecords.join('、') || '无' : '未知'
        }}。未记录不代表未进食。
      </p>
      <p v-if="period && result.coverage.record_count === 0" class="hint">
        范围内暂无有效已确认饮食。请先复核饮食照片或人工录入并确认；未记录不代表未进食。
      </p>
      <ul v-if="!period && result.items.length" class="meal-items">
        <li v-for="item in result.items" :key="item.item_id">
          {{ item.name }} · 食用份量 {{ nutrientText(item.eaten_grams, 'g') }}
        </li>
      </ul>
      <a-tag v-if="result.nutrition.estimated" color="orange">含估算项</a-tag>
      <div class="nutrition-table-wrap">
        <table class="nutrition-table">
          <thead>
            <tr>
              <th scope="col">营养项</th>
              <th scope="col">{{ period ? '确认记录总和' : '确认记录值' }}</th>
              <template v-if="period"
                ><th scope="col">已知部分之和</th>
                <th scope="col">有数值 / 缺数值条数</th></template
              >
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.code">
              <th scope="row">{{ row.label }}</th>
              <td>{{ nutrientText(period ? row.value?.recorded_total : row.value, row.unit) }}</td>
              <template v-if="period"
                ><td>{{ nutrientText(row.value?.known_sum, row.unit) }}</td>
                <td>
                  {{ count(row.value?.known_records) }} / {{ count(row.value?.missing_records) }}
                </td></template
              >
            </tr>
          </tbody>
        </table>
      </div>
      <p class="hint">
        未知值不会按零计算。已知部分之和只覆盖有数值的确认记录，不能代表缺失记录或未记录天数的摄入。
      </p>
      <p v-if="period" class="hint">
        餐后反馈
        {{ count(result.feedback?.count) }}
        条，属于用户自述；不会按吃完程度重算营养。趋势规则和最低样本未批准时，当前仅展示统计事实。
      </p>
      <p class="hint">仅说明已确认记录事实；这里不判断疾病适用性或营养是否达标。</p>
    </template>
  </section>
</template>

<style scoped lang="less">
.diet-analysis-result {
  padding: 16px;
  border: 1px solid var(--gray-200);
  border-radius: 8px;
  background: var(--gray-0);
  color: var(--gray-1000);
  h3 {
    margin: 0 0 12px;
    font-size: 16px;
  }
  p {
    margin: 8px 0;
  }
}
.hint {
  color: var(--gray-600);
  font-size: 13px;
  line-height: 1.7;
}
.questions,
.meal-items {
  padding-left: 20px;
  li {
    margin: 6px 0;
    overflow-wrap: anywhere;
  }
}
.unrecorded-dates {
  overflow-wrap: anywhere;
}
.feedback-details {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 8px 16px;
  dt {
    color: var(--gray-600);
  }
  dd {
    margin: 0;
    overflow-wrap: anywhere;
  }
}
.nutrition-table-wrap {
  overflow-x: auto;
  margin: 12px 0;
}
.nutrition-table {
  width: 100%;
  border-collapse: collapse;
  th,
  td {
    padding: 8px 12px;
    border-bottom: 1px solid var(--gray-200);
    text-align: left;
    white-space: nowrap;
  }
  th {
    font-weight: 500;
  }
  thead {
    background: var(--gray-50);
  }
}
@media (max-width: 600px) {
  .diet-analysis-result {
    padding: 12px;
  }
  .feedback-details {
    grid-template-columns: minmax(0, 1fr);
    gap: 4px;
    dd {
      margin-bottom: 8px;
    }
  }
}
</style>
