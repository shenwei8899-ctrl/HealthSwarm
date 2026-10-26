<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\CheckoutService;
use addons\shop\library\v5\DomainException;
use addons\shop\library\v5\DeliveryService;
use addons\shop\library\v5\IdempotencyService;
use addons\shop\library\v5\InventoryService;
use addons\shop\library\v5\Json;
use addons\shop\library\v5\PaymentService;
use addons\shop\library\v5\PlanOrderService;
use addons\shop\library\v5\CartService;
use think\Db;

class CommerceOrder extends Base
{
    public function create()
    {
        return $this->execute(function () {
            $this->requireMethod('POST');
            $payload = $this->input();
            $userId = $this->userId();
            return (new IdempotencyService())->run('commerce.order.create', 'miniapp:' . $userId, $this->request->header('idempotency-key'), $payload, function () use ($userId, $payload) {
                return (new CheckoutService())->createOrder($userId, $payload, $this->requestId);
            });
        });
    }

    public function index()
    {
        return $this->execute(function () {
            $page = max(1, (int)$this->request->get('page', 1));
            $size = min(100, max(1, (int)$this->request->get('page_size', 20)));
            $uid = $this->userId(); $type = $this->request->get('order_type');
            $buildQuery = function () use ($uid, $type) {
                $query = Db::name('shop_order')->alias('o')->join('shop_order_ext e', 'e.order_id=o.id', 'LEFT')->where('o.user_id', $uid);
                if ($type) $query->where('o.order_type', $type);
                return $query;
            };
            $total = $buildQuery()->count('o.id');
            $items = $buildQuery()->field('o.order_sn,o.order_type,o.saleamount,o.paystate,o.orderstate,o.shippingstate,o.createtime,e.business_status,e.payment_status,e.fulfillment_status')->order('o.id', 'desc')->page($page, $size)->select();
            $sns = array_column($items, 'order_sn');
            $lines = $sns ? Db::name('shop_order_goods_ext')->alias('e')->join('shop_order_goods g', 'g.id=e.order_goods_id')->where('e.order_sn', 'in', $sns)->field('e.*,g.goods_sku_id as sku_id,g.nums as quantity')->select() : [];
            foreach ($items as &$summary) {
                $summary['items'] = [];
                foreach ($lines as $line) {
                    if ($line['order_sn'] !== $summary['order_sn']) continue;
                    $line['sku_snapshot'] = Json::decode($line['sku_snapshot_json'], []);
                    unset($line['sku_snapshot_json'], $line['ingredient_snapshot_json']);
                    $summary['items'][] = $line;
                }
            }
            return ['items' => $items, 'total' => $total, 'page' => $page, 'page_size' => $size];
        });
    }

    public function detail($order_sn = null)
    {
        $order_sn = $order_sn ?? $this->request->route('order_sn');
        return $this->execute(function () use ($order_sn) {
            $order = Db::name('shop_order')->where('order_sn', $order_sn)->where('user_id', $this->userId())->find();
            if (!$order) {
                throw new DomainException('订单不存在', 40409, 404);
            }
            $ext = Db::name('shop_order_ext')->where('order_sn', $order_sn)->find();
            if ($ext) {
                $ext['address_snapshot'] = Json::decode($ext['address_snapshot_json'], []);
                $ext['pricing_snapshot'] = Json::decode($ext['pricing_snapshot_json'], []);
                unset($ext['address_snapshot_json'], $ext['pricing_snapshot_json']);
            }
            $items = Db::name('shop_order_goods_ext')->alias('e')->join('shop_order_goods g', 'g.id=e.order_goods_id')->where('e.order_sn', $order_sn)->field('e.*,g.goods_sku_id as sku_id,g.nums as quantity')->select();
            foreach ($items as &$item) {
                $item['sku_snapshot'] = Json::decode($item['sku_snapshot_json'], []);
                unset($item['sku_snapshot_json'], $item['ingredient_snapshot_json']);
            }
            $result = ['local_test_payment' => LocalTestPayment::enabled(), 'order' => $order, 'extension' => $ext, 'items' => $items, 'allowed_actions' => \addons\shop\library\v5\OrderActions::forOrder($order + ['payment_status' => $ext['payment_status'] ?? ''])];
            if ($order['order_type'] === 'plan') {
                $planOrder = Db::name('shop_service_plan_order')->where('order_sn', $order_sn)->find();
                $result['plan_order'] = $planOrder;
                $result['delivery_batches'] = $planOrder ? Db::name('shop_plan_delivery_batch')->where('plan_order_id', $planOrder['id'])->order('batch_no', 'asc')->select() : [];
            }
            return $result;
        });
    }

