<?php

namespace addons\shop\model;

use addons\shop\library\Service;
use app\common\exception\CommentException;
use app\common\library\Auth;
use fast\Tree;
use think\Exception;
use think\Model;
use think\Validate;

/**
 * 模型
 */
class Comment extends Model
{

    // 表名
    protected $name = 'shop_comment';
    // 开启自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';
    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    // 追加属性
    protected $append = [];

    public function getImagesAttr($value, $data)
    {
        $imagesArr = explode(',', $data['images'] ?? '');
        foreach ($imagesArr as $index => &$item) {
            $item && $item = cdnurl($item, true);
        }
        return array_filter($imagesArr);
    }

    public function setImagesAttr($value, $data)
    {
        return is_array($value) ? implode(',', $value) : $value;
    }

    public function User()
    {
        return $this->belongsTo('User', 'user_id', 'id', [], 'LEFT');
    }

    public function Manage()
    {
        return $this->belongsTo('\app\admin\model\Admin', 'user_id', 'id', [], 'LEFT');
    }

    public function Goods()
    {
        return $this->belongsTo('Goods', 'goods_id', 'id', [], 'LEFT');
    }

    /**
     * 获取评论列表
     */
    public static function getCommentList($params)
    {
        $goods_id = empty($params['goods_id']) ? 0 : $params['goods_id'];
        $pid = empty($params['pid']) ? 0 : $params['pid'];
        $condition = empty($params['condition']) ? '' : $params['condition'];
        $fragment = empty($params['fragment']) ? 'comments' : $params['fragment'];
        $row = empty($params['row']) ? 10 : (int)$params['row'];
        $orderby = empty($params['orderby']) ? 'nums' : $params['orderby'];
        $orderway = empty($params['orderway']) ? 'desc' : strtolower($params['orderway']);
        $pagesize = empty($params['pagesize']) ? $row : $params['pagesize'];
        $page = empty($params['page']) ? 1 : (int)$params['page'];
        $orderway = in_array($orderway, ['asc', 'desc']) ? $orderway : 'desc';

        $where = [
            'status' => 'normal'
        ];
        if ($goods_id !== '') {
            $where['goods_id'] = $goods_id;
        }
        if ($pid !== '') {
            $where['pid'] = $pid;
        }
        $order = $orderby == 'rand' ? 'rand()' : (in_array($orderby, ['pid', 'id', 'createtime', 'updatetime']) ? "{$orderby} {$orderway}" : "id {$orderway}");
        $config = [
            'type'     => '\\addons\\shop\\library\\Bootstrap',
            'var_page' => 'cp',
            'fragment' => $fragment,
            'page'     => $page
        ];
        $list = self::with(['user', 'reply' => function ($query) {
            $query->with(['manage' => function ($user) {
                $user->field('id,nickname');
            }]);
        }])
            ->where($where)
            ->where($condition)
            ->order($order)
            ->paginate($pagesize, false, $config);
        return $list;
    }

    //好评度
    public static function degree($goods_id)
    {
        $total = self::where('goods_id', $goods_id)->where('pid', 0)->where('status', 'normal')->sum('star');
        $favorable = self::where('goods_id', $goods_id)->where('pid', 0)->where('status', 'normal')->where('star', '>', 3)->sum('star');
        if (!$total || !$favorable) {
            return 100;
        }
        return bcmul(bcdiv($favorable, $total, 2), 100);
    }

    public function reply()
    {
        return $this->hasMany('Comment', 'pid', 'id')->where('status', 'normal');
    }
}
