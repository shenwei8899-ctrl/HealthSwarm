<?php

namespace app\index\controller\shop;

use addons\shop\model\Comment as CommentModel;
use addons\shop\model\Order;
use app\common\controller\Frontend;
use think\Config;
use think\Db;

class Comment extends Frontend
{

    protected $layout = 'default';
    protected $noNeedLogin = [];
    protected $noNeedRight = ['*'];

    /**
     * 我的评价
     */
    public function index()
    {
        $param = [];
        $param['user_id'] = $this->auth->id;
        $param['status'] = 'normal';
        $commentList = \addons\shop\model\Comment::with('goods')->where($param)->paginate();

        $this->view->assign('commentList', $commentList);
        $this->view->assign('title', '我的评价');
        return $this->view->fetch();
    }

    /**
     * 发表评价
     */
    public function post()
    {
        $order_sn = $this->request->request('orderid');

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

        if ($this->request->isPost()) {
            $pid = $this->request->post('pid/d', 0);
            $pid = 0;
            $remark = $this->request->post('remark/a', '', 'trim,xss_clean');
            if (empty($remark) || !is_array($remark)) {
                $this->error('评论内容不能为空');
            }

            $data = [];
            $goods_ids = array_column($order->order_goods, 'goods_id');

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
                    $this->error('不可越权操作');
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
                // 提交事务
                Db::commit();
            } catch (\Exception $e) {
                // 回滚事务
                Db::rollback();
                $this->error('添加评论失败');
            }
            $this->success('添加评论成功,等待审核！', $order->url);
        }

        $this->view->assign('orderInfo', $order);
        $this->view->assign('title', '我的评价');
        return $this->view->fetch();
    }


}
