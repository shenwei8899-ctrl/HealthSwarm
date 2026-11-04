import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, statSync } from 'node:fs'
import { computed, ref, watch, reactive, effectScope, nextTick } from 'vue'
import { parseAiAnswer } from '../src/utils/ai-answer.js'
import { chatMealSuggestions, chatMealAnswerBlocks, splitMealDishes } from '../src/utils/chat-meal-suggestions.js'
import { chatFoodCover } from '../src/utils/chat-food-cover.js'
import { chatFoodCovers } from '../src/data/chat-food-covers.js'

const heading = '| 餐次 | 用餐候选 | 搭配思路 |\n| --- | --- | --- |\n'
const breakfast = '| 早餐 | **燕麦粥** + 水煮蛋 + 牛奶 + 苹果 | 把主食、蛋类、奶类和水果搭配起来 |\n'
const lunch = '| 午餐 | 杂粮米饭 + 香菇蒸鸡 + 清炒西兰花 | 主食配荤菜和蔬菜，做法以蒸、炒为主 |\n'
const dinner = '| 晚餐 | 米饭 + 番茄炖豆腐 + 蒜蓉小白菜 | 换一种蛋白质食材，也更换蔬菜品种 |'
const table = (text, streaming = false) => parseAiAnswer(text, { streaming }).blocks.find(block => block.type === 'table')

test('截图三餐投影保留食物顺序、完整说明和餐次身份', () => {
  const result = chatMealSuggestions(table(heading + breakfast + lunch + dinner))
  assert.deepEqual(result.meals.map(meal => [meal.type, meal.label, meal.dishes[0]]), [
    ['breakfast', '早餐', '燕麦粥'], ['lunch', '午餐', '杂粮米饭'], ['dinner', '晚餐', '米饭'],
  ])
  assert.deepEqual(result.meals[0].dishes, ['燕麦粥', '水煮蛋', '牛奶', '苹果'])
  assert.equal(result.meals[1].notes[0].text, '主食配荤菜和蔬菜，做法以蒸、炒为主')
  assert.equal(result.pending, false)
})

test('逐字符流式输出在换行前不展示半张餐次卡，最终无换行的晚餐仍可显示', () => {
  for (let end = 1; end < breakfast.length; end++) {
    const result = chatMealSuggestions(table(heading + breakfast.slice(0, end), true))
    assert.equal(result.meals.length, 0, `premature card at ${end}`)
  }
  const streamed = chatMealSuggestions(table(heading + breakfast + lunch + dinner, true))
  assert.deepEqual(streamed.meals.map(meal => meal.type), ['breakfast', 'lunch'])
  assert.equal(streamed.pending, true)
  assert.equal(chatMealSuggestions(table(heading + breakfast + lunch + dinner)).meals.length, 3)
})

test('普通表格、非餐次数据和多余单元格不会被错误转换或丢弃', () => {
  assert.equal(chatMealSuggestions(table('| 指标 | 食物 |\n| --- | --- |\n| 血糖 | 未知 |')), null)
  assert.equal(chatMealSuggestions(table(heading + '| 血糖 | 不要停药 | 咨询医护人员 |')), null)
  assert.equal(chatMealSuggestions(table(heading + '| 早餐 | 燕麦粥 | 按需 | 必须保留的额外说明 |')), null)
  assert.equal(chatMealSuggestions({ type: 'paragraph', segments: [] }), null)
})

test('未知列和限制说明完整保留，缺失值不补造', () => {
  const result = chatMealSuggestions(table('| 提醒 | 菜品 | 餐次 | 份量 |\n| --- | --- | --- | --- |\n| 牛奶过敏者不要选 | 燕麦粥 + 苹果 | 早餐（7:30） | 由实际需求决定 |'))
  assert.equal(result.meals[0].label, '早餐（7:30）')
  assert.deepEqual(result.meals[0].notes, [{ label: '提醒', text: '牛奶过敏者不要选' }, { label: '份量', text: '由实际需求决定' }])
  assert.deepEqual(chatMealSuggestions(table(heading + '| 早餐 | 燕麦粥 |')).meals[0].notes, [])
})

test('食物拆分不拆开括号里的配料、份量和限制', () => {
  assert.deepEqual(splitMealDishes('燕麦粥（燕麦、水，适量）＋鸡蛋（1个）+ 苹果'), ['燕麦粥（燕麦、水，适量）', '鸡蛋（1个）', '苹果'])
  assert.deepEqual(splitMealDishes('米饭；番茄炖豆腐、青菜'), ['米饭', '番茄炖豆腐', '青菜'])
})

