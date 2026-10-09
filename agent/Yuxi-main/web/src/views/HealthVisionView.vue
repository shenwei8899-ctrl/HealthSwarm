<script setup>
import HealthMealFeedback from '@/components/health/HealthMealFeedback.vue'
import HealthFamilyProfile from '@/components/health/HealthFamilyProfile.vue'
import HealthProfessionalProfile from '@/components/health/HealthProfessionalProfile.vue'
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ScanLine, FileHeart, Utensils, ShieldCheck, Plus, RefreshCw } from '@lucide/vue'
import { message, Modal } from 'ant-design-vue'
import { useUserStore } from '@/stores/user'
import PageHeader from '@/components/shared/PageHeader.vue'
import ReportReview from '@/components/health/ReportReview.vue'
import MealReview from '@/components/health/MealReview.vue'
import HealthVisionAdmin from '@/components/health/HealthVisionAdmin.vue'
import HealthVisionStatistics from '@/components/health/HealthVisionStatistics.vue'
import HealthMemoryDaily from '@/components/health/HealthMemoryDaily.vue'
import HealthMealPlans from '@/components/health/HealthMealPlans.vue'
import { healthVisionApi as api } from '@/apis/health_vision_api'
import {
  newReportField,
  newMealItem,
  localDateTime,
  nutrientLabels,
  nutrientText,
  mealLabels
} from '@/utils/healthVision'

const userStore = useUserStore()
const router = useRouter()
const consultationOpen = ref(false)
const consultationConsent = ref(false)
const consultationMode = ref('daily')
const consultationError = ref('')
const consultationSourceInvalidated = ref(false)
const consultationRequest = ref(null)
const canConsult = computed(
  () =>
    !!config.value?.consultation?.available &&
    ['ai_use', 'report_view', 'diet_edit'].every((scope) => member.value?.scopes.includes(scope))
)
const tab = ref('report')
const config = ref(null)
const members = ref([])
const memberId = ref('')
const busy = ref(false)
const confirming = ref(false)
const taskRequest = ref(null)
const confirmationRequest = ref(null)
const reprocessRequest = ref(null)
const retryRequests = new Map()
let confirmationModal = null
const activeTab = computed({
  get: () => tab.value,
  set: (value) => {
    if (busy.value || confirming.value) return
    if (dirty.value && !window.confirm('当前修改尚未保存，确定切换并放弃修改吗？')) return
    tab.value = value
  }
})
const loading = ref(true)
const pageError = ref('')
const jobs = ref([])
const drafts = ref([])
const records = ref({ report: [], meal: [] })
const files = ref([])
const uploads = ref([])
const reportRotation = ref(0)
const deskewAngle = ref(0)
const preparedPreview = ref('')
const preparedPreviewOpen = ref(false)
const preparedPreviewLabel = ref('')
let preparedPreviewSequence = 0
const uploadInput = ref(null)
const cloudConsent = ref(false)
const mealType = ref('lunch')
const eatenAt = ref(localDateTime())
const selected = ref(null)
const dirty = ref(false)
const calculation = ref(null)
const acceptIncomplete = ref(false)
const reviewed = ref(false)
const editReason = ref('人工复核纠错')
const memberModal = ref(false)
const memberName = ref('')
const relationship = ref('本人')
const memberAuthorized = ref(false)
const grantModal = ref(false)
const grantActor = ref('')
const grantScopes = ref([])
const scopeLabels = {
  report_upload: '上传报告',
  report_view: '查看报告',
  profile_edit: '复核报告 / 维护档案',
  diet_edit: '饮食记录',
  ai_use: '云 AI 处理'
}
const member = computed(() => members.value.find((item) => item.id === memberId.value))
const purpose = computed(() => (tab.value === 'meal' ? 'meal' : 'report'))
const tabs = computed(() => [
  { key: 'report', label: '健康报告' },
  { key: 'profile', label: '本人档案' },
  { key: 'meal', label: '饮食照片' },
  { key: 'plans', label: '餐单草稿' },
  { key: 'records', label: '已确认记录' },
  { key: 'memory', label: '营养师记忆与历史' },
  ...(userStore.isAdmin ? [{ key: 'settings', label: '服务与食品数据' }] : [])
])
const editable = computed(() => selected.value?.review_status === 'pending_confirmation')
const canReprocessReport = computed(
  () =>
    editable.value &&
    !dirty.value &&
    cloudConsent.value &&
    !!config.value?.report?.available &&
    ['profile_edit', 'report_upload', 'ai_use'].every((scope) =>
      member.value?.scopes.includes(scope)
    )
)
const scopedJobs = computed(() => jobs.value.filter((item) => item.kind === purpose.value))
const scopedDrafts = computed(() => drafts.value.filter((item) => item.kind === purpose.value))
const statusLabels = {
  pending: '排队中',
  running: '识别中',
  success: '识别完成',
  failed: '识别失败',
  cancelled: '已取消'
}
const reviewLabels = { pending_confirmation: '待复核', confirmed: '已确认', invalidated: '已失效' }
let timer = null
let memberSequence = 0
let disposed = false

/** 加载真实就绪状态，禁止用样例数据伪装云识别。 */
async function initialize() {
  loading.value = true
  pageError.value = ''
  try {
    const [configuration, list] = await Promise.all([api.configuration(), api.members()])
    config.value = configuration
    members.value = list
    if (!list.some((item) => item.id === memberId.value)) memberId.value = list[0]?.id || ''
    await refresh()
  } catch (error) {
    pageError.value = error.message
  } finally {
    loading.value = false
  }
}

/** 轮询只覆盖列表，不覆盖用户正在修改的草稿。 */
async function refresh() {
  if (!memberId.value) return
  const id = memberId.value
  const sequence = memberSequence
  const [list, reportRecords, mealRecords] = await Promise.all([
    api.list(id),
    member.value?.scopes.includes('report_view') ? api.records(id, 'report') : [],
    member.value?.scopes.includes('diet_edit') ? api.records(id, 'meal') : []
  ])
  if (disposed || id !== memberId.value || sequence !== memberSequence) return
  jobs.value = list.jobs
  drafts.value = list.drafts
  records.value = { report: reportRecords, meal: mealRecords }
}

