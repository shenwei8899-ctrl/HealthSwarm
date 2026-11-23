import test from 'node:test'
import assert from 'node:assert/strict'
import {request} from '../src/services/request.js'
import {setSession,getSession} from '../src/services/session.js'
import {installNoticePresenter} from '../src/services/service-notice.js'
const document={version:'v1',content_hash:'b'.repeat(64),title:'声明',checkbox_text:'我已阅读',sections:[1,2,3].map(n=>({title:String(n),text:'合成正文'}))}
function harness(show=async()=>true){
 const storage=new Map(),calls=[];let acknowledged=false
 globalThis.window={};globalThis.uni={getStorageSync:key=>storage.get(key),setStorageSync:(key,value)=>storage.set(key,value),request(options){
  calls.push({path:options.url,method:options.method,data:options.data})
  let data,statusCode=200
  if(options.url==='/api/account/service-notice'){
   if(options.method==='POST')acknowledged=true
   data={version:document.version,content_hash:document.content_hash,acknowledged}
  }else if(options.url==='/api/service-notice')data=document
  else if(!acknowledged){statusCode=403;data={detail:{code:'SERVICE_NOTICE_REQUIRED',message:'请先确认'}}}
  else data={id:'existing-client-request'}
  options.success({statusCode,data})
 }}
 setSession({accountId:'one',token:'synthetic',householdId:'family-a'})
 return {calls,release:installNoticePresenter(show)}
}
test('a server notice rejection confirms then retries the exact original request once',async()=>{
 const h=harness(),data={meta:{request_id:'original'},query:'合成问题'}
 try{const result=await request({path:'/api/agent/runs',method:'POST',data});assert.equal(result.data.id,'existing-client-request');const attempts=h.calls.filter(o=>o.path==='/api/agent/runs');assert.equal(attempts.length,2);assert.deepEqual(attempts[0],attempts[1]);assert.equal(h.calls.filter(o=>o.path==='/api/account/service-notice'&&o.method==='POST').length,1)}finally{h.release();delete globalThis.window}
})
test('cancelling confirmation never retries the AI request or clears identity',async()=>{
 const h=harness(async()=>false)
 try{await assert.rejects(request({path:'/api/agent/runs',method:'POST',data:{}}),e=>e.code==='SERVICE_NOTICE_DECLINED');assert.equal(h.calls.filter(o=>o.path==='/api/agent/runs').length,1);assert.equal(getSession().accountId,'one')}finally{h.release();delete globalThis.window}
})
test('switching families during confirmation never replays the old family action',async()=>{
 const h=harness(async()=>{setSession({...getSession(),householdId:'family-b'});return true})
 try{await assert.rejects(request({path:'/api/agent/runs',method:'POST',data:{}}),e=>e.code==='SESSION_CHANGED');assert.equal(h.calls.filter(o=>o.path==='/api/agent/runs').length,1)}finally{h.release();delete globalThis.window}
})

test('a notice read outage is a known rejection rather than an uncertain AI write',async()=>{
 const h=harness();const original=globalThis.uni.request
 globalThis.uni.request=options=>options.url==='/api/account/service-notice'
  ?options.success({statusCode:503,data:{detail:'合成声明接口故障'}}):original(options)
 try{await assert.rejects(request({path:'/api/agent/runs',method:'POST',data:{}}),e=>e.code==='SERVICE_NOTICE_PENDING'&&e.noticeRejected===true);assert.equal(h.calls.filter(o=>o.path==='/api/agent/runs').length,1)}finally{h.release();delete globalThis.window}
})
