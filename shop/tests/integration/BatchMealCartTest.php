<?php
$_SERVER['REMOTE_ADDR']='127.0.0.1';
require dirname(__DIR__).'/bootstrap.php';
set_exception_handler(function($e){fwrite(STDERR,(string)$e."\n");exit(1);});
use think\Db;
use addons\shop\library\v5\{AddressService,AgentMealSourceService,CartService,CheckoutService,DomainException,Json,MealCommerceService,RecommendationPackageService};
if(config('database.database')!=='healthflow_link_test'||getenv('HEALTHFLOW_RELEASE_TEST')!=='1')throw new RuntimeException('Dedicated fixture database required');
function batchCheck($ok,$message){if(!$ok)throw new RuntimeException($message);}
function batchReject($fn,$code,$reason=null){
    try{$fn();}catch(DomainException $e){batchCheck($e->getCode()===$code,'Wrong rejection '.$e->getCode());if($reason!==null)batchCheck(($e->getDetails()['reason']??'')===$reason,'Wrong rejection reason');return;}
    throw new RuntimeException('Expected rejection '.$code);
}
function callbackControl($action='count'){
    $url=getenv('BATCH_SOURCE_FIXTURE_URL');
    if(!$url||!preg_match('~^http://127\.0\.0\.1:\d+$~D',$url))throw new RuntimeException('Local synthetic callback required');
    return json_decode(file_get_contents($url.'/'.$action),true);
}
Db::startTrans();
try{
    $suffix=bin2hex(random_bytes(5));$uid=Db::name('user')->insertGetId(['username'=>'batch_'.$suffix,'nickname'=>'SYNTHETIC ONLY','status'=>'normal']);
    $other=Db::name('user')->insertGetId(['username'=>'other_'.$suffix,'nickname'=>'SYNTHETIC ONLY','status'=>'normal']);
    Db::name('shop_external_identity')->insert(['client_id'=>'batch-fixture','external_user_ref'=>'uid:synthetic-owner','user_id'=>$uid,'status'=>'normal']);
    $items=[];
    for($i=0;$i<77;$i++){
        $gid=Db::name('shop_goods')->insertGetId(['title'=>'Synthetic '.$i,'goods_sn'=>'BATCH-'.$suffix.'-'.$i,'freight_id'=>0,'catalog_status'=>'published','data_completeness'=>'complete','agent_visible'=>1,'status'=>'normal']);
        $sid=Db::name('shop_goods_sku')->insertGetId(['goods_id'=>$gid,'sku_code'=>'BATCH-'.$suffix.'-'.$i,'sku_id'=>'500g','stocks'=>100,'price'=>'8.00','net_content_value'=>500,'net_content_unit'=>'g']);
        $items[]=['sku_id'=>(string)$sid,'quantity'=>1];
    }
    callbackControl('items?data='.rawurlencode(Json::encode($items)));
    $proof=['payload'=>Json::encode(['kind'=>'exclusive_purchase','uid'=>'synthetic-owner','family_id'=>'synthetic-family','menu_version_ref'=>'synthetic-menu']), 'signature'=>'synthetic-only'];
    $package=(new RecommendationPackageService())->create('batch-fixture',[
        'agent_task_id'=>'batch-'.$suffix,'family_ref'=>'exclusive-purchase:synthetic-family','user_ref'=>'uid:synthetic-owner','menu_version_ref'=>'synthetic-menu',
        'catalog_version'=>'synthetic','ingredient_requirements'=>[],'items'=>$items,'expires_at'=>date(DATE_ATOM,time()+1800),
        'nutrition_validation'=>['status'=>'reference_only'],'agent_source_proof'=>$proof,
    ],'batch-'.$suffix);
    $source=new AgentMealSourceService();$service=new MealCommerceService();$cart=new CartService();
    $sid=$items[0]['sku_id'];
    $direct=$cart->add($uid,$sid,2);
    batchCheck(isset($direct['cart_item_id'])&&count($direct['items'])===1,'Single add response preserved');
    $before=callbackControl()['count'];$start=microtime(true);
    $basket=$service->addToCart($uid,$package['package_sn'],1);
    $seconds=microtime(true)-$start;
    batchCheck(callbackControl()['count']-$before===1,'77 SKUs must cause exactly ONE source callback');
    $selected=array_values(array_filter($basket['items'],function($i){return $i['selected'];}));
    batchCheck(count($selected)===77,'Exactly 77 package rows selected');
    batchCheck(count($basket['items'])===78,'Unrelated cart item retained');
    foreach($selected as $line)batchCheck($line['quantity']===1&&$line['source_ref']===$package['package_sn'],'Source and quantities retained');
    $cart->update($uid,$selected[0]['cart_item_id'],3,$selected[0]['version']);
    $before=callbackControl()['count'];$again=$service->addToCart($uid,$package['package_sn'],1);
    batchCheck(callbackControl()['count']-$before===1,'Existing rows validate once too');
    foreach($again['items'] as $line)if($line['selected'])batchCheck($line['quantity']===1,'Retry replaces rather than doubles quantities');
    batchReject(function()use($service,$other,$package){$service->addToCart($other,$package['package_sn'],1);},40402);
    batchReject(function()use($service,$uid,$package){$service->addToCart($uid,$package['package_sn'],2);},40906);
    Db::name('shop_recommendation_package')->where('package_sn',$package['package_sn'])->update(['expires_at'=>time()-1]);
    batchReject(function()use($service,$uid,$package){$service->addToCart($uid,$package['package_sn'],1);},40906,'source_expired');
    batchReject(function()use($source,$uid,$package){$source->assertSource($uid,'recommendation_package',$package['package_sn'],1);},40906,'source_expired');
    Db::name('shop_recommendation_package')->where('package_sn',$package['package_sn'])->update(['expires_at'=>time()+1800]);
    callbackControl('deny');
    batchReject(function()use($service,$uid,$package){$service->addToCart($uid,$package['package_sn'],1);},40944);
    callbackControl('allow');
    batchReject(function()use($cart,$uid,$package){$cart->add($uid,'99999999',1,['source_type'=>'recommendation_package','source_ref'=>$package['package_sn'],'source_version'=>1]);},40301);
    Db::name('shop_goods_sku')->where('id',$sid)->update(['stocks'=>0]);
    batchReject(function()use($service,$uid,$package){$service->addToCart($uid,$package['package_sn'],1);},40917);
    Db::name('shop_goods_sku')->where('id',$sid)->update(['stocks'=>100]);
    $formal=Db::name('shop_recommendation_package')->insertGetId([
        'package_sn'=>'formal-'.$suffix,'agent_client_id'=>'batch-fixture','agent_task_id'=>'formal-'.$suffix,'user_id'=>$uid,
        'user_ref'=>'uid:synthetic-owner','family_ref'=>'synthetic','current_version'=>1,'menu_version_ref'=>'formal',
        'nutrition_status'=>'passed','trade_status'=>'passed','status'=>'available','expires_at'=>time()+1800,
    ]);
    $formalVersion=Db::name('shop_recommendation_package_version')->insertGetId([
        'package_id'=>$formal,'version_no'=>1,'menu_version_ref'=>'formal','recipes_snapshot_json'=>Json::encode([
            ['recipe_ref'=>'synthetic','recipe_version'=>'1','ingredients'=>['synthetic'],'steps'=>['synthetic']]
        ]),'issues_json'=>'[]',
    ]);
    Db::name('shop_recommendation_package_item')->insert(['package_version_id'=>$formalVersion,'goods_id'=>Db::name('shop_goods_sku')->where('id',$sid)->value('goods_id'),'sku_id'=>$sid,'quantity'=>1,'product_snapshot_json'=>'{}']);
    batchReject(function()use($service,$uid,$suffix){$service->addToCart($uid,'formal-'.$suffix,1);},40946);
    batchCheck(count(array_filter($cart->listItems($uid)['items'],function($i){return $i['selected'];}))===77,'Failed batch preserves previous selection');
    $province=Db::name('shop_area')->insertGetId(['pid'=>0,'name'=>'测试省','level'=>1,'adcode'=>'990000','status'=>'normal']);
    $city=Db::name('shop_area')->insertGetId(['pid'=>$province,'name'=>'测试市','level'=>2,'adcode'=>'990100','status'=>'normal']);
    Db::name('shop_area')->insert(['pid'=>$city,'name'=>'测试区','level'=>3,'adcode'=>'990101','status'=>'normal']);
    Db::name('shop_delivery_area')->insert(['area_code'=>'BATCH-'.$suffix,'name'=>'SYNTHETIC','district_code'=>'990101','status'=>'normal']);
    $address=(new AddressService())->save($uid,['name'=>'TEST ONLY','phone'=>'13800000000','region'=>'测试省 测试市 测试区','detail'=>'SYNTHETIC ONLY']);
    $refs=[];foreach($again['items'] as $line)if($line['selected'])$refs[]=['cart_item_id'=>$line['cart_item_id'],'version'=>$line['version']];
    $quote=(new CheckoutService())->preview($uid,['source_type'=>'cart','source_ref'=>(string)$uid,'source_version'=>1,'address_id'=>$address['id'],
        'cart_items'=>$refs,'meal_package_sn'=>$package['package_sn'],'meal_package_version'=>1]);
    batchCheck(!empty($quote['checkout_token'])&&count($quote['items'])===77,'Final quote generated for all selected items');
    batchCheck($quote['goods_amount_cent']===77*800,'Live prices used');
    $checkout=new CheckoutService();$orderPayload=['checkout_token'=>$quote['checkout_token']];
    Db::name('shop_goods_sku')->where('id',$sid)->update(['price'=>'9.00']);
    batchReject(function()use($checkout,$uid,$orderPayload){$checkout->createOrder($uid,$orderPayload,'synthetic-price-check');},40922);
    Db::name('shop_goods_sku')->where('id',$sid)->update(['price'=>'8.00','stocks'=>0]);
    batchReject(function()use($checkout,$uid,$orderPayload){$checkout->createOrder($uid,$orderPayload,'synthetic-stock-check');},40917);
    Db::name('shop_goods_sku')->where('id',$sid)->update(['stocks'=>100]);
    Db::name('shop_recommendation_package')->where('package_sn',$package['package_sn'])->update(['expires_at'=>time()-1]);
    batchReject(function()use($checkout,$uid,$orderPayload){$checkout->createOrder($uid,$orderPayload,'synthetic-source-check');},40906,'source_expired');
    batchCheck(Db::name('shop_order')->where('user_id',$uid)->count()===0,'Quotation never creates an order');
    echo Json::encode(['passed'=>true,'items'=>77,'source_callbacks_per_batch'=>1,'batch_seconds'=>round($seconds,3),'final_quote'=>true,'real_payment'=>false])."\n";
}finally{Db::rollback();}
