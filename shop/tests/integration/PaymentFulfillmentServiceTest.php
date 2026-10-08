<?php

require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'bootstrap.php';

use addons\shop\library\service\FulfillmentService;
use addons\shop\library\service\InventoryService;
use addons\shop\library\service\OrderService;
use addons\shop\library\service\PaymentService;
use think\Db;

function fulfillmentAssertSame($expected, $actual, $message)
{
    if ($expected !== $actual) {
        throw new RuntimeException($message . ': expected ' . var_export($expected, true) . ', got ' . var_export($actual, true));
    }
}

$stock = Db::name('shop_warehouse_sku')
    ->alias('ws')
    ->join('__SHOP_GOODS__ g', 'g.id = ws.goods_id')
    ->where('ws.goods_sku_id', 0)
    ->where('ws.supplier_id', 0)
    ->where('ws.goods_id', 'not in', Db::name('shop_supplier_sku')->where('status', 'normal')->where('goods_sku_id', 0)->column('goods_id'))
    ->where('g.status', 'normal')
    ->where('ws.on_hand_qty - ws.locked_qty - ws.unavailable_qty >= 2')
    ->field('ws.*')
    ->order('ws.id ASC')
    ->find();
if (!$stock) {
    throw new RuntimeException('No inventory is available for fulfillment testing.');
}

$userId = 700000 + random_int(1, 9999);
$testKey = 'TEST-FULFILL-' . date('YmdHis') . '-' . bin2hex(random_bytes(3));
$original = InventoryService::getAvailability($stock['id']);

Db::startTrans();
try {
    $addressId = Db::name('shop_address')->insertGetId([
        'user_id' => $userId,
        'province_id' => 0,
        'city_id' => 0,
        'area_id' => 0,
        'receiver' => '履约测试用户',
        'mobile' => '13800000000',
        'address' => '测试地址',
        'usednums' => 0,
        'createtime' => time(),
        'updatetime' => time(),
        'isdefault' => 1,
        'status' => 'normal',
    ]);
    $cartId = Db::name('shop_carts')->insertGetId([
        'user_id' => $userId,
        'goods_id' => $stock['goods_id'],
        'goods_sku_id' => 0,
        'sceneval' => 1,
        'nums' => 2,
        'createtime' => time(),
        'updatetime' => time(),
    ]);
    $order = OrderService::createFromCart($addressId, $userId, [$cartId], 0, '', $testKey);
    $transactionId = 'TX-' . $testKey;
    fulfillmentAssertSame(true, PaymentService::markPaid($order->order_sn, 'system', $transactionId, $order->saleamount), 'First payment callback must mark the order paid');
    fulfillmentAssertSame(false, PaymentService::markPaid($order->order_sn, 'system', $transactionId, $order->saleamount), 'Repeated payment callback must be idempotent');

    $afterPayment = InventoryService::getAvailability($stock['id']);
    fulfillmentAssertSame((int)$original['on_hand_qty'], (int)$afterPayment['on_hand_qty'], 'Payment must not deduct on-hand inventory');
    fulfillmentAssertSame((int)$original['locked_qty'] + 2, (int)$afterPayment['locked_qty'], 'Payment must retain locked inventory');

    $supplierOrder = Db::name('shop_order_supplier')->where('order_id', $order->id)->find();
    $orderGoodsId = (int)Db::name('shop_order_goods')->where('order_sn', $order->order_sn)->value('id');
    FulfillmentService::markPreparing($supplierOrder['id']);
    $firstLogisticCode = 'TEST-LOGISTIC-A-' . $testKey;
    $shipment = FulfillmentService::shipPackage($supplierOrder['id'], '测试快递', $firstLogisticCode, [[
        'order_goods_id' => $orderGoodsId,
        'quantity' => 1,
    ]], 'TEST');
    fulfillmentAssertSame('SHIPPED', $shipment['status'], 'Partial shipping must create a shipped package');
    fulfillmentAssertSame('LOCKED', Db::name('shop_stock_reservation')->where('supplier_order_sn', $supplierOrder['supplier_order_sn'])->value('status'), 'Partial shipping must retain the remaining reservation');
    fulfillmentAssertSame('PART_SHIPPED', Db::name('shop_order_supplier')->where('id', $supplierOrder['id'])->value('status'), 'First package must mark the supplier order partially shipped');

    $afterShipping = InventoryService::getAvailability($stock['id']);
    fulfillmentAssertSame((int)$original['on_hand_qty'] - 1, (int)$afterShipping['on_hand_qty'], 'Shipping must deduct on-hand inventory');
    fulfillmentAssertSame((int)$original['locked_qty'] + 1, (int)$afterShipping['locked_qty'], 'Partial shipping must preserve remaining locked inventory');
    fulfillmentAssertSame(0, (int)Db::name('shop_order')->where('id', $order->id)->value('shippingstate'), 'Partial shipping must not mark the main order fully shipped');

    $repeatedShipment = FulfillmentService::shipPackage($supplierOrder['id'], '测试快递', $firstLogisticCode, [[
        'order_goods_id' => $orderGoodsId,
        'quantity' => 1,
    ]], 'TEST');
    fulfillmentAssertSame((int)$shipment['id'], (int)$repeatedShipment['id'], 'Repeated shipping must be idempotent');
    fulfillmentAssertSame(1, Db::name('shop_order_shipment')->where('supplier_order_id', $supplierOrder['id'])->count(), 'Repeated shipping must not create another package');

    $secondShipment = FulfillmentService::shipPackage($supplierOrder['id'], '测试快递', 'TEST-LOGISTIC-B-' . $testKey, [[
        'order_goods_id' => $orderGoodsId,
        'quantity' => 1,
    ]], 'TEST');
    fulfillmentAssertSame(true, (int)$secondShipment['id'] !== (int)$shipment['id'], 'Second package must create a separate shipment');
    fulfillmentAssertSame('DEDUCTED', Db::name('shop_stock_reservation')->where('supplier_order_sn', $supplierOrder['supplier_order_sn'])->value('status'), 'Final package must consume the supplier reservation');
    fulfillmentAssertSame('SHIPPED', Db::name('shop_order_supplier')->where('id', $supplierOrder['id'])->value('status'), 'Final package must mark the supplier order shipped');
    fulfillmentAssertSame(2, Db::name('shop_order_shipment')->where('supplier_order_id', $supplierOrder['id'])->count(), 'Two packages must be recorded');
    $afterSecondShipment = InventoryService::getAvailability($stock['id']);
    fulfillmentAssertSame((int)$original['on_hand_qty'] - 2, (int)$afterSecondShipment['on_hand_qty'], 'Both packages must deduct their shipped quantities');
    fulfillmentAssertSame((int)$original['locked_qty'], (int)$afterSecondShipment['locked_qty'], 'Final package must consume all locked inventory');
    fulfillmentAssertSame(1, (int)Db::name('shop_order')->where('id', $order->id)->value('shippingstate'), 'Shipping all quantities must update the main order');

    Db::rollback();
} catch (Throwable $e) {
    Db::rollback();
    throw $e;
}

$afterRollback = InventoryService::getAvailability($stock['id']);
fulfillmentAssertSame((int)$original['on_hand_qty'], (int)$afterRollback['on_hand_qty'], 'Fulfillment test rollback must preserve on-hand inventory');
fulfillmentAssertSame((int)$original['locked_qty'], (int)$afterRollback['locked_qty'], 'Fulfillment test rollback must preserve locked inventory');

echo "Payment and fulfillment integration test passed.\n";
