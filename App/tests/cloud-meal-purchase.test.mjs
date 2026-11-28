import {exclusiveDeliveryPreview} from '../src/services/exclusive-delivery-preview.js'
import { useReplySelection } from '../src/composables/use-reply-selection.js'
import { replyQuote } from '../src/utils/reply-selection.js'
import test from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import {ref,computed,reactive,effectScope,watch} from 'vue'
import {referenceIngredientLabel,referenceGapDetail} from '../src/utils/meal-presentation.js'
import {newMealCommerceState,createMealCommerceController,commerceMealView,nonnegativeInteger,productAmountCents,selectedSubtotalCents,validMealDate,PLAN_DELIVERY_TIMES,deliverySlotTime} from '../src/services/meal-commerce-state.js'

function mount({daily=false,reference=false,exclusive=false,exclusivePage=false,productReference=false,unavailableSpec=false,selection,unified=false,gaps=[],saved=new Map()}={}){
  if(exclusive)reference=true
  const calls=[],hooks={},route={date:'2026-10-21',meal:'dinner',arrangement:'saved-1',version:'2'}
  if(daily){route.meal='daily';route.meals=['breakfast','lunch']}
  let scope='A',linked=false,publicationVersion=2,denied=false,referenceVersion=4
  let publishGate=null,addressPicker=null
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
    slots:async()=>({supported:true,items:[{id:10,name:'10:00–11:00',available:true},{id:20,name:'11:00–12:00',available:true}]}),pendingOrder:()=>null,
    addMeal:async()=>{calls.push('cart');return {items:[line]}},
    quantity:async(value,quantity)=>{line.quantity=quantity;line.version++;return {items:[line]}},
    quote:async (lines,address,slot)=>{calls.push(['quote',lines.map(item=>item.cart_item_id),slot]);return {checkout_token:'synthetic-quote',expires_at:new Date(Date.now()+60000).toISOString(),items:[],goods_amount_cent:800,shipping_fee_cent:500,payable_amount_cent:1300}},
    exclusiveDates:async()=>({items:['2026-12-01','2026-12-03']}),
    quoteRecommendation:async(sn,version,address,slot,items,options)=>{if(exclusive&&referenceVersion!==4)throw Object.assign(new Error('计划或商品已变化'),{code:409});if(denied)throw Object.assign(new Error('采购用途授权已撤回'),{code:403});calls.push(['direct-quote',sn,items,slot]);return {...(exclusive?{exclusive_delivery:{first_meal_date:options.firstMealDate},delivery_batches:[{batch_no:1}]}:{}),checkout_token:'synthetic-quote',expires_at:new Date(Date.now()+60000).toISOString(),items:[],goods_amount_cent:800,shipping_fee_cent:500,payable_amount_cent:1300}},
  }
  const send=async input=>{
    calls.push(input)
    if(exclusive&&input.method==='POST'&&publishGate)await publishGate
    if(denied)throw Object.assign(new Error('采购用途授权已撤回'),{code:403})
    if(exclusive)return {data:{...structuredClone(purchase),items:structuredClone(menu.items),scope_hash:String(referenceVersion),...(input.method==='POST'?{package:{package_sn:menu.package_sn,package_version:menu.package_version,expires_at:new Date(Date.now()+600000).toISOString()}}:{})}}
    if(reference){if(input.method==='POST')return {data:{preview_id:'preview',package:{package_sn:'pack-1',package_version:1}}};return {data:{date:route.date,version:referenceVersion,purchase_options:[{kind:'reference',id:'preview',meal_types:['lunch']}]}}}
    return {data:{arrangement_id:route.arrangement,version:input.method==='POST'?publicationVersion:2,
      purchase:input.method==='POST'?{...purchase,package_sn:'pack-1',package_version:1}:structuredClone(purchase)}}
  }
  const referenceItems=productReference
    ? [{product_id:'tomato-product',product_name:'合成番茄',ingredient_refs:['番茄300克'],skus:[
        {sku_id:'tomato-500',sku_name:'500克',price_cent:800,available_quantity:5,sale_status:'available'},
        {sku_id:'tomato-1000',sku_name:'1千克',price_cent:1400,available_quantity:3,sale_status:'available'},
        ...(unavailableSpec?[{sku_id:'tomato-2000',sku_name:'2千克',price_cent:2500,available_quantity:0,sale_status:'unavailable'}]:[]),
      ]}]
    : [{sku_id:'tomato',product_id:'tomato-product',product_name:'合成番茄',quantity:1}]
  const uiProps=reactive({unified,exclusivePage,visible:true,route,meal:{members:[{id:'member-1'}]},selection,...(reference?{reference:{previewId:'preview',dailyPlanVersion:4,mealTypes:['lunch'],items:referenceItems}}:{})})
  if(exclusive){uiProps.exclusive={path:'/api/health/v1/families/family/exclusive-plans/group/tiers/standard/purchase',scopeHash:'4'};delete uiProps.reference.dailyPlanVersion}
  const deps={exclusiveDeliveryPreview,useReplySelection,replyQuote,ref,computed,watch,referenceIngredientLabel,referenceGapDetail,defineEmits:()=>()=>{},defineExpose:()=>{},onMounted:fn=>hooks.mount=fn,onShow:fn=>hooks.show=fn,onHide:fn=>hooks.hide=fn,onUnmounted:fn=>hooks.unmount=fn,
    openAddressPicker:options=>{addressPicker=options},defineOptions:()=>{},defineProps:()=>uiProps,commerce:api,request:send,
    uni:{showToast:options=>calls.push(['toast',options]),navigateTo:options=>calls.push(['navigate',options])},
    commerceMealView,nonnegativeInteger,productAmountCents,selectedSubtotalCents,validMealDate,PLAN_DELIVERY_TIMES,deliverySlotTime,getSession:()=>({householdId:'family-1'}),storageContext:()=>scope,
    scopedStorage:{getStorageSync:key=>saved.get(scope+key),setStorageSync:(key,value)=>saved.set(scope+key,structuredClone(value))},
    useMealCommercePage:context=>({...createMealCommerceController({state,api,scope:()=>scope,context}),state,
      plan:computed(()=>commerceMealView(state.menu,{...context(),quantities:state.quantities}))})}
  const source=readFileSync(new URL('../src/components/CloudMealPurchase.vue',import.meta.url),'utf8')
    .match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
  const vueScope=effectScope()
  const component=vueScope.run(()=>new Function('deps',`const {${Object.keys(deps).join(',')}}=deps;${source};return {refresh,refreshUnified,checkout,submit,toggle,changeQuantity,selected,preview,products,picked,total,totalKnown,state,loginOpen,error,purchaseReady,purchaseGaps,returnKey,quoteWaiting,canSubmit,selectSlot,selectMealDate,checkoutOpen,chooseAddress,preferredTime}`)(deps))
  return {...component,calls,uiProps,api,menu,line,holdPublication(){let release;publishGate=new Promise(resolve=>release=resolve);return release},mounted:()=>hooks.mount(),hide:()=>hooks.hide(),selectAddress:id=>addressPicker.onSelected(id),deny(){denied=true},pending(){purchase.available=false;purchase.confirmation_pending=true;items[0].sku.available_quantity=0},unavailable(){purchase.available=false;purchase.confirmation_pending=false},link(){linked=true},wrongVersion(){publicationVersion=3},switch(){scope='B'},
    changeReferenceVersion(){referenceVersion++},show:()=>hooks.show(),dispose(){hooks.unmount();vueScope.stop()}}
}

