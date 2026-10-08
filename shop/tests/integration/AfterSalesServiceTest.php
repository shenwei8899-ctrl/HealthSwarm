<?php

require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'bootstrap.php';

use addons\shop\library\service\AfterSalesService;
use addons\shop\library\service\FulfillmentService;
use addons\shop\library\service\InventoryService;
use addons\shop\library\service\OrderService;
use addons\shop\library\service\PaymentService;
use addons\shop\model\OrderGoods as OrderGoodsModel;
use think\Db;

function afterSalesAssertSame($expected, $actual, $message)
{
    if ($expected !== $actual) {
        throw new RuntimeException($message . ': expected ' . var_export($expected, true) . ', got ' . var_export($actual, true));
    }
}

function afterSalesAssertThrows(callable $callback, $message)
{
    try {
        $callback();
    } catch (RuntimeException $e) {
        return;
    }
    throw new RuntimeException($message);
}

function createAfterSalesOrder(array $stock, $quantity, $testKey)
{
    $userId = 600000 + random_int(1, 99999);
    $now = time();
    $addressId = Db::name('shop_address')->insertGetId([
        'user_id' => $userId,
        'province_id' => 0,
        'city_id' => 0,
        'area_id' => 0,
        'receiver' => '售后测试用户',
        'mobile' => '13800000000',
        'address' => '售后测试地址',
        'zipcode' => '',
        'usednums' => 0,
        'createtime' => $now,
        'updatetime' => $now,
        'isdefault' => 1,
        'status' => 'normal',
    ]);
    $cartId = Db::name('shop_carts')->insertGetId([
        'user_id' => $userId,
        'goods_id' => (int)$stock['goods_id'],
        'goods_sku_id' => (int)$stock['goods_sku_id'],
        'sceneval' => 1,
        'nums' => (int)$quantity,
        'createtime' => $now,
        'updatetime' => $now,
    ]);
    $order = OrderService::createFromCart($addressId, $userId, [$cartId], 0, '', $testKey);
    $orderGoods = Db::name('shop_order_goods')->where('order_sn', $order->order_sn)->find();
    $supplierOrder = Db::name('shop_order_supplier')->where('order_id', $order->id)->find();
    return [$order, $orderGoods, $supplierOrder];
}

function createApprovedAfterSales(array $order, array $orderGoods, $type, $quantity, $testKey)
{
    return Db::name('shop_order_aftersales')->insertGetId([
        'order_id' => (int)$order['id'],
        'order_goods_id' => (int)$orderGoods['id'],
        'user_id' => (int)$order['user_id'],
        'type' => (int)$type,
        'nums' => (int)$quantity,
        'realprice' => '0.00',
        'shippingfee' => '0.00',
        'refund' => '0.00',
        'reason' => '集成测试售后-' . $testKey,
        'status' => 2,
        'createtime' => time(),
        'updatetime' => time(),
    ]);
}

function payAndShip(array $order, array $supplierOrder, $testKey)
{
    PaymentService::markPaid($order['order_sn'], 'system', 'TX-' . $testKey, $order['saleamount']);
    FulfillmentService::markPreparing($supplierOrder['id']);
    return FulfillmentService::shipSupplierOrder(
        $supplierOrder['id'],
        '售后测试快递',
        'LOGISTIC-' . $testKey,
        'TEST'
    );
}

function runAfterSalesScenario(callable $scenario)
{
    Db::startTrans();
    try {
        $scenario();
        Db::rollback();
    } catch (Throwable $e) {
        Db::rollback();
        throw $e;
    }
}

$stock = Db::name('shop_warehouse_sku')
    ->alias('ws')
    ->join('__SHOP_GOODS__ g', 'g.id = ws.goods_id')
    ->where('ws.goods_sku_id', 0)
    ->where('ws.supplier_id', 0)
    ->where('ws.goods_id', 'not in', Db::name('shop_supplier_sku')->where('status', 'normal')->where('goods_sku_id', 0)->column('goods_id'))
    ->where('g.status', 'normal')
    ->where('ws.on_hand_qty - ws.locked_qty - ws.unavailable_qty >= 5')
    ->field('ws.*')
    ->order('ws.id ASC')
    ->find();
