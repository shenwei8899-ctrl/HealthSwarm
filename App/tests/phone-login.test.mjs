import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync,existsSync } from 'node:fs'
import { createPhoneLogin } from '../src/services/phone-login.js'

// Only in-memory protocol doubles; no actual account, phone grant or business data is created.
const grant={code:'unit-only-grant',errMsg:'getPhoneNumber:ok'}
function setup({bound=false,logged=false,destination='/pages/chat/index',timers={}}={}){
 let account=logged?{accountId:'29',token:'unit-session'}:null,state,post,entry,login,restore
 const calls=[],status=()=>({user_id:12,phone_bound:bound,phone_masked:bound?'155****0000':null,verification_source:bound?'wechat_phone':null,verified_at:bound?123:null})
 const flow=createPhoneLogin({auth:{restore:async()=>{calls.push('restore');if(restore)return restore();return account},login:async()=>{calls.push('login');if(login)await login();account={accountId:'29',token:'unit-session'}}},session:()=>account,
 commerce:{connect:async()=>calls.push('exchange'),session:()=>({userId:12}),sessionRevision:()=>1,request:async(path,opt)=>{
   calls.push(path);if(path.endsWith('/config'))return {available:true,appid:'app'}
   if(opt?.method==='POST'){assert.deepEqual(opt.data,{phone_code:grant.code});if(post)return post();bound=true}
   return status()
 }},accountContext:()=>account?.accountId,appId:'app',randomKey:()=> 'inline-phone-test-key',
 resolveEntry:async()=>{calls.push('entry');return entry?entry():destination},navigate:async url=>calls.push(url),update:v=>{state=v},...timers})
 return {flow,calls,status,get state(){return state},setPost:f=>post=f,setEntry:f=>entry=f,setLogin:f=>login=f,setRestore:f=>restore=f,switchAccount:()=>{account={accountId:'30',token:'another'}},setBound:()=>{bound=true}}
}
test('one native consent callback logs in, binds existing user, and navigates directly home',async()=>{
 const h=setup();await h.flow.authorize(grant)
 assert.deepEqual(h.calls,['login','exchange','/account/phone/config','/account/phone','/account/phone/wechat','entry','/pages/chat/index'])
 assert.equal(h.state.busy,false);assert.equal(h.state.error,'');assert.equal(JSON.stringify(h.state).includes(grant.code),false)
})
test('valid bound session enters home without another grant or login',async()=>{
 const h=setup({logged:true,bound:true});await h.flow.restore()
 assert.deepEqual(h.calls,['restore','exchange','/account/phone/config','/account/phone','entry','/pages/chat/index'])
})

test('a returning bound account can renew real WeChat login without requesting another phone grant',async()=>{
 const h=setup({bound:true});await h.flow.login()
 assert.deepEqual(h.calls,['login','exchange','/account/phone/config','/account/phone','entry','/pages/chat/index'])
 assert.equal(h.state.needsAuthorization,false);assert.equal(h.state.error,'')
})

test('WeChat login alone never enters the app for an account without a verified phone',async()=>{
 const h=setup();await h.flow.login()
 assert.equal(h.state.needsAuthorization,true);assert.match(h.state.error,/尚未绑定手机号/)
 assert.equal(h.calls.includes('entry'),false);assert.equal(h.calls.includes('/account/phone/wechat'),false)
 await h.flow.authorize(grant)
 assert.equal(h.state.needsAuthorization,false);assert.equal(h.calls.at(-1),'/pages/chat/index')
 assert.equal(h.calls.filter(x=>x==='login').length,1)
})

test('only an explicit login renews an expired session; other restore failures do not replace identity',async()=>{
 const expired=setup({logged:true,bound:true})
 expired.setRestore(async()=>{throw Object.assign(Error('登录已过期'),{code:401})})
 await expired.flow.login()
 assert.equal(expired.calls.filter(x=>x==='login').length,1);assert.equal(expired.calls.at(-1),'/pages/chat/index')
 for(const code of ['NETWORK_ERROR','SESSION_CHANGED',503]){
  const h=setup({logged:true,bound:true});h.setRestore(async()=>{throw Object.assign(Error('未能验证账号'),{code})})
  await h.flow.login();assert.deepEqual(h.calls,['restore']);assert.match(h.state.error,/未能验证账号/)
 }
 const automatic=setup({logged:true,bound:true})
 automatic.setRestore(async()=>{throw Object.assign(Error('登录已过期'),{code:401})})
 await automatic.flow.restore();assert.deepEqual(automatic.calls,['restore'])
})

test('page hiding during explicit WeChat login still discards late results',async()=>{
 const h=setup({bound:true});let release
 h.setLogin(()=>new Promise(resolve=>{release=resolve}))
 const pending=h.flow.login();await h.flow.login();h.flow.dispose();release();await pending
 assert.deepEqual(h.calls,['login']);assert.equal(h.state.busy,false)
})
test('unbound session waits on welcome; denied consent neither logs in nor writes',async()=>{
 const h=setup({logged:true});await h.flow.restore();assert.equal(h.calls.includes('entry'),false)
 const count=h.calls.length;await h.flow.authorize({errMsg:'getPhoneNumber:fail user deny'})
 assert.equal(h.calls.length,count);assert.match(h.state.error,/取消/)
})

