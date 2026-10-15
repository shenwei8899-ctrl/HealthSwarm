<?php

require dirname(__DIR__) . '/tests/bootstrap.php';

use think\Db;
use addons\shop\library\v5\Migrator;

Migrator::migrate();
if (config('database.type') === 'pgsql') {
    $table = config('database.prefix') . 'user';
    Db::execute("SELECT setval(pg_get_serial_sequence('{$table}', 'id'), GREATEST(COALESCE((SELECT MAX(id) FROM \"{$table}\"), 0), COALESCE(pg_sequence_last_value(pg_get_serial_sequence('{$table}', 'id')::regclass), 0), 1), true)");
}
if ((int)Db::name('shop_area')->count() === 0) {
    $prefix = config('database.prefix');
    $sql = str_replace('__PREFIX__', $prefix, file_get_contents(ROOT_PATH . 'addons/shop/data/area.sql'));
    if (config('database.type') === 'pgsql') $sql = str_replace('`', '"', $sql);
    Db::startTrans();
    try {
        Db::connect()->getPdo()->exec($sql);
        if (config('database.type') === 'pgsql') {
            Db::execute("SELECT setval(pg_get_serial_sequence('{$prefix}shop_area', 'id'), (SELECT MAX(id) FROM \"{$prefix}shop_area\"), true)");
        }
        Db::commit();
    } catch (\Exception $e) { Db::rollback(); throw $e; }
}
echo 'Mini-program schema ready; administrative regions: ' . Db::name('shop_area')->count() . "\n";
echo 'Delivery coverage configured: ' . Db::name('shop_delivery_area')->where('status', 'normal')->count() . "\n";