    public function payment($order_sn = null)
    {
        $order_sn = $order_sn ?? $this->request->route('order_sn');
        return $this->execute(function () use ($order_sn) {
            $this->requireMethod('POST');
            $payload = $this->input();
            $uid=$this->userId();
            return (new IdempotencyService())->run('commerce.payment.create','miniapp:'.$uid,$this->request->header('idempotency-key'),['order_sn'=>$order_sn]+$payload,function()use($uid,$order_sn,$payload){return (new PaymentService())->createWechat($uid,$order_sn,isset($payload['payer_openid'])?$payload['payer_openid']:'',$this->requestId);},1800,false);
        });
    }

    public function paymentStatus($order_sn = null)
    {
        $order_sn = $order_sn ?? $this->request->route('order_sn');
        return $this->execute(function () use ($order_sn) {
            $order = Db::name('shop_order')->where('order_sn', $order_sn)->where('user_id', $this->userId())->find();
            if (!$order) {
                throw new DomainException('订单不存在', 40409, 404);
            }
            $reconciled = (new \addons\shop\library\v5\WechatPaymentLifecycle())->reconcile($order_sn, false, $this->userId());
            $payment = Db::name('shop_payment_record')->where('order_sn', $order_sn)->order('id', 'desc')->find();
            return [
                'status' => $payment ? $payment['status'] : ((int)$order['paystate'] === 1 ? 'paid' : 'unpaid'),
                'reconciliation_status' => $reconciled,
                'transaction_id_masked' => $payment && $payment['channel_transaction_id'] ? substr($payment['channel_transaction_id'], 0, 4) . '***' . substr($payment['channel_transaction_id'], -4) : '',
                'confirmed_at' => $payment && $payment['paid_at'] ? date(DATE_ATOM, $payment['paid_at']) : null,
            ];
        });
    }

    public function cancel($order_sn = null)
    {
        $order_sn = $order_sn ?? $this->request->route('order_sn');
        return $this->execute(function () use ($order_sn) {
            $this->requireMethod('POST');
            $payload = $this->input();
            $userId = $this->userId();
            return (new IdempotencyService())->run('commerce.order.cancel', 'miniapp:' . $userId, $this->request->header('idempotency-key'), ['order_sn' => $order_sn] + $payload, function () use ($order_sn, $userId) {
            $owned=Db::name('shop_order')->where('order_sn',$order_sn)->where('user_id',$userId)->find();
            if (!$owned) throw new DomainException('订单不存在',40409,404);
            if ($owned['order_type']==='plan') throw new DomainException('专属计划未付款订单等待自动关闭',40930,409);
            if ((int)$owned['paystate']!==0 || (int)$owned['orderstate']!==0) throw new DomainException('当前订单不允许取消',40934,409);
            // Commit any successful gateway reconciliation before checking cancellation.
            (new \addons\shop\library\v5\WechatPaymentLifecycle())->reconcile($order_sn, true, $userId);
            Db::startTrans();
            try {
            $order = Db::name('shop_order')->where('order_sn', $order_sn)->where('user_id', $userId)->lock(true)->find();
            if (!$order) {
                throw new DomainException('订单不存在', 40409, 404);
            }
            if ($order['order_type'] === 'plan') {
                throw new DomainException('专属计划请使用取消剩余批次入口；未付款订单等待自动关闭', 40930, 409);
            }
            if ((int)$order['paystate'] !== 0 || (int)$order['orderstate'] !== 0) {
                throw new DomainException('当前订单不允许取消', 40934, 409);
            }
            if ((new PaymentService())->hasPending($order_sn)) throw new DomainException('支付结果尚未确认，请稍后重试取消',40936,409,['retryable'=>true]);
            Db::name('shop_order')->where('id', $order['id'])->update(['orderstate' => 1, 'canceltime' => time(), 'updatetime' => time()]);
            $ext = Db::name('shop_order_ext')->where('order_sn', $order_sn)->find();
            Db::name('shop_order_ext')->where('order_sn', $order_sn)->update(['business_status' => 'cancelled', 'updatetime' => time()]);
            $reservations = Db::name('shop_inventory_reservation')->where('source_type', 'checkout')->where('source_ref', $ext['checkout_token_hash'])->where('status', 'active')->select();
            foreach ($reservations as $reservation) {
                (new InventoryService())->release($reservation['reservation_sn'], 'user_cancelled', $this->requestId);
            }
            (new DeliveryService())->releaseSlot($order_sn);
            Db::commit();
            return ['order_sn' => $order_sn, 'status' => 'cancelled'];
            } catch (\Throwable $e) { Db::rollback(); throw $e; }
            });
        });
    }

