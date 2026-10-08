<script setup>
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { healthVisionApi as api } from '@/apis/health_vision_api'

const props = defineProps({ record: { type: Object, required: true } })
const open = ref(false)
const loading = ref(false)
const working = ref(false)
const loaded = ref(false)
const error = ref('')
const current = ref(null)
const revisions = ref([])
const form = ref({ consumption: 'unknown', tags: [], comment: '' })
const attempt = ref(null)
const revokeAttempt = ref(null)
let epoch = 0
let disposed = false
const version = computed(() => current.value?.version || 0)
const tags = {
  too_salty: '偏咸',
  too_oily: '偏油',
  too_sweet: '偏甜',
  too_spicy: '偏辣',
  portion_large: '份量多',
  portion_small: '份量少',
  discomfort: '餐后不舒服'
}
const portions = {
  unknown: '未填写',
  all: '全部吃完',
  most: '大部分',
  half: '约一半',
  little: '少量',
  none: '没吃'
}
const canSave = computed(
  () =>
    loaded.value &&
    !loading.value &&
    !working.value &&
    (form.value.comment.trim() || form.value.tags.length || form.value.consumption !== 'unknown')
)
const mealLabel = computed(
  () =>
    ({ breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐' })[
      props.record.snapshot.meal.meal_type
    ]
)

/** 切换餐次或离开页面时拒绝旧响应覆盖当前成员。 */
function clear() {
  epoch += 1
  open.value = false
  loading.value = working.value = loaded.value = false
  current.value = null
  revisions.value = []
  error.value = ''
  attempt.value = revokeAttempt.value = null
  form.value = { consumption: 'unknown', tags: [], comment: '' }
}
watch(() => props.record.id, clear)
onBeforeUnmount(() => {
  disposed = true
  clear()
})

/** 刷新回读真实当前版本，错误时禁止按猜测版本保存。 */
async function reload() {
  const ticket = ++epoch
  loading.value = true
  loaded.value = false
  error.value = ''
  try {
    const result = await api.mealFeedback(props.record.id)
    if (disposed || ticket !== epoch) return
    current.value = result.feedback
    revisions.value = result.revisions
    form.value =
      result.feedback?.status === 'active'
        ? { ...result.feedback.details, tags: [...result.feedback.details.tags] }
        : { consumption: 'unknown', tags: [], comment: '' }
    loaded.value = true
    attempt.value = revokeAttempt.value = null
  } catch {
    if (ticket === epoch) error.value = '反馈读取失败，请刷新重试。'
  } finally {
    if (ticket === epoch) loading.value = false
  }
}

/** 未知保存结果保留原请求；编辑新内容需先刷新核对。 */
async function save() {
  if (!canSave.value) return
  const ticket = epoch
  if (!attempt.value)
    attempt.value = {
      client_request_id: crypto.randomUUID(),
      version: version.value,
      consumption: form.value.consumption,
      tags: [...form.value.tags],
      comment: form.value.comment.trim()
    }
  working.value = true
  error.value = ''
  try {
    await api.saveMealFeedback(props.record.id, attempt.value)
    if (disposed || ticket !== epoch) return
    working.value = false
    await reload()
  } catch {
    if (ticket === epoch) error.value = '保存结果尚未确认。重试将提交原请求；刷新可核对当前版本。'
  } finally {
    if (ticket === epoch) working.value = false
  }
}

/** 撤回后重新读取当前状态，原始修订保持可追溯。 */
async function revoke() {
  if (!loaded.value || loading.value || working.value || current.value?.status !== 'active') return
  const ticket = epoch
  if (!revokeAttempt.value)
    revokeAttempt.value = { client_request_id: crypto.randomUUID(), version: version.value }
  working.value = true
  error.value = ''
  try {
    await api.revokeMealFeedback(props.record.id, revokeAttempt.value)
    if (disposed || ticket !== epoch) return
    working.value = false
    await reload()
  } catch {
    if (ticket === epoch) error.value = '撤回结果尚未确认，请重试原请求或刷新核对。'
  } finally {
    if (ticket === epoch) working.value = false
  }
}

async function show() {
  open.value = true
  await reload()
}
</script>

<template>
  <div class="meal-feedback-entry">
    <a-button size="small" @click="show">餐后反馈</a-button>
    <a-modal
      v-model:open="open"
      title="餐后反馈"
      :footer="null"
      :mask-closable="!working"
      :closable="!working"
    >
      <p>{{ mealLabel }} · {{ new Date(record.snapshot.meal.eaten_at).toLocaleString() }}</p>
      <p class="hint">反馈只关联这一餐，可供后续营养咨询参考。吃完程度为自述，原营养记录保留。</p>
      <a-alert v-if="error" type="error" :message="error" show-icon />
      <a-button :disabled="working || loading" @click="reload">刷新反馈</a-button>
      <a-spin :spinning="loading">
        <template v-if="loaded">
          <p v-if="!current">还没有反馈，填写这餐的体验。</p>
          <p v-else-if="current.status === 'revoked'">
            已撤回。营养咨询不再使用这条反馈；可重新填写。
          </p>
          <p v-else>已保存 · 版本 {{ current.version }}</p>
          <a-form layout="vertical">
            <a-form-item label="吃完程度">
              <a-select
                v-model:value="form.consumption"
                :disabled="working || !!attempt || !!revokeAttempt"
                :options="Object.entries(portions).map(([value, label]) => ({ value, label }))"
              />
            </a-form-item>
            <a-form-item label="这餐的体验">
              <a-checkbox-group
                v-model:value="form.tags"
                :disabled="working || !!attempt || !!revokeAttempt"
                :options="Object.entries(tags).map(([value, label]) => ({ value, label }))"
              />
            </a-form-item>
            <a-form-item label="补充说明">
              <a-textarea
                v-model:value="form.comment"
                :maxlength="500"
                :rows="3"
                :disabled="working || !!attempt || !!revokeAttempt"
              />
            </a-form-item>
          </a-form>
          <div class="actions">
            <a-button
              type="primary"
              :loading="working"
              :disabled="!canSave || !!revokeAttempt"
              @click="save"
              >{{ attempt ? '重试保存' : '保存反馈' }}</a-button
            >
            <a-popconfirm
              v-if="current?.status === 'active'"
              title="撤回这餐的反馈？"
              @confirm="revoke"
            >
              <a-button danger :disabled="working || !!attempt">{{
                revokeAttempt ? '重试撤回' : '撤回反馈'
              }}</a-button>
            </a-popconfirm>
          </div>
          <a-collapse v-if="revisions.length" class="feedback-history">
            <a-collapse-panel key="history" header="查看修改记录">
              <div v-for="revision in revisions" :key="revision.version" class="revision">
                <strong
                  >版本 {{ revision.version }} ·
                  {{ revision.status === 'active' ? '保存' : '撤回' }}</strong
                >
                <p>
                  {{ portions[revision.details.consumption] }} ·
                  {{ revision.details.tags.map((tag) => tags[tag]).join('、') || '未填写标签' }}
                </p>
                <p>{{ revision.details.comment || '无补充说明' }}</p>
                <small>{{ new Date(revision.created_at).toLocaleString() }}</small>
              </div>
            </a-collapse-panel>
          </a-collapse>
        </template>
      </a-spin>
    </a-modal>
  </div>
</template>

<style scoped>
.meal-feedback-entry {
  margin-top: 12px;
}
.hint {
  color: var(--gray-600);
}
.actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.feedback-history {
  margin-top: 16px;
}
.revision {
  border-bottom: 1px solid var(--gray-200);
  padding: 10px 0;
}
.revision p {
  overflow-wrap: anywhere;
}
</style>
