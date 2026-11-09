import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {ref,computed,reactive,effectScope,watch} from 'vue'
import {referenceIngredientLabel,referenceGapDetail} from '../src/utils/meal-presentation.js'
import {newMealCommerceState,createMealCommerceController,commerceMealView} from '../src/services/meal-commerce-state.js'

function mount({daily=false,reference=false,selection,unified=false,gaps=[]}={}){
  const calls=[],hooks={},route={date:'2026-10-21',meal:'dinner',arrangement:'saved-1',version:'2'}
  if(daily){route.meal='daily';route.meals=['breakfast','lunch']}
  let scope='A',linked=false,publicationVersion=2,denied=false,referenceVersion=4
  const saved=new Map()
  const items=[{sku_id:'tomato',quantity:1,sku:{sku_id:'tomato',product_name:'合成番茄',price_cent:800,available_quantity:5,net_content:{value:500,unit:'g'},ingredients:[{ingredient_code:'tomato'}]}}]
  const purchase={status:'matched',available:true,catalog_version:'catalog-1',items,gaps,
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
    quote:async (lines,address,slot)=>{calls.push(['quote',lines.map(item=>item.cart_item_id),slot]);return {checkout_token:'synthetic-quote',expires_at:new Date(Date.now()+60000).toISOString(),items:[],goods_amount_cent:800,shipping_fee_cent:500,payable_amount_cent:1300}},
  }
  const send=async input=>{
    calls.push(input)
    if(denied)throw Object.assign(new Error('采购用途授权已撤回'),{code:403})
    if(reference){if(input.method==='POST')return {data:{preview_id:'preview',package:{package_sn:'pack-1',package_version:1}}};return {data:{date:route.date,version:referenceVersion,purchase_options:[{kind:'reference',id:'preview',meal_types:['lunch']}]}}}
    return {data:{arrangement_id:route.arrangement,version:input.method==='POST'?publicationVersion:2,
      purchase:input.method==='POST'?{...purchase,package_sn:'pack-1',package_version:1}:structuredClone(purchase)}}
  }
  const uiProps=reactive({unified,visible:true,route,meal:{members:[{id:'member-1'}]},selection,...(reference?{reference:{previewId:'preview',dailyPlanVersion:4,mealTypes:['lunch'],items:[{sku_id:'tomato',product_name:'合成番茄',quantity:1}]}}:{})})
  const deps={ref,computed,watch,referenceIngredientLabel,referenceGapDetail,defineEmits:()=>()=>{},defineExpose:()=>{},onMounted:fn=>hooks.mount=fn,onShow:fn=>hooks.show=fn,onHide:fn=>hooks.hide=fn,onUnmounted:fn=>hooks.unmount=fn,
    defineOptions:()=>{},defineProps:()=>uiProps,commerce:api,request:send,
    commerceMealView,getSession:()=>({householdId:'family-1'}),storageContext:()=>scope,
    scopedStorage:{getStorageSync:key=>saved.get(scope+key),setStorageSync:(key,value)=>saved.set(scope+key,structuredClone(value))},
    useMealCommercePage:context=>({...createMealCommerceController({state,api,scope:()=>scope,context}),state,
      plan:computed(()=>commerceMealView(state.menu,context()))})}
  const source=readFileSync(new URL('../src/components/CloudMealPurchase.vue',import.meta.url),'utf8')
    .match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
  const vueScope=effectScope()
  const component=vueScope.run(()=>new Function('deps',`const {${Object.keys(deps).join(',')}}=deps;${source};return {refresh,refreshUnified,checkout,toggle,selected,preview,products,picked,total,totalKnown,state,loginOpen,error,purchaseReady,purchaseGaps,returnKey,quoteWaiting,canSubmit,selectSlot}`)(deps))
  return {...component,calls,uiProps,deny(){denied=true},pending(){purchase.available=false;purchase.confirmation_pending=true;items[0].sku.available_quantity=0},unavailable(){purchase.available=false;purchase.confirmation_pending=false},link(){linked=true},wrongVersion(){publicationVersion=3},switch(){scope='B'},
    changeReferenceVersion(){referenceVersion++},dispose(){hooks.unmount();vueScope.stop()}}
}

test('opening unified procurement initializes address, time and quote in one step',async()=>{
 const f=mount({unified:true});try{
  f.link();await f.refreshUnified()
  assert.equal(f.state.address.id,1);assert.equal(f.state.slotId,10)
  assert.ok(f.state.quote);assert.equal(f.canSubmit.value,true)
  assert.equal(f.calls.filter(c=>c?.method==='POST').length,1)
 }finally{f.dispose()}
})

test('unified submit remains disabled when the server has not returned complete fees',async()=>{
 const f=mount({unified:true});try{
  f.link();await f.refreshUnified();assert.equal(f.canSubmit.value,true)
  f.state.quote.shipping_fee_cent=undefined;assert.equal(f.canSubmit.value,false)
  f.state.quote.shipping_fee_cent=500;f.state.slots=[];assert.equal(f.canSubmit.value,false)
 }finally{f.dispose()}
})

