<?php

namespace addons\shop\controller;

use addons\shop\model\Carts;
use addons\shop\model\Goods;
use addons\shop\model\Sku;
use think\Config;

/**
 * 购物车控制器
 * Class Cart
 * @package addons\shop\controller
 */
class Cart extends Base
{
    protected $noNeedLogin = [];
    protected $noNeedRight = '*';

    public function _initialize()
    {
        parent::_initialize();
    }

    /**
     * 购物车首页
     */
    public function index()
    {

        // 判断是否跳转移动端
        $this->checkredirect('cart');

        $ids = $this->request->param('ids');
        $sceneval = $this->request->param('sceneval/d', 1);
        $list = Carts::getGoodsList($ids, $this->auth->id, $sceneval);
        //没有商品过滤数据
        foreach ($list as $key => $item) {
            if ((empty($item->goods) && empty($item->sku)) || empty($item->goods)) {
                $item->delete();
                unset($list[$key]);
                continue;
            }
            $item['subtotal'] = bcmul($item['nums'], ($item->sku->price ?? $item->goods->price), 2);
        }

        $cartList = $list;
        $this->view->assign("cartList", $cartList);

        Config::set('shop.title', "购物车");
        return $this->view->fetch('/cart');
    }

    //添加购物车
    public function add()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $goods_id = $this->request->post('goods_id/d'); //单规格使用
        $goods_sku_id = $this->request->post('goods_sku_id/d'); //多规格使用
        $nums = $this->request->post('nums/d', 1);
        $sceneval = $this->request->post('sceneval/d', 1);
        if (empty($goods_id) && empty($goods_sku_id)) {
            $this->error('参数错误');
        }
        if ($nums <= 0) {
            $this->error('数量必须大于0');
        }
        $goods = Goods::get($goods_id);
        if (!$goods || $goods['status'] != 'normal') {
            $this->error('未找到指定商品');
        }
        if ($goods['spectype']) {
            if (!$goods_sku_id) {
                $this->error('请选择商品规格');
            }
            $row = Sku::with([
                'goods' => function ($query) {
                    $query->where('status', 'normal');
                }
            ])->where('id', $goods_sku_id)->find();

            if (empty($row) || empty($row->goods)) {
                $this->error('商品已下架');
            }
            if ($row->stocks < $nums) {
                $this->error('库存数量不足' . $nums . '件');
            }
        } else {
            $row = Goods::where('id', $goods_id)->where('status', 'normal')->find();
            if (empty($row)) {
                $this->error('商品已下架');
            }
            if ($row->stocks < $nums) {
                $this->error('库存数量不足' . $nums . '件');
            }
        }
        //去添加购物车
        $cart_id = Carts::push($goods_id, $goods_sku_id, $nums, $this->auth->id, $sceneval);
        $cartnums = Carts::where('user_id', $this->auth->id)->where('sceneval', 1)->count();
        $this->success('添加成功', '', ['cartnums' => $cartnums, 'cart_id' => $cart_id]);
    }


    //删除购物车
    public function del()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $id = $this->request->post('id/a');
        if (!$id) {
            $this->error('参数错误');
        }
        $status = Carts::where('user_id', $this->auth->id)->where('id', 'IN', $id)->delete();
        if ($status) {
            $this->success('删除成功');
        }
        $this->error('删除失败');
    }


    //购物车商品数量+-
    public function set_nums()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $id = $this->request->post('id');
        if (!$id) {
            $this->error('参数错误');
        }
        $nums = $this->request->post('nums/d');
        if ($nums <= 0) {
            $this->error('数量必须大于0');
        }
        $row = Carts::with(['Goods', 'Sku'])->where('id', $id)->where('user_id', $this->auth->id)->find();
        if (!$row) {
            $this->error('未找到记录');
        }
        if ($row->goods_sku_id) {
            if (!$row->sku) {
                $this->error('商品不存在');
            }
            if ($row->sku->stocks < $nums) {
                $this->error('库存不足');
            }
        } else {
            if (!$row->goods) {
                $this->error('商品不存在');
            }
            if ($row->goods->stocks < $nums) {
                $this->error('库存不足');
            }
        }
        $row->nums = $nums;
        $row->save();
        $this->success('操作成功');
    }

}
