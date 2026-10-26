import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {ref,computed,reactive,nextTick} from 'vue'

function setup({linked=true,available=true,entry=true,notice='',error=''}={}){
  const toasts=[],submits=[]
  const deps={ref,computed,reactive,nextTick,onShow(){},onHide(){},onMounted(){},onUnmounted(){},defineProps:()=>({route:{}}),
    storageContext:()=> 'account:family',getSession:()=>({token:'synthetic',householdId:'family'}),
    dailyArrangementState:()=>({phase:'error',error:'配餐数据未就绪',busy:false}),
    createDailyArrangementClient:()=>({reset(){},dispose(){}}),
    scopedStorage:{getStorageSync:()=>null,setStorageSync(){}},localDate:()=> '2026-10-26',
    HEALTH_TEXT_TASKS:{consultation:'咨询'},newHealthRequestId:()=> 'synthetic-request',request(){},
    uni:{showToast:o=>toasts.push(o),navigateTo(){}},
    createHealthTaskFlow:({onChange})=>({
      async open(id,type){onChange({memberId:id,taskType:type,available,notice,error})},
      async createEntry(){onChange({memberId:'health-self',taskType:'consultation',available,entry:entry?{thread_id:'thread'}:null,error:entry?'':'建立咨询失败，请重试'})},
      async submit(text){submits.push(text);return true},hide(){},
    })}
  const code=readFileSync(new URL('../src/components/CloudNutritionChat.vue',import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
  const page=new Function('deps',`const {${Object.keys(deps).join(',')}}=deps;${code};return {profile,question,task,chatError,sendQuestion,messages}`)(deps)
  page.profile.value={selfMemberId:'self',members:[{id:'self',relation:'爸爸',...(linked?{healthMemberId:'health-self'}:{})}]}
  if(linked)page.task.value={memberId:'health-self',taskType:'consultation',available,notice,error,entry:entry?{thread_id:'thread'}:null}
  return {...page,toasts,submits}
}
test('missing health link keeps the question and shows family archive guidance',async()=>{
 const p=setup({linked:false});p.question.value='你好';await p.sendQuestion()
 assert.equal(p.question.value,'你好');assert.equal(p.submits.length,0)
 assert.match(p.chatError.value,/家庭档案/);assert.equal(p.toasts[0].title,p.chatError.value)
})
test('readiness error is shown instead of silently discarding a send',async()=>{
 const p=setup({available:false,error:'咨询同意已撤回'});p.question.value='早餐怎么搭配';await p.sendQuestion()
 assert.equal(p.question.value,'早餐怎么搭配');assert.equal(p.submits.length,0)
 assert.equal(p.toasts[0].title,'咨询同意已撤回')
})
test('thread creation failure keeps the draft and shows its cause',async()=>{
 const p=setup({entry:false});p.question.value='你好';await p.sendQuestion()
 assert.equal(p.question.value,'你好');assert.equal(p.submits.length,0)
 assert.equal(p.toasts[0].title,'建立咨询失败，请重试')
})
test('available text consultation submits even when daily meals are unavailable',async()=>{
 const p=setup();p.question.value='你好';await p.sendQuestion()
 assert.deepEqual(p.submits,['你好']);assert.equal(p.question.value,'');assert.equal(p.toasts.length,0)
 assert.equal(p.messages.value[0].role,'user')
})


test('terminal processing errors do not offer to reread a finished response',()=>{
 const template=readFileSync(new URL('../src/components/CloudNutritionChat.vue',import.meta.url),'utf8')
 assert.doesNotMatch(template,/v-if="message.error"[^>]*@click="flow.refresh/)
 assert.match(template,/服务器已收到本条问题/)
 assert.match(template,/budget_price_unavailable/)
})
