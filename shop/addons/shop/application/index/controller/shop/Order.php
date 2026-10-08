<?php

namespace app\index\controller\shop;

use addons\shop\library\KdApiExpOrder;
use addons\shop\model\Order as OrderModel;
use addons\shop\model\OrderAction;
use addons\shop\model\OrderAftersales;
use addons\shop\model\OrderGoods;
use app\common\controller\Frontend;
use addons\shop\model\UserCoupon;
use think\Db;

class Order extends Frontend
{

    protected $layout = 'default';
    protected $noNeedLogin = [];
    protected $noNeedRight = ['*'];

    /**
     * 我的订单
     */
    public function index()
    {
        $param = $this->request->param();
        $param['user_id'] = $this->auth->id;
        $param['f'] = isset($param['f']) ? $param['f'] : 0;
        $orderList = OrderModel::tableList($param);

        $this->view->assign('param', $param);
        $this->view->assign('orderList', $orderList);
        $this->view->assign('title', '我的订单');
        return $this->view->fetch();
    }

    /**
     * 订单详情
     */
    public function detail()
    {
        $order_sn = $this->request->param('orderid');
        if (empty($order_sn)) {
            $this->error('参数缺失');
        }
        $order = OrderModel::getDetail($order_sn, $this->auth->id);
        if (empty($order)) {
            $this->error('未找到订单');
        }
        $this->view->assign('title', '订单详情');
        $this->view->assign('orderInfo', $order);
        return $this->view->fetch();
    }

    /**
     * 查看物流
     */
    public function logistics()
    {
        $order_sn = $this->request->param('orderid');
        if (empty($order_sn)) {
            $this->error('参数缺失');
        }
        $order = OrderModel::getDetail($order_sn, $this->auth->id);
        if (empty($order)) {
            $this->error('未找到订单');
        }
        if ($this->request->isPost()) {
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
            if (isset($result['Success']) && $result['Success']) {
                $this->success('查询成功', null, ['traces' => $result['Traces']]);
            } else {
                $this->success('查询失败');
            }
        }

        $this->view->assign('title', '物流详情');
        $this->view->assign('orderInfo', $order);
        return $this->view->fetch();
    }

    /**
     * 申请售后
     */
    public function apply()
    {
        $id = $this->request->param('id/d');
        if (empty($id)) {
            $this->error('参数缺失');
        }

        $row = \addons\shop\model\OrderGoods::get($id, ['Order']);
        if (!$row) {
            $this->error('未找到记录');
        }
        if (!in_array($row->salestate, [0, 6])) {
            $this->error('未审核，不能重复申请');
        }
        $order = $row->order;
        if (empty($order)) {
            $this->error('订单不存在');
        }
        if ($order->user_id != $this->auth->id) {
            $this->error('不可越权操作');
        }
        //未退商品
        $goodsNums = OrderGoods::where('order_sn', $order->order_sn)->where('salestate', 'IN', [0, 6])->count();

        $realprice = $row['realprice'];

        $shippingfee = $row->getAvailableRefundShippingfee();
        $refundprice = bcadd($realprice, $shippingfee, 2);

        if ($this->request->isPost()) {
            $reason = $this->request->post('reason');
            $images = $this->request->post('images');
            $expressno = $this->request->post('expressno');
            $type = $this->request->post('type'); //1=仅退款,2=退款退货

            if ($type != 1 && empty($reason)) {
                $this->error('请输入售后原因');
            }
            if (!in_array($type, [1, 2])) {
                $this->error('不存在的售后类型');
            }
            //订单正常，已发货，已支付
            if (in_array($order->orderstate, [0, 3, 4]) && $order->paystate && $goodsNums > 0) {
                if ($type != 1 && !$order->shippingstate) {
                    $this->error('申请售后类型错误');
                }
                $reason = $type == 1 && empty($reason) ? '仅退款' : $reason;

                // 启动事务
                Db::startTrans();
                try {
                    $row->salestate = $type == 1 ? 2 : 1;
                    $row->save();
                    $order->orderstate = 4;
                    $order->save();

                    //添加售后记录
                    OrderAftersales::create([
                        'user_id'        => $this->auth->id,
                        'order_id'       => $order->id,
                        'order_goods_id' => $id,
                        'type'           => $type,
                        'nums'           => $row['nums'],
                        'reason'         => $reason,
                        'realprice'      => $realprice,
                        'shippingfee'    => $shippingfee,
                        'refund'         => $refundprice,
                        'images'         => $images,
                    ]);
                    // 提交事务
                    Db::commit();
                } catch (\Exception $e) {
                    // 回滚事务
                    Db::rollback();
                    \think\Log::record('售后申请失败:' . $e->getMessage());
                    $this->error('申请失败');
                }
                //记录操作
                OrderAction::push($order->order_sn, '用户', $type == 1 ? '申请退款' : '用户申请退款退货');
                $this->success('申请售后成功，等待审核', $order->url);
            }
            $this->error('不允许的退款订单');
        }
        $this->view->assign('title', '申请售后');
        $this->view->assign('orderInfo', $order);
        $this->view->assign('goodsInfo', $row);
        $this->view->assign('refundprice', $refundprice);
        return $this->view->fetch();
    }

    /**
     * 查看售后状态
     */
    public function aftersale()
    {
        $id = $this->request->param('id');
        if (empty($id)) {
            $this->error('参数缺失');
        }
        $afterSaleInfo = OrderAftersales::with(['OrderGoods'])->where('order_goods_id', $id)->order('id desc')->where('user_id', $this->auth->id)->find();
        if (empty($afterSaleInfo)) {
            $this->error('未找到记录');
        }
        $this->view->assign('title', '售后状态');
        $this->view->assign('aftersaleInfo', $afterSaleInfo);
        $this->view->assign('goodsInfo', $afterSaleInfo->order_goods);
        return $this->view->fetch();
    }

    /**
     * 取消订单
     */
    public function cancel()
    {
        $order_sn = $this->request->post('orderid');
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

    //保存快递信息
    public function saveexpress()
    {
        $id = $this->request->post('id');
        $expressname = $this->request->post('expressname');
        $expressno = $this->request->post('expressno');
        if (empty($id)) {
            $this->error('参数缺失');
        }
        if (empty($expressname)) {
            $this->error('快递名称不能为空');
        }
        if (empty($expressno)) {
            $this->error('快递单号不能为空');
        }
        $row = OrderAftersales::where('order_goods_id', $id)->order('id desc')->where('user_id', $this->auth->id)->find();
        if (empty($row)) {
            $this->error('未找到记录');
        }
        $row->expressname = $expressname;
        $row->expressno = $expressno;
        $row->save();
        $this->success('保存成功');
    }

    /**
     * 确认收货
     */
    public function takedelivery()
    {
        $order_sn = $this->request->post('orderid');
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
        if ($order->status == 'hidden') {
            $this->error('订单已失效！');
        }
        if ($order->paystate == 1 && !$order->orderstate && $order->shippingstate == 1) {
            $order->shippingstate = 2;
            $order->save();
            //记录操作
            OrderAction::push($order->order_sn, '系统', '订单确认收货成功');
            $this->success('确认收货成功');
        }
        $this->error('未可确认收货');
    }
}
