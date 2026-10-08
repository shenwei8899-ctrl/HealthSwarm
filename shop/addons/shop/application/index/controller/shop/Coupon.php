<?php

namespace app\index\controller\shop;

use app\common\controller\Frontend;
use addons\shop\library\IntCode;
use addons\shop\model\UserCoupon;

class Coupon extends Frontend
{

    protected $layout = 'default';
    protected $noNeedLogin = [];
    protected $noNeedRight = ['*'];

    //我的优惠券列表
    public function index()
    {
        $param = $this->request->param();
        $param['user_id'] = $this->auth->id;
        $param['f'] = isset($param['is_used'])?$param['is_used']:'0';
        if(isset($param['expire_time']) && !empty($param['expire_time'])){
            $param['f'] = 4;
        }
        if(isset($param['begin_time']) && !empty($param['begin_time'])){
            $param['f'] = 3;
        }
        $list = UserCoupon::tableList($param);
        foreach ($list as $item) {
            $item->coupon_id = IntCode::encode($item->coupon_id);   
            if ($item->coupon) {
                $item->coupon->id = $item->coupon_id;                
            }        
        }
        $this->view->assign('title', '我的优惠券');
        $this->view->assign('param',$param);
        $this->view->assign('coupon_list',$list);
        return $this->view->fetch();
    }
}
