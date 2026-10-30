import {chatPresentation} from '../src/services/chat-presentation.js'
import {watch} from 'vue'
import {createChatEntryTransition} from '../src/services/chat-entry-transition.js'
import {createChatKeyboardLayout} from '../src/services/chat-keyboard-layout.js'
import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {ref,computed,reactive,nextTick} from 'vue'
import {mealQuestionAction} from '../src/services/daily-meal-plan.js'

import {parseChatMealIntent} from '../src/utils/chat-meal-intent.js'

function setup({linked=true,available=true,entry=true,notice='',error='',prepared=true,initialized=true,initializationError='',tickOverride}={}){
  const toasts=[],submits=[],modals=[],submitCalls=[]
  const deps={chatPresentation,createChatEntryTransition,createChatKeyboardLayout,watch,ref,computed,reactive,nextTick:tickOverride||nextTick,mealQuestionAction,parseChatMealIntent,onShow(){},onHide(){},onMounted(){},onUnmounted(){},defineProps:()=>({route:{}}),
    storageContext:()=> 'account:family',getSession:()=>({token:'synthetic',householdId:'family'}),
    dailyArrangementState:()=>({phase:prepared?'ready':'error',error:'配餐数据未就绪',busy:false}),
    createDailyArrangementClient:()=>({reset(){},dispose(){}}),
    scopedStorage:{getStorageSync:()=>null,setStorageSync(){}},localDate:()=> '2026-10-26',
    HEALTH_TEXT_TASKS:{consultation:'咨询'},newHealthRequestId:()=> 'synthetic-request',request(){},
    uni:{showToast:o=>toasts.push(o),showModal:o=>modals.push(o),navigateTo(){},hideKeyboard(){}},
    createHealthTaskFlow:({onChange})=>({inject:onChange,
      async open(id,type){onChange({memberId:id,taskType:type,available,notice,error})},
      async createEntry(){onChange({memberId:'health-self',taskType:'consultation',available,entry:entry?{thread_id:'thread'}:null,error:entry?'':'建立咨询失败，请重试'})},
      async submit(text,retry=false){submits.push(text);submitCalls.push({text,retry,requestId:page.task.value.requestId});return true},hide(){},
    })}
  const code=readFileSync(new URL('../src/components/CloudNutritionChat.vue',import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
  const page=new Function('deps',`const {${Object.keys(deps).join(',')}}=deps;${code};return {showMemberArchive,needsProfileLink,recoveryNotice,messageStatus,conversationId,returnVerified,draftImage,flow,inputBusy,chatBusy,primaryMode,captureDraft,settleDraft,markDraftInput,removeDraft,reading,latestAvailable,detailOpen,historyOpen,scrollLatest,scrollTarget,stageSubmitted:s=>{submittedDraft=s},profile,question,task,chatError,sendQuestion,sendVoice,switchInputMode,voiceMode,voiceBusy,draftSaving,messages,entryReady,entryError}`)(deps)
  page.entryReady.value=initialized
  page.entryError.value=initializationError
  page.profile.value={selfMemberId:'self',members:[{id:'self',relation:'爸爸',...(linked?{healthMemberId:'health-self'}:{})}]}
  if(linked)page.task.value={memberId:'health-self',taskType:'consultation',available,notice,error,entry:entry?{thread_id:'thread'}:null}
  return {...page,toasts,submits,modals,submitCalls}
}

test('linked self members use account identity rather than their relationship label',()=>{
 const p=setup()
 for(const relation of ['本人','爸爸','妈妈','配偶']){
  p.profile.value.members[0].relation=relation
  assert.equal(p.needsProfileLink.value,false)
  assert.equal(p.showMemberArchive.value,false)
 }
 delete p.profile.value.members[0].healthMemberId
 p.profile.value.members.push({id:'other',relation:'本人',healthMemberId:'other-health'})
 assert.equal(p.needsProfileLink.value,true);assert.equal(p.showMemberArchive.value,true)
})

test('submitting, queueing, generating and reconnecting show no archive or footer recovery area',()=>{
 const p=setup({available:false})
 for(const state of [
  {busy:true,status:'提交中',canRetry:true,submitUnknown:true},
  ...['queued','dispatched','pending','running','cancel_requested'].map(status=>({status})),
  {loading:true},{status:'running',error:'正在自动重试',streamPhase:'reconnecting'},
  {status:'running',notice:'回复用时较长，仍在自动获取结果'},
  {streamText:'增量预览'},
 ]){
  p.task.value={...state,available:false,requestId:'current'}
  assert.equal(p.showMemberArchive.value,false,JSON.stringify(state))
  assert.equal(p.recoveryNotice.value,'',JSON.stringify(state))
 }
 p.task.value={available:false,notice:'请核对成员授权'}
 assert.equal(p.showMemberArchive.value,true);assert.equal(p.recoveryNotice.value,'请核对成员授权')
})

test('reply template removes manual reread and retry buttons while preserving the composer check action',()=>{
 const template=readFileSync(new URL('../src/components/CloudNutritionChat.vue',import.meta.url),'utf8').split('<template>')[1]
 assert.doesNotMatch(template,/重新读取本次回复|重试原问题|task\.canRetry/)
 assert.match(template,/v-if="recoveryNotice" class="dialogue-status recovery-status"/)
 assert.match(template,/v-if="showMemberArchive"/)
 assert.match(template,/primaryMode==='check'[\s\S]*?@click="flow.refresh\(\)"/)
})

function unknownMessage(p){
 p.task.value={...p.task.value,requestId:'original',status:'提交中',submitUnknown:true,canRetry:true,busy:false}
 return {role:'user',status:'unknown',requestId:'original'}
}

test('unknown submission recovery uses the message modal and retries the original request only on confirmation',async()=>{
 const p=setup(),message=unknownMessage(p)
 assert.equal(p.primaryMode.value,'check');assert.equal(p.recoveryNotice.value,'')
 p.messageStatus(message)
 assert.equal(p.modals[0].confirmText,'重试原问题');assert.equal(p.modals[0].showCancel,true)
 p.modals[0].success({confirm:false});assert.equal(p.submitCalls.length,0)
 p.modals[0].success({confirm:true});await nextTick()
 assert.deepEqual(p.submitCalls,[{text:'',retry:true,requestId:'original'}])
})

for(const change of ['request','conversation','confirmed','busy','unverified'])test(`message retry ignores stale confirmation after ${change} changes`,()=>{
 const p=setup(),message=unknownMessage(p);p.messageStatus(message)
 if(change==='request')p.task.value.requestId='new'
 if(change==='conversation')p.conversationId.value='new'
 if(change==='confirmed')p.task.value.submitUnknown=false
 if(change==='busy')p.task.value.busy=true
 if(change==='unverified')p.returnVerified.value=false
 p.modals[0].success({confirm:true});assert.equal(p.submitCalls.length,0)
})

test('ordinary failures and another request cannot offer an unknown-submit retry',()=>{
 const p=setup();unknownMessage(p)
 for(const message of [{role:'user',status:'unknown',requestId:'other'},{role:'user',status:'failed',requestId:'original'}]){
  p.messageStatus(message);assert.equal(p.modals.at(-1).showCancel,false)
  p.modals.at(-1).success({confirm:true})
 }
 assert.equal(p.submitCalls.length,0)
 p.task.value={...p.task.value,submitUnknown:false,status:'failed',error:'处理失败'}
 assert.equal(p.recoveryNotice.value,'')
 p.task.value={...p.task.value,status:'running',cancelPhase:'error',cancelError:'停止未成功'}
 assert.equal(p.recoveryNotice.value,'停止未成功')
})
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
test('available text consultation submits after consultation initialization',async()=>{
 const p=setup();p.question.value='你好';await p.sendQuestion()
 assert.deepEqual(p.submits,['你好']);assert.equal(p.question.value,'');assert.equal(p.toasts.length,0)
 assert.equal(p.messages.value[0].role,'user')
})

test('switching input mode keeps a draft and never submits while switching or busy',()=>{
 const p=setup();p.question.value='晚饭想清淡一点'
 assert.equal(p.voiceMode.value,false)
 p.switchInputMode();assert.equal(p.voiceMode.value,true)
 assert.equal(p.question.value,'晚饭想清淡一点');assert.deepEqual(p.submits,[])
 p.voiceBusy.value=true;p.switchInputMode();assert.equal(p.voiceMode.value,true)
 p.voiceBusy.value=false;p.switchInputMode();assert.equal(p.voiceMode.value,false)
 p.draftSaving.value=true;p.switchInputMode();assert.equal(p.voiceMode.value,false)
 assert.equal(p.question.value,'晚饭想清淡一点');assert.deepEqual(p.submits,[])
})

test('recognized speech supplements a typed draft instead of replacing it',async()=>{
 const p=setup();p.question.value='我想咨询饮食习惯'
 await p.sendVoice('最近吃饭时间不规律')
 assert.deepEqual(p.submits,['我想咨询饮食习惯\n最近吃饭时间不规律'])
 assert.equal(p.question.value,'')
})


test('terminal processing errors do not offer to reread a finished response',()=>{
 const template=readFileSync(new URL('../src/components/CloudNutritionChat.vue',import.meta.url),'utf8')
 assert.doesNotMatch(template,/v-if="message.error"[^>]*@click="flow.refresh/)
 assert.match(template,/message-issue/)
 assert.match(template,/budget_price_unavailable/)
})

test('unfinished consultation initialization keeps the question and shows its actual error',async()=>{
 const p=setup({initialized:false,initializationError:'咨询资料读取失败，请重试。'});p.question.value='你好';await p.sendQuestion()
 assert.deepEqual(p.submits,[]);assert.equal(p.question.value,'你好');assert.equal(p.chatError.value,'咨询资料读取失败，请重试。')
})
test('missing daily preparation does not block initialized ordinary consultation',async()=>{
 const p=setup({prepared:false});p.question.value='你好';await p.sendQuestion()
 assert.deepEqual(p.submits,['你好']);assert.equal(p.question.value,'');assert.equal(p.chatError.value,'')
})


test('a running task permits editing a draft but Enter cannot submit it',async()=>{
 const p=setup();p.task.value={...p.task.value,requestId:'old',status:'running'};p.question.value='下一条草稿'
 assert.equal(p.inputBusy.value,false);assert.equal(p.primaryMode.value,'stop');await p.sendQuestion();assert.equal(p.submits.length,0);assert.equal(p.question.value,'下一条草稿')
 p.task.value={...p.task.value,status:'cancel_requested'};assert.equal(p.primaryMode.value,'stopping');assert.equal(p.inputBusy.value,false)
})
test('an old receipt cannot clear a new draft even when its final text is identical',()=>{
 const p=setup();p.question.value='相同文字';const snapshot=p.captureDraft();snapshot.requestId='old';p.stageSubmitted(snapshot)
 p.messages.value.push({id:'u',role:'user',requestId:'old',text:'相同文字'});p.question.value='修改中';p.question.value='相同文字'
 p.flow.inject({...p.task.value,status:'completed',requestId:'old'});assert.equal(p.question.value,'相同文字')
})
test('text and image receipts settle independently and never remove a replacement image',()=>{
 const p=setup();p.question.value='原文';p.draftImage.value={localPath:'old'};const snapshot=p.captureDraft();p.question.value='新文字'
 p.settleDraft(snapshot);assert.equal(p.question.value,'新文字');assert.equal(p.draftImage.value,null)
 p.draftImage.value={localPath:'same'};const newer=p.captureDraft();p.removeDraft();p.draftImage.value={localPath:'same'};p.settleDraft(newer)
 assert.equal(p.draftImage.value.localPath,'same')
})
test('opening an overlay between render waits invalidates the pending scroll command',async()=>{
 const jobs=[],p=setup({tickOverride:()=>new Promise(r=>jobs.push(r))});p.messages.value.push({id:'m',role:'user',text:'消息'})
 const pending=p.scrollLatest();p.detailOpen.value=true;jobs.shift()();await pending;assert.equal(p.scrollTarget.value,'')
})
test('manual reading and history pause automatic follow until the explicit latest action',async()=>{
 const p=setup();p.messages.value.push({id:'m',role:'user',text:'消息'});p.reading.value={following:false};await p.scrollLatest()
 assert.equal(p.scrollTarget.value,'');assert.equal(p.latestAvailable.value,true)
 p.historyOpen.value=true;await p.scrollLatest({force:true});assert.equal(p.scrollTarget.value,'')
 p.historyOpen.value=false;await p.scrollLatest({force:true});assert.equal(p.scrollTarget.value,'chat-bottom-anchor');assert.equal(p.latestAvailable.value,false)
})
