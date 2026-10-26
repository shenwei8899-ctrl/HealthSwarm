import assert from 'node:assert/strict'
import test from 'node:test'
import {
  resolveKnowledgeReference,
  knowledgeSourceHref
} from '../../src/utils/knowledgeSourceLinks.js'
import { createMarkdownRenderer } from '../../src/utils/markdown_preview.js'

test('知识库引用只打开本站对应文件，并保留版本和行号', () => {
  const hash = 'a'.repeat(64)
  assert.equal(
    resolveKnowledgeReference(`knowledge://kb_abc/file_123#${hash}`),
    `/knowledge/source/kb_abc/file_123?hash=${hash}`
  )
  assert.equal(
    resolveKnowledgeReference('knowledge://kb_abc/file_123#L21-L28'),
    '/knowledge/source/kb_abc/file_123?line=21&end_line=28'
  )
  assert.equal(knowledgeSourceHref({ kbId: '../other', fileId: 'file_123' }), null)
  for (const input of [
    'javascript:alert(1)',
    'knowledge://evil.example/file_123',
    'knowledge://kb_abc/file_123/../../other',
    'knowledge://kb_abc/file_123#bad'
  ]) {
    assert.equal(resolveKnowledgeReference(input), null)
  }
})

test('显式与裸引用生成可点击链接，代码块保留原文', () => {
  const renderer = createMarkdownRenderer({ themeName: 'github-light' })
  const uri = 'knowledge://kb_abc/file_123#L21-L28'
  const output = renderer.render(`[原文](${uri})\n\n${uri}\n\n\`${uri}\``)
  assert.equal(
    (output.match(/href="\/knowledge\/source\/kb_abc\/file_123\?line=21&amp;end_line=28"/g) || [])
      .length,
    2
  )
  assert.ok(output.includes(`<code>${uri}</code>`))
})
