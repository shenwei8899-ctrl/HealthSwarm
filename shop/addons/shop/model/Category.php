<?php

namespace addons\shop\model;

use addons\shop\library\Service;
use addons\shop\model\Attribute as AttributeModel;
use think\Cache;
use think\Db;
use think\Model;

/**
 * 分类模型
 */
class Category extends Model
{

    protected $name = 'shop_category';
    // 开启自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';
    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    // 追加属性
    protected $append = [
        'url',
        'flag_text',
    ];

    protected static $config = [];

    protected static $tagCount = 0;

    protected static $parentIds = null;

    protected static $outlinkParentIds = null;

    protected static $navParentIds = null;

    protected static function init()
    {
        $config = get_addon_config('shop');
        self::$config = $config;

        self::afterInsert(function ($row) {
            $row->save(['weigh' => $row['id']]);
        });
    }

    public function setFlagAttr($value, $data)
    {
        return is_array($value) ? implode(',', $value) : $value;
    }

    public function getUrlAttr($value, $data)
    {
        return $this->buildUrl($value, $data);
    }

    public function getFullurlAttr($value, $data)
    {
        return $this->buildUrl($value, $data, true);
    }

    private function buildUrl($value, $data, $domain = false)
    {
        $diyname = isset($data['diyname']) && $data['diyname'] ? $data['diyname'] : $data['id'];
        $cateid = $data['id'] ?? 0;
        $catename = isset($data['diyname']) && $data['diyname'] ? $data['diyname'] : 'all';
        $time = $data['createtime'] ?? time();

        $vars = [
            ':id'       => $data['id'],
            ':diyname'  => $diyname,
            ':category' => $cateid,
            ':catename' => $catename,
            ':cateid'   => $cateid,
            ':year'     => date("Y", $time),
            ':month'    => date("m", $time),
            ':day'      => date("d", $time)
        ];
        if (isset($data['type']) && isset($data['outlink']) && $data['type'] == 'link') {
            return $this->getAttr('outlink');
        }
        $suffix = static::$config['moduleurlsuffix']['category'] ?? static::$config['urlsuffix'];
        return addon_url('shop/category/index', $vars, $suffix, $domain);
    }

    public function getImageAttr($value, $data)
    {
        $value = $value ? $value : self::$config['default_category_img'];
        return cdnurl($value, true);
    }

    public function getFlagList()
    {
        return ['hot' => __('Hot'), 'index' => __('Index'), 'recommend' => __('Recommend')];
    }

    public function getOutlinkAttr($value, $data)
    {
        $indexUrl = $view_replace_str = config('view_replace_str.__PUBLIC__');
        $indexUrl = rtrim($indexUrl, '/');
        return str_replace('__INDEX__', $indexUrl, $value ?: '');
    }

    public function getFlagTextAttr($value, $data)
    {
        $value = $value ?: ($data['flag'] ?? '');
        $valueArr = explode(',', $value);
        $list = $this->getFlagList();
        return implode(',', array_intersect_key($list, array_flip($valueArr)));
    }

    /**
     * 判断是否拥有子列表
     * @param $value
     * @param $data
     * @return bool|mixed
     */
    public function getHasChildAttr($value, $data)
    {
        static $checked = [];
        if (isset($checked[$data['id']])) {
            return $checked[$data['id']];
        }
        if (is_null(self::$parentIds)) {
            self::$parentIds = self::where('pid', '>', 0)->cache(true, null, 'shop')->where('status', 'normal')->column('pid');
        }
        if (self::$parentIds && in_array($data['id'], self::$parentIds)) {
            return true;
        }
        return false;
    }

    /**
     * 判断导航是否拥有子列表
     * @param $value
     * @param $data
     * @return bool|mixed
     */
    public function getHasNavChildAttr($value, $data)
    {
        static $checked = [];
        if (isset($checked[$data['id']])) {
            return $checked[$data['id']];
        }
        if (is_null(self::$navParentIds)) {
            self::$navParentIds = self::where('pid', '>', 0)->cache(true, null, 'shop')->where('status', 'normal')->where('isnav', 1)->column('pid');
        }
        if (self::$navParentIds && in_array($data['id'], self::$navParentIds)) {
            return true;
        }
        return false;
    }

    public static function getIndexCategoryList()
    {
        $categoryList = self::where('status', 'normal')
            ->where('pid', 0)
            ->where("find_in_set('index',\"flag\") > 0")
            ->limit(9)
            ->order('weigh desc,id asc')
            ->cache(false)
            ->select();
        $categoryList = collection($categoryList)->toArray();
        return $categoryList;
    }


