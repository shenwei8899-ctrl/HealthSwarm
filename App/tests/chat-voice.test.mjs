import test from 'node:test'
import assert from 'node:assert/strict'
import { authorizeVoice, createVoiceCapture, pcmVoiceLevel, VOICE_OPTIONS, transcribeVoice } from '../src/services/chat-voice.js'
import { registerApiAdapters } from '../src/services/index.js'
import { readFileSync } from 'node:fs'
import { computed, ref, reactive, watch, effectScope, proxyRefs, toRefs, compile } from 'vue'

const tick = () => new Promise(resolve => setImmediate(resolve))
test('first microphone request invokes native scope.record authorization', async () => {
  let requested
  globalThis.uni = { getSetting: options => options.success({authSetting:{}}), authorize: options => {requested=options.scope;options.success({})} }
  await authorizeVoice();assert.equal(requested,'scope.record')
})
test('allowed microphone skips authorization; denied permission routes to settings', async () => {
  for (const permission of [true,false]) {
    let calls=0
    globalThis.uni={getSetting:options=>options.success({authSetting:{'scope.record':permission}}),authorize:()=>{calls++}}
    if(permission)await authorizeVoice();else await assert.rejects(authorizeVoice(),{code:'RECORD_PERMISSION_DENIED'})
    assert.equal(calls,0)
  }
})
test('native refusal is confirmed by settings after the dialog', async () => {
  let reads=0
  globalThis.uni={getSetting:options=>options.success({authSetting:++reads===1?{}:{'scope.record':false}}),authorize:options=>options.fail({errMsg:'authorize:fail auth deny'})}
  await assert.rejects(authorizeVoice(),{code:'RECORD_PERMISSION_DENIED'});assert.equal(reads,2)
})
test('runtime authorization failures retain their cause without claiming refusal', async () => {
  globalThis.uni={getSetting:options=>options.success({authSetting:{}}),authorize:options=>options.fail({errMsg:'authorize:fail privacy configuration'})}
  await assert.rejects(authorizeVoice(),error=>error.code==='RECORD_AUTH_FAILED'&&error.message.includes('privacy configuration'))
})
test('settings read failure never attempts authorization', async () => {
  let calls=0
  globalThis.uni={getSetting:options=>options.fail({errMsg:'getSetting:fail unavailable'}),authorize:()=>{calls++}}
  await assert.rejects(authorizeVoice(),error=>error.code==='RECORD_AUTH_FAILED'&&error.message.includes('getSetting:fail unavailable'))
  assert.equal(calls,0)
})
test('failed state confirmation preserves original authorize error', async () => {
  let reads=0
  globalThis.uni={getSetting:options=>++reads===1?options.success({authSetting:{}}):options.fail({errMsg:'read failed'}),authorize:options=>options.fail({errMsg:'original failure'})}
  await assert.rejects(authorizeVoice(),error=>error.code==='RECORD_AUTH_FAILED'&&error.message.includes('original failure'))
})
function deferred() { let resolve; const promise = new Promise(r => { resolve = r }); return { promise, resolve } }
function fixture(extra = {}, manager) {
  const events = {}, states = [], texts = [], levels = [], calls = { stop: 0, save: 0, transcribe: 0 }
  const native = manager || { start(options) { calls.options = options }, stop() { calls.stop++ } }
  if (!manager) for (const name of ['Start','Stop','Error','FrameRecorded','InterruptionBegin','Pause']) native['on'+name] = fn => { events[name] = fn }
  let scope = 'account-a'
  const capture = createVoiceCapture({ getRecorder: () => native, authorize: async () => {},
    save: async audio => { calls.save++; return { ...audio, filePath: '/saved.pcm' } },
    transcribe: async () => { calls.transcribe++; return '今天吃什么' }, getScope: () => scope,
    onState: state => states.push(state), onText: text => texts.push(text), onLevel: level => levels.push(level), ...extra })
  return { capture, events, states, texts, levels, calls, native, setScope(value) { scope = value }, state: () => states.at(-1) }
}
async function recording(f) { await f.capture.begin(200); f.events.Start() }
function finish(f, duration = 1000) { f.capture.end(200); f.events.Stop({ duration, tempFilePath: '/temp.pcm' }) }

