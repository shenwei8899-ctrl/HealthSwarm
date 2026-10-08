<?php

namespace app\index\controller\shop;

use app\common\controller\Frontend;
use addons\shop\model\ExchangeOrder;

class Exchange extends Frontend
{

    protected $layout = 'default';
    protected $noNeedLogin = [];
    protected $noNeedRight = ['*'];

    //我的优惠券列表
    public function index()
    {
        $param = $this->request->param();
        $param['f'] = isset($param['status']) ? $param['status'] : '';
        $param['user_id'] = $this->auth->id;
        $this->assign('__list__', ExchangeOrder::tableList($param));
        $this->assign('param', $param);
        $this->view->assign('title', '我的积分兑换');
        return $this->view->fetch();
    }
}