    public function pause($order_sn = null)
    {
        $order_sn = $order_sn ?? $this->request->route('order_sn');
        return $this->execute(function () use ($order_sn) {
            $payload = $this->input();
            $uid=$this->userId();return (new IdempotencyService())->run('commerce.plan.pause','miniapp:'.$uid,$this->request->header('idempotency-key'),['order_sn'=>$order_sn]+$payload,function()use($uid,$order_sn,$payload){return (new PlanOrderService())->pause($uid,$order_sn,$payload['version'],$this->requestId);});
        });
    }

    public function resume($order_sn = null)
    {
        $order_sn = $order_sn ?? $this->request->route('order_sn');
        return $this->execute(function () use ($order_sn) {
            $payload = $this->input();
            $uid=$this->userId();return (new IdempotencyService())->run('commerce.plan.resume','miniapp:'.$uid,$this->request->header('idempotency-key'),['order_sn'=>$order_sn]+$payload,function()use($uid,$order_sn,$payload){return (new \addons\shop\library\v5\PlanChangeService())->preview($uid,$order_sn,'resume',$payload,$this->requestId);});
        });
    }

    public function cancelRemaining($order_sn = null)
    {
        return $this->execute(function () use ($order_sn) {
            $this->requireMethod('POST');$p=$this->input();$uid=$this->userId();
            return (new IdempotencyService())->run('commerce.plan.cancel_remaining','miniapp:'.$uid,$this->request->header('idempotency-key'),['order_sn'=>$order_sn]+$p,function () use ($uid,$order_sn,$p) {
                return (new \addons\shop\library\v5\PlanChangeService())->preview($uid,$order_sn,'cancel_remaining',$p,$this->requestId);
            },300);
        });
    }

    public function confirmPlanChange($order_sn = null)
    {
        return $this->execute(function () use ($order_sn) {
            $this->requireMethod('POST');$p=$this->input();$uid=$this->userId();
            return (new IdempotencyService())->run('commerce.plan.confirm_change','miniapp:'.$uid,$this->request->header('idempotency-key'),['order_sn'=>$order_sn]+$p,function () use ($uid,$order_sn,$p) {
                return (new \addons\shop\library\v5\PlanChangeService())->confirm($uid,$order_sn,$p['change_request_sn'] ?? '',$this->requestId);
            });
        });
    }

    public function resumeDates($order_sn = null)
    {
        return $this->execute(function () use ($order_sn) {
            return (new \addons\shop\library\v5\PlanChangeService())->resumeDates($this->userId(),$order_sn,$this->request->get('address_id'),$this->request->get('delivery_slot_id',0));
        });
    }

    public function receipt($order_sn = null)
    {
        $order_sn = $order_sn ?? $this->request->route('order_sn');
        return $this->execute(function () use ($order_sn) {
            $this->requireMethod('POST');
            $payload=$this->input();$uid=$this->userId();
            return(new IdempotencyService())->run('commerce.order.receipt','miniapp:'.$uid,$this->request->header('idempotency-key'),['order_sn'=>$order_sn]+$payload,function()use($uid,$order_sn){
            Db::startTrans();
            try {
            $order=Db::name('shop_order')->where('order_sn',$order_sn)->where('user_id',$uid)->lock(true)->find();
            if(!$order) throw new DomainException('订单不存在',40409,404);
            if($order['order_type']==='plan') throw new DomainException('专属计划请按配送批次确认收货',40910,409);
            if((int)$order['paystate']!==1 || (int)$order['shippingstate']!==1 || (int)$order['orderstate']!==0) throw new DomainException('当前订单不可确认收货',40910,409);
            Db::name('shop_order')->where('id',$order['id'])->update(['shippingstate'=>2,'orderstate'=>3,'receivetime'=>time(),'updatetime'=>time()]);
            Db::name('shop_order_ext')->where('order_id',$order['id'])->update(['business_status'=>'completed','fulfillment_status'=>'completed','updatetime'=>time()]);
            if (!Db::name('shop_fulfillment_event')->where('event_id','receipt:'.$order_sn)->find()) Db::name('shop_fulfillment_event')->insert(['event_id'=>'receipt:'.$order_sn,'source_type'=>'member','source_ref'=>(string)$uid,'platform_order_sn'=>$order_sn,'source_status'=>'delivered','normalized_status'=>'delivered','occurred_at'=>time(),'description'=>'用户已确认收货','payload_json'=>'{}','createtime'=>time()]);
            (new DeliveryService())->releaseSlot($order_sn);
            Db::commit();
            return ['order_sn'=>$order_sn,'status'=>'completed'];
            } catch (\Throwable $e) { Db::rollback(); throw $e; }
            });
        });
    }

