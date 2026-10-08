<?php

namespace addons\shop\model;

use think\Model;

/**
 * 模型
 */
class Sku extends Model
{

    // 表名
    protected $name = 'shop_goods_sku';
    // 开启自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';
    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    // 追加属性
    protected $append = [
    ];

    protected static $config = [];

    protected static $tagCount = 0;

    protected static function init()
    {
        $config = get_addon_config('shop');
        self::$config = $config;
    }

    public function getImageAttr($value, $data)
    {
        if (!$value) {
            return $value;
        }
        $value = $value ? $value : '';
        return cdnurl($value, true);
    }

    public function goods()
    {
        return $this->belongsTo("Goods", "goods_id", "id", [], 'LEFT');
    }

}
