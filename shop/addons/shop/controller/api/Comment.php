<?php

namespace addons\shop\controller\api;

use addons\shop\model\Comment as CommentModel;
use addons\shop\model\Order;
use addons\shop\model\OrderAftersales;
use addons\shop\model\OrderAction;
use think\Db;

/**
 * 评论
 */
class Comment extends Base
{
    protected $noNeedLogin = ['index'];

    /**
     * 评论列表
     */
    public function index()
    {
        $list = CommentModel::getCommentList($this->request->param());
        foreach ($list as $item) {
            if ($item->user) {
                $item->user->avatar = cdnurl($item->user->avatar, true);
                $item->user->visible(explode(',', 'id,nickname,avatar'));
            }

            $item->hidden(explode(',', 'subscribe,status,ip,useragent'));
        }
        $this->success('获取成功', $list);
    }


    //添加评论
    public function add()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $pid = $this->request->post('pid/d', 0);
        $order_sn = $this->request->post('order_sn');
        $remark = $this->request->post('remark/a', '', 'trim,xss_clean');
        if (empty($remark) || !is_array($remark)) {
            $this->error('评论内容不能为空');
        }
        $order = Order::with(['OrderGoods'])
            ->where('order_sn', $order_sn)
            ->where('orderstate', 0)
            ->where('shippingstate', 2)
            ->where('paystate', 1)
            ->where('user_id', $this->auth->id)->find();

        if (!$order) {
            $this->error('未找到可评论的订单');
        }
        $row = CommentModel::where('user_id', $this->auth->id)->where('order_id', $order->id)->find();
        if ($row) {
            $this->error('订单已评论');
        }

        $data = [];
        $goods_ids = [];
        //可以评价的商品
        foreach ($order->order_goods as $item) {
            if (in_array($item['salestate'], [0, 6])) {
                $goods_ids[] = $item['goods_id'];
            }
        }
        foreach ($remark as $item) {
            if (!isset($item['goods_id'])) {
                $this->error('缺少参数goods_id');
            }
            if (!isset($item['star'])) {
                $this->error('缺少评分参数');
            }
            if (!isset($item['images'])) {
                $this->error('缺少参数images');
            }
            if (!in_array($item['goods_id'], $goods_ids)) {
                $this->error('存在不可评价的商品');
            }
            if (empty($item['content'])) {
                $this->error('评论内容不能为空');
            }
            $data[] = [
                'pid'       => $pid,
                'order_id'  => $order['id'],
                'user_id'   => $this->auth->id,
                'goods_id'  => $item['goods_id'],
                'star'      => $item['star'],
                'content'   => $item['content'],
                'images'    => $item['images'],
                'ip'        => request()->ip(),
                'useragent' => substr(request()->server('HTTP_USER_AGENT'), 0, 255),
                'status'    => 'hidden'
            ];
        }
        Db::startTrans();
        try {
            (new CommentModel())->saveAll($data);
            $order->orderstate = 3;
            $order->save();
            foreach ($order->order_goods as $item) {
                $item->save(['commentstate' => 1]);
            }
            //是否有积分
            $config = get_addon_config('shop');
            if ($config['comment_score'] > 0) {
                \app\common\model\User::score($config['comment_score'], $this->auth->id, '评论订单赠送' . $config['comment_score'] . '积分');
            }
            //结束，订单完成，给积分
            if (isset($config['money_score']) && $config['money_score'] > 0 && $order->shippingstate == 2 && $order->paystate == 1) {
                //减去退款金额
                $refund = OrderAftersales::where('order_id', $order->id)->where('type', '<>', 3)->where('status', 2)->sum('refund');
                $money = bcsub($order['payamount'], $refund, 2);
                if ($money > 0) {
                    $score = bcmul($money, $config['money_score']);
                    \app\common\model\User::score($score, $this->auth->id, '完成订单奖励' . $score . '积分');
                }
            }
            // 提交事务
            Db::commit();
        } catch (\Exception $e) {
            // 回滚事务
            Db::rollback();
            $this->error('添加评论失败');
        }
        OrderAction::push($order->order_sn, '系统', '订单已完成');
        $this->success('添加评论成功,等待审核！');
    }


    //我的评价
    public function myList()
    {
        $list = CommentModel::with([
            'Goods' => function ($query) {
                $query->field('id,title,image');
            }
        ])->where('user_id', $this->auth->id)->where('pid', 0)->where('status', 'normal')->order('createtime desc')->paginate(10);
        foreach ($list as $item) {
            $item->hidden(['ip', 'subscribe', 'useragent', 'comments']);
        }
        $this->success('获取成功', $list);
    }

    //回复评论
    // public function reply()
    // {
    //     $pid = $this->request->post('pid');
    //     $content = $this->request->post('content');
    //     if (!$content) {
    //         $this->error('回复内容不能为空');
    //     }
    //     $row = CommentModel::where('id', $pid)->where('status', 'normal')->find();
    //     if (!$row) {
    //         $this->error('未找到记录');
    //     }
    //     $row->setInc('comments');
    //     CommentModel::create([
    //         'pid' => $pid,
    //         'order_id' => $row->order_id,
    //         'user_id' => $this->auth->id,
    //         'goods_id' => $row->goods_id,
    //         'star' => 0,
    //         'content' => $content,
    //         'ip' => request()->ip(),
    //         'useragent' => substr(request()->server('HTTP_USER_AGENT'), 0, 255),
    //         'status' => 'hidden'
    //     ]);
    //     $this->success('提交回复成功');
    // }
}