test('standalone unified show refreshes through the scoped publication without a GET',async()=>{
 const f=mount({unified:true,selection:{familyId:'family-1',date:'2026-10-21',mealType:'dinner',version:2,dishKeys:['fish']}})
 try{
  f.uiProps.embedded=false;f.link();await f.show()
  await new Promise(resolve=>setTimeout(resolve,0))
  assert.equal(f.calls.some(c=>c?.path&&c.method!=='POST'),false)
 }finally{f.dispose()}
})

test('unconvertible recipe quantity reaches purchase and user changes reach direct quote within mall stock',async()=>{
 const f=mount({unified:true,selection:{familyId:'family-1',date:'2026-10-21',mealType:'dinner',version:2,dishKeys:['milk']}})
 try{
  const item=f.menu.items[0]
  item.sku.sku_name='950毫升/瓶';item.sku.net_content={value:950,unit:'ml'}
  item.quantity_basis='needs_confirmation';item.suggested_quantity=1;item.quantity_notice='用量无法换算，请按实际需要调整。'
  f.link();await f.refreshUnified()
  const product=f.products.value[0]
  assert.equal(product.packLabel,'950毫升/瓶')
  assert.match(product.quantityNotice,/按实际需要调整/)
  f.changeQuantity(product,1)
  await new Promise(resolve=>setTimeout(resolve,400))
  const quoted=f.calls.filter(c=>Array.isArray(c)&&c[0]==='direct-quote').at(-1)
  assert.equal(quoted[2][0].quantity,2)
  f.changeQuantity({...f.products.value[0],quantity:5},1)
  assert.equal(f.products.value[0].quantity,2)
 }finally{f.dispose()}
})

test('purchase panel renders mall bottle specification and adjustable quantity notice',async()=>{
 const template=readFileSync(new URL('../src/components/MealPurchasePanel.vue',import.meta.url),'utf8')
 const {compile,createSSRApp}=await import('vue'),{renderToString}=await import('vue/server-renderer')
 const render=compile(template.match(/<template>([\s\S]*?)<\/template>\s*<style/)[1])
 const html=await renderToString(createSSRApp({render,setup:()=>({
  accessRequired:false,busy:false,ready:true,choicesReady:false,fixed:false,independent:true,addressReady:true,
  productsLoading:false,addressError:'',title:'本餐食材',error:'',preparationGaps:[],optionalGaps:[],optionalText:'',
  address:null,slots:[],slotId:null,timesOpen:false,deliveryText:'待核对',picked:['milk'],pending:false,pricing:false,total:'—',quote:null,
  products:[{id:'milk',name:'合成牛奶',packLabel:'950毫升/瓶',priceCents:1000,quantity:1,availableQuantity:5,quantityNotice:'用量无法换算，请按实际需要调整。'}],
  slotName:()=>'',money:value=>'¥'+value/100,showPaymentNotice:()=>{},
 })}))
 assert.match(html,/950毫升\/瓶/)
 assert.match(html,/按实际需要调整/)
 assert.match(html,/1 件/)
 assert.doesNotMatch(html,/\/包|1 包|暂不可选/)
 assert.doesNotMatch(html,/<button[^>]*aria-label="(?:减少|增加)合成牛奶数量"[^>]*disabled[^>]*>＋/)
})

