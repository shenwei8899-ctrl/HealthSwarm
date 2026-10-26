import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import * as Vue from 'vue'
import { renderToString } from 'vue/server-renderer'

const source = readFileSync(
  new URL('../../src/views/KnowledgeSourceView.vue', import.meta.url),
  'utf8'
)
const template = source.split('<template>')[1].split('</template>\n\n<script setup>')[0]
const script = source
  .split('<script setup>')[1]
  .split('</script>')[0]
  .replace(/^import .*$/gm, '')
const setup = new Function(
  'computed',
  'ref',
  'watch',
  'useRoute',
  'getKnowledgeSourceDocument',
  `${script}; return { document, error, loading, showFull, lines, startLine, endLine, visibleLines, versionChanged }`
)

const harness = (fetchDocument, query = {}) => {
  const route = Vue.reactive({ params: { kbId: 'kb_source', fileId: 'file_recipe' }, query })
  const scope = Vue.effectScope()
  const state = scope.run(() => setup(Vue.computed, Vue.ref, Vue.watch, () => route, fetchDocument))
  const render = () =>
    renderToString(
      Vue.createSSRApp({
        setup: () => state,
        components: {
          PageHeader: { props: ['title'], template: '<h1>{{ title }}</h1>' },
          AAlert: { props: ['message'], template: '<div role="alert">{{ message }}</div>' },
          AButton: { template: '<button><slot /></button>' },
          MarkdownPreview: { props: ['content'], template: '<article>{{ content }}</article>' }
        },
        render: Vue.compile(template)
      })
    )
  return { route, state, render, close: () => scope.stop() }
}
const flush = async () => {
  await Promise.resolve()
  await Vue.nextTick()
}

test('引用页显示实际行号与上下文，完整正文按需展开并提示版本变化', async () => {
  const h = harness(
    async () => ({
      meta: { filename: '菜谱.md', content_hash: 'current' },
      content: Array.from({ length: 57 }, (_, i) => `正文${i + 1}`).join('\n') + '\n'
    }),
    { line: '21', end_line: '28', hash: 'previous' }
  )
  try {
    await flush()
    assert.equal(h.state.lines.value.length, 57)
    const html = await h.render()
    assert.match(html, /第 21–28 行，共 57 行/)
    assert.match(html, /data-line="21"/)
    assert.match(html, /引用的文件版本已变化/)
    assert.ok(!html.includes('<article>'))
    h.state.showFull.value = true
    assert.ok((await h.render()).includes('正文57'))
  } finally {
    h.close()
  }
})

test('PDF 换页符及 Unicode 分隔符与后端 splitlines 行号一致', async () => {
  const h = harness(
    async () => ({ meta: { filename: '指南' }, content: 'a\fb\nc\u2028d\u0085e\v' }),
    { line: '2' }
  )
  try {
    await flush()
    assert.deepEqual(h.state.lines.value, ['a', 'b', 'c', 'd', 'e'])
    assert.equal(h.state.visibleLines.value.find((row) => row.number === 2).text, 'b')
    assert.match(await h.render(), /第 2–2 行，共 5 行/)
  } finally {
    h.close()
  }
})

test('切换来源后旧响应不能回填另一文件的正文', async () => {
  const pending = []
  const h = harness(() => new Promise((resolve) => pending.push(resolve)))
  try {
    h.route.params.fileId = 'file_other'
    await Vue.nextTick()
    pending[1]({ meta: { filename: '当前文件' }, content: '当前正文' })
    await flush()
    pending[0]({ meta: { filename: '旧文件' }, content: '旧正文' })
    await flush()
    assert.equal(h.state.document.value.content, '当前正文')
  } finally {
    h.close()
  }
})

test('拒绝读取时展示权限错误且不保留上一份正文', async () => {
  const h = harness(async () => {
    throw Object.assign(new Error('denied'), { status: 403 })
  })
  try {
    await flush()
    const html = await h.render()
    assert.match(html, /没有权限读取这份资料/)
    assert.equal(h.state.document.value, null)
    assert.equal(h.state.loading.value, false)
  } finally {
    h.close()
  }
})