async function perform(action) {
  if (busy.value) return
  busy.value = true
  try {
    await action()
  } catch (error) {
    message.error(
      error.status === 409
        ? '版本或处理政策已变化，请重新打开草稿核对后再操作'
        : error.status === 503
          ? '识别服务未就绪，可先人工录入'
          : error.message
    )
  } finally {
    busy.value = false
  }
}

/** 成员变化与页面卸载共同撤销咨询私有状态。 */
function resetConsultation() {
  consultationOpen.value = false
  consultationConsent.value = false
  consultationError.value = ''
  consultationSourceInvalidated.value = false
  consultationRequest.value = null
  consultationMode.value = 'daily'
}

/** 切换入口保留未知新建请求，打开时重新核对当前用途同意。 */
function openConsultation(mode = 'daily') {
  if (busy.value || confirming.value) return
  consultationMode.value = mode
  consultationConsent.value = false
  consultationError.value = ''
  consultationSourceInvalidated.value = false
  consultationOpen.value = true
}

/** 咨询独立同意；每日重入和新建幂等请求的迟到响应不能导航其他成员。 */
async function enterConsultation() {
  if (
    !canConsult.value ||
    !consultationConsent.value ||
    consultationSourceInvalidated.value ||
    busy.value
  )
    return
  if (dirty.value && !window.confirm('当前修改尚未保存，确定进入咨询并放弃修改吗？')) return
  const id = memberId.value
  const sequence = memberSequence
  const processor = config.value.consultation.processor
  const policy = config.value.policy_version
  const actor = userStore.uid
  const mode = consultationMode.value
  const current = () =>
    !disposed && id === memberId.value && sequence === memberSequence && actor === userStore.uid
  if (
    mode === 'new' &&
    (!consultationRequest.value ||
      consultationRequest.value.member_id !== id ||
      consultationRequest.value.processor !== processor ||
      consultationRequest.value.policy !== policy)
  ) {
    consultationRequest.value = {
      member_id: id,
      processor,
      policy,
      client_request_id: crypto.randomUUID()
    }
  }
  const request = consultationRequest.value
  busy.value = true
  consultationError.value = ''
  consultationSourceInvalidated.value = false
  try {
    await api.consent(id, {
      purpose: 'consultation',
      accepted: true,
      processor,
      policy_version: policy
    })
    if (!current()) return
    const result =
      mode === 'new'
        ? await api.createConsultation(id, { client_request_id: request.client_request_id })
        : await api.createDailyConsultation(id)
    if (!current()) return
    if (result.member_id !== id || result.agent_slug !== 'health-consultation') {
      throw new Error('咨询绑定不一致，请刷新后重试')
    }
    consultationOpen.value = false
    consultationRequest.value = null
    await router.push({ name: 'AgentCompWithThreadId', params: { thread_id: result.thread_id } })
  } catch (error) {
    if (!current()) return
    consultationSourceInvalidated.value = error.status === 410
    if (consultationSourceInvalidated.value) {
      consultationConsent.value = false
      if (mode === 'new') consultationRequest.value = null
    }
    consultationError.value =
      error.status === 410 ? '原咨询使用的资料已变化，请新建咨询读取当前资料版本。' : error.message
  } finally {
    busy.value = false
  }
}

/** 切换成员清除私有视图及上一成员授权状态。 */
watch(memberId, () => {
  resetConsultation()
  clearPreparedPreview()
  reportRotation.value = 0
  deskewAngle.value = 0
  reprocessRequest.value = null
  taskRequest.value = null
  confirmationRequest.value = null
  memberSequence++
  jobs.value = []
  drafts.value = []
  records.value = { report: [], meal: [] }
  selected.value = null
  files.value = []
  uploads.value = []
  cloudConsent.value = false
  calculation.value = null
  dirty.value = false
  reviewed.value = false
  if (memberId.value) void perform(refresh)
})
watch(tab, () => {
  clearPreparedPreview()
  reportRotation.value = 0
  deskewAngle.value = 0
  reprocessRequest.value = null
  taskRequest.value = null
  confirmationRequest.value = null
  selected.value = null
  files.value = []
  uploads.value = []
  cloudConsent.value = false
  calculation.value = null
  dirty.value = false
  reviewed.value = false
})
watch([mealType, eatenAt], () => {
  taskRequest.value = null
})
watch(acceptIncomplete, () => {
  confirmationRequest.value = null
})
onMounted(async () => {
  await initialize()
  timer = setInterval(() => {
    if (
      !busy.value &&
      document.visibilityState === 'visible' &&
      jobs.value.some((item) => ['pending', 'running'].includes(item.execution_status))
    )
      void perform(refresh)
  }, 3000)
})
onBeforeUnmount(() => {
  disposed = true
  memberSequence++
  resetConsultation()
  clearPreparedPreview()
  retryRequests.clear()
  confirmationModal?.destroy()
  confirmationModal = null
  if (timer) clearInterval(timer)
})

function selectFiles(event) {
  const chosen = Array.from(event.target.files || [])
  const limit = purpose.value === 'meal' ? 3 : 20
  if (
    chosen.length > limit ||
    chosen.some((file) => file.size > (file.type === 'application/pdf' ? 20 : 10) * 1024 * 1024)
  ) {
    message.warning(`文件数量最多 ${limit} 个，图片不超过 10MB，PDF 不超过 20MB`)
    event.target.value = ''
    return
  }
  files.value = chosen
  event.target.value = ''
  clearPreparedPreview()
  uploads.value = []
  taskRequest.value = null
}

/** 清除私有预览和迟到请求；不将 Object URL 留给另一成员。 */
function clearPreparedPreview() {
  preparedPreviewSequence++
  if (preparedPreview.value) URL.revokeObjectURL(preparedPreview.value)
  preparedPreview.value = ''
  preparedPreviewOpen.value = false
}

