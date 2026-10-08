<?php

namespace addons\shop\library\service;

use addons\shop\model\OrderAction;
use addons\shop\model\OrderGoods;
use RuntimeException;
use think\Db;

class PaymentService
{
    public static function markPaid($orderSn, $channel, $channelTransactionId, $amount, array $callback = [])
    {
        $orderSn = trim((string)$orderSn);
        $channel = trim((string)$channel) ?: 'system';
        $channelTransactionId = trim((string)$channelTransactionId);
        if ($orderSn === '') {
            throw new RuntimeException('订单号不能为空');
        }
        if ($channelTransactionId === '') {
            $channelTransactionId = strtoupper($channel) . '-' . $orderSn;
        }

        $becamePaid = false;
        Db::startTrans();
        try {
            $order = Db::name('shop_order')->where('order_sn', $orderSn)->lock(true)->find();
            if (!$order) {
                throw new RuntimeException('订单不存在', 404);
            }
            if (bccomp((string)$amount, (string)$order['saleamount'], 2) !== 0) {
                throw new RuntimeException('订单支付金额不一致', 409);
            }
            if ((int)$order['orderstate'] !== 0) {
                throw new RuntimeException('订单已关闭，不能支付', 409);
            }

            $existingTransaction = Db::name('shop_payment_transaction')
                ->where('channel', $channel)
                ->where('channel_transaction_id', $channelTransactionId)
                ->lock(true)
                ->find();
            if ($existingTransaction) {
                if ($existingTransaction['order_sn'] !== $orderSn || bccomp((string)$existingTransaction['amount'], (string)$amount, 2) !== 0) {
                    throw new RuntimeException('支付流水号已被其他订单使用', 409);
                }
                Db::commit();
                return false;
            }

            $now = time();
            Db::name('shop_payment_transaction')->insert([
                'payment_sn' => self::paymentNumber($orderSn, $channelTransactionId),
                'order_id' => (int)$order['id'],
                'order_sn' => $orderSn,
                'channel' => $channel,
                'channel_transaction_id' => $channelTransactionId,
                'amount' => (string)$amount,
                'status' => 'SUCCESS',
                'request_json' => null,
                'callback_json' => json_encode($callback, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'paid_at' => $now,
                'createtime' => $now,
                'updatetime' => $now,
            ]);

            if ((int)$order['paystate'] === 0) {
                $affected = Db::name('shop_order')
                    ->where('id', (int)$order['id'])
                    ->where('paystate', 0)
                    ->update([
                        'paystate' => 1,
                        'transactionid' => $channelTransactionId,
                        'payamount' => (string)$amount,
                        'paytime' => $now,
                        'paytype' => $channel,
                        'method' => $channel === 'system' ? 'system' : $channel,
                        'updatetime' => $now,
                    ]);
                $becamePaid = $affected === 1;
            }

            Db::name('shop_order_ext')->where('order_id', (int)$order['id'])->update([
                'biz_status' => 'PAID',
                'fulfillment_status' => 'PENDING',
                'version' => Db::raw('version + 1'),
                'updatetime' => $now,
            ]);
            Db::name('shop_order_supplier')
                ->where('order_id', (int)$order['id'])
                ->where('status', 'PENDING_ASSIGN')
                ->update(['status' => 'PENDING_ACCEPT', 'updatetime' => $now]);
            self::statusLog((int)$order['id'], $orderSn, 'PAYMENT', 'PENDING', 'PAID', $channelTransactionId, '支付成功');
            Db::commit();
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }

        if ($becamePaid) {
            OrderGoods::setGoodsSalesInc($orderSn);
            OrderAction::push($orderSn, '系统', '订单支付成功');
        }
        return $becamePaid;
    }

    private static function paymentNumber($orderSn, $channelTransactionId)
    {
        return 'PAY' . strtoupper(substr(hash('sha256', $orderSn . '|' . $channelTransactionId), 0, 29));
    }

    private static function statusLog($orderId, $orderSn, $statusType, $fromStatus, $toStatus, $bizNo, $remark)
    {
        Db::name('shop_order_status_log')->insert([
            'order_id' => $orderId,
            'order_sn' => $orderSn,
            'supplier_order_id' => 0,
            'status_type' => $statusType,
            'from_status' => $fromStatus,
            'to_status' => $toStatus,
            'biz_no' => $bizNo,
            'operator_type' => 'SYSTEM',
            'operator_id' => 0,
            'remark' => $remark,
            'createtime' => time(),
        ]);
    }
}

