import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {ref,effectScope} from 'vue'
import {parse as parseSfc} from 'vue/compiler-sfc'
const requestId='33333333-3333-4333-8333-333333333333'
function storage(){const values=new Map();return {getStorageSync:key=>values.get(key),setStorageSync:(key,value)=>values.set(key,value)}}
function mount(file,fields,extras){
 const hooks={},deps={ref,onShow:fn=>hooks.show=fn,onHide:fn=>hooks.hide=fn,onUnload:fn=>hooks.unload=fn,...extras}
 const source=readFileSync(new URL('../src/components/'+file,import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
 const scope=effectScope(),page=scope.run(()=>new Function('deps',`const {${Object.keys(deps).join(',')}}=deps;${source};return {${fields}}`)(deps))
 return {...page,dispose(){hooks.unload?.();scope.stop()}}
}

test('memory page lists account memories across subjects and keeps archived records read only',async()=>{
 const calls=[]
 const items=[{memory_id:'mother-memory',content:'我妈妈不爱吃香菜',subject_label:'妈妈',version:1,recallable:true,editable:true},
  {memory_id:'old-memory',content:'以前家庭的口味',subject_label:'爸爸',family_label:'原家庭',version:1,recallable:false,editable:false}]
 const p=mount('CloudMemories.vue','load,memories,busy,error,pending,nextCursor,edit,remove,perform',{
  storageContext:()=> 'account:family',scopedStorage:storage(),newHealthRequestId:()=>requestId,
  request:async options=>{calls.push(options.path);return {data:{memories:items,next_cursor:null}}},
 })
 try{
  await p.load()
  assert.deepEqual(calls,['/api/health/v1/memory'])
  assert.equal(p.memories.value.length,2)
  const Vue=await import('vue'),{renderToString}=await import('vue/server-renderer')
  const template=parseSfc(readFileSync(new URL('../src/components/CloudMemories.vue',import.meta.url),'utf8')).descriptor.template.content
  const render=Vue.compile(template)
  const html=await renderToString(Vue.createSSRApp({setup:()=>p,render,components:{AppNavBar:{setup:(_,ctx)=>()=>Vue.h('view',ctx.slots.default?.())}}}))
  assert.match(html,/妈妈/);assert.match(html,/爸爸/)
  assert.match(html,/不用于当前对话/)
  assert.equal((html.match(/>修改<\/button>/g)||[]).length,1)
  assert.equal((html.match(/>删除<\/button>/g)||[]).length,2)
 }finally{p.dispose()}
})

test('memory pagination and stale account responses preserve account isolation',async()=>{
 let scope='A',resolve
 const calls=[]
 const p=mount('CloudMemories.vue','load,hide,memories,busy,error,pending,nextCursor',{
  storageContext:()=>scope,scopedStorage:storage(),newHealthRequestId:()=>requestId,
  request:async options=>{calls.push(options.path);if(calls.length===1)return {data:{memories:[{memory_id:'a'}],next_cursor:'cursor'}}
   if(calls.length===2)return {data:{memories:[{memory_id:'b'}],next_cursor:null}}
   return new Promise(done=>{resolve=done})},
 })
 try{
  await p.load();await p.load(true)
  assert.deepEqual(p.memories.value.map(m=>m.memory_id),['a','b'])
  assert.equal(calls[1],'/api/health/v1/memory?after=cursor')
  const loading=p.load();p.hide();scope='B'
  resolve({data:{memories:[{memory_id:'private-A'}],next_cursor:null}});await loading
  assert.deepEqual(p.memories.value,[])
 }finally{p.dispose()}
})
