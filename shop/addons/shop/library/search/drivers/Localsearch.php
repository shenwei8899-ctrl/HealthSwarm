<?php

namespace addons\shop\library\search\drivers;

use addons\shop\library\search\AbstractSearch;
use think\Exception;
use think\Model;

/**
 * 本地搜索引擎实现
 */
class Localsearch extends AbstractSearch
{
    /**
     * 初始化
     */
    protected function initialize()
    {
    }

    /**
     * 获取项目名称
     * @return string
     */
    public function getProjectName()
    {
        return 'shop';
    }

    public function getSubProjectName()
    {
        return '';
    }

    /**
     * 获取索引配置
     * @return array
     */
    public function getIndexConfig()
    {
        return [];
    }

    /**
     * 清空索引
     */
    protected function clearIndex()
    {
    }

    /**
     * 批量更新
     * @param array $list
     */
    public function multi(array $list)
    {

    }

    /**
     * 更新文档
     * @param Model $row
     */
    public function update(Model $row)
    {

    }

    /**
     * 删除文档
     * @param Model $row
     */
    public function delete(Model $row)
    {

    }

    /**
     * 搜索
     * @param string $keyword 关键字
     * @param int    $page    页码
     * @param int    $limit   每页数量
     * @param string $sort    排序
     * @param array  $filters 过滤条件
     * @return array
     */
    public function search($keyword, $page = 1, $limit = 20, $sort = '', $filters = [])
    {
        try {
            $sortList = array_keys($this->getSortList());
            $sort = in_array($sort, $sortList) ? $sort : 'default';
            $sort = $sort === 'default' ? 'weigh' : $sort;
            $lastUnderscorePos = strrpos($sort, '_');
            if ($lastUnderscorePos !== false) {
                $prefix = substr($sort, 0, $lastUnderscorePos);
                $suffix = substr($sort, $lastUnderscorePos + 1);
                $suffix = in_array($suffix, ['asc', 'desc']) ? $suffix : 'desc';
                $sortArr = [$prefix, $suffix];
            } else {
                $sortArr = [$sort, 'desc'];
            }

            [$orderby, $orderway] = $sortArr;

            $beginTime = microtime(true);
            $searchList = \addons\shop\model\Goods::where('title|keywords', 'like', "%{$keyword}%")
                ->where($filters)
                ->order($orderby, $orderway)
                ->paginate($limit, false, ['page' => $page]);
            $endTime = microtime(true);
            $list = collection($searchList->items())->toArray();
            foreach ($list as $index => &$item) {
                $item['content'] = $item['content'] ?? $item['description'];
                $item['url'] = $item['fullurl'];
            }
            return [
                'list'  => $list,
                'total' => $searchList->total() ?? 0,
                'time'  => $endTime - $beginTime,
            ];
        } catch (Exception $e) {
            $this->logError($e);
            throw $e;
        }
    }

    /**
     * 获取排序列表
     * @return array
     */
    public function getSortList()
    {
        $list = $this->getConfig('localsearchsortlist');
        return $list ?: ['default' => '默认排序'];
    }
}