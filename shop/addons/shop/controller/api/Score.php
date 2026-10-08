<?php

namespace addons\shop\controller\api;

use addons\shop\model\Exchange;
use addons\shop\model\ExchangeOrder;
use addons\shop\model\ScoreLog;
use addons\shop\model\Address;
use think\Db;

/**
 * 积分兑换接口
 */
class Score extends Base
{
    protected $noNeedLogin = ['exchangeList'];

    /**
     * 积分日志
     */
    public function logs()
    {
        $list = ScoreLog::where(['user_id' => $this->auth->id])
            ->order('id desc')
            ->paginate(10);

        $this->success('', $list);
    }

    /**
     * 积分兑换列表
     */
    public function exchangeList()
    {
        $this->success('获取成功', Exchange::tableList($this->request->param()));
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

        $row = Exchange::get($exchange_id);
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

    /**
     * 我的积分兑换
     */
    public function myExchange()
    {
        $param = $this->request->param();
        $param['user_id'] = $this->auth->id;
        $this->success('获取成功', ExchangeOrder::tableList($param));
    }
}
