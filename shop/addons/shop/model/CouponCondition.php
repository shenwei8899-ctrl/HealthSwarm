<?php

namespace addons\shop\model;

use think\Model;


class CouponCondition extends Model
{


    // 表名
    protected $name = 'shop_coupon_condition';

    // 自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';

    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    protected $deleteTime = false;

    // 追加属性
    protected $append = [
        'type_text'
    ];



    public function getTypeList()
    {
        return ['1' => __('Type 1'), '2' => __('Type 2'), '3' => __('Type 3'), '4' => __('Type 4')];
    }


    public function getTypeTextAttr($value, $data)
    {
        $value = $value ?: ($data['type'] ?? '');
        $list = $this->getTypeList();
        return $list[$value] ?? '';
    }

    /**
     * @ 获取指定商品的优惠券条件id
     * @param $goods_ids
     * @param $category_ids
     * @param $brand_ids
     * @param $type
     * @return bool|\PDOStatement|string|\think\Collection
     */
    public static function getGoodsCondition($goods_ids, $category_ids = [], $brand_ids = [], $type = 2)
    {
        return self::where('type', $type)
            ->whereOr(function ($query) use ($goods_ids) {
                $sql = '1=2';
                if (is_array($goods_ids)) {
                    foreach ($goods_ids as $id) {
                        $sql .= " OR FIND_IN_SET('{$id}',content)";
                    }
                } else {
                    $sql .= " OR FIND_IN_SET('{$goods_ids}',content)";
                }
                $query->where('type', 1)->where($sql);
            })
            ->whereOr(function ($query) use ($category_ids) {
                $sql = '1=2';
                if (is_array($category_ids)) {
                    foreach ($category_ids as $id) {
                        $sql .= " OR FIND_IN_SET('{$id}',content)";
                    }
                } else {
                    $sql .= " OR FIND_IN_SET('{$category_ids}',content)";
                }
                $query->where('type', 4)->where($sql);
            })
            ->whereOr(function ($query) use ($brand_ids) {
                $sql = '1=2';
                if (is_array($brand_ids)) {
                    foreach ($brand_ids as $id) {
                        $sql .= " OR FIND_IN_SET('{$id}',content)";
                    }
                } else {
                    $sql .= " OR FIND_IN_SET('{$brand_ids}',content)";
                }
                $query->where('type', 5)->where($sql);
            })
            ->select();
    }
}
