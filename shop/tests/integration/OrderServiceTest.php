<?php

require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'bootstrap.php';

use addons\shop\library\service\InventoryService;
use addons\shop\library\service\OrderService;
use think\Db;

function orderAssertSame($expected, $actual, $message)
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
    ->field('ws.*,g.stocks AS legacy_stocks')
    ->order('ws.id ASC')
    ->find();
if (!$stock) {
    throw new RuntimeException('No single-spec inventory is available for order testing.');
}

$userId = 800000 + random_int(1, 9999);
$idempotencyKey = 'TEST-ORDER-' . date('YmdHis') . '-' . bin2hex(random_bytes(3));
$originalAvailability = InventoryService::getAvailability($stock['id']);
$originalLegacyStocks = (int)$stock['legacy_stocks'];

Db::startTrans();
try {
    $addressId = Db::name('shop_address')->insertGetId([
        'user_id' => $userId,
        'province_id' => 0,
        'city_id' => 0,
        'area_id' => 0,
        'receiver' => '订单测试用户',
        'mobile' => '13800000000',
        'address' => '测试地址',
        'zipcode' => '',
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
        'nums' => 1,
        'createtime' => time(),
        'updatetime' => time(),
    ]);

    $order = OrderService::createFromCart(
        $addressId,
        $userId,
        [$cartId],
        0,
        '集成测试订单',
        $idempotencyKey,
        0,
        0,
        'TRACE-' . $idempotencyKey
    );
    $orderSn = $order->order_sn;
    orderAssertSame(1, Db::name('shop_order_ext')->where('order_id', $order->id)->count(), 'Order extension must be created');
    orderAssertSame(1, Db::name('shop_order_supplier')->where('order_id', $order->id)->count(), 'Supplier fulfillment order must be created');
    orderAssertSame(1, Db::name('shop_order_snapshot')->where('order_id', $order->id)->count(), 'Order snapshot must be created');
    orderAssertSame('LOCKED', Db::name('shop_stock_reservation')->where('order_sn', $orderSn)->value('status'), 'Order must lock inventory');

    $locked = InventoryService::getAvailability($stock['id']);
    orderAssertSame((int)$originalAvailability['locked_qty'] + 1, (int)$locked['locked_qty'], 'Creating an order must increase locked inventory');
    orderAssertSame($originalLegacyStocks, (int)Db::name('shop_goods')->where('id', $stock['goods_id'])->value('stocks'), 'Creating an order must not directly decrement legacy stocks');

    $repeated = OrderService::createFromCart($addressId, $userId, [$cartId], 0, '集成测试订单', $idempotencyKey);
    orderAssertSame((int)$order->id, (int)$repeated->id, 'Repeated order submission must return the same order');
    orderAssertSame(1, Db::name('shop_order_ext')->where('idempotency_key', $idempotencyKey)->count(), 'Idempotency key must remain unique');

    $cancelled = OrderService::cancelUnpaid($orderSn, $userId);
    orderAssertSame(1, (int)$cancelled->orderstate, 'Cancelling must update the legacy order state');
    orderAssertSame('RELEASED', Db::name('shop_stock_reservation')->where('order_sn', $orderSn)->value('status'), 'Cancelling must release inventory');
    $released = InventoryService::getAvailability($stock['id']);
    orderAssertSame((int)$originalAvailability['locked_qty'], (int)$released['locked_qty'], 'Cancelling must restore locked inventory');

    $cancelledAgain = OrderService::cancelUnpaid($orderSn, $userId);
    orderAssertSame((int)$cancelled->id, (int)$cancelledAgain->id, 'Repeated cancellation must be idempotent');

    Db::rollback();
} catch (Throwable $e) {
    Db::rollback();
    throw $e;
}

orderAssertSame(0, Db::name('shop_order_ext')->where('idempotency_key', $idempotencyKey)->count(), 'Order test data must roll back');
$afterRollback = InventoryService::getAvailability($stock['id']);
orderAssertSame((int)$originalAvailability['on_hand_qty'], (int)$afterRollback['on_hand_qty'], 'Order test rollback must preserve on-hand inventory');
orderAssertSame((int)$originalAvailability['locked_qty'], (int)$afterRollback['locked_qty'], 'Order test rollback must preserve locked inventory');

echo "OrderService integration test passed.\n";
