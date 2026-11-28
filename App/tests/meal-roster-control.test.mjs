import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {ref,computed} from 'vue'
function fixture(send=async()=>({data:{}})){
 const source=readFileSync(new URL('../src/components/MealRosterControl.vue',import.meta.url),'utf8').split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm,'')
 const calls=[],events=[];let owner='account'
 const props={familyId:'f',members:[{id:'a',name:'我'},{id:'b',name:'李女士'}],plan:{date:'2026-11-24',version:3,roster:{breakfast:{execution_locked:true}},meals:['breakfast','lunch','dinner'].map(meal_type=>({meal_type,members:[{id:'a',name:'我'}]}))}}
 const deps={ref,computed,defineProps:()=>props,defineEmits:()=> (...args)=>events.push(args),request:async data=>{calls.push(data);return send(data)},storageContext:()=>owner,newHealthRequestId:()=> 'request'}
 const view=new Function('deps',`const {${Object.keys(deps)}}=deps;${source};return {open,choose,toggle,confirm,opened,selected,targets,summary,error,saving}`)(deps)
 return {view,props,calls,events,setOwner:v=>owner=v}
}
test('top-level roster selects all uneaten meals and submits the newly selected relative',async()=>{
 const h=fixture();h.view.open();h.view.toggle('b');await h.view.confirm()
 assert.deepEqual(h.calls[0].data,{client_request_id:'request',version:3,meal_types:['lunch','dinner'],member_ids:['a','b'],consumed:false})
 assert.deepEqual(h.events,[['close'],['updated']]);assert.equal(h.view.opened.value,false)
})
test('single meal adjustment only updates members and keeps consumption unchanged',async()=>{
 const h=fixture();h.view.open();h.view.choose('lunch');h.view.toggle('b');await h.view.confirm()
 assert.deepEqual(h.calls[0].data.meal_types,['lunch']);assert.equal(h.calls[0].data.consumed,false);assert.deepEqual(h.calls[0].data.member_ids,['a','b'])
})
test('failed save remains open with a visible error and does not emit success',async()=>{
 const h=fixture(async()=>{throw Error('版本已变化')});h.view.open();await h.view.confirm()
 assert.equal(h.view.opened.value,true);assert.equal(h.view.error.value,'版本已变化');assert.deepEqual(h.events,[])
})
test('late response from a previous account never updates the new account',async()=>{
 let resolve;const h=fixture(()=>new Promise(r=>resolve=r));h.view.open();const pending=h.view.confirm();h.setOwner('other');resolve({data:{}});await pending;assert.deepEqual(h.events,[])
})

test('all-day changes exclude missing meals',async()=>{
 const h=fixture();h.props.plan.meals=h.props.plan.meals.filter(m=>m.meal_type==='lunch');h.view.open();await h.view.confirm();assert.deepEqual(h.calls[0].data.meal_types,['lunch'])
})


test('legacy consumed marker alone never locks a meal',()=>{
 const h=fixture();h.props.plan.roster={breakfast:{consumed_at:'legacy'}};h.view.open()
 assert.deepEqual(h.view.targets.value,['breakfast','lunch','dinner'])
})
test('removed household members cannot be counted or submitted',async()=>{
 const h=fixture();h.props.plan.meals.forEach(m=>m.members.push({id:'removed',name:'已移出'}));h.view.open();await h.view.confirm()
 assert.deepEqual(h.calls[0].data.member_ids,['a'])
})
test('external entry only asks the stable owner to open the panel',()=>{
 const h=fixture();h.props.entryOnly=true;h.view.open()
 assert.equal(h.view.opened.value,false);assert.deepEqual(h.events,[['open']])
})

test('a changed plan cannot silently submit an old selection at its new version',async()=>{
 const h=fixture();h.view.open();h.props.plan.version=4;await h.view.confirm()
 assert.equal(h.calls[0].data.version,3)
})
