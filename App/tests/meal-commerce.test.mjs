import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import {ref,computed} from 'vue'
import {newMealCommerceState,createMealCommerceController,commerceMealView} from '../src/services/meal-commerce-state.js'
const copy=value=>structuredClone(value)

test('structured unsupported delivery preserves meal display and does not change the cart', async () => {
  const f = fixture();
  f.api.slots = async () => ({supported:false,message:'该地区暂停配送',items:[]});
  await f.controller.load();
  assert.equal(f.state.ready,true);
  assert.equal(f.state.menu.available,true);
  assert.equal(f.state.error,'');
  assert.equal(f.state.deliverySupported,false);
  await f.controller.prepare();
  assert.equal(f.state.checkoutError,'该地区暂停配送');
  assert.equal(f.calls.some(call=>['addMeal','quantity','select','quote'].includes(call[0])),false);
});

test('unknown meal delivery state requires retry before changing cart or quoting', async () => {
  const f = fixture();
  f.api.slots = async () => {throw Object.assign(new Error('offline'),{code:'NETWORK_ERROR'})};
  await f.controller.load();
  assert.equal(f.state.ready,true);
  assert.equal(f.state.deliverySupported,null);
  assert.equal(f.state.error,'');
  await f.controller.prepare();
  assert.match(f.state.checkoutError,/配送状态暂时无法确认/);
  assert.equal(f.calls.some(call=>call[0]==='addMeal'),false);
  f.api.slots=async()=>({supported:true,items:[]});
  await f.controller.load();
  await f.controller.prepare();
  assert.equal(f.calls.some(call=>call[0]==='quote'),true);
});
function fixture(){
  const state=newMealCommerceState(),calls=[]
  let account='A',members=[{id:1,name:'我',allergies:[]}],pending=null,failOrder=false,deferMenu=null
  const menu={available:true,package_sn:'A-DINNER',package_version:1,is_local_fixture:true,meal:'dinner',date:'2026-10-14',
    dishes:[{recipe_ref:'tomato-egg',recipe_version:'1',recipe_name:'番茄炒蛋',ingredients:['番茄','鸡蛋'],steps:['炒熟']}],
    items:[{ingredient_id:'tomato',quantity:1,sku:{sku_id:2,product_name:'番茄',sku_name:'500g/包',price_cent:800,available_quantity:10,net_content:{value:500,unit:'g'}}},
      {ingredient_id:'egg',quantity:1,sku:{sku_id:3,product_name:'鸡蛋',sku_name:'6个/包',price_cent:600,available_quantity:10}}]}
  let basket=[{cart_item_id:'ordinary',sku_id:'99',source_type:'direct',selected:true,quantity:1,version:1,valid:true}]
  const api={
    meal:async()=>{calls.push(['meal']);if(deferMenu)return deferMenu;return copy(menu)},
    cart:async()=>{calls.push(['cart']);return {items:copy(basket)}},
    addresses:async()=>[{id:7,isDefault:true}],slots:async()=>({items:[]}),pendingOrder:()=>pending,
    addMeal:async()=>{calls.push(['addMeal']);basket=basket.map(x=>({...x,selected:false}));for(const item of menu.items){
      const old=basket.find(l=>l.source_ref===menu.package_sn&&l.sku_id===String(item.sku.sku_id))
      const value={cart_item_id:'meal-'+item.sku.sku_id,sku_id:String(item.sku.sku_id),source_type:'recommendation_package',source_ref:menu.package_sn,source_version:menu.package_version,quantity:item.quantity,selected:true,valid:true,version:(old?.version||0)+1}
      basket=old?basket.map(l=>l.cart_item_id===old.cart_item_id?value:l):[...basket,value]
    }return {items:copy(basket)}},
    quantity:async(line,quantity)=>{assert.equal(basket.find(l=>l.cart_item_id===line.cart_item_id).version,line.version);calls.push(['quantity',line.cart_item_id,quantity]);basket=basket.map(l=>l.cart_item_id===line.cart_item_id?{...l,quantity,version:l.version+1}:l);return {items:copy(basket)}},
    select:async(line,selected)=>{assert.equal(basket.find(l=>l.cart_item_id===line.cart_item_id).version,line.version);calls.push(['select',line.cart_item_id,selected]);basket=basket.map(l=>l.cart_item_id===line.cart_item_id?{...l,selected,version:l.version+1}:l);return {items:copy(basket)}},
    quote:async(lines,address,slot,source)=>{calls.push(['quote',copy(lines.filter(l=>l.selected)),address,source.package_sn]);return {checkout_token:'quoted',expires_at:new Date(Date.now()+60000).toISOString(),payable_amount_cent:1600}},
    createOrder:async token=>{calls.push(['createOrder',token]);if(failOrder){pending={checkout_token:token};throw new Error('网络暂不可用，操作结果尚未确认')}return {order_sn:'ORDER-ONE'}},
    retryOrder:async()=>{calls.push(['retryOrder',copy(pending)]);pending=null;return {order_sn:'ORDER-ONE'}}
  }
  const controller=createMealCommerceController({state,api,scope:()=>account,context:()=>({enabled:true,meal:'dinner',date:menu.date,members,unsupported:false})})
  return {state,controller,calls,menu,api,member:value=>{members=value},switch:()=>{account='B';controller.sync()},failOrder:()=>{failOrder=true},defer:promise=>{deferMenu=promise}}
}

