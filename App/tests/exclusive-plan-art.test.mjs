import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {reactive,nextTick} from 'vue'
const source=readFileSync(new URL('../src/components/ExclusivePlanDeck.vue',import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
function harness(){
 let dispose;const logs=[]
 const page=new Function('reactive','nextTick','onUnmounted','defineProps','defineEmits','console',source+';return {artState,artLoaded,artError}')
 (reactive,nextTick,fn=>dispose=fn,()=>{},()=>()=>{},{info:(...v)=>logs.push(v),warn:(...v)=>logs.push(v)})
 return {...page,dispose:()=>dispose(),logs}
}
const event=attempt=>({currentTarget:{dataset:{attempt}},detail:{errMsg:'synthetic failure',width:300,height:210}})
test('failed art remounts once and stale events cannot commit to the replacement',async()=>{
 const p=harness(),pending=p.artError('economy',event(0))
 assert.equal(p.artState.economy.mounted,false)
 p.artLoaded('economy',event(0));await pending
 assert.equal(p.artState.economy.attempt,1);assert.equal(p.artState.economy.status,'loading')
 p.artLoaded('economy',event(1));assert.equal(p.artState.economy.status,'loaded')
 assert.equal(p.artState.standard.attempt,0)
})
test('two failures terminate at a placeholder without an infinite retry',async()=>{
 const p=harness();await p.artError('premium',event(0));await p.artError('premium',event(1));await p.artError('premium',event(1))
 assert.equal(p.artState.premium.status,'failed');assert.equal(p.artState.premium.attempt,1);assert.equal(p.logs.length,2)
})
test('leaving during a retry never remounts the disposed image',async()=>{
 const p=harness(),pending=p.artError('standard',event(0));p.dispose();await pending
 assert.equal(p.artState.standard.mounted,false);p.artLoaded('standard',event(1));assert.equal(p.artState.standard.status,'loading')
})
