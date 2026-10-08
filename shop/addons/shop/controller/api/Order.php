<?php

namespace addons\shop\controller\api;

use addons\shop\model\UserCoupon;
use addons\shop\model\Carts;
use addons\shop\model\Order as OrderModel;
use addons\shop\model\Address;
use addons\third\model\Third;
use addons\shop\model\OrderAction;
use addons\shop\model\OrderGoods;
use addons\shop\library\KdApiExpOrder;
use think\Db;

/**
 * 订单接口
 */
class Order extends Base
{
    protected $noNeedLogin = [];


    //计算邮费，判断商品
    public function carts()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $config = get_addon_config('shop');
        $cart_ids = $this->request->post('ids');
        $address_id = $this->request->post('address_id/d'); //地址id
        if (empty($cart_ids)) {
            $this->error('参数缺失');
        }
        $user_coupon_id = $this->request->post('user_coupon_id/d'); //优惠券
        $address = Address::get($address_id);
        $orderInfo = [
            'order_sn'    => '',
            'amount'      => 0, //订单金额（包含运费）
            'shippingfee' => 0, //运费
            'goodsprice'  => 0 //商品金额
        ];
        $goodsList = [];
        $area_id = !empty($address) ? $address->area_id : 0;
        try {
            list($orderItem, $goodsList) = OrderModel::computeCarts($orderInfo, $cart_ids, $this->auth->id, $area_id, $user_coupon_id);
            if (empty($goodsList)) {
                throw new \Exception("未找到商品");
            }
        } catch (\Exception $e) {
            $this->error($e->getMessage());
        }
        foreach ($goodsList as $item) {
            $item->category_id = $item->goods->category_id;
            $item->brand_id = $item->goods->brand_id;
            $item->goods->visible(explode(',', 'id,title,image,price,marketprice'));
        }
        //获取我的可以使用的优惠券
        $goods_ids = array_column($goodsList, 'goods_id');
        $category_ids = array_column($goodsList, 'category_id');
        $brand_ids = array_column($goodsList, 'brand_id');
        $this->success('获取成功', [
            'coupons'          => UserCoupon::myGoodsCoupon($this->auth->id, $goods_ids, $category_ids, $brand_ids),
            'goods_list'       => $goodsList,
            'order_info'       => $orderInfo,
            'couponTotalPrice' => floatval(!isset($config['shippingfeecoupon']) || $config['shippingfeecoupon'] == 0 ? $orderInfo['goodsprice'] : $orderInfo['amount'])
        ]);
    }

    //提交订单
    public function add()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $cart_ids = $this->request->post('ids');
        $address_id = $this->request->post('address_id/d'); //地址id
        $user_coupon_id = $this->request->post('user_coupon_id/d'); //地址id
        $memo = $this->request->post('memo');
        if (empty($address_id)) {
            $this->error('请选择地址');
        }
        if (empty($cart_ids)) {
            $this->error('请选择商品');
        }
        //为购物车id
        //校验购物车id 合法
        $row = (new Carts)->where('id', 'IN', $cart_ids)->where('user_id', '<>', $this->auth->id)->find();
        if ($row) {
            $this->error('存在不合法购物车数据');
        }
        $order = null;
        try {
            $order = OrderModel::createOrder($address_id, $this->auth->id, $cart_ids, $user_coupon_id, $memo);
        } catch (\Exception $e) {
            $this->error($e->getMessage());
        }
        $this->success('下单成功！', array_intersect_key($order->toArray(), array_flip(['order_sn', 'paystate'])));
    }

    //订单详情
    public function detail()
    {
        $order_sn = $this->request->param('order_sn');
        if (empty($order_sn)) {
            $this->error('参数缺失');
        }
        $order = OrderModel::getDetail($order_sn, $this->auth->id);
        if (empty($order)) {
            $this->error('未找到订单');
        }
        if (OrderModel::isExpired($order_sn)) {
            $this->error("订单已经失效");
        }
        $order->append(['status_text']);
        $order->hidden(explode(',', 'province_id,city_id,area_id,address_id,method,transactionid,updatetime,deletetime'));
        $order->expiretime = $order->expiretime - time();
        $this->success('', $order);
    }

    //订单列表
    public function index()
    {
        $param = $this->request->param();
        $param['user_id'] = $this->auth->id;
        $list = OrderModel::tableList($param);
        foreach ($list as $item) {
            $item->append(['status_text']);
            $field = 'id,order_sn,amount,expressno,expressname,saleamount,shippingfee,paystate,orderstate,shippingstate,order_goods,status,status_text';
            $item->visible(explode(',', $field));
        }
        $this->success('获取成功', $list);
    }

    //取消订单
    public function cancel()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $order_sn = $this->request->post('order_sn');
        if (!$order_sn) {
            $this->error('参数错误');
        }
        $order = OrderModel::getByOrderSn($order_sn);
        if (empty($order)) {
            $this->error('订单不存在');
        }
        if ($order->user_id != $this->auth->id) {
            $this->error('不能越权操作');
        }
        if ((isset($order->order_type) && $order->order_type === 'plan') || Db::name('shop_order_ext')->where('order_id', $order->id)->where('source_type', 'service_plan')->find()) {
            $this->error('专属计划订单请使用V1计划接口；支付后不支持个人原因取消或退款');
        }
        if ($order->status == 'hidden') {
            $this->error('订单已失效！');
        }
        //可以取消
        if (!$order->paystate && !$order->orderstate) {
            // 启动事务
            Db::startTrans();
            try {
                $order->orderstate = 1;
                $order->canceltime = time();
                $order->save();
                foreach ($order->order_goods as $item) {
                    $sku = $item->sku;
                    $goods = $item->goods;
                    //商品库存恢复
                    if ($sku) {
                        $sku->setInc('stocks', $item->nums);
                    }
                    if ($goods) {
                        $goods->setInc('stocks', $item->nums);
                    }
                }
                //恢复优惠券
                UserCoupon::resetUserCoupon($order->user_coupon_id, $order->order_sn);
                // 提交事务
                Db::commit();
            } catch (\Exception $e) {
                // 回滚事务
                Db::rollback();
                $this->error('订单取消失败');
            }
            //记录操作
            OrderAction::push($order->order_sn, '系统', '订单取消成功');
            $this->success('订单取消成功！', $order['status']);
        } else {
            $this->error('订单不允许取消');
        }
    }

    //订单支付
    public function pay()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $order_sn = $this->request->post('order_sn');
        $paytype = $this->request->post('paytype');
        $method = $this->request->post('method');
        $appid = $this->request->post('appid'); //为APP的应用id
        $returnurl = $this->request->post('returnurl', '', 'trim');
        $openid = $this->request->post('openid', '', null);
        $logincode = $this->request->post('logincode', '', null);

        $orderInfo = OrderModel::getByOrderSn($order_sn);
        if (!$orderInfo) {
            $this->error("未找到指定的订单");
        }
        if ($orderInfo['paystate']) {
            $this->error("订单已经支付，请勿重复支付");
        }
        if (OrderModel::isExpired($order_sn)) {
            $this->error("订单已经失效");
        }

        //如果有传递logincode，则直接使用code换openid
        if (!$openid && $logincode) {
            $json = (new \addons\shop\library\Wechat\Service())->getWechatSession($logincode);
            $openid = $json['openid'] ?? $openid;
        }

        //必须传递openid
        if (in_array($method, ['miniapp', 'mp', 'mini']) && !$openid) {
            $this->error("未找到第三方用户信息", 'bind');
        }

        $response = null;
        try {
            $response = OrderModel::pay($order_sn, $this->auth->id, $paytype, $method, $openid, '', $returnurl);
        } catch (\Exception $e) {
            $this->error($e->getMessage());
        }
        $this->success("请求成功", $response);
    }

    //确认收货
    public function takedelivery()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $order_sn = $this->request->post('order_sn');
        if (!$order_sn) {
            $this->error('参数错误');
        }
        $order = OrderModel::getByOrderSn($order_sn);
        if (empty($order)) {
            $this->error('订单不存在');
        }
        if ($order->user_id != $this->auth->id) {
            $this->error('不能越权操作');
        }
        if ((isset($order->order_type) && $order->order_type === 'plan') || Db::name('shop_order_ext')->where('order_id', $order->id)->where('source_type', 'service_plan')->find()) {
            $this->error('专属计划需按配送批次签收，请使用V1批次签收接口');
        }
        if ($order->status == 'hidden') {
            $this->error('订单已失效！');
        }
        if ($order->paystate == 1 && !$order->orderstate && $order->shippingstate == 1) {
            $order->shippingstate = 2;
            $order->receivetime = time();
            $order->save();
            //记录操作
            OrderAction::push($order->order_sn, '系统', '订单确认收货成功');
            $this->success('确认收货成功');
        }
        $this->error('未可确认收货');
    }

    //查询物流
    public function logistics()
    {
        $order_sn = $this->request->param('order_sn');
        if (empty($order_sn)) {
            $this->error('参数缺失');
        }
        $order = OrderModel::getDetail($order_sn, $this->auth->id);
        if (empty($order)) {
            $this->error('未找到订单');
        }
        if (!$order->shippingstate) {
            $this->error('订单未发货');
        }
        $electronics = Db::name('shop_order_electronics')->where('order_sn', $order_sn)->where('status', 0)->find();
        if (!$electronics) {
            $this->error('订单未发货');
        }
        $result = KdApiExpOrder::getLogisticsQuery([
            'order_sn'      => $order_sn,
            'logistic_code' => $electronics['logistic_code'],
            'shipper_code'  => $electronics['shipper_code']
        ]);
        if ($result['Success']) {
            $this->success('查询成功', $result['Traces']);
        }
        $this->error('查询失败');
    }
}
