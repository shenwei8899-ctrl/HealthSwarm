<?php
namespace addons\shop\library\v5;

use addons\shop\library\service\WechatPayService;
use think\Db;

class WechatPaymentLifecycle
{
    // A just-started or interrupted create request must not be cancelled on an early NOTFOUND.
    const CREATE_GRACE_SECONDS = 120;

    public function reconcile($orderSn, $close = false, $userId = null)
    {
        Db::startTrans();
        try {
            $query = Db::name('shop_order')->where('order_sn',$orderSn);
            if ($userId !== null) $query->where('user_id',(int)$userId);
            $order = $query->lock(true)->find();
            if (!$order) throw new DomainException('订单不存在',40409,404);
            $payment = Db::name('shop_payment_record')->where('order_sn',$orderSn)->order('id','desc')->find();
            if ((int)$order['paystate'] === 1 || !$payment || $payment['channel'] !== 'wechat' || !in_array($payment['status'],['created','paying'],true)) {
                Db::commit();
                return (int)$order['paystate'] === 1 ? 'paid' : ($payment['status'] ?? 'unpaid');
            }
            if (!$close && (int)$payment['last_query_at'] > time()-15) { Db::commit(); return 'paying'; }
            if (!WechatPayService::isConfigured()) { Db::commit(); return 'unknown'; }
            if ((!empty($payment['appid']) && $payment['appid'] !== (string)getenv('SHOP_WECHAT_APP_ID'))
                || (!empty($payment['mchid']) && $payment['mchid'] !== (string)getenv('SHOP_WECHAT_MCH_ID'))) { Db::commit(); return 'unknown'; }
            // The order lock serializes queries/close with creation and paid callbacks.
            $result = $this->queryGateway($orderSn);
            Db::name('shop_payment_record')->where('id',$payment['id'])->update(['last_query_at'=>time()]);
            $state = $this->gatewayState($result,$order,$payment);
            if ($state === 'paid') {
                WechatPayService::confirmPaidOrder($result);
            } elseif ($close && $state === 'unpaid') {
                $closed = $this->closeGateway($orderSn);
                if (($closed['return_code'] ?? '') === 'SUCCESS' && ($closed['result_code'] ?? '') === 'SUCCESS') {
                    $state = 'closed';
                } else {
                    // ORDERPAID and response loss both require a fresh query, never a guessed close.
                    $result = $this->queryGateway($orderSn);
                    $state = $this->gatewayState($result,$order,$payment);
                    if ($state === 'paid') WechatPayService::confirmPaidOrder($result);
                    elseif ($state !== 'closed') $state = 'unknown';
                }
            }
            if ($state === 'closed' || ($close && $state === 'absent')) {
                Db::name('shop_payment_record')->where('id',$payment['id'])->update(['status'=>'closed','closed_at'=>time(),'updatetime'=>time()]);
                Db::name('shop_order_ext')->where('order_sn',$orderSn)->update(['payment_status'=>'closed','updatetime'=>time()]);
                Db::name('shop_payment_transaction')->where('order_sn',$orderSn)->where('channel_transaction_id','PREPAY:'.$orderSn)->update(['status'=>'CLOSED','updatetime'=>time()]);
                $state = 'closed';
            }
            Db::commit();
            return $state;
        } catch (DomainException $e) {
            Db::rollback(); throw $e;
        } catch (\Throwable $e) {
            Db::rollback();
            // Network/protocol failures keep the payment intent and reservations intact.
            try {
                Db::name('shop_payment_record')->where('order_sn',$orderSn)->where('channel','wechat')
                    ->where('status','in',['created','paying'])->update(['last_query_at'=>time()]);
            } catch (\Throwable $ignored) { /* Database failure will be retried by the next run. */ }
            return 'unknown';
        }
    }

    private function gatewayState(array $result, array $order, array $payment)
    {
        if (($result['return_code'] ?? '') !== 'SUCCESS') return 'unknown';
        if (($result['result_code'] ?? '') !== 'SUCCESS') {
            $attemptedAt=max((int)$payment['createtime'],(int)$payment['updatetime']);
            $knownMerchant=($payment['appid'] ?? '') === (string)getenv('SHOP_WECHAT_APP_ID') && ($payment['mchid'] ?? '') === (string)getenv('SHOP_WECHAT_MCH_ID');
            return ($result['err_code'] ?? '') === 'ORDERNOTEXIST' && $knownMerchant && $attemptedAt <= time()-self::CREATE_GRACE_SECONDS ? 'absent' : 'unknown';
        }
        if (($result['appid'] ?? '') !== (string)getenv('SHOP_WECHAT_APP_ID')
            || ($result['mch_id'] ?? '') !== (string)getenv('SHOP_WECHAT_MCH_ID')
            || ($result['out_trade_no'] ?? '') !== WechatPayService::gatewayOrderSn($order['order_sn'])
            || !isset($result['total_fee']) || (int)$result['total_fee'] !== (int)round((float)$order['saleamount']*100)) return 'unknown';
        $state = $result['trade_state'] ?? '';
        if ($state === 'SUCCESS') return !empty($result['transaction_id']) ? 'paid' : 'unknown';
        if (in_array($state,['CLOSED','REVOKED','PAYERROR'],true)) return 'closed';
        if ($state === 'NOTPAY') return 'unpaid';
        return 'unknown'; // USERPAYING, REFUND, or an unsupported state must not release stock.
    }

    protected function queryGateway($orderSn) { return WechatPayService::queryOrder($orderSn); }
    protected function closeGateway($orderSn) { return WechatPayService::closeOrder($orderSn); }
}