test('direct refresh requested during submission is queued for the settled operation',()=>{
 const text=readFileSync(new URL('../src/components/CloudMealPurchase.vue',import.meta.url),'utf8')
 const loader=text.match(/async function loadSelectedPurchase\([^)]*\) \{([\s\S]+?)\n\}/)[1]
 assert.ok(loader.includes('if (submitting.value) { refreshRequested=true; return }'))
 assert.ok(loader.includes('refreshRequested=false'))
 assert.ok(text.includes('refreshRequested&&!busy.value&&!state.busy&&!submitting.value'))
})

test('weekly exclusive purchase binds publication to its tier and scope, then reuses checkout',async()=>{
 const f=mount({exclusive:true});try{
  f.link();await f.refresh();await f.checkout()
  const writes=f.calls.filter(c=>c?.method==='POST')
  assert.equal(writes.length,1);assert.equal(writes[0].path,f.uiProps.exclusive.path)
  assert.deepEqual(writes[0].data,{scope_hash:'4'})
  assert.equal(f.state.ready,true);assert.ok(f.state.quote)
  f.changeReferenceVersion();await f.checkout();assert.match(f.error.value||f.state.error||f.state.checkoutError,/计划或商品已变化/)
  assert.equal(f.calls.filter(c=>c?.method==='POST').length,1)
 }finally{f.dispose()}
})

test('exclusive dates bind a whole-week quote and changing date immediately invalidates it',async()=>{
 const f=mount({exclusive:true});try{
  const purposes=[];const slots=f.api.slots
  f.api.slots=(address,purpose)=>{purposes.push(purpose);return slots(address,purpose)}
  f.link();await f.refresh();await f.checkout()
  assert.ok(purposes.every(purpose=>purpose==='plan'))
  assert.equal(f.state.firstMealDate,'2026-12-01')
  let release;const quote=f.api.quoteRecommendation
  f.api.quoteRecommendation=(...args)=>new Promise(resolve=>{release=()=>resolve(quote(...args))})
  const changing=f.selectMealDate('2026-12-03')
  assert.equal(f.state.quote,null)
  await new Promise(resolve=>setTimeout(resolve,0));release();await changing
  assert.equal(f.state.quote.exclusive_delivery.first_meal_date,'2026-12-03')
 }finally{f.dispose()}
})

test('unavailable meal date stays visible as a choice to correct without accepting another date',async()=>{
 const f=mount({exclusive:true});try{
  f.link();await f.refresh();await f.checkout()
  f.api.exclusiveDates=async()=>({items:['2026-12-03']})
  await f.checkout()
  assert.equal(f.state.quote,null);assert.equal(f.state.ready,true)
  assert.equal(f.state.firstMealDate,'2026-12-01');assert.deepEqual(f.state.mealDates,['2026-12-03'])
  assert.match(f.state.checkoutError,/重新选择日期/)
  await f.selectMealDate('2026-12-03');assert.ok(f.state.quote)
 }finally{f.dispose()}
})

test('pending storage rules keep products available to edit and never keep a stale quote',async()=>{
 const f=mount({exclusive:true});try{
  f.link();await f.refresh();await f.checkout()
  f.api.exclusiveDates=async()=>{throw Object.assign(new Error('储存规则待核对'),{status:409,code:40963})}
  await f.checkout()
  assert.equal(f.state.ready,true);assert.equal(f.state.quote,null)
  assert.match(f.state.checkoutError,/储存规则待核对/)
  assert.ok(f.products.value.length)
 }finally{f.dispose()}
})

test('exclusive preview displays server SKU prices, keeps package counts and recalculates selected subtotal without writes',async()=>{
 const f=mount({exclusive:true})
 try{
  const text=readFileSync(new URL('../src/pages/exclusive-plans/detail.vue',import.meta.url),'utf8')
  const projection=text.slice(text.indexOf('const purchaseReference ='),text.indexOf('const purchaseRoute ='))
  const receipt=ref({items:[{sku_id:'tomato',quantity:2,sku:{product_id:'tomato-product',product_name:'合成番茄',sku_name:'500g',price_cent:800,available_quantity:3,sale_status:'available'}}]})
  f.uiProps.reference=new Function('computed','purchaseData','route',projection+'return purchaseReference.value')(computed,receipt,ref({groupId:'group'}))
  await f.refresh()
  assert.equal(f.products.value[0].quantity,2)
  assert.equal(f.products.value[0].priceCents,800)
  assert.equal(f.totalKnown.value,true);assert.equal(f.total.value,1600)
  f.changeQuantity(f.products.value[0],1)
  assert.equal(f.total.value,2400)
  f.changeQuantity(f.products.value[0],1)
  assert.equal(f.products.value[0].quantity,3)
  f.toggle('tomato');assert.equal(f.total.value,0)
  f.toggle('tomato');assert.equal(f.total.value,2400)
  assert.equal(f.calls.some(call=>call?.method==='POST'||call==='connect'),false)
  f.link();await f.checkout()
  assert.equal(f.state.ready,true)
  assert.equal(f.products.value[0].quantity,3)
  assert.equal(f.total.value,2400)
  assert.ok(f.state.quote)
 }finally{f.dispose()}
})

