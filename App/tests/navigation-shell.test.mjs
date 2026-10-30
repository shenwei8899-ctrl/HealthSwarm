import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'

const source = file => readFileSync(new URL('../src/'+file, import.meta.url),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
const evaluate = (code, deps, result) => new Function('deps',`const {${Object.keys(deps)}}=deps;${code};return ${result}`)(deps)
const flush = () => new Promise(resolve=>setImmediate(resolve))
const deferred = () => {let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject}}
function fixture(h5=false,delayRoute=false) {
  let account={accountId:'a',token:'test-token',householdId:'family-a',clientRevision:1,expiresAt:Date.now()/1000+3600,families:[{id:'family-a',onboardingRequired:false}]}
  let route='/pages/chat/index',invite='',preparing=false
  const hooks={},calls=[],loadings=[],toasts=[],checks=[],hashListeners=new Set()
  const pending=[]
  const getSession=()=>account&&structuredClone(account)
  const storageContext=()=>JSON.stringify(account&&[account.accountId,account.token,account.householdId,account.clientRevision])
  const shell=evaluate(source('services/app-entry.js'),{getSession,pendingInvitation:()=>invite,invitationRoute:code=>'/pages/invite/index?token='+code,
    scopedStorage:{getStorageSync:()=>preparing},wechatAuth:{},loadCloudProfile(){},createEntryResolver:()=>()=>{},createEntryCoordinator:()=>()=>{}},'immediateShellEntry')
  const uni={addInterceptor:(method,hook)=>hooks[method]=hook,showLoading:value=>loadings.push(value),hideLoading(){},showToast:value=>toasts.push(value)}
  for(const method of ['navigateTo','redirectTo','reLaunch','switchTab']) uni[method]=options=>{
    if(hooks[method]?.invoke(options)===false)return
    calls.push({method,url:options.url})
    if(!delayRoute)route=options.url
    options.success?.({errMsg:method+':ok'});options.complete?.({errMsg:method+':ok'})
  }
  const nav=evaluate(source('services/navigation.js'),{uni,isMockMode:false,isCommerceEnabled:true,immediateShellEntry:shell,
    resolveAppEntry:options=>{checks.push(options);const d=deferred();pending.push(d);return d.promise},
    captureInvitation(){},rememberInvitation(){},storageContext,getSession,
    window:{location:{get hash(){return '#'+route}},addEventListener:(_,fn)=>hashListeners.add(fn),removeEventListener:(_,fn)=>hashListeners.delete(fn)},getCurrentPages:h5?undefined:()=>[{route:route.split('?')[0].slice(1),options:Object.fromEntries(new URLSearchParams(route.split('?')[1]||''))}]},'{installRouteGuards,checkCurrentEntry}')
  nav.installRouteGuards()
  return {nav,uni,calls,checks,pending,loadings,toasts,shell,completeRoute(value){route=value;for(const fn of [...hashListeners])fn()},get account(){return account},set account(value){account=value},set route(value){route=value},get route(){return route},set invite(value){invite=value},set preparing(value){preparing=value}}
}