test('saved meal procurement reads its exact package and never substitutes the current menu', async () => {
  const f=fixture(), calls=[]
  f.api.meal=async()=>{ throw new Error('must not read the current menu') }
  f.api.mealPackage=async(sn,version)=>{calls.push([sn,version]);return copy(f.menu)}
  const controller=createMealCommerceController({state:f.state,api:f.api,scope:()=> 'A',
    context:()=>({enabled:true,meal:'dinner',date:f.menu.date,packageSn:'A-DINNER',packageVersion:1,members:[{id:1,name:'我',allergies:[]}],unsupported:false})})
  await controller.load()
  assert.equal(f.state.ready,true)
  assert.deepEqual(calls,[['A-DINNER',1]])
  assert.equal(f.calls.some(call=>['addMeal','quote','createOrder'].includes(call[0])),false)
})
test('opening meal is read-only and renders real SKU fields without demo nutrition',async()=>{
  const f=fixture();await f.controller.load();assert.deepEqual(f.calls.map(c=>c[0]),['meal','cart']);
  const view=commerceMealView(f.state.menu,{members:[{id:1,name:'我'}],quantities:f.state.quantities});
  assert.equal(view.dishes[0].name,'番茄炒蛋');assert.equal(view.products[0].priceCents,800);assert.equal(view.products[0].packLabel,'500g/包');
  assert.equal(view.nutrition,null);assert.deepEqual(view.memberNotes,[]);assert.equal(view.products[0].needLabel,'用量待确认');
})

