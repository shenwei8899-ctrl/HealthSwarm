<?php

namespace addons\shop\library\service;

use RuntimeException;
use think\Db;

class RefundService
{
    public static function processRefundOnly($aftersalesId, callable $gateway = null, $channel = 'manual')
    {
        return self::process(
            $aftersalesId,
            'REFUND_ONLY',
            [],
            $gateway,
            $channel
        );
    }

    public static function processReturn(
        $aftersalesId,
        $acceptedQuantity,
        $rejectedQuantity,
        $bizNo,
        $operatorId = 0,
        $remark = '',
        callable $gateway = null,
        $channel = 'manual'
    ) {
        return self::process(
            $aftersalesId,
            'RETURN_REFUND',
            [
                'accepted_quantity' => (int)$acceptedQuantity,
                'rejected_quantity' => (int)$rejectedQuantity,
                'biz_no' => trim((string)$bizNo),
                'operator_id' => (int)$operatorId,
                'remark' => trim((string)$remark),
            ],
            $gateway,
            $channel
        );
    }

    public static function reconcileLocalCompletions($limit = 50)
    {
        $rows = Db::name('shop_refund_transaction')
            ->where('status', 'EXTERNAL_SUCCESS')
            ->order('id ASC')
            ->limit(max(1, min(500, (int)$limit)))
            ->select();
        $completed = 0;
        foreach ($rows as $row) {
            self::finalizeLocal($row);
            self::markCompleted((int)$row['id']);
            $completed++;
        }
        return $completed;
    }

    public static function reconcileTransaction($transactionId)
    {
        $row = Db::name('shop_refund_transaction')->where('id', (int)$transactionId)->find();
        if (!$row || $row['status'] !== 'EXTERNAL_SUCCESS') {
            throw new RuntimeException('退款事务当前状态不能执行本地补偿', 409);
        }
        self::finalizeLocal($row);
        self::markCompleted((int)$row['id']);
        return Db::name('shop_refund_transaction')->where('id', (int)$row['id'])->find();
    }

    public static function confirmManualTransaction($transactionId, $operatorId, $remark)
    {
        $row = Db::name('shop_refund_transaction')->where('id', (int)$transactionId)->find();
        if (!$row || !in_array($row['status'], ['CREATED', 'FAILED'], true)) {
            throw new RuntimeException('退款事务当前状态不能人工确认', 409);
        }
        $now = time();
        Db::name('shop_refund_transaction')->where('id', (int)$row['id'])->update([
            'channel' => 'manual',
            'status' => 'EXTERNAL_SUCCESS',
            'response_json' => self::encodeJson([
                'manual_confirmation' => true,
                'operator_id' => (int)$operatorId,
                'remark' => trim((string)$remark),
            ]),
            'external_succeeded_at' => $now,
            'error_message' => '',
            'updatetime' => $now,
        ]);
        return self::reconcileTransaction((int)$row['id']);
    }

    private static function process($aftersalesId, $localAction, array $payload, callable $gateway = null, $channel = 'manual')
    {
        $transaction = self::prepare($aftersalesId, $localAction, $payload, $gateway !== null, $channel);
        if ($transaction['status'] === 'COMPLETED') {
            return false;
        }

        if ($transaction['status'] !== 'EXTERNAL_SUCCESS') {
            if ($gateway !== null) {
                $transaction = self::executeGateway($transaction, $gateway);
            } else {
                $transaction = self::confirmManualRefund($transaction);
            }
        }

        self::finalizeLocal($transaction);
        self::markCompleted((int)$transaction['id']);
        return true;
    }

