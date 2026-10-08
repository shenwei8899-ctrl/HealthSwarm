<?php

require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'bootstrap.php';

use addons\shop\library\service\AfterSalesService;
use addons\shop\library\service\FulfillmentService;
use addons\shop\library\service\InventoryService;
use addons\shop\library\service\OrderService;
use addons\shop\library\service\PaymentService;
use addons\shop\library\service\RefundService;
use think\Db;

function refundAssertSame($expected, $actual, $message)
{
    if ($expected !== $actual) {
        throw new RuntimeException($message . ': expected ' . var_export($expected, true) . ', got ' . var_export($actual, true));
    }
}

function createRefundTestOrder(array $stock, $quantity, $key)
{
    $userId = 400000 + random_int(1, 99999);
    $now = time();
    $addressId = Db::name('shop_address')->insertGetId([
        'user_id' => $userId,
        'province_id' => 0,
        'city_id' => 0,
        'area_id' => 0,
        'receiver' => '退款事务测试用户',
        'mobile' => '13800000000',
        'address' => '退款事务测试地址',
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
    $orderModel = OrderService::createFromCart($addressId, $userId, [$cartId], 0, '', $key);
    PaymentService::markPaid($orderModel->order_sn, 'system', 'TX-' . $key, $orderModel->saleamount);
    return [
        Db::name('shop_order')->where('id', $orderModel->id)->find(),
        Db::name('shop_order_goods')->where('order_sn', $orderModel->order_sn)->find(),
        Db::name('shop_order_supplier')->where('order_id', $orderModel->id)->find(),
    ];
}

function createRefundAfterSales(array $order, array $orderGoods, $type, $quantity, $key)
{
    return Db::name('shop_order_aftersales')->insertGetId([
        'order_id' => (int)$order['id'],
        'order_goods_id' => (int)$orderGoods['id'],
        'user_id' => (int)$order['user_id'],
        'type' => (int)$type,
        'nums' => (int)$quantity,
        'realprice' => '1.00',
        'shippingfee' => '0.00',
        'refund' => '1.00',
        'reason' => '退款事务测试-' . $key,
        'status' => 2,
        'createtime' => time(),
        'updatetime' => time(),
    ]);
}

function runRefundScenario(callable $scenario)
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
    ->where('ws.on_hand_qty - ws.locked_qty - ws.unavailable_qty >= 4')
    ->field('ws.*')
    ->order('ws.id ASC')
    ->find();
if (!$stock) {
    throw new RuntimeException('No inventory is available for refund transaction testing.');
}

runRefundScenario(function () use ($stock) {
    $key = 'TEST-REFUND-IDEMPOTENT-' . bin2hex(random_bytes(4));
    list($order, $orderGoods) = createRefundTestOrder($stock, 2, $key);
    $aftersalesId = createRefundAfterSales($order, $orderGoods, 1, 1, $key);
    $gatewayCalls = 0;
    $gateway = function (array $context) use (&$gatewayCalls) {
        $gatewayCalls++;
        if (strpos($context['refund_sn'], 'RF') !== 0) {
            throw new RuntimeException('Refund number must be stable and prefixed.');
        }
        return ['gateway_refund_id' => 'GW-' . $context['refund_sn']];
    };

    refundAssertSame(true, RefundService::processRefundOnly($aftersalesId, $gateway, 'test'), 'First refund must execute the gateway and local mutation');
    refundAssertSame(1, $gatewayCalls, 'First refund must call the gateway once');
    refundAssertSame('COMPLETED', Db::name('shop_refund_transaction')->where('aftersales_id', $aftersalesId)->value('status'), 'Successful refund transaction must complete');
    refundAssertSame(1, (int)Db::name('shop_order_goods_ext')->where('order_goods_id', $orderGoods['id'])->value('refunded_quantity'), 'Completed refund must update local refunded quantity');

    refundAssertSame(false, RefundService::processRefundOnly($aftersalesId, $gateway, 'test'), 'Repeated completed refund must be idempotent');
    refundAssertSame(1, $gatewayCalls, 'Repeated completed refund must not call the gateway again');
    refundAssertSame(1, Db::name('shop_refund_transaction')->where('aftersales_id', $aftersalesId)->count(), 'One after-sales request must have one refund transaction');
});

runRefundScenario(function () use ($stock) {
    $key = 'TEST-REFUND-RETRY-' . bin2hex(random_bytes(4));
    list($order, $orderGoods) = createRefundTestOrder($stock, 1, $key);
    $aftersalesId = createRefundAfterSales($order, $orderGoods, 1, 1, $key);
    $gatewayCalls = 0;
    $refundSn = '';
    try {
        RefundService::processRefundOnly($aftersalesId, function (array $context) use (&$gatewayCalls, &$refundSn) {
            $gatewayCalls++;
            $refundSn = $context['refund_sn'];
            throw new RuntimeException('模拟支付渠道失败');
        }, 'test');
        throw new RuntimeException('A failed gateway call must throw.');
    } catch (RuntimeException $e) {
        if ($e->getMessage() === 'A failed gateway call must throw.') {
            throw $e;
        }
    }
    refundAssertSame('FAILED', Db::name('shop_refund_transaction')->where('aftersales_id', $aftersalesId)->value('status'), 'Gateway failure must remain retryable');
    refundAssertSame(0, (int)Db::name('shop_order_goods_ext')->where('order_goods_id', $orderGoods['id'])->value('refunded_quantity'), 'Gateway failure must not apply local refund state');

    RefundService::processRefundOnly($aftersalesId, function (array $context) use (&$gatewayCalls, $refundSn) {
        $gatewayCalls++;
        refundAssertSame($refundSn, $context['refund_sn'], 'Retry must reuse the same gateway refund number');
        return ['gateway_refund_id' => 'GW-RETRY'];
    }, 'test');
    refundAssertSame(2, $gatewayCalls, 'A failed gateway refund must be retried once');
    refundAssertSame('COMPLETED', Db::name('shop_refund_transaction')->where('aftersales_id', $aftersalesId)->value('status'), 'Successful retry must complete the refund transaction');
});

runRefundScenario(function () use ($stock) {
    $key = 'TEST-REFUND-COMPENSATE-' . bin2hex(random_bytes(4));
    $before = InventoryService::getAvailability($stock['id']);
    list($order, $orderGoods, $supplierOrder) = createRefundTestOrder($stock, 2, $key);
    FulfillmentService::markPreparing($supplierOrder['id']);
    FulfillmentService::shipSupplierOrder($supplierOrder['id'], '退款测试快递', 'LOGISTIC-' . $key, 'TEST');
    $aftersalesId = createRefundAfterSales($order, $orderGoods, 2, 2, $key);
    AfterSalesService::approve($aftersalesId);

    $goodsExtension = Db::name('shop_order_goods_ext')->where('order_goods_id', $orderGoods['id'])->find();
    Db::name('shop_order_goods_ext')->where('id', $goodsExtension['id'])->update(['warehouse_id' => 999999999]);
    $gatewayCalls = 0;
    try {
        RefundService::processReturn(
            $aftersalesId,
            2,
            0,
            'INSPECT-' . $key,
            1,
            '补偿测试',
            function (array $context) use (&$gatewayCalls) {
                $gatewayCalls++;
                return ['gateway_refund_id' => 'GW-' . $context['refund_sn']];
            },
            'test'
        );
        throw new RuntimeException('Local inventory failure after an external refund must throw.');
    } catch (RuntimeException $e) {
        if ($e->getMessage() === 'Local inventory failure after an external refund must throw.') {
            throw $e;
        }
    }
    refundAssertSame(1, $gatewayCalls, 'External refund must have succeeded exactly once before local failure');
    refundAssertSame('EXTERNAL_SUCCESS', Db::name('shop_refund_transaction')->where('aftersales_id', $aftersalesId)->value('status'), 'Local failure must retain external success for compensation');
    refundAssertSame(0, Db::name('shop_aftersales_inspection')->where('aftersales_id', $aftersalesId)->count(), 'Failed local finalization must not persist a partial inspection');

    Db::name('shop_order_goods_ext')->where('id', $goodsExtension['id'])->update(['warehouse_id' => (int)$goodsExtension['warehouse_id']]);
    refundAssertSame(1, RefundService::reconcileLocalCompletions(), 'Compensation must finalize externally successful refunds');
    refundAssertSame(1, $gatewayCalls, 'Local compensation must not call the payment gateway again');
    refundAssertSame('COMPLETED', Db::name('shop_refund_transaction')->where('aftersales_id', $aftersalesId)->value('status'), 'Compensated refund transaction must complete');
    refundAssertSame(1, Db::name('shop_aftersales_inspection')->where('aftersales_id', $aftersalesId)->count(), 'Compensation must create the missing return inspection');
    $after = InventoryService::getAvailability($stock['id']);
    refundAssertSame((int)$before['on_hand_qty'], (int)$after['on_hand_qty'], 'Compensated accepted return must restore physical inventory');
});

echo "RefundService integration test passed.\n";
