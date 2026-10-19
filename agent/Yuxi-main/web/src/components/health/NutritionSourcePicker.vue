<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { databaseApi, documentApi } from '@/apis/knowledge_api'
import { healthVisionApi } from '@/apis/health_vision_api'

const props = defineProps({ disabled: Boolean })
const emit = defineEmits(['selected'])
const databases = ref([])
const kb = ref('')
const query = ref('')
const files = ref([])
const offset = ref(0)
const hasMore = ref(false)
const loading = ref(false)
const error = ref('')
const selected = ref('')
let sequence = 0
let disposed = false

/** 按需读取来源目录，保留原始知识库权限。 */
async function loadDatabases() {
  if (props.disabled || loading.value) return
  const ticket = ++sequence
  loading.value = true
  error.value = ''
  try {
    const result = await databaseApi.getDatabases()
    if (!disposed && ticket === sequence) databases.value = result.databases
  } catch {
    if (!disposed && ticket === sequence) error.value = '知识库读取失败，请重试。'
  } finally {
    if (!disposed && ticket === sequence) loading.value = false
  }
}

/** 搜索仅返回文件名，正文继续由知识库页面管理。 */
async function search(nextOffset = 0) {
  if (!kb.value || !query.value.trim() || props.disabled) return
  const ticket = ++sequence
  loading.value = true
  error.value = ''
  files.value = []
  try {
    const result = await documentApi.searchDocuments(kb.value, {
      query: query.value.trim(),
      offset: nextOffset,
      limit: 20
    })
    if (disposed || ticket !== sequence) return
    files.value = result.files.filter((file) => !file.is_folder)
    offset.value = nextOffset
    hasMore.value = result.has_more
  } catch {
    if (!disposed && ticket === sequence) error.value = '来源搜索失败，请重试。'
  } finally {
    if (!disposed && ticket === sequence) loading.value = false
  }
}

/** 摘要由服务端回读，原件不会因被选中而获得专业批准。 */
async function choose(file) {
  if (props.disabled || loading.value) return
  const ticket = ++sequence
  loading.value = true
  error.value = ''
  try {
    const result = await healthVisionApi.nutritionSource(kb.value, file.file_id)
    if (disposed || ticket !== sequence) return
    emit('selected', result.source_ref)
    selected.value = result.filename
  } catch {
    if (!disposed && ticket === sequence)
      error.value = '无法绑定：请核对资料管理权限及原件是否完整。'
  } finally {
    if (!disposed && ticket === sequence) loading.value = false
  }
}
watch([kb, query], () => {
  sequence++
  files.value = []
  selected.value = ''
  loading.value = false
  hasMore.value = false
  offset.value = 0
})
watch(
  () => props.disabled,
  (disabled) => {
    if (disabled) {
      sequence++
      loading.value = false
    }
  }
)
onBeforeUnmount(() => {
  disposed = true
  sequence++
})
</script>

<template>
  <details class="source-picker">
    <summary>从项目知识库选择来源原件</summary>
    <p>选择后将回填来源及内容摘要。资料引用与专业审批分别登记。</p>
    <a-button :disabled="disabled" :loading="loading" @click="loadDatabases">加载知识库</a-button>
    <label
      >来源知识库
      <a-select
        v-model:value="kb"
        :disabled="disabled || loading"
        placeholder="选择知识库"
        :options="databases.map((item) => ({ value: item.kb_id, label: item.name }))"
      />
    </label>
    <label
      >原件文件名关键词
      <a-input v-model:value="query" :disabled="disabled" @press-enter="search()" />
    </label>
    <a-button :disabled="disabled || !kb || !query.trim()" :loading="loading" @click="search()"
      >搜索原件</a-button
    >
    <a-alert v-if="error" type="error" :message="error" show-icon />
    <ul v-if="files.length">
      <li v-for="file in files" :key="file.file_id">
        <span>{{ file.filename }}</span>
        <a-button size="small" :disabled="disabled || loading" @click="choose(file)"
          >绑定此原件</a-button
        >
      </li>
    </ul>
    <p v-else-if="kb && !loading">输入关键词搜索原件；未找到时可在来源字段填写可核验的外部出处。</p>
    <div v-if="offset || hasMore" class="pages">
      <a-button :disabled="disabled || loading || !offset" @click="search(offset - 20)"
        >上一页</a-button
      >
      <a-button :disabled="disabled || loading || !hasMore" @click="search(offset + 20)"
        >下一页</a-button
      >
    </div>
    <p v-if="selected" role="status">已回填：{{ selected }}</p>
  </details>
</template>

<style scoped>
.source-picker {
  margin: 12px 0;
  padding: 12px;
  border: 1px solid var(--gray-200);
  border-radius: 8px;
}
summary {
  cursor: pointer;
}
label {
  display: grid;
  gap: 6px;
  margin: 12px 0;
}
li,
.pages {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin: 8px 0;
}
ul {
  padding: 0;
  list-style: none;
}
li span {
  overflow-wrap: anywhere;
}
p {
  color: var(--color-text-secondary);
}
</style>
