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
        self::prepareOrder($order);
        $response = $app->order->unify([
            'body' => '家庭营养师商城订单-' . $order['order_sn'],
            'out_trade_no' => self::gatewayOrderSn($order['order_sn']),
            'total_fee' => (int)bcmul((string)$order['saleamount'], '100', 0),
            'trade_type' => 'JSAPI',
            'openid' => $openid,
            'notify_url' => $notifyUrl,
            'time_expire' => date('YmdHis', (int)$order['expiretime']),
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
                if (($message['return_code'] ?? '') !== 'SUCCESS' || ($message['result_code'] ?? '') !== 'SUCCESS') {
                    return $fail('支付状态不是成功');
                }
                self::confirmPaidOrder((array)$message);
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
            self::gatewayOrderSn($order['order_sn']),
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

    /** WeChat out_trade_no is limited to 32 characters; keep the platform order ID unchanged. */
    public static function gatewayOrderSn($orderSn)
    {
        return strlen($orderSn) <= 32 ? $orderSn : self::prepayNumber($orderSn);
    }

    private static function prepayNumber($orderSn)
    {
        return 'PAY' . strtoupper(substr(hash('sha256', $orderSn . '|wechat-prepay'), 0, 29));
    }

    /** Persist this mapping before contacting WeChat, including when the HTTP result is lost. */
    public static function prepareOrder(array $order)
    {
        if (Db::name('shop_payment_transaction')->where('channel','wechat')->where('channel_transaction_id','PREPAY:'.$order['order_sn'])->find()) return;
        Db::name('shop_payment_transaction')->insert([
            'payment_sn'=>self::prepayNumber($order['order_sn']), 'order_id'=>$order['id'], 'order_sn'=>$order['order_sn'],
            'channel'=>'wechat', 'channel_transaction_id'=>'PREPAY:'.$order['order_sn'], 'amount'=>$order['saleamount'],
            'status'=>'CREATED', 'request_json'=>json_encode(['gateway_order_sn'=>self::gatewayOrderSn($order['order_sn'])]),
            'createtime'=>time(), 'updatetime'=>time(),
        ]);
    }

    public static function queryOrder($orderSn)
    {
        self::assertConfigured();
        return self::arrayResult(self::application(null)->order->queryByOutTradeNumber(self::gatewayOrderSn($orderSn)));
    }

    public static function closeOrder($orderSn)
    {
        self::assertConfigured();
        return self::arrayResult(self::application(null)->order->close(self::gatewayOrderSn($orderSn)));
    }

    /** Only accepts SDK-verified notifications or authenticated server-to-server query results. */
    public static function confirmPaidOrder(array $message)
    {
        $config = self::config();
        $number = (string)($message['out_trade_no'] ?? '');
        if (($message['appid'] ?? '') !== $config['app_id'] || ($message['mch_id'] ?? '') !== $config['mch_id']
            || empty($message['transaction_id']) || !isset($message['total_fee'])) throw new RuntimeException('支付身份或流水不匹配');
        $order = Db::name('shop_order')->where('order_sn',$number)->find();
        if (!$order) {
            $mapping = Db::name('shop_payment_transaction')->where('channel','wechat')->where('payment_sn',$number)->find();
            if (!$mapping || $mapping['channel_transaction_id'] !== 'PREPAY:'.$mapping['order_sn']) throw new RuntimeException('支付单号没有平台订单映射');
            $order = Db::name('shop_order')->where('order_sn',$mapping['order_sn'])->find();
        }
        if (!$order || self::gatewayOrderSn($order['order_sn']) !== $number
            || (int)$message['total_fee'] !== (int)round((float)$order['saleamount']*100)) throw new RuntimeException('支付订单或金额不匹配');
        Db::startTrans();
        try {
            Db::name('shop_order')->where('id',$order['id'])->lock(true)->find();
            $ext = Db::name('shop_order_ext')->where('order_sn',$order['order_sn'])->find();
            if ($ext && !empty($ext['checkout_token_hash'])) {
                (new \addons\shop\library\v5\PaymentService())->onPaid($order['order_sn'],(int)$message['total_fee'],$message['transaction_id'],$message['transaction_id']);
                $existing = Db::name('shop_payment_transaction')->where('channel','wechat')->where('channel_transaction_id',$message['transaction_id'])->find();
                if ($existing && ($existing['order_sn'] !== $order['order_sn'] || (int)round((float)$existing['amount']*100) !== (int)$message['total_fee'])) throw new RuntimeException('支付流水已归属其他订单');
                if (!$existing) Db::name('shop_payment_transaction')->insert([
                    'payment_sn'=>'PAY'.strtoupper(substr(hash('sha256',$order['order_sn'].'|'.$message['transaction_id']),0,29)),
                    'order_id'=>$order['id'],'order_sn'=>$order['order_sn'],'channel'=>'wechat','channel_transaction_id'=>$message['transaction_id'],
                    'amount'=>number_format((int)$message['total_fee']/100,2,'.',''),'status'=>'SUCCESS',
                    'callback_json'=>json_encode($message,JSON_UNESCAPED_UNICODE),'paid_at'=>time(),'createtime'=>time(),'updatetime'=>time(),
                ]);
            } else {
                PaymentService::markPaid($order['order_sn'],'wechat',$message['transaction_id'],number_format((int)$message['total_fee']/100,2,'.',''),$message);
            }
            Db::name('shop_payment_transaction')->where('order_sn',$order['order_sn'])->where('channel_transaction_id','PREPAY:'.$order['order_sn'])->update(['status'=>'CLOSED','updatetime'=>time()]);
            Db::commit();
            return $order['order_sn'];
        } catch (\Throwable $e) { Db::rollback(); throw $e; }
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
        $data['payment_sn'] = self::prepayNumber($order['order_sn']);
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
            'http' => ['timeout'=>8.0, 'connect_timeout'=>3.0],
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
