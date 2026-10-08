<script setup>
import { ref, onBeforeUnmount } from 'vue'
import { message } from 'ant-design-vue'
import { healthVisionApi } from '@/apis/health_vision_api'

const props = defineProps({
  payload: { type: Object, required: true },
  readonly: Boolean,
  confirmed: Boolean,
  canReprocess: Boolean
})
const emit = defineEmits(['changed', 'add', 'excluded-pages', 'reprocess-page'])
const preview = ref('')
const selectedEvidence = ref(null)
const loading = ref(false)
let previewRequest = 0

/** 通过鉴权接口展示服务器指定页，不能依赖公共图片代理。 */
async function showEvidence(field) {
  const page = props.payload.pages.find((item) => item.page_index === field.evidence.page_index)
  if (!page) return message.error('该字段没有可定位的报告页')
  return showPage(page, field.evidence)
}

/** 失败页也能通过私有鉴权预览，不伪造字段级证据。 */
async function showPage(page, evidence = null) {
  const request = ++previewRequest
  loading.value = true
  try {
    const blob = await healthVisionApi.preview(page.upload_id, page.upload_page_index)
    if (request !== previewRequest) return
    if (preview.value) URL.revokeObjectURL(preview.value)
    preview.value = URL.createObjectURL(blob)
    selectedEvidence.value = evidence
  } catch (error) {
    message.error(error.message)
  } finally {
    if (request === previewRequest) loading.value = false
  }
}

/** 排除是明确的人工决策，保存后才参与确认。 */
function togglePage(page, excluded) {
  if (props.readonly) return
  const indices = props.payload.excluded_pages.filter((index) => index !== page.page_index)
  if (excluded) indices.push(page.page_index)
  emit(
    'excluded-pages',
    indices.sort((a, b) => a - b)
  )
}

/** 重识别由父页面提交版本化任务，组件不能自行外发图片。 */
function reprocessPage(page) {
  if (!props.readonly && props.canReprocess) emit('reprocess-page', page.page_index)
}

/** 识别状态与人工确认分开展示，排除页仍保留失败事实。 */
function pageLabel(page) {
  const extraction = page.status === 'failed' ? '未识别成功' : '识别成功'
  const review = props.payload.excluded_pages.includes(page.page_index)
    ? '已明确排除'
    : props.confirmed
      ? '已确认快照'
      : page.status === 'failed'
        ? '需处理'
        : '待核对'
  return `${extraction} · ${review}`
}

onBeforeUnmount(() => {
  previewRequest++
  if (preview.value) URL.revokeObjectURL(preview.value)
})

/** 确定性数字才转换；比较符号、阴阳性仍保留原文。 */
function updateValue(field) {
  field.value_numeric = /^[+-]?\d+(?:\.\d+)?$/.test(field.value_raw) ? field.value_raw : null
  emit('changed')
}

function closePreview() {
  previewRequest++
  if (preview.value) URL.revokeObjectURL(preview.value)
  preview.value = ''
}
</script>

