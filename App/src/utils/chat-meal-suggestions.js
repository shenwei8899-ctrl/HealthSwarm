const plain = segments => (segments || []).map(segment => segment.text).join('').trim()
const mealNames = { 早餐: 'breakfast', 早饭: 'breakfast', 午餐: 'lunch', 午饭: 'lunch', 晚餐: 'dinner', 晚饭: 'dinner', 加餐: 'snack' }
const mealHeaders = ['餐次', '餐别', '用餐时段']
const foodHeaders = ['用餐候选', '食物与份量', '食物及份量', '菜品', '菜品搭配', '推荐搭配', '餐单', '菜单', '建议食物', '推荐食物', '食物', '用餐建议', '推荐菜品']

function mealSection(text) {
  const match = String(text).trim().match(/^(?:\d+[.)、]\s*)?((早餐|早饭|午餐|午饭|晚餐|晚饭|加餐)(?:\s*[（(][^）)\n]+[）)])?)\s*(?:[:：]\s*(.*))?$/)
  return match ? { label: match[1], type: mealNames[match[2]], food: match[3] || '' } : null
}

function addMealCopy(meal, value) {
  const text = String(value).trim()
  const note = text.match(/^(搭配(?:思路|理由|建议)?|说明|提醒|注意事项|份量(?:建议)?|营养提示)\s*[:：]\s*([\s\S]+)$/)
  if (note) meal.notes.push({ label: note[1], text: note[2] })
  else meal.dishes.push(...splitMealDishes(text))
}

/** 将 Agent 已生成的餐次内容统一展示，不依赖用户提问措辞或单一表格格式。 */
export function chatMealAnswerBlocks(blocks, { streaming = false } = {}) {
  const expanded = blocks.flatMap(block => {
    if (block.type !== 'paragraph') return [block]
    const lines = plain(block.segments).split('\n')
    // 连续的“早餐：… / 午餐：…”也可能被 Markdown 解析成同一个段落。
    return lines.length > 1 && lines.every(line => mealSection(line))
      ? lines.map(line => ({ type: 'paragraph', segments: [{ text: line }] })) : [block]
  })
  const output = []
  for (let index = 0; index < expanded.length;) {
    const block = expanded[index], table = chatMealSuggestions(block)
    if (table) { output.push({ type: 'meal-suggestions', ...table }); index++; continue }
    // “1. 早餐：… 2. 午餐：…”本身就是一个列表。
    if (block.type === 'list' && block.items.length && block.items.every(item => mealSection(plain(item.segments))?.food)) {
      const meals = block.items.map(item => {
        const section = mealSection(plain(item.segments)), meal = { ...section, dishes: [], notes: [] }
        addMealCopy(meal, section.food)
        return meal
      })
      const pending = streaming && index === expanded.length - 1
      output.push({ type: 'meal-suggestions', meals: pending ? meals.slice(0, -1) : meals, pending })
      index++; continue
    }
    const section = ['heading', 'paragraph'].includes(block.type) && mealSection(plain(block.segments))
    if (!section) { output.push(block); index++; continue }
    const meal = { ...section, dishes: [], notes: [] }
    if (section.food) addMealCopy(meal, section.food)
    let next = index + 1
    while (next < expanded.length) {
      const child = expanded[next]
      if (child.type === 'list' && !child.items.some(item => mealSection(plain(item.segments)))) {
        for (const item of child.items) addMealCopy(meal, plain(item.segments))
      } else if (child.type === 'paragraph' && /^(?:搭配(?:思路|理由|建议)?|说明|提醒|注意事项|份量(?:建议)?|营养提示)\s*[:：]/.test(plain(child.segments))) {
        addMealCopy(meal, plain(child.segments))
      } else break
      next++
    }
    if (!meal.dishes.length) { output.push(block); index++; continue }
    // 列表会持续增长；下一段开始或最终回复到达后才把整餐交给卡片。
    const pending = streaming && next === expanded.length
    output.push({ type: 'meal-suggestions', meals: pending ? [] : [meal], pending })
    index = next
  }
  return output
}

/** 只在括号外拆分食物，保留份量、限制与原有顺序。 */
export function splitMealDishes(value) {
  const dishes = []; let current = '', depth = 0
  for (const char of String(value || '')) {
    if ('（([{'.includes(char)) depth++
    if ('）)]}'.includes(char)) depth = Math.max(0, depth - 1)
    if (!depth && /[+＋、;；\n]/.test(char)) {
      if (current.trim()) dishes.push(current.trim())
      current = ''
    } else current += char
  }
  if (current.trim()) dishes.push(current.trim())
  return dishes
}

/** 普通聊天中的餐次表格仅投影成展示卡，不创建或保存业务餐单。 */
export function chatMealSuggestions(block) {
  if (block.type !== 'table') return null
  const headers = block.headers.map(plain)
  const mealColumn = headers.findIndex(header => mealHeaders.includes(header))
  const foodColumn = headers.findIndex(header => foodHeaders.includes(header))
  if (mealColumn < 0 || foodColumn < 0) return null
  const meals = [], occurrences = {}; let pending = false
  for (let index = 0; index < block.rows.length; index++) {
    if (block.rowComplete?.[index] === false) { pending = true; continue }
    const row = block.rows[index], label = plain(row[mealColumn])
    const name = label.match(/^(早餐|早饭|午餐|午饭|晚餐|晚饭|加餐)(?=$|[\s（(:：\d])/)?.[1]
    const dishes = splitMealDishes(plain(row[foodColumn]))
    // 不吞掉无法识别的行、未知列或额外单元格。
    if (!name || !dishes.length || row.length > headers.length) return null
    const type = mealNames[name], occurrence = occurrences[type] || 0
    occurrences[type] = occurrence + 1
    meals.push({
      key: `${type}-${occurrence}`, type, label, dishes,
      notes: headers.flatMap((header, column) => column !== mealColumn && column !== foodColumn && plain(row[column])
        ? [{ label: header, text: plain(row[column]) }] : []),
    })
  }
  return { meals, pending }
}
