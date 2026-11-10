import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {ref,computed,watch} from 'vue'
import {dishTitle,recipeDisplay,ingredientLabels,referenceIngredientLabel,referenceGapDetail} from '../src/utils/meal-presentation.js'
import {referenceSelection,isReferencePlan,isMealPlanCandidates} from '../src/services/reference-meal-plan.js'
import {mealCandidates} from './fixtures/meal-candidates.mjs'
import {chatMessages} from '../src/services/cloud-chat.js'
import {sourceTitle} from '../src/utils/ai-answer.js'

const profile={householdId:'family',selfMemberId:'self',members:[{id:'self',healthMemberId:'health-self'},{id:'mother',healthMemberId:'health-mother'}]}
const dates={today:'2026-10-26',tomorrow:'2026-10-27'}

test('source-based candidates retain their date, breakfast, restrictions and material gaps without becoming a saved daily plan',()=>{
 const data=mealCandidates('2026-10-27')
 assert.equal(isMealPlanCandidates(data),true);assert.equal(isReferencePlan(data),false)
 const [message]=chatMessages({history:[{id:1,type:'ai',content:JSON.stringify(data),recorded_meals:[{id:'not-a-candidate-receipt'}],request_id:'original'}]})
 assert.equal(message.business.kind,'meal_plan_candidates');assert.deepEqual(message.business.data,data)
 assert.equal(message.planDate,undefined);assert.equal(message.planMeals,undefined);assert.equal(message.purchaseRequestId,'')
 assert.deepEqual(message.recordedMeals,[]);assert.match(message.text,/待核对候选.*尚未确认/)
})

test('candidate identifiers cannot be repeated across different meals',()=>{
 const data=mealCandidates('2026-10-27','self',['breakfast','lunch'])
 assert.equal(isMealPlanCandidates(data),true)
 data.meals[1].dishes[0].id=data.meals[0].dishes[0].id
 data.candidate_selection[1].candidate_ids=[data.meals[0].dishes[0].id]
 assert.equal(isMealPlanCandidates(data),false)
})

for(const change of [data=>data.status='reference_ready',data=>data.scope='daily_reference',data=>data.purchase_allowed=true,
 data=>data.purchase_items.push({sku_id:'unsafe'}),data=>data.preview_id='unsafe',data=>data.plan_id='unsafe',
 data=>data.purchase_ready=true,data=>data.approval_status='approved',data=>data.restriction_verification.status='verified',
 data=>data.meals[0].dishes[0].source.kind='verbatim',data=>data.meals[0].dishes[0].source.content_hash='',
 data=>data.meals[0].dishes[0].steps=[],data=>data.selection.plan_date='2026-11-01',data=>data.meals={},
 data=>delete data.selection,data=>delete data.restriction_verification,
 data=>data.result_type='meal_plan_candidates',data=>data.meals[0].dishes[0].source.url='http://example.com/rice',
 data=>data.members=[null],data=>data.members[0].id='other-member',data=>data.restriction_verification.restrictions[0].member_id='other-member',
 data=>data.selection.meal_types=['breakfast','lunch']]){
 test('a candidate with an unverified identity or readiness claim fails closed: '+change.toString(),()=>{
  const data=mealCandidates();change(data);assert.equal(isMealPlanCandidates(data),false)
  const [message]=chatMessages({history:[{id:1,type:'ai',content:JSON.stringify(data)}]})
  assert.equal(message.business,null);assert.equal(message.planDate,undefined);assert.equal(message.purchaseRequestId,'')
  assert.match(message.text,/无法核对/)
 })
}

