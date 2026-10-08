<?php

require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'bootstrap.php';

use addons\shop\library\service\SupplierSyncService;
use think\Db;

function syncAssertSame($expected, $actual, $message)
{
    if ($expected !== $actual) {
        throw new RuntimeException($message . ': expected ' . var_export($expected, true) . ', got ' . var_export($actual, true));
    }
}

$goods = Db::name('shop_goods')->where('status', 'normal')->where('spectype', 0)->order('id ASC')->find();
if (!$goods) {
    throw new RuntimeException('No goods are available for supplier sync testing.');
}

$suffix = date('His') . bin2hex(random_bytes(3));
$now = time();
Db::startTrans();
try {
    $supplierId = Db::name('shop_supplier')->insertGetId([
        'code' => 'TEST-SYNC-' . $suffix,
        'name' => '供应商同步测试',
        'company_name' => '供应商同步测试',
        'fulfillment_mode' => 'SUPPLIER_DIRECT',
        'api_type' => 'MANUAL',
        'status' => 'normal',
        'createtime' => $now,
        'updatetime' => $now,
    ]);
    $supplierSkuId = Db::name('shop_supplier_sku')->insertGetId([
        'supplier_id' => $supplierId,
        'goods_id' => (int)$goods['id'],
        'goods_sku_id' => 0,
        'supplier_goods_code' => 'SYNC-G-' . $suffix,
        'supplier_sku_code' => 'SYNC-S-' . $suffix,
        'supply_price' => '3.00',
        'min_order_qty' => 1,
        'delivery_days' => 1,
        'fulfillment_mode' => 'SUPPLIER_DIRECT',
        'sync_status' => 'PENDING',
        'status' => 'normal',
        'createtime' => $now,
        'updatetime' => $now,
    ]);
    $warehouseId = Db::name('shop_warehouse')->insertGetId([
        'code' => 'TEST-SYNC-WH-' . $suffix,
        'name' => '供应商同步测试仓',
        'owner_type' => 'SUPPLIER',
        'owner_id' => $supplierId,
        'warehouse_type' => 'VIRTUAL_DIRECT',
        'status' => 'normal',
        'createtime' => $now,
        'updatetime' => $now,
    ]);
    $warehouseSkuId = Db::name('shop_warehouse_sku')->insertGetId([
        'warehouse_id' => $warehouseId,
        'supplier_id' => $supplierId,
        'supplier_sku_id' => $supplierSkuId,
        'goods_id' => (int)$goods['id'],
        'goods_sku_id' => 0,
        'on_hand_qty' => 10,
        'locked_qty' => 0,
        'unavailable_qty' => 0,
        'in_transit_qty' => 0,
        'version' => 0,
        'createtime' => $now,
        'updatetime' => $now,
    ]);

    $pricePayload = ['items' => [[
        'supplier_sku_id' => $supplierSkuId,
        'supply_price' => '4.25',
    ]]];
    $priceJob = SupplierSyncService::enqueue($supplierId, 'PRICE', 'PRICE-' . $suffix, $pricePayload);
    $samePriceJob = SupplierSyncService::enqueue($supplierId, 'PRICE', 'PRICE-' . $suffix, $pricePayload);
    syncAssertSame((int)$priceJob['id'], (int)$samePriceJob['id'], 'Enqueue must be idempotent for a supplier business key');
    $priceResult = SupplierSyncService::process($priceJob['id']);
    syncAssertSame('SUCCESS', $priceResult['status'], 'Price sync must succeed');
    syncAssertSame('4.25', (string)Db::name('shop_supplier_sku')->where('id', $supplierSkuId)->value('supply_price'), 'Price sync must update supplier price');

    $stockJob = SupplierSyncService::enqueue($supplierId, 'STOCK', 'STOCK-' . $suffix, ['items' => [[
        'supplier_sku_id' => $supplierSkuId,
        'warehouse_code' => 'TEST-SYNC-WH-' . $suffix,
        'on_hand_quantity' => 12,
    ]]]);
    $stockResult = SupplierSyncService::process($stockJob['id']);
    syncAssertSame('SUCCESS', $stockResult['status'], 'Stock sync must succeed');
    syncAssertSame(12, (int)Db::name('shop_warehouse_sku')->where('id', $warehouseSkuId)->value('on_hand_qty'), 'Stock sync must update warehouse inventory');
    syncAssertSame(1, Db::name('shop_stock_flow')->where('biz_type', 'SYNC_ADJUST')->where('biz_no', $stockJob['job_sn'] . ':0')->count(), 'Stock sync must create an inventory flow');

    $deliveryJob = SupplierSyncService::enqueue($supplierId, 'DELIVERY', 'DELIVERY-' . $suffix, ['items' => [[
        'province_id' => 0,
        'city_id' => 0,
        'area_id' => 0,
        'shipping_fee' => '6.00',
        'free_shipping_amount' => '99.00',
        'delivery_days' => 2,
    ]]]);
    syncAssertSame('SUCCESS', SupplierSyncService::process($deliveryJob['id'])['status'], 'Delivery sync must succeed');
    syncAssertSame('6.00', (string)Db::name('shop_supplier_delivery_region')->where('supplier_id', $supplierId)->value('shipping_fee'), 'Delivery sync must update shipping fee');

    $failedJob = SupplierSyncService::enqueue($supplierId, 'PRICE', 'FAILED-' . $suffix, ['items' => [[
        'supplier_sku_code' => 'MISSING',
        'supply_price' => '1.00',
    ]]], 'INBOUND', 1);
    $failedResult = SupplierSyncService::process($failedJob['id']);
    syncAssertSame('MANUAL_REQUIRED', $failedResult['status'], 'Exhausted retries must require manual compensation');
    $manual = SupplierSyncService::completeManually($failedJob['id'], ['confirmed' => true], 1, '测试人工补偿');
    syncAssertSame('SUCCESS', $manual['status'], 'Manual compensation must close a failed job');

    syncAssertSame(4, Db::name('shop_supplier_sync_log')->where('supplier_id', $supplierId)->count(), 'Every sync attempt must have an audit log');
    Db::rollback();
} catch (Throwable $e) {
    Db::rollback();
    throw $e;
}

echo "Supplier sync integration test passed.\n";
