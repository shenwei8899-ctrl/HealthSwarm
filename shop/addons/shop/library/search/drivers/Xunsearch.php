<?php

namespace addons\shop\library\search\drivers;

use addons\shop\library\search\AbstractSearch;
use addons\xunsearch\library\Xunsearch as XunsearchClient;
use think\Exception;
use think\Model;

/**
 * Xunsearch搜索引擎实现
 */
class Xunsearch extends AbstractSearch
{

    /**
     * 初始化
     */
    protected function initialize()
    {
        $info = get_addon_info('xunsearch');
        if (!$info || !$info['state']) {
            throw new Exception('Xunsearch插件未安装或未启用');
        }
    }

    /**
     * 获取项目名称
     * @return string
     */
    public function getProjectName()
    {
        return $this->getConfig('xunsearchprojectname', 'shop');
    }

    /**
     * 获取子项目名称
     * @return string
     */
    public function getSubProjectName()
    {
        return $this->getConfig('xunsearchsubprojectname', '');
    }

    /**
     * 获取索引配置
     * @return array
     */
    public function getIndexConfig()
    {
        return [
            [
                'name'   => $this->getProjectName(),
                'title'  => $this->getConfig('sitename', 'shop'),
                'fields' => [
                    ['name' => $this->_id, 'type' => 'id', 'title' => '主键'],
                    ['name' => $this->_project, 'type' => 'string', 'title' => '子项目名称'],

                    ['name' => 'id', 'type' => 'numeric', 'title' => 'ID', 'extra' => 0, 'sortable' => 0],
                    ['name' => 'category_id', 'type' => 'numeric', 'title' => '分类ID', 'index' => 'self', 'extra' => 0],
                    ['name' => 'image', 'type' => 'string', 'title' => '图片', 'extra' => 0, 'sortable' => 0],
                    ['name' => 'title', 'type' => 'title', 'title' => '标题', 'sortable' => 0],
                    ['name' => 'subtitle', 'type' => 'string', 'title' => '子标题', 'sortable' => 0],
                    ['name' => 'keywords', 'type' => 'string', 'title' => '关键字', 'extra' => 0, 'sortable' => 0],
                    ['name' => 'description', 'type' => 'string', 'title' => '描述', 'extra' => 0, 'sortable' => 0],
                    ['name' => 'content', 'type' => 'body', 'title' => '内容', 'extra' => 0, 'sortable' => 0],
                    ['name' => 'url', 'type' => 'string', 'title' => '链接', 'extra' => 0, 'sortable' => 0],
                    ['name' => 'price', 'type' => 'numeric', 'title' => '价格', 'extra' => 0, 'sortable' => 1],
                    ['name' => 'views', 'type' => 'numeric', 'title' => '浏览次数', 'extra' => 0, 'sortable' => 1],
                    ['name' => 'comments', 'type' => 'numeric', 'title' => '评论次数', 'extra' => 0, 'sortable' => 1],
                    ['name' => 'createtime', 'type' => 'numeric', 'title' => '发布时间', 'sortable' => 1],
                ]
            ]
        ];
    }

    /**
     * 清空索引
     */
    protected function clearIndex()
    {
        $index = XunsearchClient::instance($this->getProjectName())->getXS()->getIndex();
        if ($this->isSubProject()) {
            $index->del($this->getSubProjectName(), $this->_project);
        } else {
            //关闭之前的索引，避免中途有关闭的情况
            $index->stopRebuild();
            //清空索引
            $index->clean();
        }
    }

    /**
     * 批量添加索引数据
     * @param array $list
     * @return void
     */
    public function multi(array $list)
    {
        $index = XunsearchClient::instance($this->getProjectName())->getXS()->getIndex();
        // 1. 开启缓冲区
        $index->openBuffer(12);

        foreach ($list as $item) {
            $item = $this->formatData($item);
            $doc = new \XSDocument();
            $doc->setFields($item);

            // 2. 将文档添加到缓冲区
            $index->add($doc);
        }

        // 3. 关闭缓冲区并提交数据
        $index->closeBuffer();
    }

    /**
     * 更新文档
     * @param Model $row
     */
    public function update(Model $row)
    {
        try {
            XunsearchClient::instance($this->getProjectName())->update($this->formatData($row));
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
            XunsearchClient::instance($this->getProjectName())->del($data[$this->_id]);
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
            $fulltext = true;
            $fuzzy = false;
            $synonyms = false;

            if ($sort) {
                $sort = $sort === 'default' || !in_array($sort, array_keys($this->getSortList())) ? 'relevance' : $sort;
            }

            $result = XunsearchClient::instance($this->getProjectName())->search($keyword, $page, $limit, $sort, $fulltext, $fuzzy, $synonyms);

            // 添加高亮
            $list = $result['list'] ?? [];
            foreach ($list as $index => &$item) {
                $item['title'] = $result['highlight']($item['title']);
                $item['content'] = $result['highlight']($item['content']);
            }
            return [
                'list'  => $list ?? [],
                'total' => $result['count'] ?? 0,
                'time'  => $result['microseconds'] ?? 0,
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
        $list = $this->getConfig('xunsearchsortlist');
        return $list ?: ['default' => '默认排序'];
    }
}