<?php

namespace addons\shop\library;

use addons\shop\library\search\AbstractSearch;
use addons\shop\model\SearchLog;
use think\Exception;

/**
 * 搜索类
 */
class Search
{

    /**
     * 获取搜索引擎实例
     * @return AbstractSearch
     * @throws Exception
     */
    public static function getDriver($driver = null)
    {
        $config = get_addon_config('shop');

        $searchType = is_null($driver) ? ($config['searchtype'] ?? 'default') : $driver;

        switch ($searchType) {
            case 'xunsearch':
                return new \addons\shop\library\search\drivers\Xunsearch($config);
            case 'meilisearch':
                return new \addons\shop\library\search\drivers\Meilisearch($config);
            case 'local':
                return new \addons\shop\library\search\drivers\Localsearch($config);
            default:
                throw new Exception("不支持的搜索引擎类型: {$searchType}");
        }
    }

    /**
     * 更新索引记录
     */
    public static function update($row)
    {
        try {
            self::getDriver()->update($row);
        } catch (Exception $e) {
            if (config('app_debug')) {
                throw $e;
            }
        }
    }

    /**
     * 删除索引记录
     */
    public static function del($row)
    {
        try {
            self::getDriver()->delete($row);
        } catch (Exception $e) {
            if (config('app_debug')) {
                throw $e;
            }
        }
    }

    /**
     * 重置索引
     */
    public static function reset()
    {
        try {
            return self::getDriver()->reset();
        } catch (Exception $e) {
            if (config('app_debug')) {
                throw $e;
            }
            return false;
        }
    }

    /**
     * 获取搜索建议关键字
     */
    public static function suggestion($q, $limit = 10)
    {
        return SearchLog::where('status', 'normal')
            ->where('keywords', 'like', "{$q}%")
            ->limit($limit)
            ->column('keywords');
    }

    /**
     * 获取相关搜索关键字
     */
    public static function related($q, $limit = 10)
    {
        return SearchLog::where('status', 'normal')
            ->where('keywords', 'like', "%{$q}%")
            ->where('keywords', "<>", $q)
            ->limit($limit)
            ->column('keywords');
    }

    /**
     * 获取热门搜索关键字
     */
    public static function hot($limit = 10)
    {
        return SearchLog::where('status', 'normal')
            ->order('nums', 'desc')
            ->limit($limit)
            ->column('keywords');
    }

    /**
     * 获取排序方式
     * @return array
     */
    public static function getSortList()
    {
        try {
            $sortList = self::getDriver()->getSortList();
            $result = [];
            foreach ($sortList as $index => $item) {
                $result[$index] = ['title' => $item, 'value' => $index];
            }
        } catch (Exception $e) {
            if (config('app_debug')) {
                throw $e;
            }
            $result = [
                'default' => ['title' => '默认排序', 'value' => 'default']
            ];
        }

        return $result;
    }

    /**
     * 获取搜索列表
     */
    public static function getSearchList($q, $page = null, $pagesize = 20, $sort = '', $filters = [])
    {
        $page = is_null($page) ? request()->get('page/d', 1) : (int)$page;
        $pagesize = (int)$pagesize;

        $list = [];
        $total = 0;
        $time = 0;

        try {
            $result = self::getDriver()->search($q, $page, $pagesize, $sort, $filters);
            $list = $result['list'] ?? [];
            $total = $result['total'] ?? 0;
            $time = $result['time'] ?? 0;
        } catch (Exception $e) {
            if (config('app_debug')) {
                throw $e;
            }
        }

        $options = [
            'path'  => request()->baseUrl(),
            'query' => request()->get(),
        ];

        return \think\paginator\driver\Bootstrap::make($list, $pagesize, $page, $total, false, $options);
    }
}