import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {ref} from 'vue'
import {referenceSelection,isReferencePlan} from '../src/services/reference-meal-plan.js'
import {chatMessages} from '../src/services/cloud-chat.js'

const profile={householdId:'family',selfMemberId:'self',members:[{id:'self',healthMemberId:'health-self'},{id:'mother',healthMemberId:'health-mother'}]}
const dates={today:'2026-10-26',tomorrow:'2026-10-27'}
test('reference choice preserves requested meal set, date and actor scope',()=>{
 assert.deepEqual(referenceSelection(profile,'全家明天的早餐和午餐',dates),{mode:'reference',family_id:'family',plan_date:'2026-10-27',participant_ids:['mother','self'],meal_types:['breakfast','lunch']})
 assert.deepEqual(referenceSelection(profile,'今天晚餐',{...dates,memberId:'health-mother'}).participant_ids,['mother'])
 assert.throws(()=>referenceSelection(profile,'后天三餐',dates),/原问题已保留/)
 assert.throws(()=>referenceSelection(profile,'今天三餐',{...dates,memberId:'inaccessible'}),/成员/)
})
test('reference boundary cannot be promoted into an approved result by display',()=>{
 const plan={scope:'daily_reference',status:'reference_ready',professional_status:'not_reviewed',nutrition_status:'not_calculated',preview_id:'preview',meals:[{}]}
 assert.ok(isReferencePlan(plan))
 assert.equal(isReferencePlan({...plan,nutrition_status:'passed'}),false)
 assert.equal(isReferencePlan({...plan,professional_status:'approved'}),false)
})
test('reference followup questions restore as readable text after reopening',()=>{
 const [message]=chatMessages({history:[{id:1,type:'assistant',content:JSON.stringify({status:'needs_input',questions:['早餐需要几人食用？']})}]})
 assert.equal(message.text,'早餐需要几人食用？');assert.equal(message.business,null)
})
function card({scopeChange=false,planChange=false,version=2,available=true}={}){
 const calls=[],props={plan:{preview_id:'preview'}},hooks={};let scope='A'
 const deps={ref,defineProps:()=>props,onUnmounted:fn=>hooks.unmount=fn,storageContext:()=>scope,
  request:async()=>{calls.push('publish');return {data:{preview_id:'preview',package:{package_sn:'package',package_version:version}}}},
  commerce:{connect:async()=>{if(scopeChange)scope='B';if(planChange)props.plan={preview_id:'new-preview'}},mealPackage:async(sn,v)=>{calls.push(['read',sn,v]);return {package_sn:sn,package_version:v,scope:'daily_reference',available}},addMeal:async menu=>calls.push(['cart',menu.package_version])},
  uni:{navigateTo:o=>calls.push(['route',o.url])}}
 const source=readFileSync(new URL('../src/components/ReferenceMealPlanCard.vue',import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
 const page=new Function('deps',`const {${Object.keys(deps).join(',')}}=deps;${source};return {purchase,error}`)(deps)
 return {page,calls,hooks}
}
test('explicit reference purchase uses returned package version and actual cart route',async()=>{
 const h=card();await h.page.purchase()
 assert.deepEqual(h.calls,['publish',['read','package',2],['cart',2],['route','/pages/shop/index?commerce=1&cart=1']])
 const pages=JSON.parse(readFileSync(new URL('../src/pages.json',import.meta.url)))
 assert.ok(pages.pages.some(p=>p.path==='pages/shop/index'))
})
for(const options of [{scopeChange:true},{planChange:true}])test('changed account or preview cancels purchase before writing a package',async()=>{
 const h=card(options);await h.page.purchase();assert.deepEqual(h.calls,[])
})
test('unavailable reference product cannot be added to cart',async()=>{
 const h=card({available:false});await h.page.purchase();assert.match(h.page.error.value,/重新生成/)
 assert.ok(!h.calls.some(c=>Array.isArray(c)&&c[0]==='cart'))
})


test('rendered reference card explains partial selection and distinguishes historical empty results',async()=>{
 const {compile,createSSRApp}=await import('vue')
 const {renderToString}=await import('vue/server-renderer')
 const template=readFileSync(new URL('../src/components/ReferenceMealPlanCard.vue',import.meta.url),'utf8').match(/<template>([\s\S]*?)<\/template>\s*<style/)[1]
 const render=compile(template)
 async function html(plan){return renderToString(createSSRApp({render,setup:()=>({plan,names:{breakfast:'早餐'},gapNames:{not_sold:'自行准备'},expanded:false,busy:false,error:'',purchase(){}})}))}
 const partial=await html({meals:[],purchase_items:[{sku_id:'56',product_name:'富硒鸡蛋',sku_name:'10枚',quantity:1,ingredient_refs:['鸡蛋1个']}],purchase_gaps:[{ingredient:'水适量',reason:'not_sold',detail:'饮用水自行准备'}]})
 assert.match(partial,/富硒鸡蛋/);assert.match(partial,/用于：鸡蛋1个/);assert.match(partial,/饮用水自行准备/)
 assert.match(partial,/确认这些商品并加入购物车/)
 const empty=await html({meals:[],purchase_items:[],purchase_gaps:[{ingredient:'水适量',reason:'not_sold',detail:'饮用水自行准备'}]})
 assert.match(empty,/本次未选定采购商品，原因见下方/);assert.doesNotMatch(empty,/确认这些商品并加入购物车/)
 assert.match(await html({meals:[],purchase_items:[]}),/这份餐单未记录采购商品及原因/)
})
