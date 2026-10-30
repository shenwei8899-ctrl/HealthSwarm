import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {ref,computed,reactive,effectScope,watch} from 'vue'
import {newMealCommerceState,createMealCommerceController,commerceMealView} from '../src/services/meal-commerce-state.js'

function mount({daily=false,reference=false}={}){
  const calls=[],hooks={},route={date:'2026-10-21',meal:'dinner',arrangement:'saved-1',version:'2'}
  if(daily){route.meal='daily';route.meals=['breakfast','lunch']}
  let scope='A',linked=false,publicationVersion=2,denied=false,referenceVersion=4
  const saved=new Map()
  const items=[{sku_id:'tomato',quantity:1,sku:{sku_id:'tomato',product_name:'合成番茄',price_cent:800,available_quantity:5,net_content:{value:500,unit:'g'},ingredients:[{ingredient_code:'tomato'}]}}]
  const purchase={status:'matched',available:true,catalog_version:'catalog-1',items,
    ingredient_requirements:[{ingredient_id:'tomato',ingredient_code:'tomato',required_value:'300',required_unit:'g'}]}
  const menu={...purchase,...(reference?{scope:'daily_reference'}:{}),package_sn:'pack-1',package_version:1,dishes:[]}
  const line={cart_item_id:'line-1',sku_id:'tomato',quantity:1,version:1,selected:true,
    source_type:'recommendation_package',source_ref:'pack-1',source_version:1}
  const state=reactive(newMealCommerceState())
  const api={
    connect:async()=>{calls.push('connect');if(!linked)throw new Error('请关联商城会员')},session:()=>linked?{token:'synthetic'}:null,
    mealPackage:async()=>structuredClone(menu),cart:async()=>({items:[line]}),addresses:async()=>[{id:1,name:'测试地址',isDefault:true}],
    slots:async()=>({supported:true,items:[{id:10,available:true},{id:20,available:true}]}),pendingOrder:()=>null,
    addMeal:async()=>{calls.push('cart');return {items:[line]}},
    quote:async (lines,address,slot)=>{calls.push(['quote',lines.map(item=>item.cart_item_id),slot]);return {checkout_token:'synthetic-quote',expires_at:new Date(Date.now()+60000).toISOString(),items:[]}},
  }
  const send=async input=>{
    calls.push(input)
    if(denied)throw Object.assign(new Error('采购用途授权已撤回'),{code:403})
    if(reference){if(input.method==='POST')return {data:{preview_id:'preview',package:{package_sn:'pack-1',package_version:1}}};return {data:{date:route.date,version:referenceVersion,purchase_options:[{kind:'reference',id:'preview',meal_types:['lunch']}]}}}
    return {data:{arrangement_id:route.arrangement,version:input.method==='POST'?publicationVersion:2,
      purchase:input.method==='POST'?{...purchase,package_sn:'pack-1',package_version:1}:structuredClone(purchase)}}
  }
  const deps={ref,computed,watch,defineEmits:()=>()=>{},defineExpose:()=>{},onMounted:fn=>hooks.mount=fn,onShow:fn=>hooks.show=fn,onUnmounted:fn=>hooks.unmount=fn,
    defineProps:()=>({route,meal:{members:[{id:'member-1'}]},...(reference?{reference:{previewId:'preview',dailyPlanVersion:4,mealTypes:['lunch'],items:[{sku_id:'tomato',product_name:'合成番茄',quantity:1}]}}:{})}),commerce:api,request:send,
    commerceMealView,getSession:()=>({householdId:'family-1'}),storageContext:()=>scope,
    scopedStorage:{getStorageSync:key=>saved.get(scope+key),setStorageSync:(key,value)=>saved.set(scope+key,structuredClone(value))},
    useMealCommercePage:context=>({...createMealCommerceController({state,api,scope:()=>scope,context}),state,
      plan:computed(()=>commerceMealView(state.menu,context()))})}
  const source=readFileSync(new URL('../src/components/CloudMealPurchase.vue',import.meta.url),'utf8')
    .match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
  const vueScope=effectScope()
  const component=vueScope.run(()=>new Function('deps',`const {${Object.keys(deps).join(',')}}=deps;${source};return {refresh,checkout,toggle,selected,preview,products,picked,total,state,loginOpen,error,purchaseReady}`)(deps))
  return {...component,calls,deny(){denied=true},pending(){purchase.available=false;purchase.confirmation_pending=true;items[0].sku.available_quantity=0},unavailable(){purchase.available=false;purchase.confirmation_pending=false},link(){linked=true},wrongVersion(){publicationVersion=3},switch(){scope='B'},
    changeReferenceVersion(){referenceVersion++},dispose(){hooks.unmount();vueScope.stop()}}
}

