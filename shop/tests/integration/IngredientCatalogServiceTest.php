<?php
$_SERVER['REMOTE_ADDR']='127.0.0.1';
require dirname(__DIR__).'/bootstrap.php';
set_exception_handler(function($e){fwrite(STDERR,(string)$e."\n");exit(1);});
use think\Db;
use addons\shop\library\v5\{DomainException,IngredientCatalogService};
if(config('database.database')!=='healthflow_link_test'||getenv('HEALTHFLOW_RELEASE_TEST')!=='1')throw new RuntimeException('Dedicated fixture database required');
function ingredientCheck($ok,$message){if(!$ok)throw new RuntimeException($message);}
function ingredientReject($fn){try{$fn();}catch(DomainException $e){ingredientCheck($e->getCode()===40004,'Unexpected rejection');return;}throw new RuntimeException('Invalid input was accepted');}
$catalog=new IngredientCatalogService();$prefix='sync_'.bin2hex(random_bytes(4));
Db::startTrans();
try {
    $a=Db::name('shop_ingredient')->insertGetId(['ingredient_code'=>$prefix.'_a','name'=>$prefix.' literal %_','default_unit'=>'g','status'=>'normal']);
    $b=Db::name('shop_ingredient')->insertGetId(['ingredient_code'=>$prefix.'_b','name'=>$prefix.' second','default_unit'=>'g','status'=>'normal']);
    Db::name('shop_ingredient_alias')->insert(['ingredient_id'=>$a,'alias'=>$prefix.'-alias','status'=>'normal']);
    $goods=Db::name('shop_goods')->insertGetId(['goods_sn'=>$prefix,'title'=>'Synthetic ingredient SKU','status'=>'normal','agent_visible'=>1,'catalog_status'=>'published']);
    $sku=Db::name('shop_goods_sku')->insertGetId(['goods_id'=>$goods,'sku_code'=>$prefix,'stocks'=>20,'reserved_stock'=>0,'safety_stock'=>1,'price'=>10]);
    $map=['goods_id'=>$goods,'sku_id'=>$sku,'net_value'=>100,'net_unit'=>'g','convert_ratio'=>1,'loss_rate'=>0,'status'=>'normal'];
    $pending=Db::name('shop_ingredient_sku_map')->insertGetId($map+['ingredient_id'=>$a,'review_status'=>'pending']);
    $approved=Db::name('shop_ingredient_sku_map')->insertGetId($map+['ingredient_id'=>$b,'review_status'=>'approved']);
    $rows=$catalog->listIngredients(['q'=>$prefix,'limit'=>1]);
    ingredientCheck($rows['has_more']===true&&count($rows['items'])===1&&$rows['items'][0]['candidate_sku_ids']===[]&&$rows['items'][0]['mapping_status']==='pending_review','Pending maps must never become purchase candidates');
    $next=$catalog->listIngredients(['q'=>$prefix,'limit'=>1,'cursor'=>$rows['next_cursor']]);
    ingredientCheck($next['has_more']===false&&$next['items'][0]['candidate_sku_ids']===[(string)$sku],'Pagination must reach the approved available SKU');
    ingredientReject(function()use($catalog,$rows){$catalog->listIngredients(['q'=>'different','cursor'=>$rows['next_cursor']]);});
    ingredientCheck(count($catalog->listIngredients(['q'=>$prefix.'-alias'])['items'])===1,'Aliases must resolve ingredients');
    ingredientCheck(count($catalog->listIngredients(['q'=>'literal %_'])['items'])===1,'SQL wildcard characters must be literal');
    ingredientCheck(count($catalog->listIngredients(['q'=>"%' OR 1=1 --"])['items'])===0,'SQL text cannot broaden the query');
    foreach([0,201,'1.2',[]] as $limit)ingredientReject(function()use($catalog,$limit){$catalog->listIngredients(['limit'=>$limit]);});
    ingredientReject(function()use($catalog){$catalog->listIngredients(['q'=>['nested']]);});
    ingredientReject(function()use($catalog){$catalog->listIngredients(['cursor'=>'not-a-valid-cursor']);});
    foreach([['valid_to'=>time()-1],['valid_from'=>time()+100],['convert_ratio'=>0],['loss_rate'=>1],['goods_id'=>$goods+999]] as $change){
        Db::name('shop_ingredient_sku_map')->where('id',$approved)->update(array_merge(['valid_to'=>0,'valid_from'=>0,'convert_ratio'=>1,'loss_rate'=>0,'goods_id'=>$goods],$change));
        $item=$catalog->listIngredients(['q'=>$prefix.'_b'])['items'][0];
        ingredientCheck($item['candidate_sku_ids']===[],'Expired, invalid or mismatched mappings cannot become candidates');
    }
    Db::name('shop_ingredient_sku_map')->where('id',$approved)->update(['valid_to'=>0,'valid_from'=>0,'convert_ratio'=>1,'loss_rate'=>0,'goods_id'=>$goods]);
    Db::name('shop_goods_sku')->where('id',$sku)->update(['stocks'=>1]);
    ingredientCheck($catalog->listIngredients(['q'=>$prefix.'_b'])['items'][0]['candidate_sku_ids']===[],'Safety stock must not be offered for purchase');
    Db::name('shop_goods')->where('id',$goods)->update(['catalog_status'=>'draft']);
    ingredientCheck($catalog->listIngredients(['q'=>$prefix.'_b'])['items'][0]['candidate_sku_ids']===[],'Unpublished products must be unavailable');
} finally {Db::rollback();}
echo "Ingredient catalog passed: aliases, literal search, cursor integrity, pending/expired/invalid maps, stock and publication gates.\n";