if (!$stock) {
    throw new RuntimeException('No single-spec inventory is available for after-sales testing.');
}

runAfterSalesScenario(function () use ($stock) {
    $key = 'TEST-AFTERSALE-PARTIAL-' . bin2hex(random_bytes(4));
    $before = InventoryService::getAvailability($stock['id']);
    list($orderModel, $orderGoods, $supplierOrder) = createAfterSalesOrder($stock, 3, $key);
    $order = $orderModel->toArray();
    $orderGoodsModel = OrderGoodsModel::get($orderGoods['id'], ['Order']);
    afterSalesAssertSame(3, $orderGoodsModel->getAvailableRefundQuantity(), 'New order line must expose its full refundable quantity');
    $expectedPartialPrice = bcdiv(bcmul((string)$orderGoods['realprice'], '1', 2), '3', 2);
    afterSalesAssertSame($expectedPartialPrice, $orderGoodsModel->getAvailableRefundRealprice(1), 'Partial refund amount must be prorated by quantity');
    PaymentService::markPaid($order['order_sn'], 'system', 'TX-' . $key, $order['saleamount']);
    $aftersalesId = createApprovedAfterSales($order, $orderGoods, 1, 1, $key);

    afterSalesAssertSame(true, AfterSalesService::approve($aftersalesId), 'First partial refund approval must change inventory');
    $afterApproval = InventoryService::getAvailability($stock['id']);
    afterSalesAssertSame((int)$before['locked_qty'] + 2, (int)$afterApproval['locked_qty'], 'Partial refund must release only the refunded quantity');
    afterSalesAssertSame(1, (int)Db::name('shop_order_goods_ext')->where('order_goods_id', $orderGoods['id'])->value('refunded_quantity'), 'Partial refund quantity must be accumulated');
    afterSalesAssertSame(2, OrderGoodsModel::get($orderGoods['id'], ['Order'])->getAvailableRefundQuantity(), 'Approved partial refund must reduce the remaining refundable quantity');
    afterSalesAssertSame(1, Db::name('shop_stock_reservation_adjustment')->where('aftersales_id', $aftersalesId)->where('adjustment_type', 'RELEASE')->count(), 'Partial refund must write one release adjustment');

    AfterSalesService::approve($aftersalesId);
    afterSalesAssertSame((int)$before['locked_qty'] + 2, (int)InventoryService::getAvailability($stock['id'])['locked_qty'], 'Repeated approval must not release inventory again');
    afterSalesAssertSame(1, Db::name('shop_stock_reservation_adjustment')->where('aftersales_id', $aftersalesId)->count(), 'Repeated approval must not duplicate adjustments');

    FulfillmentService::markPreparing($supplierOrder['id']);
    $shipment = FulfillmentService::shipSupplierOrder($supplierOrder['id'], '售后测试快递', 'LOGISTIC-' . $key, 'TEST');
    $afterShipping = InventoryService::getAvailability($stock['id']);
    afterSalesAssertSame((int)$before['on_hand_qty'] - 2, (int)$afterShipping['on_hand_qty'], 'Shipping after a partial refund must deduct only the remaining quantity');
    afterSalesAssertSame((int)$before['locked_qty'], (int)$afterShipping['locked_qty'], 'Shipping must consume the remaining lock');
    afterSalesAssertSame(2, (int)Db::name('shop_order_shipment_item')->where('shipment_id', $shipment['id'])->value('quantity'), 'Package quantity must exclude refunded items');
    afterSalesAssertSame(2, (int)Db::name('shop_order_goods_ext')->where('order_goods_id', $orderGoods['id'])->value('shipped_quantity'), 'Shipped quantity must exclude refunded items');
});

