<?php

namespace addons\shop\library\v5;

use think\Db;

class PaymentService
{
    public function createWechat($userId, $orderSn, $openid, $requestId)
    {
        if (!\addons\shop\library\service\WechatPayService::isConfigured()) throw new DomainException('微信商户支付尚未配置',50301,503);
        $openid=(string)Db::name('shop_miniapp_identity')->where('user_id',$userId)->where('app_id',(string)getenv('SHOP_WECHAT_APP_ID'))->value('openid');
        if ($openid==='') throw new DomainException('请先验证微信支付身份',40935,409);
        // Commit the order-owned payment intent before contacting the gateway.
        Db::startTrans();
        try {
            $order=Db::name('shop_order')->where('order_sn',$orderSn)->where('user_id',$userId)->lock(true)->find();
            if (!$order) throw new DomainException('订单不存在',40409,404);
            if ((int)$order['paystate']===1) throw new DomainException('订单已支付',40923,409);
            if ((int)$order['orderstate']!==0 || (int)$order['expiretime']<=time()) throw new DomainException('订单已失效',40924,409);
            $latest=Db::name('shop_payment_record')->where('order_sn',$orderSn)->order('id','desc')->find();
            if ($latest && ($latest['channel']!=='wechat' || $latest['status']==='closed')) throw new DomainException('支付单已关闭或渠道不同，请重新下单',40938,409);
            $payment=Db::name('shop_payment_record')->where('order_sn',$orderSn)->where('status','in',['created','paying'])->order('id','desc')->find();
            $paymentSn=$payment?$payment['payment_sn']:Identifiers::make('pay');
            if (!$payment) Db::name('shop_payment_record')->insert([
                'payment_sn'=>$paymentSn,'order_sn'=>$orderSn,'channel'=>'wechat','amount_cent'=>(int)round((float)$order['saleamount']*100),
                'appid'=>(string)getenv('SHOP_WECHAT_APP_ID'),'mchid'=>(string)getenv('SHOP_WECHAT_MCH_ID'),
                'currency'=>'CNY','status'=>'paying','request_id'=>$requestId,'createtime'=>time(),'updatetime'=>time(),
            ]);
            else Db::name('shop_payment_record')->where('id',$payment['id'])->update(['updatetime'=>time()]);
            Db::name('shop_order_ext')->where('order_sn',$orderSn)->update(['payment_status'=>'paying','updatetime'=>time()]);
            \addons\shop\library\service\WechatPayService::prepareOrder($order);
            Db::commit();
        } catch (\Throwable $e) { Db::rollback(); throw $e; }
        Db::startTrans();
        try {
            // The durable intent above survives a worker failure. This second lock prevents
            // a concurrent cancellation/query from racing the actual gateway create call.
            $order=Db::name('shop_order')->where('order_sn',$orderSn)->where('user_id',$userId)->lock(true)->find();
            if ((int)$order['paystate']===1) throw new DomainException('订单已支付',40923,409);
            if ((int)$order['orderstate']!==0 || (int)$order['expiretime']<=time()) throw new DomainException('订单已失效',40924,409);
            $payment=Db::name('shop_payment_record')->where('payment_sn',$paymentSn)->find();
            if (!$payment || !in_array($payment['status'],['created','paying'],true)) throw new DomainException('支付意图已关闭，请重新下单',40938,409);
            $cached=Db::name('shop_payment_transaction')->where('order_sn',$orderSn)->where('channel_transaction_id','PREPAY:'.$orderSn)->where('status','PENDING')->find();
            if ($cached && (int)$cached['updatetime'] > time()-6600) {
                $params=Json::decode($cached['request_json'],[]);
                if (!empty($params['parameters'])) { Db::commit(); return ['payment_sn'=>$paymentSn,'payment_params'=>$params['parameters']]; }
            }
            $notifyUrl=trim((string)getenv('SHOP_WECHAT_NOTIFY_URL')) ?: \think\Request::instance()->domain().'/api/v1/payment/wechat/notify';
            $response=$this->createGatewayPayment($orderSn,$userId,$openid,$notifyUrl);
            Db::commit();
            return ['payment_sn'=>$paymentSn,'payment_params'=>$response['parameters']];
        } catch (DomainException $e) {
            Db::rollback(); throw $e;
        } catch (\Throwable $e) {
            Db::rollback();
            // A lost gateway response does not prove failure; keep cancellation and expiry blocked.
            (new ExceptionService())->open('payment_create:'.$paymentSn,'payment','wechat_payment_result_unknown','微信支付结果待核对',[
                'resource_type'=>'payment','resource_ref'=>$paymentSn,'order_sn'=>$orderSn,
            ],[],'high');
            throw new DomainException('微信支付结果尚未确认，请查询订单或联系商城核对',50201,502,['retryable'=>true]);
        }
    }

