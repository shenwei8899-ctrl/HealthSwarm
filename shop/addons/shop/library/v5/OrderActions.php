<?php
namespace addons\shop\library\v5;

class OrderActions
{
    public static function forOrder(array $order)
    {
        $paid = (int)$order['paystate'] === 1;
        $open = (int)$order['orderstate'] === 0;
        $normal = ($order['order_type'] ?? 'normal') !== 'plan';
        $actions = [];
        if (!$paid && $open) {
            if ($normal && ($order['payment_status']??'')!=='paying') $actions[] = 'cancel';
            if ((int)($order['expiretime'] ?? 0) > time() && ($order['payment_status'] ?? '') !== 'closed') $actions[] = 'pay';
        }
        if ($normal && $paid && $open && (int)$order['shippingstate'] === 1) $actions[] = 'receive';
        if ($paid && !in_array((int)$order['orderstate'], [1, 2], true)) $actions[] = 'afterSale';
        if ($normal) $actions[] = 'repurchase';
        return $actions;
    }
}
