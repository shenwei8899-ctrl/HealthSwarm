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
            throw new DomainException('专属计划付款后不支持因个人原因取消或退款', 40930, 409, [
                'allowed_exception_reasons' => $this->planExceptionReasons,
            ]);
        }
        $ext = Db::name('shop_order_goods_ext')->where('order_goods_id', (int)$orderGoodsId)->find();
        if (!$ext || !(int)$ext['plan_batch_id']) {
            throw new DomainException('计划售后必须关联具体配送批次', 40931, 409);
        }
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
            throw new DomainException('专属计划仅允许平台责任或法律强制情形退款', 40930, 409);
        }
    }
}