    public function hasPending($orderSn)
    {
        return (bool)Db::name('shop_payment_record')->where('order_sn',$orderSn)->where('status','in',['created','paying'])->count();
    }

    protected function createGatewayPayment($orderSn,$userId,$openid,$notifyUrl)
    {
        return \addons\shop\library\service\WechatPayService::createMiniProgramPayment($orderSn,$userId,$openid,$notifyUrl);
    }

    public function onPaid($orderSn, $amountCent, $transactionId, $notifyId = '', $channel = 'wechat')
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
            $order=Db::name('shop_order')->where('id',$order['id'])->lock(true)->find();
            $closed=in_array((int)$order['orderstate'],[1,2],true);
            if (!empty($order['transactionid']) && $order['transactionid'] !== $transactionId) {
                throw new DomainException('订单已有另一笔付款，请核对支付流水',40938,409);
            }
            $newlySynchronized = (int)$order['paystate'] === 0;
            if ((int)$order['paystate']===0) Db::name('shop_order')->where('id',$order['id'])->update([
                'paystate'=>1,'payamount'=>number_format($amountCent/100,2,'.',''),'transactionid'=>$transactionId,
                'paytype'=>$channel,'method'=>'miniapp','paytime'=>time(),'updatetime'=>time(),
            ]);
            $ext = Db::name('shop_order_ext')->where('id', $ext['id'])->lock(true)->find();
            $payment = Db::name('shop_payment_record')->where('order_sn', $orderSn)->order('id', 'desc')->lock(true)->find();
            if (!$payment) {
                Db::name('shop_payment_record')->insert([
                    'payment_sn' => Identifiers::make('pay'), 'order_sn' => $orderSn, 'channel' => $channel,
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
            $recoverInitialState = in_array($ext['payment_status'], ['created','unpaid','paying'], true)
                && $ext['business_status'] === 'created';
            if ($newlySynchronized || $recoverInitialState) {
                Db::name('shop_order_ext')->where('id', $ext['id'])->update([
                    'business_status' => $closed?'payment_exception':'paid', 'payment_status' => 'paid',
                    'row_version' => (int)$ext['row_version'] + 1, 'updatetime' => time(),
                ]);
            }
            if (!$closed && $order['order_type'] === 'plan'
                && ($newlySynchronized || $recoverInitialState || $ext['payment_status'] === 'paid')) {
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
            if ($closed) {
                (new ExceptionService())->open('paid_after_close:'.$orderSn,'payment','paid_after_close','已关闭订单收到付款，需核对退款',['order_sn'=>$orderSn,'resource_ref'=>$orderSn],[],'high');
                Db::commit();
                return true;
            }
            if ($newlySynchronized) {
                \addons\shop\model\OrderGoods::setGoodsSalesInc($orderSn);
                \addons\shop\model\OrderAction::push($orderSn,'系统','订单支付成功');
            }
            // 仅首次付款或仍待恢复的履约可继续；重复通知不能回退收货和退款状态。
            $recoverable = (int)$order['orderstate'] === 0 && (int)$order['shippingstate'] === 0
                && $ext['payment_status'] === 'paid' && $ext['business_status'] === 'paid'
                && $ext['fulfillment_status'] === 'pending';
            if ($order['order_type'] !== 'plan' && ($newlySynchronized || $recoverInitialState || $recoverable)) {
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
            Db::commit();
            return true;
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }
}
