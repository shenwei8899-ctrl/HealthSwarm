<?php

namespace addons\shop\model;

use think\Model;

/**
 * 规格模型
 */
class Spec extends Model
{

    // 表名
    protected $name = 'shop_spec';
    // 开启自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';
    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    // 追加属性
    protected $append = [
    ];

}