test('an arrangement reads its exact package instead of the newest meal',async()=>{
  const f=fixture(), calls=[]
  f.api.meal=async()=>{throw new Error('must not read newest package')}
  f.api.mealPackage=async(sn,version)=>{calls.push([sn,version]);return f.menu}
  const controller=createMealCommerceController({state:f.state,api:f.api,scope:()=> 'A',
    context:()=>({enabled:true,meal:'dinner',date:f.menu.date,members:[],packageSn:'A-DINNER',packageVersion:1})})
  await controller.load()
  assert.deepEqual(calls,[['A-DINNER',1]])
  assert.equal(f.state.menu.package_sn,'A-DINNER')
})
test('meal checkout applies selected quantities and never quotes unrelated cart lines',async()=>{
  const f=fixture();await f.controller.load();f.controller.quantity('2',2);f.controller.toggle('3');await f.controller.prepare();
  const quoted=f.calls.find(c=>c[0]==='quote');assert.equal(quoted[1].length,1);assert.equal(quoted[1][0].sku_id,'2');assert.equal(quoted[1][0].quantity,2);assert.equal(quoted[3],'A-DINNER');
  const order=await f.controller.submit();assert.equal(order.order_sn,'ORDER-ONE');assert.equal(f.state.quote,null);
  await f.controller.submit();assert.equal(f.calls.filter(c=>c[0]==='createOrder').length,1);
})
test('member changes invalidate the quote and block stale purchase without fake regeneration',async()=>{
  const f=fixture();await f.controller.load();await f.controller.prepare();
  f.member([{id:2,name:'家人',allergies:[]}]);f.controller.membersChanged();assert.equal(f.state.quote,null);
  await f.controller.prepare();assert.match(f.state.checkoutError,/重配服务尚未接入/);assert.equal(f.calls.filter(c=>c[0]==='quote').length,1);
  f.member([{id:1,name:'我',allergies:[]}]);f.controller.membersChanged();assert.equal(f.state.contextIssue,'');
})
test('changed health data with the same member IDs blocks submitting an old quote',async()=>{
  const f=fixture();await f.controller.load();await f.controller.prepare();f.member([{id:1,name:'我',allergies:['鸡蛋']}]);
  await f.controller.submit();assert.match(f.state.checkoutError,/健康档案已调整/);assert.equal(f.state.quote,null);assert.equal(f.calls.filter(c=>c[0]==='createOrder').length,0);
})
test('missing address and expired quote cannot create an order',async()=>{
  const f=fixture();await f.controller.load();f.state.address=null;await f.controller.prepare();assert.equal(f.state.quote,null);assert.match(f.state.checkoutError,/配送地址/);
  f.state.address={id:7};await f.controller.prepare();f.state.quote.expires_at='2020-01-01T00:00:00Z';await f.controller.submit();assert.match(f.state.checkoutError,/报价已失效/);assert.equal(f.calls.filter(c=>c[0]==='createOrder').length,0);
})
test('uncertain order creation recovers the original intent instead of creating another order',async()=>{
  const f=fixture();await f.controller.load();await f.controller.prepare();f.failOrder();await f.controller.submit();assert.ok(f.state.pending);
  await f.controller.prepare();assert.match(f.state.checkoutError,/原订单/);assert.equal(f.calls.filter(c=>c[0]==='quote').length,1);
  const order=await f.controller.recover();assert.equal(order.order_sn,'ORDER-ONE');assert.equal(f.state.pending,null);assert.equal(f.state.quote,null);assert.equal(f.calls.filter(c=>c[0]==='createOrder').length,1);
})
test('switching accounts rejects late menu responses and removes private state',async()=>{
  const f=fixture();let complete;f.defer(new Promise(resolve=>{complete=resolve}));const load=f.controller.load();f.switch();complete(f.menu);await load;
  assert.equal(f.state.menu,null);assert.equal(f.state.address,null);assert.deepEqual(f.state.selected,[]);assert.equal(f.state.busy,false);
})
test('refresh failure invalidates an existing quote and blocks checkout until reload',async()=>{
  const f=fixture();await f.controller.load();await f.controller.prepare();f.api.meal=async()=>{throw new Error('菜单服务不可用')};await f.controller.load();
  assert.equal(f.state.ready,false);assert.equal(f.state.quote,null);await f.controller.submit();assert.match(f.state.checkoutError,/尚未确认/);assert.equal(f.calls.filter(c=>c[0]==='createOrder').length,0);
})
function originalPage(options){
  const f=fixture(),navigation=[],profile={members:[{id:1,name:'我',allergies:[]}],defaultDiners:[1]}
  let show
  const deps={ref,computed,watch:()=>{},isCommerceEnabled:true,isMockMode:true,
    getProfile:()=>profile,mealProfile:p=>p,getMealMembers:p=>p.members,localDate:()=>f.menu.date,
    mealFromRoute:m=>({breakfast:'早餐',lunch:'午餐',dinner:'晚餐'}[m]||'晚餐'),mealToRoute:m=>({'早餐':'breakfast','午餐':'lunch','晚餐':'dinner'}[m]),
    commerce:{...f.api,session:()=>({token:'test-token'})},commerceSessionEpoch:ref(0),
    useMealCommercePage:context=>{const controller=createMealCommerceController({state:f.state,api:f.api,scope:()=> 'A',context});return {state:f.state,plan:computed(()=>commerceMealView(f.state.menu,{...context(),quantities:f.state.quantities,contextIssue:f.state.contextIssue})),...controller}},
    subtotal:(items,selected)=>items.filter(i=>selected.includes(i.id)).reduce((sum,i)=>sum+i.priceCents*i.quantity,0),
    onLoad:callback=>callback(options),onShow:callback=>{show=callback},onUnload:()=>{}
  }
  globalThis.uni={navigateTo:target=>navigation.push(target.url)}
  const script=fs.readFileSync(new URL('../src/pages/shop/index.vue',import.meta.url),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
  const page=new Function('deps',`const {${Object.keys(deps)}}=deps;${script};return {commercePage,plan,selected,orderOpen,checkout,submitCommerceOrder}`)(deps)
  return {page,f,navigation,show:()=>show()}
}
test('meal entry retains its original page and checkout drawer; catalog entry is explicit',async()=>{
  for(const route of [{meal:'dinner'},{commerce:'1',meal:'dinner'}]){
    const h=originalPage(route);assert.equal(h.page.commercePage.value,false);await h.show();assert.equal(h.page.plan.value.dishes[0].name,'番茄炒蛋');
    await h.page.checkout();assert.equal(h.page.orderOpen.value,true);assert.deepEqual(h.navigation,[]);assert.equal(h.f.state.quote.checkout_token,'quoted');
    await h.page.submitCommerceOrder();assert.deepEqual(h.navigation,['/pages/orders/detail?id=ORDER-ONE']);
  }
  assert.equal(originalPage({commerce:'1'}).page.commercePage.value,true)
})