test('unknown, invalid and overflowing prices or quantities cannot become a known subtotal',async()=>{
 const f=mount()
 try{
  await f.refresh()
  const row=f.preview.value.items[0]
  for(const value of [null,undefined,'',false,'800',-1,1.5,Infinity,NaN,Number.MAX_SAFE_INTEGER+1]){
   row.sku.price_cent=value
   assert.equal(f.totalKnown.value,false,String(value))
   assert.equal(f.total.value,null,String(value))
  }
  row.sku.price_cent=800
  for(const quantity of [undefined,null,0,-1,1.5,Infinity,Number.MAX_SAFE_INTEGER+1]){
   row.quantity=quantity
   assert.equal(f.totalKnown.value,false,String(quantity))
   assert.equal(f.total.value,null,String(quantity))
  }
  row.quantity=2;row.sku.price_cent=Number.MAX_SAFE_INTEGER
  assert.equal(f.totalKnown.value,false);assert.equal(f.total.value,null)
  row.quantity=1
  f.preview.value.items.push({sku_id:'other',quantity:1,sku:{...row.sku,sku_id:'other',price_cent:1}})
  f.selected.value=['tomato','other']
  assert.equal(f.totalKnown.value,false);assert.equal(f.total.value,null)
  f.preview.value.items.pop();f.selected.value=['tomato']
  row.quantity=1;row.sku.price_cent=0
  assert.equal(f.totalKnown.value,true);assert.equal(f.total.value,0)
  row.sku.price_cent=800;f.selected.value=['missing-sku']
  assert.equal(f.totalKnown.value,false);assert.equal(f.total.value,null)
 }finally{f.dispose()}
})

test('flat reference rows keep unknown prices unknown and reject unavailable stock',async()=>{
 const f=mount({exclusive:true})
 try{
  Object.assign(f.uiProps.reference.items[0],{price_cent:0,available_quantity:2,sale_status:'available'})
  await f.refresh();assert.equal(f.totalKnown.value,true);assert.equal(f.total.value,0)
  f.uiProps.reference.items[0].price_cent=null
  assert.equal(f.totalKnown.value,false);assert.equal(f.total.value,null)
  f.uiProps.reference.items[0].available_quantity=0
  await f.refresh();assert.deepEqual(f.picked.value,[])
  f.toggle('tomato');assert.deepEqual(f.picked.value,[])
 }finally{f.dispose()}
})

test('exclusive entry renders the fresh parent receipt without another read, but refresh and checkout revalidate',async()=>{
 const f=mount({exclusive:true});try{
  f.uiProps.exclusive.initialPurchase={scope_hash:'4'}
  await f.show();await f.mounted()
  assert.equal(f.calls.length,0)
  assert.equal(f.products.value[0].name,'合成番茄')
  assert.deepEqual(f.picked.value,['tomato'])
  await f.refresh()
  assert.equal(f.calls.filter(c=>c?.path).length,1)
  f.link();f.changeReferenceVersion();await f.checkout()
  assert.match(f.error.value||f.state.error||f.state.checkoutError,/计划或商品已变化/)
  assert.equal(f.calls.filter(c=>c?.method==='POST').length,1)
 }finally{f.dispose()}
})

test('a mismatched initial exclusive receipt is revalidated instead of being reused',async()=>{
 const f=mount({exclusive:true});try{
  f.uiProps.exclusive.initialPurchase={scope_hash:'old'}
  await f.mounted()
  assert.equal(f.calls.filter(c=>c?.path).length,1)
 }finally{f.dispose()}
})

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

test('expired exclusive package is republished before quoting and keeps quantity and delivery',async()=>{
 const f=mount({exclusive:true});try{
  f.link();await f.refresh();await f.checkout()
  f.changeQuantity(f.products.value[0],1);f.state.slotId=20
  f.state.menu.expires_at=new Date(Date.now()-1000).toISOString()
  await f.checkout()
  assert.equal(f.calls.filter(call=>call?.method==='POST').length,2)
  assert.equal(f.state.quantities.tomato,2);assert.equal(f.state.slotId,20)
  assert.ok(f.state.quote);assert.equal(f.state.checkoutError,'')
 }finally{f.dispose()}
})

test('renewing into a new package keeps deselected products and user quantities',async()=>{
 const f=mount({exclusive:true});try{
  f.uiProps.reference.items.push({sku_id:'egg',product_name:'合成鸡蛋',quantity:1})
  f.menu.items.push({quantity:1,sku:{sku_id:'egg',product_name:'合成鸡蛋',price_cent:600,available_quantity:5}})
  const eggLine={...f.line,cart_item_id:'line-2',sku_id:'egg'}
  f.api.cart=async()=>({items:[f.line,eggLine]})
  f.api.addMeal=async()=>{f.line.source_ref=f.menu.package_sn;eggLine.source_ref=f.menu.package_sn;return {items:[f.line,eggLine]}}
  f.api.select=async(line,selected)=>{line.selected=selected;return {items:[f.line,eggLine]}}
  f.api.quantity=async(line,quantity)=>{line.quantity=quantity;line.version++;return {items:[f.line,eggLine]}}
  f.link();await f.refresh();await f.checkout()
  f.toggle('egg');f.changeQuantity(f.products.value.find(p=>p.id==='tomato'),1)
  f.state.menu.expires_at=new Date(Date.now()-1000).toISOString();f.menu.package_sn='pack-2'
  await f.checkout()
  assert.deepEqual(f.state.selected,['tomato']);assert.equal(f.state.quantities.tomato,2)
  assert.equal(f.state.menu.package_sn,'pack-2');assert.ok(f.state.quote)
  assert.equal(f.state.selected.includes('egg'),false)
 }finally{f.dispose()}
})

