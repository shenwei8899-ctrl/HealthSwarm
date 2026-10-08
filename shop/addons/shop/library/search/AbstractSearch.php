<?php

namespace addons\shop\library\search;

use addons\shop\model\Goods;
use think\Exception;
use think\Log;
use think\Model;

/**
 * 搜索引擎抽象类
 */
abstract class AbstractSearch
{
    /**
     * 主键字段名
     * @var string
     */
    protected $_id = '_id';

    /**
     * 子项目字段名
     * @var string
     */
    protected $_project = '_project';

    /**
     * 配置信息
     * @var array
     */
    protected $config = [];

    /**
     * 构造函数
     * @param array $config
     */
    public function __construct(array $config = [])
    {
        $this->config = $config;
        $this->initialize();
    }

    /**
     * 初始化方法
     */
    protected function initialize()
    {
    }

    /**
     * 获取项目名称
     * @return string
     */
    abstract public function getProjectName();

    /**
     * 获取子项目名称
     * @return string
     */
    abstract public function getSubProjectName();

    /**
     * 获取索引配置
     * @return array
     */
    abstract public function getIndexConfig();

    /**
     * 清空索引
     */
    abstract protected function clearIndex();


    /**
     * 是否是子项目
     * @return bool
     */
    protected function isSubProject()
    {
        $subProjectName = $this->getSubProjectName();
        return !empty($subProjectName) && $this->getProjectName() !== $subProjectName;
    }

    /**
     * 获取主键值
     * @param int $id
     * @return string|int
     */
    protected function getPrimaryValue($id)
    {
        return $this->isSubProject() ? $this->getSubProjectName() . '_' . $id : $id;
    }

    /**
     * 添加文档
     * @param Model $row
     */
    public function add(Model $row)
    {
        $this->update($row);
    }

    /**
     * 批量添加文档
     * @param array $list
     */
    abstract public function multi(array $list);

    /**
     * 更新文档
     * @param Model $row
     */
    abstract public function update(Model $row);

    /**
     * 删除文档
     * @param Model $row
     */
    abstract public function delete(Model $row);

    /**
     * 搜索
     * @param string $keyword 关键词
     * @param int    $page    页码
     * @param int    $limit   每页数量
     * @param string $sort    排序
     * @param array  $filters 过滤条件
     * @return array
     */
    abstract public function search($keyword, $page = 1, $limit = 10, $sort = '', $filters = []);

    /**
     * 获取排序列表
     * @return array
     */
    abstract public function getSortList();

    /**
     * 获取配置项
     * @param string $key     键名
     * @param mixed  $default 默认值
     * @return mixed
     */
    protected function getConfig($key, $default = null)
    {
        return $this->config[$key] ?? $default;
    }

    /**
     * 重置索引
     * @return bool
     */
    public function reset()
    {
        try {
            // 清空现有索引
            $this->clearIndex();

            // 批量添加文档
            Goods::where('status', 'normal')
                ->field('id,title,category_id,image,content,marketprice,price,sales,stocks,comments,createtime,views')
                ->chunk(1000, function ($list) {
                    //使用批量写入
                    $this->multi($list);
                });

            return true;
        } catch (Exception $e) {
            Log::record($e->getMessage());
            return false;
        }
    }

    /**
     * 格式化商品数据
     * @param Model $row
     * @return array
     */
    protected function formatData(Model $row)
    {
        $data = $row->toArray();

        //额外追加的_id和_project必须存在
        $data['_id'] = $this->getPrimaryValue($data['id']);
        $data['_project'] = $this->getSubProjectName();

        $data['title'] = htmlspecialchars(strip_tags($row['title'] ?? ''));
        $data['image'] = isset($row['image']) ? cdnurl($row['image'], true) : '';
        $data['content'] = htmlspecialchars(strip_tags($row['content'] ?? ''));
        $data['url'] = $row['fullurl'] ?? '';

        unset($data['taglist']);

        return $data;
    }

    /**
     * 记录错误日志
     * @param Exception $e
     */
    protected function logError(Exception $e)
    {
        Log::record($e->getMessage());
    }
}