test('opening a saved meal reads current products without commerce login or a purchase write',async()=>{
  const f=mount();try{await f.refresh()
    assert.equal(f.calls.length,1);assert.match(f.calls[0].path,/saved-1&version=2$/)
    assert.equal(f.calls[0].method,undefined);assert.equal(f.products.value[0].needLabel,'300g')
    assert.equal(f.total.value,800)
    f.toggle('tomato');await f.refresh();assert.deepEqual(f.selected.value,[])
  }finally{f.dispose()}
})
test('an unlinked commerce account only interrupts explicit checkout and keeps the meal visible',async()=>{
  const f=mount();try{await f.refresh();await f.checkout()
    assert.equal(f.loginOpen.value,true);assert.ok(f.preview.value)
    assert.equal(f.calls.some(call=>call?.method==='POST'),false)
  }finally{f.dispose()}
})

test('revoked purchase access during explicit publication clears preview and checkout state',async()=>{
 const f=mount();try{
  await f.refresh();f.link();f.deny();await f.checkout()
  assert.equal(f.preview.value,null);assert.equal(f.state.quote,null);assert.equal(f.state.ready,false)
  assert.equal(f.products.value.length,0);assert.match(f.error.value,/授权已撤回/)
 }finally{f.dispose()}
})
test('explicit checkout publishes the saved version and quotes only this meal',async()=>{
  const f=mount();try{await f.refresh();f.link();await f.checkout()
    const publication=f.calls.find(call=>call?.method==='POST')
    assert.deepEqual(publication.data,{arrangement_id:'saved-1',version:2})
    assert.equal(f.state.error,'')
    assert.equal(f.state.checkoutError,'')
    assert.deepEqual(f.calls.find(call=>Array.isArray(call)&&call[0]==='quote'),['quote',['line-1'],10])
    assert.ok(f.state.quote)
  }finally{f.dispose()}
})
test('a different arrangement version never reaches the cart or quotation',async()=>{
  const f=mount();try{await f.refresh();f.link();f.wrongVersion();await f.checkout()
    assert.match(f.error.value,/本餐已更新/);assert.equal(f.calls.includes('cart'),false)
    assert.equal(f.state.quote,null)
  }finally{f.dispose()}
})

test('requote preserves the explicitly selected second delivery slot',async()=>{
  const f=mount();try{await f.refresh();f.link();await f.checkout()
    f.state.slotId=20;f.state.quote=null;await f.checkout()
    assert.equal(f.state.slotId,20)
    assert.equal(f.calls.filter(call=>Array.isArray(call)&&call[0]==='quote').at(-1)[2],20)
    assert.equal(f.calls.filter(call=>call?.method==='POST').length,1)
  }finally{f.dispose()}
})