test('server expiry refreshes exclusive source once and requotes without placing an order',async()=>{
 const f=mount({exclusive:true});try{
  let attempts=0
  const quote=f.api.quoteRecommendation
  f.api.quoteRecommendation=async(...args)=>{
   if(++attempts===1)throw Object.assign(new Error('采购来源已过期'),{status:409,code:40906,details:{reason:'source_expired'}})
   return quote(...args)
  }
  f.link();await f.refresh();await f.checkout()
  assert.equal(attempts,2);assert.ok(f.state.quote)
  assert.equal(f.calls.filter(call=>call?.method==='POST').length,2)
  assert.equal(f.state.sourceExpired,false)
 }finally{f.dispose()}
})

test('source refresh is bounded and a changed source is never silently accepted',async()=>{
 const f=mount({exclusive:true});try{
  let attempts=0
  f.api.quoteRecommendation=async()=>{attempts++;throw Object.assign(new Error('采购来源已过期'),{status:409,code:40906,details:{reason:'source_expired'}})}
  f.link();await f.refresh();await f.checkout()
  assert.equal(attempts,2);assert.equal(f.state.quote,null)
  assert.match(f.state.checkoutError,/已过期/)
  f.changeReferenceVersion();await f.checkout()
  assert.match(f.error.value||f.state.error||f.state.checkoutError,/计划或商品已变化/)
  assert.equal(attempts,2)
 }finally{f.dispose()}
})

test('a generic version conflict does not automatically republish the source',async()=>{
 const f=mount({exclusive:true});try{
  f.api.quoteRecommendation=async()=>{throw Object.assign(new Error('购物车版本冲突'),{status:409,code:40906})}
  f.link();await f.refresh();await f.checkout()
  assert.equal(f.calls.filter(call=>call?.method==='POST').length,1)
  assert.equal(f.state.quote,null);assert.match(f.state.checkoutError,/版本冲突/)
 }finally{f.dispose()}
})

test('an uncertain order prevents source refresh and remains available for recovery',async()=>{
 const f=mount({exclusive:true});try{
  f.link();await f.refresh();await f.checkout()
  f.state.menu.expires_at=new Date(Date.now()-1000).toISOString()
  f.api.pendingOrder=()=>({requestId:'synthetic-original'})
  await f.checkout()
  assert.equal(f.calls.filter(call=>call?.method==='POST').length,1)
  assert.equal(f.state.pending.requestId,'synthetic-original')
  assert.match(f.error.value,/先确认原订单/)
 }finally{f.dispose()}
})