/** 上传固定处理参数，不创建 Task、不签署云处理同意。 */
async function uploadSelectedFiles(kind, id) {
  if (uploads.value.length) return
  const saved = []
  const sequence = memberSequence
  const chosen = [...files.value]
  const rotation = reportRotation.value
  const angle = deskewAngle.value ?? 0
  try {
    for (const file of chosen) {
      const data = new FormData()
      data.append('member_id', id)
      data.append('purpose', kind)
      data.append('file', file)
      if (kind === 'report') {
        data.append('rotation', String(rotation))
        data.append('deskew_angle', String(angle))
      }
      saved.push(await api.upload(data))
      if (
        disposed ||
        sequence !== memberSequence ||
        id !== memberId.value ||
        kind !== purpose.value
      )
        throw new Error('成员或用途已变化，请重新选择文件')
    }
    uploads.value = saved
  } catch (error) {
    for (const item of saved) {
      try {
        await api.removeUpload(item.upload_id)
      } catch {
        /* 私有删除接口可重试；失败不创建付费任务。 */
      }
    }
    throw error
  }
}

/** 原页预览读取同一私有处理副本，预览本身不调用云模型。 */
async function showPreparedPage(upload, page) {
  const sequence = ++preparedPreviewSequence
  const blob = await api.preview(upload.upload_id, page)
  if (disposed || sequence !== preparedPreviewSequence) return
  if (preparedPreview.value) URL.revokeObjectURL(preparedPreview.value)
  preparedPreview.value = URL.createObjectURL(blob)
  preparedPreviewLabel.value = `处理页 ${page + 1} · 私有处理副本`
  preparedPreviewOpen.value = true
}

/** 服务未配置也允许本地私有预处理，完成后用户自行选择是否外发。 */
async function prepareReport() {
  if (purpose.value !== 'report' || !memberId.value || !files.value.length) return
  await perform(async () => {
    await uploadSelectedFiles('report', memberId.value)
    await showPreparedPage(uploads.value[0], 0)
    message.success('处理副本已私有保存，尚未调用云模型；请核对方向和清晰度')
  })
}

/** 用户单次明确同意后才创建云任务，上传本身不代表同意。 */
async function startRecognition() {
  if (!memberId.value || !files.value.length || !cloudConsent.value)
    return message.warning('请选择成员、文件并确认本次云处理')
  await perform(async () => {
    const kind = purpose.value
    const id = memberId.value
    const sequence = memberSequence
    await api.consent(id, {
      purpose: kind,
      accepted: true,
      processor: config.value[kind].processor,
      policy_version: config.value.policy_version
    })
    if (disposed || sequence !== memberSequence || id !== memberId.value || kind !== purpose.value)
      throw new Error('成员或用途已变化，请重新确认本次云处理')
    await uploadSelectedFiles(kind, id)
    const request = taskRequest.value || {
      member_id: id,
      upload_ids: uploads.value.map((item) => item.upload_id),
      client_request_id: crypto.randomUUID(),
      ...(kind === 'meal'
        ? { meal_type: mealType.value, eaten_at: new Date(eatenAt.value).toISOString() }
        : {})
    }
    taskRequest.value = request
    await api.createTask(kind, request)
    taskRequest.value = null
    cloudConsent.value = false
    files.value = []
    uploads.value = []
    clearPreparedPreview()
    if (uploadInput.value) uploadInput.value.value = ''
    await refresh()
    message.success('识别任务已提交，完成后请打开草稿复核')
  })
}

async function manualDraft() {
  if (!memberId.value) return message.warning('请先创建或选择健康成员')
  await perform(async () => {
    const kind = purpose.value
    selected.value = await api.manual({
      member_id: memberId.value,
      kind,
      ...(kind === 'report'
        ? {
            report: {
              fields: [{ ...newReportField(), name: '待填写指标' }],
              pages: [],
              excluded_pages: []
            }
          }
        : {
            meal: {
              meal_type: mealType.value,
              eaten_at: new Date(eatenAt.value).toISOString(),
              items: [{ ...newMealItem(), name: '待填写食物' }]
            }
          })
    })
    dirty.value = false
    confirmationRequest.value = null
    calculation.value = null
    reviewed.value = false
    await refresh()
  })
}

async function openDraft(id) {
  if (dirty.value && !window.confirm('尚有未保存修改，确定放弃并重新打开草稿吗？')) return
  await perform(async () => {
    selected.value = await api.draft(purpose.value, id)
    confirmationRequest.value = null
    reprocessRequest.value = null
    dirty.value = false
    calculation.value = null
    reviewed.value = false
    acceptIncomplete.value = false
  })
}

function changed() {
  reprocessRequest.value = null
  confirmationRequest.value = null
  dirty.value = true
  calculation.value = null
  reviewed.value = false
}

/** 新增记录由父组件持有并标记版本变更。 */
function addResult() {
  if (selected.value.kind === 'report') selected.value.payload.fields.push(newReportField())
  else selected.value.payload.items.push(newMealItem())
  changed()
}

async function saveDraft() {
  if (!dirty.value) return
  const draft = selected.value
  selected.value = await api.patch(draft.kind, draft.id, {
    version: draft.version,
    reason: editReason.value,
    [draft.kind]: draft.payload
  })
  dirty.value = false
  confirmationRequest.value = null
  calculation.value = null
  reviewed.value = false
  await refresh()
}

async function calculate() {
  await perform(async () => {
    await saveDraft()
    calculation.value = await api.calculate(selected.value.id, selected.value.version)
    confirmationRequest.value = null
    acceptIncomplete.value = false
  })
}

function excludeReportPages(indices) {
  selected.value.payload.excluded_pages = indices
  changed()
}

/** 保存、同意和当前版本明确后，只提交选中的失败页；未知响应保留请求键。 */
async function reprocessReportPage(index) {
  if (!canReprocessReport.value)
    return message.warning('请先保存修改，并在上方确认本用途云处理同意及服务就绪')
  const draft = selected.value
  if (
    !reprocessRequest.value ||
    reprocessRequest.value.draft_id !== draft.id ||
    reprocessRequest.value.version !== draft.version ||
    reprocessRequest.value.page_indices[0] !== index
  ) {
    reprocessRequest.value = {
      draft_id: draft.id,
      version: draft.version,
      page_indices: [index],
      client_request_id: crypto.randomUUID()
    }
  }
  await perform(async () => {
    await api.consent(draft.member_id, {
      purpose: 'report',
      accepted: true,
      processor: config.value.report.processor,
      policy_version: config.value.policy_version
    })
    await api.reprocessReport(reprocessRequest.value)
    reprocessRequest.value = null
    reviewed.value = false
    confirmationRequest.value = null
    await refresh()
    message.success('单页任务已创建，完成后请重新打开草稿。处理中修改或确认将阻止旧任务回写。')
  })
}

