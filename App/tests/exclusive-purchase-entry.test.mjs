import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {ref,computed,reactive,watch} from 'vue'
import {createExclusivePlanBrowser,exclusiveBrowseState} from '../src/services/exclusive-plan-browser.js'

function page({purchase=true,denied=false}={}) {
  const calls=[],hooks={}
  let current=true
  const receipt={tier_name:'经济型',members:[{display_alias:'合成成员'}],scope_hash:'scope',available:true,items:[],gaps:[]}
  const deps={ref,computed,reactive,watch,exclusiveBrowseState,createExclusivePlanBrowser:options=>createExclusivePlanBrowser({...options,later:()=>null}),storageContext:()=> 'family',onLoad:fn=>hooks.load=fn,onShow:()=>{},onHide:()=>{},onUnload:()=>{},
    getSession:()=>({householdId:'family'}),sessionRevision:()=>1,planTiers:['economy','standard','premium'],
    createExclusiveImageFlow:()=>({stop(){},open(){},retry(){}}),exclusiveImages(){},recipeCover(){},
    selectedDay:()=>null,dayMeals:()=>[],validPlanRoute:()=>({sn:'legacy',version:1}),commerce:{},
    useCommercePage:()=>({busy:ref(false),error:ref(''),run:async work=>work(()=>current)}),
    request:async input=>{
      calls.push(input);if(denied)throw new Error('授权已撤回')
      if(input.path.endsWith('/directory'))return {data:{tier_name:'经济型',days:Array.from({length:7},(_,i)=>({day_no:i+1,available:true}))}}
      if(input.path.endsWith('/days/1'))return {data:{day_no:1,version:'v1',day:{day_no:1,meals:[]}}}
      return {data:receipt}
    },
    readExclusivePreview:async()=>{calls.push('preview');return {days:[],tier_name:'计划详情'}},
  }
  const source=readFileSync(new URL('../src/pages/exclusive-plans/detail.vue',import.meta.url),'utf8')
    .match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
  const instance=new Function('deps',`const {${Object.keys(deps).join(',')}}=deps;${source};return {load,plan,purchaseData,purchaseReference}`)(deps)
  hooks.load({group_id:'group',tier:'economy',purchase:purchase?'1':'0'})
  return {...instance,calls,receipt,deny(){denied=true},invalidate(){current=false}}
}

test('purchase entry reads a single receipt and renders server plan metadata',async()=>{
  const p=page();await p.load()
  assert.equal(p.calls.length,1)
  assert.match(p.calls[0].path,/\/tiers\/economy\/purchase$/)
  assert.equal(p.plan.value.tier_name,p.receipt.tier_name)
  assert.deepEqual(p.plan.value.members,p.receipt.members)
  assert.deepEqual(p.purchaseData.value,p.receipt)
})
test('ordinary detail reads the directory and only the selected day',async()=>{
  const p=page({purchase:false});await p.load()
  assert.equal(p.calls.length,2);assert.match(p.calls[0].path,/\/directory$/);assert.match(p.calls[1].path,/\/days\/1$/)
  assert.equal(p.purchaseData.value,null)
})

test('exclusive purchase passes current trade facts and original package count to the purchase component',async()=>{
  const p=page()
  p.receipt.items=[{sku_id:'rice',quantity:5,sku:{product_id:'rice-product',product_name:'合成大米',sku_name:'500g',price_cent:500,available_quantity:8,sale_status:'available',image_url:'/rice.png'}}]
  await p.load()
  const item=p.purchaseReference.value.items[0]
  assert.equal(item.quantity,5)
  assert.equal(item.price_cent,500)
  assert.equal(item.available_quantity,8)
  assert.equal(item.sale_status,'available')
  assert.equal(item.product_id,'rice-product')
})
test('invalidated and denied procurement responses cannot populate the page',async()=>{
  const stale=page();stale.invalidate();await stale.load()
  assert.equal(stale.plan.value,null);assert.equal(stale.purchaseData.value,null)
  const denied=page({denied:true});await assert.rejects(denied.load(),/授权已撤回/)
  assert.equal(denied.plan.value,null);assert.equal(denied.purchaseData.value,null)
})


test('refresh keeps editor mounted but access failure clears old receipt',async()=>{
 const p=page();await p.load();const values=[]
 const stop=watch(p.purchaseData,v=>values.push(v),{flush:'sync'});await p.load();stop()
 assert.equal(values.includes(null),false);p.deny();await assert.rejects(p.load(),/授权已撤回/)
 assert.equal(p.purchaseData.value,null);assert.equal(p.plan.value,null)
})
