<?php

namespace addons\shop\library\coupon;

class ToCalculate
{
    public $obj;

    public function __construct(calculateInterface $obj)
    {
        $this->obj = $obj;
    }

    public function doing($result_data,$money)
    {
        return $this->obj->calculate($result_data,$money);
    }
}