test('the rendered candidate card shows complete cooking notes and source text with no save, purchase or navigation control',async()=>{
 const {compile,createSSRApp}=await import('vue'),{renderToString}=await import('vue/server-renderer')
 const source=readFileSync(new URL('../src/components/HealthChatBusinessCard.vue',import.meta.url),'utf8')
 const template=source.slice(source.indexOf('<template>')+10,source.lastIndexOf('</template>'))
 const data=mealCandidates('2026-10-27'),result={type:'business',kind:'meal_plan_candidates',data}
 const calls=[],props={result,memberId:'self'},deps={ref,defineProps:()=>props,defineEmits:()=>()=>{},
  onUnmounted(){},storageContext:()=> 'scope',scopedStorage:{getStorageSync:()=>null,setStorageSync:()=>calls.push('storage')},request:()=>calls.push('request'),uni:{navigateTo:()=>calls.push('navigate')}}
 const script=source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
 const card=new Function('deps',`const {${Object.keys(deps)}}=deps;${script};return {save,inspect,sourceDetails,toggleSourceDetails,names,busy,error,saved}`)(deps)
 const render=compile(template),html=await renderToString(createSSRApp({render,setup:()=>({...card,result:props.result})}))
 for(const value of ['2026-10-27','早餐','待核对候选','非逐字原文','个人适用性尚未确认','未保存为每日餐单','暂不提供采购',data.notice,
  ...data.unresolved_materials,...data.meals[0].dishes[0].ingredients,...data.meals[0].dishes[0].steps,
  data.meals[0].dishes[0].source.title,data.meals[0].dishes[0].source.url,'合成限制仍需核对'])assert.ok(html.includes(value),value)
 assert.doesNotMatch(html,/<navigator|<a\b|确认这些商品|保存这份餐单|已保存餐单/)
 assert.equal(html.includes(data.meals[0].dishes[0].source.notes),false);assert.match(html,/aria-expanded="false"/)
 card.toggleSourceDetails(data.meals[0].dishes[0].id)
 const expanded=await renderToString(createSSRApp({render,setup:()=>({...card,result:props.result})}))
 assert.ok(expanded.includes(data.meals[0].dishes[0].source.notes));assert.match(expanded,/aria-expanded="true"/)
 card.toggleSourceDetails(data.meals[0].dishes[0].id)
 const collapsed=await renderToString(createSSRApp({render,setup:()=>({...card,result:props.result})}))
 assert.equal(collapsed.includes(data.meals[0].dishes[0].source.notes),false)
 props.result={...result,data:{...data,preview_id:'cannot-save',plan_id:'cannot-open'}}
 await card.save();card.inspect();assert.deepEqual(calls,[])
})
test('reference choice preserves requested meal set, date and actor scope',()=>{
 assert.deepEqual(referenceSelection(profile,'全家明天的早餐和午餐',dates),{mode:'reference',family_id:'family',plan_date:'2026-10-27',participant_ids:['mother','self'],meal_types:['breakfast','lunch']})
 assert.deepEqual(referenceSelection(profile,'今天晚餐',{...dates,memberId:'health-mother'}).participant_ids,['mother'])
 assert.throws(()=>referenceSelection(profile,'后天三餐',dates),/原问题已保留/)
 assert.throws(()=>referenceSelection(profile,'今天三餐',{...dates,memberId:'inaccessible'}),/成员/)
})
test('an unspecified personal request uses the current profile rather than all default diners',()=>{
 const family={...profile,defaultDiners:['self','mother']}
 assert.deepEqual(referenceSelection(family,'为我配餐',dates).participant_ids,['self'])
 assert.deepEqual(referenceSelection(family,'按家庭档案为我配餐',dates).participant_ids,['self'])
 assert.deepEqual(referenceSelection(family,'今天怎么吃',dates).participant_ids,['self'])
 assert.deepEqual(referenceSelection(family,'今天怎么吃',{...dates,memberId:'health-mother'}).participant_ids,['mother'])
 const named={...family,members:[...family.members,{id:'father',healthMemberId:'health-father',relation:'父亲'}]}
 for(const text of ['给我父亲配餐','为我的父亲配餐','帮我的父亲安排今天晚餐'])assert.deepEqual(referenceSelection(named,text,dates).participant_ids,['father'],text)
})

test('colloquial meal and date names preserve an explicit single meal across a month boundary',()=>{
 const monthEnd={today:'2026-10-31',tomorrow:'2026-11-01'}
 for(const [text,date,meal] of [['安排明早早饭','2026-11-01','breakfast'],['安排明晚晚饭','2026-11-01','dinner'],['安排今天午饭','2026-10-31','lunch']]){
  assert.deepEqual(referenceSelection(profile,text,monthEnd),{mode:'reference',family_id:'family',plan_date:date,participant_ids:['self'],meal_types:[meal]})
 }
})

