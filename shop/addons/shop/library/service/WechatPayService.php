<?php

namespace addons\shop\library\service;

use EasyWeChat\Factory;
use RuntimeException;
use think\Db;

class WechatPayService
{
    public static function isConfigured()
    {
        $config = self::config();
        return $config['app_id'] !== '' && $config['mch_id'] !== '' && strlen($config['key']) === 32;
    }

    public static function createMiniProgramPayment($orderSn, $userId, $openid, $notifyUrl)
    {
        self::assertConfigured();
        $order = Db::name('shop_order')
            ->where('order_sn', trim((string)$orderSn))
            ->where('user_id', (int)$userId)
            ->find();
        if (!$order) {
            throw new RuntimeException('订单不存在', 404);
        }
        if ((int)$order['paystate'] === 1) {
            throw new RuntimeException('订单已支付', 409);
        }
        if ((int)$order['orderstate'] !== 0 || (int)$order['expiretime'] <= time()) {
            throw new RuntimeException('订单已关闭或支付超时', 409);
        }
        $openid = trim((string)$openid);
        if ($openid === '') {
            throw new RuntimeException('微信用户 openid 不能为空', 422);
        }
        $app = self::application($notifyUrl);
        $response = $app->order->unify([
            'body' => '家庭营养师商城订单-' . $order['order_sn'],
            'out_trade_no' => $order['order_sn'],
            'total_fee' => (int)bcmul((string)$order['saleamount'], '100', 0),
            'trade_type' => 'JSAPI',
            'openid' => $openid,
            'notify_url' => $notifyUrl,
        ]);
        $result = self::arrayResult($response);
        if (($result['return_code'] ?? '') !== 'SUCCESS' || ($result['result_code'] ?? '') !== 'SUCCESS' || empty($result['prepay_id'])) {
            throw new RuntimeException('微信支付下单失败：' . ($result['return_msg'] ?? $result['err_code_des'] ?? '未知错误'), 502);
        }
        $parameters = $app->jssdk->bridgeConfig((string)$result['prepay_id'], false);
        self::recordPending($order, $openid, $result, $parameters);
        Db::name('shop_order')->where('id', (int)$order['id'])->update([
            'paytype' => 'wechat',
            'method' => 'miniapp',
            'openid' => $openid,
            'updatetime' => time(),
        ]);
        return [
            'order_sn' => $order['order_sn'],
            'amount' => (string)$order['saleamount'],
            'channel' => 'wechat',
            'method' => 'miniapp',
            'parameters' => $parameters,
        ];
    }

    public static function handlePaidNotify($notifyUrl)
    {
        self::assertConfigured();
        $app = self::application($notifyUrl);
        return $app->handlePaidNotify(function ($message, $fail) {
            try {
                $orderSn = (string)($message['out_trade_no'] ?? '');
                $transactionId = (string)($message['transaction_id'] ?? '');
                $amount = bcdiv((string)($message['total_fee'] ?? 0), '100', 2);
                if (($message['return_code'] ?? '') !== 'SUCCESS' || ($message['result_code'] ?? '') !== 'SUCCESS') {
                    return $fail('支付状态不是成功');
                }
                PaymentService::markPaid($orderSn, 'wechat', $transactionId, $amount, $message);
                (new \addons\shop\library\v5\PaymentService())->onPaid(
                    $orderSn,
                    (int)($message['total_fee'] ?? 0),
                    $transactionId,
                    (string)($message['transaction_id'] ?? '')
                );
                Db::name('shop_payment_transaction')
                    ->where('order_sn', $orderSn)
                    ->where('channel_transaction_id', 'PREPAY:' . $orderSn)
                    ->update(['status' => 'CLOSED', 'updatetime' => time()]);
                return true;
            } catch (\Throwable $e) {
                return $fail($e->getMessage());
            }
        });
    }

    public static function handleRefundedNotify($notifyUrl)
    {
        self::assertConfigured();
        $app = self::application($notifyUrl);
        return $app->handleRefundedNotify(function ($message, $fail) {
            try {
                $refundSn = (string)($message['out_refund_no'] ?? '');
                if ($refundSn === '') {
                    return $fail('退款单号不能为空');
                }
                (new \addons\shop\library\v5\RefundService())->onWechatResult(
                    $refundSn,
                    (string)($message['refund_status'] ?? 'SUCCESS'),
                    (string)($message['refund_id'] ?? ''),
                    (string)($message['refund_id'] ?? '')
                );
                return true;
            } catch (\Throwable $e) {
                return $fail($e->getMessage());
            }
        });
    }