test('direct source expiry reloads publication once and restores saved choices',async()=>{
 const f=mount({unified:true,selection:{familyId:'family-1',date:'2026-10-21',mealType:'dinner',version:2,dishKeys:['fish']}})
 try{
  f.link();await f.refreshUnified()
  f.changeQuantity(f.products.value[0],1);f.state.slotId=20
  let count=0;const original=f.api.quoteRecommendation
  f.api.quoteRecommendation=async(...args)=>{
   if(++count===1)throw Object.assign(new Error('采购来源已过期'),{status:409,code:40906,details:{reason:'source_expired'}})
   return original(...args)
  }
  await f.refreshUnified()
  assert.equal(count,2);assert.ok(f.state.quote)
  assert.equal(f.state.quantities.tomato,2);assert.equal(f.state.slotId,20)
  assert.equal(f.calls.filter(c=>c?.method==='POST').length,2)
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
  const deps={exclusiveDeliveryPreview,useReplySelection,replyQuote,ref,computed,watch,referenceIngredientLabel,referenceGapDetail,defineEmits:()=>()=>{},defineExpose:()=>{},onMounted:fn=>hooks.mount=fn,onShow:fn=>hooks.show=fn,onUnmounted:fn=>hooks.unmount=fn,
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
test('product reference returns every spec and publishes only the user selected spec',async()=>{
 const f=mount({reference:true,productReference:true});try{await f.refresh();assert.equal(f.products.value.length,2);assert.deepEqual(f.picked.value,['tomato-500'])
 f.toggle('tomato-1000');assert.deepEqual(f.picked.value,['tomato-1000']);f.link();await f.checkout();const write=f.calls.find(c=>c?.method==='POST')
 assert.deepEqual(write.data,{preview_id:'preview',version:4,meal_types:['lunch'],product_choices:[{product_id:'tomato-product',sku_id:'tomato-1000',quantity:1}]})
 }finally{f.dispose()}
})
test('unified product reference confirmation only shows payment notice without publication',async()=>{
 const f=mount({reference:true,productReference:true,unified:true});try{
  f.link();await f.refreshUnified()
  assert.equal(f.products.value.length,2);assert.deepEqual(f.picked.value,['tomato-500'])
  assert.equal(f.calls.filter(c=>c?.method==='POST').length,0);assert.equal(f.state.ready,false);assert.equal(f.canSubmit.value,true)
  f.toggle('tomato-1000');await f.submit()
  assert.equal(f.calls.some(c=>c?.method==='POST'),false)
  assert.deepEqual(f.calls.at(-1),['toast',{title:'尚未接入微信支付',icon:'none'}])
 }finally{f.dispose()}
})

test('exclusive confirmation stays in the sheet and never creates or opens an order',async()=>{
 const f=mount({exclusive:true});try{
  f.link();await f.refresh();await f.checkout()
  f.api.createOrder=async()=>{throw new Error('Order creation must not run')}
  const before=f.calls.length,quote=f.state.quote,address=f.state.address
  await f.submit();await f.submit()
  assert.deepEqual(f.calls.slice(before),[
   ['toast',{title:'尚未接入微信支付',icon:'none'}],['toast',{title:'尚未接入微信支付',icon:'none'}],
  ])
  assert.equal(f.state.quote,quote);assert.equal(f.state.address,address);assert.equal(f.state.orderSn,'')
  const sheet=readFileSync(new URL('../src/components/PurchaseCheckoutSheet.vue',import.meta.url),'utf8')
  assert.doesNotMatch(sheet,/下单后进入订单详情支付/)
 }finally{f.dispose()}
})
test('unavailable specs stay visible but cannot be selected or restored',async()=>{
 const f=mount({reference:true,productReference:true,unavailableSpec:true});try{
  await f.refresh();assert.equal(f.products.value.length,3);assert.deepEqual(f.picked.value,['tomato-500'])
  f.toggle('tomato-2000');assert.deepEqual(f.picked.value,['tomato-500'])
  f.selected.value=['tomato-2000'];await f.refresh();assert.deepEqual(f.picked.value,[])
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
  assert.deepEqual(f.calls.find(call=>Array.isArray(call)&&call[0]==='direct-quote')[2],[{sku_id:'tomato',quantity:1}])
  assert.equal(f.calls.filter(call=>call?.path&&call.method!=='POST').length,0)
  assert.equal(f.calls.filter(call=>call?.method==='POST').length,1)
  assert.equal(f.calls.includes('cart'),false)
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
  accessRequired:false,busy:false,ready:false,choicesReady:false,fixed:false,error:'',retryLabel:'重新核对',preparationGaps:props.gaps.slice(0,1),optionalGaps:[],optionalText:'',
  address:null,slots:[],slotId:null,timesOpen:false,deliveryText:'待核对',picked:[],products:[],pending:false,pricing:false,canSubmit:false,total:'—',quote:null,
  slotName:()=>'',money:()=>'',
 })}))
 assert.match(html.replace(/<!--[\s\S]*?-->/g,''),/Oil · 自行购买 · 暂无价格/)
 const specHtml=await renderToString(createSSRApp({render,setup:()=>({
  accessRequired:false,busy:false,ready:false,choicesReady:true,fixed:false,title:'本餐食材',error:'',retryLabel:'重新核对',preparationGaps:[],optionalGaps:[],optionalText:'',
  address:null,slots:[],slotId:null,timesOpen:false,deliveryText:'待核对',picked:['tomato-500'],products:[{id:'tomato-500',name:'合成番茄',packLabel:'500克',priceCents:800,quantity:1,availableQuantity:5,saleStatus:'available'}],pending:false,pricing:false,canSubmit:true,total:'—',quote:null,
  slotName:()=>'',money:value=>value==null?'—':'¥'+(value/100).toFixed(2),
 })}))
 assert.match(specHtml,/合成番茄/);assert.match(specHtml,/500克/);assert.match(specHtml,/确认下单/);assert.doesNotMatch(specHtml,/商品金额/)
 const readyHtml=await renderToString(createSSRApp({render,setup:()=>({
  accessRequired:false,busy:false,ready:true,choicesReady:false,fixed:false,title:'本餐食材',error:'',retryLabel:'重新核对',preparationGaps:[],optionalGaps:[],optionalText:'',
  address:null,slots:[],slotId:null,timesOpen:false,deliveryText:'待核对',picked:['tomato'],products:[{id:'tomato',name:'合成番茄',packLabel:'500克',priceCents:800,quantity:2,availableQuantity:5}],pending:false,pricing:false,canSubmit:true,total:'—',quote:null,
  slotName:()=>'',money:()=>'',
 })}))
 assert.doesNotMatch(readyHtml,/暂不可选/)
 assert.doesNotMatch(readyHtml,/<button[^>]*aria-label="(?:取消选择|减少|增加)合成番茄[^"]*"[^>]*disabled/)
 const loadingAddressHtml=await renderToString(createSSRApp({render,setup:()=>({
  accessRequired:false,busy:true,independent:true,addressReady:false,addressLoading:true,addressError:'',ready:true,choicesReady:false,fixed:false,title:'本餐食材',error:'',retryLabel:'重新核对',preparationGaps:[],optionalGaps:[],optionalText:'',
  address:{name:'合成收件人',phone:'13800000000',region:'测试地区',detail:'测试地址'},slots:[],slotId:null,timesOpen:false,deliveryText:'待核对',picked:[],products:[],pending:false,pricing:true,canSubmit:false,total:'—',quote:null,
  slotName:()=>'',money:()=>'',showPaymentNotice:()=>{},
 })}))
 assert.match(loadingAddressHtml,/合成收件人/);assert.match(loadingAddressHtml,/测试地区/)
 assert.doesNotMatch(loadingAddressHtml,/正在(?:核对|读取).*地址/)
})


