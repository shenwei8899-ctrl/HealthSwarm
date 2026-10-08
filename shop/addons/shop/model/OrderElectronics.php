<?php

namespace addons\shop\model;

use think\Model;


class OrderElectronics extends Model
{

    // 表名
    protected $name = 'shop_order_electronics';

    // 自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';

    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    protected $deleteTime = false;

    // 追加属性
    protected $append = [];

    /**
     * Persist an electronic waybill response for the order fulfillment log.
     * This belongs to the runtime model, not the retired admin model layer.
     */
    public static function push($res, $orderSn, $customerName, $customerPwd)
    {
        if (empty($res['Success'])) {
            return;
        }

        (new self)->save([
            'order_sn'       => $orderSn,
            'customer_name'  => $customerName,
            'customer_pwd'   => $customerPwd,
            'print_template' => isset($res['PrintTemplate']) ? $res['PrintTemplate'] : '',
            'kdn_order_code' => isset($res['Order']['KDNOrderCode']) ? $res['Order']['KDNOrderCode'] : '',
            'logistic_code'  => isset($res['Order']['LogisticCode']) ? $res['Order']['LogisticCode'] : '',
            'shipper_code'   => isset($res['Order']['ShipperCode']) ? $res['Order']['ShipperCode'] : '',
            'order'          => json_encode(isset($res['Order']) ? $res['Order'] : [], JSON_UNESCAPED_UNICODE),
        ]);
    }

}
