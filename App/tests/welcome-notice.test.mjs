import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {createRequire} from 'node:module'
import {ref} from 'vue'

const source=readFileSync(new URL('../src/pages/index/index.vue',import.meta.url),'utf8')
const script=source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
const original={version:'synthetic-v1',content_hash:'a'.repeat(64),checkbox_text:'完整确认文案',sections:[1,2,3].map(n=>({title:String(n),text:'合成声明'}))}
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject}}
function page(){
 const hooks={},calls={reads:0,views:[],login:[],native:0,authorize:0,restore:0,ack:0}
 let document=structuredClone(original),account=null,read=async()=>document,view=async()=>{}
 let flowOptions
 const deps={ref,isMockMode:false,canUseBusinessLogin:false,isCommerceEnabled:true,request(){},
  onShow:f=>hooks.show=f,onHide:f=>hooks.hide=f,onUnload:f=>hooks.unload=f,
  getSession:()=>account,storageContext:()=>String(account?.accountId||'guest'),wechatAppId:'wx1234567890abcdef',commerce:{},
  uni:{getDeviceInfo:()=>({platform:'ios'})},
  wechatAuth:{restore:async()=>account,cancelPending(){}},service:{login:async value=>{calls.login.push(value)}},
  readServiceNotice:async()=>{calls.reads++;return read()},viewNoticeDocument:async value=>{calls.views.push(value);await view()},
  acknowledgeReadNotice:async()=>{calls.ack++},resolveAppEntry:async()=>'/pages/chat/index',
  createPhoneLogin:options=>{flowOptions=options;return {
   beginAuthorization(){calls.native++;options.update({busy:false,error:'',awaitingAuthorization:true})},
   async authorize(){calls.authorize++;await options.auth.login()},
   async login(){await options.auth.login()},restore(){calls.restore++},dispose(){},
  }},
 }
 const p=new Function('deps',`const {${Object.keys(deps)}}=deps;${script};return {loadLoginNotice,showLoginNotice,changeLoginNotice,requireLoginNotice,authorizePhone,beginPhoneAuthorization,loginWechatAccount,refreshRejectedNotice,loginNotice,noticeDocument,noticeLoading,noticeViewing,loggingIn,awaitingPhoneAuthorization,loginError,phoneLogin}`)(deps)
 return {p,hooks,calls,setRead:f=>read=f,setView:f=>view=f,setDocument:v=>document=v,setAccount:v=>account=v,get flow(){return flowOptions}}
}
const check=h=>h.p.changeLoginNotice({detail:{value:['yes']}})
const uncheck=h=>h.p.changeLoginNotice({detail:{value:[]}})

