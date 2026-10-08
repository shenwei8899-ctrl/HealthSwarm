<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { healthVisionApi as api } from '@/apis/health_vision_api'

const props = defineProps({
  memberId: { type: String, default: '' },
  scopes: { type: Array, default: () => [] }
})
const router = useRouter()
const memories = ref([])
const days = ref([])
const loading = ref(false)
const working = ref(false)
const error = ref('')
const edit = ref(null)
const editAttempt = ref(null)
const revokeAttempt = ref(null)
const detail = ref(null)
const selectedThread = ref('')
const summary = ref(null)
const summaryLoading = ref(false)
const nextBefore = ref(null)
const canRead = computed(() => !!props.memberId && props.scopes.includes('ai_use'))
const canEdit = computed(() => canRead.value && props.scopes.includes('profile_edit'))
const canHistory = computed(
  () => canRead.value && ['report_view', 'diet_edit'].every((scope) => props.scopes.includes(scope))
)
const kindLabels = {
  preference: '长期偏好',
  restriction: '用户自述限制',
  health_self_report: '健康自述 · 未专业审核'
}
const summaryLabels = {
  day_open: '当天对话尚未结束',
  pending: '摘要待生成',
  stale: '来源有变化，旧摘要已隐藏',
  waiting_for_requests: '等待咨询结束后自动补跑',
  ready: '日终消息摘录已生成'
}
let epoch = 0
let summarySequence = 0
let disposed = false

/** 页面结果须属于当前成员与读取代次。 */
async function reload(before = null) {
  const ticket = ++epoch
  loading.value = true
  error.value = ''
  if (!before) {
    memories.value = []
    days.value = []
    summary.value = null
    selectedThread.value = ''
    summaryLoading.value = false
    nextBefore.value = null
  }
  if (!canRead.value) {
    loading.value = false
    return
  }
  const results = await Promise.allSettled([
    api.memberMemory(props.memberId),
    canHistory.value
      ? api.dailyHistory(props.memberId, before)
      : Promise.resolve({ days: [], next_before: null })
  ])
  if (disposed || ticket !== epoch) return
  if (results[0].status === 'fulfilled') memories.value = results[0].value.memories
  if (results[1].status === 'fulfilled') {
    days.value = before ? [...days.value, ...results[1].value.days] : results[1].value.days
    nextBefore.value = results[1].value.next_before
  }
  if (results.some((item) => item.status === 'rejected'))
    error.value = '部分内容加载失败，请重试。授权发生变化时请重新选择成员。'
  loading.value = false
}

/** 保存未知响应后保留原请求，重试不改变已提交的内容和版本。 */
async function saveEdit() {
  if (!canEdit.value || !edit.value || working.value) return
  const ticket = epoch
  if (!editAttempt.value)
    editAttempt.value = {
      client_request_id: crypto.randomUUID(),
      version: edit.value.version,
      content: edit.value.content,
      kind: edit.value.kind
    }
  working.value = true
  error.value = ''
  try {
    await api.editMemory(edit.value.memory_id, editAttempt.value)
    if (disposed || ticket !== epoch) return
    edit.value = null
    editAttempt.value = null
    working.value = false
    await reload()
  } catch {
    if (ticket === epoch) error.value = '保存未确认。可重试原请求；若版本已变化，请关闭编辑并刷新。'
  } finally {
    if (ticket === epoch) working.value = false
  }
}

/** 删除采用后端撤回事实，成功后重新读取当前有效列表。 */
async function revoke(fact) {
  if (!canEdit.value || working.value) return
  const ticket = epoch
  if (
    !revokeAttempt.value ||
    revokeAttempt.value.memory_id !== fact.memory_id ||
    revokeAttempt.value.version !== fact.version
  )
    revokeAttempt.value = {
      memory_id: fact.memory_id,
      version: fact.version,
      client_request_id: crypto.randomUUID()
    }
  const { memory_id, ...payload } = revokeAttempt.value
  working.value = true
  error.value = ''
  try {
    await api.revokeMemory(memory_id, payload)
    if (disposed || ticket !== epoch) return
    revokeAttempt.value = null
    working.value = false
    await reload()
  } catch {
    if (ticket === epoch) error.value = '撤回未确认，请重试或刷新核对当前状态。'
  } finally {
    if (ticket === epoch) working.value = false
  }
}

/** 版本与来源只展示当前成员的响应。 */
async function showDetail(fact) {
  const ticket = epoch
  try {
    const result = await api.memoryHistory(fact.memory_id)
    if (!disposed && ticket === epoch) detail.value = result
  } catch {
    if (ticket === epoch) error.value = '记忆详情读取失败，请刷新后重试。'
  }
}

/** 摘要加载按选择序号隔离，旧日期响应不能覆盖新选择。 */
async function showSummary(thread, refresh = false) {
  const ticket = epoch
  const sequence = ++summarySequence
  selectedThread.value = thread
  summary.value = null
  summaryLoading.value = true
  try {
    const result = await (refresh ? api.refreshDailySummary(thread) : api.dailySummary(thread))
    if (!disposed && ticket === epoch && sequence === summarySequence) summary.value = result
  } catch {
    if (ticket === epoch && sequence === summarySequence)
      error.value = '摘要读取或补跑失败，请稍后重试。'
  } finally {
    if (ticket === epoch && sequence === summarySequence) summaryLoading.value = false
  }
}