function confirmDraft() {
  if (dirty.value || !reviewed.value) return message.warning('请先保存修改，并明确确认已逐项复核')
  if (
    selected.value.kind === 'report' &&
    selected.value.payload.pages.some(
      (page) =>
        page.status === 'failed' && !selected.value.payload.excluded_pages.includes(page.page_index)
    )
  )
    return message.warning('请处理失败页，或明确排除后保存再确认')
  if (
    selected.value.kind === 'meal' &&
    (!calculation.value || (!calculation.value.complete && !acceptIncomplete.value))
  )
    return message.warning('请先计算营养；不完整结果需要明确接受')
  const draft = selected.value
  const id = memberId.value
  const sequence = memberSequence
  const current = () => !disposed && id === memberId.value && sequence === memberSequence
  const request = confirmationRequest.value || {
    version: draft.version,
    client_request_id: crypto.randomUUID(),
    ...(draft.kind === 'meal'
      ? {
          calculation_id: calculation.value.calculation_id,
          accept_incomplete: acceptIncomplete.value
        }
      : {})
  }
  confirmationRequest.value = request
  confirming.value = true
  confirmationModal = Modal.confirm({
    title: selected.value.kind === 'report' ? '确认写入健康档案？' : '确认写入饮食日记？',
    content: '确认后保留不可变快照，不能再修改此草稿。识别结果不构成医疗诊断。',
    okText: '确认入库',
    cancelText: '继续复核',
    onCancel: () => {
      confirming.value = false
      confirmationModal = null
    },
    onOk: () =>
      perform(async () => {
        if (!current()) return
        await api.confirm(draft.kind, draft.id, request)
        if (!current()) return
        const result = await api.draft(draft.kind, draft.id)
        if (!current()) return
        selected.value = result
        await refresh()
        message.success('已确认入库')
      }).finally(() => {
        confirming.value = false
        confirmationModal = null
      })
  })
}

async function createMember() {
  if (!memberName.value.trim() || !memberAuthorized.value)
    return message.warning('请填写成员称呼，并确认本人或合法代理授权')
  await perform(async () => {
    const result = await api.createMember({
      display_name: memberName.value,
      relationship_label: relationship.value,
      authorized: true
    })
    memberModal.value = false
    members.value = await api.members()
    memberId.value = result.id
    memberName.value = ''
    memberAuthorized.value = false
    await refresh()
  })
}

async function saveGrant() {
  if (!grantActor.value.trim()) return message.warning('请填写被授权账号 UID')
  await perform(async () => {
    await api.grant(memberId.value, { actor_uid: grantActor.value, scopes: grantScopes.value })
    grantModal.value = false
    message.success('授权范围已保存；空范围表示撤回')
  })
}

function deleteSource(job) {
  Modal.confirm({
    title: '删除该任务的源文件？',
    content:
      '将删除其私有原图和解析结果，并使所有关联草稿及记录不可访问。共享同一文件的任务也会失效，此操作不能撤销。',
    okText: '删除文件',
    okType: 'danger',
    onOk: () =>
      perform(async () => {
        const task = await apiRequestJob(job.task_id)
        for (const upload of task.uploads) await api.removeUpload(upload.upload_id)
        selected.value = null
        await refresh()
        message.success('源文件已删除，关联结果已失效')
      })
  })
}

/** 任务详情读取也走已认证的 API 层。 */
function apiRequestJob(id) {
  return api.task(id)
}

/** 在脚本作用域生成重试编号，模板不直接读取浏览器全局。 */
async function retryJob(job) {
  const id = memberId.value
  const sequence = memberSequence
  await perform(async () => {
    let request = retryRequests.get(job.task_id)
    if (!request) {
      request = { client_request_id: crypto.randomUUID() }
      retryRequests.set(job.task_id, request)
    }
    await api.retry(job.task_id, request)
    if (disposed || sequence !== memberSequence || id !== memberId.value) return
    await refresh()
    if (disposed || sequence !== memberSequence || id !== memberId.value) return
    retryRequests.delete(job.task_id)
  })
}
</script>

