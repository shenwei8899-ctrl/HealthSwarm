<?php

namespace addons\shop\library\search\drivers;

use addons\meilisearch\library\SearchService;
use addons\meilisearch\library\MeilisearchClient;
use addons\shop\library\search\AbstractSearch;
use think\Exception;
use think\Model;

/**
 * Meilisearch搜索引擎实现
 */
class Meilisearch extends AbstractSearch
{
    /**
     * 客户端实例
     * @var MeilisearchClient
     */
    protected $client;

    /**
     * 初始化
     */
    protected function initialize()
    {
        $info = get_addon_info('meilisearch');
        if (!$info || !$info['state']) {
            throw new Exception('Meilisearch插件未安装或未启用');
        }
        $this->client = MeilisearchClient::getInstance();
    }

    /**
     * 获取项目名称
     * @return string
     */
    public function getProjectName()
    {
        return $this->getConfig('meilisearchprojectname', 'shop');
    }

    /**
     * 获取子项目名称
     * @return string
     */
    public function getSubProjectName()
    {
        return $this->getConfig('meilisearchsubprojectname', '');
    }

    /**
     * 获取索引配置
     * @return array
     */
    public function getIndexConfig()
    {
        return [
            [
                'name'           => $this->getProjectName(),
                'title'          => $this->getConfig('sitename', '商城'),
                'filter_options' => [],
                'index_config'   => [
                    'primaryKey'         => $this->_id,
                    'sortableAttributes' => ['relevance', 'createtime_desc', 'createtime_asc']
                ]
            ]
        ];
    }

    /**
     * 清空索引
     */
    protected function clearIndex()
    {
        if ($this->isSubProject()) {
            $this->client->getIndex($this->getProjectName())
                ->deleteDocuments(['filter' => $this->_project . '=' . $this->getSubProjectName()]);
        } else {
            $this->client->getIndex($this->getProjectName())
                ->deleteAllDocuments();
        }
    }

    /**
     * 批量更新索引
     * @param array $list
     */
    public function multi(array $list)
    {
        foreach ($list as $index => &$item) {
            $item = $this->formatData($item);
        }

        try {
            $this->client->getIndex($this->getProjectName())->addDocuments($list, $this->_id);
        } catch (Exception $e) {
            $this->logError($e);
            throw $e;
        }
    }

    /**
     * 更新文档
     * @param Model $row
     */
    public function update(Model $row)
    {
        try {
            $data = $this->formatData($row);
            unset($data['taglist']);
            $this->client->getIndex($this->getProjectName())->addDocuments($data, $this->_id);
        } catch (Exception $e) {
            $this->logError($e);
            throw $e;
        }
    }

    /**
     * 删除文档
     * @param Model $row
     */
    public function delete(Model $row)
    {
        try {
            $data = $this->formatData($row);
            $this->client->getIndex($this->getProjectName())->deleteDocument($data[$this->_id]);
        } catch (Exception $e) {
            $this->logError($e);
            throw $e;
        }
    }

    /**
     * 搜索
     * @param string $keyword 关键词
     * @param int    $page    页码
     * @param int    $limit   每页数量
     * @param string $sort    排序
     * @param array  $filters 过滤条件
     * @return array
     */
    public function search($keyword, $page = 1, $limit = 10, $sort = '', $filters = [])
    {
        try {
            $options = [
                'offset'                => ($page - 1) * $limit,
                'limit'                 => $limit,
                'attributesToHighlight' => ['title', 'content'],
            ];

            // 处理子项目过滤
            if ($this->isSubProject()) {
                $filters = array_merge(['_project' => $this->getSubProjectName()], $filters);
            }

            // 处理排序
            if ($sort) {
                $sort = $sort === 'default' ? 'relevance' : $sort;
                if (!in_array($sort, ['default', 'relevance']) && in_array($sort, $this->getSortList())) {
                    $options['sort'] = [$sort];
                }
            }

            $searchService = new SearchService($this->getProjectName());
            $result = $searchService->advancedSearch($keyword, $filters, $options);

            return [
                'list'  => $result['hits'] ?? [],
                'total' => $result['total'] ?? 0,
                'time'  => $result['processingTime'] ?? 0,
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
        $list = $this->getConfig('meilisearchsortlist');
        return $list ?: ['default' => '默认排序'];
    }
}