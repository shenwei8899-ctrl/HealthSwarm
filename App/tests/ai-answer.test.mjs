import test from 'node:test'
import assert from 'node:assert/strict'
import { answerSegments, parseAiAnswer } from '../src/utils/ai-answer.js'

const visible = answer => answer.blocks.map(block => block.segments?.map(s => s.text).join('') || block.items?.map(item => item.segments.map(s => s.text).join('')).join('\n') || block.text || '').join('\n')

test('streamed purchase receipts and evidence ids stay hidden without losing readable content', () => {
  const token = 'signed_receipt_'.repeat(12)
  assert.equal(visible(parseAiAnswer(`可核对食材清单。[食材包:${token}]`)), '可核对食材清单。')
  assert.equal(visible(parseAiAnswer(`尚在整理。[食材包:${token}`, {streaming:true})), '尚在整理。')
  assert.equal(visible(parseAiAnswer('参考资料。[证据:11111111-1111-4111-8111-111111111111]')), '参考资料。')
})

test('answers become native semantic blocks without Markdown formatting symbols', () => {
  const answer = parseAiAnswer('# 今天这样吃\n\n先保持**规律进餐**，不要突然停药。\n\n1. **早餐**：鸡蛋、燕麦\n2. 午餐：蔬菜\n\n> 如有肾病，请先咨询医护人员。')
  assert.deepEqual(answer.blocks.map(block => block.type), ['heading', 'paragraph', 'list', 'quote'])
  assert.equal(answer.blocks[2].items[0].marker, '1')
  assert.ok(answer.blocks[1].segments.some(segment => segment.strong && segment.text === '规律进餐'))
  assert.doesNotMatch(visible(answer), /\*\*|^#|^>/m)
  assert.match(visible(answer), /不要突然停药/)
  assert.match(visible(answer), /如有肾病，请先咨询医护人员/)
})

test('storage citations move to deduplicated human readable sources, preserving medical qualification', () => {
  const id = '96c82ed8-b878-469e-9110-e893c9bbb6a8'
  const text = `一般饮食建议。[资料:${id}]（文件名：成人糖尿病食养指南（2023年版）_nhc_diabetes_2023.md）\n\n不能替代个人诊疗。[资料:${id}]（文件名：成人糖尿病食养指南（2023年版）_nhc_diabetes_2023.md）`
  const answer = parseAiAnswer(text, { citations: [{ title: '已审核的公开指南' }, id] })
  assert.deepEqual(answer.sources, ['已审核的公开指南', '成人糖尿病食养指南（2023年版）'])
  assert.doesNotMatch(visible(answer), /96c82ed8|文件名|\.md/)
  assert.match(visible(answer), /不能替代个人诊疗/)
})

test('missing source titles never invent provenance; ordinary parentheses survive', () => {
  const answer = parseAiAnswer('一份水果（以个人耐受为准）。[资料:96c82ed8-b878-469e-9110-e893c9bbb6a8]', { citations: [{ id: 'unknown' }, {}] })
  assert.deepEqual(answer.sources, [])
  assert.equal(visible(answer), '一份水果（以个人耐受为准）。')
})

test('bare storage identifiers never appear in paragraphs, tables or code blocks', () => {
  const id='96c82ed8-b878-469e-9110-e893c9bbb6a8'
  for(const text of [`建议规律进餐。来源ID：${id}`,`| 建议 | 依据 |\n| --- | --- |\n| 规律进餐 | 证据编号：${id} |`,`\`\`\`text\n保持数值 30 g。资料：${id}\n\`\`\``]){
    const answer=parseAiAnswer(text)
    assert.doesNotMatch(JSON.stringify(answer),/96c82ed8|来源ID|证据编号|资料：/)
    assert.match(JSON.stringify(answer),/规律进餐|30 g/)
  }
  assert.equal(visible(parseAiAnswer('建议规律进餐。来源ID：96c82ed8-b878',{streaming:true})),'建议规律进餐。')
})

test('streamed incomplete references stay hidden and unclosed emphasis stays readable', () => {
  for (const suffix of ['[资料:96c82ed8-b878', '（文件名：成人糖尿病食养指南（2023']) {
    const answer = parseAiAnswer('选择**适量主食' + suffix, { streaming: true })
    assert.equal(visible(answer), '选择适量主食')
    assert.equal(answer.blocks[0].segments.at(-1).strong, true)
  }
  assert.equal(answerSegments('参考[指南](https://example.com/unfinished').map(segment => segment.text).join(''), '参考指南')
  assert.equal(visible(parseAiAnswer('###', { streaming: true })), '')
  assert.equal(visible(parseAiAnswer('需要保留[资料:96c82ed8', { streaming: false })), '需要保留')
})

test('tables produce labelled card data that retains long values, missing cells and units', () => {
  const answer = parseAiAnswer('| 餐次 | 食物与份量 | 提醒 |\n| :--- | --- | ---: |\n| 早餐 | 燕麦 30 g、鸡蛋 1 个 | 视个人情况调整 |\n| 午餐 | 不要停药 |')
  const table = answer.blocks[0]
  assert.equal(table.type, 'table')
  assert.equal(table.headers[1][0].text, '食物与份量')
  assert.equal(table.rows[0][1][0].text, '燕麦 30 g、鸡蛋 1 个')
  assert.equal(table.rows[1][1][0].text, '不要停药')
  assert.equal(table.rows[1].length, 2)
})

test('formatting links keeps their actual labels; HTML is plain data rather than interpreted markup', () => {
  const answer = parseAiAnswer('[公开指南](https://example.com) 与 `<img onerror=alert(1)>`')
  assert.equal(visible(answer), '公开指南 与 <img onerror=alert(1)>')
  assert.ok(answer.blocks[0].segments.some(segment => segment.code))
})

test('multiline lists and code retain their content without fences', () => {
  const answer = parseAiAnswer('- 第一条\n  继续说明\n  - 子条目\n\n```text\n保持原始数值 3 * 2\n```')
  assert.equal(answer.blocks[0].items[0].segments[0].text, '第一条\n继续说明')
  assert.equal(answer.blocks[0].items[1].level, 1)
  assert.equal(answer.blocks[1].text, '保持原始数值 3 * 2')
  assert.equal(visible(parseAiAnswer('每份 3 * 2 g；*适量*即可。')), '每份 3 * 2 g；适量即可。')
})

test('escaped table pipes stay in a single cell without newer regexp features', () => {
  const table = parseAiAnswer('| 食物 | 备注 |\n| --- | --- |\n| A\\|B | 按需 |').blocks[0]
  assert.equal(table.rows[0].length, 2)
  assert.equal(table.rows[0][0][0].text, 'A|B')
})