test('native tap immediately shows consent feedback without disabling the button or sending requests',()=>{
 let timeout,cleared=0
 const h=setup({timers:{setTimer:callback=>{timeout=callback;return 1},clearTimer:()=>{cleared++}}})
 h.flow.beginAuthorization()
 assert.equal(h.state.awaitingAuthorization,true);assert.equal(h.state.busy,false)
 assert.deepEqual(h.calls,[])
 timeout()
 assert.equal(h.state.awaitingAuthorization,false);assert.match(h.state.error,/未返回手机号授权/)
 assert.deepEqual(h.calls,[])
 h.flow.beginAuthorization();h.flow.dispose()
 assert.equal(cleared,1);assert.equal(h.state.awaitingAuthorization,false);assert.equal(h.state.error,'')
})

test('native callbacks cancel the watchdog; platform failures are not reported as user cancellation',async()=>{
 for(const [detail,expected] of [
   [{errMsg:'getPhoneNumber:fail user deny'},/取消/],
   [{errMsg:'getPhoneNumber:fail',errno:1400001},/额度已用完.*1400001/],
   [{errMsg:'getPhoneNumber:fail privacy permission is not authorized'},/隐私保护指引/],
   [{errMsg:'getPhoneNumber:fail no permission'},/接口权限/],
   [{errMsg:'getPhoneNumber:fail internal error'},/未取得微信手机号授权/],
 ]){
  let cleared=0
  const h=setup({timers:{setTimer:()=>1,clearTimer:()=>{cleared++}}})
  h.flow.beginAuthorization();await h.flow.authorize(detail)
  assert.equal(cleared,1);assert.equal(h.state.awaitingAuthorization,false)
  assert.match(h.state.error,expected);assert.deepEqual(h.calls,[])
 }
 const h=setup({timers:{setTimer:()=>1,clearTimer:()=>{}}})
 h.flow.beginAuthorization();await h.flow.authorize(grant)
 assert.equal(h.state.error,'');assert.equal(h.state.awaitingAuthorization,false)
 assert.equal(h.calls.at(-1),'/pages/chat/index')
})
test('binding conflict never advances and never creates a second login',async()=>{
 const h=setup();h.setPost(async()=>{throw Object.assign(Error('手机号已关联其他账号'),{code:40962})});await h.flow.authorize(grant)
 assert.equal(h.calls.includes('entry'),false);assert.match(h.state.error,/其他账号/);assert.equal(h.calls.filter(x=>x==='login').length,1)
})
test('unknown POST outcome rereads status; only confirmed success enters home',async()=>{
 for(const committed of [true,false]){
  const h=setup();h.setPost(async()=>{if(committed)h.setBound();throw Object.assign(Error('timeout'),{code:'NETWORK_ERROR'})})
  await h.flow.authorize(grant);assert.equal(h.calls.includes('/pages/chat/index'),committed)
  assert.equal(h.calls.filter(x=>x==='/account/phone/wechat').length,1);assert.equal(h.state.uncertain,!committed)
 }
})
test('double callbacks, page hiding and account switching cannot produce duplicate writes or late navigation',async()=>{
 const h=setup();let release;h.setLogin(()=>new Promise(r=>{release=r}));const pending=h.flow.authorize(grant)
 await h.flow.authorize(grant);h.flow.dispose();release();await pending
 assert.deepEqual(h.calls,['login']);assert.equal(h.state.busy,false)
 const other=setup({logged:true,bound:true});let finish;other.setEntry(()=>new Promise(r=>{finish=r}));const p=other.flow.restore()
 while(!finish)await new Promise(r=>setTimeout(r,0));other.switchAccount();finish('/pages/chat/index');await p
 assert.equal(other.calls.includes('/pages/chat/index'),false)
})
test('new users still follow genuine onboarding instead of forging completed health profiles',async()=>{
 const h=setup({destination:'/pages/onboarding/index'});await h.flow.authorize(grant)
 assert.equal(h.calls.at(-1),'/pages/onboarding/index')
})
test('welcome owns the native consent button and standalone binding page is no longer registered',()=>{
 const root=new URL('../',import.meta.url),welcome=readFileSync(new URL('src/pages/index/index.vue',root),'utf8')
 assert.match(welcome,/open-type="getPhoneNumber"/);assert.match(welcome,/@getphonenumber="authorizePhone"/)
 const pages=JSON.parse(readFileSync(new URL('src/pages.json',root),'utf8'))
 assert.equal(pages.pages.some(p=>p.path==='pages/account/phone'),false)
 assert.equal(existsSync(new URL('src/pages/account/phone.vue',root)),false)
 assert.equal(readFileSync(new URL('src/components/CloudMyProfile.vue',root),'utf8').includes('/pages/account/phone'),false)
})
