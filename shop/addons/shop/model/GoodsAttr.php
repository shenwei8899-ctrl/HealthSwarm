<?php

namespace addons\shop\model;

use think\Model;
use think\Db;

class GoodsAttr extends Model
{

    // 表名
    protected $name = 'shop_goods_attr';

    // 自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';

    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    protected $deleteTime = false;

    // 追加属性
    protected $append = [];

    //查询符合的goods_id
    public static function getGoodsIds($attributes)
    {
        if (!is_array($attributes) && empty($attributes)) {
            return [];
        }
        $attributes = array_values($attributes);
        $attrSql = '';
        $whereSql = '1=1';
        foreach ($attributes as $key => $item) {
            $sql = self::field('goods_id')->where('attribute_id', $item['attribute_id'])->where('value_id', 'IN', $item['value_id'])->fetchSql(true)->select();
            if (!$key) {
                $attrSql .= "({$sql}) AS A{$key}";
            } else {
                $attrSql .= " INNER JOIN ({$sql}) AS A{$key}";
                $k = $key - 1;
                $whereSql .= " AND A{$k}.goods_id = A{$key}.goods_id";
            }
        }
        $sql = "SELECT * FROM {$attrSql} WHERE {$whereSql}";
        $list = Db::query($sql);
        return array_unique(array_column($list, 'goods_id'));

        $valueIds = [];
        foreach ($attributes as $key => $item) {
            $valueIds = array_merge($valueIds, explode(',', $item['value_id']));
        }
        $goodsAttrList = GoodsAttr::field('goods_id')->where('value_id', 'in', $valueIds)->column('value_id,attribute_id,goods_id');
        $goodsArr = [];
        foreach ($goodsAttrList as $index => $attr) {
            $goodsArr[$attr['goods_id']][$attr['attribute_id']] = $attr['value_id'];
        }
        $goodsIds = [];
        foreach ($goodsArr as $index => $item) {
            if (count($item) >= count($attributes)) {
                $goodsIds[] = $index;
            }
        }
        return array_unique($goodsIds);
    }
}
