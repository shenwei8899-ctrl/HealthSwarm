<?php

namespace addons\shop\controller;


use think\Config;

/**
 * 订单
 * Class Order
 * @package addons\shop\controller
 */
class Order extends Base
{
    protected $noNeedLogin = ['epay'];
    protected $noNeedRight = '*';

    public function _initialize()
    {
        parent::_initialize();
    }

    /**
     * 订单结算
     */
    public function checkout()
    {
        Config::set('shop.title', "订单结算");
        return $this->view->fetch('/checkout');
    }

    /**
     * @ DateTime 2021-06-01
     * @ 支付回调
     * @return void
     */
    public function epay()
    {
        $type = $this->request->param('type');
        $paytype = $this->request->param('paytype');
        if ($type == 'notify') {
            $pay = \addons\epay\library\Service::checkNotify($paytype);
            if (!$pay) {
                echo '签名错误';
                return;
            }
            $data = $pay->verify();
            try {
                $payamount = $paytype == 'alipay' ? $data['total_amount'] : $data['total_fee'] / 100;
                \addons\shop\model\Order::settle($data['out_trade_no'], $payamount, $paytype == 'alipay' ? $data['trade_no'] : $data['transaction_id']);
            } catch (\Exception $e) {
                \think\Log::write($e->getMessage(), 'epay');
            }
            echo $pay->success();
        } elseif ($type == 'return') {
            $order_sn = $this->request->param('order_sn');
            $this->redirect("index/shop.order/detail", ['orderid' => $order_sn]);
        }
        return;
    }
}
