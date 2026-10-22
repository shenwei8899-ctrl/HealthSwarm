<?php
$_SERVER['REMOTE_ADDR']='127.0.0.1';
require dirname(__DIR__).'/bootstrap.php';
use think\Db;
use addons\shop\library\v5\AgentMemberService;
use addons\shop\library\v5\AgentSessionVerifier;
use addons\shop\library\v5\AgentMealSourceService;
use addons\shop\library\v5\CartService;
use addons\shop\library\v5\RecommendationPackageService;
use addons\shop\library\v5\Json;
use addons\shop\library\v5\DomainException;
if (config('database.database')!=='healthflow_link_test' || getenv('SHOP_AGENT_CLIENT_ID')!=='mainline-fixture') throw new RuntimeException('Dedicated fixture database required');
function mainlineCheck($ok,$message){if(!$ok)throw new RuntimeException($message);}
function mainlineReject($fn,$code){try{$fn();}catch(DomainException $e){mainlineCheck($e->getCode()===$code,'Unexpected rejection '.$e->getCode());return;}throw new RuntimeException('Expected rejection '.$code);}
if (($argv[1]??'')==='auto') {
    $auth=new \app\common\library\Auth();
    (new AgentMemberService())->exchange('Bearer synthetic-racing',[],$auth);
    echo (string)$auth->id;
    exit;
}
$uid=(int)Db::name('user')->where('username','link_demo')->value('id');
mainlineCheck($uid>0,'Synthetic member required');
$client='mainline-fixture';
Db::name('shop_address')->insert(['user_id'=>$uid,'receiver'=>'SYNTHETIC','mobile'=>'13800000000','address'=>'TEST ONLY','status'=>'normal']);
Db::name('shop_carts')->insert(['user_id'=>$uid,'goods_id'=>123,'goods_sku_id'=>456,'nums'=>2]);
Db::name('shop_order')->insert(['user_id'=>$uid,'order_sn'=>'MAINLINE-OLD-TEST-ORDER']);
Db::name('shop_external_identity')->insert(['client_id'=>$client,'external_user_ref'=>'uid:existing','user_id'=>$uid,'status'=>'normal','createtime'=>time(),'updatetime'=>time()]);
$user=Db::name('user')->where('id',$uid)->find();
$old=[];foreach(['shop_carts','shop_address','shop_order'] as $table)$old[$table]=Db::name($table)->where('user_id',$uid)->select();
$auth=new \app\common\library\Auth();
(new AgentMemberService())->exchange('Bearer synthetic-existing',[],$auth);
mainlineCheck((int)$auth->id===$uid,'Existing mapping must reuse member');
(new AgentMemberService())->exchange('Bearer synthetic-existing',[],$auth);
$after=Db::name('user')->where('id',$uid)->find();
mainlineCheck($user['password']===$after['password']&&$user['salt']===$after['salt'],'Credentials preserved');
foreach($old as $table=>$rows)mainlineCheck($rows===Db::name($table)->where('user_id',$uid)->select(),'Existing business rows preserved');
mainlineReject(function(){(new AgentSessionVerifier())->account(['account'=>['id'=>17,'uid'=>'existing']]);},40100);
$sku=Db::name('shop_goods_sku')->where('sku_code','LOCAL-NORMAL-tomato')->find();
$map=Db::name('shop_ingredient_sku_map')->where('sku_id',$sku['id'])->find();
Db::name('shop_ingredient_sku_map')->where('id',$map['id'])->update(['convert_ratio'=>0.8,'loss_rate'=>0.1]);
$proof=['payload'=>Json::encode(['kind'=>'conversation_package','uid'=>'existing']),'signature'=>'synthetic-trusted-test-proof'];
$payload=['agent_task_id'=>'mainline-package','family_ref'=>'conversation:test','user_ref'=>'uid:existing','menu_version_ref'=>'conversation:test','catalog_version'=>'test',
 'ingredient_requirements'=>[['ingredient_id'=>(string)$map['ingredient_id'],'ingredient_code'=>'local-tomato','required_value'=>'360.00','required_unit'=>'g']],
 'items'=>[['sku_id'=>(string)$sku['id'],'quantity'=>1]],'nutrition_validation'=>['status'=>'passed','summary'=>'synthetic protocol only'],'agent_source_proof'=>$proof];
$packages=new RecommendationPackageService();$package=$packages->create($client,$payload,'mainline-package');
mainlineCheck($package['status']==='available','Actual PHP package matching: '.Json::encode($package['trade_issues']));
mainlineCheck($packages->create($client,$payload,'mainline-package')['package_sn']===$package['package_sn'],'Idempotent package');
$source=['source_type'=>'recommendation_package','source_ref'=>$package['package_sn'],'source_version'=>1];
$cart=new CartService();$sourceService=new AgentMealSourceService();
mainlineReject(function()use($cart,$uid,$sku){$cart->add($uid,$sku['id'],1);},40301);
$other=(int)Db::name('shop_goods_sku')->where('sku_code','LOCAL-NORMAL-egg')->value('id');
mainlineReject(function()use($cart,$uid,$other,$source){$cart->add($uid,$other,1,$source);},40301);
$basket=$cart->add($uid,$sku['id'],1,$source);
$sourceService->assertCart($uid,[array_merge($source,['sku_id'=>(string)$sku['id']])]);
mainlineReject(function()use($sourceService,$uid,$other,$source){$sourceService->assertCart($uid,[array_merge($source,['sku_id'=>(string)$other])]);},40301);
Db::name('shop_recommendation_package')->where('package_sn',$package['package_sn'])->update(['agent_source_proof_json'=>'{}']);
mainlineReject(function()use($sourceService,$uid,$source){$sourceService->assertSource($uid,$source['source_type'],$source['source_ref'],1);},40301);
echo Json::encode(['passed'=>true,'existing_member_and_data_preserved'=>true,'real_sku_coverage_checked'=>true,'unrelated_sku_rejected'=>true,'missing_source_rejected'=>true]);