    private static function prepare($aftersalesId, $localAction, array $payload, $externalRequired, $channel)
    {
        $aftersalesId = (int)$aftersalesId;
        $channel = trim((string)$channel) ?: 'manual';
        $payloadJson = self::encodeJson($payload);

        Db::startTrans();
        try {
            $aftersales = Db::name('shop_order_aftersales')->where('id', $aftersalesId)->lock(true)->find();
            if (!$aftersales || (int)$aftersales['status'] !== 2) {
                throw new RuntimeException('售后单尚未审核通过', 409);
            }
            $order = Db::name('shop_order')->where('id', (int)$aftersales['order_id'])->lock(true)->find();
            if (!$order) {
                throw new RuntimeException('退款关联订单不存在', 404);
            }
            if (bccomp((string)$aftersales['refund'], '0.00', 2) < 0) {
                throw new RuntimeException('退款金额无效', 409);
            }

            $existing = Db::name('shop_refund_transaction')->where('aftersales_id', $aftersalesId)->lock(true)->find();
            if ($existing) {
                if ($existing['local_action'] !== $localAction || bccomp((string)$existing['amount'], (string)$aftersales['refund'], 2) !== 0) {
                    throw new RuntimeException('退款事务参数与原申请不一致', 409);
                }
                $existingPayload = $existing['local_payload_json'] ?: '{}';
                if (self::canonicalJson($existingPayload) !== self::canonicalJson($payloadJson)) {
                    throw new RuntimeException('退款本地处理参数与首次请求不一致', 409);
                }
                Db::commit();
                return $existing;
            }

            $now = time();
            $refundSn = self::refundNumber($aftersalesId, $order['order_sn']);
            $id = Db::name('shop_refund_transaction')->insertGetId([
                'refund_sn' => $refundSn,
                'aftersales_id' => $aftersalesId,
                'order_id' => (int)$order['id'],
                'order_sn' => $order['order_sn'],
                'channel' => $channel,
                'amount' => (string)$aftersales['refund'],
                'local_action' => $localAction,
                'local_payload_json' => $payloadJson,
                'external_required' => $externalRequired ? 1 : 0,
                'status' => 'CREATED',
                'request_json' => self::encodeJson([
                    'refund_sn' => $refundSn,
                    'order_sn' => $order['order_sn'],
                    'amount' => (string)$aftersales['refund'],
                ]),
                'attempt_count' => 0,
                'createtime' => $now,
                'updatetime' => $now,
            ]);
            $transaction = Db::name('shop_refund_transaction')->where('id', $id)->find();
            Db::commit();
            return $transaction;
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    private static function executeGateway(array $transaction, callable $gateway)
    {
        Db::startTrans();
        try {
            $locked = Db::name('shop_refund_transaction')->where('id', (int)$transaction['id'])->lock(true)->find();
            if (in_array($locked['status'], ['EXTERNAL_SUCCESS', 'COMPLETED'], true)) {
                Db::commit();
                return $locked;
            }
            if ($locked['status'] === 'PROCESSING' && (int)$locked['updatetime'] > time() - 300) {
                throw new RuntimeException('退款正在处理中，请勿重复提交', 409);
            }
            Db::name('shop_refund_transaction')->where('id', (int)$locked['id'])->update([
                'status' => 'PROCESSING',
                'attempt_count' => (int)$locked['attempt_count'] + 1,
                'error_message' => '',
                'next_retry_at' => null,
                'updatetime' => time(),
            ]);
            Db::commit();
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }

        try {
            $response = $gateway([
                'refund_sn' => $transaction['refund_sn'],
                'aftersales_id' => (int)$transaction['aftersales_id'],
                'order_id' => (int)$transaction['order_id'],
                'order_sn' => $transaction['order_sn'],
                'amount' => (string)$transaction['amount'],
                'channel' => $transaction['channel'],
            ]);
            $response = is_array($response) ? $response : [];
            $now = time();
            Db::name('shop_refund_transaction')->where('id', (int)$transaction['id'])->update([
                'status' => 'EXTERNAL_SUCCESS',
                'gateway_refund_id' => (string)($response['gateway_refund_id'] ?? ''),
                'response_json' => self::encodeJson($response),
                'external_succeeded_at' => $now,
                'error_message' => '',
                'updatetime' => $now,
            ]);
            return Db::name('shop_refund_transaction')->where('id', (int)$transaction['id'])->find();
        } catch (\Throwable $e) {
            Db::name('shop_refund_transaction')->where('id', (int)$transaction['id'])->update([
                'status' => 'FAILED',
                'error_message' => mb_substr($e->getMessage(), 0, 1000),
                'next_retry_at' => time() + 300,
                'updatetime' => time(),
            ]);
            throw $e;
        }
    }

    private static function confirmManualRefund(array $transaction)
    {
        $now = time();
        Db::name('shop_refund_transaction')->where('id', (int)$transaction['id'])->update([
            'status' => 'EXTERNAL_SUCCESS',
            'response_json' => self::encodeJson(['manual_confirmation' => true]),
            'external_succeeded_at' => $now,
            'updatetime' => $now,
        ]);
        return Db::name('shop_refund_transaction')->where('id', (int)$transaction['id'])->find();
    }

    private static function finalizeLocal(array $transaction)
    {
        $payload = json_decode($transaction['local_payload_json'] ?: '{}', true) ?: [];
        if ($transaction['local_action'] === 'REFUND_ONLY') {
            AfterSalesService::approve((int)$transaction['aftersales_id']);
            return;
        }
        if ($transaction['local_action'] === 'RETURN_REFUND') {
            AfterSalesService::inspectReturn(
                (int)$transaction['aftersales_id'],
                (int)($payload['accepted_quantity'] ?? 0),
                (int)($payload['rejected_quantity'] ?? 0),
                (string)($payload['biz_no'] ?? ''),
                (int)($payload['operator_id'] ?? 0),
                (string)($payload['remark'] ?? '')
            );
            return;
        }
        throw new RuntimeException('未知的退款本地处理类型', 409);
    }

    private static function markCompleted($transactionId)
    {
        $now = time();
        Db::name('shop_refund_transaction')
            ->where('id', (int)$transactionId)
            ->where('status', 'EXTERNAL_SUCCESS')
            ->update([
                'status' => 'COMPLETED',
                'completed_at' => $now,
                'updatetime' => $now,
            ]);
    }

    private static function refundNumber($aftersalesId, $orderSn)
    {
        return 'RF' . strtoupper(substr(hash('sha256', $orderSn . '|' . $aftersalesId), 0, 30));
    }

    private static function canonicalJson($json)
    {
        $value = json_decode((string)$json, true);
        return self::encodeJson(is_array($value) ? $value : []);
    }

    private static function encodeJson(array $value)
    {
        return json_encode($value, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    }
}
