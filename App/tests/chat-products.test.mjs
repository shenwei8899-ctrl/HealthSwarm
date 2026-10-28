import test from 'node:test'
import {parseChatMealIntent} from '../src/utils/chat-meal-intent.js'
import {referenceSelection} from '../src/services/reference-meal-plan.js'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {ref,computed,reactive,nextTick} from 'vue'

function setup(route={}){
 const submitted=[],opened=[],selections=[]
 const stored=new Map(),thread='22222222-2222-4222-8222-222222222222',referenceThread='33333333-3333-4333-8333-333333333333'
 const deps={parseChatMealIntent,ref,computed,reactive,nextTick,onShow(){},onHide(){},onMounted(){},onUnmounted(){},defineProps:()=>({route}),
 storageContext:()=> 'scope',getSession:()=>({token:'unit'}),
 dailyArrangementState:()=>({phase:'ready'}),createDailyArrangementClient:()=>({dispose(){}}),
 scopedStorage:{getStorageSync:key=>stored.get(key),setStorageSync:(key,value)=>stored.set(key,value)},localDate:date=>date?'2026-10-28':'2026-10-27',
 HEALTH_TEXT_TASKS:{consultation:'咨询',reference_meal_preview:'参考餐单',blood_pressure_review:'血压'},newHealthRequestId:()=> 'request',request(){},
 uni:{showToast(){},navigateTo(){}},chooseReference:referenceSelection,
 readChatSnapshot:async()=>({messages:[],runs:[]}),
 createHealthTaskFlow:({onChange})=>({async open(memberId,taskType,selection){opened.push(taskType);selections.push(selection);onChange({memberId,taskType,available:true,entry:{thread_id:taskType==='consultation'?thread:referenceThread,agent_slug:taskType==='consultation'?'health-consultation':'health-meal-planner'}})},
 async submit(text){submitted.push(text);return true},async createEntry(){},hide(){}})}
 const source=readFileSync(new URL('../src/components/CloudNutritionChat.vue',import.meta.url),'utf8')
 const code=source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
 const page=new Function('deps',`const {${Object.keys(deps).join(',')}}=deps;${code};return {profile,question,task,entryReady,chatError,sendQuestion,rememberThread}`)(deps)
 page.entryReady.value=true
 page.profile.value={selfMemberId:'self',householdId:'family',members:[{id:'self',healthMemberId:'health-self',relation:'本人'}]}
 page.task.value={memberId:'health-self',taskType:'consultation',available:true,entry:{thread_id:thread,agent_slug:'health-consultation'}}
 page.rememberThread()
 return {...page,submitted,opened,selections}
}

for(const text of ['为我配菜','今晚吃什么','今天吃什么','晚餐推荐','推荐几道菜'])test(`普通聊天使用咨询商品流程：${text}`,async()=>{
 const p=setup();p.question.value=text;await p.sendQuestion()
 assert.deepEqual(p.submitted,[text]);assert.equal(p.task.value.taskType,'consultation')
})

test('普通安排请求保留原问题，继续当前咨询而不自动生成参考餐单',async()=>{
 const p=setup();p.question.value='给我安排明天早餐';await p.sendQuestion()
 assert.deepEqual(p.opened,[]);assert.deepEqual(p.submitted,['给我安排明天早餐'])
 assert.equal(p.task.value.taskType,'consultation');assert.deepEqual(p.selections,[])
})
test('显式生成明天早餐保留本人单餐选择、问题及日期',async()=>{
 const p=setup();p.question.value='给我安排明天早餐';await p.sendQuestion('reference_meal_preview')
 assert.deepEqual(p.opened,['reference_meal_preview']);assert.deepEqual(p.submitted,['给我安排明天早餐'])
 assert.equal(p.task.value.taskType,'reference_meal_preview')
 assert.deepEqual(p.selections,[{mode:'reference',family_id:'family',plan_date:'2026-10-28',participant_ids:['self'],meal_types:['breakfast']}])
})
test('显式参考餐单按钮仍进入参考餐单而非普通商品咨询',async()=>{
 const p=setup();p.question.value='请帮我安排今天的三餐';await p.sendQuestion('reference_meal_preview')
 assert.deepEqual(p.opened,['reference_meal_preview']);assert.equal(p.submitted.length,1)
})
test('显式指标任务入口保持原类型',async()=>{
 const p=setup({taskType:'blood_pressure_review'});p.question.value='查看记录';await p.sendQuestion()
 assert.deepEqual(p.opened,['blood_pressure_review'])
})

for(const text of ['为我配餐，必须为我进行配餐今天怎么吃','一个人，直接为我进行这顿配餐','生成今天的三餐食谱'])test(`配餐措辞仍留在连续咨询，正式生成由显式操作触发：${text}`,async()=>{
 const p=setup();p.question.value=text;await p.sendQuestion()
 assert.deepEqual(p.opened,[]);assert.deepEqual(p.submitted,[text]);assert.equal(p.task.value.taskType,'consultation');assert.deepEqual(p.selections,[])
})
test('多天安排作为普通咨询完整提交，不创建错误日期的正式餐单',async()=>{
 const p=setup();p.question.value='为我配餐，安排未来三天';await p.sendQuestion()
 assert.deepEqual(p.opened,[]);assert.deepEqual(p.submitted,['为我配餐，安排未来三天']);assert.equal(p.task.value.taskType,'consultation');assert.deepEqual(p.selections,[])
})
test('显式生成仍拒绝未支持的多天日期，并保留原问题',async()=>{
 const p=setup();p.question.value='为我配餐，安排未来三天';await p.sendQuestion('reference_meal_preview')
 assert.deepEqual(p.opened,[]);assert.deepEqual(p.submitted,[]);assert.equal(p.question.value,'为我配餐，安排未来三天');assert.match(p.chatError.value,/今天或明天/)
})