    /**
     * 获取面包屑导航
     * @param array $category
     * @param array $goods
     * @param array $page
     * @return array
     */
    public static function getBreadcrumb($category, $goods = [], $page = [])
    {
        $list = [];
        $list[] = ['name' => __('Home'), 'url' => addon_url('shop/index/index', [], false)];
        if ($category) {
            if ($category['pid']) {
                $categoryList = self::where('status', 'normal')
                    ->order('weigh desc,id desc')
                    ->field('id,name,pid,diyname')
                    ->cache(true, null, 'shop')
                    ->select();
                //获取栏目的所有上级栏目
                $parents = \fast\Tree::instance()->init(collection($categoryList)->toArray(), 'pid')->getParents($category['id']);
                foreach ($parents as $k => $v) {
                    $list[] = ['name' => $v['name'], 'url' => $v['url']];
                }
            }
            $list[] = ['name' => $category['name'], 'url' => $category['url']];
        }
        if ($goods) {
            //$list[] = ['name' => $goods['title'], 'url' => $goods['url']];
        }
        if ($page && $category['url'] != $page['url']) {
            $list[] = ['name' => $page['title'], 'url' => $page['url']];
        }
        return $list;
    }

    /**
     * 获取导航分类列表HTML
     * @param       $category
     * @param array $tag
     * @return mixed|string
     */
    public static function getNav($category, $tag = [])
    {
        $config = get_addon_config('shop');
        $condition = empty($tag['condition']) ? '' : $tag['condition'];
        $maxLevel = !isset($tag['maxlevel']) ? 0 : $tag['maxlevel'];

        list($cacheKey, $cacheExpire) = Service::getCacheKeyExpire('nav', $tag);

        $cacheName = 'shop-nav-' . md5(serialize($tag));
        $result = Cache::tag('shop')->get($cacheName);
        if ($result === false) {
            $categoryList = Category::where($condition)
                ->where('status', 'normal')
                ->order('weigh desc,id desc')
                ->cache($cacheKey, $cacheExpire, 'shop')
                ->select();
            $tree = \fast\Tree::instance();
            $tree->init(collection($categoryList)->toArray(), 'pid');
            $result = self::getTreeUl($tree, 0, $category ? $category['id'] : '', '', 1, $maxLevel);
            Cache::tag('shop')->set($cacheName, $result);
        }
        return $result;
    }

    /**
     * 获取栏目所有子级的ID
     * @param mixed $ids      栏目ID或集合ID
     * @param bool  $withself 是否包含自身
     * @return array
     */
    public static function getCategoryChildrenIds($ids, $withself = true)
    {
        $cacheName = 'shop-childrens-' . $ids . '-' . $withself;
        $result = Cache::get($cacheName);
        if ($result === false) {
            $categoryList = Category::where('status', 'normal')
                ->order('weigh desc,id desc')
                ->cache(true, null, 'shop')
                ->select();

            $result = [];
            $tree = \fast\Tree::instance();
            $tree->init(collection($categoryList)->toArray(), 'pid');
            $CategoryIds = is_array($ids) ? $ids : explode(',', $ids);
            foreach ($CategoryIds as $index => $CategoryId) {
                $result = array_merge($result, $tree->getChildrenIds($CategoryId, $withself));
            }
            Cache::set($cacheName, $result);
        }
        return $result;
    }

