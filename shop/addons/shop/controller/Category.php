<?php

namespace addons\shop\controller;

use addons\shop\model\GoodsAttr;
use think\Config;

/**
 * 分类控制器
 * Class Category
 * @package addons\shop\controller
 */
class Category extends Base
{
    protected $noNeedLogin = '*';
    protected $noNeedRight = '*';

    public function _initialize()
    {
        parent::_initialize();
    }

    /**
     * 分类首页
     */
    public function index()
    {

        $diyname = $this->request->param('diyname');

        if ($diyname && !is_numeric($diyname)) {
            $category = \addons\shop\model\Category::getByDiyname($diyname);
        } else {
            $id = $diyname ? $diyname : $this->request->param('id', '');
            $category = \addons\shop\model\Category::get($id);
        }

        if (!$category) {
            $this->error("分类未找到");
        }

        // 判断是否跳转移动端
        $this->checkredirect('goods/goods', ['category_id'=>$category['id']]);

        $orderList = [
            'default'    => ['title' => '默认排序', 'value' => 'weigh'],
            'sales'      => ['title' => '销量', 'value' => 'sales'],
            'comments'   => ['title' => '评价次数', 'value' => 'comments'],
            'createtime' => ['title' => '发布时间', 'value' => 'createtime'],
        ];
        $orderby = $this->request->get('orderby', 'default');
        $orderway = $this->request->get('orderway', 'desc');
        $order = isset($orderList[$orderby]) ? $orderList[$orderby] : $orderList['default'];
        $orderby = $order['value'];
        $orderway = $orderway == 'asc' ? 'asc' : 'desc';

        $filter = $this->request->get();
        $multiple = $this->request->get('multiple/d', 0);
        $params = $filter;

        $goodsList = \addons\shop\model\Goods::where('category_id', 'in', \addons\shop\model\Category::getCategoryChildrenIds($category['id']))
            ->where(function ($query) use ($filter) {
                //属性
                $attributes = [];
                if ($filter) {
                    foreach ($filter as $index => $item) {
                        if (preg_match("/^f_(\d+)\$/i", $index, $match)) {
                            $attributes[] = ['attribute_id' => $match[1], 'value_id' => $item];
                        }
                    }
                    if ($attributes) {
                        $query->where('id', 'IN', GoodsAttr::getGoodsIds($attributes));
                    }
                }
                //品牌
                if (isset($filter['brand_id']) && !empty($filter['brand_id'])) {
                    $query->where('brand_id', 'IN', $filter['brand_id']);
                }
            })
            ->where('status', '<>', 'hidden')
            ->order($orderby, $orderway)
            ->paginate(20, false, [
                'query' => $this->request->get()
            ]);

        if ($multiple) {
            $params['multiple'] = 1;
        } else {
            unset($filter['multiple']);
        }
        $filterList = \addons\shop\model\Category::getFilterList($category, $filter, $params, $multiple);

        foreach ($orderList as $key => &$item) {
            $query = array_merge($params, ['orderby' => $key, 'orderway' => ($orderby == $item['value'] ? ($orderway == 'desc' ? 'asc' : 'desc') : 'desc')]);
            $item['active'] = $item['value'] == $orderby ? true : false;
            $item['url'] = $category['url'] . (stripos($category['url'], '?') !== false ? '&' : '?') . http_build_query($query);
        }

        $this->view->assign('orderby', $orderby);
        $this->view->assign('orderway', $orderway);
        $this->view->assign('orderList', $orderList);
        $this->view->assign('filterList', $filterList);
        $this->view->assign('goodsList', $goodsList);
        $this->view->assign('__category__', $category);

        Config::set('shop.title', isset($category['seotitle']) && $category['seotitle'] ? $category['seotitle'] : $category['name']);
        Config::set('shop.keywords', $category['keywords']);
        Config::set('shop.description', $category['description']);
        return $this->view->fetch('/list');
    }

}
