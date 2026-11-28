import test from 'node:test'
import assert from 'node:assert/strict'
import { createMyProfileLoader } from '../src/services/my-profile-loader.js'
import { readFileSync } from 'node:fs'
import { ref, reactive, computed } from 'vue'

const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return{promise,resolve,reject}}
const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve()}
const profile=(patch={})=>({source:'api',householdId:'family-a',usageMode:'家庭使用',members:[{relation:'本人',name:'合成用户',health:'不得缓存的健康正文'}],...patch})
function scene(options={}) {
  let clock=100000,serial=0,scope='account-a:family-a:r1',account={token:'synthetic-a',householdId:'family-a'},local=null
  const state={profile:null,avatar:'',nickname:'',busy:false,error:''},cache=options.cache||{entry:null},jobs=new Map(),calls={restore:0,profile:0,account:0,login:0},reports=[]
  const loader=createMyProfileLoader({state,cache,session:()=>account,context:()=>scope,now:()=>clock,
    readCachedProfile:()=>local,schedule:fn=>{jobs.set(++serial,fn);return serial},cancel:id=>jobs.delete(id),
    restore:async()=>{calls.restore++;return options.restore?options.restore():account},
    readProfile:async()=>{calls.profile++;const value=await(options.readProfile?options.readProfile():profile());local={...value,revision:clock};return value},
    readAccount:async()=>{calls.account++;return options.readAccount?options.readAccount():{nickname:'合成昵称',avatar:'https://example.test/avatar.png'}},
    loginRequired:()=>calls.login++,report:value=>reports.push(value)})
  return {loader,state,cache,calls,jobs,reports,
    advance:ms=>{clock+=ms},expire:()=>{clock+=20000;for(const job of [...jobs.values()])job()},
    local:value=>{local=value},switch:()=>{scope='account-b:family-b:r2';account={token:'synthetic-b',householdId:'family-b'};local=null},
    logout:()=>{scope='guest';account=null}}
}

test('mount/show and hide/show share one read; warm return keeps summary without rereading',async()=>{
  const gate=deferred(),s=scene({readProfile:()=>gate.promise})
  const first=s.loader.show(),second=s.loader.show()
  assert.equal(first,second);assert.equal(s.state.busy,true)
  await flush();assert.deepEqual(s.calls,{restore:1,profile:1,account:1,login:0})
  s.loader.hide();gate.resolve(profile());await first
  assert.equal(s.cache.entry.profile.memberCount,1)
  await s.loader.show();assert.equal(s.state.profile.usageMode,'家庭使用');assert.equal(s.state.busy,false)
  assert.equal(s.calls.profile,1);assert.equal(s.calls.restore,1)
  assert.equal(JSON.stringify(s.cache).includes('不得缓存的健康正文'),false)
})

test('a confirmed existing family cache renders immediately without another profile request',async()=>{
  const s=scene();s.local({...profile(),revision:99900})
  const pending=s.loader.show()
  assert.equal(s.state.profile.memberCount,1);assert.equal(s.state.busy,false)
  await pending;assert.equal(s.calls.restore,0);assert.equal(s.calls.profile,0);assert.equal(s.calls.account,1)
  s.local({...profile({usageMode:'个人使用'}),revision:100001});s.advance(1)
  await s.loader.show();assert.equal(s.state.profile.usageMode,'个人使用');assert.equal(s.calls.profile,0)
})

test('expired summary stays visible while background refresh replaces it',async()=>{
  let gate=null
  const s=scene({readProfile:()=>gate?gate.promise:profile()})
  await s.loader.show();s.advance(60001);gate=deferred()
  const pending=s.loader.show();assert.equal(s.state.profile.memberCount,1);assert.equal(s.state.busy,false)
  await flush();assert.equal(s.calls.profile,2)
  gate.resolve(profile({members:[]}));await pending
  assert.equal(s.state.profile.memberCount,0)
})

test('a callback that never returns ends loading at the deadline and late content is ignored',async()=>{
  const gate=deferred(),s=scene({restore:()=>gate.promise})
  const pending=s.loader.show();s.expire();assert.equal(await pending,false)
  assert.equal(s.state.busy,false);assert.match(s.state.error,/超时/);assert.equal(s.jobs.size,0)
  gate.resolve({token:'synthetic-a'});await flush()
  assert.equal(s.calls.profile,0);assert.equal(s.state.profile,null)
  assert.deepEqual(s.reports,[{stage:'session',code:'PROFILE_TIMEOUT',elapsedMs:20000}])
})

test('timed-out background refresh preserves display and a manual retry succeeds',async()=>{
  let blocked=false,gate=deferred()
  const s=scene({readProfile:()=>blocked?gate.promise:profile()})
  await s.loader.show();s.advance(60001);blocked=true
  const pending=s.loader.show();await flush();s.expire();await pending
  assert.equal(s.state.profile.memberCount,1);assert.match(s.state.error,/上次/)
  blocked=false;await s.loader.show({force:true});assert.equal(s.state.error,'')
  gate.resolve(profile({members:[]}));await flush()
  assert.equal(s.state.profile.memberCount,1)
})