    /**
     * 获取分类列表
     * @param $tag
     * @return false|\PDOStatement|string|\think\Collection
     */
    public static function getCategoryList($tag)
    {
        $config = get_addon_config('shop');
        $type = empty($tag['type']) ? '' : $tag['type'];
        $typeid = !isset($tag['typeid']) ? '' : $tag['typeid'];
        $condition = empty($tag['condition']) ? '' : $tag['condition'];
        $field = empty($tag['field']) ? '*' : $tag['field'];
        $row = empty($tag['row']) ? 10 : (int)$tag['row'];
        $flag = empty($tag['flag']) ? '' : $tag['flag'];
        $orderby = empty($tag['orderby']) ? 'weigh' : $tag['orderby'];
        $orderway = empty($tag['orderway']) ? 'desc' : strtolower($tag['orderway']);
        $limit = empty($tag['limit']) ? $row : $tag['limit'];
        $orderway = in_array($orderway, ['asc', 'desc']) ? $orderway : 'desc';
        $paginate = !isset($tag['paginate']) ? false : $tag['paginate'];

        list($cacheKey, $cacheExpire) = Service::getCacheKeyExpire('categorylist', $tag);

        $where = ['status' => 'normal'];

        self::$tagCount++;

        if ($type === 'top') {
            //顶级分类
            $where['pid'] = 0;
        } elseif ($type === 'brother') {
            $subQuery = self::where('id', 'in', $typeid)->field('pid')->buildSql();
            //同级
            $where['pid'] = ['exp', Db::raw(' IN ' . '(' . $subQuery . ')')];
        } elseif ($type === 'son') {
            $subQuery = self::where('pid', 'in', $typeid)->field('id')->buildSql();
            //子级
            $where['id'] = ['exp', Db::raw(' IN ' . '(' . $subQuery . ')')];
        } elseif ($type === 'sons') {
            //所有子级
            $where['id'] = ['in', self::getCategoryChildrenIds($typeid)];
        } else {
            if ($typeid !== '') {
                $where['id'] = ['in', $typeid];
            }
        }

        //如果有设置标志,则拆分标志信息并构造condition条件
        if ($flag !== '') {
            if (stripos($flag, '&') !== false) {
                $arr = [];
                foreach (explode('&', $flag) as $k => $v) {
                    $arr[] = "FIND_IN_SET('{$v}', flag)";
                }
                if ($arr) {
                    $condition .= "(" . implode(' AND ', $arr) . ")";
                }
            } else {
                $condition .= ($condition ? ' AND ' : '');
                $arr = [];
                foreach (explode(',', str_replace('|', ',', $flag)) as $k => $v) {
                    $arr[] = "FIND_IN_SET('{$v}', flag)";
                }
                if ($arr) {
                    $condition .= "(" . implode(' OR ', $arr) . ")";
                }
            }
        }

        $order = $orderby == 'rand' ? Db::raw('rand()') : (preg_match("/\,|\s/", $orderby) ? $orderby : "{$orderby} {$orderway}");
        $order = $orderby == 'weigh' ? $order . ',id DESC' : $order;

        $CategoryModel = self::where($where)
            ->where($condition)
            ->field($field)
            ->orderRaw($order);
        if ($paginate) {
            $paginateArr = explode(',', $paginate);
            $listRows = is_numeric($paginate) ? $paginate : (is_numeric($paginateArr[0]) ? $paginateArr[0] : $row);
            $config = [];
            $config['var_page'] = $paginateArr[2] ?? 'cpage' . self::$tagCount;
            $config['path'] = $paginateArr[3] ?? '';
            $config['fragment'] = $paginateArr[4] ?? '';
            $config['query'] = request()->get();
            $list = $CategoryModel->paginate($listRows, ($paginateArr[1] ?? false), $config);
        } else {
            $list = $CategoryModel->limit($limit)->cache($cacheKey, $cacheExpire, 'shop')->select();
        }

        return $list;
    }

    public static function getFilterList($category, $filter, $params = [], $multiple = false)
    {
        $filterList = [];
        $attributeList = (new AttributeModel())->with(['AttributeValue'])->where('category_id', $category['id'])->where('is_search', 1)->select();

        foreach ($attributeList as $k => $v) {
            $v['title'] = $v['name'];
            $v['name'] = 'f_' . $v['id'];
            $content = [];
            $valueList = ['' => __('All')];
            foreach ($v['attribute_value'] as $index => $item) {
                $valueList[$item['id']] = $item['name'];
            }
            foreach ($valueList as $m => $n) {
                $filterArr = isset($filter[$v['name']]) && $filter[$v['name']] !== '' ? ($multiple ? explode(',', $filter[$v['name']]) : [$filter[$v['name']]]) : [];
                $active = ($m === '' && !$filterArr) || ($m !== '' && in_array($m, $filterArr)) ? true : false;
                if ($active) {
                    $current = implode(',', array_diff($filterArr, [$m]));
                } else {
                    $current = $multiple ? implode(',', array_merge($filterArr, [$m])) : $m;
                }
                $prepare = $m === '' ? array_diff_key($filter, [$v['name'] => $m]) : array_merge($filter, [$v['name'] => $current]);
                $url = '?' . str_replace(['%2C', '%3B'], [',', ';'], http_build_query(array_merge($prepare, array_intersect_key($params, array_flip(['orderby', 'orderway', 'multiple'])))));
                $content[] = ['value' => $m, 'title' => $n, 'active' => $active, 'url' => $url];
            }

            $filterList[] = [
                'name'   => $v['name'],
                'title'  => $v['title'],
                'values' => $content,
            ];
        }
        foreach ($filter as $index => &$item) {
            $item = is_array($item) ? $item : explode(',', str_replace(';', ',', $item));
        }
        return $filterList;
    }

    public static function getCategorySubList($id)
    {
        return self::where('pid', $id)->where('status', 'normal')->order('weigh desc,id asc')->select();
    }

    public static function getCategorySubIds($id)
    {
        return self::where('pid', $id)->where('status', 'normal')->column('id');
    }

    public function Goods()
    {
        return $this->hasMany('Goods', 'category_id', 'id');
    }

}
