<?php

namespace addons\shop\model;

use addons\shop\library\Service;
use think\Cache;
use think\Db;
use think\Model;
use traits\model\SoftDelete;

/**
 * 商品模型
 */
class Goods extends Model
{

    use SoftDelete;

    // 表名
    protected $name = 'shop_goods';
    // 开启自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';
    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    protected $deleteTime = 'deletetime';
    // 追加属性
    protected $append = [
        'url',
        'fullurl',
    ];
    protected static $config = [];

    protected static $tagCount = 0;

    protected static function init()
    {
        $config = get_addon_config('shop');
        self::$config = $config;
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
        $catename = isset($this->category) && $this->category ? $this->category->diyname : 'all';
        $cateid = isset($this->category) && $this->category ? $this->category->id : 0;
        $time = $data['publishtime'] ?? time();
        $vars = [
            ':id'       => $data['id'],
            ':diyname'  => $diyname,
            ':category' => $cateid,
            ':catename' => $catename,
            ':cateid'   => $cateid,
            ':year'     => date("Y", $time),
            ':month'    => date("m", $time),
            ':day'      => date("d", $time),
        ];
        $suffix = static::$config['moduleurlsuffix']['goods'] ?? static::$config['urlsuffix'];
        return addon_url('shop/goods/index', $vars, $suffix, $domain);
    }

    public function getImageAttr($value, $data)
    {
        $value = $value ?: self::$config['default_goods_img'];
        return cdnurl($value, true);
    }

    public function getImagesAttr($value, $data)
    {
        $images = explode(',', $data['images'] ?? '');
        foreach ($images as $index => &$image) {
            $image && $image = cdnurl($image, true);
        }
        return array_filter($images);
    }

    public function setImagesAttr($value, $data)
    {
        return is_array($value) ? implode(',', $value) : $value;
    }

    public function getContentAttr($value, $data)
    {
        //组装卡片信息
        return \addons\shop\library\Service::formatSourceTpl($value);
    }

    public static function getIndexGoodsList()
    {
        return self::where('status', 'normal')
            ->where("find_in_set('recommend',\"flag\") > 0")
            ->order('weigh desc')
            ->limit(12)
            ->cache(false)
            ->select();
    }

    /**
     * 获取SQL查询结果
     */
    public static function getQueryList($params)
    {
        $config = get_addon_config('shop');
        $sql = $params['sql'] ?? '';
        $bind = isset($params['bind']) ? explode(',', $params['bind']) : [];
        list($cacheKey, $cacheExpire) = Service::getCacheKeyExpire('sql', $params);
        $list = Cache::tag('shop')->get($cacheKey);
        if (!$list) {
            $list = Db::query($sql, $bind);
            Cache::tag('shop')->set($cacheKey, $list, $cacheExpire);
        }
        return $list;
    }

    public static function refreshStar($goods_id)
    {
        $goods = self::get($goods_id);
        if ($goods) {
            $one = Comment::where('goods_id', $goods_id)->field("COUNT(*) as nums,SUM(star) as amount")->find();
            if ($one) {
                $goods->star = floor($one['amount'] / $one['nums']);
                $goods->save();
            }
        }
    }


    /**
     * 获取商品列表
     * @param $params
     * @return array|false|\PDOStatement|string|\think\Collection
     */
    public static function getGoodsList($params)
    {
        $config = get_addon_config('shop');
        $type = empty($params['type']) ? '' : $params['type'];
        $category = !isset($params['category']) ? '' : $params['category'];
        $condition = empty($params['condition']) ? '' : $params['condition'];
        $field = empty($params['field']) ? '*' : $params['field'];
        $flag = empty($params['flag']) ? '' : $params['flag'];
        $row = empty($params['row']) ? 10 : (int)$params['row'];
        $orderby = empty($params['orderby']) ? 'createtime' : $params['orderby'];
        $orderway = empty($params['orderway']) ? 'desc' : strtolower($params['orderway']);
        $limit = empty($params['limit']) ? $row : $params['limit'];
        $orderway = in_array($orderway, ['asc', 'desc']) ? $orderway : 'desc';
        $paginate = !isset($params['paginate']) ? false : $params['paginate'];
        $page = !isset($params['page']) ? 1 : (int)$params['page'];
        $with = !isset($params['with']) ? 'category' : $params['with'];

        list($cacheKey, $cacheExpire) = Service::getCacheKeyExpire('goodslist', $params);

        $where = ['status' => 'normal'];

        $where['deletetime'] = ['exp', Db::raw('IS NULL')];

        self::$tagCount++;

        $goodsModel = self::with($with)->alias('a');
        if ($category !== '') {
            if ($type === 'son') {
                $subQuery = Category::where('parent_id', 'in', $category)->field('id')->buildSql();
                //子级
                $where['category_id'] = ['exp', Db::raw(' IN ' . '(' . $subQuery . ')')];
            } elseif ($type === 'sons') {
                //所有子级
                $where['category_id'] = ['in', Category::getCategoryChildrenIds($category)];
            } else {
                $where['category_id'] = ['in', $category];
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

        $modelInfo = null;
        $prefix = config('database.prefix');
        $goodsModel
            ->where($where)
            ->where($condition)
            ->field($field, false, $prefix . "shop_goods", "a")
            ->orderRaw($order);

        if ($paginate) {
            $paginateArr = explode(',', $paginate);
            $listRows = is_numeric($paginate) ? $paginate : (is_numeric($paginateArr[0]) ? $paginateArr[0] : $row);
            $config = [];
            $config['var_page'] = $paginateArr[2] ?? (isset($params['page']) ? 'page' : 'apage' . self::$tagCount);
            $config['path'] = $paginateArr[3] ?? '';
            $config['fragment'] = $paginateArr[4] ?? '';
            $config['query'] = request()->get();
            $config['page'] = $page;
            $list = $goodsModel->paginate($listRows, ($paginateArr[1] ?? false), $config);
        } else {
            $list = $goodsModel->limit($limit)->cache($cacheKey, $cacheExpire, 'shop')->select();
        }

        return $list;
    }


    public function Category()
    {
        return $this->belongsTo('Category', 'category_id', 'id');
    }

    public function Sku()
    {
        return $this->hasMany('Sku', 'goods_id', 'id');
    }

    public function Comment()
    {
        return $this->hasMany('Comment', 'goods_id', 'id');
    }
}
