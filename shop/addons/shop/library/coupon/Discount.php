<?php

namespace addons\shop\library\coupon;

//订单满xx打xx折
class Discount implements calculateInterface
{
    public function calculate($result_data, $money)
    {
        $arr = is_array($result_data) ? $result_data : (array)json_decode($result_data, true);
        if ($arr['money'] > 0 && $arr['money'] > $money) {
            throw new \Exception('订单金额未满足优惠条件');
        }
        $new_money = bcmul(bcdiv($arr['number'], 10, 2), $money, 2);
        $coupon_money = bcsub($money, $new_money, 2);
        return [$new_money, $coupon_money];
    }
}
