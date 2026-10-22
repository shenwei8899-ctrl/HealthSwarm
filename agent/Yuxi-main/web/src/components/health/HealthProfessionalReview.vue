<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useUserStore } from '@/stores/user'
import { healthVisionApi as api } from '@/apis/health_vision_api'
import HealthMealPlanSnapshot from './HealthMealPlanSnapshot.vue'
import HealthFamilyMealPlanSnapshot from './HealthFamilyMealPlanSnapshot.vue'

const props = defineProps({
  memberId: { type: String, default: '' },
  scopes: { type: Array, default: () => [] }
})
defineEmits(['profile', 'plans'])
const user = useUserStore()
const inbox = ref(false)
const rows = ref([])
const plans = ref([])
const planId = ref('')
const ruleCode = ref('')
const detail = ref(null)
const offset = ref(0)
const nextOffset = ref(null)
const loading = ref(false)
const working = ref(false)
const error = ref('')
const plansError = ref('')
const reason = ref('')
const evidence = ref('')
const confirmed = ref(false)
const attempt = ref(null)
let epoch = 0
let readId = 0
let disposed = false
const labels = {
  draft: '待提交',
  pending_review: '待专业复核',
  returned: '退回补资料',
  approved: '审核通过',
  invalidated: '来源已失效'
}
const actions = { submit: '提交复核', return: '退回补资料', approve: '批准当前版本' }
const canRead = computed(
  () =>
    props.memberId &&
    props.scopes.includes('profile_view') &&
    props.scopes.includes(inbox.value ? 'professional_review' : 'diet_edit')
)
const selectedPlan = computed(() => plans.value.find((p) => p.plan_id === planId.value))
const formReady = computed(() => reason.value.trim() && evidence.value.trim() && confirmed.value)
const current = (ticket) => !disposed && ticket === epoch

/** 切换账号或成员立即清理资料，迟到请求不得写回。 */
function reset() {
  epoch++
  readId++
  rows.value = []
  plans.value = []
  detail.value = null
  attempt.value = null
  planId.value = ''
  ruleCode.value = ''
  reason.value = ''
  evidence.value = ''
  confirmed.value = false
  working.value = false
  error.value = ''
  plansError.value = ''
  offset.value = 0
  void load()
}

/** 每次翻页回读当前授权，列表不推断专业资格。 */
async function load(page = 0) {
  const ticket = epoch,
    read = ++readId
  rows.value = []
  detail.value = null
  nextOffset.value = null
  plans.value = []
  if (!canRead.value) {
    loading.value = false
    return
  }
  loading.value = true
  error.value = ''
  try {
    const [listed, choices] = await Promise.allSettled([
      api.professionalReviews(props.memberId, inbox.value, page),
      inbox.value ? Promise.resolve(null) : api.mealPlans(props.memberId)
    ])
    if (!current(ticket) || read !== readId) return
    if (listed.status === 'rejected') throw listed.reason
    const list = listed.value
    rows.value = list.items
    nextOffset.value = list.next_offset
    offset.value = page
    plans.value = choices.status === 'fulfilled' ? choices.value?.plans || [] : []
    plansError.value = choices.status === 'rejected' ? '餐单暂不可读取，可继续处理已有申请。' : ''
  } catch (err) {
    if (current(ticket) && read === readId) error.value = err.message
  } finally {
    if (current(ticket) && read === readId) loading.value = false
  }
}

/** 详情始终读取服务端允许动作，版本冲突后重新核对。 */
async function open(id) {
  const ticket = epoch,
    read = ++readId
  detail.value = null
  confirmed.value = false
  reason.value = ''
  evidence.value = ''
  error.value = ''
  loading.value = true
  try {
    const result = await api.reviewWorkbench(id)
    if (current(ticket) && read === readId) detail.value = result
  } catch (err) {
    if (current(ticket) && read === readId) error.value = err.message
  } finally {
    if (current(ticket) && read === readId) loading.value = false
  }
}

/** 未知响应保留同一请求与正文，只允许重试原动作。 */
async function perform(action) {
  if (working.value || !detail.value || !formReady.value) return
  if (!attempt.value)
    attempt.value = {
      kind: action,
      id: detail.value.review.review_id,
      data: {
        client_request_id: crypto.randomUUID(),
        version: detail.value.review.version,
        reason: reason.value.trim(),
        evidence_refs: evidence.value
          .split('\n')
          .map((v) => v.trim())
          .filter(Boolean)
      }
    }
  await executeAttempt()
}