<template>
  <div class="report-review">
    <a-alert
      message="请逐项核对姓名所属成员、结果、单位和参考区间。日期与空腹状态不明确时保持未知；本功能不提供诊断。"
      type="info"
      show-icon
    />
    <section v-if="payload.pages.length" class="page-review">
      <strong>报告页复核 · 共 {{ payload.pages.length }} 页</strong>
      <p>请核对是否缺页、顺序正确以及文字清晰；识别成功不代表已人工复核。</p>
      <a-alert
        v-if="payload.pages.some((page) => page.status === 'failed')"
        type="warning"
        show-icon
        :message="
          confirmed
            ? '此已确认快照保留失败页及人工排除记录，仅已接受指标写入档案。这不是完整报告。'
            : '报告有未识别成功的页。其他页结果已保留；可保存修改并确认上方云处理同意后只重识别失败页，也可重新上传，或明确排除后保存再确认。不应将此结果视为完整报告。'
        "
      />
      <div v-for="page in payload.pages" :key="page.page_index" class="page-row">
        <strong>第 {{ page.page_index + 1 }} 页</strong>
        <a-tag :color="page.status === 'failed' ? 'orange' : 'blue'">
          {{ pageLabel(page) }}
        </a-tag>
        <small v-if="page.error_code">原因：{{ page.error_code }}</small>
        <small v-if="page.quality_flags?.includes('low_resolution')"
          >分辨率较低，请核对原文或重新拍摄</small
        >
        <a-button size="small" :loading="loading" @click="showPage(page)">查看原页</a-button>
        <a-button
          v-if="page.status === 'failed' && !confirmed"
          size="small"
          :disabled="readonly || !canReprocess"
          title="请先保存修订，并在上方确认本用途云处理同意；仅重识别此页，可能再次计费"
          @click="reprocessPage(page)"
          >只重识别此页</a-button
        >
        <a-checkbox
          :checked="payload.excluded_pages.includes(page.page_index)"
          :disabled="readonly"
          @change="togglePage(page, $event.target.checked)"
          >明确排除此页</a-checkbox
        >
      </div>
      <small v-if="payload.excluded_pages.length"
        >已排除 {{ payload.excluded_pages.length }} 页：这些页的指标不会写入档案。</small
      >
    </section>
    <div v-for="(field, index) in payload.fields" :key="field.field_id" class="field-card">
      <div class="field-heading">
        <strong>指标 {{ index + 1 }}</strong
        ><a-tag>{{
          field.source === 'ocr'
            ? confirmed
              ? 'OCR 来源 · 已确认快照'
              : 'OCR 候选 · 需人工复核'
            : '人工录入'
        }}</a-tag
        ><a-checkbox v-model:checked="field.excluded" :disabled="readonly" @change="emit('changed')"
          >排除此项</a-checkbox
        >
      </div>
      <div class="field-grid">
        <label
          >指标名称<a-input
            v-model:value="field.name"
            :disabled="readonly"
            :maxlength="120"
            placeholder="如：空腹血糖"
            @change="emit('changed')"
        /></label>
        <label
          >原始结果<a-input
            v-model:value="field.value_raw"
            :disabled="readonly"
            :maxlength="500"
            placeholder="保留原文，如 <0.1、阴性"
            @change="updateValue(field)"
        /></label>
        <label
          >原始单位<a-input
            v-model:value="field.unit_raw"
            :disabled="readonly"
            :maxlength="100"
            placeholder="未知时留空"
            @change="emit('changed')"
        /></label>
        <label
          >参考区间<a-input
            v-model:value="field.reference_raw"
            :disabled="readonly"
            :maxlength="500"
            placeholder="按报告原文填写"
            @change="emit('changed')"
        /></label>
        <label
          >检查日期<input
            v-model="field.observed_at"
            type="date"
            :disabled="readonly"
            @change="emit('changed')"
        /></label>
        <label
          >空腹状态<a-select
            v-model:value="field.fasting"
            :disabled="readonly"
            @change="emit('changed')"
            ><a-select-option value="unknown">未知</a-select-option
            ><a-select-option value="yes">空腹</a-select-option
            ><a-select-option value="no">非空腹</a-select-option></a-select
          ></label
        >
      </div>
      <div v-if="field.evidence" class="evidence">
        <a-button size="small" :loading="loading" @click="showEvidence(field)"
          >查看第 {{ field.evidence.page_index + 1 }} 页原文</a-button
        >
        <pre>{{ field.evidence.raw_text }}</pre>
        <small
          >证据块 {{ field.evidence.block_id }} ·
          {{ field.evidence.bbox ? '有原文区域定位' : '无可靠坐标，仅定位整页' }}</small
        >
      </div>
      <small v-if="field.review_flags.length">复核标记：{{ field.review_flags.join(' / ') }}</small>
    </div>
    <a-button v-if="!readonly && payload.fields.length < 300" @click="emit('add')"
      >添加指标</a-button
    >
    <a-empty
      v-if="!payload.fields.length"
      description="没有可确认指标，请人工补充或重新上传清晰报告"
    />
    <a-modal
      :open="!!preview"
      title="报告原文证据"
      :footer="null"
      width="850px"
      @cancel="closePreview"
    >
      <div class="page-preview">
        <img :src="preview" alt="鉴权后的报告处理页" />
        <div
          v-if="selectedEvidence?.bbox"
          class="bbox"
          :style="{
            left: `${selectedEvidence.bbox[0] * 100}%`,
            top: `${selectedEvidence.bbox[1] * 100}%`,
            width: `${(selectedEvidence.bbox[2] - selectedEvidence.bbox[0]) * 100}%`,
            height: `${(selectedEvidence.bbox[3] - selectedEvidence.bbox[1]) * 100}%`
          }"
        />
      </div>
    </a-modal>
  </div>
</template>

<style scoped lang="less">
.page-review {
  margin: 16px 0;
  p {
    color: var(--gray-600);
  }
}
.page-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  border-bottom: 1px solid var(--gray-200);
  padding: 12px 0;
}
.field-card {
  border: 1px solid var(--gray-200);
  padding: 16px;
  margin: 14px 0;
  border-radius: 10px;
}
.field-heading {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin-bottom: 14px;
}
.field-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  label {
    display: flex;
    flex-direction: column;
    gap: 6px;
    color: var(--gray-700);
  }
}
input[type='date'] {
  background: var(--gray-0);
  color: var(--gray-1000);
  border: 1px solid var(--gray-300);
  border-radius: 6px;
  padding: 5px 10px;
  min-width: 0;
}
.evidence {
  margin-top: 12px;
  pre {
    white-space: pre-wrap;
    word-break: break-word;
    color: var(--gray-800);
  }
}
small {
  color: var(--gray-600);
}
.page-preview {
  position: relative;
  img {
    width: 100%;
    display: block;
  }
  .bbox {
    position: absolute;
    border: 2px solid var(--main-color);
    background: color-mix(in srgb, var(--main-color) 10%, transparent);
    pointer-events: none;
  }
}
@media (max-width: 700px) {
  .field-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
