import { resolveCheckoutAddress } from './address-test-helpers.mjs'
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { ref } from 'vue'
import { createEntryResolver } from '../src/services/entry-routing.js'
import { createWechatAuthClient } from '../src/services/wechat-auth-client.js'
import { getSession, setSession, clearSession, sessionRevision } from '../src/services/session.js'
import { storageContext } from '../src/services/storage.js'
import { rememberInvitation, pendingInvitation, clearInvitation } from '../src/services/family-invitations.js'

function storage() {
  const values=new Map(),redirects=[]
  const navigate=options=>{redirects.push(options.url);options.success?.({errMsg:'navigate:ok'});options.complete?.({errMsg:'navigate:ok'})}
  globalThis.uni={getStorageSync:key=>values.get(key),setStorageSync:(key,value)=>values.set(key,structuredClone(value)),reLaunch:navigate,navigateTo:navigate}
  return {values,redirects}
}
function navigation(resolveAppEntry) {
  const source=readFileSync(new URL('../src/services/navigation.js',import.meta.url),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
  return new Function('isMockMode','isCommerceEnabled','resolveAppEntry','captureInvitation','rememberInvitation','storageContext','getSession',`${source};return {canOpenPage,protectedDestination,checkCurrentEntry,installRouteGuards}`)(false,true,resolveAppEntry,()=>{},rememberInvitation,storageContext,getSession)
}
test('onboarding cannot create a separate household while an invitation is pending',async()=>{
  storage();rememberInvitation('family_'+ 'b'.repeat(48))
  let calls=0
  const source=readFileSync(new URL('../src/services/cloud-profile.js',import.meta.url),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
  const load=new Function('getSession','pendingInvitation','request',`${source};return loadCloudProfile`)(()=>({token:'wechat',householdId:null}),pendingInvitation,async()=>{calls++;return {data:[]}})
  await assert.rejects(load(),error=>error.code==='INVITATION_PENDING')
  assert.equal(calls,0)
})
test('an invitation arriving during household lookup prevents the following creation write',async()=>{
  storage();const calls=[],writes=[]
  const source=readFileSync(new URL('../src/services/cloud-profile.js',import.meta.url),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
  const deps={getSession:()=>({token:'wechat',householdId:null}),pendingInvitation,sessionRevision:()=>1,
    scopedStorage:{getStorageSync:()=>null,setStorageSync:(...args)=>writes.push(args)},
    request:async options=>{calls.push(options);rememberInvitation('family_'+ 'c'.repeat(48));return {data:[]}}}
  const load=new Function('deps',`const {${Object.keys(deps)}}=deps;${source};return loadCloudProfile`)(deps)
  await assert.rejects(load(),error=>error.code==='INVITATION_PENDING')
  assert.equal(calls.length,1);assert.equal(calls[0].method,undefined)
  assert.deepEqual(writes,[])
})
test('pending invitation survives login and logout and takes priority over creating a household',async()=>{
  storage();const code='familyshare_'+ 'a'.repeat(80)
  rememberInvitation(code)
  setSession({accountId:'self',householdId:'home',token:'wechat',authSource:'wechat'})
  clearSession();assert.equal(pendingInvitation(),code)
  const account={accountId:'self',token:'wechat',householdId:null,families:[]}
  let reads=0,selections=0
  const resolve=createEntryResolver({auth:{restore:async()=>account,selectFamily:async()=>{selections++}},readProfile:async()=>{reads++},session:()=>account,invitation:pendingInvitation})
  assert.equal(await resolve(),'/pages/invite/index?token='+code)
  assert.equal(reads,0);assert.equal(selections,0)
  clearInvitation('another');assert.equal(pendingInvitation(),code)
  clearInvitation(code);assert.equal(await resolve(),'/pages/onboarding/index')
})

test('hot launch and intercepted legacy store links return even onboarded users to AI',async()=>{
  const {redirects}=storage(),nav=navigation(async()=>'/pages/chat/index')
  globalThis.getCurrentPages=()=>[{route:'pages/shop/index',options:{commerce:'1'}}]
  await nav.checkCurrentEntry({path:'pages/shop/index',query:{commerce:'1'}})
  assert.deepEqual(redirects,['/pages/chat/index'])
  assert.equal(nav.canOpenPage('/pages/shop/index'),false)
  assert.equal(nav.canOpenPage('/pages/shop/index?commerce=1'),false)
  assert.equal(nav.canOpenPage('/pages/shop/index?commerce=1&cart=1'),true)
  assert.equal(nav.protectedDestination('/pages/shop/index?commerce=1&cart=1','/pages/chat/index'),'/pages/shop/index?commerce=1&cart=1')
  assert.equal(nav.protectedDestination('/pages/shop/index?commerce=1&cart=1','/pages/onboarding/index'),'/pages/onboarding/index')
  assert.equal(nav.canOpenPage('/pages/shop/index?commerce=1&cart=0'),false)
  assert.equal(nav.canOpenPage('/pages/shop/index?commerce=1&cart=1&cart=0'),false)
  assert.equal(nav.protectedDestination('/pages/orders/index','/pages/onboarding/index'),'/pages/onboarding/index')
  const hooks={};uni.addInterceptor=(name,hook)=>hooks[name]=hook
  nav.installRouteGuards()
  assert.equal(hooks.reLaunch.invoke({url:'/pages/shop/index?commerce=1'}),false)
  await new Promise(resolve=>setImmediate(resolve))
  assert.equal(redirects.at(-1),'/pages/chat/index')
  delete globalThis.getCurrentPages
})

test('App foreground restoration and page request retain identity revision until actual account change',async()=>{
  storage()
  setSession({accountId:'17',householdId:'home',token:'wechat',authSource:'wechat'})
  const original=storageContext(),revision=sessionRevision()
  const auth=createWechatAuthClient({session:{read:getSession,save:setSession,clear:clearSession,revision:sessionRevision},send:async()=>({data:{wechat_authenticated:true,account:{id:17},families:[{id:'home',name:'家庭',onboarding_required:false}]}})})
  const nav=navigation(async()=>{await auth.restore();return '/pages/chat/index'})
  globalThis.getCurrentPages=()=>[{route:'pages/orders/detail',options:{id:'original-order'}}]
  await Promise.all([nav.checkCurrentEntry({}),auth.restore()])
  assert.equal(sessionRevision(),revision)
  assert.equal(storageContext(),original)
  setSession({...getSession(),token:'new-token'},{preserveRevision:true})
  assert.notEqual(sessionRevision(),revision)
  delete globalThis.getCurrentPages
})

test('foreground revalidation is fresh and leaves the current page visible while the network is pending',async()=>{
  const {redirects}=storage();let finish,options
  setSession({accountId:'17',householdId:'home',token:'synthetic',authSource:'wechat'})
  const page={route:'pages/chat/index',options:{}}
  globalThis.getCurrentPages=()=>[page]
  const nav=navigation(input=>{options=input;return new Promise(done=>finish=done)})
  const checking=nav.checkCurrentEntry({path:'pages/chat/index'})
  await Promise.resolve()
  assert.deepEqual(options,{fresh:true})
  assert.deepEqual(redirects,[])
  assert.equal(getCurrentPages()[0],page)
  finish('/pages/chat/index');await checking
  assert.deepEqual(redirects,[])
  delete globalThis.getCurrentPages
})

test('a late foreground result cannot jump back from a different page opened during validation',async()=>{
  const {redirects}=storage();let finish
  setSession({accountId:'17',householdId:'home',token:'synthetic',authSource:'wechat'})
  let page={route:'pages/chat/index',options:{}}
  globalThis.getCurrentPages=()=>[page]
  const nav=navigation(()=>new Promise(done=>finish=done))
  const checking=nav.checkCurrentEntry({path:'pages/chat/index'})
  await Promise.resolve();page={route:'pages/profile/index',options:{}}
  finish('/pages/onboarding/index');await checking
  assert.deepEqual(redirects,[])
  delete globalThis.getCurrentPages
})

test('concurrent foreground checks issue one native navigation until completion',async()=>{
  storage();const calls=[]
  uni.reLaunch=options=>calls.push(options)
  globalThis.getCurrentPages=()=>[{route:'pages/chat/index',options:{}}]
  const nav=navigation(async()=>'/pages/onboarding/index')
  const first=nav.checkCurrentEntry({path:'pages/chat/index'}),second=nav.checkCurrentEntry({path:'pages/chat/index'})
  await new Promise(resolve=>setImmediate(resolve));assert.equal(calls.length,1)
  const third=nav.checkCurrentEntry({path:'pages/chat/index'})
  calls[0].success({errMsg:'reLaunch:ok'});calls[0].complete({errMsg:'reLaunch:ok'})
  await Promise.all([first,second,third]);delete globalThis.getCurrentPages
})

test('duplicate page navigations settle both callers through one native operation',async()=>{
  storage();const calls=[],hooks={},settled=[]
  uni.addInterceptor=(method,hook)=>hooks[method]=hook
  uni.reLaunch=options=>calls.push(options)
  const nav=navigation(async()=>'/pages/chat/index');nav.installRouteGuards()
  for(const id of ['first','second'])hooks.reLaunch.invoke({url:'/pages/chat/index',success:()=>settled.push(id),complete:()=>settled.push(id+'-complete')})
  await new Promise(resolve=>setImmediate(resolve));assert.equal(calls.length,1)
  calls[0].success({errMsg:'reLaunch:ok'});calls[0].complete({errMsg:'reLaunch:ok'})
  await new Promise(resolve=>setImmediate(resolve))
  assert.deepEqual(settled.sort(),['first','first-complete','second','second-complete'])
})

test('an account switch during entry resolution cancels the old navigation before native dispatch',async()=>{
  storage();setSession({accountId:'A',householdId:'family-a',token:'token-a'})
  let release;const calls=[],hooks={},failures=[]
  uni.addInterceptor=(method,hook)=>hooks[method]=hook;uni.reLaunch=options=>calls.push(options)
  const nav=navigation(()=>new Promise(resolve=>{release=resolve}));nav.installRouteGuards()
  hooks.reLaunch.invoke({url:'/pages/chat/index',fail:result=>failures.push(result)})
  setSession({accountId:'B',householdId:'family-b',token:'token-b'});release('/pages/chat/index')
  await new Promise(resolve=>setImmediate(resolve));assert.equal(calls.length,0);assert.equal(failures[0].code,'SESSION_CHANGED')
})
test('different taps do not queue multiple pages while one navigation is pending',async()=>{
  storage();let release;const calls=[],hooks={},failures=[]
  uni.addInterceptor=(method,hook)=>hooks[method]=hook;uni.navigateTo=options=>calls.push(options)
  const nav=navigation(()=>new Promise(resolve=>{release=resolve}));nav.installRouteGuards()
  hooks.navigateTo.invoke({url:'/pages/profile/index'})
  hooks.navigateTo.invoke({url:'/pages/my/index',fail:value=>failures.push(value)})
  assert.equal(failures[0].code,'NAVIGATION_IN_PROGRESS')
  release('/pages/chat/index');await new Promise(resolve=>setImmediate(resolve))
  assert.equal(calls.length,1);assert.equal(calls[0].url,'/pages/profile/index')
  calls[0].complete({errMsg:'navigateTo:ok'})
})
test('a new account can navigate without waiting for the previous account request',async()=>{
  storage();setSession({accountId:'A',householdId:'family-a',token:'token-a'})
  const releases=[],calls=[],hooks={},failures=[]
  uni.addInterceptor=(method,hook)=>hooks[method]=hook;uni.navigateTo=options=>calls.push(options)
  const nav=navigation(()=>new Promise(resolve=>releases.push(resolve)));nav.installRouteGuards()
  hooks.navigateTo.invoke({url:'/pages/profile/index',fail:value=>failures.push(value)})
  setSession({accountId:'B',householdId:'family-b',token:'token-b'})
  hooks.navigateTo.invoke({url:'/pages/my/index'})
  assert.equal(failures[0].code,'SESSION_CHANGED')
  releases[1]('/pages/chat/index');await new Promise(resolve=>setImmediate(resolve))
  assert.equal(calls.length,1);assert.equal(calls[0].url,'/pages/my/index')
  calls[0].complete({errMsg:'navigateTo:ok'})
  releases[0]('/pages/chat/index');await new Promise(resolve=>setImmediate(resolve))
  assert.equal(calls.length,1)
})
test('a navigation failure is visible when the caller supplied no failure callback',async()=>{
  storage();const hooks={},toasts=[]
  uni.addInterceptor=(method,hook)=>hooks[method]=hook;uni.showToast=value=>toasts.push(value.title)
  const nav=navigation(async()=>{throw Object.assign(new Error('网络暂不可用'),{code:'NETWORK_ERROR'})});nav.installRouteGuards()
  hooks.navigateTo.invoke({url:'/pages/my/index'})
  await new Promise(resolve=>setImmediate(resolve))
  assert.deepEqual(toasts,['网络暂不可用'])
})

function invitationPage() {
  const {redirects}=storage(),calls=[],code='family_'+ 'a'.repeat(48)
  rememberInvitation(code)
  const deps={ref,defineProps:()=>({token:code}),onMounted(){},onShow(){},onHide(){},onUnmounted(){},getSession:()=>({token:'wechat'}),pendingInvitation,rememberInvitation,clearInvitation,
    request:async options=>{calls.push(options);return {data:options.method?{id:'home'}:{kind:'family',can_accept:true}}},
    wechatAuth:{selectFamily:async id=>{calls.push({selected:id})}},resolveAppEntry:async()=>'/pages/onboarding/index'}
  const codeText=readFileSync(new URL('../src/components/CloudFamilyInvitation.vue',import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
  const page=new Function('deps',`const {${Object.keys(deps)}}=deps;${codeText};return {load,decide,invitation}`)(deps)
  return {page,calls,redirects}
}
test('invitation preview is read-only; decline never calls join or selects a family',async()=>{
  const h=invitationPage();await h.page.load()
  assert.equal(h.calls.length,1);assert.equal(h.calls[0].method,undefined)
  await h.page.decide(false)
  assert.ok(h.calls[1].path.endsWith('/decline'))
  assert.equal(h.calls.some(call=>call.path==='/api/family/join'||call.selected),false)
  assert.equal(pendingInvitation(),'')
})
test('explicit acceptance selects the accepted household before own onboarding',async()=>{
  const h=invitationPage();await h.page.load();await h.page.decide(true)
  assert.equal(h.calls[1].path,'/api/family/join')
  assert.deepEqual(h.calls[2],{selected:'home'})
  assert.equal(h.redirects.at(-1),'/pages/onboarding/index')
})

function packagePage() {
  const {redirects}=storage(),calls=[]
  let failConfirm=true,pending=null,expires=new Date(Date.now()+60000).toISOString(),scope='self',release
  const offer={offer_token:'signed-offer',available:true,name:'青椒肉丝'}
  const commerce={pendingOrder:()=>pending,connect:async()=>{},addresses:async()=>[{id:'address',isDefault:true}],slots:async()=>({supported:true,items:[{id:1,available:true},{id:2,available:false}]}),
    confirmRecommendation:async()=>{calls.push('confirm');if(failConfirm)throw new Error('confirm offline')},
    quoteRecommendation:async()=>{calls.push('quote');return {checkout_token:'quote',expires_at:expires}},
    createOrder:async()=>{calls.push('create');pending={intent:'original'};throw new Error('unknown order')},retryOrder:async()=>{calls.push('recover');pending=null;return {order_sn:'original-order'}}}
  const deps={ref,resolveCheckoutAddress,defineProps:()=>({route:{conversation:'request',offer:'signed-offer'}}),onMounted(){},onShow(){},onUnmounted(){},storageContext:()=>scope,commerce,
    request:async options=>{calls.push(options.method||'GET');if(release)await release;return {data:options.method==='POST'?{package:{package_sn:'package',package_version:1,status:'available'}}:{offers:[offer]}}}}
  const code=readFileSync(new URL('../src/components/ConversationPackagePurchase.vue',import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
  const page=new Function('deps',`const {${Object.keys(deps)}}=deps;${code};return {load,checkout,submit,slots,quote,pending,error,offer,busy}`)(deps)
  return {page,calls,redirects,confirm:()=>failConfirm=false,invalidExpiry:()=>expires='invalid',switch:()=>scope='other',delay:p=>release=p}
}
test('viewing food package does not publish; checkout retries confirmation and uses actual available delivery slots',async()=>{
  const h=packagePage();await h.page.load();assert.deepEqual(h.calls,['GET'])
  await h.page.checkout();assert.match(h.page.error.value,/confirm offline/)
  h.confirm();await h.page.checkout()
  assert.equal(h.calls.filter(call=>call==='POST').length,1)
  assert.equal(h.calls.filter(call=>call==='confirm').length,2)
  assert.deepEqual(h.page.slots.value.map(slot=>slot.id),[1])
  assert.equal(h.page.quote.value.checkout_token,'quote')
})
test('malformed quote expiry cannot create an order; unknown order retries the original intent',async()=>{
  const h=packagePage();h.confirm();h.invalidExpiry();await h.page.load();await h.page.checkout();await h.page.submit()
  assert.equal(h.calls.includes('create'),false);assert.equal(h.page.quote.value,null)
  h.page.quote.value={checkout_token:'quote',expires_at:new Date(Date.now()+60000).toISOString()}
  await h.page.submit();assert.equal(h.page.pending.value,true)
  await h.page.submit(true);assert.equal(h.calls.filter(call=>call==='create').length,1)
  assert.equal(h.redirects.at(-1),'/pages/orders/detail?id=original-order')
})
test('late package read cannot expose the prior account offer',async()=>{
  const h=packagePage();let release;h.delay(new Promise(resolve=>release=resolve))
  const work=h.page.load();h.switch();release();await work
  assert.equal(h.page.offer.value,null)
  await h.page.load();assert.equal(h.page.busy.value,false)
})