/** 新资料需要新检查；不在历史申请中覆盖原餐单。 */
async function check() {
  if (!selectedPlan.value || !ruleCode.value.trim() || working.value) return
  if (!attempt.value)
    attempt.value = {
      kind: 'check',
      id: selectedPlan.value.plan_id,
      data: {
        client_request_id: crypto.randomUUID(),
        version: selectedPlan.value.version,
        rule_code: ruleCode.value.trim()
      }
    }
  await executeAttempt()
}

async function executeAttempt() {
  const pending = attempt.value,
    ticket = epoch
  if (!pending) return
  working.value = true
  error.value = ''
  try {
    let id = pending.id
    if (pending.kind === 'check') {
      const result = await api.checkMealPlan(pending.id, pending.data)
      if (!current(ticket)) return
      const checked = await api.qualityCheck(result.check_id)
      id = checked.review.review_id
    } else await api.reviewAction(pending.id, pending.kind, pending.data)
    if (!current(ticket)) return
    attempt.value = null
    await load(offset.value)
    if (current(ticket)) await open(id)
  } catch (err) {
    if (current(ticket)) {
      error.value = err.message
      if ([400, 401, 403, 404, 409, 410, 422].includes(err.status)) {
        attempt.value = null
        detail.value = null
        rows.value = []
      }
    }
  } finally {
    if (current(ticket)) working.value = false
  }
}

watch(() => [user.uid, props.memberId, props.scopes.join('|'), inbox.value], reset, {
  immediate: true
})
onBeforeUnmount(() => {
  disposed = true
  epoch++
  readId++
})
</script>