runAfterSalesScenario(function () use ($stock) {
    $key = 'TEST-AFTERSALE-SHIPPING-FEE-' . bin2hex(random_bytes(4));
    list($orderModel, $orderGoods) = createAfterSalesOrder($stock, 1, $key);
    $order = Db::name('shop_order')->where('id', $orderModel->id)->find();
    Db::name('shop_order')->where('id', $order['id'])->update([
        'shippingfee' => '6.00',
        'payamount' => bcadd((string)$order['payamount'], '6.00', 2),
        'saleamount' => bcadd((string)$order['saleamount'], '6.00', 2),
    ]);
    Db::name('shop_order_aftersales')->insert([
        'order_id' => (int)$order['id'],
        'order_goods_id' => (int)$orderGoods['id'],
        'user_id' => (int)$order['user_id'],
        'type' => 1,
        'nums' => 1,
        'realprice' => '0.00',
        'shippingfee' => '2.00',
        'refund' => '2.00',
        'reason' => '已退部分运费',
        'status' => 2,
        'createtime' => time(),
        'updatetime' => time(),
    ]);
    $model = OrderGoodsModel::get($orderGoods['id'], ['Order']);
    afterSalesAssertSame('4.00', $model->getAvailableRefundShippingfee(1), 'Refundable shipping fee must subtract prior refunds by numeric order ID');
});

runAfterSalesScenario(function () use ($stock) {
    $key = 'TEST-AFTERSALE-SHIPPED-REFUND-' . bin2hex(random_bytes(4));
    $before = InventoryService::getAvailability($stock['id']);
    list($orderModel, $orderGoods, $supplierOrder) = createAfterSalesOrder($stock, 2, $key);
    $order = $orderModel->toArray();
    payAndShip($order, $supplierOrder, $key);
    $afterShipping = InventoryService::getAvailability($stock['id']);
    $aftersalesId = createApprovedAfterSales($order, $orderGoods, 1, 1, $key);
    AfterSalesService::approve($aftersalesId);
    $afterRefund = InventoryService::getAvailability($stock['id']);
    afterSalesAssertSame((int)$afterShipping['on_hand_qty'], (int)$afterRefund['on_hand_qty'], 'A shipped refund without return must not restock inventory');
    afterSalesAssertSame((int)$afterShipping['unavailable_qty'], (int)$afterRefund['unavailable_qty'], 'A shipped refund without return must not change unavailable inventory');
    afterSalesAssertSame((int)$before['on_hand_qty'] - 2, (int)$afterRefund['on_hand_qty'], 'Shipping must remain deducted after a refund-only request');
});

runAfterSalesScenario(function () use ($stock) {
    $key = 'TEST-AFTERSALE-ACCEPTED-' . bin2hex(random_bytes(4));
    $before = InventoryService::getAvailability($stock['id']);
    list($orderModel, $orderGoods, $supplierOrder) = createAfterSalesOrder($stock, 2, $key);
    $order = $orderModel->toArray();
    payAndShip($order, $supplierOrder, $key);
    $aftersalesId = createApprovedAfterSales($order, $orderGoods, 2, 2, $key);
    AfterSalesService::approve($aftersalesId);
    afterSalesAssertSame(0, (int)Db::name('shop_order_goods_ext')->where('order_goods_id', $orderGoods['id'])->value('refunded_quantity'), 'Return refund must wait for inspection before completing quantity');
    afterSalesAssertSame(true, AfterSalesService::inspectReturn($aftersalesId, 2, 0, 'INSPECT-' . $key, 1, '全部合格'), 'First inspection must restock returned goods');
    $afterInspection = InventoryService::getAvailability($stock['id']);
    afterSalesAssertSame((int)$before['on_hand_qty'], (int)$afterInspection['on_hand_qty'], 'Accepted return must restore on-hand inventory');
    afterSalesAssertSame((int)$before['available_qty'], (int)$afterInspection['available_qty'], 'Accepted return must restore saleable inventory');
    afterSalesAssertSame(2, (int)Db::name('shop_order_goods_ext')->where('order_goods_id', $orderGoods['id'])->value('refunded_quantity'), 'Inspected return must update refunded quantity');
    afterSalesAssertSame(false, AfterSalesService::inspectReturn($aftersalesId, 2, 0, 'INSPECT-' . $key, 1, '全部合格'), 'Repeated inspection must be idempotent');
    afterSalesAssertSame((int)$before['on_hand_qty'], (int)InventoryService::getAvailability($stock['id'])['on_hand_qty'], 'Repeated inspection must not restock twice');
});