test('PCM meter measures signed samples, silence and odd byte frames', () => {
  assert.equal(pcmVoiceLevel(new ArrayBuffer(8)), 0)
  assert.equal(pcmVoiceLevel(new ArrayBuffer(1)), 0)
  const positive = new Int16Array([10000,10000]).buffer, negative = new Int16Array([-10000,-10000]).buffer
  assert.equal(pcmVoiceLevel(positive), pcmVoiceLevel(negative))
  assert.ok(pcmVoiceLevel(positive) > pcmVoiceLevel(new Int16Array([100,100]).buffer))
  assert.ok(Number.isFinite(pcmVoiceLevel(new ArrayBuffer(3))))
})
test('normal release saves PCM and sends recognized text exactly once', async () => {
  const f = fixture(); await recording(f)
  assert.deepEqual(f.calls.options, VOICE_OPTIONS); assert.equal(VOICE_OPTIONS.format, 'PCM')
  assert.equal(VOICE_OPTIONS.sampleRate, 16000); assert.equal(VOICE_OPTIONS.numberOfChannels, 1)
  f.events.FrameRecorded({ frameBuffer: new Int16Array([20000]).buffer }); assert.ok(f.levels[0] > 0)
  finish(f); await tick(); f.events.Stop({ duration: 1000, tempFilePath: '/temp.pcm' })
  assert.deepEqual(f.texts, ['今天吃什么']); assert.equal(f.calls.save, 1); assert.equal(f.state().phase, 'idle')
})
test('upward release discards, moving back down restores sending', async () => {
  const f = fixture(); await recording(f); f.capture.move(100); f.capture.end(100)
  f.events.Stop({ duration:1000,tempFilePath:'/temp.pcm' }); await tick()
  assert.equal(f.calls.save,0); assert.equal(f.state().phase,'idle')
  await recording(f); f.capture.move(100); f.capture.move(190); finish(f); await tick()
  assert.equal(f.texts.length,1)
})
test('short recordings never transcribe', async () => {
  const f = fixture(); await recording(f); finish(f,200); await tick()
  assert.equal(f.calls.transcribe,0); assert.equal(f.state().phase,'error')
})
test('permission denial reports settings state', async () => {
  const f=fixture({authorize:async()=>{throw Object.assign(new Error('denied'),{code:'RECORD_PERMISSION_DENIED'})}})
  await f.capture.begin(); assert.equal(f.state().permissionDenied,true); assert.equal(f.calls.options,undefined)
})
test('release during authorization never starts recorder', async () => {
  const pending=deferred(),f=fixture({authorize:()=>pending.promise})
  const begin=f.capture.begin(); f.capture.end(); pending.resolve(); await begin
  assert.equal(f.calls.options,undefined); assert.equal(f.state().phase,'idle')
})
test('late native start after release or disposal stops immediately', async () => {
  for (const dispose of [false,true]) {
    const f=fixture(); await f.capture.begin(); dispose ? f.capture.dispose() : f.capture.end()
    f.events.Start(); assert.equal(f.calls.stop,1); f.events.Stop({duration:100,tempFilePath:'/temp.pcm'}); await tick()
    assert.equal(f.texts.length,0)
  }
})
test('cancel followed by native error recovers for another recording', async () => {
  const f=fixture(); await recording(f); f.capture.cancel(); f.events.Error()
  assert.equal(f.state().phase,'idle'); await recording(f); finish(f); await tick(); assert.equal(f.texts.length,1)
})
test('canceling an idle controller does not leave a pending stop', async () => {
  const f=fixture();f.capture.cancel();assert.equal(f.state().phase,'idle')
  await recording(f);finish(f);await tick();assert.equal(f.texts.length,1)
})
test('failed transcription retains saved audio and retry reuses request', async () => {
  const requests=[]; const f=fixture({transcribe:async audio=>{requests.push({...audio}); if(requests.length===1)throw new Error('offline'); return '重试成功'}})
  await recording(f); finish(f); await tick(); assert.equal(f.state().hasAudio,true)
  await f.capture.retry(); assert.equal(f.calls.save,1); assert.equal(requests[0].id,requests[1].id)
  assert.deepEqual(f.texts,['重试成功']); assert.equal(f.state().hasAudio,false)
})
test('save failure can retry from temporary audio', async () => {
  let saves=0; const f=fixture({save:async audio=>{if(++saves===1)throw new Error('storage');return {...audio,filePath:'/saved.pcm'}}})
  await recording(f); finish(f); await tick(); assert.equal(f.state().hasAudio,true)
  await f.capture.retry(); assert.equal(saves,2); assert.equal(f.texts.length,1)
})
test('cancel, disposal and account switch invalidate in-flight transcription', async () => {
  for(const action of ['cancel','dispose','scope']) {
    const pending=deferred(),f=fixture({transcribe:()=>pending.promise}); await recording(f); finish(f); await tick()
    if(action==='scope')f.setScope('account-b');else f.capture[action]()
    pending.resolve('stale'); await tick(); assert.equal(f.texts.length,0)
  }
})
test('interruption discards audio; duration-limit stop transcribes automatically', async () => {
  const f=fixture(); await recording(f); f.events.InterruptionBegin(); f.events.Stop({duration:1000,tempFilePath:'/temp.pcm'})
  await tick(); assert.equal(f.texts.length,0)
  await recording(f); f.events.Stop({duration:60000,tempFilePath:'/max.pcm'}); await tick(); assert.equal(f.texts.length,1)
})
test('singleton recorder refuses another owner without stealing callbacks', async () => {
  const f=fixture(); await recording(f); const other=fixture({},f.native); await other.capture.begin()
  assert.equal(other.state().phase,'error'); finish(f); await tick(); assert.equal(f.texts.length,1); assert.equal(other.texts.length,0)
})
test('transcription adapter explicitly rejects missing service and blank content', async () => {
  registerApiAdapters({transcribeVoice:undefined})
  await assert.rejects(transcribeVoice({}), {code:'VOICE_NOT_READY'})
  let received; registerApiAdapters({transcribeVoice:async data=>{received=data;return {text:'  已识别  '}}})
  assert.equal(await transcribeVoice({filePath:'/saved.pcm',duration:1000,id:'request-1'}),'已识别')
  assert.equal(received.clientRequestId,'request-1'); assert.equal(received.format,'PCM')
  registerApiAdapters({transcribeVoice:async()=>({text:' '})}); await assert.rejects(transcribeVoice({}),/没有识别/)
  registerApiAdapters({transcribeVoice:undefined})
})

