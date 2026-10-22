<?php
// Synthetic fixtures may only operate on the dedicated identity database.
$_SERVER['REMOTE_ADDR'] = '127.0.0.1';
require dirname(__DIR__) . '/bootstrap.php';
use think\Db;
if (config('database.database') !== 'identity_commerce_test') throw new RuntimeException('Dedicated test database required');
$action = $argv[1] ?? '';
if ($action === 'seed') {
    $auth = new \app\common\library\Auth();
    if (!$auth->register('identity_existing', 'synthetic-password')) throw new RuntimeException($auth->getError());
    $id = (int)$auth->id;
    Db::name('shop_address')->insert(['user_id'=>$id,'receiver'=>'SYNTHETIC','mobile'=>'13800000000','address'=>'TEST ONLY','status'=>'normal']);
    Db::name('shop_carts')->insert(['user_id'=>$id,'goods_id'=>123,'goods_sku_id'=>456,'nums'=>2]);
    Db::name('shop_order')->insert(['user_id'=>$id,'order_sn'=>'IDENTITY-TEST-ORDER']);
    $auth->logout();
    $otherAuth = new \app\common\library\Auth();
    if (!$otherAuth->register('identity_other', 'synthetic-password')) throw new RuntimeException($otherAuth->getError());
    $otherAuth->logout();
} else {
    $id = (int)Db::name('user')->where('username', 'identity_existing')->value('id');
}
if (!$id) throw new RuntimeException('Fixture member missing');
$user = Db::name('user')->where('id',$id)->field('id,username,password,salt')->find();
$rows=[];
foreach (['shop_address','shop_carts','shop_order'] as $table) $rows[$table]=Db::name($table)->where('user_id',$id)->order('id')->select();
echo json_encode(['id'=>$id,'credentials_hash'=>hash('sha256',json_encode($user)),'business_hash'=>hash('sha256',json_encode($rows)),
    'members'=>Db::name('user')->count(),'mappings'=>Db::name('shop_external_identity')->count()]);