test('unified selection immediately invalidates price and debounces a fresh quote',async()=>{
 const f=mount({unified:true});try{
  f.link();await f.refreshUnified();const before=f.calls.filter(Array.isArray).length
  f.toggle('tomato');assert.equal(f.state.quote,null);assert.equal(f.canSubmit.value,false)
  f.toggle('tomato');assert.equal(f.quoteWaiting.value,true)
  await new Promise(resolve=>setTimeout(resolve,300))
  assert.equal(f.calls.filter(Array.isArray).length,before+1)
  assert.ok(f.state.quote);assert.equal(f.calls.filter(c=>c?.method==='POST').length,1)
 }finally{f.dispose()}
})

test('address return cannot resume checkout belonging to another dish, meal or daily version',()=>{
 const scope={familyId:'family',date:'2026-11-02',mealType:'dinner',version:4,dishKeys:['fish']}
 const fixtures=[scope,{...scope,dishKeys:[]},{...scope,dishKeys:['rice']},{...scope,version:5},{...scope,mealType:'lunch'}].map(selection=>mount({selection}))
 try{assert.equal(new Set(fixtures.map(f=>f.returnKey())).size,fixtures.length)}finally{fixtures.forEach(f=>f.dispose())}
})

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
  const deps={ref,computed,watch,referenceIngredientLabel,referenceGapDetail,defineEmits:()=>()=>{},defineExpose:()=>{},onMounted:fn=>hooks.mount=fn,onShow:fn=>hooks.show=fn,onUnmounted:fn=>hooks.unmount=fn,
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

test('unread, rejected or unavailable procurement never displays a known zero amount',async()=>{
 const f=mount()
 try{
  assert.equal(f.totalKnown.value,false)
  await f.refresh();assert.equal(f.totalKnown.value,true)
  f.unavailable();await f.refresh();assert.equal(f.totalKnown.value,false)
  f.deny();await f.refresh();assert.equal(f.totalKnown.value,false)
 }finally{f.dispose()}
})


test('saved meal gaps stay visible while only purchasable products reach quote',async()=>{
 const gaps=[{ingredient:'Oil',ingredient_label:'油',reason:'needs_confirmation',purchase_mode:'self_purchase',sku_id:null,price_cent:null,detail:'自行购买，暂无价格。'},
   {ingredient:'Scallion (optional), sliced',ingredient_label:'葱（可选），切片',reason:'optional_not_selected',detail:'原谱可选，本次未采用。'}]
 const f=mount({unified:true,selection:{familyId:'family-1',date:'2026-10-21',mealType:'dinner',version:2,dishKeys:['dish-1']},gaps})
 try{
  f.link();await f.refreshUnified()
  assert.equal(f.error.value,'');assert.equal(f.canSubmit.value,true)
  assert.deepEqual(f.purchaseGaps.value.map(g=>[g.label,g.reason]),[['油','needs_confirmation'],['葱（可选），切片','optional_not_selected']])
  assert.deepEqual(f.products.value.map(p=>p.id),['tomato'])
  assert.deepEqual(f.calls.find(call=>Array.isArray(call)&&call[0]==='quote')[1],['line-1'])
  f.deny();await f.refreshUnified()
  assert.deepEqual(f.purchaseGaps.value,[]);assert.equal(f.canSubmit.value,false)
 }finally{f.dispose()}
})

test('purchase panel distinguishes failure from loading and renders self-purchase without a price',async()=>{
 const props=reactive({gaps:[{ingredient:'Oil',reason:'needs_confirmation',purchase_mode:'self_purchase'},{ingredient:'Scallion',reason:'optional_not_selected'}],slots:[],ready:false,busy:false,error:'食材核对失败',picked:[]})
 const source=readFileSync(new URL('../src/components/MealPurchasePanel.vue',import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
 const panel=new Function('computed','ref','defineProps','defineEmits',source+';return {deliveryText,preparationGaps,optionalGaps}')(computed,ref,()=>props,()=>()=>{})
 assert.equal(panel.deliveryText.value,'暂不可用')
 props.error='';props.busy=true;assert.equal(panel.deliveryText.value,'正在读取…')
 props.busy=false;assert.equal(panel.deliveryText.value,'待核对')
 props.ready=true;assert.equal(panel.deliveryText.value,'添加地址后选择')
 assert.deepEqual(panel.preparationGaps.value.map(g=>g.ingredient),['Oil'])
 assert.deepEqual(panel.optionalGaps.value.map(g=>g.ingredient),['Scallion'])
 const template=readFileSync(new URL('../src/components/MealPurchasePanel.vue',import.meta.url),'utf8')
 assert.ok(template.includes('{{deliveryText}}'))
 assert.ok(template.includes('不计入订单金额'))
 assert.ok(template.includes("gap.purchase_mode==='self_purchase'"))
 assert.ok(template.includes('自行购买 · 暂无价格'))
 const {compile,createSSRApp}=await import('vue'),{renderToString}=await import('vue/server-renderer')
 const render=compile(template.match(/<template>([\s\S]*?)<\/template>\s*<style/)[1])
 const html=await renderToString(createSSRApp({render,setup:()=>({
  accessRequired:false,busy:false,ready:false,fixed:false,error:'',retryLabel:'重新核对',preparationGaps:props.gaps.slice(0,1),optionalGaps:[],optionalText:'',
  address:null,slots:[],slotId:null,timesOpen:false,deliveryText:'待核对',picked:[],products:[],pending:false,pricing:false,canSubmit:false,total:'—',quote:null,
  slotName:()=>'',money:()=>'',
 })}))
 assert.match(html.replace(/<!--[\s\S]*?-->/g,''),/Oil · 自行购买 · 暂无价格/)
})
