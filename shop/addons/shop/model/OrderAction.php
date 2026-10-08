<?php

namespace addons\shop\model;

use think\Model;

/**
 * 模型
 */
class OrderAction extends Model
{

    // 表名
    protected $name = 'shop_order_action';
    // 开启自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';
    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = '';
    // 追加属性
    protected $append = [];


    public static function push($order_sn, $operator, $memo)
    {
        self::create([
            'order_sn' => $order_sn,
            'operator' => $operator,
            'memo' => $memo
        ]);
        return true;
    }
}
