import assert from 'node:assert/strict'
import test from 'node:test'
import { createPinia, setActivePinia } from 'pinia'
import { createServer } from 'vite'

test('普通用户通过工作区读取解析原文；错误 JSON 不能伪装成空正文', async () => {
  const server = await createServer({
    server: { middlewareMode: true },
    appType: 'custom',
    optimizeDeps: { noDiscovery: true, include: [] },
    ssr: { noExternal: ['ant-design-vue'] },
    plugins: [
      {
        name: 'source-api-test-message',
        enforce: 'pre',
        resolveId(id) {
          return id === 'ant-design-vue' ? '\0source-test-message' : null
        },
        load(id) {
          return id === '\0source-test-message' ? 'export const message = { error() {} }' : null
        }
      }
    ]
  })
  const previousStorage = globalThis.localStorage
  const previousFetch = globalThis.fetch
  globalThis.localStorage = { getItem: () => 'reader-token', setItem() {}, removeItem() {} }
  try {
    setActivePinia(createPinia())
    const { useUserStore } = await server.ssrLoadModule('/src/stores/user.js')
    const user = useUserStore()
    user.token = 'reader-token'
    user.role = 'user'
    const { getKnowledgeSourceDocument } = await server.ssrLoadModule('/src/apis/knowledge_api.js')
    globalThis.fetch = async (url) => {
      assert.equal(
        url,
        '/api/workspace/knowledge/download?kb_id=kb_source&file_id=file_recipe&variant=parsed'
      )
      return new Response('ingredients\nmethod', {
        headers: {
          'Content-Type': 'text/markdown; charset=utf-8',
          'Content-Disposition': "attachment; filename*=UTF-8''recipe.md.parsed.md",
          'X-Yuxi-Source-Hash': 'a'.repeat(64)
        }
      })
    }
    const document = await getKnowledgeSourceDocument('kb_source', 'file_recipe')
    assert.equal(document.content, 'ingredients\nmethod')
    assert.equal(document.meta.filename, 'recipe.md')
    assert.equal(document.meta.content_hash, 'a'.repeat(64))
    globalThis.fetch = async () =>
      new Response(JSON.stringify({ status: 'failed' }), {
        headers: { 'Content-Type': 'application/json' }
      })
    await assert.rejects(
      getKnowledgeSourceDocument('kb_source', 'file_recipe'),
      /原文解析结果不可用/
    )
  } finally {
    globalThis.localStorage = previousStorage
    globalThis.fetch = previousFetch
    await server.close()
  }
})
