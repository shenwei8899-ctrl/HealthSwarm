<?php

namespace addons\shop\controller\api;

use addons\shop\model\Coupon as CouponModel;
use addons\shop\model\UserCoupon;
use addons\shop\model\CouponCondition;
use addons\shop\model\Goods;
use think\Db;
use addons\shop\library\IntCode;

/**
 * 优惠券
 */
class Coupon extends Base
{

    protected $noNeedLogin = ['couponList', 'couponDetail'];

    //领取优惠券
    public function drawCoupon()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $coupon_id = $this->request->post('id');
        if (!$coupon_id) {
            $this->error('参数错误');
        }
        $coupon_id = IntCode::decode($coupon_id);
        if (!$coupon_id) {
            $this->error('参数错误');
        }
        $model = new CouponModel();
        try {
            $row = $model->getCoupon($coupon_id)
                ->checkCoupon()
                ->checkOpen()
                ->checkNumber()
                ->checkMyNumber($this->auth->id)
                ->checkReceiveTime();
            list($begin_time, $expire_time) = $row->getUseTime();
            Db::startTrans();
            try {
                //检测没问题，可领取
                (new UserCoupon())->save([
                    'coupon_id'   => $coupon_id,
                    'user_id'     => $this->auth->id,
                    'begin_time'  => $begin_time,
                    'expire_time' => $expire_time
                ]);
                $row->setInc('received_num');
                // 提交事务
                Db::commit();
            } catch (\Exception $e) {
                // 回滚事务
                Db::rollback();
                throw new \Exception($e->getMessage());
            }
        } catch (\Exception $e) {
            $this->error($e->getMessage());
        }
        $this->success('领取优惠券成功！');
    }

    //优惠券列表
    public function couponList()
    {
        $param = $this->request->param();
        $param['is_private'] = 'no';
        $param['is_open'] = 1;
        $param['num'] = 15;
        $list = CouponModel::tableList($param);
        //已经登录，渲染已领的优惠券
        $coupon_ids = [];
        if ($this->auth->isLogin()) {
            $coupon_ids = UserCoupon::where('user_id', $this->auth->id)->column('coupon_id');
        }
        foreach ($list as $key => &$item) {
            CouponModel::render($item, $coupon_ids);
            $item->hidden(['received_num', 'give_num', 'condition_ids']);
        }
        $this->success('获取成功！', $list);
    }

    //优惠券详情
    public function couponDetail()
    {
        $coupon_id = $this->request->param('id');
        $id = IntCode::decode($coupon_id);
        if (!$id) {
            $this->error('参数错误');
        }
        $row = CouponModel::where('id', $id)->where('is_open', 1)->find();
        if ($row) {
            //优惠券可使用的商品
            $conditions = CouponCondition::where('id', 'IN', $row['condition_ids'])->select();
            $row->goods = Goods::field('id,title,image,price,views,sales,marketprice')
                ->where(function ($query) use ($conditions) {
                    //组合条件
                    foreach ($conditions as $item) {
                        switch ($item['type']) { //1商品
                            case 1:
                                $goods_ids = explode(',', $item['content']);
                                if ($goods_ids) {
                                    $query->where('id', 'IN', $goods_ids);
                                }
                                break;
                            case 4: //指定分类
                                $category_ids = explode(',', $item['content']);
                                if ($category_ids) {
                                    $query->whereOr('category_id', 'IN', $category_ids);
                                }
                                break;
                            case 5: //指定品牌
                                $brand_ids = explode(',', $item['content']);
                                if ($brand_ids) {
                                    $query->whereOr('brand_id', 'IN', $brand_ids);
                                }
                                break;
                        }
                    }
                })
                ->limit(15)
                ->select();
            //已经登录，渲染已领的优惠券
            $coupon_ids = [];
            if ($this->auth->isLogin()) {
                $coupon_ids = UserCoupon::where('user_id', $this->auth->id)->column('coupon_id');
            }
            CouponModel::render($row, $coupon_ids);
            $this->success('获取成功！', $row);
        }
        $this->error('记录未找到');
    }

    //我的优惠券列表
    public function myCouponList()
    {
        $param = $this->request->param();
        $param['user_id'] = $this->auth->id;
        $list = UserCoupon::tableList($param);
        foreach ($list as $item) {
            if ($item->coupon) {
                $item->coupon->id = is_numeric($item->coupon->id) ? IntCode::encode($item->coupon->id) : $item->coupon->id;
                $item->coupon_id = $item->coupon->id;
            }
            $item->expired = $item->expire_time < time();
            $item->begin = $item->begin_time < time();
        }
        $this->success('获取成功！', $list);
    }
}
