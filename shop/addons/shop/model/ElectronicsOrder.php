<?php

namespace addons\shop\model;

use think\Model;


class ElectronicsOrder extends Model
{

    // 表名
    protected $name = 'shop_electronics_order';

    // 自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';

    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    protected $deleteTime = false;

    // 追加属性
    protected $append = [

    ];

    public function Shipper()
    {
        return $this->hasOne('Shipper', 'id', 'shipper_id', [], 'LEFT');
    }

}