<template>
  <section class="review-workbench">
    <header>
      <h2>专业复核</h2>
      <p>核对当前方案与依据，提交补充材料或作出独立审核决定。</p>
    </header>
    <div class="toolbar">
      <a-radio-group v-model:value="inbox" :disabled="working || !!attempt"
        ><a-radio-button :value="false">我的申请</a-radio-button
        ><a-radio-button :value="true">复核收件</a-radio-button></a-radio-group
      >
      <a-button :disabled="working || !!attempt" @click="load(offset)">刷新</a-button>
    </div>
    <a-alert
      v-if="!canRead"
      type="info"
      show-icon
      message="请选择具备档案查看及相应用途授权的成员；复核收件还需有效专业资格。"
    />
    <a-alert v-if="error" type="error" show-icon :message="error" />
    <a-alert
      v-if="attempt && !working"
      type="warning"
      message="尚未确认操作结果，请使用原请求重试。"
      ><template #action><a-button @click="executeAttempt">重试原请求</a-button></template></a-alert
    >
    <a-spin :spinning="loading">
      <template v-if="canRead">
        <div v-if="!inbox" class="new-check">
          <h3>核对方案并创建申请</h3>
          <a-alert v-if="plansError" type="warning" :message="plansError" />
          <label
            >已保存餐单<a-select
              v-model:value="planId"
              :disabled="working || !!attempt"
              placeholder="选择当前餐单"
              ><a-select-option v-for="p in plans" :key="p.plan_id" :value="p.plan_id"
                >{{ p.date || p.updated_at?.slice(0, 10) || '餐单' }} · 第
                {{ p.version }} 版</a-select-option
              ></a-select
            ></label
          >
          <label
            >已发布规则编号<a-input
              v-model:value="ruleCode"
              :disabled="working || !!attempt"
              placeholder="由专业资料负责人提供"
          /></label>
          <a-button
            :disabled="!selectedPlan || !ruleCode.trim() || !!attempt"
            :loading="working"
            @click="check"
            >重新检查并创建申请</a-button
          >
          <p>
            补充档案或调整餐单后重新检查，旧申请保留。<a-button
              type="link"
              :disabled="working || !!attempt"
              @click="$emit('profile')"
              >补充档案</a-button
            ><a-button type="link" :disabled="working || !!attempt" @click="$emit('plans')"
              >调整餐单</a-button
            >
          </p>
        </div>
        <a-empty v-if="!loading && !rows.length" description="当前没有可查看的复核申请" />
        <div class="cases">
          <a-button
            v-for="row in rows"
            :key="row.review_id"
            :disabled="working || !!attempt"
            @click="open(row.review_id)"
            >{{ labels[row.status] }} · 餐单第 {{ row.plan_version }} 版 · 申请
            {{ row.review_id.slice(0, 8) }}</a-button
          >
        </div>
        <div class="toolbar">
          <a-button
            :disabled="!offset || working || !!attempt"
            @click="load(Math.max(0, offset - 20))"
            >上一页</a-button
          ><a-button
            :disabled="nextOffset === null || working || !!attempt"
            @click="load(nextOffset)"
            >下一页</a-button
          >
        </div>
        <article v-if="detail" class="case-detail">
          <h3>{{ labels[detail.review.status] }} · 第 {{ detail.review.version }} 次修订</h3>
          <a-alert
            v-if="detail.review.status === 'invalidated'"
            type="warning"
            message="此申请来源已变化，历史批准不可继续使用。请补充当前资料并重新检查。"
          />
          <p>
            工程检查：{{
              { passed: '通过', unknown: '资料不足', conflict: '存在冲突' }[
                detail.review.safety_status
              ]
            }}。专业决定另行记录。
          </p>
          <HealthFamilyMealPlanSnapshot
            v-if="detail.plan_snapshot?.members"
            :snapshot="detail.plan_snapshot"
            review-context
          />
          <HealthMealPlanSnapshot
            v-else-if="detail.plan_snapshot"
            :snapshot="detail.plan_snapshot"
            review-context
          />
          <h4>需要核对的资料与冲突</h4>
          <ul>
            <li
              v-for="(item, i) in [
                ...detail.check.safety_check.missing,
                ...detail.check.safety_check.conflicts
              ]"
              :key="i"
            >
              <span v-if="item.member_id">成员 {{ item.member_id }} · </span
              >{{ item.message || item.reason || item.code
              }}<span v-if="item.field"> · {{ item.field }}</span>
            </li>
          </ul>
          <details>
            <summary>查看来源版本及检查依据</summary>
            <pre>{{ JSON.stringify(detail.check.sources, null, 2) }}</pre>
            <p>以下为本次检查对应的历史专业依据，当前有效性以申请状态为准。</p>
            <pre>{{ JSON.stringify(detail.reviewed_basis, null, 2) }}</pre>
          </details>
          <h4>审核与补充历史</h4>
          <a-empty v-if="!detail.review.actions.length" description="尚无提交或审核记录" />
          <ol>
            <li v-for="a in detail.review.actions" :key="a.version">
              <strong>{{ labels[a.status] }}</strong> · {{ a.created_at }}
              <p>{{ a.reason }}</p>
              <p v-for="ref in a.evidence_refs" :key="ref">{{ ref }}</p>
              <small>操作人：{{ a.actor_uid }}</small>
            </li>
          </ol>
          <div v-if="detail.allowed_actions.length" class="action-form">
            <label
              >{{ detail.is_applicant ? '申请说明／补充说明' : '审核理由与补资料要求'
              }}<a-textarea
                v-model:value="reason"
                :maxlength="500"
                :disabled="working || !!attempt"
            /></label>
            <label
              >证据或材料引用（每行一项）<a-textarea
                v-model:value="evidence"
                :disabled="working || !!attempt"
                placeholder="填写可核对的材料名称、版本或来源；无需上传无关健康资料"
            /></label>
            <a-checkbox v-model:checked="confirmed" :disabled="working || !!attempt"
              >已核对所选版本、资料和本次操作</a-checkbox
            >
            <div class="toolbar">
              <a-button
                v-for="action in detail.allowed_actions"
                :key="action"
                :disabled="!formReady || !!attempt"
                :loading="working"
                @click="perform(action)"
                >{{ actions[action] }}</a-button
              >
            </div>
          </div>
        </article>
      </template>
    </a-spin>
  </section>
</template>

<style scoped>
.review-workbench {
  display: grid;
  gap: 16px;
  color: var(--color-text);
}
.toolbar,
.cases {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin: 12px 0;
}
.new-check,
.case-detail {
  padding: 20px;
  background: var(--gray-0);
  border: 1px solid var(--gray-150);
  border-radius: 8px;
}
.new-check > label,
.action-form > label:not(.ant-checkbox-wrapper),
.action-form {
  display: grid;
  gap: 8px;
  margin: 12px 0;
}
label .ant-select {
  min-width: 0;
  width: 100%;
}
pre,
li {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
pre {
  max-height: 360px;
  overflow: auto;
  background: var(--gray-25);
  padding: 12px;
}
@media (max-width: 600px) {
  .new-check,
  .case-detail {
    padding: 12px;
  }
  .cases {
    flex-direction: column;
  }
}
</style>