const voiceSource=readFileSync(new URL('../src/components/VoiceInput.vue',import.meta.url),'utf8')
const voiceScript=voiceSource.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
const voiceRender=compile(voiceSource.match(/<template>([\s\S]*?)<\/template>/)[1],{isCustomElement:tag=>['view','text'].includes(tag)})
function voiceComponent(extra={}) {
  const props=reactive({disabled:false,embedded:true}),events=[],nativeEvents={},cleanup=[],calls={start:0,stop:0}
  const native={start(){calls.start++},stop(){calls.stop++}}
  for(const name of ['Start','Stop','Error','FrameRecorded','InterruptionBegin','Pause'])native['on'+name]=fn=>{nativeEvents[name]=fn}
  const deps={computed,ref,watch,defineProps:()=>props,defineEmits:()=>((name,value)=>events.push({name,value})),defineExpose(){},onBeforeUnmount:fn=>cleanup.push(fn),
    createVoiceCapture:options=>createVoiceCapture({...options,getRecorder:()=>native,authorize:async()=>{},save:async audio=>({...audio,filePath:'/saved.pcm'}),transcribe:async()=> '正常语音',discard(){},getScope:()=> 'synthetic-voice-scope',...extra})}
  const scope=effectScope()
  const page=scope.run(()=>new Function('deps',`const {${Object.keys(deps)}}=deps;${voiceScript};return {state,levels,busy,overlay,prompt,label,progressVisible,canCancel,progressLabel,cancelLabel,recorder,start,end,touchY,cancel,openSettings}`)(deps))
  const context=proxyRefs({...toRefs(props),...page})
  function cancelButton() {
    function find(node) {
      if(!node||typeof node!=='object')return null
      if(node.type==='button'&&node.props?.class==='voice-progress-cancel')return node
      return Array.isArray(node.children)?node.children.map(find).find(Boolean)||null:null
    }
    return find(voiceRender.call(context,context,[]))
  }
  return {page,events,nativeEvents,calls,cancelButton,
    cancel(){const button=cancelButton();assert.ok(button,'a visible cancel button must be available');button.props.onClick({stopPropagation(){}})},
    async record(){page.start({touches:[{clientY:200}]});await tick();nativeEvents.Start()},
    stop(){page.end({changedTouches:[{clientY:200}]})},
    finish(){nativeEvents.Stop({duration:1000,tempFilePath:'/temp.pcm'})},
    dispose(){cleanup.forEach(fn=>fn());scope.stop()}}
}

