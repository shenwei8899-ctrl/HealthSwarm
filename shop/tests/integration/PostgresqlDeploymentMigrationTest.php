<?php
// 只允许显式独立数据库，验证真实安装入口和重复升级。
require dirname(__DIR__) . '/bootstrap.php';
set_exception_handler(function ($error) { fwrite(STDERR, (string)$error . "\n"); exit(1); });

use addons\shop\library\v5\Migrator;
use think\Db;

if (!preg_match('/^migration_clean_test(?:_[0-9]{14})?$/D', config('database.database')) || getenv('HEALTHFLOW_RELEASE_TEST') !== '1') {
    throw new RuntimeException('Only the isolated deployment migration database is allowed');
}
function deploymentMigrationAssert($value, $message)
{
    if (!$value) throw new RuntimeException($message);
}

$columns = function () {
    return Db::query("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema='public' AND (table_name='fa_shop_recommendation_package' AND column_name='agent_source_proof_json' OR table_name='fa_shop_ingredient_sku_map' AND column_name='source_ref')");
};
deploymentMigrationAssert(count($columns()) === 0, 'The baseline fixture already contains new columns');
$legacy = Db::name('shop_external_identity')->insertGetId(['client_id'=>'migration-fixture','external_user_ref'=>'uid:legacy','user_id'=>99999,'status'=>'normal','createtime'=>123,'updatetime'=>123]);
Migrator::migrate();
deploymentMigrationAssert(count($columns()) === 2, 'Default upgrade did not add both commerce columns');
deploymentMigrationAssert((bool)Db::query("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='fa_shop_catalog_review_log'"), 'Review log table is missing');
$versions = ['20261019_001_agent_meal_source', '20261021_commerce_catalog_review', '20261022_miniapp_user_access', '20261023_wechat_phone', '20261025_021_exclusive_plan_contract'];
foreach (['fa_shop_phone_binding', 'fa_shop_phone_binding_request'] as $table) {
    deploymentMigrationAssert((bool)Db::query("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=:table", ['table'=>$table]), 'Phone binding table is missing: ' . $table);
}
deploymentMigrationAssert((bool)Db::query("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='fa_shop_plan_policy'"), 'Plan policy table is missing');
deploymentMigrationAssert((bool)Db::query("SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='fa_shop_service_plan' AND column_name='basis_hash'"), 'Plan contract column is missing');
$phoneUser = Db::name('user')->insertGetId(['username'=>'migration-phone-fixture', 'nickname'=>'SYNTHETIC ONLY', 'password'=>'synthetic-unusable', 'salt'=>'fixture', 'status'=>'normal']);
Db::name('shop_phone_binding')->insert(['user_id'=>$phoneUser, 'country_code'=>'86', 'national_number'=>'13800000000', 'app_id'=>'wx0000000000000000', 'verification_source'=>'wechat_phone', 'verified_at'=>123]);
$phoneBefore = Db::name('shop_phone_binding')->where('user_id', $phoneUser)->find();
$row = Db::name('shop_external_identity')->where('id',$legacy)->find();
deploymentMigrationAssert($row['external_account_id']==='' && $row['external_account_name']==='' && $row['last_login_channel']==='unknown' && (int)$row['last_seen_at']===0 && (int)$row['last_wechat_verified_at']===0, 'Migration must preserve unknown login history');
$before = Db::name('shop_schema_migration')->where('version', 'in', $versions)->order('version')->select();
deploymentMigrationAssert(count($before) === 5, 'Migration versions were not recorded');
Migrator::migrate();
$after = Db::name('shop_schema_migration')->where('version', 'in', $versions)->order('version')->select();
deploymentMigrationAssert($before === $after, 'Repeated upgrade changed migration records');
deploymentMigrationAssert($phoneBefore === Db::name('shop_phone_binding')->where('user_id', $phoneUser)->find(), 'Repeated upgrade changed the synthetic phone binding');
$record = array_values(array_filter($after, function ($row) { return $row['version'] === '20261023_wechat_phone'; }))[0];
Db::name('shop_schema_migration')->where('id', $record['id'])->update(['checksum' => str_repeat('0', 64)]);
try {
    $rejected = false;
    try { Migrator::migrate(); }
    catch (RuntimeException $error) { $rejected = strpos($error->getMessage(), 'Applied shop migration changed:') === 0; }
    deploymentMigrationAssert($rejected, 'Changed applied migration was accepted');
} finally {
    Db::name('shop_schema_migration')->where('id', $record['id'])->update(['checksum' => $record['checksum']]);
}
echo "PostgreSQL deployment migrations passed: baseline upgrade, recorded versions, repeated execution, checksum rejection.\n";
