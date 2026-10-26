// 知识库引用只映射到本站阅读页，权限由正文接口检查。
export const knowledgeSourceHref = ({ kbId, fileId, line, endLine, hash } = {}) => {
  if (!/^kb_[\w-]+$/.test(kbId || '') || !/^file_[\w-]+$/.test(fileId || '')) return null
  const query = new URLSearchParams()
  if (Number.isSafeInteger(Number(line)) && Number(line) > 0) query.set('line', Number(line))
  if (Number.isSafeInteger(Number(endLine)) && Number(endLine) >= Number(line)) {
    query.set('end_line', Number(endLine))
  }
  if (/^[a-f0-9]{64}$/i.test(hash || '')) query.set('hash', hash)
  const suffix = query.size ? `?${query}` : ''
  return `/knowledge/source/${encodeURIComponent(kbId)}/${encodeURIComponent(fileId)}${suffix}`
}

export const resolveKnowledgeReference = (value) => {
  const match = String(value || '').match(
    /^knowledge:\/\/(kb_[\w-]+)\/(file_[\w-]+)(?:#([a-f0-9]{64}|L(\d+)(?:-L?(\d+))?))?$/i
  )
  if (!match) return null
  return knowledgeSourceHref({
    kbId: match[1],
    fileId: match[2],
    hash: match[3],
    line: match[4],
    endLine: match[5]
  })
}
