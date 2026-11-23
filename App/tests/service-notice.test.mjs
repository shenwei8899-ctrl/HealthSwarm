import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { setSession, getSession } from '../src/services/session.js'
import { installNoticePresenter, ensureServiceNotice, readServiceNotice, viewNoticeDocument, viewServiceNotice, acknowledgeReadNotice, HOME_SERVICE_NOTICE } from '../src/services/service-notice.js'

const document={version:'test-v1',content_hash:'a'.repeat(64),title:'服务声明',checkbox_text:'我已阅读',sections:[1,2,3].map(n=>({title:String(n),text:'合成提示'}))}
const storage=new Map()
globalThis.uni={getStorageSync:key=>storage.get(key),setStorageSync:(key,value)=>storage.set(key,value)}
function setup({accepted=false}={}){
 storage.clear();setSession({accountId:'one',householdId:'family-a',token:'synthetic',isDemo:true})
 let status={version:document.version,content_hash:document.content_hash,acknowledged:accepted},posts=0,shown=0
 const send=async options=>{
  if(options.path==='/api/service-notice')return {data:structuredClone(document)}
  assert.equal(options.path,'/api/account/service-notice')
  if(options.method==='POST'){posts++;assert.deepEqual(options.data,{version:document.version,content_hash:document.content_hash,acknowledged:true});status={...status,acknowledged:true,acknowledged_at:'2026-11-22T00:00:00Z'}}
  return {data:structuredClone(status)}
 }
 const release=installNoticePresenter(async()=>{shown++;return true})
 return {send,release,get posts(){return posts},get shown(){return shown}}
}
test('registration viewing is read-only and never returns an accepted receipt',async()=>{
 const h=setup();let mode;const release=installNoticePresenter(async value=>{mode=value.mode;return true})
 try{const loaded=await readServiceNotice(h.send);assert.equal(await viewNoticeDocument(loaded),undefined);assert.equal(mode,'read');assert.equal(h.posts,0);assert.equal(getSession().serviceNotice,undefined)}finally{release();h.release()}
})
test('the account confirms once and keeps the original session revision',async()=>{
 const h=setup(),before=getSession().clientRevision
 try{await ensureServiceNotice(h.send);assert.equal(h.posts,1);assert.equal(getSession().clientRevision,before);await ensureServiceNotice(h.send);assert.equal(h.posts,1);assert.equal(h.shown,1)}finally{h.release()}
})
test('switching families does not require another account acknowledgement',async()=>{
 const h=setup({accepted:true});try{await ensureServiceNotice(h.send);setSession({...getSession(),householdId:'family-b'});await ensureServiceNotice(h.send);assert.equal(h.shown,0);assert.equal(h.posts,0)}finally{h.release()}
})
test('declining keeps the session and performs no acknowledgement write',async()=>{
 const h=setup(),release=installNoticePresenter(async()=>false)
 try{await assert.rejects(ensureServiceNotice(h.send),e=>e.code==='SERVICE_NOTICE_DECLINED');assert.equal(h.posts,0);assert.equal(getSession().accountId,'one')}finally{release();h.release()}
})
test('switching accounts while the sheet is open cannot confirm the new account',async()=>{
 const h=setup(),release=installNoticePresenter(async()=>{setSession({accountId:'two',householdId:'family-b',token:'other'});return true})
 try{await assert.rejects(ensureServiceNotice(h.send),e=>e.code==='SESSION_CHANGED');assert.equal(h.posts,0);assert.equal(getSession().serviceNotice,undefined)}finally{release();h.release()}
})
test('parallel operations share one reading and confirmation',async()=>{
 const h=setup();try{await Promise.all([ensureServiceNotice(h.send),ensureServiceNotice(h.send)]);assert.equal(h.posts,1);assert.equal(h.shown,1)}finally{h.release()}
})
test('a lost confirmation receipt is checked by reading before continuing',async()=>{
 const h=setup();let lost=false
 const send=async options=>{const reply=await h.send(options);if(options.method==='POST'&&!lost){lost=true;throw Object.assign(new Error('lost'),{code:'NETWORK_ERROR'})}return reply}
 try{assert.equal((await ensureServiceNotice(send)).acknowledged,true);assert.equal(h.posts,1)}finally{h.release()}
})
test('a failed acknowledgement is never cached as success',async()=>{
 const h=setup();const send=options=>options.method==='POST'?Promise.reject(Object.assign(new Error('offline'),{code:'NETWORK_ERROR'})):h.send(options)
 try{await assert.rejects(ensureServiceNotice(send),/offline/);assert.equal(getSession().serviceNotice,undefined)}finally{h.release()}
})
test('read-only statement viewing never changes confirmation',async()=>{
 const h=setup();let mode;const release=installNoticePresenter(async value=>{mode=value.mode;return false})
 try{await viewServiceNotice(h.send);assert.equal(mode,'read');assert.equal(h.posts,0)}finally{release();h.release()}
})
test('homepage displays the approved non-interactive short notice',()=>{
 assert.equal(HOME_SERVICE_NOTICE,'饮食建议仅供参考，不能替代医疗建议、药物及医嘱。')
 const source=readFileSync(new URL('../src/components/ChatWelcome.vue',import.meta.url),'utf8')
 assert.match(source,/<text class="service-notice-summary">\{\{HOME_SERVICE_NOTICE\}\}<\/text>/)
 const sheet=readFileSync(new URL('../src/components/ServiceNoticeSheet.vue',import.meta.url),'utf8')
 assert.match(sheet,/checked=ref\(false\)/);assert.match(sheet,/:disabled="!checked"/)
})

