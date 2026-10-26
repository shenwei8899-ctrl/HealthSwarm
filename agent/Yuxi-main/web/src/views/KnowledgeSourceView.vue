<template>
  <main class="knowledge-source layout-container">
    <PageHeader :title="document?.meta?.filename || '知识库原文'" :loading="loading" />
    <a-alert v-if="error" type="error" :message="error" show-icon />
    <template v-else-if="document">
      <a-alert
        v-if="versionChanged"
        type="warning"
        message="引用的文件版本已变化，当前显示现有版本。"
        show-icon
      />
      <p v-if="!lines.length">该文件尚未生成可阅读的解析正文。</p>
      <template v-else>
        <p class="source-location">第 {{ startLine }}–{{ endLine }} 行，共 {{ lines.length }} 行</p>
        <pre class="source-window" aria-label="引用原文"><span
          v-for="row in visibleLines" :key="row.number"
          :class="{ cited: row.number >= startLine && row.number <= endLine }"
          :data-line="row.number"
        ><span class="line-number">{{ row.number }}</span>{{ row.text }}{{ '\n' }}</span></pre>
        <a-button @click="showFull = !showFull">{{
          showFull ? '收起完整正文' : '阅读完整正文'
        }}</a-button>
        <MarkdownPreview v-if="showFull" :content="document.content" />
      </template>
    </template>
  </main>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getKnowledgeSourceDocument } from '@/apis/knowledge_api'
import PageHeader from '@/components/shared/PageHeader.vue'
import MarkdownPreview from '@/components/common/MarkdownPreview.vue'

const route = useRoute()
const document = ref(null)
const error = ref('')
const loading = ref(false)
const showFull = ref(false)
let requestVersion = 0
const lines = computed(() => {
  const content = document.value?.content || ''
  if (!content) return []
  // 与后端 Python splitlines 一致，PDF 换页符也占独立行。
  // eslint-disable-next-line no-control-regex
  const result = content.split(/\r\n|[\n\r\v\f\u001c-\u001e\u0085\u2028\u2029]/)
  if (result.at(-1) === '') result.pop()
  return result
})
const startLine = computed(() =>
  Math.min(Math.max(Number.parseInt(route.query.line, 10) || 1, 1), lines.value.length || 1)
)
const endLine = computed(() =>
  Math.min(
    Math.max(Number.parseInt(route.query.end_line, 10) || startLine.value, startLine.value),
    lines.value.length
  )
)
const visibleLines = computed(() =>
  lines.value
    .slice(Math.max(startLine.value - 21, 0), endLine.value + 20)
    .map((text, index) => ({ text, number: Math.max(startLine.value - 21, 0) + index + 1 }))
)
const versionChanged = computed(
  () => route.query.hash && document.value?.meta?.content_hash !== route.query.hash
)

watch(
  () => [route.params.kbId, route.params.fileId],
  async ([kbId, fileId]) => {
    const version = ++requestVersion
    loading.value = true
    error.value = ''
    document.value = null
    showFull.value = false
    try {
      const result = await getKnowledgeSourceDocument(kbId, fileId)
      if (version === requestVersion) document.value = result
    } catch (cause) {
      if (version === requestVersion)
        error.value =
          cause?.status === 403
            ? '没有权限读取这份资料。'
            : '无法读取这份资料，请确认文件仍存在且当前账号有访问权限。'
    } finally {
      if (version === requestVersion) loading.value = false
    }
  },
  { immediate: true }
)
</script>

<style scoped lang="less">
.knowledge-source {
  padding: 24px;
  overflow: auto;
}
.source-location {
  color: var(--gray-600);
  margin: 16px 0 8px;
}
.source-window {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: var(--gray-50);
  color: var(--gray-800);
  padding: 16px;
  border-radius: 8px;
  max-height: 60vh;
  overflow: auto;
}
.cited {
  background: var(--color-primary-100);
}
.line-number {
  display: inline-block;
  min-width: 4em;
  color: var(--gray-500);
  user-select: none;
}
</style>
