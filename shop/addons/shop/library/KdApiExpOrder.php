<?php

namespace addons\shop\library;

use addons\shop\model\Order;
use addons\shop\model\ElectronicsOrder;
use addons\shop\model\OrderElectronics;
use fast\Http;

/**
 * 电子面单
 * @ DateTime 2021-06-11
 * @ 
 */
class KdApiExpOrder
{

    protected static $reqUrl = '';

    /**
     * @ DateTime 2021-06-11
     * @ 
     * @electronics [type] $electronics
     * @electronics [type] $sender
     * @return void
     */
    public static function create($order_id, $electronics_id)
    {
        $order = Order::with(['OrderGoods'])
            ->field('o.*,p.name province_name,c.name city_name,a.name area_name')
            ->alias('o')
            ->join('shop_address d', 'o.address_id=d.id', 'LEFT')
            ->join('shop_area p', 'd.province_id=p.id', 'LEFT')
            ->join('shop_area c', 'd.city_id=c.id', 'LEFT')
            ->join('shop_area a', 'd.area_id=a.id', 'LEFT')
            ->where('o.id', $order_id)
            ->find();

        if ($order->orderstate == 1) {
            throw new \Exception('订单已取消,不支持生成电子面单');
        }

        if ($order->orderstate == 2) {
            throw new \Exception('订单已失效,不支持生成电子面单');
        }

        if ($order->orderstate == 3) {
            throw new \Exception('订单已完成,不支持生成电子面单');
        }

        if (!$order->paystate) {
            throw new \Exception('订单未支付,不支持生成电子面单');
        }

        if ($order->shippingstate) {
            throw new \Exception('订单已发货,不支持生成电子面单');
        }

        $electronics = ElectronicsOrder::with(['Shipper'])->where('id', $electronics_id)->find();

        if (empty($order)) {
            throw new \Exception('未找到订单');
        }

        if (empty($electronics)) {
            throw new \Exception("电子面单模板不存在");
        }

        if (empty($electronics->shipper)) {
            throw new \Exception("快递公司不存在");
        }

        if (empty($order->order_goods)) {
            throw new \Exception("订单商品不存在");
        }

        $Commodity = [];
        $quantity = 0;
        $Weight = 0;

        foreach ($order->order_goods as $item) {
            $Commodity[] =  [
                'GoodsName' => $item['title'],
                'GoodsCode' => $item['goods_id'] . '_' . $item['goods_sku_id'],
                'Goodsquantity' => $item['nums'],
                'GoodsPrice' => $item['price'],
                'GoodsWeight' => $item['weight'],
                // 'GoodsVol' => 0,
                'GoodsDesc' => $item['attrdata']
            ];
            $quantity = bcadd($quantity, $item['nums']);
            $Weight = bcadd($Weight, $item['weight']);
        }

        // 组装应用级参数
        $requestData = [
            'MemberID'  => $order->user_id,
            'OrderCode' => $order->order_sn,
            'ShipperCode' => $electronics->shipper->shipper_code,
            'LogisticCode'  => $electronics->logistic_code,
            'CustomerName' => $electronics->customer_name,
            'CustomerPwd' => $electronics->customer_pwd,
            // 'ThrOrderCode' => '1234567890',
            'SendSite'  => $electronics->send_site,
            'PayType'  => $electronics->paytype,
            'MonthCode'  => $electronics->month_code,
            'IsReturnSignBill'  => $electronics->is_return_sign_bill,
            'OperateRequire'  => $electronics->operate_require,
            'ExpType'  => $electronics->exp_type,
            'Cost'  => $order->shippingfee,
            'OtherCost'  => 0,
            'Sender'  => [
                'Company' => $electronics->company,
                'Name' => $electronics->name,
                'Tel' => $electronics->tel,
                'Mobile' => $electronics->mobile,
                'PostCode' => $electronics->post_code,
                'ProvinceName' => $electronics->province_name,
                'CityName' => $electronics->city_name,
                'ExpAreaName' => $electronics->exp_area_name,
                'Address' => $electronics->address
            ],
            'Receiver' => [
                'Company' => '',
                'Name' => $order->receiver,
                'Tel' => '',
                'Mobile' => $order->mobile,
                'PostCode' => $order->zipcode,
                'ProvinceName' => $order->province_name,
                'CityName' => $order->city_name,
                'ExpAreaName' => $order->area_name,
                'Address' => $order->address
            ],
            'Commodity' => $Commodity,
            'IsNotice' => $electronics->is_notice,
            'StartDate' => '',
            'EndDate' => '',
            'AddService' => [],
            'Weight' => $Weight,
            'Quantity' => $quantity,
            // 'Volume' => 0,
            'IsReturnPrintTemplate' => $electronics->is_return_temp,
            'Remark' => $electronics->remark
        ];
        self::setReqUrl();
        $res = self::sendPost($requestData, 1007);

        //生成电子面单后，替换快递单号
        if (isset($res['Success']) && $res['Success']) {
            $order->expressno = $res['Order']['LogisticCode'];
            $order->expressname = $electronics['shipper']['name'];
            $order->save();
        }
        //入库
        OrderElectronics::push($res, $order->order_sn, $electronics->customer_name, $electronics->customer_pwd);
        return $res;
    }

