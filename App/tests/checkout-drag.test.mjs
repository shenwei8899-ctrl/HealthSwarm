import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {ref,watch,effectScope,nextTick,reactive,computed} from 'vue'
function mount(embedded=false){
 const scope=effectScope(),props=reactive({open:true,embedded}),listeners=new Map(),hooks=[]
 const source=readFileSync(new URL('../src/components/PurchaseCheckoutSheet.vue',import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
 const deps={ref,watch,computed,defineProps:()=>props,defineEmits:()=>{},onUnmounted:fn=>hooks.push(fn),uni:{getWindowInfo:()=>({windowHeight:800})},document:{addEventListener:(name,fn)=>listeners.set(name,fn),removeEventListener:name=>listeners.delete(name)}}
 const page=scope.run(()=>new Function('deps',`const {${Object.keys(deps)}}=deps;${source};return {panelHeight,dragging,startDrag,moveDrag,stopDrag,toggleHeight}`)(deps))
 return {...page,props,listeners,dispose:()=>{hooks.forEach(fn=>fn());scope.stop()}}
}
const touch=y=>({target:{id:'uni-target'},touches:[{clientY:y,identifier:1}]})
test('header follows upward and downward drag continuously, preserving the chosen height',()=>{
 const p=mount();try{p.startDrag(touch(400));p.moveDrag(touch(360));assert.equal(p.panelHeight.value,85);p.moveDrag(touch(560));assert.equal(p.panelHeight.value,60);p.stopDrag();assert.equal(p.dragging.value,false);assert.equal(p.panelHeight.value,60)}finally{p.dispose()}
})
test('large drags clamp at both limits and never dismiss the sheet',()=>{
 const p=mount();try{p.startDrag(touch(400));p.moveDrag(touch(-1000));assert.equal(p.panelHeight.value,92);p.moveDrag(touch(2000));assert.equal(p.panelHeight.value,42);assert.equal(p.props.open,true)}finally{p.dispose()}
})
test('embedded checkout leaves height under its parent control',()=>{
 const p=mount(true);try{p.startDrag(touch(400));p.moveDrag(touch(600));assert.equal(p.dragging.value,false);assert.equal(p.panelHeight.value,80)}finally{p.dispose()}
})
test('mouse listeners are removed on cancellation, close and unmount',async()=>{
 const p=mount();p.startDrag({clientY:400,button:0,preventDefault(){}});assert.equal(p.listeners.size,2);p.props.open=false;await nextTick();assert.equal(p.listeners.size,0);assert.equal(p.panelHeight.value,80);p.startDrag({clientY:400,button:0,preventDefault(){}});p.dispose();assert.equal(p.listeners.size,0)
})
test('multitouch cancels dragging and small taps toggle height',()=>{
 const p=mount();try{p.startDrag(touch(400));p.moveDrag(touch(398));p.stopDrag();p.toggleHeight();assert.equal(p.panelHeight.value,92);p.startDrag(touch(400));p.moveDrag({touches:[{clientY:200},{clientY:300}]});assert.equal(p.dragging.value,false);assert.equal(p.panelHeight.value,92)}finally{p.dispose()}
})
