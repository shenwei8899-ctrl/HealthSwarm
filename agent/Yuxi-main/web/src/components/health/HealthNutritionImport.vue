<script setup>
import { ref, watch, onBeforeUnmount } from 'vue'
import { healthVisionApi as api } from '@/apis/health_vision_api'
import { useUserStore } from '@/stores/user'
const user = useUserStore()
const knowledgeQuery = ref(''), knowledgeTask = ref(null), knowledgePending = ref(null)
let pollTimer = null
const kind = ref('food'),
  text = ref(''),
  report = ref(null),
  busy = ref(false),
  error = ref(''),
  pending = ref(null)
let epoch = 0
const codes = {
  metadata_required: '待补来源/许可/版本',
  duplicate_in_batch: '批次内重复',
  published_version_conflict: '已发布版本冲突',
  unpublished_food: '配方引用未发布食品',
  value_error: '值或营养单位无效',
  missing: '缺少字段',
  extra_forbidden: '不接受此字段'
}
/** 身份变化清除未发布候选，重试不能更改已冻结内容。 */
function reset() {
  epoch++
  text.value = ''
  report.value = null
  pending.value = null
  error.value = ''
  busy.value = false
  knowledgeQuery.value = ''
  knowledgeTask.value = null
  knowledgePending.value = null
  clearTimeout(pollTimer)
}

/** 后台提取保留原片段；页面只读取候选和异常，不自动发布。 */
async function prepareKnowledge() {
  if (busy.value) return
  const ticket = epoch
  busy.value = true
  error.value = ''
  try {
    knowledgePending.value ||= { kind: kind.value, query: knowledgeQuery.value.trim(), client_request_id: crypto.randomUUID() }
    knowledgeTask.value = await api.prepareKnowledgeNutrition(knowledgePending.value)
    if (ticket !== epoch) return
    await pollKnowledge(ticket)
  } catch (exc) {
    if (ticket === epoch) { error.value = exc.message; busy.value = false }
  }
}

async function pollKnowledge(ticket) {
  if (ticket !== epoch || !knowledgeTask.value) return
  try {
    const value = await api.knowledgeNutritionStatus(knowledgeTask.value.task_id)
    if (ticket !== epoch) return
    knowledgeTask.value = value
    if (value.status === 'success') {
      report.value = value.report
      busy.value = false
      knowledgePending.value = null
      return
    }
    if (['failed', 'cancelled'].includes(value.status)) {
      error.value = value.message
      busy.value = false
      knowledgePending.value = null
      return
    }
  } catch (exc) {
    if (ticket !== epoch) return
    error.value = exc.message
    busy.value = false
    return
  }
  pollTimer = setTimeout(() => pollKnowledge(ticket), 2000)
}
/** 候选导入仅登记异常和待审清单。 */
async function prepare() {
  if (busy.value) return
  const ticket = epoch
  busy.value = true
  error.value = ''
  report.value = null
  try {
    if (!pending.value)
      pending.value = {
        kind: kind.value,
        rows: JSON.parse(text.value),
        client_request_id: crypto.randomUUID()
      }
    const value = await api.prepareNutritionImport(pending.value)
    if (ticket !== epoch) return
    report.value = value
    pending.value = null
  } catch (exc) {
    if (ticket !== epoch) return
    if ([400, 401, 403, 409, 422].includes(exc.status)) pending.value = null
    error.value = exc.message
  } finally {
    if (ticket === epoch) busy.value = false
  }
}
watch(() => user.uid, reset)
onBeforeUnmount(reset)
</script>
<template>
  <section class="nutrition-import">
    <h3>批量营养资料导入准备</h3>
    <p>
      粘贴食品或菜谱 JSON 数组，每批最多500行、1MB。食品营养值按每100克填写：能量 kcal，钠 mg，其余
      g；缺失值用 null。
    </p>
    <p>这里只保存候选、异常和待审清单。资料通过专业审核后，再走原有发布流程。</p>
    <a-input v-model:value="knowledgeQuery" :disabled="busy || !!knowledgePending" :maxlength="120" placeholder="从已有知识库整理，例如：燕麦的每百克营养或家常菜配方" />
    <a-button :disabled="busy || !knowledgeQuery.trim()" @click="prepareKnowledge">{{ knowledgePending ? '重试读取原提取任务' : '从已有知识库整理候选' }}</a-button>
    <p v-if="knowledgeTask && busy">后台正在整理资料，退出页面后任务仍会继续。任务 {{ knowledgeTask.task_id }}</p>
    <a-select
      v-model:value="kind"
      :disabled="busy || !!pending"
      :options="[
        { label: '食品候选', value: 'food' },
        { label: '菜谱候选', value: 'recipe' }
      ]"
    />
    <a-textarea
      v-model:value="text"
      :disabled="busy || !!pending"
      :rows="6"
      placeholder='[{"record_code":"...","name":"...","cooking_state":"熟","nutrients":{"energy_kcal":null}}]'
    />
    <a-button :disabled="!text.trim()" :loading="busy" @click="prepare">{{
      pending ? '重试原批次' : '校验并保存候选'
    }}</a-button>
    <a-alert v-if="error" type="error" :message="error" show-icon />
    <template v-if="report">
      <p>
        共 {{ report.summary.total }} 行，异常 {{ report.summary.invalid }} 行，待审
        {{ report.summary.pending_review }} 行；发布 {{ report.published_count }} 条。
      </p>
      <div class="report">
        <article v-for="row in report.items" :key="row.row">
          <strong
            >第{{ row.row }}行 · {{ row.candidate.name || '未命名' }} ·
            {{ row.status === 'invalid' ? '需修正' : '待专业审核' }}</strong
          >
          <p v-for="(issue, index) in row.issues" :key="index">
            {{ issue.field }}：{{ codes[issue.code] || issue.code }}
          </p>
        </article>
      </div>
      <small>批次 {{ report.id }} 已保存；后续需补来源版本、许可、适用范围和专业审核。</small>
      <details v-if="report.knowledge_sources?.length">
        <summary>核对原文来源与数值证据</summary>
        <article v-for="source in report.knowledge_sources" :key="source.source_id">
          <strong>{{ source.filename }}</strong><p>{{ source.content }}</p>
          <small>片段 {{ source.chunk_id }} · 版本 {{ source.chunk_hash }}</small>
        </article>
        <pre>{{ JSON.stringify(report.evidence, null, 2) }}</pre>
      </details>
    </template>
  </section>
</template>
<style scoped>
.nutrition-import {
  border-top: 1px solid var(--gray-200);
  padding: 20px 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  color: var(--gray-1000);
}
.nutrition-import p,
.nutrition-import small {
  color: var(--gray-600);
  overflow-wrap: anywhere;
}
.report {
  max-height: 400px;
  overflow: auto;
}
.report article {
  padding: 10px;
  border-bottom: 1px solid var(--gray-150);
}
</style>
