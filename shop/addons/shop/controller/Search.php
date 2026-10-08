<?php

namespace addons\shop\controller;

use addons\shop\library\Service;
use addons\shop\model\SearchLog;
use think\Config;
use think\Session;

/**
 * 搜索控制器
 * Class Search
 * @package addons\shop\controller
 */
class Search extends Base
{
    protected $noNeedLogin = '*';
    protected $noNeedRight = '*';

    public function _initialize()
    {
        parent::_initialize();
    }

    /**
     * 搜索首页
     */
    public function index()
    {
        $search = $this->request->request("search", $this->request->request("q", ""));
        $search = mb_substr($search, 0, 100);

        if (!$search) {
            $this->error("关键字不能为空");
        }

        //禁止搜索过滤域名
        if (preg_match("/\.[a-z]{2,}/i", $search)) {
            $this->error("未找到相关记录");
        }

        //限制搜索字符长度
        if (mb_strlen($search) > 15) {
            $this->error("搜索关键字长度超出限制");
        }

        //限制搜索来源
        $referer = $this->request->server('HTTP_REFERER', '');
        if ($referer && ($config['limitsearch'] ?? true) && !Service::isInternalRequest()) {
            $this->error("请求不允许");
        }

        //搜索入库
        $token = $this->request->request("__searchtoken__");
        if ($search && $token && $token == Session::get("__searchtoken__")) {
            $log = SearchLog::getByKeywords($search);
            if ($log) {
                $log->setInc("nums");
            } else {
                SearchLog::create(['keywords' => $search, 'nums' => 1, 'status' => 'hidden']);
            }
        }

        $sort = $this->request->get('sort', 'default');

        // 搜索列表
        $searchList = \addons\shop\library\Search::getSearchList($search, null, 20, $sort);

        // 排序列表
        $sortList = \addons\shop\library\Search::getSortList();
        foreach ($sortList as $key => & $item) {
            $item['active'] = $sort == $key;
            $item['url'] = '?' . http_build_query(['q' => $search, 'sort' => $key]);
        }

        $this->view->assign('keyword', $search);
        $this->view->assign('sort', $sort);
        $this->view->assign('sortList', $sortList);
        $this->view->assign('searchList', $searchList);
        $this->view->assign('relatedList', \addons\shop\library\Search::related($search));
        $this->view->assign('hotList', \addons\shop\library\Search::hot($search));

        Config::set('shop.title', __('Search result'));
        return $this->view->fetch('/search');
    }


    /**
     * 搜索建议
     */
    public function suggestion()
    {
        $q = trim($this->request->get('q', ''));
        $q = mb_substr($q, 0, 100);

        $terms = \addons\shop\library\Search::suggestion($q);
        return json($terms);
    }

}
