<?php

namespace addons\shop\controller\api;

use addons\shop\model\Collect as CollectModel;
use addons\shop\model\Goods;

/**
 * 收藏
 */
class Collect extends Base
{
    protected $noNeedLogin = [];

    /**
     * 添加/取消收藏
     */
    public function optionCollect()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $goods_id = $this->request->post('goods_id');
        if (!$this->request->isPost()) {
            $this->error('请求错误');
        }
        if (!$goods_id) {
            $this->error('缺少参数！');
        }
        $data = (new Goods())->get($goods_id);
        if (!$data || $data['status'] != 'normal') {
            $this->error('收藏的商品已失效！');
        }
        $status = CollectModel::addOrCancel($this->auth->id, $goods_id);
        if ($status) {
            $this->success('操作成功');
        }
        $this->error('操作失败');
    }

    /**
     * 我的收藏
     */
    public function collectList()
    {
        $param = $this->request->param();
        $param['user_id'] = $this->auth->id;
        $list = CollectModel::tableList($param);
        $this->success('', $list);
    }
}
