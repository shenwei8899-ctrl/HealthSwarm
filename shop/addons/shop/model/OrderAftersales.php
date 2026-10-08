<?php

namespace addons\shop\model;

use think\Model;

/**
 * 模型
 */
class OrderAftersales extends Model
{

    // 表名
    protected $name = 'shop_order_aftersales';
    // 开启自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';
    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    // 追加属性
    protected $append = [
        'status_text',
        'type_text'
    ];

    public function getStatusList()
    {
        return ['1' => '等待审核', '2' => '审核通过', '3' => '审核拒绝'];
    }

    public function getStatusTextAttr($value, $data)
    {
        $value = $value ?: ($data['status'] ?? '');
        $list = $this->getStatusList();
        return $list[$value] ?? '';
    }

    public function getTypeList()
    {
        return ['1' => '仅退款', '2' => '退货退款'];
    }

    public function getTypeTextAttr($value, $data)
    {
        $value = $value ?: ($data['type'] ?? '');
        $list = $this->getTypeList();
        return $list[$value] ?? '';
    }

    public function getImagesAttr($value, $data)
    {
        $value = $value ?: ($data['images'] ?? '');
        if (empty($value)) {
            return [];
        }
        $value = explode(',', $value);
        foreach ($value as &$img) {
            $img = cdnurl($img, true);
        }
        return $value;
    }

    public function OrderGoods()
    {
        return $this->hasOne('OrderGoods', 'id', 'order_goods_id', [], 'LEFT');
    }
}