test('closing a history preview restores the underlying page presenter',async()=>{
 const h=setup();let preview=0
 const release=installNoticePresenter(async()=>{preview++;return false})
 release()
 try{await ensureServiceNotice(h.send);assert.equal(preview,0);assert.equal(h.shown,1);assert.equal(h.posts,1)}finally{h.release()}
})

test('a previously logged-in unbound account saves the notice already read before phone login',async()=>{
 const h=setup();try{const loaded=await readServiceNotice(h.send);await viewNoticeDocument(loaded);assert.equal(h.shown,1);await acknowledgeReadNotice(h.send,{version:loaded.version,content_hash:loaded.content_hash,acknowledged:true});await ensureServiceNotice(h.send);assert.equal(h.posts,1);assert.equal(h.shown,1)}finally{h.release()}
})

test('prelogin viewing does not require an authenticated account status request',async()=>{
 const h=setup(),calls=[]
 try{const loaded=await readServiceNotice(async options=>{calls.push(options.path);return {data:document}});await viewNoticeDocument(loaded);assert.deepEqual(calls,['/api/service-notice']);assert.equal(h.posts,0)}finally{h.release()}
})
test('malformed confirmation status cannot authorize continuing',async()=>{
 const h=setup();try{await assert.rejects(ensureServiceNotice(async()=>({data:{acknowledged:true}})),/状态暂时无法读取/);assert.equal(getSession().serviceNotice,undefined)}finally{h.release()}
})

test('API packaging excludes only mock bundle artwork and keeps live oats cover',()=>{
 const source=readFileSync(new URL('../vite.config.js',import.meta.url),'utf8').replace(/^import .*$/gm,'').replace('export default','return')
 const build=mode=>new Function('defineConfig','loadEnv','uniModule','process',source)(factory=>factory({mode:'production'}),()=>({VITE_SERVICE_MODE:mode}),()=>({name:'uni'}),{env:{UNI_PLATFORM:'mp-weixin'},cwd:()=>'.'})
 for(const mode of ['api','mock']){
  const project={type:'asset',source:JSON.stringify({packOptions:{ignore:[]}})}
  build(mode).plugins.at(-1).generateBundle({}, {'project.config.json':project})
  const ignored=JSON.parse(project.source).packOptions.ignore.map(item=>item.value)
  assert.equal(ignored.includes('static/bundles/eggs.webp'),mode==='api')
  assert.equal(ignored.includes('static/bundles/oats.webp'),false)
 }
})
