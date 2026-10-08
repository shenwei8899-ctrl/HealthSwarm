<?php

namespace addons\shop\model;

use think\Model;

/**
 * 商品属性
 * Class AttributeValue
 * @package addons\shop\model
 */
class AttributeValue extends Model
{

    // 表名
    protected $name = 'shop_attribute_value';

    // 自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';

    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    protected $deleteTime = false;

    // 追加属性
    protected $append = [];

    /**
     * 获取商品属性
     * @param $attribute_ids
     * @return array|false|\PDOStatement|string|\think\Collection
     */
    public static function getAttributeList($attribute_ids)
    {
        if (!$attribute_ids) {
            return [];
        }
        $list = self::with([
            'AttributeValue' => function ($query) use ($attribute_ids) {
                $query->field('id,attribute_id,name')->where('id', 'in', $attribute_ids);
            },
            'Attribute'
        ])
            ->field('MIN("id") AS "id", "attribute_id"')
            ->where('id', 'in', $attribute_ids)
            ->group('attribute_id')
            ->select();
        return $list;
    }

    public function AttributeValue()
    {
        return $this->hasMany('AttributeValue', 'attribute_id', 'attribute_id');
    }

    public function Attribute()
    {
        return $this->hasOne('Attribute', 'id', 'attribute_id', [], 'LEFT')->bind('name');
    }
}