for(const url of ['/pages/profile/index','/pages/my/index','/pages/chat/history','/pages/exclusive-plans/index','/pages/scan/index']) {
  test('native shell opens before unresolved network: '+url,async()=>{
    const h=fixture();let settled=false
    h.uni.navigateTo({url,complete:()=>settled=true})
    assert.deepEqual(h.calls,[{method:'navigateTo',url}]);assert.equal(settled,true)
    assert.equal(h.checks.length,0);assert.deepEqual(h.loadings,[])
    await flush();assert.equal(h.checks.length,1);assert.deepEqual(h.checks[0],{fresh:true})
    h.pending[0].resolve('/pages/chat/index');await flush()
    assert.equal(h.route,url);assert.deepEqual(h.loadings,[])
  })
}
test('unknown, expired, unselected and unfinished sessions cannot use the shell shortcut',()=>{
  for(const change of [h=>h.account=null,h=>h.account.expiresAt=1,h=>h.account.families=[],h=>h.account.families[0].onboardingRequired=true,h=>delete h.account.expiresAt]){
    const h=fixture();change(h);h.uni.navigateTo({url:'/pages/exclusive-plans/index'})
    assert.equal(h.calls.length,0);assert.equal(h.checks.length,1)
  }
})
test('invitation and pending preparation still take priority',()=>{
  const h=fixture();h.invite='test-invite';h.uni.navigateTo({url:'/pages/exclusive-plans/index'})
  assert.equal(h.calls[0].url,'/pages/invite/index?token=test-invite')
  const p=fixture();p.preparing=true;p.uni.navigateTo({url:'/pages/exclusive-plans/index'})
  assert.equal(p.calls[0].url,'/pages/onboarding/preparing')
})
test('server entry decision corrects a shell after it has opened',async()=>{
  const h=fixture();h.uni.navigateTo({url:'/pages/exclusive-plans/index'});await flush()
  h.pending[0].resolve('/pages/onboarding/index');await flush()
  // The correction retains the normal guard before dispatching.
  h.pending[1].resolve('/pages/onboarding/index');await flush()
  assert.equal(h.route,'/pages/onboarding/index')
})
for(const result of ['redirect','error'])test('late '+result+' cannot replace a page after the user returns',async()=>{
  const h=fixture();h.uni.navigateTo({url:'/pages/my/index'});await flush();h.route='/pages/chat/index'
  if(result==='redirect')h.pending[0].resolve('/pages/onboarding/index')
  else h.pending[0].reject(Object.assign(new Error('expired'),{code:401}))
  await flush();assert.equal(h.calls.length,1);assert.equal(h.route,'/pages/chat/index');assert.deepEqual(h.toasts,[])
})
test('new page gets its own completion check while an earlier check is pending',async()=>{
  const h=fixture();h.uni.navigateTo({url:'/pages/my/index'});await flush()
  h.uni.navigateTo({url:'/pages/exclusive-plans/index'});await flush()
  assert.equal(h.pending.length,2)
  h.pending[0].resolve('/pages/onboarding/index');await flush();assert.equal(h.calls.length,2)
  h.pending[1].resolve('/pages/onboarding/index');await flush()
  h.pending[2].resolve('/pages/onboarding/index');await flush();assert.equal(h.route,'/pages/onboarding/index')
})
test('account switch rejects both late success and late errors',async()=>{
  for(const error of [false,true]){
    const h=fixture();h.uni.navigateTo({url:'/pages/my/index'});await flush()
    h.account={...h.account,accountId:'b',token:'new-token',householdId:'family-b',clientRevision:2}
    if(error)h.pending[0].reject(Object.assign(new Error('old forbidden'),{code:403}))
    else h.pending[0].resolve('/pages/onboarding/index')
    await flush();assert.equal(h.calls.length,1);assert.deepEqual(h.toasts,[])
  }
})
for(const code of [401,'SESSION_CHANGED','WECHAT_LOGIN_REQUIRED'])test('a parallel request clearing the active session still redirects to login: '+code,async()=>{
  const h=fixture();h.uni.navigateTo({url:'/pages/my/index'});await flush();h.account=null
  h.pending[0].reject(Object.assign(new Error('expired'),{code}));await flush()
  assert.equal(h.route,'/pages/index/index')
})
test('network failure leaves the shell and its back button usable',async()=>{
  const h=fixture();h.uni.navigateTo({url:'/pages/profile/index'});await flush()
  h.pending[0].reject(Object.assign(new Error('offline'),{code:'NETWORK_ERROR'}));await flush()
  assert.equal(h.route,'/pages/profile/index');assert.equal(h.calls.length,1);assert.equal(h.toasts[0].title,'offline')
})
test('H5 without a global getCurrentPages still validates and redirects an expired session',async()=>{
  const h=fixture(true);h.uni.navigateTo({url:'/pages/my/index'});await flush()
  assert.equal(h.checks.length,1);h.account=null
  h.pending[0].reject(Object.assign(new Error('expired'),{code:401}));await flush()
  assert.equal(h.route,'/pages/index/index')
})
test('H5 revalidates after a lazy page changes its hash following native completion',async()=>{
  const h=fixture(true,true);h.uni.navigateTo({url:'/pages/my/index'});await flush()
  assert.equal(h.checks.length,0);h.completeRoute('/pages/my/index');await flush()
  assert.equal(h.checks.length,1);h.account=null
  h.pending[0].reject(Object.assign(new Error('expired'),{code:'SESSION_CHANGED'}));await flush()
  assert.equal(h.calls.at(-1).url,'/pages/index/index')
})
test('only concurrent read-only profile calls share a request and failure permits retry',async()=>{
  let revision=1,account={accountId:'a',token:'token',householdId:'family-a'},calls=[]
  const pending=[]
  const load=evaluate(source('services/cloud-profile.js'),{getSession:()=>account,sessionRevision:()=>revision,pendingInvitation:()=>'',
    request:options=>{calls.push(options);const d=deferred();pending.push(d);return d.promise},normalizeProfile:x=>x,saveProfile(){}},'loadCloudProfile')
  const options={openConsultation:false,readConfiguration:false}
  const a=load(options),b=load(options);assert.equal(calls.length,1)
  pending[0].resolve({data:{source:'api',householdId:'family-a',members:[]}});assert.deepEqual(await a,await b)
  const c=load(options);assert.equal(calls.length,2)
  pending[1].reject(new Error('offline'));await assert.rejects(c,/offline/)
  const d=load(options);assert.equal(calls.length,3)
  // Another account must never join the original read.
  account={...account,accountId:'b',token:'other'};revision=2
  const e=load(options);assert.equal(calls.length,4)
  pending[2].reject(new Error('account changed'));pending[3].resolve({data:{source:'api',householdId:'family-a',members:[]}})
  await assert.rejects(d);await e
})
