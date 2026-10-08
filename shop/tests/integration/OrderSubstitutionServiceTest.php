<?php

require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'bootstrap.php';

use addons\shop\library\service\OrderService;
use addons\shop\library\service\OrderQueryService;
use addons\shop\library\service\OrderSubstitutionService;
use addons\shop\library\service\PaymentService;
use think\Db;

function substitutionAssertSame($expected, $actual, $message)
{
    if ($expected !== $actual) {
        throw new RuntimeException($message . ': expected ' . var_export($expected, true) . ', got ' . var_export($actual, true));
    }
}

$relation = Db::name('shop_goods_substitute')->alias('sub')
    ->join('__SHOP_GOODS__ source', 'source.id=sub.goods_id')
    ->join('__SHOP_GOODS__ target', 'target.id=sub.substitute_goods_id')
    ->where('source.goods_sn', 'like', 'MOCK_NUTRITION_%')
    ->where('sub.status', 'normal')->field('sub.*')->find();
if (!$relation) {
    throw new RuntimeException('A MOCK substitute relation is required.');
}

$userId = 890000 + random_int(1, 9999);
$key = 'TEST-SUBSTITUTION-' . bin2hex(random_bytes(4));
$now = time();
Db::startTrans();
try {
    $addressId = Db::name('shop_address')->insertGetId([
        'user_id' => $userId, 'province_id' => 0, 'city_id' => 0, 'area_id' => 0,
        'receiver' => '替代确认测试用户', 'mobile' => '13800000000', 'address' => '替代确认测试地址',
        'zipcode' => '', 'usednums' => 0, 'createtime' => $now, 'updatetime' => $now, 'isdefault' => 1, 'status' => 'normal',
    ]);
    $cartId = Db::name('shop_carts')->insertGetId([
        'user_id' => $userId, 'goods_id' => (int)$relation['goods_id'], 'goods_sku_id' => (int)$relation['goods_sku_id'],
        'sceneval' => 1, 'nums' => 1, 'createtime' => $now, 'updatetime' => $now,
    ]);
    $order = OrderService::createFromCart($addressId, $userId, [$cartId], 0, '', $key);
    $orderGoods = Db::name('shop_order_goods')->where('order_sn', $order->order_sn)->find();
    $ext = Db::name('shop_order_goods_ext')->where('order_goods_id', (int)$orderGoods['id'])->find();
    $substitutionId = Db::name('shop_order_substitution')->insertGetId([
        'order_id' => (int)$order->id, 'order_goods_id' => (int)$orderGoods['id'],
        'from_supplier_id' => (int)$ext['supplier_id'], 'from_goods_id' => (int)$relation['goods_id'],
        'from_goods_sku_id' => (int)$relation['goods_sku_id'], 'to_supplier_id' => 0,
        'to_goods_id' => (int)$relation['substitute_goods_id'], 'to_goods_sku_id' => (int)$relation['substitute_goods_sku_id'],
        'constraint_result_json' => json_encode(['allowed' => true]), 'price_difference' => '0.00',
        'status' => 'PENDING_CONFIRM', 'createtime' => $now, 'updatetime' => $now,
    ]);

    $detail = OrderQueryService::detail($order->order_sn, $userId);
    substitutionAssertSame(1, count($detail['substitutions']), 'Order detail must expose pending substitutions.');
    substitutionAssertSame((int)$substitutionId, (int)$detail['substitutions'][0]['id'], 'Order detail must expose the expected substitution.');
    if (empty($detail['substitutions'][0]['from_goods_title']) || empty($detail['substitutions'][0]['to_goods_title'])) {
        throw new RuntimeException('Order substitutions must include user-facing product titles.');
    }

    $ownershipRejected = false;
    try {
        OrderSubstitutionService::confirm($order->order_sn, $substitutionId, $userId + 1);
    } catch (RuntimeException $e) {
        $ownershipRejected = (int)$e->getCode() === 404;
    }
    substitutionAssertSame(true, $ownershipRejected, 'Another user must not confirm the substitution.');

    $confirmed = OrderSubstitutionService::confirm($order->order_sn, $substitutionId, $userId);
    substitutionAssertSame('CONFIRMED', $confirmed['status'], 'Substitution must be confirmed.');
    substitutionAssertSame((int)$relation['substitute_goods_id'], (int)Db::name('shop_order_goods')->where('id', $orderGoods['id'])->value('goods_id'), 'Order line must use the substitute goods.');
    substitutionAssertSame('RELEASED', Db::name('shop_stock_reservation')->where('order_sn', $order->order_sn)->where('goods_id', (int)$relation['goods_id'])->value('status'), 'Original reservation must be released.');
    substitutionAssertSame('LOCKED', Db::name('shop_stock_reservation')->where('order_sn', $order->order_sn)->where('goods_id', (int)$relation['substitute_goods_id'])->value('status'), 'Substitute inventory must be locked.');
    substitutionAssertSame(1, Db::name('shop_order_snapshot')->where('order_id', $order->id)->where('snapshot_type', 'FULFILLMENT')->count(), 'Substitution must write an audit snapshot.');

    $repeated = OrderSubstitutionService::confirm($order->order_sn, $substitutionId, $userId);
    substitutionAssertSame('CONFIRMED', $repeated['status'], 'Repeated confirmation must be idempotent.');

    $rejectCartId = Db::name('shop_carts')->insertGetId([
        'user_id' => $userId, 'goods_id' => (int)$relation['goods_id'], 'goods_sku_id' => (int)$relation['goods_sku_id'],
        'sceneval' => 1, 'nums' => 1, 'createtime' => $now, 'updatetime' => $now,
    ]);
    $rejectOrder = OrderService::createFromCart($addressId, $userId, [$rejectCartId], 0, '', $key . '-REJECT');
    $rejectOrderGoods = Db::name('shop_order_goods')->where('order_sn', $rejectOrder->order_sn)->find();
    $rejectExt = Db::name('shop_order_goods_ext')->where('order_goods_id', (int)$rejectOrderGoods['id'])->find();
    $rejectSubstitutionId = Db::name('shop_order_substitution')->insertGetId([
        'order_id' => (int)$rejectOrder->id, 'order_goods_id' => (int)$rejectOrderGoods['id'],
        'from_supplier_id' => (int)$rejectExt['supplier_id'], 'from_goods_id' => (int)$relation['goods_id'],
        'from_goods_sku_id' => (int)$relation['goods_sku_id'], 'to_supplier_id' => 0,
        'to_goods_id' => (int)$relation['substitute_goods_id'], 'to_goods_sku_id' => (int)$relation['substitute_goods_sku_id'],
        'constraint_result_json' => json_encode(['allowed' => true]), 'price_difference' => '0.00',
        'status' => 'PENDING_CONFIRM', 'createtime' => $now, 'updatetime' => $now,
    ]);
    $rejected = OrderSubstitutionService::reject($rejectOrder->order_sn, $rejectSubstitutionId, $userId);
    substitutionAssertSame(true, $rejected['order_cancelled'], 'Rejecting a substitution on an unpaid order must cancel the order.');
    substitutionAssertSame('REJECTED', Db::name('shop_order_substitution')->where('id', $rejectSubstitutionId)->value('status'), 'Rejected substitution must persist its decision.');
    substitutionAssertSame(1, (int)Db::name('shop_order')->where('id', $rejectOrder->id)->value('orderstate'), 'Rejected unpaid order must be cancelled.');
    substitutionAssertSame('RELEASED', Db::name('shop_stock_reservation')->where('order_sn', $rejectOrder->order_sn)->value('status'), 'Rejecting an unpaid substitution must release inventory.');
    $repeatedReject = OrderSubstitutionService::reject($rejectOrder->order_sn, $rejectSubstitutionId, $userId);
    substitutionAssertSame(true, $repeatedReject['order_cancelled'], 'Repeated rejection must be idempotent.');

    $paidRejectCartId = Db::name('shop_carts')->insertGetId([
        'user_id' => $userId, 'goods_id' => (int)$relation['goods_id'], 'goods_sku_id' => (int)$relation['goods_sku_id'],
        'sceneval' => 1, 'nums' => 1, 'createtime' => $now, 'updatetime' => $now,
    ]);
    $paidRejectOrder = OrderService::createFromCart($addressId, $userId, [$paidRejectCartId], 0, '', $key . '-PAID-REJECT');
    PaymentService::markPaid($paidRejectOrder->order_sn, 'system', 'TX-' . $key . '-PAID-REJECT', $paidRejectOrder->saleamount);
    $paidRejectGoods = Db::name('shop_order_goods')->where('order_sn', $paidRejectOrder->order_sn)->find();
    $paidRejectExt = Db::name('shop_order_goods_ext')->where('order_goods_id', (int)$paidRejectGoods['id'])->find();
    $paidRejectSubstitutionId = Db::name('shop_order_substitution')->insertGetId([
        'order_id' => (int)$paidRejectOrder->id, 'order_goods_id' => (int)$paidRejectGoods['id'],
        'from_supplier_id' => (int)$paidRejectExt['supplier_id'], 'from_goods_id' => (int)$relation['goods_id'],
        'from_goods_sku_id' => (int)$relation['goods_sku_id'], 'to_supplier_id' => 0,
        'to_goods_id' => (int)$relation['substitute_goods_id'], 'to_goods_sku_id' => (int)$relation['substitute_goods_sku_id'],
        'constraint_result_json' => json_encode(['allowed' => true]), 'price_difference' => '0.00',
        'status' => 'PENDING_CONFIRM', 'createtime' => $now, 'updatetime' => $now,
    ]);
    $paidRejected = OrderSubstitutionService::reject($paidRejectOrder->order_sn, $paidRejectSubstitutionId, $userId);
    substitutionAssertSame(false, $paidRejected['order_cancelled'], 'Rejecting a substitution on a paid order must not cancel the order.');
    if ((int)$paidRejected['aftersales_id'] <= 0) {
        throw new RuntimeException('Rejecting a substitution on a paid order must create an after-sales request.');
    }
    substitutionAssertSame(1, (int)Db::name('shop_order_aftersales')->where('id', $paidRejected['aftersales_id'])->value('status'), 'Paid rejection must leave the refund application pending review.');
    substitutionAssertSame(0, Db::name('shop_refund_transaction')->where('aftersales_id', $paidRejected['aftersales_id'])->count(), 'Paid rejection must not falsely complete a payment refund.');
    $repeatedPaidReject = OrderSubstitutionService::reject($paidRejectOrder->order_sn, $paidRejectSubstitutionId, $userId);
    substitutionAssertSame((int)$paidRejected['aftersales_id'], (int)$repeatedPaidReject['aftersales_id'], 'Repeated paid rejection must return the original after-sales request.');
    substitutionAssertSame(1, Db::name('shop_order_aftersales')->where('order_goods_id', $paidRejectGoods['id'])->where('reason', '拒绝缺货替代商品')->count(), 'Repeated paid rejection must not duplicate after-sales requests.');
    Db::rollback();
} catch (Throwable $e) {
    Db::rollback();
    throw $e;
}

echo "Order substitution integration test passed.\n";
