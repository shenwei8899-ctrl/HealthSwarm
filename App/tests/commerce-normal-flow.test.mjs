import test from 'node:test'
import assert from 'node:assert/strict'
import { createCommerceClient } from '../src/services/commerce-client.js'
import { makeCommerceMealRecord } from '../src/services/commerce-meal-record.js'

function fixture(){
  const storage=new Map(),calls=[]
  let account='guest',revision=0,nextId='2',rejectLogin=false
  const client=createCommerceClient({baseUrl:'http://127.0.0.1:18081',parent:{scope:()=>account+':'+revision,storageScope:()=>account},
    storage:{get:k=>storage.get(k),set:(k,v)=>storage.set(k,v)},randomKey:()=>Math.random().toString(36),
    activateIdentity:({identity_namespace,userId})=>{account=identity_namespace+':'+userId;revision++},deactivateIdentity:()=>{account='guest';revision++},
    transport:async options=>{calls.push(options);if(options.url.endsWith('/session/login')&&rejectLogin)return {statusCode:401,data:{code:40100,message:'Bad login'}};
      const data=options.url.endsWith('/session/login')||options.url.endsWith('/session')?{identity_namespace:'instance-A',user:{id:nextId,token:'member-'+nextId},local_test_payment:true}:{items:[]};
      return {statusCode:200,data:{code:0,data}};
    }})
  return {client,calls,account:()=>account,other:()=>{nextId='3'},fail:()=>{rejectLogin=true}}
}
test('verified member becomes the local app identity and restores under its own storage scope',async()=>{
  const f=fixture();await f.client.login({account:'member',password:'test'});
  assert.equal(f.account(),'instance-A:2');assert.equal(f.client.session().userId,'2');
  await f.client.restore();await f.client.cart();assert.equal(f.calls.at(-1).header.token,'member-2');
  await f.client.logout();assert.equal(f.account(),'guest');await assert.rejects(f.client.cart());
})
test('a bad login cannot activate an identity, and a switched member cannot inherit another member token',async()=>{
  const f=fixture();await f.client.login({account:'one',password:'test'});f.other();await f.client.login({account:'two',password:'test'});
  assert.equal(f.account(),'instance-A:3');await f.client.cart();assert.equal(f.calls.at(-1).header.token,'member-3');
  f.fail();await assert.rejects(f.client.login({account:'bad',password:'bad'}));assert.equal(f.account(),'instance-A:3');
})
test('meal quote includes only a server menu reference and selected cart versions',async()=>{
  const f=fixture();await f.client.login({account:'one',password:'test'});
  await f.client.quote([{cart_item_id:'9',version:4,selected:true,valid:true}],7,0,{package_sn:'MEAL-1',package_version:3,dishes:['untrusted']});
  assert.equal(f.calls.at(-1).data.meal_package_sn,'MEAL-1');assert.equal(f.calls.at(-1).data.meal_package_version,3);
  assert.equal(f.calls.at(-1).data.dishes,undefined);assert.deepEqual(f.calls.at(-1).data.cart_items,[{cart_item_id:'9',version:4}]);
})
test('manual records preserve recipe and order provenance, individual intake, and unknown nutrition',()=>{
  const context={order_sn:'ORDER-1',meal_snapshot:{package_sn:'MEAL-1',package_version:3,menu_version_ref:'menu-3',meal:'dinner',dishes:[{recipe_name:'番茄炒蛋',recipe_ref:'r1',recipe_version:'2'},{recipe_name:'西兰花',recipe_ref:'r2',recipe_version:'1'}]}};
  const record=makeCommerceMealRecord(context,{oil:'不确定',people:[{memberId:1,memberName:'我',dishes:['番茄炒蛋'],portion:'一般',grams:'120'},{memberId:2,memberName:'家人',dishes:['西兰花'],portion:'少量',grams:''}]},{id:'RECORD-1',createdAt:'2026-10-14T12:00:00Z'});
  assert.equal(record.sourceOrderSn,'ORDER-1');assert.equal(record.recipeVersions[0].recipeVersion,'2');assert.equal(record.memberIntake[0].grams,120);
  assert.deepEqual(record.memberIntake[1].dishes,['西兰花']);assert.equal(record.kcal,null);assert.equal(record.isDemo,false);assert.equal(record.storage,'local-member');
  assert.throws(()=>makeCommerceMealRecord(context,{oil:'不确定',people:[]},{id:'bad'}));
  context.meal_snapshot.is_local_fixture=true;assert.equal(makeCommerceMealRecord(context,{oil:'不确定',people:[record.memberIntake[0]]},{id:'test'}).isDemo,true);
})