    public static function refund(array $context)
    {
        self::assertConfigured(true);
        $order = Db::name('shop_order')->where('id', (int)$context['order_id'])->find();
        if (!$order || (int)$order['paystate'] !== 1) {
            throw new RuntimeException('退款关联订单未支付', 409);
        }
        $app = self::application(self::config()['notify_url']);
        $response = $app->refund->byOutTradeNumber(
            $order['order_sn'],
            $context['refund_sn'],
            (int)bcmul((string)$order['payamount'], '100', 0),
            (int)bcmul((string)$context['amount'], '100', 0)
        );
        $result = self::arrayResult($response);
        if (($result['return_code'] ?? '') !== 'SUCCESS' || ($result['result_code'] ?? '') !== 'SUCCESS') {
            throw new RuntimeException('微信退款失败：' . ($result['return_msg'] ?? $result['err_code_des'] ?? '未知错误'), 502);
        }
        return ['gateway_refund_id' => (string)($result['refund_id'] ?? ''), 'response' => $result];
    }

    public static function queryRefund($refundSn)
    {
        self::assertConfigured();
        $response = self::application(self::config()['notify_url'])->refund->queryByOutRefundNumber((string)$refundSn);
        return self::arrayResult($response);
    }

    private static function recordPending(array $order, $openid, array $gatewayResponse, array $parameters)
    {
        $key = 'PREPAY:' . $order['order_sn'];
        $existing = Db::name('shop_payment_transaction')->where('channel', 'wechat')->where('channel_transaction_id', $key)->find();
        $data = [
            'order_id' => (int)$order['id'],
            'order_sn' => $order['order_sn'],
            'amount' => (string)$order['saleamount'],
            'status' => 'PENDING',
            'request_json' => json_encode(['openid' => $openid, 'gateway' => $gatewayResponse, 'parameters' => $parameters], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
            'updatetime' => time(),
        ];
        if ($existing) {
            Db::name('shop_payment_transaction')->where('id', (int)$existing['id'])->update($data);
            return;
        }
        $data['payment_sn'] = 'PAY' . strtoupper(substr(hash('sha256', $order['order_sn'] . '|wechat-prepay'), 0, 29));
        $data['channel'] = 'wechat';
        $data['channel_transaction_id'] = $key;
        $data['callback_json'] = null;
        $data['createtime'] = time();
        Db::name('shop_payment_transaction')->insert($data);
    }

    private static function application($notifyUrl)
    {
        $config = self::config();
        if ($notifyUrl) {
            $config['notify_url'] = $notifyUrl;
        }
        return Factory::payment($config);
    }

    private static function config()
    {
        return [
            'app_id' => trim((string)getenv('SHOP_WECHAT_APP_ID')),
            'mch_id' => trim((string)getenv('SHOP_WECHAT_MCH_ID')),
            'key' => trim((string)getenv('SHOP_WECHAT_API_V2_KEY')),
            'cert_path' => trim((string)getenv('SHOP_WECHAT_CERT_PATH')),
            'key_path' => trim((string)getenv('SHOP_WECHAT_KEY_PATH')),
            'notify_url' => trim((string)getenv('SHOP_WECHAT_NOTIFY_URL')),
            'sandbox' => filter_var(getenv('SHOP_WECHAT_SANDBOX'), FILTER_VALIDATE_BOOLEAN),
        ];
    }

    private static function assertConfigured($requireCertificate = false)
    {
        $config = self::config();
        if (!self::isConfigured()) {
            throw new RuntimeException('微信支付未配置：需要 APPID、商户号和 32 位 API v2 密钥', 503);
        }
        if ($requireCertificate && (!is_file($config['cert_path']) || !is_file($config['key_path']))) {
            throw new RuntimeException('微信退款未配置商户证书路径', 503);
        }
    }

    private static function arrayResult($result)
    {
        if (is_array($result)) {
            return $result;
        }
        if (is_object($result) && method_exists($result, 'toArray')) {
            return $result->toArray();
        }
        return (array)$result;
    }
}
