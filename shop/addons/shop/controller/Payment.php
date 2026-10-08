<?php

namespace addons\shop\controller;


use addons\shop\model\UserCoupon;
use addons\shop\model\OrderGoods;
use think\Config;
use think\Db;
use think\Exception;

/**
 * 支付
 * Class Payment
 * @package addons\shop\controller
 */
class Payment extends Base
{
    protected $noNeedLogin = [];
    protected $noNeedRight = '*';

    public function _initialize()
    {
        parent::_initialize();
    }

    /**
     * 支付页
     */
    public function index()
    {
        $orderid = $this->request->get('orderid');
        $orderInfo = \addons\shop\model\Order::getByOrderSn($orderid);
        if (!$orderInfo) {
            $this->error("未找到指定的订单");
        }
        if ($orderInfo['paystate']) {
            $this->error("订单已经支付", url('index/shop.order/index'));
        }
        if ($orderInfo['orderstate'] > 0) {
            $this->error("订单无法进行支付", url('index/shop.order/index'));
        }

        //订单过期
        if (!$orderInfo['orderstate'] && time() > $orderInfo['expiretime']) {
            // 启动事务
            Db::startTrans();
            try {
                $orderInfo->save(['orderstate' => 2]);
                //库存恢复
                OrderGoods::setGoodsStocksInc($orderInfo->order_sn);
                //恢复优惠券
                UserCoupon::resetUserCoupon($orderInfo->user_coupon_id, $orderInfo->order_sn);
                // 提交事务
                Db::commit();
            } catch (\Exception $e) {
                // 回滚事务
                Db::rollback();
            }
            $this->error("订单已失效", url("index/shop.order/index"));
        }
        $config = get_addon_config('shop');
        $paytypeList = [];
        $isWechat = stripos($this->request->server('HTTP_USER_AGENT'), 'MicroMessenger') !== false;

        foreach (explode(',', $config['paytypelist']) as $index => $item) {
            $paytypeList[] = ['value' => $item, 'image' => '/assets/addons/shop/img/paytype/' . $item . '.png', 'default' => $item === $config['defaultpaytype']];
        }
        $this->view->assign('paytypeList', $paytypeList);

        if ($this->request->isPost()) {
            $paytype = $this->request->post("paytype");
            $response = null;
            try {
                $response = \addons\shop\model\Order::pay($orderid, $orderInfo['user_id'], $paytype);
            } catch (Exception $e) {
                $this->error($e->getMessage());
            }
            return $response;
        } else {
            $this->view->assign('orderInfo', $orderInfo);

            Config::set('shop.title', "立即支付");
            return $this->view->fetch('/payment');
        }
    }

}
