<?php

require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'bootstrap.php';

use addons\shop\library\service\SupplyReportService;
use think\Db;

function mockOperationsAssert($condition, $message)
{
    if (!$condition) {
        throw new RuntimeException($message);
    }
}

mockOperationsAssert(Db::name('shop_brand')->count() >= 3, 'Brand management must contain MOCK data.');
mockOperationsAssert(Db::name('shop_supplier_sync_log')->where('biz_key', 'like', 'MOCK-%')->count() >= 7, 'Supplier sync history must contain MOCK data.');
mockOperationsAssert(Db::name('shop_supplier_reconciliation')->where('reconciliation_sn', 'like', 'MOCK-REC-%')->count() === 4, 'Supplier reconciliation must cover all demo statuses.');
mockOperationsAssert(Db::name('shop_stock_reservation')->where('reservation_sn', 'like', 'MOCK-RES-%')->count() === 4, 'Inventory reservations must cover the demo lifecycle.');
mockOperationsAssert(Db::name('shop_order')->where('order_sn', 'like', 'MOCK-ORD-%')->count() === 10, 'Ten MOCK orders must be available.');
mockOperationsAssert(Db::name('shop_order_supplier')->where('supplier_order_sn', 'like', 'MOCK-SUB-%')->count() === 10, 'Every MOCK order must have a supplier order.');
mockOperationsAssert(Db::name('shop_order_shipment')->where('shipment_sn', 'like', 'MOCK-SHIP-%')->count() === 5, 'Shipment management must contain lifecycle data.');
mockOperationsAssert(Db::name('shop_order_aftersales')->where('order_id', 'in', Db::name('shop_order')->where('order_sn', 'like', 'MOCK-ORD-%')->column('id'))->count() === 4, 'Aftersales tabs must contain MOCK data.');
mockOperationsAssert(Db::name('shop_refund_transaction')->where('refund_sn', 'like', 'MOCK-REF-%')->count() === 3, 'Refund reporting must contain MOCK data.');

$orderStates = Db::name('shop_order')->where('order_sn', 'like', 'MOCK-ORD-%')->group('orderstate')->column('orderstate');
foreach ([0, 1, 3, 4] as $state) {
    mockOperationsAssert(in_array($state, array_map('intval', $orderStates), true), 'Missing MOCK order state: ' . $state);
}
$supplierStatuses = Db::name('shop_order_supplier')->where('supplier_order_sn', 'like', 'MOCK-SUB-%')->column('status');
foreach (['PENDING_ACCEPT', 'ACCEPTED', 'PREPARING', 'SHIPPED', 'COMPLETED', 'CANCELLED', 'REJECTED'] as $status) {
    mockOperationsAssert(in_array($status, $supplierStatuses, true), 'Missing MOCK supplier-order status: ' . $status);
}
mockOperationsAssert(Db::name('shop_warehouse_sku')->alias('stock')
    ->join('__SHOP_SKU_EXT__ ext', 'ext.goods_id=stock.goods_id AND ext.goods_sku_id=stock.goods_sku_id')
    ->where('stock.on_hand_qty-stock.locked_qty-stock.unavailable_qty <= ext.safety_stock')->count() > 0, 'Low-stock workspace must contain MOCK data.');

foreach (['product_sales', 'orders', 'supplier_fulfillment', 'inventory', 'refunds', 'expiry'] as $reportType) {
    mockOperationsAssert(count(SupplyReportService::rows($reportType)) > 0, 'Report must contain MOCK data: ' . $reportType);
}

echo "MOCK commerce operations integration test passed.\n";
