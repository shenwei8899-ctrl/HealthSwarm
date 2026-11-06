<?php

require dirname(__DIR__) . '/bootstrap.php';
set_exception_handler(function ($error) { fwrite(STDERR, (string)$error); exit(1); });

use addons\shop\library\v5\Migrator;
use think\Db;

if (config('database.database') !== 'partner_intake_test_20261101' || getenv('HEALTHFLOW_RELEASE_TEST') !== '1') {
    throw new RuntimeException('Dedicated partner intake test database required');
}
$path = ROOT_PATH . 'database/postgresql/migrations/20261101_partner_intake.sql';
$original = file_get_contents($path);
$canonical = str_replace(["\r\r\n", "\r\n"], "\n", $original);
$legacy = hash('sha256', str_replace("\n", "\r\n", $canonical));
try {
    Db::name('shop_schema_migration')->where('version', '20261101_partner_intake')->update(['checksum' => $legacy]);
    file_put_contents($path, $canonical);
    Migrator::migrate();
    $record = Db::name('shop_schema_migration')->where('version', '20261101_partner_intake')->find();
    if ($record['checksum'] !== $legacy) throw new RuntimeException('Existing migration audit must remain intact');
    $changed = str_replace('contact_wechat varchar(64)', 'contact_wechat varchar(65)', $canonical);
    if ($changed === $canonical) throw new RuntimeException('Negative control did not change SQL');
    file_put_contents($path, $changed);
    $rejected = false;
    try { Migrator::migrate(); }
    catch (RuntimeException $error) {
        if (strpos($error->getMessage(), 'Applied shop migration changed: 20261101_partner_intake') === false) throw $error;
        $rejected = true;
    }
    if (!$rejected) throw new RuntimeException('Modified migration was not rejected');
    echo "PostgreSQL migration passed: historical CRLF journal accepts LF source and rejects SQL changes.\n";
} finally {
    file_put_contents($path, $original);
}