test('图片严格跟随首菜，份量和别名可匹配，不用后一道菜或相似菜冒充', () => {
  const meals = chatMealSuggestions(table(heading + breakfast + lunch + dinner)).meals
  assert.deepEqual(meals.map(meal => chatFoodCover(meal.dishes[0]).src.split('/').pop()), ['oatmeal.jpg', 'multigrain-rice.jpg', 'white-rice.jpg'])
  assert.equal(chatFoodCover('主食：燕麦粥（1碗）').src, chatFoodCover('燕麦粥').src)
  assert.equal(chatFoodCover('白米饭 100g').src, chatFoodCover('米饭').src)
  assert.equal(chatFoodCover('番茄牛肉盖饭'), null)
  assert.equal(chatFoodCover(splitMealDishes('未知菜 + 米饭')[0]), null)
  assert.equal(chatFoodCover('米饭（不要加糖）'), null)
  assert.equal(chatFoodCover('燕麦或全麦面包一份').src, '/static/bundles/oats.webp')
  assert.equal(chatFoodCover('白米饭一小碗').src, chatFoodCover('米饭').src)
  for (const cover of chatFoodCovers.filter(item => item.image.startsWith('/static/food/chat-meals/'))) assert.ok(statSync(new URL('../src' + cover.image, import.meta.url)).size < 30000)
})

function renderer(values = {}, seen = []) {
  const props = reactive({ text: '', citations: [], streaming: false, compact: true, animateMeals: true, messageKey: 'request-1', shownMeals: seen, ...values })
  const events = [], scope = effectScope()
  const source = readFileSync(new URL('../src/components/AiAnswer.vue', import.meta.url), 'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  const deps = { computed, ref, watch, parseAiAnswer, chatMealAnswerBlocks, defineProps: () => props,
    defineEmits: () => (name, event) => { events.push([name, event]); seen.push(event.key) } }
  const state = scope.run(() => new Function('deps', `const {${Object.keys(deps)}}=deps;${source};return {displayBlocks,answer}`)(deps))
  return { ...state, props, events, dispose: () => scope.stop() }
}

test('流式已出现餐次移交最终回复后不重播，最后完成的晚餐仍淡入', async () => {
  const seen = [], live = renderer({ text: heading + breakfast, streaming: true }, seen)
  assert.equal(live.displayBlocks.value[0].meals[0].animate, true)
  live.props.text += lunch + dinner
  await nextTick()
  assert.equal(live.events.length, 2)
  const final = renderer({ text: '下面是三餐候选。\n\n' + heading + breakfast + lunch + dinner }, seen)
  assert.deepEqual(final.displayBlocks.value.find(block => block.type === 'meal-suggestions').meals.map(meal => meal.animate), [false, false, true])
  assert.deepEqual(final.events.map(([, event]) => event.key), ['dinner:0'])
  final.props.text += '\n\n今天规律进餐，少量多次饮水。'
  await nextTick()
  assert.equal(final.events.length, 1)
  live.dispose(); final.dispose()
})

test('同批卡片依次错开，历史恢复、重复刷新不播放新动画', async () => {
  const fresh = renderer({ text: heading + breakfast + lunch + dinner })
  assert.deepEqual(fresh.displayBlocks.value[0].meals.map(meal => meal.delay), [0, 90, 180])
  fresh.props.citations = ['公开膳食指南']
  await nextTick()
  assert.equal(fresh.events.length, 3)
  const history = renderer({ text: heading + breakfast + lunch + dinner, animateMeals: false })
  assert.deepEqual(history.displayBlocks.value[0].meals.map(meal => meal.animate), [false, false, false])
  assert.equal(history.events.length, 0)
  fresh.dispose(); history.dispose()
})

const listIntro = '下面是一份今日普通饮食候选，仅供参考，不保存为正式餐单，也不是个体化治疗方案。当前未读取到你的过敏、忌口、医嘱或完整营养档案，若有这些限制，请先按实际情况替换。'
const listBreakfast = '早餐\n\n- 燕麦或全麦面包一份\n\n- 水煮蛋1个\n\n- 无糖牛奶或无糖豆浆一杯\n\n- 一个水果，如苹果或橙子'
const listLunch = '## 午餐：\n\n- 杂粮米饭一小碗\n- 香菇蒸鸡\n- 清炒西兰花\n\n搭配思路：主食配荤菜和蔬菜。'
const listDinner = '**晚餐**\n\n- 米饭一小碗\n- 番茄炖豆腐\n- 蒜蓉小白菜'
const menuBlocks = (text, streaming = false) => chatMealAnswerBlocks(parseAiAnswer(text, { streaming }).blocks, { streaming })
const menuMeals = blocks => blocks.filter(block => block.type === 'meal-suggestions').flatMap(block => block.meals)