<template>
  <div class="health-workbench">
    <PageHeader
      title="健康识图"
      v-model:active-key="activeTab"
      :tabs="tabs"
      :loading="loading || busy"
    />
    <main class="workbench-content">
      <a-alert v-if="pageError" :message="pageError" type="error" show-icon
        ><template #action><a-button @click="initialize">重试</a-button></template></a-alert
      >
      <template v-if="config">
        <div class="intro">
          <div class="intro-icon"><ScanLine :size="28" /></div>
          <div>
            <h1>从照片到可复核的健康记录</h1>
            <p>私有存储 · 原文证据 · 人工确认后入库</p>
          </div>
          <a-tag color="cyan"><ShieldCheck :size="12" /> 不自动生成医疗建议</a-tag>
        </div>
        <div v-if="tab !== 'settings'" class="member-toolbar">
          <label
            >健康成员<a-select
              v-model:value="memberId"
              placeholder="选择已授权成员"
              :disabled="busy || confirming"
              style="min-width: 200px"
              ><a-select-option v-for="item in members" :key="item.id" :value="item.id"
                >{{ item.display_name }} · {{ item.relationship_label }}</a-select-option
              ></a-select
            ></label
          ><a-button :disabled="busy" @click="memberModal = true"
            ><Plus :size="14" /> 新建成员</a-button
          ><a-button v-if="member?.is_owner" @click="grantModal = true">成员授权</a-button
          ><a-button :disabled="busy || !memberId" @click="perform(refresh)"
            ><RefreshCw :size="14" /> 刷新</a-button
          ><a-tooltip
            :title="
              config.consultation?.reason ||
              (!canConsult
                ? '请先选择同时具备 AI 使用、报告查看和饮食维护授权的成员'
                : '基于当前成员已确认记录进行咨询')
            "
          >
            <a-button :disabled="busy || confirming || !canConsult" @click="openConsultation()">
              今日营养咨询
            </a-button>
          </a-tooltip>
          <a-button :disabled="busy || confirming || !canConsult" @click="openConsultation('new')"
            >新建营养咨询</a-button
          >
          <span v-if="!config.consultation?.available" class="consultation-status"
            >咨询未启用：{{ config.consultation?.reason || '尚未配置咨询模型' }}</span
          >
        </div>
        <HealthVisionAdmin
          v-if="tab === 'settings' && userStore.isAdmin"
          :configuration="config"
          @saved="initialize"
        />
        <div v-else-if="tab === 'profile'" class="profile-panels">
          <HealthFamilyProfile
            :key="`family-${memberId}`"
            :member="member"
            :disabled="busy || confirming"
            @consult="openConsultation('new')"
          />
          <HealthProfessionalProfile
            :key="`professional-${memberId}`"
            :member="member"
            :disabled="busy || confirming"
            @plans="activeTab = 'plans'"
          />
        </div>
        <HealthMemoryDaily
          v-else-if="tab === 'memory'"
          :member-id="memberId"
          :scopes="member?.scopes || []"
        />
        <HealthMealPlans
          v-else-if="tab === 'plans'"
          :member-id="memberId"
          :members="members"
          :scopes="member?.scopes || []"
          :configuration="config"
          @profile="activeTab = 'profile'"
        />
        <template v-else-if="tab === 'report' || tab === 'meal'">
          <section class="panel upload-panel">
            <div class="section-title">
              <FileHeart v-if="tab === 'report'" :size="22" /><Utensils v-else :size="22" />
              <h2>{{ tab === 'report' ? '健康报告识别' : '饮食照片识别' }}</h2>
              <a-tag :color="config[purpose].available ? 'green' : 'orange'">{{
                config[purpose].available ? '服务已配置' : '服务待配置'
              }}</a-tag>
            </div>
            <a-alert
              v-if="!config[purpose].available"
              :message="`${config[purpose].reason}。当前不会调用云模型，您仍可人工录入。`"
              type="warning"
              show-icon
            />
            <a-alert
              v-if="!memberId"
              message="尚无授权成员，请先新建健康成员。管理员身份不代表有权读取其他人的健康数据。"
              type="info"
              show-icon
            />
            <div class="upload-area">
              <ScanLine :size="32" /><strong>{{
                tab === 'report' ? '上传体检报告 / 检验单' : '上传同一餐的 1—3 张照片'
              }}</strong>
              <p>
                {{
                  tab === 'report'
                    ? '支持 JPG、PNG、WebP、PDF；报告总计最多 20 页'
                    : '支持 JPG、PNG、WebP；不同餐请分别提交'
                }}
              </p>
              <p>图片 ≤10MB，PDF ≤20MB。请避免无关人员与身份证等隐私信息。</p>
              <input
                ref="uploadInput"
                type="file"
                multiple
                :accept="tab === 'report' ? '.jpg,.jpeg,.png,.webp,.pdf' : '.jpg,.jpeg,.png,.webp'"
                :disabled="
                  busy || !member?.scopes.includes(tab === 'report' ? 'report_upload' : 'diet_edit')
                "
                @change="selectFiles"
              />
              <ul v-if="files.length">
                <li v-for="file in files" :key="`${file.name}-${file.size}`">
                  {{ file.name }} · {{ (file.size / 1024 / 1024).toFixed(2) }}MB
                </li>
              </ul>
            </div>
            <div v-if="tab === 'report'" class="meal-context">
              <label
                >顺时针旋转<a-select
                  v-model:value="reportRotation"
                  :disabled="busy || !!uploads.length"
                >
                  <a-select-option v-for="angle in [0, 90, 180, 270]" :key="angle" :value="angle"
                    >{{ angle }}°</a-select-option
                  >
                </a-select></label
              >
              <label
                >倾斜校正（顺时针为正，度）<a-input-number
                  v-model:value="deskewAngle"
                  :min="-10"
                  :max="10"
                  :step="0.5"
                  :disabled="busy || !!uploads.length"
              /></label>
            </div>
            <p v-if="tab === 'report'" class="privacy-note">
              方向和角度应用于本次全部报告页，只改变处理副本。原始文件保留；PDF
              按文档方向渲染后再调整。上传后参数固定，要改角度请重新选择文件。人工校正不保证文字可识别。
            </p>
            <div v-if="tab === 'report'" class="actions">
              <a-button
                :disabled="
                  busy ||
                  !files.length ||
                  !!uploads.length ||
                  !member?.scopes.includes('report_upload') ||
                  !member?.scopes.includes('report_view')
                "
                @click="prepareReport"
                >上传并预览处理页</a-button
              >
              <small>仅本地私有存储，不调用云模型</small>
            </div>
            <div v-if="tab === 'report' && uploads.length" class="prepared-pages">
              <div v-for="(upload, index) in uploads" :key="upload.upload_id">
                <strong>{{ files[index]?.name }} · {{ upload.page_count }} 页</strong>
                <a-button
                  v-for="page in upload.page_count"
                  :key="page"
                  size="small"
                  :disabled="busy"
                  @click="perform(() => showPreparedPage(upload, page - 1))"
                  >查看处理页 {{ page }}</a-button
                >
              </div>
            </div>
            <div v-if="tab === 'meal'" class="meal-context">
              <label
                >餐次<a-select v-model:value="mealType" :disabled="busy"
                  ><a-select-option v-for="(label, key) in mealLabels" :key="key" :value="key">{{
                    label
                  }}</a-select-option></a-select
                ></label
              ><label
                >就餐时间（本地时区）<input
                  v-model="eatenAt"
                  type="datetime-local"
                  :disabled="busy"
              /></label>
            </div>
            <a-checkbox
              v-model:checked="cloudConsent"
              :disabled="busy || !config[purpose].available || !memberId"
              >我已获得该成员授权，同意本次将{{
                tab === 'report'
                  ? '报告处理页发送给 PaddleOCR，脱敏文本发送给字段模型'
                  : '照片发送给视觉模型'
              }}，用途仅为本次识别（政策 {{ config.policy_version || '尚未批准' }}）。</a-checkbox
            >
            <p class="privacy-note">
              处理方：{{
                config[purpose].processor || '未配置'
              }}；您可以撤回用途同意。每账号每天最多 10
              个任务。请先确认数据跨境及敏感信息处理政策已获得批准。
            </p>
            <div class="actions">
              <a-button
                type="primary"
                :loading="busy"
                :disabled="
                  !memberId || !files.length || !cloudConsent || !config[purpose].available
                "
                @click="startRecognition"
                >上传并开始识别</a-button
              ><a-button
                :disabled="
                  busy ||
                  !memberId ||
                  !member?.scopes.includes(tab === 'report' ? 'profile_edit' : 'diet_edit')
                "
                @click="manualDraft"
                >人工录入</a-button
              ><a-button
                :disabled="
                  busy ||
                  !member?.scopes.includes('ai_use') ||
                  !config[purpose].processor ||
                  !config.policy_version
                "
                @click="
                  perform(async () => {
                    await api.consent(memberId, {
                      purpose,
                      accepted: false,
                      processor: config[purpose].processor,
                      policy_version: config.policy_version
                    })
                    cloudConsent = false
                    message.success('用途同意已撤回')
                  })
                "
                >撤回本用途同意</a-button
              >
            </div>
          </section>
          <HealthVisionStatistics
            :member-id="memberId"
            :kind="purpose"
            :allowed="!!member?.scopes.includes(purpose === 'report' ? 'report_view' : 'diet_edit')"
          />
          <div class="history-grid">
            <section class="panel">
              <h2>识别任务</h2>
              <a-empty v-if="!scopedJobs.length" description="暂无任务；提交后在这里查看真实进度" />
              <div v-for="job in scopedJobs" :key="job.task_id" class="history-row">
                <div>
                  <strong>{{ statusLabels[job.execution_status] || job.execution_status }}</strong
                  ><small>{{ new Date(job.created_at).toLocaleString() }}</small
                  ><small v-if="job.phase === 'partial_ready'"
                    >部分页面未识别成功，请打开草稿处理</small
                  ><a-progress
                    v-if="['pending', 'running'].includes(job.execution_status)"
                    :percent="Math.round(job.progress || 0)"
                    size="small"
                  /><small v-if="job.error_code"
                    >错误：{{ job.error_code }}，可重试或人工录入</small
                  >
                </div>
                <div class="row-actions">
                  <a-button v-if="job.result_id" size="small" @click="openDraft(job.result_id)"
                    >打开草稿</a-button
                  ><a-button
                    v-if="['pending', 'running'].includes(job.execution_status)"
                    size="small"
                    :disabled="busy"
                    @click="
                      perform(async () => {
                        await api.cancel(job.task_id)
                        await refresh()
                      })
                    "
                    >{{ job.cancel_requested ? '取消处理中' : '取消' }}</a-button
                  ><a-button
                    v-if="['failed', 'cancelled'].includes(job.execution_status)"
                    size="small"
                    :disabled="busy"
                    @click="retryJob(job)"
                    >重试</a-button
                  ><a-button size="small" danger :disabled="busy" @click="deleteSource(job)"
                    >删除源文件</a-button
                  >
                </div>
              </div>
            </section>
            <section class="panel">
              <h2>复核草稿</h2>
              <a-empty v-if="!scopedDrafts.length" description="识别完成或人工录入后产生草稿" />
              <div v-for="draft in scopedDrafts" :key="draft.id" class="history-row">
                <div>
                  <strong>{{ reviewLabels[draft.review_status] || draft.review_status }}</strong
                  ><small
                    >{{ draft.model_version ? '模型提取' : '人工录入' }} · v{{ draft.version }} ·
                    {{ new Date(draft.created_at).toLocaleString() }}</small
                  >
                </div>
                <a-button size="small" @click="openDraft(draft.id)">{{
                  draft.review_status === 'confirmed' ? '查看快照' : '复核'
                }}</a-button>
              </div>
            </section>
          </div>
          <section v-if="selected" class="panel review-panel">
            <div class="section-title">
              <h2>{{ selected.kind === 'report' ? '报告指标复核' : '食物与份量复核' }}</h2>
              <a-tag>{{ reviewLabels[selected.review_status] }}</a-tag
              ><small>草稿 v{{ selected.version }}{{ dirty ? ' · 尚未保存' : '' }}</small>
            </div>
            <ReportReview
              v-if="selected.kind === 'report'"
              :key="selected.id"
              :payload="selected.payload"
              :readonly="!editable || busy"
              :confirmed="selected.review_status === 'confirmed'"
              :can-reprocess="canReprocessReport"
              @changed="changed"
              @excluded-pages="excludeReportPages"
              @reprocess-page="reprocessReportPage"
              @add="addResult"
            /><MealReview
              v-else
              :key="selected.id"
              :payload="selected.payload"
              :readonly="!editable || busy"
              @changed="changed"
              @add="addResult"
            />
            <template v-if="editable"
              ><div class="save-area">
                <label
                  >修订原因<a-input
                    v-model:value="editReason"
                    :maxlength="500"
                    :disabled="busy" /></label
                ><a-button
                  :disabled="busy || !dirty || !editReason.trim()"
                  @click="perform(saveDraft)"
                  >保存修订</a-button
                ><a-button v-if="selected.kind === 'meal'" :disabled="busy" @click="calculate"
                  >计算当前营养预览</a-button
                >
              </div>
              <div v-if="calculation" class="calculation">
                <div class="section-title">
                  <h3>营养预览</h3>
                  <a-tag :color="calculation.complete ? 'green' : 'orange'">{{
                    calculation.complete ? '数据完整' : '数据不完整'
                  }}</a-tag
                  ><a-tag v-if="calculation.estimated" color="orange">估算</a-tag>
                </div>
                <div class="nutrient-grid">
                  <div v-for="([label, unit], key) in nutrientLabels" :key="key">
                    <small>{{ label }}</small
                    ><strong>{{ nutrientText(calculation.totals[key], unit) }}</strong>
                  </div>
                </div>
                <p v-if="calculation.missing.length">
                  缺失项：{{
                    calculation.missing
                      .map((item) => (typeof item === 'string' ? item : JSON.stringify(item)))
                      .join('；')
                  }}。未知值不记为零。
                </p>
                <p v-for="(source, sourceIndex) in calculation.sources" :key="sourceIndex">
                  {{ source.name || source.unit_label }}：{{ source.source }} ·
                  {{ source.edition }} · {{ source.dataset_version }} · {{ source.license }}
                </p>
                <a-checkbox v-if="!calculation.complete" v-model:checked="acceptIncomplete"
                  >我理解缺失数据不会被计为零，接受保存不完整的饮食日记</a-checkbox
                >
              </div>
              <div class="confirm-area">
                <a-checkbox v-model:checked="reviewed" :disabled="busy || dirty"
                  >我已逐项核对上述结果及所属成员，确认记录准确</a-checkbox
                ><a-button
                  type="primary"
                  :loading="busy"
                  :disabled="
                    dirty ||
                    !reviewed ||
                    (selected.kind === 'meal' &&
                      (!calculation || (!calculation.complete && !acceptIncomplete)))
                  "
                  @click="confirmDraft"
                  >确认入库</a-button
                >
              </div></template
            >
          </section>
        </template>
        <div v-else-if="tab === 'records'" class="history-grid">
          <section class="panel">
            <h2>已确认健康指标</h2>
            <a-empty v-if="!records.report.length" description="仅展示人工确认的正式记录" />
            <div v-for="record in records.report" :key="record.id" class="record">
              <strong
                >{{ record.snapshot.name }}：{{ record.snapshot.value_raw }}
                {{ record.snapshot.unit_raw }}</strong
              >
              <p>
                参考区间：{{ record.snapshot.reference_raw || '未知' }} · 检查日期：{{
                  record.snapshot.observed_at || '未知'
                }}
              </p>
              <small
                >{{ record.snapshot.source === 'ocr' ? 'OCR 提取后人工确认' : '人工录入' }} ·
                {{ new Date(record.created_at).toLocaleString() }}</small
              >
            </div>
          </section>
          <section class="panel">
            <h2>已确认饮食日记</h2>
            <a-empty v-if="!records.meal.length" description="待确认草稿不进入饮食日记" />
            <div v-for="record in records.meal" :key="record.id" class="record">
              <strong
                >{{ mealLabels[record.snapshot.meal.meal_type] }} ·
                {{ new Date(record.snapshot.meal.eaten_at).toLocaleString() }}</strong
              ><a-tag v-if="record.snapshot.nutrition.estimated" color="orange">估算</a-tag>
              <p v-for="([label, unit], key) in nutrientLabels" :key="key">
                {{ label }}：{{ nutrientText(record.snapshot.nutrition.totals[key], unit) }}
              </p>
              <small>计算版本：{{ record.snapshot.nutrition.calculation_version }}</small>
              <HealthMealFeedback :record="record" />
            </div>
          </section>
        </div>
      </template>
    </main>
    <a-modal
      v-model:open="consultationOpen"
      :title="consultationMode === 'new' ? '新建成员专属营养咨询' : '进入今日营养咨询'"
      ok-text="同意并进入"
      :confirm-loading="busy"
      :ok-button-props="{
        disabled: !consultationConsent || !canConsult || consultationSourceInvalidated
      }"
      @ok="enterConsultation"
    >
      <p>
        当前成员：{{
          member?.display_name
        }}。会话创建后不能更换成员；咨询按当前授权读取已确认记录、已关联的本人确认档案及独立实测体重、血压、血糖、血脂四项。
      </p>
      <p>处理方：{{ config?.consultation?.processor }}；政策：{{ config?.policy_version }}。</p>
      <p>
        咨询会将问题和必要的已确认记录、本人档案及实测体重、血压、血糖、血脂四项发送给已审批模型。实测与档案确认版本分开，
        体重、血压、血糖、血脂各仅包含近30个北京时间自然日最多20条记录；体重保留原值与kg，血压保留成对收缩压、舒张压与mmHg，
        血糖保留原值、mmol/L及空腹、餐后2小时或随机的测量条件；血脂保留同条总胆固醇、甘油三酯、高密度脂蛋白、低密度脂蛋白原值与mmol/L，
        均含测量时间、来源、记录ID和版本。报告原图或 OCR 原文证据、实测备注、血压和血脂测量条件及更正历史不发送。
        营养安全评估与21天控糖仍未就绪，当前不生成个人配餐或治疗方案。
      </p>
      <p v-if="consultationMode === 'new'">将创建新的独立咨询，保留原会话。</p>
      <a-alert
        v-if="!canConsult"
        :message="config?.consultation?.reason || '当前成员缺少咨询所需授权'"
        type="warning"
        show-icon
      />
      <a-alert v-if="consultationError" :message="consultationError" type="error" show-icon>
        <template v-if="consultationSourceInvalidated" #action>
          <a-button :disabled="busy" @click="openConsultation('new')">新建咨询</a-button>
        </template>
      </a-alert>
      <a-checkbox v-model:checked="consultationConsent">{{
        member?.is_owner && member?.relationship_label === '本人'
          ? '我单独同意本次营养咨询用途的云处理。'
          : '我有权代理此成员，并单独同意本次营养咨询用途的云处理。'
      }}</a-checkbox>
    </a-modal>
    <a-modal
      v-model:open="preparedPreviewOpen"
      :title="preparedPreviewLabel"
      :footer="null"
      width="800px"
      @after-close="clearPreparedPreview"
    >
      <p>这是供识别与证据定位使用的同一处理副本，请核对完整性、方向和清晰度。</p>
      <img
        v-if="preparedPreview"
        :src="preparedPreview"
        class="prepared-image"
        alt="私有报告处理页预览"
      />
    </a-modal>
    <a-modal
      v-model:open="memberModal"
      title="新建健康成员"
      :confirm-loading="busy"
      ok-text="建档"
      @ok="createMember"
      ><a-form layout="vertical"
        ><a-form-item label="成员称呼"
          ><a-input
            v-model:value="memberName"
            :maxlength="80"
            placeholder="建议使用昵称，不填写身份证号码" /></a-form-item
        ><a-form-item label="与账号的关系"
          ><a-input v-model:value="relationship" :maxlength="40" /></a-form-item
        ><a-checkbox v-model:checked="memberAuthorized"
          >这是本人档案，或我已获得有效的代理 / 监护授权；建档不自动授权其他家庭成员访问</a-checkbox
        ></a-form
      ></a-modal
    >
    <a-modal v-model:open="grantModal" title="成员访问授权" :confirm-loading="busy" @ok="saveGrant"
      ><p>仅档案所有者可操作，平台管理员不会自动获得访问权限。</p>
      <a-input
        v-model:value="grantActor"
        placeholder="被授权账号 UID（非成员 ID）"
        :maxlength="100"
      /><a-checkbox-group
        v-model:value="grantScopes"
        :options="Object.entries(scopeLabels).map(([value, label]) => ({ value, label }))"
      />
      <p>范围为空将撤回该账号授权，正在运行的任务也会重新校验。</p></a-modal
    >
  </div>
