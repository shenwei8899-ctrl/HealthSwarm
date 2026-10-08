<?php

namespace addons\shop\controller;

use addons\shop\model\Coupon as CouponModel;
use addons\shop\model\UserCoupon;
use addons\shop\model\CouponCondition;
use addons\shop\model\Goods;
use think\Db;
use addons\shop\library\IntCode;

class Coupon extends Base
{

    protected $noNeedLogin = ['show', 'index'];
    protected $noNeedRight = '*';

    public function _initialize()
    {
        parent::_initialize();
    }

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
    public function index()
    {
        // 判断是否跳转移动端
        $this->checkredirect('coupon/list');

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
            $item = CouponModel::render($item, $coupon_ids);
        }
        $this->view->assign('result', $this->request->param('result'));
        $this->view->assign('couponList', $list);
        return $this->view->fetch('/coupon_index');
    }

    //优惠券详情
    public function show()
    {
        $coupon_id = $this->request->param('coupon');

        // 判断是否跳转移动端
        $this->checkredirect('coupon/detail', ['id' => $coupon_id]);

        $id = IntCode::decode($coupon_id);
        if (!$id) {
            $this->error('参数错误');
        }

        $row = CouponModel::where('id', $id)->where('is_open', 1)->find();
        if (!$row) {
            $this->error('未找到可用的优惠券');
        }
        //优惠券可使用的商品
        $conditions = CouponCondition::where('id', 'IN', $row['condition_ids'])->select();
        $goods = Goods::where(function ($query) use ($conditions) {
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
        })->limit(16)->where('status', 'normal')->select();
        $this->view->assign('coupon_goods', $goods);
        //已经登录，渲染已领的优惠券
        $coupon_ids = [];
        if ($this->auth->isLogin()) {
            $coupon_ids = UserCoupon::where('user_id', $this->auth->id)->column('coupon_id');
        }
        CouponModel::render($row, $coupon_ids);
        $this->view->assign('__info__', $row);
        return $this->view->fetch('/coupon_show');
    }
}
