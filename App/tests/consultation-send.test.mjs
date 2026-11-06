import {todayMealPlanState,createTodayMealPlan} from '../src/services/today-meal-plan.js'
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
import {isReferencePlan} from '../src/services/reference-meal-plan.js'

function setup({linked=true,available=true,entry=true,notice='',error='',prepared=true,initialized=true,initializationError='',tickOverride}={}){
  const toasts=[],submits=[],modals=[],submitCalls=[],refreshCalls=[],hooks={},identity={scope:'account:family'}
  const deps={todayMealPlanState,createTodayMealPlan:()=>({open:async()=>{},isGenerating:()=>false,pause(){},clear(){},dispose(){}}),defineOptions(){},selectChatPrompts:()=>[],loadCloudProfile:async()=>{throw new Error('咨询资料读取失败，请重试。')},isReferencePlan,chatPresentation,createChatEntryTransition,createChatKeyboardLayout,watch,ref,computed,reactive,nextTick:tickOverride||nextTick,mealQuestionAction,parseChatMealIntent,onShow:fn=>{hooks.show=fn},onHide:fn=>{hooks.hide=fn},onMounted(){},onUnmounted:fn=>{hooks.unmount=fn},defineProps:()=>({route:{}}),
    storageContext:()=>identity.scope,getSession:()=>({token:'synthetic',householdId:'family'}),
    dailyArrangementState:()=>({phase:prepared?'ready':'error',error:'配餐数据未就绪',busy:false}),
    createDailyArrangementClient:()=>({reset(){},dispose(){},pause(){}}),
    scopedStorage:{getStorageSync:()=>null,setStorageSync(){}},localDate:()=> '2026-10-26',
    HEALTH_TEXT_TASKS:{consultation:'咨询'},newHealthRequestId:()=> 'synthetic-request',request(){},
    uni:{showToast:o=>toasts.push(o),showModal:o=>modals.push(o),navigateTo(){},hideKeyboard(){}},
    createHealthTaskFlow:({onChange})=>({inject:onChange,
      async open(id,type){onChange({memberId:id,taskType:type,available,notice,error})},
      async createEntry(){onChange({memberId:'health-self',taskType:'consultation',available,entry:entry?{thread_id:'thread'}:null,error:entry?'':'建立咨询失败，请重试'})},
      async submit(text,retry=false){submits.push(text);submitCalls.push({text,retry,requestId:page.task.value.requestId});return true},hide(){},
      async refresh(...args){refreshCalls.push(args)},pause(){},
    })}
  const code=readFileSync(new URL('../src/components/CloudNutritionChat.vue',import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
  const page=new Function('deps',`const {${Object.keys(deps).join(',')}}=deps;${code};return {canCheckTask,checkTaskStatus,submitting,visibleMessages,hasMessageIssue,taskMessageIssue,messageStatus,canRetryMessage,needsProfileLink,recoveryNotice,conversationId,returnVerified,draftImage,flow,inputBusy,chatBusy,primaryMode,captureDraft,settleDraft,markDraftInput,removeDraft,reading,latestAvailable,detailOpen,historyOpen,scrollLatest,scrollTarget,stageSubmitted:s=>{submittedDraft=s},profile,question,task,chatError,sendQuestion,sendVoice,switchInputMode,voiceMode,voiceBusy,draftSaving,messages,entryReady,entryError}`)(deps)
  page.entryReady.value=initialized
  page.entryError.value=initializationError
  page.profile.value={selfMemberId:'self',members:[{id:'self',relation:'爸爸',...(linked?{healthMemberId:'health-self'}:{})}]}
  if(linked)page.task.value={memberId:'health-self',taskType:'consultation',available,notice,error,entry:entry?{thread_id:'thread'}:null}
  return {...page,toasts,submits,modals,submitCalls,refreshCalls,hooks,identity}
}

test('linked self members use account identity rather than their relationship label',()=>{
 const p=setup()
 for(const relation of ['本人','爸爸','妈妈','配偶']){
  p.profile.value.members[0].relation=relation
  assert.equal(p.needsProfileLink.value,false)
 }
 delete p.profile.value.members[0].healthMemberId
 p.profile.value.members.push({id:'other',relation:'本人',healthMemberId:'other-health'})
 assert.equal(p.needsProfileLink.value,true)
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
  assert.equal(p.recoveryNotice.value,'',JSON.stringify(state))
 }
 p.task.value={available:false}
 p.task.value={memberId:'health-self',available:false,notice:'请核对成员授权'}
 assert.equal(p.recoveryNotice.value,'请核对成员授权')
})

test('reply template keeps recovery out of the footer and exposes safe unknown-message confirmation',()=>{
 const template=readFileSync(new URL('../src/components/CloudNutritionChat.vue',import.meta.url),'utf8').split('<template>')[1]
 assert.doesNotMatch(template,/重新读取本次回复|重试原问题|task\.canRetry/)
 assert.doesNotMatch(template,/class="dialogue-status recovery-status"/)
 assert.doesNotMatch(template,/aria-label="咨询未完成"/)
 assert.doesNotMatch(template,/showMemberArchive|查看该成员档案/)
 assert.match(template,/@click="messageStatus\(message\)"/)
 assert.match(template,/primaryMode==='check'[^>]*@click="checkTaskStatus"/)
 assert.doesNotMatch(template,/status-only/)
})

function unknownMessage(p){
 p.task.value={...p.task.value,requestId:'original',status:'提交中',submitUnknown:true,canRetry:true,busy:false}
 return {role:'user',status:'unknown',requestId:'original'}
}

test('an uncertain submission stays blocked and offers no reason modal or duplicate question',async()=>{
 const p=setup();unknownMessage(p);p.question.value='另一个问题'
 assert.equal(p.primaryMode.value,'check');assert.equal(p.recoveryNotice.value,'')
 await p.sendQuestion();assert.equal(p.submitCalls.length,0);assert.equal(p.modals.length,0)
 assert.equal(p.question.value,'另一个问题')
})

test('terminal messages expose no recovery modal while internal cancellation failure remains available',()=>{
 const p=setup();p.task.value={...p.task.value,submitUnknown:false,status:'failed',error:'处理失败'}
 assert.equal(p.recoveryNotice.value,'');assert.equal(p.modals.length,0)
 p.task.value={...p.task.value,status:'running',cancelPhase:'error',cancelError:'停止未成功'}
 assert.equal(p.recoveryNotice.value,'停止未成功')
})

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
 assert.match(p.chatError.value,/连接尚未就绪/);assert.equal(p.toasts[0].title,p.chatError.value)
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

test('unfinished consultation keeps the draft and reports why sending failed',async()=>{
 const p=setup({initialized:false,initializationError:'咨询资料读取失败，请重试。'})
 try{
  p.question.value='你好';await p.sendQuestion()
  assert.deepEqual(p.submits,[]);assert.equal(p.question.value,'你好')
  assert.match(p.chatError.value,/问题已保留/)
  assert.equal(p.toasts.at(-1)?.title,p.chatError.value)
 }finally{p.hooks.unmount()}
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

for(const [name,state,mode,delivery,red] of [
 ['sending',{status:'提交中',busy:true,submitUnknown:true},'submitting','sending',false],
 ['retrying',{status:'提交中',busy:true,submitUnknown:true,canRetry:true},'submitting','sending',false],
 ['unconfirmed',{status:'提交中',busy:false,submitUnknown:true},'check','unknown',false],
 ['queued',{status:'queued'},'stop','sent',false],
 ['running',{status:'running'},'stop','sent',false],
 ['stopping',{status:'running',cancelPhase:'requesting',busy:true},'stopping','sent',false],
 ['confirming stop',{status:'cancel_requested',cancelPhase:'confirming'},'stopping','sent',false],
 ['unconfirmed stop',{status:'running',cancelPhase:'unknown'},'check','sent',false],
 ['stop rejected',{status:'running',cancelPhase:'error'},'stop','sent',false],
 ['stopped',{status:'cancelled'},'voice','cancelled',false],
 ['failed',{status:'failed'},'voice','failed',true],
 ['rejected',{status:'rejected'},'voice','rejected',true],
 ['interrupted',{status:'interrupted'},'voice','interrupted',true],
])test(`${name} shows the correct composer control and message severity`,()=>{
 const p=setup()
 p.messages.value.push({id:'user',role:'user',requestId:'original',status:'sending',text:'原问题'})
 p.flow.inject({...p.task.value,requestId:'original',submitUnknown:false,busy:false,...state})
 assert.equal(p.primaryMode.value,mode)
 assert.equal(p.visibleMessages.value[0].status,delivery)
 assert.equal(p.hasMessageIssue(p.visibleMessages.value[0]),red)
 if(state.submitUnknown)assert.equal(p.recoveryNotice.value,'')
})

test('a slow submit stays neutral and recovery clears all transient send warnings without clearing a new draft',async()=>{
 const p=setup();let release
 p.flow.submit=async()=>{
  p.flow.inject({...p.task.value,requestId:'original',status:'提交中',busy:true,submitUnknown:true,canRetry:true})
  await new Promise(resolve=>{release=resolve})
  p.flow.inject({...p.task.value,busy:false,error:'提交结果尚未确认'})
  return false
 }
 p.question.value='原问题'
 const pending=p.sendQuestion()
 while(!release)await new Promise(resolve=>setImmediate(resolve))
 assert.equal(p.primaryMode.value,'submitting');assert.equal(p.taskMessageIssue.value,false)
 assert.equal(p.visibleMessages.value[0].status,'sending');assert.equal(p.chatError.value,'')
 p.question.value='下一条草稿';release();await pending
 assert.equal(p.primaryMode.value,'check');assert.equal(p.taskMessageIssue.value,true)
 assert.equal(p.chatError.value,'');assert.equal(p.toasts.length,0)
 p.flow.inject({...p.task.value,status:'completed',submitUnknown:false,canRetry:false,error:'',result:{type:'answer',text:'已恢复回复',citations:[]}})
 assert.equal(p.chatError.value,'');assert.equal(p.recoveryNotice.value,'');assert.equal(p.taskMessageIssue.value,false)
 assert.equal(p.messages.value.filter(m=>m.role==='user').length,1)
 assert.equal(p.messages.value.at(-1).text,'已恢复回复');assert.equal(p.question.value,'下一条草稿')
})

test('checking an uncertain submission only refreshes its original task and ignores repeated clicks',async()=>{
 const p=setup();unknownMessage(p);p.question.value='下一条草稿';let release
 p.flow.refresh=async(...args)=>{
  p.refreshCalls.push(args);p.flow.inject({...p.task.value,refreshing:true})
  await new Promise(resolve=>{release=resolve})
  p.flow.inject({...p.task.value,refreshing:false,submitUnknown:false,status:'running'})
 }
 assert.equal(p.canCheckTask.value,true)
 const pending=p.checkTaskStatus({type:'click'})
 await p.checkTaskStatus()
 assert.deepEqual(p.refreshCalls,[[]]);assert.equal(p.canCheckTask.value,false)
 assert.equal(p.task.value.requestId,'original');assert.equal(p.submitCalls.length,0)
 release();await pending
 assert.equal(p.primaryMode.value,'stop');assert.equal(p.question.value,'下一条草稿')
})

test('checking a lost stop response only reads the task before making stop reachable again',async()=>{
 const p=setup();p.task.value={...p.task.value,requestId:'original',status:'running',cancelPhase:'unknown'}
 assert.equal(p.canCheckTask.value,true);await p.checkTaskStatus()
 assert.deepEqual(p.refreshCalls,[[]]);assert.equal(p.submitCalls.length,0)
 p.flow.inject({...p.task.value,cancelPhase:'error',cancelError:'任务仍在处理'})
 assert.equal(p.primaryMode.value,'stop');assert.equal(p.canCheckTask.value,false)
})

for(const change of ['busy','loading','refreshing','unverified','invalidated','hidden','account','missing-request','confirmed'])test(`manual task checking is blocked after ${change}`,async()=>{
 const p=setup();unknownMessage(p)
 if(['busy','loading','refreshing'].includes(change))p.task.value[change]=true
 if(change==='unverified')p.returnVerified.value=false
 if(change==='invalidated')p.task.value.invalidated=true
 if(change==='hidden')p.hooks.hide()
 if(change==='account')p.identity.scope='another-account:family'
 if(change==='missing-request')p.task.value.requestId=''
 if(change==='confirmed')p.task.value.submitUnknown=false
 await p.checkTaskStatus();assert.equal(p.refreshCalls.length,0);assert.equal(p.submitCalls.length,0)
})

test('a failed message explains its status without retrying a finished request',()=>{
 const p=setup();p.messageStatus({role:'user',status:'failed',requestId:'old'})
 assert.match(p.modals[0].content,/处理失败/);assert.equal(p.modals[0].showCancel,false)
 p.modals[0].success({confirm:true});assert.equal(p.submitCalls.length,0)
})

test('definite send failure keeps earlier chat and marks only the original question with a red issue',async()=>{
 const p=setup();p.messages.value.push({id:'old',role:'assistant',text:'上一轮答复'})
 p.question.value='这次的问题'
 p.flow.submit=async()=>{
  p.flow.inject({...p.task.value,requestId:'current',status:'提交中',submitUnknown:true,busy:true})
  p.flow.inject({...p.task.value,status:'failed',submitUnknown:false,busy:false,result:{type:'error',code:'request_rejected'}})
  return false
 }
 await p.sendQuestion()
 assert.equal(p.messages.value[0].text,'上一轮答复')
 const message=p.visibleMessages.value.find(m=>m.role==='user')
 assert.equal(message.text,'这次的问题');assert.equal(message.status,'failed');assert.equal(p.hasMessageIssue(message),true)
 assert.equal(p.messages.value.length,2);assert.notEqual(p.task.value.invalidated,true)
})

test('unavailable task keeps chat, blocks duplicate sends, and offers read-only recovery from its red marker',async()=>{
 const p=setup();p.messages.value.push({id:'old',role:'assistant',text:'上一轮答复'},{id:'current',role:'user',requestId:'current',text:'原问题',status:'sent'})
 p.flow.inject({...p.task.value,requestId:'current',status:'recovering',readUnavailable:true})
 const message=p.visibleMessages.value[1]
 assert.equal(message.status,'unavailable');assert.equal(p.hasMessageIssue(message),true)
 assert.equal(p.primaryMode.value,'check');assert.equal(p.chatBusy.value,true)
 p.messageStatus(message);assert.equal(p.modals[0].confirmText,'重新读取')
 p.modals[0].success({confirm:true});assert.equal(p.refreshCalls.length,1);assert.equal(p.submitCalls.length,0)
 p.flow.inject({...p.task.value,status:'completed',readUnavailable:false,result:{type:'answer',text:'自动恢复的答复',citations:[]}})
 assert.equal(p.visibleMessages.value[1].status,'sent');assert.equal(p.messages.value[0].text,'上一轮答复')
 assert.equal(p.messages.value.at(-1).text,'自动恢复的答复');assert.equal(p.chatBusy.value,false)
})
