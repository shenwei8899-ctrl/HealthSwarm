const plain = segments => (segments || []).map(segment => segment.text).join('')
const mealName = '(?:早餐|早饭|午餐|午饭|晚餐|晚饭|加餐)'
const mealLabel = new RegExp('^' + mealName + '(?=$|[\\s（(:：\\d])')
const mealPrefix = new RegExp('^\\s*(' + mealName + '(?:\\s*[（(][^）)\\n]+[）)])?)\\s*[:：]\\s*')
const mealHeaders = ['餐次', '餐别', '用餐时段']
const foodHeaders = ['用餐候选', '食物与份量', '食物及份量', '菜品', '菜品搭配', '推荐搭配', '餐单', '菜单', '建议食物', '推荐食物', '食物', '用餐建议', '推荐菜品']

/** 切分排版时保留原文及加粗、链接文本等内联样式。 */
function sliceSegments(segments, start, end = Infinity) {
  const result = []; let offset = 0
  for (const segment of segments) {
    const from = Math.max(0, start - offset), to = Math.min(segment.text.length, end - offset)
    if (to > from) result.push({ ...segment, text: segment.text.slice(from, to) })
    offset += segment.text.length
  }
  return result
}

function sectionBlocks(segments) {
  const match = plain(segments).match(mealPrefix)
  if (!match) return null
  const start = match[0].indexOf(match[1]), body = sliceSegments(segments, match[0].length)
  return [{ type: 'heading', level: 3, segments: sliceSegments(segments, start, start + match[1].length) },
    ...(plain(body) ? [{ type: 'paragraph', segments: body }] : [])]
}

/** 聊天餐次只作文字排版；普通段落、列表和正式业务餐单保持各自的路径。 */
export function chatMealAnswerBlocks(blocks) {
  return blocks.flatMap(block => {
    if (block.type === 'paragraph') {
      const lines = plain(block.segments).split('\n')
      if (lines.length > 1 && lines.every(line => mealPrefix.test(line))) {
        let offset = 0
        return lines.flatMap(line => {
          const segments = sliceSegments(block.segments, offset, offset + line.length)
          offset += line.length + 1
          return sectionBlocks(segments)
        })
      }
      return sectionBlocks(block.segments) || [block]
    }
    if (block.type === 'list' && block.items.length && block.items.every(item => mealPrefix.test(plain(item.segments))))
      return block.items.flatMap(item => sectionBlocks(item.segments))
    if (block.type !== 'table') return [block]
    const headers = block.headers.map(segments => plain(segments).trim())
    const mealColumn = headers.findIndex(header => mealHeaders.includes(header))
    const foodColumn = headers.findIndex(header => foodHeaders.includes(header))
    if (mealColumn < 0 || foodColumn < 0 || !block.rows.length ||
        block.rows.some(row => !mealLabel.test(plain(row[mealColumn]).trim()) || row.length > headers.length)) return [block]
    return block.rows.flatMap(row => [
      { type: 'heading', level: 3, segments: row[mealColumn] },
      { type: 'list', items: headers.flatMap((header, column) => column === mealColumn || !plain(row[column]).trim() ? [] : [{
        marker: '', level: 0, segments: [
          ...(column !== foodColumn && header ? [...block.headers[column], { text: '：' }] : []), ...row[column],
        ],
      }]) },
    ])
  })
}
