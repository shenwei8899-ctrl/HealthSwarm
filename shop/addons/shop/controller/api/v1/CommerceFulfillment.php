<?php

namespace addons\shop\controller\api\v1;

use addons\shop\library\v5\DomainException;
use addons\shop\library\v5\IdempotencyService;
use think\Db;

class CommerceFulfillment extends Base
{
    public function timeline($order_sn = null)
    {
        return $this->execute(function () use ($order_sn) {
            $order = Db::name('shop_order')->where('order_sn', $order_sn)->where('user_id', $this->userId())->find();
            if (!$order) {
                throw new DomainException('订单不存在', 40409, 404);
            }
            $events = Db::name('shop_fulfillment_event')->where('platform_order_sn', $order_sn)->order('occurred_at', 'asc')->select();
            return ['order_sn' => $order_sn, 'events' => $events];
        });
    }

    public function batchTimeline($order_sn = null, $batch_no = null)
    {
        return $this->execute(function () use ($order_sn,$batch_no) {
            $po=Db::name('shop_service_plan_order')->where('order_sn',$order_sn)->where('user_id',$this->userId())->find();
            $batch=$po?Db::name('shop_plan_delivery_batch')->where('plan_order_id',$po['id'])->where('batch_no',(int)$batch_no)->find():null;
            if(!$batch)throw new DomainException('配送批次不存在',40410,404);
            return ['batch'=>$batch,'events'=>Db::name('shop_fulfillment_event')->where('plan_batch_id',$batch['id'])->order('occurred_at','asc')->select()];
        });
    }

    public function deliveryIssue($order_sn = null)
    {
        return $this->execute(function () use ($order_sn) {
            $this->requireMethod('POST');$p=$this->input();$uid=$this->userId();
            return(new IdempotencyService())->run('commerce.fulfillment.delivery_issue','miniapp:'.$uid,$this->request->header('idempotency-key'),['order_sn'=>$order_sn]+$p,function()use($uid,$order_sn,$p){
            $order=Db::name('shop_order')->where('order_sn',$order_sn)->where('user_id',$uid)->find();
            if(!$order)throw new DomainException('订单不存在',40409,404);
            $sn=(new \addons\shop\library\v5\ExceptionService())->open('user_delivery_issue:'.$order_sn.':'.$this->requestId,'fulfillment','user_reported',isset($p['description'])?$p['description']:'用户上报配送问题',['resource_type'=>'order','resource_ref'=>$order_sn,'order_sn'=>$order_sn],$p,'medium');
            return ['accepted'=>true,'exception'=>$sn];
            });
        });
    }
}
