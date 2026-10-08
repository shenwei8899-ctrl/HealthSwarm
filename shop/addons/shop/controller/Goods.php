<?php

namespace addons\shop\controller;

use addons\shop\model\Category;
use addons\shop\model\Collect;
use addons\shop\model\Goods as GoodsModel;
use addons\shop\model\CouponCondition;
use addons\shop\model\UserCoupon;
use addons\shop\model\Coupon;
use addons\shop\model\SkuSpec;
use addons\shop\model\Guarantee;
use addons\shop\model\AttributeValue;
use think\Config;

/**
 * 详情控制器
 * Class Goods
 * @package addons\shop\controller
 */
class Goods extends Base
{
    protected $noNeedLogin = '*';
    protected $noNeedRight = '*';

    public function _initialize()
    {
        parent::_initialize();
    }

    /**
     * 商品详情页
     */
    public function index()
    {

        $id = $this->request->param('id/d');

        // 判断是否跳转移动端
        $this->checkredirect('goods/detail', ['id' => $id]);

        if (!$id) {
            $this->error('参数错误');
        }

        $row = (new GoodsModel())->with([
            'Sku',
            'Comment' => function ($query) {
                $query->where('status', 'normal')->field('id,goods_id,content,star,user_id,images,createtime')->with([
                    'User' => function ($u) {
                        $u->field('id,nickname,avatar');
                    }
                ]);
            }
        ])->where('status', '<>', 'hidden')->where('id', $id)->find();
        if (!$row) {
            $this->error('未找到该商品');
        }
        $row->setInc('views');

        $category = Category::get($row['category_id']);

        //收藏
        if ($this->auth->isLogin()) {
            $row->is_collect = !!(Collect::where('user_id', $this->auth->id)->where('goods_id', $id)->where('status', 1)->find());
        } else {
            $row->is_collect = false;
        }
        $row->sku_spec = SkuSpec::getGoodsSkuSpec($id);
        //$row->visible(explode(',', 'id,title,price,marketprice,sales,views,image,content,images,sku_spec,sku,comment,is_collect'));

        $sku_spec = collection($row->sku_spec)->toArray();
        array_multisort(array_column($sku_spec, 'id'), SORT_ASC, $sku_spec);
        $row->sku_spec = $sku_spec;

        //print_r(collection($sku)->toArray());exit;
        $priceList = [];
        foreach ($row->sku as $index => $item) {
            $priceList[$item['sku_id']] = $item;
        }

        //评论列表
        $commentList = $row->comment()->relation([
            'reply' => function ($query) {
                $query->with([
                    'manage' => function ($u) {
                        $u->field('id,nickname');
                    }
                ]);
            }
        ])->where('status', 'normal')->paginate([
            'path' => 'javascript:load_comment_list([PAGE]);'
        ]);
        foreach ($commentList as &$item) {
            if ($item['user']) {
                $item['user']['avatar'] = cdnurl($item['user']['avatar'], true);
            }
        }
        unset($item);
        //服务保障
        $guarantee = [];
        if ($row->guarantee_ids) {
            $guarantee = Guarantee::where('id', 'IN', $row->guarantee_ids)->where('status', 'normal')->select();
        }
        $this->view->assign('guarantee', $guarantee);
        //属性
        $attributes = AttributeValue::getAttributeList($row->attribute_ids);
        $this->view->assign('attributes', $attributes);

        //优惠券
        $conditions = CouponCondition::getGoodsCondition($id, $row->category_id, $row->brand_id);
        $sql = "condition_ids IS NULL OR condition_ids=''";
        foreach ($conditions as $key => $item) {
            $sql .= " OR FIND_IN_SET('{$item['id']}',condition_ids)";
        }
        $couponList = Coupon::where($sql)
            ->where('is_open', 1)
            ->where('is_private', 'no')
            ->where('endtime', '>', time())
            ->limit(3)
            ->select();
        //已经登录，渲染已领的优惠券
        $coupon_ids = [];
        if ($this->auth->isLogin()) {
            $coupon_ids = UserCoupon::where('user_id', $this->auth->id)->column('coupon_id');
        }
        foreach ($couponList as $key => &$item) {
            Coupon::render($item, $coupon_ids);
        }

        $this->view->assign('couponList', $couponList);
        $this->view->assign('commentList', $commentList);
        $this->view->assign('priceList', $priceList);
        $this->view->assign('__category__', $category);
        $this->view->assign('__goods__', $row);

        Config::set('shop.title', isset($row['seotitle']) && $row['seotitle'] ? $row['seotitle'] : $row['title']);
        Config::set('shop.keywords', $row['keywords']);
        Config::set('shop.description', $row['description']);
        Config::set('shop.image', cdnurl($row['image'], true));
        return $this->view->fetch('/show');
    }

    /**
     * 获取评论列表
     */
    public function get_comment_list()
    {
        if (!$this->request->isPost()) {
            $this->error('请求方式错误');
        }
        $id = $this->request->post("id/d");
        $page = $this->request->post("page/d", 1);
        if (!$id || !$page) {
            $this->error("参数不正确");
        }
        $row = GoodsModel::get($id);
        if (!$row) {
            $this->error('未找到指定的商品');
        }

        //评论列表
        $commentList = $row->comment()->where('status', 'normal')->paginate([
            'path' => 'javascript:load_comment_list([PAGE]);'
        ]);

        $this->success('', '', $this->fetch('common/comment', ['__goods__' => $row, 'commentList' => $commentList]));
    }
}