test('a revision retains the existing date, members and meal scope unless the user explicitly changes them',()=>{
 const previous=referenceSelection(profile,'全家明天三餐',dates)
 for(const text of ['把这个餐单换一下','这个食谱改成粥']){
  assert.deepEqual(referenceSelection(profile,text,{...dates,previous}),previous,text)
 }
 for(const text of ['把早餐改成粥','早餐换成不含鸡蛋的']){
  assert.deepEqual(referenceSelection(profile,text,{...dates,previous}),{...previous,meal_types:['breakfast']},text)
 }
 assert.equal(referenceSelection(profile,'今天早餐改成粥',{...dates,previous}).plan_date,dates.today)
 assert.deepEqual(referenceSelection(profile,'只给我改一下',{...dates,previous}).participant_ids,['self'])
 assert.throws(()=>referenceSelection(profile,'改一下',{...dates,previous:{...previous,family_id:'other-family'}}),/成员资料已变化/)
 assert.throws(()=>referenceSelection(profile,'后天改成粥',{...dates,previous}),/今天或明天/)
 for(const text of ['晚餐换成清淡一点，早餐和午餐不变','只改晚餐，早餐和午餐保持原样','早餐不要改，午餐照旧，晚餐换一下'])assert.deepEqual(referenceSelection(profile,text,{...dates,previous}).meal_types,['dinner'],text)
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
 const deps={ref,computed,watch,ingredientLabels,defineEmits:()=>()=>{},defineProps:()=>props,onUnmounted:fn=>hooks.unmount=fn,storageContext:()=>scope,
  request:async options=>{if(!options.method)return {data:props.plan};calls.push('publish');return {data:{preview_id:'preview',package:{package_sn:'package',package_version:version}}}},
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
 const routes=[...pages.pages.map(p=>p.path),...(pages.subPackages||pages.subpackages||[]).flatMap(group=>group.pages.map(p=>group.root.replace(/\/$/,'')+'/'+p.path))]
 const destination=h.calls.at(-1)[1],path=destination.slice(1).split('?')[0]
 assert.equal(routes.filter(route=>route===path).length,1,'the actual purchase destination must be registered exactly once, including subpackages')
 assert.ok(readFileSync(new URL('../src/'+path+'.vue',import.meta.url),'utf8').includes('CommerceShop'))
 assert.equal(new URLSearchParams(destination.split('?')[1]).get('cart'),'1')
})
for(const options of [{scopeChange:true},{planChange:true}])test('changed account or preview cancels purchase before writing a package',async()=>{
 const h=card(options);await h.page.purchase();assert.deepEqual(h.calls,[])
})
test('unavailable reference product cannot be added to cart',async()=>{
 const h=card({available:false});await h.page.purchase();assert.match(h.page.error.value,/重新生成/)
 assert.ok(!h.calls.some(c=>Array.isArray(c)&&c[0]==='cart'))
})


test('rendered reference card hides incomplete historical menus and permits verified results',async()=>{
 const {compile,createSSRApp}=await import('vue')
 const {renderToString}=await import('vue/server-renderer')
 const template=readFileSync(new URL('../src/components/ReferenceMealPlanCard.vue',import.meta.url),'utf8').match(/<template>([\s\S]*?)<\/template>\s*<style/)[1]
 const render=compile(template)
 async function html(plan,detailMode=false){return renderToString(createSSRApp({render,setup:()=>({plan,purchaseComplete:plan.purchase_ready===true||plan.purchase_validation_version===1,sourceTitle,dishTitle,recipeDisplay,referenceIngredientLabel,referenceGapDetail,labels:ingredientLabels((plan.meals||[]).flatMap(m=>m.dishes||[])),detailMode,displayError:'',names:{breakfast:'早餐'},gapNames:{not_sold:'自行准备'},expanded:false,busy:false,error:'',emit(){},purchase(){}})}))}
 const old={meals:[{meal_type:'breakfast',dishes:[{name:'未配齐的菜',ingredients:[]}]}],purchase_items:[{sku_id:'56',product_name:'富硒鸡蛋',quantity:1}],purchase_gaps:[{ingredient:'盐',reason:'no_match'}]}
 const unavailable=await html(old)
 assert.match(unavailable,/需要重新安排/)
 assert.doesNotMatch(unavailable,/未配齐的菜|富硒鸡蛋|确认这些商品/)
 const ready=await html({purchase_ready:true,meals:[],purchase_items:[{sku_id:'56',product_name:'富硒鸡蛋',sku_name:'10枚',quantity:1}],purchase_gaps:[]})
 assert.match(ready,/富硒鸡蛋/);assert.match(ready,/确认这些商品并加入购物车/)
 assert.match(await html({meals:[],purchase_items:[]}),/需要重新安排/)
 const productDetail=await html({purchase_ready:true,meals:[],product_matches:[{product_id:'egg',product_name:'富硒鸡蛋',skus:[{sku_id:'egg-6'}]}],purchase_items:[],purchase_gaps:[]},true)
 assert.match(productDetail,/选择规格后购买/);assert.doesNotMatch(productDetail,/未记录采购商品/)
})

test('reference self-purchase gaps show no price and never become cart products',()=>{
 const source=readFileSync(new URL('../src/components/ReferenceMealPlanCard.vue',import.meta.url),'utf8')
 assert.match(source,/no_match:'自行购买 · 暂无价格'/)
 assert.match(source,/needs_confirmation:'自行购买 · 暂无价格'/)
 assert.doesNotMatch(source,/purchase_gaps[^\n]+confirm.*cart/i)
})