test('weekly checkout exposes address while one publication is delayed and never reads or writes cart',async()=>{
 const f=mount({exclusive:true});const release=f.holdPublication()
 try{
  for(const name of ['mealPackage','cart','addMeal','quantity','select','quote'])f.api[name]=async()=>{throw new Error('legacy checkout must not run')}
  f.link();await f.refresh();const pending=f.checkout()
  await new Promise(resolve=>setImmediate(resolve))
  assert.equal(f.state.addressReady,true);assert.equal(f.state.address.id,1)
  assert.equal(f.state.ready,false);assert.equal(f.state.productsLoading,true)
  const second=f.checkout();await second
  assert.equal(f.calls.filter(c=>c?.method==='POST').length,1)
  release();await pending
  assert.ok(f.state.quote);assert.equal(f.state.error,'')
  const count=f.calls.filter(c=>c?.path).length;await f.selectSlot(20)
  assert.equal(f.state.slotId,20);assert.equal(f.calls.filter(c=>c?.path).length,count)
  assert.equal(f.calls.filter(c=>Array.isArray(c)&&c[0]==='direct-quote').length,2)
 }finally{release();f.dispose()}
})

test('closed weekly sheet rejects late publication and never shows its quote',async()=>{
 const f=mount({exclusive:true});const release=f.holdPublication()
 try{
  f.link();await f.refresh();const pending=f.checkout()
  await new Promise(resolve=>setImmediate(resolve));f.checkoutOpen.value=false
  await new Promise(resolve=>setImmediate(resolve));release();await pending
  assert.equal(f.state.ready,false);assert.equal(f.state.quote,null)
  assert.equal(f.calls.filter(c=>Array.isArray(c)&&c[0]==='direct-quote').length,0)
 }finally{release();f.dispose()}
})


test('single-page opens and quotes without intermediate checkout',async()=>{
 const f=mount({exclusive:true,exclusivePage:true});try{
  f.link();await f.mounted();assert.equal(f.checkoutOpen.value,true);assert.ok(f.state.quote)
 }finally{f.dispose()}
})
test('single-page edits debounce; all deselected products remain available to restore',async()=>{
 const f=mount({exclusive:true,exclusivePage:true});try{
  f.link();await f.mounted();f.changeQuantity(f.products.value[0],1);f.changeQuantity(f.products.value[0],1)
  assert.equal(f.state.quote,null);assert.equal(f.state.quantities.tomato,3)
  await new Promise(r=>setTimeout(r,320))
  const quotes=()=>f.calls.filter(c=>Array.isArray(c)&&c[0]==='direct-quote')
  assert.equal(quotes().length,2);assert.equal(quotes().at(-1)[2][0].quantity,3)
  f.toggle('tomato');assert.equal(f.state.quote,null);assert.equal(f.products.value.length,1)
  await new Promise(r=>setTimeout(r,320));assert.equal(quotes().length,2)
  f.toggle('tomato');await new Promise(r=>setTimeout(r,320))
  assert.equal(f.state.quantities.tomato,3);assert.equal(quotes().length,3)
 }finally{f.dispose()}
})
test('single-page address return preserves quantities and chosen meal date',async()=>{
 const f=mount({exclusive:true,exclusivePage:true});try{
  f.api.addresses=async()=>[{id:1,isDefault:true},{id:2}];f.link();await f.mounted()
  f.changeQuantity(f.products.value[0],1);await new Promise(r=>setTimeout(r,320))
  await f.selectMealDate('2026-12-03');f.chooseAddress();f.hide();f.selectAddress(2);f.show()
  await new Promise(r=>setTimeout(r,30))
  assert.equal(f.state.address.id,2);assert.equal(f.state.quantities.tomato,2)
  assert.equal(f.state.firstMealDate,'2026-12-03');assert.ok(f.state.quote)
 }finally{f.dispose()}
})

test('a date can be selected while publication loads and the resulting quote uses it',async()=>{
 const f=mount({exclusive:true,exclusivePage:true}),release=f.holdPublication()
 try{
  f.link();const loading=f.mounted();await new Promise(r=>setImmediate(r))
  assert.equal(f.state.loading,true)
  await f.selectMealDate('2026-12-03')
  assert.equal(f.state.firstMealDate,'2026-12-03');assert.equal(f.state.quote,null)
  release();await loading
  assert.equal(f.state.quote.exclusive_delivery.first_meal_date,'2026-12-03')
 }finally{release();f.dispose()}
})

