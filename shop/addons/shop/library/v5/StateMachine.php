<?php

namespace addons\shop\library\v5;

class StateMachine
{
    protected static $transitions = [
        'recommendation' => [
            'draft'     => ['validated', 'blocked', 'expired'],
            'validated' => ['available', 'blocked', 'expired'],
            'available' => ['confirmed', 'blocked', 'expired'],
            'confirmed' => ['ordered', 'blocked', 'expired'],
            'blocked'   => ['validated', 'expired'],
        ],
        'purchase_list' => [
            'draft'    => ['matching', 'expired'],
            'matching' => ['ready', 'expired'],
            'ready'    => ['confirmed', 'matching', 'expired'],
            'confirmed'=> ['ordered', 'expired'],
        ],
        'plan_order' => [
            'pending_payment'   => ['active'],
            'active'            => ['paused', 'exception_handling', 'completed'],
            'paused'            => ['active', 'exception_handling'],
            'exception_handling'=> ['active', 'paused', 'completed'],
        ],
        'batch' => [
            'scheduled'       => ['paused', 'preparing', 'exception'],
            'paused'          => ['scheduled', 'cancelled'],
            'preparing'       => ['supplier_pending', 'exception'],
            'supplier_pending'=> ['shipped', 'exception'],
            'shipped'         => ['delivered', 'exception'],
            'exception'       => ['preparing', 'supplier_pending', 'shipped', 'cancelled'],
        ],
        'supplier_order' => [
            'created'  => ['pushing', 'cancelled'],
            'pushing'  => ['accepted', 'preparing', 'shipped', 'completed', 'rejected', 'exception'],
            'accepted' => ['preparing', 'shipped', 'completed', 'cancelled', 'exception'],
            'rejected' => ['pushing', 'cancelled'],
            'preparing'=> ['shipped', 'completed', 'exception'],
            'shipped'  => ['completed', 'exception'],
            'exception'=> ['pushing', 'preparing', 'shipped', 'completed', 'cancelled'],
        ],
        'refund' => [
            'created'   => ['submitted', 'closed'],
            'submitted' => ['processing', 'success', 'failed'],
            'processing'=> ['success', 'failed'],
            'failed'    => ['submitted', 'closed'],
        ],
    ];

    public static function assertTransition($machine, $from, $to)
    {
        $allowed = isset(self::$transitions[$machine][$from]) ? self::$transitions[$machine][$from] : [];
        if (!in_array($to, $allowed, true)) {
            throw new DomainException('不允许的状态变更', 40903, 409, [
                'machine' => $machine,
                'from'    => $from,
                'to'      => $to,
            ]);
        }
    }

    public static function allowed($machine, $from)
    {
        return isset(self::$transitions[$machine][$from]) ? self::$transitions[$machine][$from] : [];
    }
}
