<?php

namespace addons\shop\controller;

use addons\shop\model\Block;
use addons\shop\model\Category;
use addons\shop\model\Goods;
use think\Config;

/**
 * 商城首页控制器
 * Class Index
 * @package addons\shop\controller
 */
class Index extends Base
{
    protected $noNeedLogin = '*';
    protected $noNeedRight = '*';

    public function _initialize()
    {
        parent::_initialize();
    }

    /**
     * 首页
     */
    public function index()
    {

        // 判断是否跳转移动端
        $this->checkredirect('index');

        $config = get_addon_config('shop');

        //设置TKD
        Config::set('shop.title', $config['title'] ?: '首页');
        Config::set('shop.keywords', $config['keywords']);
        Config::set('shop.description', $config['description']);

        $this->view->assign('indexCategoryList', Category::getIndexCategoryList());
        $this->view->assign('indexGoodsList', Goods::getIndexGoodsList());
        $this->view->assign('indexFocusList', Block::getBlockListByName('indexfocus'));
        return $this->view->fetch('/index');
    }

}