test('missing delivery configuration does not prevent choosing and restoring a preferred date',async()=>{
 const saved=new Map(),f=mount({exclusive:true,exclusivePage:true,saved})
 const missing=async()=>{throw Object.assign(new Error('专属计划规则尚未配置'),{status:503,code:50317})}
 try{
  f.api.exclusiveDates=missing;f.link();await f.mounted()
  assert.deepEqual(f.state.mealDates,[])
  await f.selectMealDate('2026-12-03')
  assert.equal(f.state.firstMealDate,'2026-12-03');assert.equal(f.state.quote,null)
  assert.match(f.state.checkoutError,/尚未配置/)
  assert.equal(f.calls.some(c=>Array.isArray(c)&&c[0]==='direct-quote'),false)
 }finally{f.dispose()}
 const reopened=mount({exclusive:true,exclusivePage:true,saved})
 try{
  reopened.api.exclusiveDates=missing;reopened.link();await reopened.mounted()
  assert.equal(reopened.state.firstMealDate,'2026-12-03');assert.equal(reopened.state.quote,null)
 }finally{reopened.dispose()}
})

test('a calendar date that is unavailable is retained for correction and cannot produce a quote',async()=>{
 const f=mount({exclusive:true,exclusivePage:true})
 try{
  f.link();await f.mounted();await f.selectMealDate('2026-12-02')
  assert.equal(f.state.firstMealDate,'2026-12-02');assert.equal(f.state.quote,null)
  assert.match(f.state.checkoutError,/不可预约/)
  await f.selectMealDate('2026-12-03');assert.ok(f.state.quote)
  await f.selectMealDate('2020-01-01');assert.equal(f.state.firstMealDate,'2026-12-03')
 }finally{f.dispose()}
})

test('a newer chosen date rejects the late availability response for an older choice',async()=>{
 const f=mount({exclusive:true,exclusivePage:true})
 try{
  f.link();await f.mounted();let release,calls=0
  f.api.exclusiveDates=async()=>{if(!calls++)await new Promise(r=>release=r);return {items:['2026-12-01','2026-12-03']}}
  const old=f.selectMealDate('2026-12-03');await new Promise(r=>setImmediate(r))
  await f.selectMealDate('2026-12-01');assert.equal(f.state.quote.exclusive_delivery.first_meal_date,'2026-12-01')
  release();await old
  assert.equal(f.state.firstMealDate,'2026-12-01');assert.equal(f.state.quote.exclusive_delivery.first_meal_date,'2026-12-01')
 }finally{f.dispose()}
})

test('default time can be selected without an address, restored, and bound to the new address slot',async()=>{
 const saved=new Map(),f=mount({exclusive:true,exclusivePage:true,saved})
 try{
  f.api.addresses=async()=>[];f.link();await f.mounted()
  assert.equal(f.preferredTime.value,'10:00–11:00');assert.equal(f.state.address,null)
  await f.selectSlot('11:00–12:00')
  assert.equal(f.preferredTime.value,'11:00–12:00');assert.equal(f.state.slotId,0)
  assert.equal(f.calls.some(c=>Array.isArray(c)&&c[0]==='direct-quote'),false)
 }finally{f.dispose()}
 const next=mount({exclusive:true,exclusivePage:true,saved})
 try{
  next.api.addresses=async()=>[];next.link();await next.mounted()
  assert.equal(next.preferredTime.value,'11:00–12:00')
  next.api.addresses=async()=>[{id:2,isDefault:true}]
  next.api.slots=async()=>({supported:true,items:[{id:302,start_time:'11:00',end_time:'12:00',available:true}]})
  next.chooseAddress();next.hide();next.selectAddress(2);next.show();await new Promise(r=>setTimeout(r,30))
  assert.equal(next.preferredTime.value,'11:00–12:00');assert.equal(next.state.slotId,302)
  assert.equal(next.calls.filter(c=>Array.isArray(c)&&c[0]==='direct-quote').at(-1)[3],302)
 }finally{next.dispose()}
})

test('choosing during slot loading wins over the late address response default',async()=>{
 const f=mount({exclusive:true,exclusivePage:true});let release
 try{
  f.api.slots=async()=>{await new Promise(r=>release=r);return {supported:true,items:[{id:10,name:'10:00–11:00',available:true},{id:30,name:'12:00–13:00',available:true}]}}
  f.link();const loading=f.mounted();await new Promise(r=>setImmediate(r))
  assert.equal(f.state.slotsLoading,true)
  await f.selectSlot('12:00–13:00');release();await loading
  assert.equal(f.preferredTime.value,'12:00–13:00');assert.equal(f.state.slotId,30)
  assert.equal(f.calls.filter(c=>Array.isArray(c)&&c[0]==='direct-quote').at(-1)[3],30)
 }finally{release?.();f.dispose()}
})

test('an empty or different server schedule preserves the chosen time without quoting a fabricated slot',async()=>{
 const f=mount({exclusive:true,exclusivePage:true})
 try{
  f.link();await f.mounted();const before=f.calls.filter(c=>Array.isArray(c)&&c[0]==='direct-quote').length
  f.api.slots=async()=>({supported:true,items:[]})
  await f.checkout();await f.selectSlot('12:00–13:00')
  assert.equal(f.preferredTime.value,'12:00–13:00');assert.equal(f.state.slotId,0);assert.equal(f.state.quote,null)
  f.api.slots=async()=>({supported:true,items:[{id:10,name:'17:00–18:00',available:true}]})
  await f.checkout()
  assert.equal(f.preferredTime.value,'12:00–13:00');assert.equal(f.state.slotId,0)
  assert.equal(f.calls.filter(c=>Array.isArray(c)&&c[0]==='direct-quote').length,before)
 }finally{f.dispose()}
})
