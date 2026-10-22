import * as planning from '../src/services/meal-planning.js'
import * as contexts from '../src/utils/meal-context.js'
import { isMockMode, isCommerceEnabled } from '../src/services/config.js'
import { callApiAdapter } from '../src/services/index.js'
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { computed, effectScope, nextTick, ref, watch } from 'vue'
import * as profiles from '../src/utils/profile.js'
import * as mealState from '../src/utils/meal-state.js'
import * as mealFlow from '../src/utils/meal-flow.js'
import * as bundles from '../src/utils/meal-bundles.js'
import * as memory from '../src/utils/memory.js'
import * as healthCases from '../src/utils/health-cases.js'
import * as customization from '../src/utils/meal-customization.js'
import { createPlan } from '../src/utils/demo.js'
import { scopedStorage, storageContext } from '../src/services/storage.js'
import { setSession } from '../src/services/session.js'
import { mockDelay } from '../src/services/mock-control.js'
import * as images from '../src/services/chat-images.js'
import { registerApiAdapters } from '../src/services/index.js'

function setup() {
  const data = new Map(), calls = { back: 0, toasts: [], selected: [] }
  globalThis.uni = {
    getStorageSync: key => data.get(key), setStorageSync: (key,value) => data.set(key,structuredClone(value)),
    getStorageInfoSync: () => ({ keys:[...data.keys()] }),
    showToast: options => calls.toasts.push(options), hideKeyboard() {},
    saveFile: options => options.success({savedFilePath:'wxfile://saved/' + options.tempFilePath.split('/').pop()}),
    navigateBack: () => { calls.back++ }, redirectTo: options => { calls.redirect=options },
    navigateTo: options => { calls.navigation=options; options.complete?.() },
    previewImage: options => { calls.preview=options },
    getWindowInfo: () => ({statusBarHeight:30}),
    createCameraContext: () => ({
      takePhoto: options => { calls.capture=options },
      setZoom: options => { calls.zoom=options; options.success({zoom:options.zoom}) },
    }),
    chooseImage: options => { calls.picker=options },
    openSetting: options => { calls.settings=options },
  }
  registerApiAdapters({uploadChatImage:undefined,chatWithImage:undefined})
  return {data,calls}
}
function page(path, exposed, extras={}) {
  let show, ready, hide, unload
  const deps={ref,computed,nextTick,watch,...profiles,...mealState,...mealFlow,...bundles,...memory,...healthCases,...customization,...images,...planning,...contexts,isMockMode,isCommerceEnabled,callApiAdapter,
    createPlan,scopedStorage,storageScope:storageContext,storageContext,mockDelay,
    getCurrentInstance:()=>({proxy:{getOpenerEventChannel:()=>({emit(name,image){extras.calls?.selected.push({name,image})}})}}),
    onLoad(fn){fn({})},onShow(fn){show=fn},onReady(fn){ready=fn},onHide(fn){hide=fn},onUnload(fn){unload=fn},...extras,
  }
  const source=readFileSync(new URL('../src/pages/'+path,import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
  const scope=effectScope()
  const value=scope.run(()=>new Function('deps',`const {${Object.keys(deps).join(',')}}=deps;\n${source}\nreturn {${exposed}}`)(deps))
  return {...value,show,ready,hide,dispose(){unload?.();scope.stop()}}
}
const chatFields='input,draftImage,draftSaving,draftError,hasDraftContent,canSend,prepareDraftImage,removeDraftImage,openCamera,ask,messages,thinking,replyError,retryReply,voice,voiceMode,voiceBusy,voiceRef,sendVoice'
const cameraFields='mounted,ready,busy,error,device,flash,zoomChoices,zoom,cameraReady,cameraError,takePhoto,choosePhoto,switchCamera,toggleFlash,setZoom,close'
const chat=extras=>page('chat/index.vue',chatFields,extras)

test('recognized speech automatically sends with the existing photo draft',async()=>{
  setup();const p=chat();await p.prepareDraftImage({path:'/tmp/voice-meal.jpg',source:'album'})
  p.voice();assert.equal(p.voiceMode.value,true);await p.sendVoice('看看这顿饭')
  assert.equal(p.messages.value[0].text,'看看这顿饭');assert.ok(p.messages.value[0].image)
  assert.equal(p.draftImage.value,null);assert.equal(p.input.value,'');p.dispose()
})

test('active voice blocks sending and camera; hiding page cancels recording',async()=>{
  const {calls}=setup();const p=chat();let canceled=0;p.voiceRef.value={cancel(){canceled++}}
  p.voiceBusy.value=true;p.input.value='等待';await p.ask();p.openCamera()
  assert.equal(p.messages.value.length,0);assert.equal(calls.navigation,undefined)
  p.hide();assert.equal(canceled,1);p.dispose()
})

test('chat camera returns a draft without sending, and cancellation keeps input',async()=>{
  const {calls}=setup();const p=chat();p.input.value='这顿饭怎么样？';p.openCamera()
  assert.equal(calls.navigation.url,'/pages/chat/camera');assert.equal(p.input.value,'这顿饭怎么样？');assert.equal(p.messages.value.length,0)
  calls.navigation.events.photoSelected({path:'/tmp/dinner.jpg',source:'camera'});await nextTick();await nextTick()
  assert.equal(p.draftImage.value.localPath,'wxfile://saved/dinner.jpg');assert.equal(p.canSend.value,true);assert.equal(p.messages.value.length,0)
  p.removeDraftImage();assert.equal(p.input.value,'这顿饭怎么样？');p.dispose()
})
test('pure photo send stores one durable message and honestly reports unavailable AI',async()=>{
  setup();const p=chat();await p.prepareDraftImage({path:'/tmp/meal.jpg',source:'album'})
  assert.equal(p.input.value,'');assert.equal(p.canSend.value,true)
  await p.ask();await nextTick()
  assert.equal(p.messages.value.length,1);assert.equal(p.messages.value[0].text,'');assert.match(p.messages.value[0].image.localPath,/saved/)
  assert.match(p.replyError.value,/AI 看图服务暂不可用/);assert.equal(p.draftImage.value,null)
  assert.equal(scopedStorage.getStorageSync('chat-'+mealState.localDate())[0].image.localPath,'wxfile://saved/meal.jpg')
  await p.retryReply();assert.equal(p.messages.value.length,1);p.dispose()
})
test('image retry uses the original photo and text and leaves a newer draft untouched',async()=>{
  setup();const requests=[];let attempts=0
  const p=chat({sendChatImage:async snapshot=>{requests.push(JSON.parse(JSON.stringify(snapshot)));if(++attempts===1)throw new Error('网络失败');return {text:'来自测试服务的回复'}}})
  await p.prepareDraftImage({path:'/tmp/first.jpg'});p.input.value='第一张的问题';await p.ask()
  await p.prepareDraftImage({path:'/tmp/second.jpg'});p.input.value='第二张的问题';await p.retryReply()
  assert.deepEqual(requests[0],requests[1]);assert.equal(p.input.value,'第二张的问题');assert.match(p.draftImage.value.localPath,/second/)
  assert.equal(p.messages.value.filter(m=>m.role==='user').length,1);assert.equal(p.messages.value.at(-1).text,'来自测试服务的回复');p.dispose()
})
test('an urgent text question retains its safety response when a photo is attached',async()=>{
  setup();let calls=0;const p=chat({sendChatImage:async()=>{calls++;return {text:'不应调用'}}})
  await p.prepareDraftImage({path:'/tmp/meal.jpg'});p.input.value='头晕出汗，低血糖怎么办？';await p.ask()
  assert.equal(calls,0);assert.equal(p.messages.value[1].safety,true);assert.match(p.messages.value[1].text,/立即/);assert.ok(p.messages.value[0].image);p.dispose()
})
test('quick prompts stay text-only and preserve the photo draft',async()=>{
  setup();const p=chat({mockDelay:async()=>{}});await p.prepareDraftImage({path:'/tmp/draft.jpg'});p.input.value='还没发的问题'
  await p.ask('糖尿病家庭怎么吃？');assert.equal(p.messages.value[0].image,undefined);assert.match(p.draftImage.value.localPath,/draft/);assert.equal(p.input.value,'还没发的问题');p.dispose()
})
test('failed local save blocks sending, retains the draft and supports retry',async()=>{
  setup();uni.saveFile=options=>options.fail({});const p=chat();await p.prepareDraftImage({path:'/tmp/retain.jpg'})
  assert.equal(p.canSend.value,false);assert.match(p.draftError.value,/保存失败/);assert.equal(p.draftImage.value.path,'/tmp/retain.jpg')
  await p.ask();assert.equal(p.messages.value.length,0)
  uni.saveFile=options=>options.success({savedFilePath:'wxfile://saved/retain.jpg'});await p.prepareDraftImage();assert.equal(p.canSend.value,true);p.dispose()
})
test('removing a photo while it saves cannot resurrect the removed draft',async()=>{
  setup();let finish;const p=chat({persistChatImage:()=>new Promise(resolve=>{finish=resolve})})
  const pending=p.prepareDraftImage({path:'/tmp/removed.jpg'});p.removeDraftImage();finish({localPath:'wxfile://saved/removed.jpg'});await pending
  assert.equal(p.draftImage.value,null);assert.equal(scopedStorage.getStorageSync('last-chat-image'),undefined);p.dispose()
})
test('account switch clears the draft and ignores delayed image preparation',async()=>{
  setup();setSession({accountId:'a',householdId:'home'});let finish;const p=chat({persistChatImage:()=>new Promise(resolve=>{finish=resolve})})
  p.input.value='旧账号内容';const pending=p.prepareDraftImage({path:'/tmp/old.jpg'})
  setSession({accountId:'b',householdId:'home'});p.show();finish({localPath:'wxfile://saved/old.jpg'});await pending
  assert.equal(p.input.value,'');assert.equal(p.draftImage.value,null);assert.equal(p.draftSaving.value,false);assert.equal(scopedStorage.getStorageSync('last-chat-image'),undefined);p.dispose()
})
test('duplicate send is blocked and an unloaded image reply cannot append messages',async()=>{
  setup();let finish,attempts=0;const p=chat({sendChatImage:()=>{attempts++;return new Promise(resolve=>{finish=resolve})}})
  await p.prepareDraftImage({path:'/tmp/photo.jpg'});const pending=p.ask();await p.ask();assert.equal(attempts,1)
  p.dispose();finish({text:'迟到的回复'});await pending;assert.equal(p.messages.value.length,1)
})
test('upload is reused after failed reply, and adapters receive ids rather than device paths',async()=>{
  setup();const uploads=[],requests=[];let attempts=0
  registerApiAdapters({uploadChatImage:async request=>{uploads.push(request);return {id:'image-1'}},chatWithImage:async request=>{requests.push(request);if(++attempts===1)throw new Error('网络失败');return {text:'照片回复'}}})
  const message={id:'client-1',text:'这是什么？',image:{localPath:'wxfile://saved/food.jpg'}}
  await assert.rejects(images.sendChatImage(message),/网络失败/);assert.equal(message.image.remoteId,'image-1')
  assert.deepEqual(await images.sendChatImage(message),{text:'照片回复'});assert.equal(uploads.length,1)
  assert.deepEqual(requests[0],{clientMessageId:'client-1',text:'这是什么？',images:[{id:'image-1'}]});assert.deepEqual(requests[0],requests[1])
})
test('switching account during upload prevents the subsequent AI request',async()=>{
  setup();let finish,chats=0;registerApiAdapters({uploadChatImage:()=>new Promise(resolve=>{finish=resolve}),chatWithImage:async()=>{chats++;return {text:'回复'}}})
  const pending=images.sendChatImage({id:'stale',text:'',image:{localPath:'wxfile://saved/photo.jpg'}})
  setSession({accountId:'other',householdId:'other-home'});finish({id:'image-2'});await assert.rejects(pending,error=>error.code==='STALE_CHAT_REQUEST');assert.equal(chats,0)
})
test('camera waits for readiness, blocks duplicate shutter, and emits one selected photo',()=>{
  const {calls}=setup();const p=page('chat/camera.vue',cameraFields,{calls});p.show();p.ready()
  p.takePhoto();assert.equal(calls.capture,undefined)
  p.cameraReady({detail:{maxZoom:4}});p.takePhoto();const capture=calls.capture;p.takePhoto();assert.equal(calls.capture,capture);assert.equal(p.busy.value,true)
  capture.success({tempImagePath:'/tmp/captured.jpg'});capture.success({tempImagePath:'/tmp/duplicate.jpg'});capture.complete()
  assert.equal(calls.selected.length,1);assert.deepEqual(calls.selected[0],{name:'photoSelected',image:{path:'/tmp/captured.jpg',source:'camera'}});assert.equal(calls.back,1);p.dispose()
})
test('denied camera permission still allows album selection and cancellation stays on camera',()=>{
  const {calls}=setup();const p=page('chat/camera.vue',cameraFields,{calls});p.show();p.ready();p.cameraError()
  p.choosePhoto();assert.deepEqual(calls.picker.sourceType,['album']);assert.equal(calls.picker.count,1)
  calls.picker.fail({errMsg:'chooseImage:fail cancel'});calls.picker.complete();assert.equal(calls.back,0);assert.equal(calls.selected.length,0)
  p.choosePhoto();calls.picker.success({tempFilePaths:['/tmp/album.jpg']});calls.picker.complete();assert.equal(calls.back,1);assert.equal(calls.selected[0].image.source,'album');p.dispose()
})
test('camera uses device zoom limits and switching lens resets zoom and flash',async()=>{
  const {calls}=setup();const p=page('chat/camera.vue',cameraFields,{calls});p.show();p.ready();p.cameraReady({detail:{maxZoom:2.5}})
  assert.deepEqual(p.zoomChoices.value,[1,2]);p.setZoom(4);assert.equal(calls.zoom,undefined);p.setZoom(2);assert.equal(p.zoom.value,2)
  p.toggleFlash();assert.equal(p.flash.value,'on');await p.switchCamera();assert.equal(p.device.value,'front');assert.equal(p.flash.value,'off');assert.equal(p.zoom.value,1);assert.equal(p.mounted.value,true);p.dispose()
})
test('camera releases the preview when hidden and ignores a selection after unload',()=>{
  const {calls}=setup();const p=page('chat/camera.vue',cameraFields,{calls});p.show();p.ready();p.choosePhoto();p.hide()
  assert.equal(p.mounted.value,false);p.dispose();calls.picker.success({tempFilePaths:['/tmp/late.jpg']});calls.picker.complete();assert.equal(calls.selected.length,0);assert.equal(calls.back,0)
})
test('a recoverable capture failure does not disable the next shutter attempt',()=>{
  const {calls}=setup();const p=page('chat/camera.vue',cameraFields,{calls});p.show();p.ready();p.cameraReady({detail:{maxZoom:1}})
  p.takePhoto();const first=calls.capture;first.fail();first.complete();assert.match(p.error.value,/拍照失败/)
  p.takePhoto();assert.notEqual(calls.capture,first);calls.capture.complete();p.dispose()
})
