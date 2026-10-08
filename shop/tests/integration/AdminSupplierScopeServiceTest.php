<?php

require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'bootstrap.php';

use addons\shop\library\service\AdminSupplierScopeService;
use think\Db;

function scopeAssertSame($expected, $actual, $message)
{
    if ($expected !== $actual) {
        throw new RuntimeException($message . ': expected ' . var_export($expected, true) . ', got ' . var_export($actual, true));
    }
}

$groupId = (int)Db::name('auth_group')->where('name', '供应商运营')->value('id');
$supplierIds = array_map('intval', Db::name('shop_supplier')->where('status', 'normal')->order('id ASC')->limit(2)->column('id'));
if (!$groupId || count($supplierIds) < 2) {
    throw new RuntimeException('Supplier scope fixtures are unavailable.');
}
$adminId = 990000 + random_int(1, 9999);
Db::startTrans();
try {
    Db::name('auth_group_access')->insert(['uid' => $adminId, 'group_id' => $groupId]);
    $unassigned = AdminSupplierScopeService::apply(Db::name('shop_supplier'), $adminId, 'id')->count();
    scopeAssertSame(0, $unassigned, 'Unassigned supplier operator must default to no data.');

    Db::name('shop_admin_supplier_scope')->insert(['admin_id' => $adminId, 'supplier_id' => $supplierIds[0], 'createtime' => time()]);
    $assigned = AdminSupplierScopeService::apply(Db::name('shop_supplier'), $adminId, 'id')->column('id');
    scopeAssertSame([$supplierIds[0]], array_map('intval', $assigned), 'Supplier operator must only see assigned suppliers.');

    $denied = false;
    try {
        AdminSupplierScopeService::assertAllowed($adminId, $supplierIds[1]);
    } catch (RuntimeException $e) {
        $denied = (int)$e->getCode() === 403;
    }
    scopeAssertSame(true, $denied, 'Supplier operator must not access another supplier.');
    AdminSupplierScopeService::assertAllowed(1, $supplierIds[1]);
    Db::rollback();
} catch (Throwable $e) {
    Db::rollback();
    throw $e;
}

echo "Admin supplier scope integration test passed.\n";
