<?php

namespace addons\shop\controller\api;

use addons\shop\model\OrderAction;
use addons\shop\model\OrderAftersales;
use addons\shop\model\OrderGoods as orderGoodsModel;
use think\Db;

/**
 * 订单接口
 */
class OrderGoods extends Base
{
    protected $noNeedLogin = [];

    public function detail()
    {
        $id = $this->request->param('id');
        if (empty($id)) {
            $this->error('参数缺失');
        }
        $row = orderGoodsModel::get($id, ['Order']);
        if (!$row) {
            $this->error('未找到记录');
        }
        if ($row->salestate && $row->salestate != 6) {
            $this->error('未拒绝，不能重复申请');
        }
        $order = $row->order;
        if (empty($order)) {
            $this->error('订单不存在');
        }
        if ($order->user_id != $this->auth->id) {
            $this->error('不可越权操作');
        }
        //订单正常，已发货，已支付
        if (in_array($order->orderstate, [0, 3, 4]) && $order->shippingstate && $order->paystate) {
            $row->visible(explode(',', 'id,order_sn,goods_id,title,image,attrdata,price,nums'));
            $this->success('', $row);
        }
        $this->error('不允许的退款订单');
    }

    //申请售后
    public function apply()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $id = $this->request->post('id');
        $reason = $this->request->post('reason');
        $images = $this->request->post('images');
        $expressno = $this->request->post('expressno');
        $type = $this->request->post('type'); //1=仅退款,2=退款退货
        $reasonCode = $this->request->post('reason_code', '');

        if (empty($id)) {
            $this->error('参数缺失');
        }
        if ($type != 1 && empty($reason)) {
            $this->error('请输入售后原因');
        }
        if (!in_array($type, [1, 2])) {
            $this->error('不存在的售后类型');
        }
        $row = orderGoodsModel::get($id, ['Order']);
        if (!$row) {
            $this->error('未找到记录');
        }
        if ($row->salestate && $row->salestate != 6) {
            $this->error('未审核，不能重复申请');
        }
        $order = $row->order;
        if (empty($order)) {
            $this->error('订单不存在');
        }
        if ($order->user_id != $this->auth->id) {
            $this->error('不可越权操作');
        }
        try {
            $policy = (new \addons\shop\library\v5\AftersalePolicyService())
                ->assertUserApplicationAllowed($order->order_sn, $id, $reasonCode);
        } catch (\addons\shop\library\v5\DomainException $e) {
            $this->error($e->getMessage());
        }
        //未退商品
        $goodsNums = \addons\shop\model\OrderGoods::where('order_sn', $order->order_sn)->where('salestate', 'IN', [0, 6])->count();

        $realprice = $row['realprice'];

        $shippingfee = $row->getAvailableRefundShippingfee();
        $refundprice = bcadd($realprice, $shippingfee, 2);

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
                    'source_type'    => $policy['source_type'],
                    'batch_id'       => $policy['batch_id'],
                    'reason_code'    => $reasonCode,
                    'request_id'     => \addons\shop\library\v5\Identifiers::requestId(),
                ]);
                // 提交事务
                Db::commit();
            } catch (\Exception $e) {
                // 回滚事务
                Db::rollback();
                \think\Log::record('售后申请失败:'.$e->getMessage());
                $this->error('申请失败');
            }
            //记录操作
            OrderAction::push($order->order_sn, '用户', $type == 1 ? '申请退款' : '用户申请退款退货');
            $this->success('申请售后成功，等待审核', $order->url);
        }
        $this->error('不允许的退款订单');
    }

    //查看售后
    public function aftersale()
    {
        $id = $this->request->param('id');
        if (empty($id)) {
            $this->error('参数缺失');
        }
        $row = OrderAftersales::with(['OrderGoods'])->where('order_goods_id', $id)->order('id desc')->where('user_id', $this->auth->id)->find();
        if (empty($row)) {
            $this->error('未找到记录');
        }
        $this->success('获取成功', $row);
    }

    //保存快递信息
    public function saveExpressInfo()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
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
        if (!empty($row->expressname)) {
            $this->error('快递已提交');
        }
        $row->expressname = $expressname;
        $row->expressno = $expressno;
        $row->save();
        $this->success('保存成功');
    }
}