test('daily purchase preview and explicit publication reference the chosen meals',async()=>{
  const f=mount({daily:true});try{await f.refresh();f.link();await f.checkout()
    assert.match(f.calls[0].path,/\/purchase\?.*&meals=breakfast&meals=lunch$/)
    assert.doesNotMatch(f.calls[0].path,/\/meals\//)
    assert.deepEqual(f.calls.find(call=>call?.method==='POST').data.meals,['breakfast','lunch'])
  }finally{f.dispose()}
})

test('daily summary clears former account dishes before awaiting a new read',async()=>{
  const route={arrangement:'saved-1',version:'2',date:'2026-10-21'},hooks={}
  let scope='A',answer={status:'ready',id:'saved-1',version:2,meals:[{members:[],dishes:[{name:'前账号菜品'}]}]},release
  const deps={ref,computed,watch,defineEmits:()=>()=>{},defineExpose:()=>{},onMounted:fn=>hooks.mount=fn,onShow:fn=>hooks.show=fn,onUnmounted:fn=>hooks.unmount=fn,
    defineProps:()=>({route}),storageContext:()=>scope,getSession:()=>({householdId:scope}),
    request:async()=>answer?{data:answer}:new Promise(resolve=>{release=resolve})}
  const source=readFileSync(new URL('../src/components/CloudDailyPurchase.vue',import.meta.url),'utf8')
    .match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
  const f=new Function('deps',`const {${Object.keys(deps).join(',')}}=deps;${source};return {load,arrangement,error}`)(deps)
  await f.load();assert.equal(f.arrangement.value.meals[0].dishes[0].name,'前账号菜品')
  scope='B';answer=null;const pending=hooks.show()
  assert.equal(f.arrangement.value,null)
  release({data:{status:'stale'}});await pending
  assert.equal(f.arrangement.value,null);assert.match(f.error.value,/已更新/)
  hooks.unmount()
})

test('each arrangement card opens a detail purchase for its own date and saved ID',()=>{
 const source=readFileSync(new URL('../src/components/CloudNutritionChat.vue',import.meta.url),'utf8')
 const action=source.match(/function shop\(arrangement\)\{[^\n]+/)[0]
 const calls=[],open=new Function('openFormalDetail',`${action};return shop`)((meal,arrangement,date,options)=>calls.push({meal,arrangement,date,options}))
 open({id:'today',date:'2026-10-21',version:1,meals:[{type:'breakfast',members:[]}]});open({id:'tomorrow',date:'2026-10-22',version:3,meals:[{type:'dinner',members:[]}]})
 assert.equal(calls[1].date,'2026-10-22');assert.equal(calls[1].arrangement.id,'tomorrow');assert.equal(calls[1].arrangement.version,3)
 assert.deepEqual(calls[1].options.purchaseMeals,['dinner']);assert.equal(calls[1].options.initialView,'purchase')
})

test('an uncertain purchase stays reachable to confirm the original result without claiming stock is available',async()=>{
  const f=mount();try{
    f.pending();await f.refresh()
    assert.equal(f.preview.value.available,false)
    assert.equal(f.purchaseReady.value,true)
    assert.equal(f.products.value[0].availableQuantity,0)
    assert.deepEqual(f.picked.value,['tomato'])
    assert.equal(f.products.value[0].name,'合成番茄')
    assert.equal(f.total.value,800)
    f.link();await f.checkout()
    assert.ok(f.calls.some(call=>call?.method==='POST'))
    f.unavailable();await f.refresh()
    assert.equal(f.purchaseReady.value,false)
    const view=readFileSync(new URL('../src/components/CloudMealPurchase.vue',import.meta.url),'utf8')
    assert.match(view, /!purchaseReady/)
    assert.match(view, /确认上次采购结果/)
  }finally{f.dispose()}
})

test('reference sheet reads without publishing, leaves prices unknown and quotes only on explicit checkout',async()=>{
 const f=mount({reference:true});try{await f.refresh();assert.equal(f.products.value[0].priceCents,null);assert.equal(f.calls.some(c=>c?.method==='POST'),false)
 f.link();await f.checkout();const write=f.calls.find(c=>c?.method==='POST');assert.deepEqual(write.data,{preview_id:'preview',version:4,meal_types:['lunch']});assert.ok(f.state.quote)
 }finally{f.dispose()}
})
test('changed reference plan prevents publication and discards a prior quote',async()=>{
 const f=mount({reference:true});try{await f.refresh();f.link();f.changeReferenceVersion();await f.checkout();assert.equal(f.calls.some(c=>c?.method==='POST'),false);assert.equal(f.state.quote,null);assert.match(f.error.value,/参考餐单已更新/)}finally{f.dispose()}
})
test('revoked reference purchase does not leave prior products visible',async()=>{
 const f=mount({reference:true});try{await f.refresh();f.deny();await f.refresh();assert.equal(f.products.value.length,0);assert.equal(f.state.quote,null)}finally{f.dispose()}
})
