<?php

namespace addons\shop\model;

use think\Model;

/**
 * 模型
 */
class SkuSpec extends Model
{

    // 表名
    protected $name = 'shop_goods_sku_spec';
    // 开启自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';
    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    // 追加属性
    protected $append = [];

    /**
     * 获取指定商品的SKU信息
     * @param int $goods_id 商品ID
     * @return array
     */
    public static function getGoodsSkuSpec($goods_id)
    {
        $list = (new self)->field('MIN("id") AS "id", MIN("goods_id") AS "goods_id", "spec_id"')->where('goods_id', $goods_id)
            ->with([
                'Spec',
                'SkuValue' => function ($query) use ($goods_id) {
                    $query->where('goods_id', $goods_id)->field('id,goods_id,spec_id,spec_value_id')->with(['SpecValue']);
                }
            ])->group('spec_id')->select();

        $list = collection($list)->toArray();
        return $list;
    }

    public function SkuValue()
    {
        return $this->hasMany('SkuSpec', 'spec_id', 'spec_id');
    }

    public function Spec()
    {
        return $this->hasOne('Spec', 'id', 'spec_id', [], 'LEFT')->bind(['title' => 'name']);
    }

    public function SpecValue()
    {
        return $this->hasOne('SpecValue', 'id', 'spec_value_id', [], 'LEFT')->bind(['title' => 'value']);
    }
}
