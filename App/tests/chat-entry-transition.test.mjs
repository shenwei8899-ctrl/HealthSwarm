import test from 'node:test'
import assert from 'node:assert/strict'
import {createChatEntryTransition,canRestoreChatHome} from '../src/services/chat-entry-transition.js'
import {createChatKeyboardLayout,chatAvailableHeight} from '../src/services/chat-keyboard-layout.js'

function scene() {
  const context={eligible:true},jobs=[]
  let view
  const motion=createChatEntryTransition({read:()=>context,onChange:v=>view=v,schedule:fn=>{jobs.push(fn);return jobs.length},cancel(){}})
  motion.reconcile()
  return {context,jobs,motion,get view(){return view}}
}
test('focus starts leaving before a message; loading and immediate send do not tear down the welcome',()=>{
  const s=scene();s.motion.enter();s.context.focused=true
  assert.equal(s.view.phase,'leaving')
  s.context.eligible=false;s.context.busy=true;s.motion.reconcile()
  assert.equal(s.view.phase,'leaving')
  s.context.hasMessages=true;s.motion.reconcile();assert.equal(s.view.phase,'leaving')
  s.motion.finish(s.view.generation);assert.equal(s.view.phase,'conversation')
  s.jobs[0]();assert.equal(s.view.phase,'conversation')
})
test('empty close restores home only after the fade; draft/voice/camera/intent/task prevent restoration',()=>{
  for(const key of ['hasDraft','voiceMode','busy','intent','keyboardOpen','focused','blocked','hasMessages']) {
    const s=scene();s.motion.enter();s.context[key]=true;s.motion.finish(s.view.generation)
    assert.notEqual(s.view.phase,'home',key)
    s.context[key]=false;s.motion.reconcile();assert.equal(s.view.phase,'home',key)
  }
  assert.equal(canRestoreChatHome({eligible:false}),false)
})
test('hide, account reset and rapid reopen ignore the old animation callback',()=>{
  const s=scene();s.motion.enter();s.motion.pause();s.motion.reset();s.motion.resume()
  s.motion.enter();s.context.focused=true;const ticket=s.view.generation
  s.jobs[0]();s.motion.finish(ticket-1);assert.equal(s.view.phase,'leaving')
  s.motion.finish(ticket);assert.equal(s.view.phase,'composing')
  s.motion.dispose();s.jobs.at(-1)();assert.equal(s.view.phase,'composing')
})
test('consent and failure panels cancel a fade immediately instead of being covered',()=>{
  const s=scene();s.motion.enter();s.context.blocked=true;s.motion.reconcile()
  assert.equal(s.view.phase,'composing');s.jobs[0]();assert.equal(s.view.phase,'composing')
})
test('keyboard height is accounted for once with full, partial or absent native resize',()=>{
  for(const windowHeight of [800,650,500])assert.equal(chatAvailableHeight({baseline:800,windowHeight,keyboardHeight:300}),500)
  assert.equal(chatAvailableHeight({baseline:800,windowHeight:800}),800)
})
function nativeKeyboard() {
  const listeners={},info={windowHeight:800,windowWidth:390};let view
  const api={getWindowInfo:()=>info,onWindowResize:fn=>listeners.resize=fn,offWindowResize:()=>delete listeners.resize,onKeyboardHeightChange:fn=>listeners.keyboard=fn,offKeyboardHeightChange:()=>delete listeners.keyboard}
  const layout=createChatKeyboardLayout({platform:'native',api,onChange:v=>view=v})
  layout.start();layout.focus(true)
  return {layout,listeners,info,get view(){return view}}
}
test('native resize arriving before keyboard height preserves the keyboard-closed baseline',()=>{
  const k=nativeKeyboard();k.info.windowHeight=500;k.listeners.resize({size:{windowHeight:500}})
  k.listeners.keyboard({height:300});assert.equal(k.view.height,500);assert.equal(k.view.homeHeight,800)
  k.listeners.keyboard({height:0});k.layout.focus(false);k.info.windowHeight=800;k.listeners.resize({size:{windowHeight:800}})
  assert.equal(k.view.height,800);assert.equal(k.view.keyboardOpen,false)
})
test('native keyboard-first order and listener cleanup work across repeated page returns',()=>{
  const k=nativeKeyboard();k.listeners.keyboard({height:300});assert.equal(k.view.height,500)
  k.info.windowHeight=500;k.listeners.resize({size:{windowHeight:500}});assert.equal(k.view.height,500)
  const late=k.listeners.keyboard;k.layout.stop();late({height:300})
  assert.deepEqual(Object.keys(k.listeners),[]);assert.equal(k.view.height,0)
  k.info.windowHeight=800;k.layout.start();assert.equal(k.view.height,800)
  k.layout.stop()
})
test('H5 follows visualViewport and retains frozen welcome dimensions without double avoidance',()=>{
  const events=new Map(),viewportEvents=new Map();let view
  const viewport={height:800,offsetTop:0,scale:1,addEventListener:(n,f)=>viewportEvents.set(n,f),removeEventListener:n=>viewportEvents.delete(n)}
  const browser={innerWidth:390,innerHeight:800,visualViewport:viewport,addEventListener:(n,f)=>events.set(n,f),removeEventListener:n=>events.delete(n)}
  const layout=createChatKeyboardLayout({platform:'h5',browser,onChange:v=>view=v})
  layout.start();layout.focus(true);viewport.height=490;viewport.offsetTop=12;viewportEvents.get('resize')()
  layout.keyboard({height:310});assert.equal(view.height,490);assert.equal(view.offsetTop,12);assert.equal(view.keyboardOpen,true);assert.equal(view.homeHeight,800)
  layout.focus(false);assert.equal(view.keyboardOpen,true)
  viewport.height=800;viewport.offsetTop=0;viewportEvents.get('resize')();assert.equal(view.keyboardOpen,false)
  layout.stop();assert.equal(events.size,0);assert.equal(viewportEvents.size,0)
})
