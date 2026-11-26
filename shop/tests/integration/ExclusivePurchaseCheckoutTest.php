<?php
// 仅合成测试库；回源 HTTP provider 由 runner 提供固定契约，不依赖真实用户或供应商。
$_SERVER['REMOTE_ADDR']='127.0.0.1';
$root=dirname(__DIR__,2);
define('APP_PATH',$root.'/application/');
if (getenv('EXCLUSIVE_TEST_FRAMEWORK')) {
    define('RUNTIME_PATH',getenv('EXCLUSIVE_TEST_RUNTIME').'/');
    require getenv('EXCLUSIVE_TEST_FRAMEWORK').'/base.php';
    \think\App::initCommon();
    \think\Loader::addNamespace('addons',$root.'/addons/');
} else require dirname(__DIR__).'/bootstrap.php';
use think\Db;
use addons\shop\library\v5\{CheckoutService,ExclusivePurchaseDeliveryService,Json,DomainException,AgentMealSourceService,PlanScheduleService};
class SyntheticExclusivePayment extends \addons\shop\library\v5\PaymentService {
    public static $gatewayCalls=0;
    protected function createGatewayPayment($orderSn,$userId,$openid,$notifyUrl) {
        self::$gatewayCalls++;
        return ['parameters'=>['synthetic_only'=>true]];
    }
}
if (getenv('HEALTHFLOW_RELEASE_TEST')!=='1') throw new RuntimeException('Dedicated synthetic database required');
config('database',array_merge(config('database'),[
    'type'=>'pgsql','hostname'=>'127.0.0.1','hostport'=>55449,'database'=>'healthflow_exclusive_confirmation_test',
    'username'=>'lin','password'=>'','prefix'=>'fa_','debug'=>false,
]));
set_exception_handler(function($error){fwrite(STDERR,(string)$error."\n");exit(1);});
if (getenv('EXCLUSIVE_TEST_ORDER_INPUT')) {
    $input=Json::decode(file_get_contents(getenv('EXCLUSIVE_TEST_ORDER_INPUT')),[]);
    if (!empty($input['verify'])) {
        $count=Db::name('shop_order')->where('request_id','like','race-'.$input['suffix'].'-%')->count();
        if ((int)$count!==1) throw new RuntimeException('Concurrent checkout persisted '.$count.' orders instead of one');
        echo "Concurrent PostgreSQL checkout persisted exactly one order for the last slot.\n";
    } else {
        try {
            $order=(new CheckoutService())->createOrder($input['uid'],['checkout_token'=>$input['token']],$input['request_id']);
            echo Json::encode(['code'=>0,'order_sn'=>$order['order_sn']]);
        } catch (DomainException $error) { echo Json::encode(['code'=>$error->getCode()]); }
    }
    exit(0);
}
\addons\shop\library\v5\Migrator::migrate();
function verify($ok,$message){if(!$ok)throw new RuntimeException($message);}
function rejects($fn,$code){try{$fn();}catch(DomainException $error){verify($error->getCode()===$code,'Wrong rejection '.$error->getCode().':'.$error->getMessage());return;}throw new RuntimeException('Expected rejection '.$code);}
$suffix=bin2hex(random_bytes(5));$now=time();
foreach(['user','shop_area','shop_goods','shop_goods_sku','shop_address','shop_delivery_area','shop_delivery_slot','shop_ingredient','shop_ingredient_sku_map','shop_sku_ingredient_component'] as $name) {
    Db::execute("SELECT setval(pg_get_serial_sequence('fa_".$name."','id'),(SELECT COALESCE(MAX(id),0)+1 FROM fa_".$name."),false)");
}
Db::startTrans();
try {
    $uid=Db::name('user')->insertGetId(['username'=>'exclusive_'.$suffix,'nickname'=>'Synthetic ONLY','status'=>'normal']);
    $client='exclusive-test';$userRef='uid:'.$uid;
    Db::name('shop_external_identity')->insert(['client_id'=>$client,'external_user_ref'=>$userRef,'user_id'=>$uid,'status'=>'normal','createtime'=>$now,'updatetime'=>$now]);
    Db::name('shop_miniapp_identity')->insert(['app_id'=>(string)getenv('SHOP_WECHAT_APP_ID'),'openid'=>'synthetic-'.$suffix,'user_id'=>$uid,'createtime'=>$now]);
    $areaIds=[];
    do { $district='99'.random_int(1000,9999); } while(Db::name('shop_delivery_area')->where('district_code',$district)->count());
    $city=substr($district,0,4).'00';
    foreach([['pid'=>0,'name'=>'合成省','adcode'=>'990000'],['pid'=>null,'name'=>'合成市','adcode'=>$city],['pid'=>null,'name'=>'合成区','adcode'=>$district]] as $index=>$area) {
        if($index)$area['pid']=$areaIds[$index-1];
        $areaIds[]=Db::name('shop_area')->insertGetId($area);
    }
    $address=Db::name('shop_address')->insertGetId(['user_id'=>$uid,'province_id'=>$areaIds[0],'city_id'=>$areaIds[1],'area_id'=>$areaIds[2],'receiver'=>'合成收件人','mobile'=>'13800000000','address'=>'仅合成测试地址','status'=>'normal']);
    $area=Db::name('shop_delivery_area')->insertGetId(['area_code'=>'synthetic-'.$suffix,'name'=>'合成测试区','province_code'=>'990000','city_code'=>$city,'district_code'=>$district,'status'=>'normal']);
    $slot=Db::name('shop_delivery_slot')->insertGetId(['area_id'=>$area,'slot_code'=>'synthetic-'.$suffix,'name'=>'10:00–11:00','start_time'=>'10:00','end_time'=>'11:00','service_scope'=>'plan','status'=>'normal','capacity'=>2,'used_capacity'=>0,'extra_fee_cent'=>100,'weekday_mask'=>'1,2,3,4,5,6,7','blackout_dates_json'=>'[]']);
    $skuIds=[];$ingredientIds=[];$initial=[];$requirements=[];
    foreach([['name'=>'大米','days'=>[6,7],'width'=>7,'quantity'=>2,'price'=>500],['name'=>'青菜','days'=>range(1,7),'width'=>3,'quantity'=>5,'price'=>300]] as $index=>$food) {
        $goods=Db::name('shop_goods')->insertGetId(['title'=>'合成'.$food['name'],'status'=>'normal','agent_visible'=>1,'catalog_status'=>'published','data_completeness'=>'complete','catalog_version'=>1]);
        $sid=Db::name('shop_goods_sku')->insertGetId(['goods_id'=>$goods,'sku_code'=>'synthetic-'.$suffix.'-'.$index,'price'=>number_format($food['price']/100,2,'.',''),'stocks'=>100,'reserved_stock'=>0,'safety_stock'=>0,'net_content_value'=>500,'net_content_unit'=>'g']);
        $ingredient=Db::name('shop_ingredient')->insertGetId(['ingredient_code'=>'synthetic-'.$suffix.'-'.$index,'name'=>$food['name'],'status'=>'normal']);
        $ingredientIds[]=$ingredient;
        Db::name('shop_ingredient_sku_map')->insert(['ingredient_id'=>$ingredient,'goods_id'=>$goods,'sku_id'=>$sid,'role'=>'main','net_value'=>500,'net_unit'=>'g','convert_ratio'=>1,'loss_rate'=>0,'review_status'=>'approved','status'=>'normal']);
        $skuIds[]=$sid;$initial[]=['sku_id'=>(string)$sid,'quantity'=>$food['quantity']];
        $requirements[]=['sku_id'=>(string)$sid,'food'=>$food['name'],'storage_rule'=>['review_status'=>'approved','condition'=>$index?'refrigerated':'ambient','max_days'=>$food['width'],'source'=>'synthetic-only','version'=>'test-v1'],
            'uses'=>array_map(static function($day){return ['day_no'=>$day,'weight'=>100];},$food['days'])];
    }
    $source=['kind'=>'exclusive_purchase','uid'=>$uid,'family_id'=>'synthetic-family','menu_version_ref'=>'exclusive-purchase:'.$suffix,'delivery_requirements'=>['version'=>1,'period_days'=>7,'items'=>$requirements],'test_items'=>$initial];
    $packageSn='exclusive-'.$suffix;
    $package=Db::name('shop_recommendation_package')->insertGetId(['package_sn'=>$packageSn,'agent_client_id'=>$client,'agent_task_id'=>$suffix,'user_id'=>$uid,'user_ref'=>$userRef,'family_ref'=>'exclusive-purchase:synthetic-family','menu_version_ref'=>$source['menu_version_ref'],'current_version'=>1,'nutrition_status'=>'reference_only','trade_status'=>'passed','status'=>'available','expires_at'=>$now+3600,'agent_source_proof_json'=>Json::encode(['payload'=>Json::encode($source),'signature'=>'synthetic-provider-fixture'])]);
    $version=Db::name('shop_recommendation_package_version')->insertGetId(['package_id'=>$package,'version_no'=>1,'recipes_snapshot_json'=>'[]']);
    foreach($initial as $index=>$item)Db::name('shop_recommendation_package_item')->insert(['package_version_id'=>$version,'sku_id'=>$item['sku_id'],'goods_id'=>Db::name('shop_goods_sku')->where('id',$item['sku_id'])->value('goods_id'),'quantity'=>$item['quantity'],'sort'=>$index]);
    $tier=['allowed_sku_ids'=>$skuIds,'allowed_recipe_version_ids'=>[1],'difference'=>'合成测试','budget'=>[['min_members'=>1,'max_members'=>20,'min_cent'=>0,'max_cent'=>999999,'includes_service_fee'=>false,'includes_delivery_fee'=>false]],'repeat'=>['dish_gap_days'=>0,'dish_max_per_7_days'=>7,'main_ingredient_max_per_7_days'=>7]];
    $config=['tiers'=>array_fill_keys(['economy','standard','premium'],$tier),'repeat_identity'=>[1=>['dish_key'=>'synthetic','main_ingredient_key'=>'synthetic']],'service_fee_cent'=>0,'quote_ttl_seconds'=>900,'estimate_ttl_seconds'=>900,'delivery'=>[
        'first_lead_days'=>1,'resume_lead_days'=>1,'cutoff_lead_days'=>0,'pause_max_days'=>7,'booking_horizon_days'=>21,'cutoff_time'=>'23:59','meal_lead_days'=>1,'storage_rules'=>array_column($requirements,'storage_rule','sku_id'),
        'regions'=>[['area_id'=>(string)$area,'fee_cent'=>500,'weekdays'=>range(1,7),'closed_dates'=>[],'daily_capacity'=>2]],
    ]];
    Db::name('shop_plan_policy')->insert(['policy_version'=>'synthetic-'.$suffix,'content_hash'=>hash('sha256',Json::canonical($config)),'config_json'=>Json::encode($config),'effective_at'=>$now,'status'=>'active','createtime'=>$now,'updatetime'=>$now]);
    $catalog=new \addons\shop\library\v5\CatalogService();
    verify($catalog->getSku($skuIds[0],true)['storage_rule']===$requirements[0]['storage_rule'],'Catalog must expose the actual approved storage rule');
    verify($catalog->versionSummary()['catalog_version']===$catalog->currentVersion(),'Catalog probe and full-page version must use one policy-bound identity');
    $badRules=$config;$badRules['delivery']['storage_rules'][$skuIds[0]]['review_status']='draft';
    rejects(static function()use($badRules){\addons\shop\library\v5\PlanPolicyService::validate($badRules);},50317);
    $payload=['source_type'=>'recommendation_package','source_ref'=>$packageSn,'source_version'=>1,'address_id'=>$address,'delivery_slot_id'=>$slot,'items'=>$initial];
    $deliveryService=new ExclusivePurchaseDeliveryService();$checkout=new CheckoutService();
    $dates=$deliveryService->availableDates($uid,$payload);
    verify(count($dates['items'])>1,'Actual available dates required');
    $payload['first_meal_date']=$dates['items'][0];
    $quote=$checkout->preview($uid,$payload);
    verify(count($quote['delivery_batches'])===3,'Fresh food must create three actual trips');
    verify($quote['goods_amount_cent']===2500 && $quote['shipping_fee_cent']===1800 && $quote['payable_amount_cent']===4300,'Whole-week fees must be quoted, no single-trip substitution');
    verify($quote['delivery_batches'][0]['delivery_date']===(new DateTimeImmutable($payload['first_meal_date']))->modify('-1 day')->format('Y-m-d'),'Delivery precedes first meal');
    $reduced=$payload;$reduced['items']=[$initial[0]];
    $one=$checkout->preview($uid,$reduced);
    verify(count($one['delivery_batches'])===1 && $one['shipping_fee_cent']===600 && $one['goods_amount_cent']===1000,'Deselection must remove both trips and their shipping fees');
    $short=$payload;$short['items'][1]['quantity']=2;rejects(static function()use($checkout,$uid,$short){$checkout->preview($uid,$short);},40963);
    rejects(static function()use($checkout,$uid,$payload){$bad=$payload;unset($bad['first_meal_date']);$checkout->preview($uid,$bad);},40001);
    rejects(static function()use($deliveryService,$uid,$payload){$deliveryService->availableDates($uid+99999,$payload);},40301);
    rejects(static function()use($uid,$packageSn,$initial){(new AgentMealSourceService())->assertCart($uid,[['source_type'=>'recommendation_package','source_ref'=>$packageSn,'source_version'=>1,'sku_id'=>$initial[0]['sku_id']]]);},40963);
    $blocked=$quote['delivery_batches'][1]['delivery_date'];
    Db::name('shop_delivery_slot')->where('id',$slot)->update(['blackout_dates_json'=>Json::encode([$blocked])]);
    rejects(static function()use($checkout,$uid,$quote){$checkout->createOrder($uid,['checkout_token'=>$quote['checkout_token']],'blackout-rejected');},40961);
    verify(!Db::name('shop_order_ext')->where('source_ref',$packageSn)->count(),'Rejected order must not persist');
    Db::name('shop_delivery_slot')->where('id',$slot)->update(['blackout_dates_json'=>'[]']);
    $policyRow=Db::name('shop_plan_policy')->where('policy_version','synthetic-'.$suffix)->find();
    $changedRules=$config;$changedRules['delivery']['storage_rules'][$skuIds[0]]['max_days']=3;
    $versionBefore=$catalog->currentVersion();
    Db::name('shop_plan_policy')->where('id',$policyRow['id'])->update(['config_json'=>Json::encode($changedRules),'content_hash'=>hash('sha256',Json::canonical($changedRules))]);
    verify($catalog->currentVersion()!==$versionBefore,'Rule activation must invalidate the catalog identity');
    rejects(static function()use($checkout,$uid,$quote){$checkout->createOrder($uid,['checkout_token'=>$quote['checkout_token']],'changed-storage-rule');},40906);
    Db::name('shop_plan_policy')->where('id',$policyRow['id'])->update(['config_json'=>$policyRow['config_json'],'content_hash'=>$policyRow['content_hash']]);
    // 回源 fixture 保留原 items，复现真实回源目录缓存未刷新时的本地事实变化。
    Db::name('shop_goods_sku')->where('id',$skuIds[0])->update(['net_content_value'=>250]);
    rejects(static function()use($checkout,$uid,$quote){$checkout->createOrder($uid,['checkout_token'=>$quote['checkout_token']],'changed-packaging');},40946);
    Db::name('shop_goods_sku')->where('id',$skuIds[0])->update(['net_content_value'=>500]);
    Db::name('shop_ingredient_sku_map')->where('sku_id',$skuIds[0])->update(['net_value'=>250]);
    rejects(static function()use($checkout,$uid,$quote){$checkout->createOrder($uid,['checkout_token'=>$quote['checkout_token']],'changed-composition');},40946);
    Db::name('shop_ingredient_sku_map')->where('sku_id',$skuIds[0])->update(['net_value'=>500]);
    $component=Db::name('shop_sku_ingredient_component')->insertGetId(['sku_id'=>$skuIds[0],'ingredient_id'=>$ingredientIds[0],'component_value'=>500,'component_unit'=>'g','allergen_flag'=>1,'data_source'=>'synthetic','data_version'=>'synthetic']);
    rejects(static function()use($checkout,$uid,$quote){$checkout->createOrder($uid,['checkout_token'=>$quote['checkout_token']],'changed-allergen');},40946);
    Db::name('shop_sku_ingredient_component')->where('id',$component)->delete();
    verify(!Db::name('shop_order_ext')->where('source_ref',$packageSn)->count(),'Changed product facts must never create orders');
    $order=$checkout->createOrder($uid,['checkout_token'=>$quote['checkout_token']],'synthetic-exclusive-'.$suffix);
    $saved=Json::decode(Db::name('shop_order_ext')->where('order_sn',$order['order_sn'])->value('pricing_snapshot_json'),[]);
    verify(Json::canonical($saved['delivery_batches'])===Json::canonical($quote['delivery_batches']),'Persisted order must contain precisely the reviewed schedule');
    verify($saved['shipping_fee_cent']===1800,'Actual order retains whole-week shipping');
    $payments=new SyntheticExclusivePayment();
    rejects(static function()use($payments,$uid,$order){$payments->createWechat($uid,$order['order_sn'],'','synthetic-blocked-payment');},50318);
    rejects(static function()use($payments,$order){$payments->onPaid($order['order_sn'],4300,'LOCAL-SYNTHETIC','','local_test');},50318);
    rejects(static function()use($uid,$order){\addons\shop\library\service\WechatPayService::createMiniProgramPayment($order['order_sn'],$uid,'synthetic-openid','');},50318);
    verify(SyntheticExclusivePayment::$gatewayCalls===0 && !Db::name('shop_payment_record')->where('order_sn',$order['order_sn'])->count() && !Db::name('shop_payment_transaction')->where('order_sn',$order['order_sn'])->count(),'Blocked payment must have zero intent, prepay and gateway side effects');
    verify((int)Db::name('shop_order')->where('order_sn',$order['order_sn'])->value('paystate')===0,'Test payment cannot mark a weekly preview as paid');
    $normal=Db::name('shop_order')->where('order_sn',$order['order_sn'])->find();unset($normal['id']);$normal['order_sn']='normal-'.$suffix;$normal['request_id']='synthetic-normal-'.$suffix;
    $normalId=Db::name('shop_order')->insertGetId($normal);
    $normalExt=Db::name('shop_order_ext')->where('order_sn',$order['order_sn'])->find();unset($normalExt['id']);
    $normalExt['order_id']=$normalId;$normalExt['order_sn']=$normal['order_sn'];$normalExt['checkout_token_hash']=hash('sha256','normal-'.$suffix);$normalExt['request_id']=$normal['request_id'];
    $normalPricing=$saved;unset($normalPricing['exclusive_delivery']);$normalPricing['delivery_batches']=[];$normalExt['pricing_snapshot_json']=Json::encode($normalPricing);
    Db::name('shop_order_ext')->insert($normalExt);
    $normalPayment=$payments->createWechat($uid,$normal['order_sn'],'','synthetic-normal-payment');
    verify(SyntheticExclusivePayment::$gatewayCalls===1 && !empty($normalPayment['payment_params']['synthetic_only']),'Ordinary payment path still reaches its provider boundary');
    $counts=ExclusivePurchaseDeliveryService::reservedCapacity($area,$quote['delivery_batches'][0]['delivery_date'],$slot);
    verify($counts===['area'=>1,'slot'=>1],'One dated reservation per trip must be counted');
    Db::name('shop_delivery_slot')->where('id',$slot)->update(['capacity'=>1]);
    rejects(static function()use($checkout,$uid,$payload){$checkout->preview($uid,$payload);},40961);
    Db::name('shop_order')->where('order_sn',$order['order_sn'])->update(['orderstate'=>1]);
    verify(ExclusivePurchaseDeliveryService::reservedCapacity($area,$quote['delivery_batches'][0]['delivery_date'],$slot)===['area'=>0,'slot'=>0],'Cancellation releases each future trip capacity');
    verify(!empty($checkout->preview($uid,$payload)['checkout_token']),'Cancelled reservation permits fresh quote');
    echo "PostgreSQL exclusive dates, quote, order snapshot, fee, ownership, cart bypass, capacity and blackout checks passed.\n";
    if (getenv('EXCLUSIVE_TEST_RACE_PATH')) {
        $tokens=[];
        for($index=0;$index<2;$index++)$tokens[]=$checkout->preview($uid,$payload)['checkout_token'];
        Db::commit();
        file_put_contents(getenv('EXCLUSIVE_TEST_RACE_PATH'),Json::encode(['uid'=>$uid,'tokens'=>$tokens,'suffix'=>$suffix]));
    }
} finally { Db::rollback(); }