test('用户实际截图的餐次标题与分散项目列表生成卡片，不需要表格', () => {
  const blocks = menuBlocks(listIntro + '\n\n' + listBreakfast + '\n\n' + listLunch + '\n\n' + listDinner + '\n\n今天按作息规律进餐。')
  const meals = menuMeals(blocks)
  assert.deepEqual(meals.map(meal => meal.type), ['breakfast', 'lunch', 'dinner'])
  assert.deepEqual(meals[0].dishes, ['燕麦或全麦面包一份', '水煮蛋1个', '无糖牛奶或无糖豆浆一杯', '一个水果，如苹果或橙子'])
  assert.equal(chatFoodCover(meals[0].dishes[0]).src, '/static/bundles/oats.webp')
  assert.deepEqual(meals[1].notes, [{ label: '搭配思路', text: '主食配荤菜和蔬菜。' }])
  assert.equal(blocks[0].segments.map(segment => segment.text).join(''), listIntro)
  assert.equal(blocks.at(-1).segments.map(segment => segment.text).join(''), '今天按作息规律进餐。')
})

test('餐次行内段落、连续段落和编号列表使用同一套卡片', () => {
  for (const text of [
    '早餐：燕麦粥 + 鸡蛋\n午餐：杂粮米饭 + 青菜\n晚餐：米饭 + 豆腐',
    '1. **早餐**：燕麦粥 + 鸡蛋\n2. **午餐**：杂粮米饭 + 青菜\n3. **晚餐**：米饭 + 豆腐',
  ]) assert.deepEqual(menuMeals(menuBlocks(text)).map(meal => meal.dishes[0]), ['燕麦粥', '杂粮米饭', '米饭'])
  const text = '早餐：燕麦粥 + 鸡蛋\n\n午餐：杂粮米饭 + 青菜\n\n晚餐：米饭 + 豆腐'
  assert.equal(menuMeals(menuBlocks(text)).length, 3)
})

test('普通科普、无菜品的餐次标题以及段落后的提醒保持原始内容', () => {
  for (const text of ['早餐的重要性\n\n- 规律进餐有帮助。', '早餐\n\n请先补充信息。', '如何安排午餐\n\n- 不要自行停药。']) {
    const original = parseAiAnswer(text).blocks
    assert.deepEqual(chatMealAnswerBlocks(original), original)
  }
  const blocks = menuBlocks('早餐：燕麦粥\n\n> 牛奶过敏者不要选牛奶。')
  assert.equal(blocks.at(-1).type, 'quote')
  assert.match(blocks.at(-1).segments.map(segment => segment.text).join(''), /过敏/)
})

test('列表餐次在完整前不提前出现，后续餐次开始才显示上一餐', () => {
  for (let length = 1; length <= listBreakfast.length; length++) {
    assert.equal(menuMeals(menuBlocks(listBreakfast.slice(0, length), true)).length, 0, `partial list at ${length}`)
  }
  const blocks = menuBlocks(listBreakfast + '\n\n' + listLunch + '\n\n' + listDinner, true)
  assert.deepEqual(menuMeals(blocks).map(meal => meal.type), ['breakfast', 'lunch'])
  assert.equal(blocks.at(-1).pending, true)
  assert.equal(menuMeals(menuBlocks(listBreakfast)).length, 1)
})

test('Agent 最终回复由表格改成列表时已出现餐次也不重播', () => {
  const seen = [], live = renderer({ text: heading + breakfast + lunch + dinner, streaming: true }, seen)
  const final = renderer({ text: listIntro + '\n\n' + listBreakfast + '\n\n' + listLunch + '\n\n' + listDinner }, seen)
  assert.deepEqual(final.displayBlocks.value.filter(block => block.type === 'meal-suggestions').flatMap(block => block.meals).map(meal => meal.animate), [false, false, true])
  assert.deepEqual(final.events.map(([, event]) => event.key), ['dinner:0'])
  live.dispose(); final.dispose()
})
