<?php
$_SERVER['REMOTE_ADDR']='127.0.0.1';
require dirname(__DIR__).'/bootstrap.php';
set_exception_handler(function ($e) { fwrite(STDERR,(string)$e."\n"); exit(1); });
use think\Db;
use addons\shop\library\v5\{AddressService, AgentMealSourceService, CatalogService, CheckoutService, DomainException, IdempotencyService, PurchaseListService, RecommendationPackageService};
if (config('database.database')!=='healthflow_link_test' || getenv('HEALTHFLOW_RELEASE_TEST')!=='1') throw new RuntimeException('Dedicated release database required');
function contractAssert($ok,$message) {if (!$ok) throw new RuntimeException($message);}
function contractReject($fn,$code) {try {$fn();} catch (DomainException $e) {contractAssert($e->getCode()===$code,'Wrong rejection '.$e->getCode());return;}throw new RuntimeException('Expected rejection '.$code);}
$suffix=bin2hex(random_bytes(6));
Db::startTrans();
try {
    $uid=Db::name('user')->insertGetId(['username'=>'checkout_contract_'.$suffix,'nickname'=>'Synthetic contract','status'=>'normal']);
    $client='synthetic-checkout-contract';$ref='synthetic:'.$suffix;
    Db::name('shop_external_identity')->insert(['client_id'=>$client,'external_user_ref'=>$ref,'user_id'=>$uid,'status'=>'normal','createtime'=>time(),'updatetime'=>time()]);
    $sid=Db::name('shop_goods_sku')->where('sku_code','LOCAL-NORMAL-tomato')->value('id');
    contractAssert((bool)$sid,'Explicit synthetic SKU required');
    $sku=(new CatalogService())->getSku($sid,true);
    $map=Db::name('shop_ingredient_sku_map')->where('sku_id',$sku['sku_id'])->where('review_status','approved')->find();
    $code=Db::name('shop_ingredient')->where('id',$map['ingredient_id'])->value('ingredient_code');
    contractAssert(!empty($sku['ingredients'][0]['ingredient_id']),'Actual catalog exposes ingredient identity');
    Db::name('shop_goods_sku')->where('id',$sku['sku_id'])->update(['stocks'=>1,'reserved_stock'=>0,'safety_stock'=>0]);
    $required=(float)$map['net_value']*(float)$map['convert_ratio']*(1-(float)$map['loss_rate']);
    $package=(new RecommendationPackageService())->create($client,[
        'agent_task_id'=>'contract-'.$suffix,'family_ref'=>'synthetic-family','user_ref'=>$ref,'menu_version_ref'=>'synthetic-v1','catalog_version'=>'synthetic-contract',
        'ingredient_requirements'=>[['ingredient_id'=>(string)$map['ingredient_id'],'ingredient_code'=>$code,'required_value'=>$required,'required_unit'=>$map['net_unit']]],
        'items'=>[['sku_id'=>$sku['sku_id'],'quantity'=>1]],'nutrition_validation'=>['status'=>'passed','summary'=>'synthetic protocol only'],
    ],'contract-'.$suffix);
    contractAssert($package['status']==='available','Recommendation available before confirmation');
    $packages=new PurchaseListService();
    $list=$packages->confirmRecommendation($uid,$package['package_sn'],1,'confirm-'.$suffix);
    contractAssert((float)Db::name('shop_purchase_match')->alias('m')->join('shop_purchase_item i','i.id=m.purchase_item_id')->join('shop_purchase_list l','l.id=i.purchase_list_id')->where('l.purchase_list_sn',$list['purchase_list_sn'])->value('m.match_score') < 10000,'Exact match score fits numeric(8,4)');
    $repeat=$packages->confirmRecommendation($uid,$package['package_sn'],1,'confirm-'.$suffix);
    contractAssert($repeat['purchase_list_sn']===$list['purchase_list_sn'],'Lost confirmation response reuses original list');
    contractAssert(Db::name('shop_recommendation_package')->where('package_sn',$package['package_sn'])->value('status')==='confirmed','Actual confirmation persisted');
    $source=new AgentMealSourceService();
    contractReject(function()use($source,$uid,$package){$source->assertSource($uid,'recommendation_package',$package['package_sn'],2);},40906);
    Db::name('shop_ingredient_sku_map')->where('id',$map['id'])->update(['review_status'=>'rejected']);
    contractReject(function()use($source,$uid,$package){$source->assertSource($uid,'recommendation_package',$package['package_sn'],1);},40946);
    Db::name('shop_ingredient_sku_map')->where('id',$map['id'])->update(['review_status'=>'approved']);
    $extraIngredient=Db::name('shop_ingredient')->where('ingredient_code','local-egg')->value('id');
    Db::execute('SAVEPOINT extra_composition');
    Db::name('shop_ingredient_sku_map')->insert(['ingredient_id'=>$extraIngredient,'goods_id'=>$sku['product_id'],'sku_id'=>$sku['sku_id'],'role'=>'component','net_value'=>10,'net_unit'=>'g','convert_ratio'=>1,'loss_rate'=>0,'priority'=>10,'review_status'=>'approved','status'=>'normal']);
    contractReject(function()use($source,$uid,$package){$source->assertSource($uid,'recommendation_package',$package['package_sn'],1);},40946);
    Db::execute('ROLLBACK TO SAVEPOINT extra_composition');
    Db::name('shop_sku_ingredient_component')->insert(['sku_id'=>$sku['sku_id'],'ingredient_id'=>$extraIngredient,'component_value'=>1,'component_unit'=>'g','allergen_flag'=>1,'data_source'=>'synthetic-contract','data_version'=>'v1']);
    contractReject(function()use($source,$uid,$package){$source->assertSource($uid,'recommendation_package',$package['package_sn'],1);},40946);
    Db::execute('ROLLBACK TO SAVEPOINT extra_composition');
    Db::name('shop_goods_sku')->where('id',$sku['sku_id'])->update(['net_content_value'=>999]);
    contractReject(function()use($source,$uid,$package){$source->assertSource($uid,'recommendation_package',$package['package_sn'],1);},40946);
    Db::execute('ROLLBACK TO SAVEPOINT extra_composition');
    Db::execute('RELEASE SAVEPOINT extra_composition');
    $address=(new AddressService())->save($uid,['name'=>'TEST ONLY','phone'=>'13800000000','region'=>'上海市 徐汇区','detail'=>'SYNTHETIC ONLY']);
    $checkout=new CheckoutService();
    $quote=$checkout->preview($uid,['source_type'=>'recommendation_package','source_ref'=>$package['package_sn'],'source_version'=>1,'address_id'=>$address['id']]);
    contractAssert(!empty($quote['checkout_token']),'Confirmed package can be quoted');
    $source->assertSource($uid,'recommendation_package',$package['package_sn'],1);
    $body=['checkout_token'=>$quote['checkout_token']];
    $create=function()use($checkout,$uid,$body,$suffix){return $checkout->createOrder($uid,$body,'order-'.$suffix);};
    $idempotency=new IdempotencyService();
    $order=$idempotency->run('commerce.order.create','miniapp:'.$uid,'order-'.$suffix,$body,$create);
    contractAssert((int)Db::name('shop_goods_sku')->where('id',$sku['sku_id'])->value('reserved_stock')===1,'Order reserves its only stock');
    $source->assertSource($uid,'recommendation_package',$package['package_sn'],1);
    $replay=$idempotency->run('commerce.order.create','miniapp:'.$uid,'order-'.$suffix,$body,$create);
    contractAssert($order['order_sn']===$replay['order_sn'],'Order replay is idempotent');
    contractAssert(Db::name('shop_order')->where('order_sn',$order['order_sn'])->count()===1,'Exactly one actual order persisted');
    echo "Recommendation confirmation, quote, order, reserved-stock provenance and rejection tests passed.\n";
} finally {Db::rollback();}
