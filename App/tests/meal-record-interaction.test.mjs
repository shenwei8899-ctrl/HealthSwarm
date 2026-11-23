import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {createRequire} from 'node:module'
import {join} from 'node:path'
import vm from 'node:vm'
import {ref,computed,watch,reactive,nextTick,effectScope} from 'vue'
const source=readFileSync(new URL('../src/components/MealRecordSheet.vue',import.meta.url),'utf8')
function mount(height=800){
 const scope=effectScope(),props=reactive({entry:{key:'test'},availableHeight:height}),events=[],hooks=[],listeners=new Map();let now=1000,api
 const deps={ref,computed,watch,onUnmounted:fn=>hooks.push(fn),defineOptions(){},defineProps:()=>props,defineEmits:()=>((...args)=>events.push(args)),defineExpose:value=>api=value,Date:{now:()=>now},uni:{getWindowInfo:()=>({windowHeight:800})},document:{addEventListener:(type,fn)=>listeners.set(type,fn),removeEventListener:type=>listeners.delete(type)}}
 const script=source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
 const state=scope.run(()=>new Function('deps',`const {${Object.keys(deps)}}=deps;${script};return {capture,panelHeight,dragging,startDrag,moveDrag,stopDrag,close,closeMask}`)(deps))
 return {...state,props,events,listeners,api,advance:n=>now+=n,dispose(){hooks.forEach(fn=>fn());scope.stop()}}
}
const touch=(y,id=1)=>({touches:[{clientY:y,identifier:id}]})
test('header drag follows both directions relative to its actual container',()=>{
 const p=mount(600);try{p.startDrag(touch(400));p.moveDrag(touch(340));assert.equal(p.panelHeight.value,90);p.moveDrag(touch(520));assert.equal(p.panelHeight.value,60);p.stopDrag();assert.equal(p.panelHeight.value,60);assert.equal(p.events.length,0)}finally{p.dispose()}
})
test('drag limits clamp without closing or consuming an accidental release tap',()=>{
 const p=mount();try{p.startDrag(touch(400));p.moveDrag(touch(-500));assert.equal(p.panelHeight.value,94);p.moveDrag(touch(1400));assert.equal(p.panelHeight.value,42);p.stopDrag();p.closeMask();assert.equal(p.events.length,0);p.advance(351);p.closeMask();assert.deepEqual(p.events,[['close']])}finally{p.dispose()}
})
test('small taps do not resize; multiple fingers and touch cancellation stop resizing',()=>{
 const p=mount();try{p.startDrag(touch(400));p.moveDrag(touch(398));p.stopDrag();assert.equal(p.panelHeight.value,80);p.startDrag(touch(400));p.moveDrag({touches:[{clientY:300},{clientY:280}]});assert.equal(p.dragging.value,false);p.moveDrag(touch(100));assert.equal(p.panelHeight.value,80)}finally{p.dispose()}
})
test('touch identifier changes cannot move the panel',()=>{
 const p=mount();try{p.startDrag(touch(400));p.moveDrag(touch(100,2));assert.equal(p.panelHeight.value,80)}finally{p.dispose()}
})
test('resize and unmount clear mouse tracking; reopening resets the default height',async()=>{
 const p=mount();p.startDrag({clientY:400,button:0,preventDefault(){}});p.moveDrag({clientY:300});assert.equal(p.listeners.size,2);p.props.availableHeight=500;await nextTick();assert.equal(p.dragging.value,false);assert.equal(p.listeners.size,0);p.startDrag({clientY:400,button:0,preventDefault(){}});p.dispose();assert.equal(p.listeners.size,0);const reopened=mount();assert.equal(reopened.panelHeight.value,80);reopened.dispose()
})
test('close stays blocked during transport and delegates nested editing to the editor',()=>{
 const p=mount();try{p.capture.value={isBusy:true,handleBack:()=>false};p.close();assert.equal(p.events.length,0);p.capture.value={isBusy:false,handleBack:()=>true};p.close();assert.equal(p.events.length,0);p.capture.value={isBusy:false,handleBack:()=>false};p.close();assert.deepEqual(p.events,[['close']])}finally{p.dispose()}
})
const require=createRequire(import.meta.url),mpRequire=createRequire(require.resolve('@dcloudio/uni-mp-weixin/package.json')),{compile}=mpRequire('@dcloudio/uni-mp-compiler')
function wxml(template){const assets=[];compile(template,{filename:'components/MealRecordSheet.wxml',miniProgram:{directive:'wx:',event:{key:true},class:{array:true},slot:{fallbackContent:false,dynamicSlotNames:true},emitFile:a=>assets.push(a)}});return String(assets[0].source)}
test('real WeChat compiler isolates panel taps and binds header-only native touch dragging',()=>{
 const xml=wxml(source.match(/<template>([\s\S]*?)<\/template>/)[1]);const panel=xml.match(/<view[^>]*record-panel[^>]*>/)[0],area=xml.match(/<view[^>]*record-drag-area[^>]*>/)[0],mask=xml.match(/<view[^>]*record-mask[^>]*>/)[0],close=xml.match(/<button[^>]*aria-label="关闭记一餐"[^>]*>/)[0]
 assert.match(panel,/catchtap=/);assert.match(mask,/bindtap=/);assert.match(close,/catchtap=/);assert.match(close,/catchtouchstart=/)
 for(const event of ['start','move','end','cancel'])assert.match(area,new RegExp('catchtouch'+event+'='))
 assert.doesNotMatch(source,/@click\.self=/)
})
test('installed WeChat handlers stop an option tap before reaching close',{skip:!process.env.MEAL_RECORD_MINIAPP},()=>{
 let component;const hooks=[],vendor={ref,computed,watch,onUnmounted:fn=>hooks.push(fn),_export_sfc:x=>x,o:fn=>fn,sr:()=>null,p:x=>x,n:x=>x,s:x=>x,t:String};const scope=effectScope()
 const base=join(process.env.MEAL_RECORD_MINIAPP,'components/MealRecordSheet'),xml=readFileSync(base+'.wxml','utf8');vm.runInNewContext(readFileSync(base+'.js','utf8'),{require:()=>vendor,wx:{createComponent:x=>component=x},Math,exports:{},document:{removeEventListener(){}},Date})
 const events=[],render=scope.run(()=>component.setup({entry:{},availableHeight:800},{expose(){},emit:(...args)=>events.push(args)})),bindings=render({},{}),panel=xml.match(/<view[^>]*record-panel[^>]*>/)[0],mask=xml.match(/<view[^>]*record-mask[^>]*>/)[0]
 // Simulate native bubbling from an editor option through the compiled ancestor tags.
 for(const tag of [panel,mask]){const m=tag.match(/(catchtap|bindtap)="\{\{([^}]+)\}\}"/);if(m){bindings[m[2]]({type:'tap',target:{id:'option'},currentTarget:{id:'ancestor'}});if(m[1]==='catchtap')break}}
 assert.equal(events.length,0);const key=mask.match(/bindtap="\{\{([^}]+)\}\}"/)[1];bindings[key]({type:'tap'});assert.deepEqual(events,[['close']]);hooks.forEach(fn=>fn());scope.stop()
})
