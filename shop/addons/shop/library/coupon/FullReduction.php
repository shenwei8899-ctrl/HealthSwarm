<?php

namespace addons\shop\library\coupon;

//订单满xx减xx
class FullReduction implements calculateInterface
{

    public function calculate($result_data, $money)
    {
        $arr = is_array($result_data) ? $result_data : (array)json_decode($result_data, true);
        if ($arr['money'] > 0 && $arr['money'] > $money) {
            throw new \Exception('订单金额未满足优惠条件');
        }
        $coupon_money = $arr['number'];
        $new_money = bcsub($money, $coupon_money, 2);
        return [$new_money, $coupon_money];
    }
}
