import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {normalizeProfile,saveProfile,getProfile} from '../src/utils/profile.js'
import {createPlan,subtotal} from '../src/utils/demo.js'
import {ingredientConflicts} from '../src/utils/health.js'
import {getDishSwapOptions,saveMealSwap} from '../src/utils/meal-customization.js'
import {todayPlan,setMealMembers,saveSelection,selectedFor,mergeDailyProducts,localDate,saveTomorrowProposal} from '../src/utils/meal-state.js'
import {createCookingGuide,createDishGuide} from '../src/utils/meal-flow.js'
import {createDemoOrder,getOrder} from '../src/utils/orders.js'
import {adaptExclusivePlan,getExclusivePlan,createDeliveryBatches,regenerateExclusivePlans} from '../src/utils/exclusive-plans.js'
import {createInvite,acceptInvite} from '../src/utils/invitations.js'
import {remember,forget,editMemory} from '../src/utils/memory.js'
test('family overview omits bottom navigation and its reserved space while preserving page actions',()=>{
  const source=readFileSync(new URL('../src/pages/profile/index.vue',import.meta.url),'utf8')
  assert.ok(!source.includes('bottom-nav'))
  assert.ok(!source.includes('padding-bottom:150rpx'))
  for(const action of ['@click="backHome"','@click="share"','@click="detail(m)"','@click="add"']) assert.ok(source.includes(action))
})
test('community entry is a tool chip immediately after today plan and keeps its popup action',()=>{
  const source=readFileSync(new URL('../src/pages/chat/index.vue',import.meta.url),'utf8')
  const strip=source.match(/<view class="tool-row">([\s\S]*?)<\/scroll-view>/)[1]
  const entries=[...strip.matchAll(/<button\b[^>]*class="[^"]*tool-chip[^\"]*"[^>]*>[\s\S]*?<\/button>/g)].map(match=>match[0])
  assert.equal(entries.length,5)
  assert.match(entries[3],/今日饮食计划/)
  assert.match(entries[4],/加入社群/)
  assert.match(entries[4],/@click="communityOpen=true"/)
  assert.ok(!source.includes('<button class="community-entry"'))
  assert.ok(source.includes('v-if="communityOpen"'))
  assert.match(source,/\.tool-chip,\.tool-divider\s*\{\s*flex-shrink:\s*0;/)
})
const setup=()=>{const storage=new Map();globalThis.uni={getStorageSync:k=>storage.get(k),setStorageSync:(k,v)=>storage.set(k,JSON.parse(JSON.stringify(v)))};return normalizeProfile({members:[{id:1,name:'我',age:28,relation:'本人',healthStatus:'none',allergyStatus:'none',intoleranceStatus:'none',avoidanceStatus:'none',doctorStatus:'none'},{id:2,name:'妈妈',age:55,healthStatus:'set',conditions:['高血压'],allergyStatus:'none',intoleranceStatus:'none',avoidanceStatus:'none',doctorStatus:'none'},{id:3,name:'爸爸',age:58,healthStatus:'set',conditions:['糖尿病'],allergyStatus:'set',allergies:['鱼类'],intoleranceStatus:'set',intolerances:['大豆不耐受'],avoidanceStatus:'none',doctorStatus:'none'}],defaultDiners:[1,2]})}
test('applicable members, not everyone, drive three-meal safety and cancellation state',()=>{const p=setup();saveProfile(p);const before=todayPlan(p,'晚餐');assert.ok(before.dishes.some(d=>d.name==='清蒸鲈鱼'));setMealMembers(p,'晚餐',[1,3]);const after=todayPlan(p,'晚餐');assert.ok(!after.dishes.some(d=>/鱼|豆腐/.test(d.name)));assert.equal(after.blocked.length,0);assert.equal(todayPlan(p,'早餐').count,2);assert.deepEqual(todayPlan(p,'早餐').members.map(m=>m.id),[1,2]);assert.deepEqual(after.members.map(m=>m.id),[1,3])})
test('unchecking a product never bypasses recipe safety, swap count filters restrictions',()=>{const p=setup();assert.equal(getDishSwapOptions('晚餐','清蒸鲈鱼',p.members).length,0);assert.equal(getDishSwapOptions('晚餐','清蒸鲈鱼',[p.members[2]]).length,0);assert.equal(getDishSwapOptions('晚餐','清蒸鲈鱼',[{...p.members[0],allergyStatus:'set',allergies:['含甲壳类']}]).length,2);assert.ok(ingredientConflicts([p.members[2]],['鲜鲈鱼']).length)})
test('SKU boundary, not linear diner pricing; preserving deselection across recomputation',()=>{const p=setup();const two=createPlan(p);saveSelection('晚餐',two.products,two.products.filter(x=>x.id!==6).map(x=>x.id));setMealMembers(p,'晚餐',[1,2,3]);const three=todayPlan(p,'晚餐');assert.ok(!selectedFor('晚餐',three.products).includes(6));assert.ok(selectedFor('晚餐',three.products).includes(20));const q=setup();q.defaultDiners=[1];const one=createPlan(q);q.defaultDiners=[1,2];const pair=createPlan(q);assert.equal(one.products.find(p=>p.id===1).quantity,pair.products.find(p=>p.id===1).quantity);assert.equal(subtotal(one.products,[1]),subtotal(pair.products,[1]))})
test('daily procurement sums demands before rounding packaging and respects excluded selections',()=>{setup();const p={id:4,pack:500,unit:'g',priceCents:790,need:200};const plans=[{meal:'午餐',products:[p]},{meal:'晚餐',products:[{...p,need:200}]}];assert.equal(mergeDailyProducts(plans)[0].quantity,1);assert.equal(mergeDailyProducts(plans)[0].need,400);assert.equal(mergeDailyProducts(plans,{'午餐':[4],'晚餐':[]})[0].need,200)})
test('proposal and active paid snapshot priority, profile changes never mutate paid order',()=>{const p=setup();saveProfile(p);saveTomorrowProposal(p,'早餐');const date=new Date();date.setDate(date.getDate()+1);const tomorrow=localDate(date);assert.equal(todayPlan(p,'早餐',tomorrow).source,'已保存的明日提议');const changed={...p,goals:['减脂']};assert.equal(todayPlan(changed,'早餐',tomorrow).source,'家庭档案建议');const template=adaptExclusivePlan(getExclusivePlan('balanced'),p),batches=createDeliveryBatches(template,localDate(),21),plan=createPlan(p,'晚餐');const order=createDemoOrder({items:plan.products,totalCents:10000,meal:'晚餐',sourcePlanId:'balanced',deliveryBatches:batches,cookingGuides:batches.map(b=>({index:b.index,guides:b.meals.map(m=>createCookingGuide(plan,template,{batchIndex:b.index,meal:m.type}))}))});const snapshot=JSON.stringify(getOrder(order.id));setMealMembers(p,'晚餐',[3]);assert.equal(todayPlan(p,'晚餐').source,'执行中的 AI 专属计划');assert.ok(todayPlan(p,'晚餐').blocked.length);assert.equal(JSON.stringify(getOrder(order.id)),snapshot)})
test('actual alternative recipes, step images and tier refresh are functional',()=>{const p=setup();p.defaultDiners=[1,3];const adapted=adaptExclusivePlan(getExclusivePlan('balanced'),p);assert.ok(adapted.fixturePlans.flat().every(plan=>!plan.products.some(i=>i.id===1||i.id===5)));const guide=createCookingGuide(createPlan(p),adapted);assert.ok(guide.dishGuides.every(g=>g.steps.length===g.stepImages.length&&g.stepImages.every(img=>img.startsWith('data:image/svg'))));const before=JSON.stringify(adapted.days);regenerateExclusivePlans();assert.notEqual(JSON.stringify(adaptExclusivePlan(getExclusivePlan('balanced'),p).days),before)})
test('family invitation multi-accept vs member single claim, no duplicate record',()=>{const p=setup();saveProfile(p);const general=createInvite();assert.ok(acceptInvite(general,'账号 A').id);assert.ok(acceptInvite(general,'账号 B').id);let fresh=getProfile();fresh.viewerAccount='creator';saveProfile(fresh);const bound=createInvite(2),before=getProfile().members.length;assert.equal(acceptInvite(bound,'妈妈账号').id,2);assert.ok(acceptInvite(bound,'其他账号').error);assert.equal(getProfile().members.length,before);assert.equal(acceptInvite(bound,'妈妈账号').id,2)})
test('long-term memory really changes same member and edit/delete/undo preserves empty state',()=>{const p=setup();saveProfile(p);assert.ok(remember('以后不吃香菜').question);const first=remember('我以后不吃香菜').entry;assert.ok(getProfile().members[0].avoidances.includes('香菜'));const edited=editMemory(first.id,'我以后不吃葱蒜').entry;assert.ok(!getProfile().members[0].avoidances.includes('香菜'));assert.ok(getProfile().members[0].avoidances.includes('葱蒜'));forget(edited.id);assert.deepEqual(getProfile().memories,[]);assert.deepEqual(getProfile().members[0].avoidances,[])})