test('visible cancel control releases microphone authorization and ignores a late grant',async t=>{
  const permission=deferred(),c=voiceComponent({authorize:()=>permission.promise});t.after(()=>c.dispose())
  c.page.start({touches:[{clientY:200}]})
  assert.equal(c.page.state.value.phase,'authorizing');assert.equal(c.page.cancelLabel.value,'取消录音')
  c.cancel()
  assert.equal(c.page.state.value.phase,'idle');assert.equal(c.cancelButton(),null)
  assert.deepEqual(c.events.at(-1),{name:'busy',value:false})
  permission.resolve();await tick()
  assert.equal(c.calls.start,0);assert.equal(c.events.filter(e=>e.name==='send').length,0)
})

test('visible cancel control stops a late native start without sending or releasing ownership early',async t=>{
  const c=voiceComponent();t.after(()=>c.dispose())
  c.page.start({touches:[{clientY:200}]});await tick()
  assert.equal(c.page.state.value.phase,'starting');c.cancel()
  assert.equal(c.page.state.value.phase,'stopping');assert.equal(c.page.prompt.value,'正在取消录音…')
  assert.equal(c.cancelButton(),null);assert.equal(c.calls.stop,0)
  c.nativeEvents.Start();assert.equal(c.calls.stop,1)
  c.finish();await tick()
  assert.deepEqual(c.events.at(-1),{name:'busy',value:false})
  assert.equal(c.events.filter(e=>e.name==='send').length,0)
})

test('cancel send during native stopping suppresses the impending transcription',async t=>{
  let transcriptions=0
  const c=voiceComponent({transcribe:async()=>{transcriptions++;return '不应发送'}});t.after(()=>c.dispose())
  await c.record();c.stop()
  assert.equal(c.page.state.value.phase,'stopping');assert.equal(c.page.cancelLabel.value,'取消发送')
  c.cancel();c.finish();await tick()
  assert.equal(transcriptions,0);assert.equal(c.page.state.value.phase,'idle')
  assert.deepEqual(c.events.at(-1),{name:'busy',value:false})
  assert.equal(c.events.filter(e=>e.name==='send').length,0)
})

test('cancel recognition aborts model work, releases busy and ignores late text before a fresh recording',async t=>{
  const pending=deferred();let transcriptions=0,aborts=0
  const c=voiceComponent({transcribe:audio=>{
    if(++transcriptions>1)return Promise.resolve('正常语音')
    audio.onModelDownload(true);audio.onCancelReady(()=>{aborts++});return pending.promise
  }});t.after(()=>c.dispose())
  await c.record();c.stop();c.finish();await tick()
  assert.equal(c.page.progressLabel.value,'正在下载语音模型…');assert.equal(c.page.cancelLabel.value,'取消识别')
  c.cancel()
  assert.equal(aborts,1);assert.equal(c.page.state.value.phase,'idle');assert.equal(c.cancelButton(),null)
  assert.deepEqual(c.events.at(-1),{name:'busy',value:false})
  pending.resolve('迟到语音');await tick()
  assert.equal(c.events.filter(e=>e.name==='send').length,0)
  await c.record();c.stop();c.finish();await tick()
  assert.deepEqual(c.events.filter(e=>e.name==='send'),[{name:'send',value:'正常语音'}])
  assert.equal(c.page.busy.value,false)
})
