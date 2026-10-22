<?php
require dirname(__DIR__) . '/bootstrap.php';
use think\Db;
use addons\shop\library\v5\RecommendationPackageService;
use addons\shop\library\v5\Json;

if (config('database.database')!=='healthflow_link_test') throw new RuntimeException('Only the isolated local database is allowed');
$date=$argv[1]??date('Y-m-d');
if (!preg_match('/^\d{4}-\d{2}-\d{2}$/D',$date)) throw new RuntimeException('Invalid fixture date');
Db::startTrans();
try {
    $supplier=Db::name('shop_supplier')->where('supplier_code','LOCAL-NORMAL')->find();
    $supplierId=$supplier?$supplier['id']:Db::name('shop_supplier')->insertGetId(['supplier_code'=>'LOCAL-NORMAL','name'=>'本地联调供货商（不实际发货）','status'=>'normal']);
    $specs=[['tomato','番茄',500,'g','8.00'],['egg','鸡蛋',6,'piece','6.00'],['broccoli','西兰花',300,'g','5.00']];
    foreach ($specs as [$code,$name,$net,$unit,$price]) {
        $ingredient=Db::name('shop_ingredient')->where('ingredient_code','local-'.$code)->find();
        $iid=$ingredient?$ingredient['id']:Db::name('shop_ingredient')->insertGetId(['ingredient_code'=>'local-'.$code,'name'=>$name,'default_unit'=>$unit,'status'=>'normal']);
        $goods=Db::name('shop_goods')->where('goods_sn','LOCAL-NORMAL-'.$code)->find();
        $gid=$goods?$goods['id']:Db::name('shop_goods')->insertGetId(['title'=>$name.'（本地联调）','goods_sn'=>'LOCAL-NORMAL-'.$code,'freight_id'=>0,'image'=>'/assets/img/logo.png','catalog_status'=>'published','data_completeness'=>'complete','agent_visible'=>1,'status'=>'normal']);
        $sku=Db::name('shop_goods_sku')->where('sku_code','LOCAL-NORMAL-'.$code)->find();
        $sid=$sku?$sku['id']:Db::name('shop_goods_sku')->insertGetId(['goods_id'=>$gid,'sku_code'=>'LOCAL-NORMAL-'.$code,'sku_id'=>$net.$unit.'/包','stocks'=>100,'price'=>$price,'net_content_value'=>$net,'net_content_unit'=>$unit]);
        if (!Db::name('shop_ingredient_sku_map')->where('ingredient_id',$iid)->where('sku_id',$sid)->find()) Db::name('shop_ingredient_sku_map')->insert(['ingredient_id'=>$iid,'goods_id'=>$gid,'sku_id'=>$sid,'role'=>'primary','net_value'=>$net,'net_unit'=>$unit,'convert_ratio'=>1,'loss_rate'=>0,'priority'=>100,'review_status'=>'approved','status'=>'normal']);
        if (!Db::name('shop_supplier_sku')->where('supplier_id',$supplierId)->where('sku_id',$sid)->find()) Db::name('shop_supplier_sku')->insert(['supplier_id'=>$supplierId,'sku_id'=>$sid,'supplier_sku_code'=>'LOCAL-'.$code,'supplier_sku_name'=>$name,'purchase_price_cent'=>(int)round((float)$price*100),'stock_status'=>'available','stock_quantity'=>100,'priority'=>100,'status'=>'normal']);
    }
    foreach (Db::name('user')->where('username','in',['link_demo','link_other'])->select() as $member) {
        $ref='local-member:'.$member['id'];
        if (!Db::name('shop_external_identity')->where('client_id','local-normal-fixture')->where('external_user_ref',$ref)->find()) Db::name('shop_external_identity')->insert(['client_id'=>'local-normal-fixture','external_user_ref'=>$ref,'user_id'=>$member['id'],'status'=>'normal','createtime'=>time(),'updatetime'=>time()]);
        $task='local-normal:'.$date.':'.$member['id'];
        $existing=Db::name('shop_recommendation_package')->where('agent_task_id',$task)->find();
        if ($existing) continue;
        $result=(new RecommendationPackageService())->create('local-normal-fixture',[
            'agent_task_id'=>$task,'family_ref'=>'local-health:'.$member['id'],'user_ref'=>$ref,'menu_version_ref'=>'local-dinner-v1','catalog_version'=>'local-normal-v1','meal_date'=>$date,'expires_at'=>date(DATE_ATOM,strtotime($date.' 23:59:59')),
            'recipes'=>[
                ['recipe_ref'=>'local-tomato-egg','recipe_version'=>'1','recipe_name'=>'番茄炒蛋','meal_type'=>'dinner','ingredients'=>['番茄','鸡蛋'],'steps'=>['番茄洗净切块，鸡蛋打散。','先炒熟鸡蛋盛出，再将番茄炒软。','合炒并确保鸡蛋熟透，调味按实际需要确认。']],
                ['recipe_ref'=>'local-steamed-broccoli','recipe_version'=>'1','recipe_name'=>'蒸西兰花','meal_type'=>'dinner','ingredients'=>['西兰花'],'steps'=>['西兰花洗净切小朵。','蒸熟后装盘，按实际需要调味。']]
            ],
            'ingredient_requirements'=>[
                ['ingredient_code'=>'local-tomato','required_value'=>300,'required_unit'=>'g'],
                ['ingredient_code'=>'local-egg','required_value'=>2,'required_unit'=>'piece'],
                ['ingredient_code'=>'local-broccoli','required_value'=>300,'required_unit'=>'g']
            ],
            'nutrition_validation'=>['validation_id'=>'local-fixture-only','status'=>'passed','rules_version'=>'local-fixture','summary'=>'仅用于交易联调，未经个体化营养评估，不提供营养数值。']
        ],'local-normal-fixture');
        $row=Db::name('shop_recommendation_package')->where('package_sn',$result['package_sn'])->find();
        Db::name('shop_recommendation_package_version')->where('package_id',$row['id'])->update(['created_by_type'=>'local_fixture']);
    }
    Db::commit(); echo "Local dinner, reviewed ingredient maps and supplier fixtures ready for {$date}; no real nutrition or payment claims.\n";
} catch (\Throwable $e) { Db::rollback(); throw $e; }
