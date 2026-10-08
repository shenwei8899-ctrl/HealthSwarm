<?php

namespace addons\shop\model;

use addons\shop\library\Service;
use fast\Tree;
use think\Cache;
use think\Db;
use think\Model;

/**
 * 模型
 */
class Menu extends Model
{

    // 表名
    protected $name = 'shop_menu';
    // 开启自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';
    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = '';
    // 追加属性
    protected $append = [
    ];

    protected static $tagCount = 0;

    protected static $parentIds = null;

    protected static $outlinkParentIds = null;

    protected static $navParentIds = null;

    /**
     * 获取分类列表
     * @param $params
     * @return false|\PDOStatement|string|\think\Collection
     */
    public static function getMenuList($params)
    {
        $config = get_addon_config('shop');
        $type = empty($params['type']) ? '' : $params['type'];
        $typeid = !isset($params['typeid']) ? '' : $params['typeid'];
        $condition = empty($params['condition']) ? '' : $params['condition'];
        $field = empty($params['field']) ? '*' : $params['field'];
        $row = empty($params['row']) ? 10 : (int)$params['row'];
        $flag = empty($params['flag']) ? '' : $params['flag'];
        $orderby = empty($params['orderby']) ? 'weigh' : $params['orderby'];
        $orderway = empty($params['orderway']) ? 'desc' : strtolower($params['orderway']);
        $limit = empty($params['limit']) ? $row : $params['limit'];
        $orderway = in_array($orderway, ['asc', 'desc']) ? $orderway : 'desc';
        $paginate = !isset($params['paginate']) ? false : $params['paginate'];

        list($cacheKey, $cacheExpire) = Service::getCacheKeyExpire('menulist', $params);

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
            $where['id'] = ['in', self::getMenuChildrenIds($typeid)];
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

        $MenuModel = self::where($where)
            ->where($condition)
            ->field($field)
            ->orderRaw($order);
        if ($paginate) {
            $paginateArr = explode(',', $paginate);
            $listRows = is_numeric($paginate) ? $paginate : (is_numeric($paginateArr[0]) ? $paginateArr[0] : $row);
            $config = [];
            $config['var_page'] = $paginateArr[2] ?? 'mpage' . self::$tagCount;
            $config['path'] = $paginateArr[3] ?? '';
            $config['fragment'] = $paginateArr[4] ?? '';
            $config['query'] = request()->get();
            $list = $MenuModel->paginate($listRows, ($paginateArr[1] ?? false), $config);
        } else {
            $list = $MenuModel->limit($limit)->cache($cacheKey, $cacheExpire, 'shop')->select();
        }

        return $list;
    }

    /**
     * 获取菜单列表HTML
     * @param array $params
     * @return mixed|string
     */
    public static function getMenu($params = [])
    {
        $config = get_addon_config('shop');
        $condition = empty($params['condition']) ? '' : $params['condition'];
        $maxLevel = !isset($params['maxlevel']) ? 0 : $params['maxlevel'];

        list($cacheKey, $cacheExpire) = Service::getCacheKeyExpire('menu', $params);

        $menuList = Menu::where($condition)
            ->where('status', 'normal')
            ->field('id,pid,name,url')
            ->order('weigh desc,id desc')
            ->cache($cacheKey, $cacheExpire, 'shop')
            ->select();
        $tree = \fast\Tree::instance();
        $tree->init(collection($menuList)->toArray(), 'pid');
        $result = self::getTreeUl($tree, 0, '', '', 1, $maxLevel);

        return $result;
    }

    public static function getTreeUl($tree, $myid, $selectedids = '', $disabledids = '', $level = 1, $maxlevel = 0)
    {
        $str = '';
        $childs = $tree->getChild($myid);
        if ($childs) {
            foreach ($childs as $value) {
                $id = $value['id'];
                unset($value['child']);
                $selected = $selectedids && in_array($id, (is_array($selectedids) ? $selectedids : explode(',', $selectedids))) ? 'active' : '';
                $disabled = $disabledids && in_array($id, (is_array($disabledids) ? $disabledids : explode(',', $disabledids))) ? 'disabled' : '';
                if (!$selected && request()->url(substr($value['url'], 0, 1) !== '/' ? true : null) == $value['url']) {
                    $selected = 'active';
                }
                $value = array_merge($value, array('selected' => $selected, 'disabled' => $disabled));
                $value = array_combine(array_map(function ($k) {
                    return '@' . $k;
                }, array_keys($value)), $value);
                $itemtpl = '<li class="@dropdown @selected" value=@id @disabled><a data-toggle="@toggle" data-target="#" href="@url">@name@caret</a> @childlist</li>';
                $nstr = strtr($itemtpl, $value);
                $childlist = '';
                if (!$maxlevel || $level < $maxlevel) {
                    $childdata = self::getTreeUl($tree, $id, $selectedids, $disabledids, $level + 1, $maxlevel);
                    $childlist = $childdata ? '<ul class="dropdown-menu" role="menu">' . $childdata . '</ul>' : "";
                }
                $str .= strtr($nstr, [
                    '@childlist' => $childlist,
                    '@caret'     => $childlist ? ($level == 1 ? '<span class="indicator"><i class="fa fa-angle-down"></i></span>' : '<span class="indicator"><i class="fa fa-angle-right"></i></span>') : '',
                    '@dropdown'  => $childlist ? ($level == 1 ? 'dropdown' : 'dropdown-submenu') : '',
                    '@toggle'    => $childlist ? 'dropdown' : ''
                ]);
            }
        }
        return $str;
    }
}
