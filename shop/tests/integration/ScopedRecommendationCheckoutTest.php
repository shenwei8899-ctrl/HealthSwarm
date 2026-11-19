<?php
$_SERVER['REMOTE_ADDR']='127.0.0.1';
require dirname(__DIR__).'/bootstrap.php';
set_exception_handler(function ($e) { fwrite(STDERR,(string)$e."\n"); exit(1); });
use think\Db;
use addons\shop\library\v5\{AddressService,CatalogService,CheckoutService,DomainException,Json,RecommendationPackageService};
if (config('database.database')!=='healthflow_link_test' || getenv('HEALTHFLOW_RELEASE_TEST')!=='1') throw new RuntimeException('Dedicated fixture database required');
function scopedCheck($ok,$message) { if (!$ok) throw new RuntimeException($message); }
function scopedReject($work,$code) {
    try { $work(); } catch (DomainException $e) { scopedCheck($e->getCode()===$code,'Wrong rejection '.$e->getCode()); return; }
    throw new RuntimeException('Expected rejection '.$code);
}
Db::startTrans();
try {
    $suffix=bin2hex(random_bytes(5));
    $uid=Db::name('user')->insertGetId(['username'=>'scoped_'.$suffix,'nickname'=>'SYNTHETIC ONLY','status'=>'normal']);
    $ref='synthetic:'.$suffix;
    Db::name('shop_external_identity')->insert(['client_id'=>'scoped-fixture','external_user_ref'=>$ref,'user_id'=>$uid,'status'=>'normal']);
    $requirements=[]; $items=[]; $skus=[];
    foreach (['tomato','egg'] as $code) {
        $sid=Db::name('shop_goods_sku')->where('sku_code','LOCAL-NORMAL-'.$code)->value('id');
        scopedCheck((bool)$sid,'Explicit synthetic catalog required');
        Db::name('shop_goods_sku')->where('id',$sid)->update(['stocks'=>10,'reserved_stock'=>0,'safety_stock'=>0]);
        $sku=(new CatalogService())->getSku($sid,false);
        $map=Db::name('shop_ingredient_sku_map')->where('sku_id',$sid)->where('review_status','approved')->find();
        $requirements[]=['ingredient_id'=>(string)$map['ingredient_id'],'ingredient_code'=>'local-'.$code,
            'required_value'=>(float)$map['net_value'],'required_unit'=>$map['net_unit']];
        $items[]=['sku_id'=>(string)$sid,'quantity'=>1]; $skus[$code]=$sku;
    }
    $package=(new RecommendationPackageService())->create('scoped-fixture',[
        'agent_task_id'=>'scoped-'.$suffix,'family_ref'=>'synthetic-family','user_ref'=>$ref,
        'menu_version_ref'=>'synthetic-v1','catalog_version'=>'synthetic',
        'ingredient_requirements'=>$requirements,'items'=>$items,'nutrition_validation'=>['status'=>'passed'],
    ],'scoped-'.$suffix);
    $address=(new AddressService())->save($uid,['name'=>'TEST ONLY','phone'=>'13800000000','region'=>'上海市 徐汇区','detail'=>'SYNTHETIC ONLY']);
    $checkout=new CheckoutService();
    $payload=['source_type'=>'recommendation_package','source_ref'=>$package['package_sn'],'source_version'=>1,
        'address_id'=>$address['id'],'items'=>[['sku_id'=>$skus['tomato']['sku_id'],'quantity'=>2]]];
    Db::name('shop_goods_sku')->where('id',$skus['egg']['sku_id'])->update(['stocks'=>0]);
    $quote=$checkout->preview($uid,$payload);
    scopedCheck(count($quote['items'])===1 && $quote['items'][0]['quantity']===2,'Only selected quantities priced');
    scopedCheck($quote['payable_amount_cent']===2*$skus['tomato']['price_cent'],'Selected total uses live price');
    scopedCheck(!isset($quote['_validated_package']),'Internal source not returned');
    scopedCheck($quote['meal_snapshot']['purchased_sku_ids']===[(string)$skus['tomato']['sku_id']],'Snapshot binds purchased subset');
    scopedReject(function()use($checkout,$uid,$payload){$checkout->preview($uid,array_replace($payload,['items'=>[['sku_id'=>'99999999','quantity'=>1]]]));},40012);
    $orderPayload=['checkout_token'=>$quote['checkout_token']];
    $sid=$skus['tomato']['sku_id'];
    $price=Db::name('shop_goods_sku')->where('id',$sid)->value('price');
    Db::name('shop_goods_sku')->where('id',$sid)->update(['price'=>(float)$price+1]);
    scopedReject(function()use($checkout,$uid,$orderPayload){$checkout->createOrder($uid,$orderPayload,'price-changed');},40922);
    Db::name('shop_goods_sku')->where('id',$sid)->update(['price'=>$price,'stocks'=>1]);
    scopedReject(function()use($checkout,$uid,$orderPayload){$checkout->createOrder($uid,$orderPayload,'stock-changed');},40911);
    Db::name('shop_goods_sku')->where('id',$sid)->update(['stocks'=>10]);
    Db::name('shop_recommendation_package')->where('package_sn',$package['package_sn'])->update(['status'=>'expired']);
    scopedReject(function()use($checkout,$uid,$orderPayload){$checkout->createOrder($uid,$orderPayload,'source-changed');},40906);
    Db::name('shop_recommendation_package')->where('package_sn',$package['package_sn'])->update(['status'=>'available']);
    Db::name('shop_address')->where('id',$address['id'])->update(['address'=>'changed synthetic detail']);
    scopedReject(function()use($checkout,$uid,$orderPayload){$checkout->createOrder($uid,$orderPayload,'address-changed');},40906);
    Db::name('shop_address')->where('id',$address['id'])->update(['address'=>'SYNTHETIC ONLY']);
    $order=$checkout->createOrder($uid,$orderPayload,'scoped-order-'.$suffix);
    $lines=Db::name('shop_order_goods')->where('order_sn',$order['order_sn'])->select();
    scopedCheck(count($lines)===1,'Order contains exactly selected SKU');
    scopedCheck((int)Db::name('shop_goods_sku')->where('id',$sid)->value('reserved_stock')===2,'Selected quantity reserved');
    scopedCheck((int)Db::name('shop_goods_sku')->where('id',$skus['egg']['sku_id'])->value('reserved_stock')===0,'Excluded stock untouched');
    scopedCheck(Db::name('shop_carts')->where('user_id',$uid)->count()===0,'Direct quote and order never write cart');
    $stored=Json::decode(Db::name('shop_order_ext')->where('order_sn',$order['order_sn'])->value('pricing_snapshot_json'),[]);
    scopedCheck(!isset($stored['_validated_package']),'Internal source not persisted');
    echo "Scoped direct checkout passed: subset, quantity, excluded stock, no cart, price/stock/source/address rejection and actual order.\n";
} finally { Db::rollback(); }