for(const code of [401,403,404,410])test(`explicit ${code} rejects cached display`,async()=>{
  let rejected=false
  const s=scene({readProfile:async()=>{if(rejected)throw Object.assign(new Error('denied'),{code});return profile()}})
  await s.loader.show();s.advance(60001);rejected=true;await s.loader.show()
  assert.equal(s.state.profile,null);assert.equal(s.state.avatar,'');assert.equal(s.cache.entry,null)
  assert.equal(s.calls.login,code===401?1:0)
})

test('switching account during a slow read prevents its result from entering the new account',async()=>{
  const gate=deferred();let reads=0
  const s=scene({readProfile:()=>++reads===1?gate.promise:profile({householdId:'family-b',usageMode:'个人使用'})})
  const old=s.loader.show();await flush();s.switch()
  await s.loader.show();assert.equal(s.state.profile.usageMode,'个人使用')
  gate.resolve(profile());await old;await flush()
  assert.equal(s.state.profile.usageMode,'个人使用');assert.equal(s.cache.entry.key,'account-b:family-b:r2')
})

test('a mismatched family cache is ignored and logout clears the display',async()=>{
  const s=scene();s.local({...profile({householdId:'another-family'}),revision:99999})
  const pending=s.loader.show();assert.equal(s.state.profile,null);await pending;assert.equal(s.calls.profile,1)
  s.logout();await s.loader.show();assert.equal(s.state.profile,null);assert.equal(s.calls.login,1)
})

test('mounted/show callbacks without a session request login only once',async()=>{
  const s=scene();s.logout();await Promise.all([s.loader.show(),s.loader.show()])
  assert.equal(s.calls.login,1);assert.equal(s.calls.profile,0);assert.equal(s.calls.restore,0)
})

test('optional avatar network failure does not discard the family summary',async()=>{
  const s=scene({readAccount:async()=>{throw Object.assign(new Error('network'),{code:'NETWORK_ERROR'})}})
  assert.equal(await s.loader.show(),true);assert.equal(s.state.profile.memberCount,1)
  assert.equal(s.state.error,'');assert.equal(s.state.busy,false)
  assert.equal(s.reports[0].stage,'account')
})

test('a permanently pending optional read cannot keep the page busy after profile success',async()=>{
  const s=scene({readAccount:()=>new Promise(()=>{})})
  const pending=s.loader.show();await flush();assert.equal(s.state.profile.memberCount,1);assert.equal(s.state.busy,false)
  s.expire();await pending;assert.equal(s.jobs.size,0)
  assert.equal(s.reports.at(-1).stage,'account')
})

test('disposing cancels the page deadline and prevents delayed publication',async()=>{
  const gate=deferred(),s=scene({readProfile:()=>gate.promise})
  const pending=s.loader.show();await flush();s.loader.dispose();await pending
  assert.equal(s.jobs.size,0);gate.resolve(profile());await flush();assert.equal(s.state.profile,null)
})

test('returning from settings refreshes nickname without clearing or rereading the family',async()=>{
  let nickname='旧昵称'
  const s=scene({readAccount:async()=>({nickname,avatar:''})})
  await s.loader.show();s.loader.hide();nickname='新昵称'
  const pending=s.loader.show();assert.equal(s.state.profile.memberCount,1);await pending
  assert.equal(s.state.nickname,'新昵称');assert.equal(s.calls.profile,1);assert.equal(s.calls.restore,1)
})

test('actual My component lifecycle reuses its loaded family and exposes working manual retry',async()=>{
  const source=readFileSync(new URL('../src/components/CloudMyProfile.vue',import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
  const hooks={},cache={entry:null};let reads=0,restores=0,local=null
  const account={token:'synthetic',householdId:'family-a',accountName:'合成用户'}
  const deps={ref,reactive,computed,
    onMounted:fn=>hooks.mount=fn,onShow:fn=>hooks.show=fn,onHide:fn=>hooks.hide=fn,onUnmounted:fn=>hooks.dispose=fn,
    createMyProfileLoader:options=>createMyProfileLoader({...options,cache}),getSession:()=>account,
    storageContext:()=> 'account-a:family-a:r1',scopedStorage:{getStorageSync:()=>local},
    loadCloudProfile:async()=>{reads++;local={...profile(),revision:Date.now()};return local},
    wechatAuth:{restore:async()=>{restores++;return account}},accountSettings:{profile:async()=>({avatar:'',nickname:'新昵称'})},
    isCommerceEnabled:true,uni:{reLaunch:()=>{throw Error('unexpected login redirect')}}}
  const page=new Function('deps',`const {${Object.keys(deps)}}=deps;${source};return {profile,busy,name,retry,planItems}`)(deps)
  const mounted=hooks.mount();hooks.show();await mounted
  assert.equal(page.profile.value.memberCount,1);assert.equal(page.name.value,'新昵称')
  assert.equal(page.planItems.find(item=>item.name==='我的餐单').url,'/pages/health/plans?archive=1')
  hooks.hide();assert.equal(page.profile.value.memberCount,1)
  hooks.show();await flush();assert.equal(reads,1);assert.equal(restores,1)
  await page.retry();assert.equal(reads,2);assert.equal(page.busy.value,false)
  hooks.dispose()
})
