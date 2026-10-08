<?php

require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'bootstrap.php';

use addons\shop\library\service\AfterSalesApplicationService;
use addons\shop\library\service\AfterSalesService;
use addons\shop\library\service\CatalogQueryService;
use addons\shop\library\service\FulfillmentService;
use addons\shop\library\service\OrderQueryService;
use addons\shop\library\service\OrderService;
use addons\shop\library\service\PaymentService;
use think\Db;

function queryAssertSame($expected, $actual, $message)
{
    if ($expected !== $actual) {
        throw new RuntimeException($message . ': expected ' . var_export($expected, true) . ', got ' . var_export($actual, true));
    }
}

function queryAssertTrue($actual, $message)
{
    if (!$actual) {
        throw new RuntimeException($message);
    }
}

function queryAssertThrows(callable $callback, $message)
{
    try {
        $callback();
    } catch (RuntimeException $e) {
        return;
    }
    throw new RuntimeException($message);
}

$catalog = CatalogQueryService::listGoods(['page_size' => 2]);
queryAssertTrue(count($catalog['items']) > 0, 'Catalog list must return active goods');
$catalogDetail = CatalogQueryService::detail($catalog['items'][0]['id']);
queryAssertSame((int)$catalog['items'][0]['id'], (int)$catalogDetail['id'], 'Catalog detail must return the requested goods');
queryAssertTrue(isset($catalogDetail['composition'], $catalogDetail['allergen_tags'], $catalogDetail['origin'], $catalogDetail['skus']), 'Catalog detail must expose supply-chain product fields');
queryAssertTrue(count($catalogDetail['skus']) > 0, 'Catalog detail must expose at least one SKU representation');
$firstAvailability = $catalogDetail['skus'][0]['availability'];
queryAssertTrue(array_key_exists('sources', $firstAvailability), 'SKU availability must expose fulfillment sources');
if ($firstAvailability['sources']) {
    queryAssertTrue(!array_key_exists('supply_price', $firstAvailability['sources'][0]), 'Public catalog must not expose supplier cost price');
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
    throw new RuntimeException('No inventory is available for order query testing.');
}

Db::startTrans();
try {
    $userId = 300000 + random_int(1, 99999);
    $key = 'TEST-ORDER-QUERY-' . bin2hex(random_bytes(4));
    $now = time();
    $addressId = Db::name('shop_address')->insertGetId([
        'user_id' => $userId,
        'province_id' => 0,
        'city_id' => 0,
        'area_id' => 0,
        'receiver' => '订单查询测试用户',
        'mobile' => '13812345678',
        'address' => '订单查询测试地址',
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
        'goods_sku_id' => 0,
        'sceneval' => 1,
        'nums' => 2,
        'createtime' => $now,
        'updatetime' => $now,
    ]);
    $order = OrderService::createFromCart($addressId, $userId, [$cartId], 0, '查询测试', $key);
    $detail = OrderQueryService::detail($order->order_sn, $userId);
    queryAssertSame('138****5678', $detail['mobile'], 'Order detail must mask the mobile number');
    queryAssertSame(1, count($detail['supplier_orders']), 'Order detail must include supplier fulfillment orders');
    queryAssertSame(1, count($detail['items']), 'Order detail must include order items');
    queryAssertTrue(isset($detail['items'][0]['goods_snapshot'], $detail['items'][0]['delivery_snapshot']), 'Order item must expose immutable snapshots');
    queryAssertThrows(function () use ($order, $userId) {
        OrderQueryService::detail($order->order_sn, $userId + 1);
    }, 'Another user must not read an order');

    $orders = OrderQueryService::listOrders($userId, ['page_size' => 10]);
    queryAssertSame(1, (int)$orders['pagination']['total'], 'Order list must include the created order');
    $pendingOrders = OrderQueryService::listOrders($userId, ['biz_status' => 'PENDING_PAYMENT,PAID', 'orderstate' => 0]);
    queryAssertSame(1, (int)$pendingOrders['pagination']['total'], 'Order list must support grouped business-status filters');
    queryAssertSame(false, OrderQueryService::paymentStatus($order->order_sn, $userId)['paid'], 'New order must initially be unpaid');

    PaymentService::markPaid($order->order_sn, 'system', 'TX-' . $key, $order->saleamount);
    queryAssertSame(true, OrderQueryService::paymentStatus($order->order_sn, $userId)['paid'], 'Payment query must reflect a successful payment');
    $supplierOrder = Db::name('shop_order_supplier')->where('order_id', $order->id)->find();
    FulfillmentService::markPreparing($supplierOrder['id']);
    FulfillmentService::shipSupplierOrder($supplierOrder['id'], '查询测试快递', 'LOGISTIC-' . $key, 'TEST');
    $shipments = OrderQueryService::shipments($order->order_sn, $userId);
    queryAssertSame(1, count($shipments), 'Shipment query must include the generated package');
    queryAssertSame(2, (int)$shipments[0]['items'][0]['quantity'], 'Shipment package must include the actual shipped quantity');
    queryAssertSame((string)$detail['items'][0]['title'], (string)$shipments[0]['items'][0]['title'], 'Shipment package must expose user-facing goods details');

    $orderGoodsId = (int)$detail['items'][0]['id'];
    $application = AfterSalesApplicationService::create($orderGoodsId, $userId, 2, 1, '查询退货状态');
    Db::name('shop_order_aftersales')->where('id', $application['aftersales_id'])->update(['status' => 2, 'updatetime' => time()]);
    AfterSalesService::approve($application['aftersales_id']);
    $return = OrderQueryService::saveReturnShipment(
        $application['aftersales_id'],
        $userId,
        '退货测试快递',
        'RETURN-' . $key
    );
    queryAssertSame('SHIPPED', $return['return_status'], 'Submitting return logistics must update the return state');
    $repeated = OrderQueryService::saveReturnShipment(
        $application['aftersales_id'],
        $userId,
        '退货测试快递',
        'RETURN-' . $key
    );
    queryAssertSame($return['express_no'], $repeated['express_no'], 'Repeated identical return logistics must be idempotent');
    $updatedDetail = OrderQueryService::detail($order->order_sn, $userId);
    queryAssertSame(1, count($updatedDetail['aftersales']), 'Order detail must aggregate after-sales records');
    queryAssertSame((int)$application['aftersales_id'], (int)$updatedDetail['items'][0]['aftersales_id'], 'Order item must link to its latest after-sales request');
    queryAssertSame((int)$orderGoodsId, (int)$return['order_goods']['id'], 'After-sales detail must include the related order item');
    queryAssertSame('查询退货状态', $return['reason'], 'After-sales detail must include the application reason');

    Db::rollback();
} catch (Throwable $e) {
    Db::rollback();
    throw $e;
}

echo "Catalog and order query integration test passed.\n";
