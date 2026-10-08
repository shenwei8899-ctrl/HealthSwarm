<?php

namespace addons\shop\model;

use think\Model;
use addons\shop\model\FreightItems;

/**
 * 模型
 */
class Freight extends Model
{

    // 表名
    protected $name = 'shop_freight';
    // 开启自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';
    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    // 追加属性
    protected $append = [];

    public function getFirstNumAttr($value, $data)
    {
        return $data['first_num'] ?? $data['num'];
    }

    public function getFirstPriceAttr($value, $data)
    {
        return $data['first_price'] ?? $data['price'];
    }

    /**
     * @ DateTime 2021-05-28
     * @ 计算邮费
     * @param $freight_id
     * @param $area_id
     * @param $nums
     * @param $weight
     * @param $amount
     * @return int
     */
    public static function calculate($freight_id, $area_id, $nums, $weight, $amount)
    {
        //模板id
        $freight = self::where('id', $freight_id)->where('switch', 1)->find();
        $shippingfee = 0;
        if (empty($freight)) {
            return $shippingfee;
        }
        //当前模板 计费类型 ，1=计件 ，2=计重
        $FreightItems = new FreightItems();
        switch ($freight['type']) {
            case 1:
                $shippingfee = $FreightItems->numPostage($freight, $area_id, $nums, $amount);
                break;
            case 2:
                $shippingfee = $FreightItems->weightPostage($freight, $area_id, $nums, $weight, $amount);
                break;
        }
        return $shippingfee;
    }
}
