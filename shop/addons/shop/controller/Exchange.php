<?php

namespace addons\shop\controller;

use addons\shop\model\Exchange as ExchangeModel;
use addons\shop\model\ExchangeOrder;
use addons\shop\model\Address;
use think\Db;

/**
 * 积分兑换接口
 */
class Exchange extends Base
{
    protected $noNeedLogin = ['index', 'show'];


    /**
     * 积分兑换列表
     */
    public function index()
    {
        // 判断是否跳转移动端
        $this->checkredirect('exchange/list');

        $list = ExchangeModel::tableList($this->request->param());
        $this->assign('exchangeList', $list);
        $this->assign('type', $this->request->param('type'));
        return $this->view->fetch('/exchange_index');
    }

    /**
     * 积分兑换详情
     */
    public function show()
    {
        $id = $this->request->param('id/d');
        if (!$id) {
            $this->error('参数错误');
        }
        $row = ExchangeModel::get($id);
        if (empty($row)) {
            $this->error('兑换商品未找到');
        }
        if ($row->stocks <= 0) {
            $this->error('兑换商品库存不足');
        }
        $addressList = [];
        if ($this->auth->isLogin()) {
            $addressList = Address::where('status', 'normal')->where('user_id', $this->auth->id)->select();
        }
        $this->assign('addressList', $addressList);
        $this->assign('row', $row);
        return $this->view->fetch('/exchange_show');
    }

    /**
     * 积分兑换
     */
    public function exchange()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $address_id = $this->request->post('address_id/d');
        $memo = $this->request->post('memo');
        $nums = (int)$this->request->post('nums/d', 1);
        $exchange_id = $this->request->post('exchange_id/d');

        $row = ExchangeModel::get($exchange_id);
        if (empty($row)) {
            $this->error('兑换物品不存在');
        }
        $data = [];
        if ($row->type == 'reality') {
            $address = Address::where('status', 'normal')->where('id', $address_id)->find();
            if (empty($address)) {
                $this->error('未找到正确地址');
            }
            if ($address->user_id != $this->auth->id) {
                $this->error('不能越权操作');
            }
            $data = array_merge($data, [
                'receiver' => $address->receiver,
                'mobile'   => $address->mobile,
                'address'  => $address->address
            ]);
        }
        if ($nums <= 0) {
            $nums = 1;
        }
        $score = bcmul($nums, $row['score']);
        if ($this->auth->score < $score) {
            $this->error('积分不足，无法兑换');
        }
        // 启动事务
        Db::startTrans();
        try {
            $data = array_merge($data, [
                'type'        => $row->type,
                'memo'        => $memo,
                'score'       => $score,
                'nums'        => $nums,
                'user_id'     => $this->auth->id,
                'exchange_id' => $exchange_id
            ]);
            ExchangeOrder::createOrder($data);
            $row->setDec('stocks');
            $row->setInc('sales');
            \app\common\model\User::score(-$score, $this->auth->id, '积分兑换商品');
            // 提交事务
            Db::commit();
        } catch (\Exception $e) {
            // 回滚事务
            Db::rollback();
            $this->error('提交失败');
        }
        $this->success('提交成功，等待管理员处理！');
    }

}
