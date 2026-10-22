<?php
require dirname(__DIR__) . '/bootstrap.php';
use think\Db;
use app\common\library\Auth;

if (config('database.database') !== 'healthflow_link_test') throw new RuntimeException('Isolated linking database required');
$file = ROOT_PATH . 'runtime/local-link/credentials.json';
if (!is_dir(dirname($file))) mkdir(dirname($file), 0700, true);
if (is_file($file)) { echo "Local linking fixtures already available.\n"; return; }
Db::startTrans();
try {
    $members = [];
    foreach (['link_demo', 'link_other'] as $account) {
        $password = bin2hex(random_bytes(12)); $salt = bin2hex(random_bytes(4));
        $uid = Db::name('user')->insertGetId(['username'=>$account, 'nickname'=>'本地联调测试会员', 'password'=>Auth::instance()->getEncryptPassword($password,$salt), 'salt'=>$salt, 'status'=>'normal', 'createtime'=>time(), 'updatetime'=>time()]);
        $members[] = ['account'=>$account, 'password'=>$password, 'id'=>$uid];
    }
    $gid = Db::name('shop_goods')->insertGetId(['title'=>'联调测试食材（不发货）', 'goods_sn'=>'LOCAL-LINK-20261013', 'freight_id'=>0, 'image'=>'/assets/img/logo.png', 'catalog_status'=>'published', 'data_completeness'=>'complete', 'agent_visible'=>1, 'status'=>'normal']);
    $sid = Db::name('shop_goods_sku')->insertGetId(['goods_id'=>$gid, 'sku_code'=>'LOCAL-LINK-SKU-20261013', 'stocks'=>100, 'price'=>'12.34', 'net_content_value'=>500, 'net_content_unit'=>'g']);
    Db::name('shop_delivery_area')->insert(['area_code'=>'LOCAL-LINK-310104', 'name'=>'联调测试配送范围', 'district_code'=>'310104', 'status'=>'normal']);
    Db::commit();
    file_put_contents($file, json_encode(['members'=>$members, 'sku_id'=>$sid], JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
    echo "Synthetic catalog, members and Shanghai Xuhui coverage created in isolated database. Credentials stored locally.\n";
} catch (\Throwable $e) { Db::rollback(); throw $e; }
