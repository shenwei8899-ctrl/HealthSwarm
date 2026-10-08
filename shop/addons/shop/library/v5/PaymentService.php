<?php

namespace addons\shop\library\v5;

use think\Db;

class PaymentService
{
    public function createWechat($userId, $orderSn, $openid, $requestId)
    {
        $order = Db::name('shop_order')->where('order_sn', $orderSn)->where('user_id', $userId)->find();
        if (!$order) {
            throw new DomainException('订单不存在', 40409, 404);
        }
        if ((int)$order['paystate'] === 1) {
            throw new DomainException('订单已支付', 40923, 409);
        }
        if ((int)$order['orderstate'] !== 0 || (int)$order['expiretime'] <= time()) {
            throw new DomainException('订单已失效', 40924, 409);
        }
        $payment = Db::name('shop_payment_record')->where('order_sn', $orderSn)
            ->where('status', 'in', ['created', 'paying'])->order('id', 'desc')->find();
        if (!$payment) {
            $paymentSn = Identifiers::make('pay');
            Db::name('shop_payment_record')->insert([
                'payment_sn' => $paymentSn, 'order_sn' => $orderSn, 'channel' => 'wechat',
                'amount_cent' => (int)round((float)$order['saleamount'] * 100), 'currency' => 'CNY',
                'status' => 'created', 'request_id' => $requestId, 'createtime' => time(), 'updatetime' => time(),
            ]);
        } else {
            $paymentSn = $payment['payment_sn'];
        }
        try {
            $notifyUrl = trim((string)getenv('SHOP_WECHAT_NOTIFY_URL'));
            if ($notifyUrl === '') {
                $notifyUrl = \think\Request::instance()->domain() . '/api/v1/payment/wechat/notify';
            }
            $response = \addons\shop\library\service\WechatPayService::createMiniProgramPayment(
                $orderSn,
                $userId,
                $openid,
                $notifyUrl
            );
            Db::name('shop_payment_record')->where('payment_sn', $paymentSn)->update(['status' => 'paying', 'updatetime' => time()]);
            Db::name('shop_order_ext')->where('order_sn', $orderSn)->update(['payment_status' => 'paying', 'updatetime' => time()]);
            return ['payment_sn' => $paymentSn, 'payment_params' => $response['parameters']];
        } catch (\Exception $e) {
            Db::name('shop_payment_record')->where('payment_sn', $paymentSn)->update(['status' => 'failed', 'updatetime' => time()]);
            (new ExceptionService())->open('payment_create:' . $paymentSn, 'payment', 'wechat_payment_create_failed', $e->getMessage(), [
                'resource_type' => 'payment', 'resource_ref' => $paymentSn, 'order_sn' => $orderSn,
            ], [], 'high');
            throw new DomainException($e->getMessage(), 50201, 502);
        }
    }

    public function onPaid($orderSn, $amountCent, $transactionId, $notifyId = '')
    {
        $order = Db::name('shop_order')->where('order_sn', $orderSn)->find();
        if (!$order) {
            throw new DomainException('订单不存在', 40409, 404);
        }
        $expected = (int)round((float)$order['saleamount'] * 100);
        if ((int)$amountCent !== $expected) {
            throw new DomainException('支付金额与订单不一致', 40925, 409);
        }
        $ext = Db::name('shop_order_ext')->where('order_sn', $orderSn)->find();
        if (!$ext) {
            return false;
        }
        Db::startTrans();
        try {
            $ext = Db::name('shop_order_ext')->where('id', $ext['id'])->lock(true)->find();
            $payment = Db::name('shop_payment_record')->where('order_sn', $orderSn)->order('id', 'desc')->lock(true)->find();
            if (!$payment) {
                Db::name('shop_payment_record')->insert([
                    'payment_sn' => Identifiers::make('pay'), 'order_sn' => $orderSn, 'channel' => 'wechat',
                    'channel_transaction_id' => $transactionId ?: null, 'amount_cent' => $amountCent,
                    'currency' => 'CNY', 'status' => 'paid', 'paid_at' => time(), 'notify_id' => $notifyId,
                    'notify_received_at' => time(), 'createtime' => time(), 'updatetime' => time(),
                ]);
            } elseif ($payment['status'] !== 'paid') {
                Db::name('shop_payment_record')->where('id', $payment['id'])->update([
                    'channel_transaction_id' => $transactionId ?: $payment['channel_transaction_id'],
                    'status' => 'paid', 'paid_at' => time(), 'notify_id' => $notifyId,
                    'notify_received_at' => time(), 'updatetime' => time(),
                ]);
            }
            $newlySynchronized = $ext['payment_status'] !== 'paid';
            if ($newlySynchronized) {
                Db::name('shop_order_ext')->where('id', $ext['id'])->update([
                    'business_status' => 'paid', 'payment_status' => 'paid',
                    'row_version' => (int)$ext['row_version'] + 1, 'updatetime' => time(),
                ]);
            }
            if ($order['order_type'] === 'plan') {
                Db::name('shop_service_plan_order')->where('order_sn', $orderSn)->where('status', 'pending_payment')->update([
                    'status' => 'active', 'row_version' => Db::raw('row_version+1'), 'updatetime' => time(),
                ]);
                $planOrder = Db::name('shop_service_plan_order')->where('order_sn', $orderSn)->find();
                if ($planOrder) {
                    Db::name('shop_service_plan')->where('id', $planOrder['plan_id'])->update(['status' => 'ordered', 'updatetime' => time()]);
                }
            }
            if ($newlySynchronized) {
                (new OutboxService())->append('order.paid', 'order', $orderSn, (int)$ext['row_version'] + 1, 'agent', [
                    'order_sn' => $orderSn, 'order_type' => $order['order_type'], 'amount_cent' => $amountCent,
                ]);
            }
            Db::commit();
        } catch (\Exception $e) {
            Db::rollback();
            throw $e;
        }
        if ($order['order_type'] !== 'plan') {
            $reservations = Db::name('shop_inventory_reservation')->where('source_type', 'checkout')
                ->where('source_ref', $ext['checkout_token_hash'])->where('status', 'active')->select();
            foreach ($reservations as $reservation) {
                (new InventoryService())->confirm($reservation['reservation_sn'], $ext['request_id']);
            }
            try {
                (new SupplierOrderService())->createForNormalOrder($orderSn, $ext['request_id']);
                $orderGoodsIds=Db::name('shop_order_goods')->where('order_sn',$orderSn)->column('id');
                $covered=$orderGoodsIds?Db::name('shop_supplier_order_item')->where('order_goods_id','in',$orderGoodsIds)->count():0;
                if($orderGoodsIds && (int)$covered<count($orderGoodsIds))throw new DomainException('部分订单商品尚未匹配可用供应商',40932,409);
                Db::name('shop_order_ext')->where('id',$ext['id'])->update(['fulfillment_status'=>'supplier_pending','exception_status'=>'normal','updatetime'=>time()]);
            } catch (\Exception $e) {
                Db::name('shop_order_ext')->where('id',$ext['id'])->update(['fulfillment_status'=>'pending','exception_status'=>'open','updatetime'=>time()]);
                (new ExceptionService())->open('normal_supplier_create:' . $orderSn, 'supplier', 'supplier_order_create_failed', $e->getMessage(), [
                    'resource_type' => 'order', 'resource_ref' => $orderSn, 'order_sn' => $orderSn,
                ], [], 'high');
            }
        }
        return true;
    }
}