</template>

<style scoped lang="less">
.profile-panels {
  display: grid;
  gap: 24px;
}
.health-workbench {
  height: 100%;
  overflow-y: auto;
  color: var(--gray-1000);
  background: var(--gray-50);
}
.workbench-content {
  max-width: 1440px;
  margin: auto;
  padding: 24px;
}
.intro {
  display: flex;
  gap: 14px;
  align-items: center;
  margin-bottom: 24px;
  flex-wrap: wrap;
  h1 {
    margin: 0;
    font-size: 24px;
    letter-spacing: -0.5px;
    color: var(--gray-1000);
  }
  p {
    margin: 6px 0 0;
    color: var(--gray-600);
  }
  .intro-icon {
    display: grid;
    place-items: center;
    width: 54px;
    height: 54px;
    background: color-mix(in srgb, var(--main-color) 12%, var(--gray-0));
    color: var(--main-color);
    border-radius: 16px;
  }
  .ant-tag {
    margin-left: auto;
    display: flex;
    gap: 5px;
    align-items: center;
  }
}
.member-toolbar,
.actions,
.section-title,
.save-area,
.confirm-area {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.member-toolbar {
  margin-bottom: 20px;
  label {
    display: flex;
    align-items: center;
    gap: 12px;
  }
}
.panel {
  padding: 20px;
  border: 1px solid var(--gray-200);
  border-radius: 12px;
  background: var(--gray-0);
  margin-bottom: 18px;
  min-width: 0;
  h2 {
    font-size: 17px;
    font-weight: 600;
    margin: 0 0 16px;
    color: var(--gray-1000);
  }
}
.section-title {
  margin-bottom: 14px;
  color: var(--main-color);
  h2,
  h3 {
    margin: 0;
    color: var(--gray-1000);
  }
  small {
    margin-left: auto;
    color: var(--gray-600);
  }
}
.upload-area {
  padding: 28px 20px;
  border: 1px dashed var(--gray-300);
  border-radius: 10px;
  margin: 16px 0;
  background: var(--gray-50);
  display: flex;
  align-items: center;
  flex-direction: column;
  gap: 8px;
  text-align: center;
  svg {
    color: var(--main-color);
  }
  p {
    margin: 0;
    color: var(--gray-600);
    font-size: 13px;
  }
  ul {
    margin: 0;
    padding-left: 18px;
    word-break: break-word;
  }
  input {
    max-width: 100%;
  }
}
.meal-context {
  display: flex;
  gap: 20px;
  margin: 16px 0;
  flex-wrap: wrap;
  label {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 170px;
  }
}
.prepared-pages {
  margin: 16px 0;
  > div {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
    margin-bottom: 8px;
  }
  strong {
    width: 100%;
    overflow-wrap: anywhere;
  }
}
.prepared-image {
  max-width: 100%;
  height: auto;
}
input[type='datetime-local'] {
  padding: 5px 10px;
  border: 1px solid var(--gray-300);
  border-radius: 6px;
  color: var(--gray-1000);
  background: var(--gray-0);
}
.privacy-note {
  font-size: 12px;
  color: var(--gray-600);
  line-height: 1.8;
}
.history-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}
.history-row {
  padding: 14px 0;
  display: flex;
  align-items: center;
  gap: 12px;
  border-top: 1px solid var(--gray-100);
  > div:first-child {
    flex: 1;
    min-width: 0;
  }
  small {
    display: block;
    margin-top: 6px;
    color: var(--gray-600);
  }
  .row-actions {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    justify-content: flex-end;
  }
}
.save-area {
  margin-top: 20px;
  label {
    display: flex;
    align-items: center;
    gap: 10px;
    flex: 1;
    min-width: 200px;
  }
}
.confirm-area {
  border-top: 1px solid var(--gray-200);
  padding-top: 20px;
  margin-top: 20px;
  justify-content: space-between;
}
.calculation {
  border-radius: 10px;
  background: var(--gray-50);
  padding: 16px;
  margin-top: 20px;
  p {
    font-size: 12px;
    color: var(--gray-600);
    word-break: break-word;
  }
}
.nutrient-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  small,
  strong {
    display: block;
  }
  small {
    color: var(--gray-600);
    margin-bottom: 8px;
  }
}
.record {
  border-top: 1px solid var(--gray-200);
  padding: 16px 0;
  p {
    color: var(--gray-700);
    margin: 6px 0;
  }
  small {
    color: var(--gray-600);
  }
}
@media (max-width: 900px) {
  .history-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .workbench-content {
    padding: 16px;
  }
  .intro h1 {
    font-size: 20px;
  }
  .intro .ant-tag {
    margin-left: 0;
  }
}
@media (max-width: 600px) {
  .nutrient-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .panel {
    padding: 14px;
  }
  .history-row {
    flex-direction: column;
    align-items: stretch;
  }
  :deep(.page-header) {
    height: auto;
    min-height: 48px;
    padding: 10px;
  }
  :deep(.page-header-left) {
    flex-wrap: wrap;
  }
  :deep(.page-header-tabs) {
    padding-left: 0;
    border: none;
    flex-wrap: wrap;
    height: auto;
    max-width: 100%;
    flex-shrink: 1;
    row-gap: 8px;
  }
}
</style>