    /**
     * @ DateTime 2021-06-11
     * @ 电子面单取消
     * @return void
     */
    public static function cancel($param)
    {
        // 组装应用级参数
        $requestData = [
            'ShipperCode' => $param['shipper_code'],
            'OrderCode' => $param['order_sn'],
            'ExpNo' => $param['logistic_code'],
            'CustomerName' => $param['customer_name'],
            'CustomerPwd' => $param['customer_pwd']
        ];
        self::setReqUrl();
        return self::sendPost($requestData, 1147);
    }

    /**
     * @ DateTime 2021-06-11
     * @ 单号余量查询
     * @return void
     */
    public static function getOrderTraces($param)
    {
        $requestData = [
            'ShipperCode' => $param['shipper_code'],
            'StationCode' => '',
            'StationName' => '',
            'CustomerName' => $param['customer_name'],
            'CustomerPwd' => $param['customer_pwd']
        ];
        self::setReqUrl();
        return self::sendPost($requestData, 1127);
    }

    /**
     * @ 物流查询
     * @param [type] $param
     * @return void
     */
    public static function getLogisticsQuery($param)
    {
        $requestData = [
            'OrderCode' => $param['order_sn'],
            'ShipperCode' => $param['shipper_code'],
            'LogisticCode' => $param['logistic_code'],
        ];
        self::setReqUrl(1);
        return self::sendPost($requestData, 1002);
    }

    //设置url
    protected static function setReqUrl($type = 0)
    {
        $config = get_addon_config('shop');
        if ($config['api_mode'] == 'sandbox') {
            self::$reqUrl = 'http://sandboxapi.kdniao.com:8080/kdniaosandbox/gateway/exterfaceInvoke.json';
        } else {
            switch ($type) {
                case 1: //即时物流
                    self::$reqUrl = 'https://api.kdniao.com/Ebusiness/EbusinessOrderHandle.aspx';
                    break;
                default: //电子面单
                    self::$reqUrl = 'https://api.kdniao.com/api/EOrderService';
            }
        }
    }


    /**
     * @ DateTime 2021-06-11
     * @ 请求
     * @return void
     */
    protected static function sendPost($requestData, $requestType)
    {
        $requestData = json_encode($requestData, JSON_UNESCAPED_UNICODE);
        $config = get_addon_config('shop');
        // 组装系统级参数
        $data = array(
            'EBusinessID' => $config['EBusinessID'],
            'RequestType' => $requestType,
            'RequestData' => urlencode($requestData),
            'DataType' => '2',
        );
        $data['DataSign'] = self::encrypt($requestData, $config['kdNiaoApiKey']);
        //以form表单形式提交post请求，post请求体中包含了应用级参数和系统级参数
        $result = Http::post(self::$reqUrl, $data);
        return (array)json_decode($result, true);
    }

    /**
     * Sign签名生成
     * @electronics data 内容   
     * @electronics ApiKey ApiKey
     * @return DataSign签名
     */
    protected static function encrypt($data, $apiKey)
    {
        return urlencode(base64_encode(md5($data . $apiKey)));
    }
}