function openEdit(fact) {
  edit.value = { ...fact }
  editAttempt.value = null
}
function closeEdit() {
  if (!working.value) {
    edit.value = null
    editAttempt.value = null
  }
}
function openConversation(thread) {
  router.push({ name: 'AgentCompWithThreadId', params: { thread_id: thread } })
}
watch(
  () => [props.memberId, props.scopes.join(',')],
  () => {
    edit.value = null
    detail.value = null
    revokeAttempt.value = null
    editAttempt.value = null
    working.value = false
    reload()
  }
)
onMounted(() => reload())
onBeforeUnmount(() => {
  disposed = true
  epoch++
})
</script>

<template>
  <section class="memory-daily">
    <a-alert v-if="!canRead" type="info" show-icon message="请选择具备 AI 使用授权的成员。" />
    <template v-else>
      <a-alert v-if="error" type="error" show-icon :message="error" />
      <div class="heading">
        <h2>AI 记住的事</h2>
        <a-button :loading="loading" :disabled="working" @click="reload()">刷新</a-button>
      </div>
      <p class="muted">当前账号维护的成员自述。健康自述尚未专业审核，也未写入正式健康档案。</p>
      <a-spin :spinning="loading">
        <a-empty
          v-if="!memories.length && !loading"
          description="暂无长期记忆。明确成员的长期信息可在营养咨询中保存。"
        />
        <article v-for="fact in memories" :key="fact.memory_id" class="fact">
          <a-tag>{{ kindLabels[fact.kind] }}</a-tag
          ><span class="muted">版本 {{ fact.version }}</span>
          <p>{{ fact.content }}</p>
          <div class="actions">
            <a-button size="small" @click="showDetail(fact)">版本与来源</a-button
            ><a-button size="small" :disabled="!canEdit || working" @click="openEdit(fact)"
              >修改</a-button
            >
            <a-popconfirm title="撤回后停止未来召回，历史消息仍保留。" @confirm="revoke(fact)"
              ><a-button size="small" danger :disabled="!canEdit || working"
                >删除／撤回</a-button
              ></a-popconfirm
            >
          </div>
        </article>
      </a-spin>
      <div class="heading">
        <h2>每日对话与摘要</h2>
        <span class="muted">北京时间 · 当前成员</span>
      </div>
      <a-alert v-if="!canHistory" type="info" message="查看每日历史还需报告查看和饮食维护授权。" />
      <a-empty
        v-else-if="!days.length && !loading"
        description="暂无每日对话，请从“今日营养咨询”进入。"
      />
      <article v-for="day in days" :key="day.thread_id" class="day">
        <strong>{{ day.date }}</strong>
        <div class="actions">
          <a-button size="small" @click="openConversation(day.thread_id)">查看对话</a-button
          ><a-button size="small" @click="showSummary(day.thread_id)">查看摘要</a-button>
        </div>
      </article>
      <a-button v-if="nextBefore" :disabled="loading || working" @click="reload(nextBefore)"
        >更早的对话</a-button
      >
      <a-spin :spinning="summaryLoading"
        ><section v-if="summary" class="summary">
          <h3>{{ summary.date }} · {{ summaryLabels[summary.status] }}</h3>
          <template v-if="summary.summary"
            ><p class="muted">
              摘要为成功消息摘录；以下预览最近 8 条，共
              {{ summary.summary.message_count }} 条，不代表已生成餐单。
            </p>
            <p v-for="item in summary.summary.excerpts.slice(-8)" :key="item.message_id">
              <strong>{{ item.role === 'user' ? '用户' : '营养师' }}：</strong>{{ item.excerpt
              }}{{ item.truncated ? '…' : '' }}
            </p></template
          >
          <a-button
            v-if="summary.status !== 'day_open'"
            :disabled="summaryLoading"
            @click="showSummary(selectedThread, true)"
            >补跑日终摘要</a-button
          >
        </section></a-spin
      >
    </template>
    <a-modal
      :open="!!edit"
      title="修改成员自述"
      :confirm-loading="working"
      @ok="saveEdit"
      @cancel="closeEdit"
    >
      <template v-if="edit"
        ><p>修改后仍保留用户自述来源和旧版本。</p>
        <a-select v-model:value="edit.kind" :disabled="!!editAttempt" style="width: 100%"
          ><a-select-option v-for="(label, key) in kindLabels" :key="key" :value="key">{{
            label
          }}</a-select-option></a-select
        ><a-textarea
          v-model:value="edit.content"
          :disabled="!!editAttempt"
          :maxlength="500"
          :rows="4"
      /></template>
    </a-modal>
    <a-modal :open="!!detail" title="记忆版本与来源" :footer="null" @cancel="detail = null"
      ><template v-if="detail"
        ><p v-for="revision in detail.revisions" :key="revision.version">
          版本 {{ revision.version }} · {{ revision.status === 'active' ? '有效' : '已撤回'
          }}<br />{{ revision.content }}<br /><span class="muted">{{
            revision.source_message_id ? `来源消息 ${revision.source_message_id}` : '用户管理操作'
          }}</span>
        </p></template
      ></a-modal
    >
  </section>
</template>

<style scoped>
.memory-daily {
  background: var(--gray-0);
  border: 1px solid var(--gray-150);
  border-radius: 12px;
  padding: 24px;
}
.heading,
.day {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.heading {
  margin: 16px 0;
}
.heading h2 {
  margin: 0;
  font-size: 18px;
}
.muted {
  color: var(--gray-600);
  font-size: 13px;
}
.fact,
.day,
.summary {
  border-top: 1px solid var(--gray-150);
  padding: 16px 0;
}
.fact p,
.summary p {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
@media (max-width: 600px) {
  .memory-daily {
    padding: 16px;
  }
}
</style>
