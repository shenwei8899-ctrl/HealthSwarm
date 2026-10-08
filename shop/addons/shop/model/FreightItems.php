<?php

namespace addons\shop\model;

use think\Model;

/**
 * 运费条件模型
 */
class FreightItems extends Model
{

    // 表名
    protected $name = 'shop_freight_items';
    // 开启自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';
    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    // 追加属性
    protected $append = [];

    /**
     * @ DateTime 2021-05-31
     * @ 计件费用
     * @param Freight $freight
     * @param int     $area_id
     * @param int     $nums
     * @param float   $amount
     * @return float
     */
    public function numPostage($freight, $area_id, $nums, $amount)
    {
        //计件
        $shippingfee = 0; //邮费
        $is_free = false; //包邮的
        $result = []; //计费的
        $freightItems = $this->where('freight_id', $freight->id)->select();
        if (empty($freightItems)) {
            // 默认计件费用
            //首件
            $money = $freight['price'];
            //续费
            if ($freight['num'] < $nums && $freight['continue_num'] > 0 && $freight['continue_price'] > 0) {
                $money = bcadd($money, bcmul(bcdiv($freight['continue_price'], $freight['continue_num'], 2), bcsub($nums, $freight['num'], 2), 2), 2);
            }
            return $money;
        }
        // 是否指定地区包邮 -> 是否有在包邮地区里 ->
        foreach ($freightItems as $item) {
            $postage_area_ids = explode(',', $item['postage_area_ids']); //包邮限制地区
            $area_ids = explode(',', $item['area_ids']); //邮费限制地区
            //首先判断是否满足包邮
            if (in_array($item['type'], [1, 2])) {
                $is_free = $this->getWeightNumsFree($item, $area_id, $postage_area_ids, $nums, $amount);
                if ($is_free) {
                    break;
                }
            }
            //走到这里，则包邮未满足，追加邮费结果
            if (in_array($area_id, $area_ids)) {
                $result[] = $item;
            }
        }
        //包邮
        if ($is_free) {
            return $shippingfee;
        }

        if (!$result) {
            //如果未找到指定地区的运费模板，则使用主运费模板
            $result = $freight;
        }

        //计算邮费
        $monies = [];
        foreach ($result as $res) {
            //首件
            $money = $res['first_price'];
            //续费
            if ($res['first_num'] < $nums && $res['continue_num'] > 0 && $res['continue_price'] > 0) {
                $money = bcadd($money, bcmul(bcdiv($res['continue_price'], $res['continue_num'], 2), bcsub($nums, $res['first_num'], 2), 2), 2);
            }
            $monies[] = $money;
        }
        $config = get_addon_config('shop');
        $shippingfee = isset($config['freightitemfee']) || $config['freightitemfee'] == 'max' ? max($monies) : min($monies);
        return $shippingfee;
    }

    /**
     * @ DateTime 2021-05-31
     * @ 计重费用
     * @param Freight $freight
     * @param int     $area_id
     * @param int     $nums
     * @param float   $weight
     * @param float   $amount
     * @return float
     */
    public function weightPostage($freight, $area_id, $nums, $weight, $amount)
    {
        //计重
        $shippingfee = 0; //邮费
        $is_free = false; //包邮的
        $result = []; //计费的
        $totalWeight = bcmul($nums, $weight, 2); //总重量
        $freightItems = $this->where('freight_id', $freight->id)->select();
        if (empty($freightItems)) {
            // 默认计件费用
            //首重
            $money = $freight['price'];
            //续费
            if ($freight['num'] < $totalWeight && $freight['continue_num'] > 0 && $freight['continue_price'] > 0) {
                $money = bcadd($money, bcmul(bcdiv($freight['continue_price'], $freight['continue_num'], 2), bcsub($totalWeight, $freight['num'], 2), 2), 2);
            }
            return $money;
        }
        // 是否指定地区包邮 -> 是否有在包邮地区里 ->
        foreach ($freightItems as $item) {
            $postage_area_ids = explode(',', $item['postage_area_ids']); //包邮限制地区
            $area_ids = explode(',', $item['area_ids']); //邮费限制地区
            if (in_array($item['type'], [1, 2])) {
                $is_free = $this->getWeightNumsFree($item, $area_id, $postage_area_ids, $nums, $amount);
                if ($is_free) {
                    break;
                }
            }
            //走到这里，则包邮未满足，追加邮费结果
            if (in_array($area_id, $area_ids)) {
                $result[] = $item;
            }
        }
        //包邮
        if ($is_free) {
            return $shippingfee;
        }

        if (!$result) {
            //如果未找到指定地区的运费模板，则使用主运费模板
            $result = [$freight];
        }

        //计算邮费
        $monies = [];
        foreach ($result as $res) {
            //首重
            $money = $res['first_price'];
            //续费
            if ($res['first_num'] < $totalWeight && $res['continue_num'] > 0 && $res['continue_price'] > 0) {
                $money = bcadd($money, bcmul(bcdiv($res['continue_price'], $res['continue_num'], 2), bcsub($totalWeight, $res['first_num'], 2), 2), 2);
            }
            $monies[] = $money;
        }
        $config = get_addon_config('shop');
        $shippingfee = isset($config['freightitemfee']) || $config['freightitemfee'] == 'max' ? max($monies) : min($monies);
        return $shippingfee;
    }

    /**
     * @ DateTime 2021-05-31
     * @ 包邮判断
     * @param $item
     * @param $area_id
     * @param $postage_area_ids
     * @param $nums
     * @param $amount
     * @return boolean
     */
    protected function getWeightNumsFree($item, $area_id, $postage_area_ids, $nums, $amount)
    {
        //判断条件
        if (empty($postage_area_ids)) {
            //开启包邮，没有限制地区，则全部包邮
            return true;
        }
        if ($item['type'] == 1 && in_array($area_id, $postage_area_ids) && $item['postage_num'] <= $nums) { //计件的开启包邮
            //在包邮地区里
            //满足包邮条件
            return true;
        } elseif ($item['type'] == 2 && in_array($area_id, $postage_area_ids) && $item['postage_price'] <= $amount) { //金额开启包邮
            //在包邮地区里
            //满足包邮条件
            return true;
        }
        return false;
    }
}
