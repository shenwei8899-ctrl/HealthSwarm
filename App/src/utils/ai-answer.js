// The answer stays plain data: rendering never executes model supplied HTML.
const UUID = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/ig
const FILE_REFERENCE = /[（(]\s*文件名\s*[:：]\s*([\s\S]*?\.(?:markdown|md|pdf|docx?|txt|html?))\s*[）)]/ig
const INTERNAL_REFERENCE = /\[(?:资料|证据|来源|文档|食材包)\s*[:：][^\]\n]*\]/g

export function sourceTitle(value) {
  let title = String(value || '').replace(INTERNAL_REFERENCE, '').replace(UUID, '').trim()
  if (/\.(?:markdown|md|pdf|docx?|txt|html?)$/i.test(title) && !/^https?:\/\//i.test(title)) title = title.split(/[\\/]/).pop()
  title = title.replace(/^文件名\s*[:：]\s*/, '').replace(/\.(?:markdown|md|pdf|docx?|txt|html?)$/i, '')
  // Keep the human title; ingestion often appends an English storage filename.
  if (/[\u3400-\u9fff]/.test(title)) title = title.replace(/[_]+[a-z][a-z0-9_. -]*$/i, '')
  return title.replace(/\*\*|__|`/g, '').replace(/^\[|\]$/g, '').trim()
}

function extractReferences(value, citations, streaming) {
  const sources = []
  const add = value => { const title = sourceTitle(value); if (title && !sources.includes(title)) sources.push(title) }
  for (const citation of Array.isArray(citations) ? citations : []) {
    if (typeof citation === 'string') add(citation)
    else if (citation && typeof citation === 'object') add(citation.title || citation.document_title || citation.source_title || citation.name)
  }
  let text = String(value || '').replace(/\r\n?/g, '\n')
  text = text.replace(FILE_REFERENCE, (_, name) => { add(name); return '' }).replace(INTERNAL_REFERENCE, '').replace(/\[[0-9a-f-]{36}\]/ig, '')
  text = text.replace(/(?:资料|证据|来源|文档)\s*(?:ID|编号)?\s*[:：]\s*[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/ig, '').replace(UUID, '')
  text = text.replace(/(?:资料|证据|来源|文档)\s*(?:ID|编号)\s*[:：]\s*[0-9a-f-]*$/ig, '')
  // A partial citation must not expose a document id or storage path, including
  // an interrupted response that is no longer marked as streaming.
  text = text.replace(/\[(?:资料|证据|来源|文档|食材包)\s*[:：][^\]]*$/, '').replace(/[（(]\s*文件名\s*[:：][\s\S]*$/, '')
  if (streaming) text = text.replace(/\[(?:资|资料|证|证据|来|来源|文|文档|食|食材|食材包)\s*$/, '')
  return { text: text.replace(/[ \t]+\n/g, '\n'), sources }
}

export function answerSegments(value) {
  const text = String(value || '')
    .replace(/!?\[([^\]\n]*)\]\([^\n)]*\)/g, '$1')
    .replace(/!?\[([^\]\n]*)\]\([^\n)]*$/, '$1')
  const segments = []
  const strong = { value: false }, emphasis = { value: false }, code = { value: false }
  const append = content => {
    if (!content) return
    const last = segments[segments.length - 1]
    if (last && last.strong === strong.value && last.emphasis === emphasis.value && last.code === code.value) last.text += content
    else segments.push({ text: content, strong: strong.value, emphasis: emphasis.value, code: code.value })
  }
  for (let i = 0; i < text.length;) {
    if (text[i] === '\\' && /[\\`*_~\[\]#|]/.test(text[i + 1] || '')) { append(text[i + 1]); i += 2; continue }
    const pair = text.slice(i, i + 2)
    if (!code.value && (pair === '**' || pair === '__')) { strong.value = !strong.value; i += 2; continue }
    if (text[i] === '`') { code.value = !code.value; i++; continue }
    if (!code.value && pair === '~~') { i += 2; continue }
    if (!code.value && (text[i] === '*' || text[i] === '_') && (emphasis.value || (text[i + 1] && !/\s/.test(text[i + 1]) && !/\w/.test(text[i - 1] || '')))) { emphasis.value = !emphasis.value; i++; continue }
    append(text[i]); i++
  }
  return segments
}

function cells(line) {
  const content = line.trim().replace(/^\|/, '').replace(/([^\\])\|$/, '$1'), result = []
  let cell = ''
  for (let i = 0; i < content.length; i++) {
    if (content[i] === '\\' && content[i + 1] === '|') { cell += '|'; i++ }
    else if (content[i] === '|') { result.push(cell.trim()); cell = '' }
    else cell += content[i]
  }
  result.push(cell.trim())
  return result
}
function tableRule(line) { return line.includes('|') && cells(line).every(cell => /^:?-{3,}:?$/.test(cell)) }
function listLine(line) { return /^(\s*)(?:(\d+)[.)、]|[-+*])\s+(.+)$/.exec(line) }
function startsBlock(lines, index) {
  const line = lines[index] || ''
  return /^(?:\s*#{1,6}\s|\s*>|\s*```|\s*~~~|\s*([-*_])(?:\s*\1){2,}\s*$)/.test(line) || listLine(line) || (line.includes('|') && tableRule(lines[index + 1] || ''))
}

export function parseAiAnswer(value, { citations = [], streaming = false } = {}) {
  const { text, sources } = extractReferences(value, citations, streaming)
  const lines = text.split('\n'), blocks = []
  const pushText = (type, content, extra = {}) => { if (content.trim()) blocks.push({ type, segments: answerSegments(content.trim()), ...extra }) }
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) { i++; continue }
    if (streaming && /^\s*(?:#{1,6}|[-+*]|>)\s*$/.test(line)) { i++; continue }
    const heading = /^\s*(#{1,6})\s+(.+?)(?:\s+#+)?\s*$/.exec(line)
    if (heading) { pushText('heading', heading[2], { level: heading[1].length }); i++; continue }
    if (/^\s*([-*_])(?:\s*\1){2,}\s*$/.test(line)) { blocks.push({ type: 'divider' }); i++; continue }
    if (/^\s*(```|~~~)/.test(line)) {
      const fence = line.trim().slice(0, 3), content = []; i++
      while (i < lines.length && !lines[i].trim().startsWith(fence)) content.push(lines[i++])
      if (i < lines.length) i++
      if (content.length) blocks.push({ type: 'code', text: content.join('\n') })
      continue
    }
    if (line.includes('|') && tableRule(lines[i + 1] || '')) {
      const headers = cells(line).map(answerSegments), rows = []; i += 2
      while (i < lines.length && lines[i].includes('|') && lines[i].trim()) rows.push(cells(lines[i++]).map(answerSegments))
      blocks.push({ type: 'table', headers, rows }); continue
    }
    if (/^\s*>/.test(line)) {
      const content = []
      while (i < lines.length && /^\s*>/.test(lines[i])) content.push(lines[i++].replace(/^\s*>\s?/, ''))
      pushText('quote', content.join('\n')); continue
    }
    if (listLine(line)) {
      const items = []
      while (i < lines.length) {
        const match = listLine(lines[i])
        if (!match) break
        let content = match[3]; i++
        while (i < lines.length && /^\s+\S/.test(lines[i]) && !startsBlock(lines, i)) content += '\n' + lines[i++].trim()
        items.push({ marker: match[2] ? match[2] : '', level: Math.min(2, Math.floor(match[1].replace(/\t/g, '  ').length / 2)), segments: answerSegments(content) })
      }
      blocks.push({ type: 'list', items }); continue
    }
    const content = [line]; i++
    while (i < lines.length && lines[i].trim() && !startsBlock(lines, i)) content.push(lines[i++])
    pushText('paragraph', content.join('\n'))
  }
  return { blocks, sources }
}