test('page entry loads public text without opening a sheet, selecting consent or logging in',async()=>{
 const h=page();h.hooks.show();await h.p.loadLoginNotice()
 assert.equal(h.calls.reads,1);assert.deepEqual(h.calls.views,[]);assert.equal(h.p.loginNotice.value,null);assert.deepEqual(h.calls.login,[])
})
test('unchecked login cannot request a native grant or send any login payload',async()=>{
 const h=page();await h.p.loadLoginNotice();h.p.beginPhoneAuthorization();h.p.authorizePhone({detail:{code:'synthetic'}});h.p.loginWechatAccount()
 assert.equal(h.calls.native,0);assert.equal(h.calls.authorize,0);assert.deepEqual(h.calls.login,[]);assert.match(h.p.loginError.value,/请先阅读并勾选/)
})
test('viewing and closing the document never checks or writes acknowledgement',async()=>{
 const h=page();await h.p.showLoginNotice()
 assert.equal(h.calls.views.length,1);assert.equal(h.p.loginNotice.value,null);assert.equal(h.calls.ack,0);assert.deepEqual(h.calls.login,[])
})
test('explicit checkbox creates exact version receipt and unchecking immediately prevents authorization',async()=>{
 const h=page();await h.p.loadLoginNotice();check(h)
 assert.deepEqual(h.p.loginNotice.value,{version:original.version,content_hash:original.content_hash,acknowledged:true})
 h.p.beginPhoneAuthorization();assert.equal(h.calls.native,1)
 h.p.awaitingPhoneAuthorization.value=false;uncheck(h);h.p.beginPhoneAuthorization();assert.equal(h.calls.native,1)
})
test('new version or hash invalidates selection and viewing never silently accepts it',async()=>{
 for(const document of [{...original,version:'synthetic-v2'},{...original,content_hash:'b'.repeat(64)}]){
  const h=page();await h.p.loadLoginNotice();check(h);h.setDocument(document);await h.p.showLoginNotice()
  assert.equal(h.p.loginNotice.value,null);assert.deepEqual(h.calls.views,[document]);assert.equal(h.calls.ack,0)
 }
})
test('a public document outage cannot enable new login and clicking the link can recover',async()=>{
 const h=page();h.setRead(async()=>{throw Error('synthetic offline')});await h.p.showLoginNotice();check(h)
 assert.equal(h.p.loginNotice.value,null);assert.match(h.p.loginError.value,/offline/)
 h.setRead(async()=>original);await h.p.showLoginNotice();check(h);assert.equal(h.p.requireLoginNotice(),true)
})
test('page hide discards old reads and cannot overwrite a fresh selection after reopening',async()=>{
 const h=page(),old=deferred();h.setRead(()=>old.promise);const pending=h.p.loadLoginNotice();h.hooks.hide()
 h.setRead(async()=>original);h.hooks.show();await h.p.loadLoginNotice();check(h)
 old.resolve({...original,version:'stale'});await pending
 assert.equal(h.p.noticeDocument.value.version,original.version);assert.equal(h.p.requireLoginNotice(),true)
})
test('account changes invalidate a checked guest receipt before native authorization',async()=>{
 const h=page();await h.p.loadLoginNotice();check(h);h.setAccount({accountId:'other',token:'synthetic-token'});h.p.beginPhoneAuthorization()
 assert.equal(h.p.loginNotice.value,null);assert.equal(h.calls.native,0)
})
test('login in progress and an open viewer cannot change selection',async()=>{
 const h=page();await h.p.loadLoginNotice();check(h);h.p.loggingIn.value=true;uncheck(h);assert.ok(h.p.loginNotice.value)
 h.p.loggingIn.value=false;const open=deferred();h.setView(()=>open.promise);const viewing=h.p.showLoginNotice()
 await new Promise(resolve=>setTimeout(resolve,0));uncheck(h);assert.ok(h.p.loginNotice.value);open.resolve();await viewing
})
test('server version rejection clears consent and preloads replacement without selecting it',async()=>{
 const h=page();await h.p.loadLoginNotice();check(h);h.setDocument({...original,version:'synthetic-v2'});h.p.refreshRejectedNotice();await h.p.loadLoginNotice()
 assert.equal(h.p.loginNotice.value,null);assert.equal(h.p.noticeDocument.value.version,'synthetic-v2')
})
test('the login adapter forwards the checked receipt and saves it for an unbound current account',async()=>{
 const h=page();h.setAccount({accountId:'one',token:'synthetic'});await h.p.loadLoginNotice();check(h);h.p.phoneLogin()
 await h.flow.auth.restore();assert.equal(h.calls.ack,1);await h.flow.auth.login()
 assert.deepEqual(h.calls.login,[{serviceNotice:{version:original.version,content_hash:original.content_hash,acknowledged:true}}])
 uncheck(h);assert.throws(()=>h.flow.auth.login(),/请先阅读并勾选/)
})
test('compiled WeChat title uses catchtap outside the checkbox label and follows the login buttons',()=>{
 const require=createRequire(import.meta.url),mpRequire=createRequire(require.resolve('@dcloudio/uni-mp-weixin/package.json'))
 const {compile}=mpRequire('@dcloudio/uni-mp-compiler'),assets=[]
 compile(source.match(/<template>([\s\S]*?)<\/template>/)[1],{filename:'pages/index/index.wxml',miniProgram:{directive:'wx:',event:{key:true},class:{array:true},slot:{fallbackContent:false,dynamicSlotNames:true},emitFile:a=>assets.push(a)}})
 const wxml=String(assets[0].source),link=wxml.match(/<button[^>]*class="login-notice-link"[^>]*>/)?.[0]
 assert.ok(link);assert.match(link,/catchtap=/)
 assert.ok(wxml.indexOf('login-notice')>wxml.indexOf('open-type="getPhoneNumber"'))
 assert.match(wxml,/<\/label><view class="login-notice-copy"/)
})
