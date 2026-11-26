import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {computed,ref,watch,reactive,effectScope,nextTick} from 'vue'
import {parseAiAnswer} from '../src/utils/ai-answer.js'
import {chatMealAnswerBlocks} from '../src/utils/chat-meal-suggestions.js'
import {quoteLayout} from '../src/utils/reply-selection.js'
const blocks=(text,streaming=false)=>chatMealAnswerBlocks(parseAiAnswer(text,{streaming}).blocks)
const text=value=>quoteLayout(value).text
const advice='如果两餐之间想吃水果，选低含糖量、低升糖指数的，并计入全天总量。'
const table='| 餐次 | 食物与份量 | 提醒 | 其他限制 |\n| --- | --- | --- | --- |\n| 早餐 | **燕麦粥**1碗＋鸡蛋1个 | 牛奶过敏者不要选牛奶 | 按医嘱调整 |\n| 午餐（12:00） | 米饭半碗＋豆腐 | 缺失营养保持未知 | 不加糖 |'

test('截图中的加餐建议完整保留为标题和普通文字，不按顿号拆成菜品',()=>{
 const result=blocks('**加餐**：'+advice)
 assert.deepEqual(result.map(b=>b.type),['heading','paragraph'])
 assert.equal(text(result),'加餐\n\n'+advice)
 assert.equal(result[1].segments.map(s=>s.text).join(''),advice)
 assert.ok(result[0].segments.every(s=>s.strong))
})

test('已有餐次标题和食物列表保留原内容、份量、格式与顺序',()=>{
 const input='## 早餐\n\n- **燕麦粥**（燕麦、水）1碗\n- 牛奶过敏者改用豆浆\n\n份量：按实际需要。'
 const original=parseAiAnswer(input).blocks
 assert.deepEqual(blocks(input),original)
 assert.match(text(blocks(input)),/燕麦粥（燕麦、水）1碗/)
})

test('连续餐次和编号餐次使用文字标题，样式不会丢失',()=>{
 for(const input of ['早餐：**燕麦粥**1碗\n午餐：豆腐\n晚餐：米饭','1. 早餐：**燕麦粥**1碗\n2. 午餐：豆腐\n3. 晚餐：米饭']){
  const result=blocks(input)
  assert.deepEqual(result.filter(b=>b.type==='heading').map(b=>b.segments.map(s=>s.text).join('')),['早餐','午餐','晚餐'])
  assert.ok(result.some(b=>b.segments?.some(s=>s.strong&&s.text==='燕麦粥')))
 }
})

test('餐次表格变成普通标题列表，每一列内容均保留且不使用图片',()=>{
 const result=blocks(table)
 assert.deepEqual(result.map(b=>b.type),['heading','list','heading','list'])
 for(const value of ['燕麦粥','1碗＋鸡蛋1个','提醒：牛奶过敏者不要选牛奶','其他限制：按医嘱调整','午餐（12:00）','缺失营养保持未知','不加糖'])assert.ok(text(result).includes(value),value)
 assert.ok(result[1].items[0].segments.some(s=>s.strong&&s.text==='燕麦粥'))
})

test('普通表格、未知餐次及多余单元格保留原始结构，绝不丢内容',()=>{
 for(const input of ['| 指标 | 食物 |\n| --- | --- |\n| 血糖 | 未知 |','| 餐次 | 食物 |\n| --- | --- |\n| 未知 | 请补充信息 |','| 餐次 | 食物 |\n| --- | --- |\n| 早餐 | 米饭 | 额外说明 |']){
  const original=parseAiAnswer(input).blocks;assert.deepEqual(chatMealAnswerBlocks(original),original)
 }
})

test('普通科普、过敏提醒和引用保留原文，不重写建议',()=>{
 for(const input of ['早餐的重要性\n\n规律进餐有帮助。','如何安排午餐\n\n- 不要自行停药。','> 牛奶过敏者不要选牛奶。','**提醒**：按医嘱调整。'])assert.deepEqual(blocks(input),parseAiAnswer(input).blocks)
})

test('流式逐字输出持续展示已收到的建议，最终回复与历史重读一致',()=>{
 const input='加餐：'+advice
 for(let end=1;end<=input.length;end++){
  const result=blocks(input.slice(0,end),true)
  assert.ok(result.every(b=>b.type!=='meal-suggestions'))
  if(end>3)assert.ok(text(result).includes(advice.slice(0,end-3)))
 }
 assert.deepEqual(blocks(input,true),blocks(input,false))
})

test('表格流式末行也显示已收到文字，完整份量与限制最终不丢失',()=>{
 const prefix='| 餐次 | 食物 | 提醒 |\n| --- | --- | --- |\n| 早餐 | 燕麦粥1碗 | 不加'
 assert.ok(text(blocks(prefix,true)).includes('不加'))
 const done=blocks(prefix+'糖 |',false)
 assert.match(text(done),/提醒：不加糖/)
})

test('全部餐次文字都能进入长按引用布局，选择内容与显示内容一致',()=>{
 const result=blocks('早餐：鸡蛋1个\n午餐：豆腐\n晚餐：米饭'),layout=quoteLayout(result,true)
 assert.ok(layout.text.includes('鸡蛋1个'));assert.ok(layout.text.includes('豆腐'));assert.ok(layout.text.includes('米饭'))
 assert.equal(layout.leaves.flatMap(l=>l.groups.flatMap(g=>g.glyphs)).map(g=>g.text).join(''),layout.text.replace(/\n\n/g,''))
})

test('真实回复组件在流式转最终及历史恢复时始终使用普通文字块',async()=>{
 const props=reactive({text:'加餐：'+advice,citations:[],streaming:true,selectionActive:false})
 const source=readFileSync(new URL('../src/components/AiAnswer.vue',import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
 const scope=effectScope(),deps={computed,ref,watch,nextTick,getCurrentInstance:()=>null,onUnmounted(){},parseAiAnswer,chatMealAnswerBlocks,quoteLayout,defineProps:()=>props,defineEmits:()=>()=>{}}
 try{
  const state=scope.run(()=>new Function('deps',`const {${Object.keys(deps)}}=deps;${source};return {displayBlocks,quoteContent}`)(deps))
  assert.equal(state.quoteContent.value.text,'加餐\n\n'+advice)
  props.streaming=false;await nextTick();assert.equal(state.quoteContent.value.text,'加餐\n\n'+advice)
  props.text=table;await nextTick();assert.deepEqual(state.displayBlocks.value.map(b=>b.type),['heading','list','heading','list'])
 }finally{scope.stop()}
})

test('回复渲染不再引用餐次图文组件，正式业务餐单仍保留',()=>{
 const answer=readFileSync(new URL('../src/components/AiAnswer.vue',import.meta.url),'utf8'),chat=readFileSync(new URL('../src/components/CloudNutritionChat.vue',import.meta.url),'utf8')
 assert.doesNotMatch(answer,/ChatMealSuggestionCard|answer-meal-cards|正在整理下一餐|mealShown/)
 assert.doesNotMatch(chat,/mealAppearances|rememberMealAppearance|animate-meals|shown-meals/)
 assert.match(chat,/<DailyMealPlanCard/);assert.match(chat,/<ChatMealRecordCard/);assert.match(chat,/<HealthChatBusinessCard/)
})