    public function repurchase($order_sn = null)
    {
        $order_sn = $order_sn ?? $this->request->route('order_sn');
        return $this->execute(function () use ($order_sn) {
            $this->requireMethod('POST');
            $payload=$this->input();$uid=$this->userId();
            return(new IdempotencyService())->run('commerce.order.repurchase','miniapp:'.$uid,$this->request->header('idempotency-key'),['order_sn'=>$order_sn]+$payload,function()use($uid,$order_sn){
            $order=Db::name('shop_order')->where('order_sn',$order_sn)->where('user_id',$uid)->find();
            if(!$order) throw new DomainException('订单不存在',40409,404);
            $items=Db::name('shop_order_goods')->where('order_sn',$order['order_sn'])->select();$invalid=[];$cart=new CartService();
            foreach($items as $item){try{$cart->add($order['user_id'],$item['goods_sku_id'],$item['nums'],['source_type'=>'repurchase','source_ref'=>$order_sn]);}catch(\Exception $e){$invalid[]=['order_item_id'=>(string)$item['id'],'reason'=>$e->getMessage()];}}
            return ['cart'=>$cart->listItems($order['user_id']),'invalid_items'=>$invalid];
            });
        });
    }

    public function timeline($order_sn = null)
    {
        $order_sn = $order_sn ?? $this->request->route('order_sn');
        return $this->execute(function () use ($order_sn) {$order=Db::name('shop_order')->where('order_sn',$order_sn)->where('user_id',$this->userId())->find();if(!$order)throw new DomainException('订单不存在',40409,404);$actions=Db::name('shop_order_action')->where('order_sn',$order_sn)->order('id','asc')->select();$fulfillment=Db::name('shop_fulfillment_event')->where('platform_order_sn',$order_sn)->order('occurred_at','asc')->select();return ['order_sn'=>$order_sn,'order_status'=>['paystate'=>$order['paystate'],'shippingstate'=>$order['shippingstate'],'orderstate'=>$order['orderstate']],'actions'=>$actions,'fulfillment_events'=>$fulfillment];});
    }

    public function planDetail($order_sn = null)
    {
        $order_sn = $order_sn ?? $this->request->route('order_sn');
        return $this->detail($order_sn);
    }

    public function batches($order_sn = null)
    {
        $order_sn = $order_sn ?? $this->request->route('order_sn');
        return $this->execute(function () use ($order_sn) { $po=Db::name('shop_service_plan_order')->where('order_sn',$order_sn)->where('user_id',$this->userId())->find();if(!$po)throw new DomainException('计划订单不存在',40410,404);return ['plan_order'=>$po,'items'=>Db::name('shop_plan_delivery_batch')->where('plan_order_id',$po['id'])->order('batch_no','asc')->select()]; });
    }

    public function batchAddress($order_sn = null, $batch_no = null)
    {
        return $this->execute(function () use ($order_sn,$batch_no) { $p=$this->input();$uid=$this->userId();return(new IdempotencyService())->run('commerce.plan.batch_address','miniapp:'.$uid,$this->request->header('idempotency-key'),['order_sn'=>$order_sn,'batch_no'=>$batch_no]+$p,function()use($uid,$order_sn,$batch_no,$p){return (new PlanOrderService())->changeBatchAddress($uid,$order_sn,$batch_no,$p['version'],$p['address_id'],isset($p['delivery_slot_id'])?$p['delivery_slot_id']:0,$this->requestId);}); });
    }

    public function batchReceipt($order_sn = null, $batch_no = null)
    {
        return $this->execute(function () use ($order_sn,$batch_no) { $p=$this->input();$uid=$this->userId();return(new IdempotencyService())->run('commerce.plan.batch_receipt','miniapp:'.$uid,$this->request->header('idempotency-key'),['order_sn'=>$order_sn,'batch_no'=>$batch_no]+$p,function()use($uid,$order_sn,$batch_no,$p){return (new PlanOrderService())->receiptBatch($uid,$order_sn,$batch_no,$p['version'],$this->requestId);}); });
    }
}
