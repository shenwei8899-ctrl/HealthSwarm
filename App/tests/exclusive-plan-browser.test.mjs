import test from 'node:test'
import assert from 'node:assert/strict'
import {reactive,nextTick} from 'vue'
import {createExclusivePlanBrowser,exclusiveBrowseState} from '../src/services/exclusive-plan-browser.js'
const target={familyId:'family',groupId:'group',tier:'standard'}
function harness(){
 let account='A',fail=null,release=null
 const calls=[],scheduled=[],state=reactive(exclusiveBrowseState())
 const directory={version:'root',days:Array.from({length:7},(_,i)=>({day_no:i+1,plan_date:'2026-11-'+String(i+1).padStart(2,'0'),available:true,content_version:'content',version:'source'}))}
 const browser=createExclusivePlanBrowser({state,scope:()=>account,later:fn=>{scheduled.push(fn);return scheduled.length},cancelLater:()=>{},send:async request=>{
  calls.push(request.path)
  if(fail)throw fail
  if(request.path.endsWith('/directory'))return {data:structuredClone(directory)}
  const no=Number(request.path.match(/days\/(\d+)/)[1]);if(release)return new Promise(resolve=>release.push([no,resolve]))
  return {data:{day_no:no,version:'version-'+no,unchanged:request.path.includes('known_version'),day:{day_no:no,meals:[{recipe_name:'当天菜'+no}]}}}
 }})
 return {state,browser,calls,scheduled,directory,changeAccount:a=>account=a,fail:e=>fail=e,delay:()=>release=[],get delayed(){return release}}
}
test('first entry fetches directory and one day; prefetch is one lower-priority next day',async()=>{
 const h=harness();await h.browser.open(target);assert.equal(h.calls.length,2);assert.ok(h.calls[1].endsWith('/days/1'));assert.equal(h.state.days[2],undefined)
 h.scheduled.shift()();await new Promise(r=>setImmediate(r));assert.equal(h.calls.length,3);assert.equal(h.scheduled.length,0);assert.equal(h.state.days[2].data.day_no,2)
})
test('return retains visible content, selected day and conditional read; reactive data updates the UI',async()=>{
 const h=harness();await h.browser.open(target);await h.browser.select(4);await nextTick();const previous=h.state.days[4].data
 h.browser.hide();assert.equal(h.state.days[4].data,previous);assert.equal(h.browser.ready(),false)
 await h.browser.open(target);assert.equal(h.state.selected,4);assert.equal(h.state.days[4].data,previous);assert.ok(h.calls.at(-1).includes('/days/4?known_version='));assert.equal(h.browser.ready(),true)
})
test('late response cannot replace the selected day and prefetch does not recursively fetch all days',async()=>{
 const h=harness();await h.browser.open(target);h.delay();const second=h.browser.select(2);await Promise.resolve();const third=h.browser.select(3);await Promise.resolve()
 const answer=no=>h.delayed.find(x=>x[0]===no)[1]({data:{day_no:no,version:'v'+no,unchanged:false,day:{day_no:no,meals:[]}}})
 answer(3);await third;answer(2);await second;assert.equal(h.state.selected,3);assert.equal(h.state.days[3].data.day_no,3)
})
test('only changed date is invalidated while unaffected cached day remains',async()=>{
 const h=harness();await h.browser.open(target);await h.browser.select(3);const old=h.state.days[1].data
 h.directory.days[2].available=false;await h.browser.open(target);assert.equal(h.state.days[3].data,null);assert.equal(h.state.days[1].data,old);assert.equal(h.browser.ready(),false)
})
test('permission loss and account switch cannot reuse private cached content',async()=>{
 const h=harness();await h.browser.open(target);h.fail(Object.assign(Error('撤权'),{code:403}));await h.browser.open(target);assert.equal(h.state.directory,null);assert.deepEqual(h.state.days,{})
 const k=harness();await k.browser.open(target);k.changeAccount('B');await k.browser.select(2);assert.equal(k.state.directory,null)
})
test('one day failure leaves directory and other days intact',async()=>{
 const h=harness();await h.browser.open(target);h.fail(Object.assign(Error('暂不可用'),{code:503}));await h.browser.select(2);assert.ok(h.state.directory);assert.ok(h.state.days[1].data);assert.match(h.state.days[2].error,/暂不可用/)
})

test('unchanged response without cached body cannot authorize purchase',async()=>{
 const state=reactive(exclusiveBrowseState()),directory={days:Array.from({length:7},(_,i)=>({day_no:i+1,available:true}))}
 const browser=createExclusivePlanBrowser({state,scope:()=> 'A',send:async({path})=>({data:path.endsWith('/directory')?directory:{day_no:1,version:'v1',unchanged:true}})})
 await browser.open(target)
 assert.equal(browser.ready(),false);assert.equal(state.days[1].data,null);assert.match(state.days[1].error,/返回不完整/)
})

test('whole-plan basis change discovered by a day read clears every cached day',async()=>{
 const h=harness();await h.browser.open(target);await h.browser.select(2)
 h.fail(Object.assign(Error('成员资料变化'),{code:410,businessCode:'plan_basis_changed'}));await h.browser.select(3)
 assert.equal(h.state.directory,null);assert.deepEqual(h.state.days,{});assert.equal(h.browser.ready(),false)
})

test('source failure clears its conditional version so recovery fetches a body',async()=>{
 const h=harness();await h.browser.open(target)
 h.fail(Object.assign(Error('来源变化'),{code:410}));await h.browser.select(1)
 assert.equal(h.state.days[1].data,null);assert.equal(h.state.days[1].version,null)
 h.fail(null);await h.browser.retry();assert.ok(h.calls.at(-1).endsWith('/days/1'));assert.equal(h.browser.ready(),true)
})
