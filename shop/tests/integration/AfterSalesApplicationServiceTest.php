<?php

require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'bootstrap.php';

use addons\shop\library\service\AfterSalesApplicationService;
use addons\shop\library\service\AfterSalesService;
use addons\shop\library\service\OrderService;
use addons\shop\library\service\PaymentService;
use think\Db;

function afterSalesApplicationAssertSame($expected, $actual, $message)
{
    if ($expected !== $actual) {
        throw new RuntimeException($message . ': expected ' . var_export($expected, true) . ', got ' . var_export($actual, true));
    }
}

function afterSalesApplicationAssertThrows(callable $callback, $message)
{
    try {
        $callback();
    } catch (RuntimeException $e) {
        return;
    }
    throw new RuntimeException($message);
}

function createApplicationTestOrder(array $stock, $quantity, $userId, $key)
{
    $now = time();
    $addressId = Db::name('shop_address')->insertGetId([
        'user_id' => $userId,
        'province_id' => 0,
        'city_id' => 0,
        'area_id' => 0,
        'receiver' => '售后申请测试用户',
        'mobile' => '13800000000',
        'address' => '售后申请测试地址',
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
    $order = OrderService::createFromCart($addressId, $userId, [$cartId], 0, '', $key);
    PaymentService::markPaid($order->order_sn, 'system', 'TX-' . $key, $order->saleamount);
    return [
        Db::name('shop_order')->where('id', $order->id)->find(),
        Db::name('shop_order_goods')->where('order_sn', $order->order_sn)->find(),
    ];
}

$stock = Db::name('shop_warehouse_sku')
    ->alias('ws')
    ->join('__SHOP_GOODS__ g', 'g.id = ws.goods_id')
    ->where('ws.goods_sku_id', 0)
    ->where('ws.supplier_id', 0)
    ->where('ws.goods_id', 'not in', Db::name('shop_supplier_sku')->where('status', 'normal')->where('goods_sku_id', 0)->column('goods_id'))
    ->where('g.status', 'normal')
    ->where('ws.on_hand_qty - ws.locked_qty - ws.unavailable_qty >= 6')
    ->field('ws.*')
    ->order('ws.id ASC')
    ->find();
if (!$stock) {
    throw new RuntimeException('No single-spec inventory is available for after-sales application testing.');
}

Db::startTrans();
try {
    $userId = 500000 + random_int(1, 99999);
    $key = 'TEST-AFTERSALE-APPLICATION-' . bin2hex(random_bytes(4));
    list($order, $orderGoods) = createApplicationTestOrder($stock, 3, $userId, $key);
    $first = AfterSalesApplicationService::create($orderGoods['id'], $userId, 1, 1, '', '');
    afterSalesApplicationAssertSame(1, $first['quantity'], 'Application service must preserve the requested partial quantity');
    afterSalesApplicationAssertSame(1, (int)Db::name('shop_order_aftersales')->where('id', $first['aftersales_id'])->value('nums'), 'Created request must store the partial quantity');
    afterSalesApplicationAssertSame(2, (int)Db::name('shop_order_goods')->where('id', $orderGoods['id'])->value('salestate'), 'Refund-only request must enter pending refund state');
    afterSalesApplicationAssertSame(4, (int)Db::name('shop_order')->where('id', $order['id'])->value('orderstate'), 'Creating a request must put the order into after-sales state');

    afterSalesApplicationAssertThrows(function () use ($orderGoods, $userId) {
        AfterSalesApplicationService::create($orderGoods['id'], $userId, 1, 1, '重复申请');
    }, 'A pending request must block concurrent duplicate applications');
    afterSalesApplicationAssertSame(1, Db::name('shop_order_aftersales')->where('order_goods_id', $orderGoods['id'])->count(), 'Duplicate application must not create another request');
    afterSalesApplicationAssertThrows(function () use ($orderGoods, $userId) {
        AfterSalesApplicationService::create($orderGoods['id'], $userId + 1, 1, 1, '越权申请');
    }, 'Another user must not create after-sales requests');

    Db::name('shop_order_aftersales')->where('id', $first['aftersales_id'])->update(['status' => 2, 'updatetime' => time()]);
    AfterSalesService::approve($first['aftersales_id']);
    $second = AfterSalesApplicationService::create($orderGoods['id'], $userId, 1, 2, '申请剩余数量');
    afterSalesApplicationAssertSame(2, $second['quantity'], 'A completed partial refund must allow applying for the remaining quantity');
    afterSalesApplicationAssertSame(
        number_format((float)$orderGoods['realprice'], 2, '.', ''),
        bcadd($first['realprice'], $second['realprice'], 2),
        'Multiple partial refund amounts must add up to the original line amount'
    );

    list($unshippedOrder, $unshippedGoods) = createApplicationTestOrder(
        $stock,
        1,
        $userId + 10,
        $key . '-RETURN'
    );
    afterSalesApplicationAssertThrows(function () use ($unshippedGoods, $userId) {
        AfterSalesApplicationService::create($unshippedGoods['id'], $userId + 10, 2, 1, '未发货退货');
    }, 'An unshipped order must reject return-and-refund requests');
    afterSalesApplicationAssertSame(0, Db::name('shop_order_aftersales')->where('order_goods_id', $unshippedGoods['id'])->count(), 'Rejected return request must roll back completely');

    list($quantityOrder, $quantityGoods) = createApplicationTestOrder(
        $stock,
        2,
        $userId + 20,
        $key . '-QUANTITY'
    );
    afterSalesApplicationAssertThrows(function () use ($quantityGoods, $userId) {
        AfterSalesApplicationService::create($quantityGoods['id'], $userId + 20, 1, 3, '超量申请');
    }, 'An excessive refund quantity must be rejected');
    afterSalesApplicationAssertSame(0, Db::name('shop_order_aftersales')->where('order_goods_id', $quantityGoods['id'])->count(), 'Excessive request must not persist data');

    Db::rollback();
} catch (Throwable $e) {
    Db::rollback();
    throw $e;
}

echo "AfterSalesApplicationService integration test passed.\n";
