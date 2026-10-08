<?php

require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'bootstrap.php';

use addons\shop\library\service\InventoryService;
use think\Db;

$suppliers = Db::name('shop_supplier')->where('code', 'in', ['ACCEPTANCE_SUPPLIER_A', 'ACCEPTANCE_SUPPLIER_B'])->where('status', 'normal')->select();
if (count($suppliers) !== 2) {
    throw new RuntimeException('Two acceptance suppliers must be available.');
}
$shared = Db::name('shop_supplier_sku')
    ->where('supplier_id', 'in', array_column($suppliers, 'id'))
    ->where('status', 'normal')
    ->group('goods_id,goods_sku_id')
    ->having('COUNT(DISTINCT supplier_id) >= 2')
    ->field('goods_id,goods_sku_id')
    ->find();
if (!$shared) {
    throw new RuntimeException('The same platform SKU must have two acceptance suppliers.');
}
$sources = InventoryService::listAvailableSources((int)$shared['goods_id'], (int)$shared['goods_sku_id'], 1);
$supplierIds = array_unique(array_map(function ($source) { return (int)$source['supplier_id']; }, $sources));
if (count(array_intersect($supplierIds, array_map('intval', array_column($suppliers, 'id')))) !== 2) {
    throw new RuntimeException('Both acceptance suppliers must expose saleable warehouse inventory.');
}
foreach (['商城运营', '订单客服', '供应商运营', '仓库人员', '财务人员'] as $role) {
    if (!Db::name('auth_group')->where('name', $role)->where('status', 'normal')->find()) {
        throw new RuntimeException('Missing admin role: ' . $role);
    }
}
echo "Acceptance supplier data and admin role test passed.\n";
