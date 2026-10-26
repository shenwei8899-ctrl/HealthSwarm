<?php

namespace addons\shop\library\v5;

use think\Db;

class AftersalePolicyService
{
    protected $planExceptionReasons = [
        'platform_non_delivery',
        'wrong_item',
        'missing_item',
        'food_quality',
        'quality_issue',
        'legal_required',
        'legal_mandatory',
    ];

    public function assertUserApplicationAllowed($orderSn, $orderGoodsId, $reasonCode)
    {
        $order = Db::name('shop_order')->where('order_sn', $orderSn)->find();
        if (!$order || $order['order_type'] !== 'plan') {
            return ['source_type' => 'normal', 'batch_id' => 0];
        }
        if (!in_array($reasonCode, $this->planExceptionReasons, true)) {
            throw new DomainException('取消未执行的批次请使用取消剩余计划入口；本入口处理具体商品售后', 40930, 409, [
                'allowed_exception_reasons' => $this->planExceptionReasons,
            ]);
        }
        $ext = Db::name('shop_order_goods_ext')->where('order_goods_id', (int)$orderGoodsId)->find();
        if (!$ext || !(int)$ext['plan_batch_id']) {
            throw new DomainException('计划售后必须关联具体配送批次', 40931, 409);
        }
        $this->assertBatchAvailable($order,(int)$ext['plan_batch_id']);
        return ['source_type' => 'plan_exception', 'batch_id' => (int)$ext['plan_batch_id']];
    }

    public function assertAdminRefundAllowed($orderSn, $aftersale)
    {
        $order = Db::name('shop_order')->where('order_sn', $orderSn)->find();
        if (!$order || $order['order_type'] !== 'plan') {
            return;
        }
        $sourceType = is_array($aftersale) ? $aftersale['source_type'] : $aftersale->source_type;
        $reasonCode = is_array($aftersale) ? $aftersale['reason_code'] : $aftersale->reason_code;
        if ($sourceType !== 'plan_exception' || !in_array($reasonCode, $this->planExceptionReasons, true)) {
            throw new DomainException('本售后入口只处理批次商品问题；取消剩余计划使用独立退款流程', 40930, 409);
        }
        $this->assertBatchAvailable($order,(int)(is_array($aftersale)?$aftersale['batch_id']:$aftersale->batch_id));
    }

    /** 调用方先锁订单，再与剩余取消共用 plan→batch 锁序。 */
    private function assertBatchAvailable(array $order,$batchId)
    {
        $plan=Db::name('shop_service_plan_order')->where('order_id',$order['id'])->lock(true)->find();
        $batch=$plan?Db::name('shop_plan_delivery_batch')->where('plan_order_id',$plan['id'])->where('id',$batchId)->lock(true)->find():null;
        if (!$batch) throw new DomainException('计划售后必须关联本订单的配送批次',40931,409);
        $reserved=Db::name('shop_refund_allocation')->alias('a')->join('shop_refund_record r','r.id=a.refund_id')
            ->where('a.batch_id',$batchId)->where('a.allocation_type','plan_remaining')->where('r.status','not in',['closed','cancelled'])->count();
        if ($reserved || in_array($batch['status'],['refund_pending','refunded','cancelled'],true)) throw new DomainException('该批次已取消或正在退款，不能重复申请商品售后',40935,409);
    }

    /** 调用方持有订单锁；终态售后不再阻断尚未执行的批次。 */
    public function refreshBatchStatus($batchId)
    {
        if (!$batchId) return;
        $open=Db::name('shop_order_aftersales')->where('batch_id',$batchId)->where('status','in',[1,2])->count();
        Db::name('shop_plan_delivery_batch')->where('id',$batchId)->update(['aftersale_status'=>$open?'pending':'none','row_version'=>Db::raw('row_version+1'),'updatetime'=>time()]);
    }
}
