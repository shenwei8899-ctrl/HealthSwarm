<?php

namespace addons\shop\controller;

use addons\shop\model\Address;
use addons\shop\model\Carts;
use addons\shop\model\Order;
use addons\shop\model\UserCoupon;
use think\Config;

/**
 * 结算控制器
 * Class Checkout
 * @package addons\shop\controller
 */
class Checkout extends Base
{
    protected $noNeedLogin = [];
    protected $noNeedRight = '*';

    public function _initialize()
    {
        parent::_initialize();
    }

    /**
     * 结算页
     */
    public function index()
    {
        $cartIds = $this->request->post('ids/a');
        $addressId = $this->request->post('address_id/d'); //地址id
        $user_coupon_id = $this->request->post('user_coupon_id/d'); //优惠券
        if (empty($cartIds)) {
            $this->error('请选择需要结算的商品');
        }
        $addressInfo = Address::get($addressId);
        if (!$addressInfo) {
            $addressInfo = Address::where('isdefault', 1)->where('user_id', $this->auth->id)->where('status', 'normal')->find();
        }
        $orderItem = [];
        $orderInfo = [
            'order_sn'    => '',
            'goodsprice'  => 0, //商品总金额
            'amount'      => 0, //总金额
            'shippingfee' => 0, //运费
            'discount'    => 0, //优惠金额
        ];
        $goodsList = [];
        $areaId = !empty($addressInfo) ? $addressInfo->area_id : 0;
        try {
            list($orderItem, $goodsList) = Order::computeCarts($orderInfo, $cartIds, $this->auth->id, $areaId, $user_coupon_id);
            if (empty($goodsList)) {
                throw new \Exception("未找到商品");
            }
        } catch (\Exception $e) {
            $this->error($e->getMessage());
        }
        foreach ($goodsList as $item) {
            $item->category_id = $item->goods->category_id;
            $item->brand_id = $item->goods->brand_id;
        }
        $goods_ids = array_column($goodsList, 'goods_id');
        $category_ids = array_column($goodsList, 'category_id');
        $brand_ids = array_column($goodsList, 'brand_id');
        $addressList = Address::getAddressList($this->auth->id);
        $couponList = UserCoupon::myGoodsCoupon($this->auth->id, $goods_ids, $category_ids, $brand_ids);
        $this->view->assign([
            'cartIds'     => $cartIds,
            'addressList' => $addressList,
            'goodsList'   => $goodsList,
            'orderItem'   => $orderItem,
            'addressInfo' => $addressInfo,
            'orderInfo'   => $orderInfo,
            'couponList'  => $couponList
        ]);

        Config::set('shop.title', "订单结算");
        return $this->view->fetch('/checkout');
    }

    /**
     * 提交订单
     */
    public function submit()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $cartIds = $this->request->post('ids');
        $addressId = $this->request->post('address_id/d'); //地址id
        $user_coupon_id = $this->request->post('user_coupon_id/d'); //优惠券
        $memo = $this->request->post('memo');
        if (empty($cartIds)) {
            $this->error('商品信息已变更，请返回刷新重试');
        }
        if (empty($addressId)) {
            $this->error('请选择收货地址');
        }
        //为购物车id
        //校验购物车id 合法
        $row = (new Carts)->where('id', 'IN', $cartIds)->where('user_id', '<>', $this->auth->id)->find();
        if ($row) {
            $this->error('存在不合法购物车数据');
        }
        $order = null;
        try {
            $order = Order::createOrder($addressId, $this->auth->id, $cartIds, $user_coupon_id, $memo);
        } catch (\Exception $e) {
            $this->error($e->getMessage());
        }
        $this->redirect(addon_url('shop/payment/index') . '?orderid=' . $order['order_sn']);
    }

    /**
     * 重新统计
     */
    public function recount()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $cartIds = $this->request->post('ids');
        $cartIds = explode(',', $cartIds);
        $addressId = $this->request->post('address_id/d'); //地址id
        if (empty($cartIds)) {
            $this->error('请选择需要结算的商品');
        }
        $user_coupon_id = $this->request->post('user_coupon_id/d'); //优惠券
        $addressInfo = Address::get($addressId);
        if (!$addressInfo) {
            $addressInfo = Address::where('isdefault', 1)->where('user_id', $this->auth->id)->where('status', 'normal')->find();
        }
        $orderInfo = [
            'order_sn'    => '',
            'goodsprice'  => 0, //商品总金额
            'amount'      => 0, //总金额
            'shippingfee' => 0, //运费
            'discount'    => 0, //优惠金额
        ];

        $areaId = !empty($addressInfo) ? $addressInfo->area_id : 0;
        try {
            list($orderItem, $goodsList) = Order::computeCarts($orderInfo, $cartIds, $this->auth->id, $areaId, $user_coupon_id);
            if (empty($goodsList)) {
                throw new \Exception("未找到商品");
            }
        } catch (\Exception $e) {
            $this->error($e->getMessage());
        }

        $this->success('', '', ['orderInfo' => $orderInfo]);
    }

}
