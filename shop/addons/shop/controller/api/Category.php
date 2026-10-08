<?php

namespace addons\shop\controller\api;

use addons\shop\model\Category as CategoryModel;
use fast\Tree;

/**
 * 商品分类
 */
class Category extends Base
{
    protected $noNeedLogin = ['index', 'alls'];

    //分类列表
    public function index()
    {
        $category_mode = $this->request->param('category_mode');
        if ($category_mode == 1) { //一级分类

            $list = CategoryModel::relation([
                'goods' => function ($query) {
                    $query->field('id,title,image,price,sales,views,description,marketprice,createtime')->limit(10);
                }
            ])->where('pid', 0)->where('isnav', 1)
                ->field('id,name,image,diyname,flag')
                ->order('weigh desc,id asc')->select();

        } else //二级分类 //三级分类
        {
            $tree = Tree::instance();
            $categoryList = CategoryModel::field('id,pid,name,image,diyname,flag')->order('weigh desc,id asc')->where('isnav', 1)->select();
            $tree->init(collection($categoryList)->toArray(), 'pid');
            $list = $tree->getTreeArray(0);

        }

        $this->success('获取成功', $list);
    }

    //所有分类
    public function alls()
    {
        $tree = Tree::instance();
        $list = CategoryModel::field('id,pid,name,image')->order('weigh asc,id asc')->where('isnav', 1)->select();
        $tree->init(collection($list)->toArray(), 'pid');
        $categoryList = $tree->getTreeList($tree->getTreeArray(0), 'name');

        $this->success('获取成功', $categoryList);
    }
}