runAfterSalesScenario(function () use ($stock) {
    $key = 'TEST-AFTERSALE-MIXED-' . bin2hex(random_bytes(4));
    $before = InventoryService::getAvailability($stock['id']);
    list($orderModel, $orderGoods, $supplierOrder) = createAfterSalesOrder($stock, 3, $key);
    $order = $orderModel->toArray();
    payAndShip($order, $supplierOrder, $key);
    $aftersalesId = createApprovedAfterSales($order, $orderGoods, 2, 3, $key);
    AfterSalesService::approve($aftersalesId);
    AfterSalesService::inspectReturn($aftersalesId, 2, 1, 'INSPECT-' . $key, 1, '混合质检');
    $afterInspection = InventoryService::getAvailability($stock['id']);
    afterSalesAssertSame((int)$before['on_hand_qty'], (int)$afterInspection['on_hand_qty'], 'All physically returned units must increase on-hand inventory');
    afterSalesAssertSame((int)$before['unavailable_qty'] + 1, (int)$afterInspection['unavailable_qty'], 'Rejected return quantity must enter unavailable inventory');
    afterSalesAssertSame((int)$before['available_qty'] - 1, (int)$afterInspection['available_qty'], 'Only accepted return quantity may become saleable');
    afterSalesAssertSame('PARTIAL', Db::name('shop_aftersales_inspection')->where('aftersales_id', $aftersalesId)->value('status'), 'Mixed inspection must be recorded as partial');
});

runAfterSalesScenario(function () use ($stock) {
    $key = 'TEST-AFTERSALE-REJECTED-' . bin2hex(random_bytes(4));
    $before = InventoryService::getAvailability($stock['id']);
    list($orderModel, $orderGoods, $supplierOrder) = createAfterSalesOrder($stock, 2, $key);
    $order = $orderModel->toArray();
    payAndShip($order, $supplierOrder, $key);
    $aftersalesId = createApprovedAfterSales($order, $orderGoods, 2, 2, $key);
    AfterSalesService::approve($aftersalesId);
    AfterSalesService::inspectReturn($aftersalesId, 0, 2, 'INSPECT-' . $key, 1, '全部不合格');
    $afterInspection = InventoryService::getAvailability($stock['id']);
    afterSalesAssertSame((int)$before['on_hand_qty'], (int)$afterInspection['on_hand_qty'], 'Rejected physical returns must still restore on-hand inventory');
    afterSalesAssertSame((int)$before['unavailable_qty'] + 2, (int)$afterInspection['unavailable_qty'], 'All rejected returns must enter unavailable inventory');
    afterSalesAssertSame((int)$before['available_qty'] - 2, (int)$afterInspection['available_qty'], 'Rejected returns must not increase saleable inventory');
});

runAfterSalesScenario(function () use ($stock) {
    $key = 'TEST-AFTERSALE-INVALID-' . bin2hex(random_bytes(4));
    list($orderModel, $orderGoods, $supplierOrder) = createAfterSalesOrder($stock, 2, $key);
    $order = $orderModel->toArray();
    payAndShip($order, $supplierOrder, $key);
    $aftersalesId = createApprovedAfterSales($order, $orderGoods, 2, 2, $key);
    AfterSalesService::approve($aftersalesId);
    $beforeInspection = InventoryService::getAvailability($stock['id']);
    afterSalesAssertThrows(function () use ($aftersalesId, $key) {
        AfterSalesService::inspectReturn($aftersalesId, 1, 0, 'INSPECT-' . $key, 1, '数量错误');
    }, 'Inspection quantity mismatch must be rejected');
    afterSalesAssertSame(0, Db::name('shop_aftersales_inspection')->where('aftersales_id', $aftersalesId)->count(), 'Rejected inspection must not write an inspection record');
    $afterInspection = InventoryService::getAvailability($stock['id']);
    afterSalesAssertSame((int)$beforeInspection['on_hand_qty'], (int)$afterInspection['on_hand_qty'], 'Rejected inspection must not change on-hand inventory');
    afterSalesAssertSame((int)$beforeInspection['unavailable_qty'], (int)$afterInspection['unavailable_qty'], 'Rejected inspection must not change unavailable inventory');
});

echo "AfterSalesService integration test passed.\n";
