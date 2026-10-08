<?php

namespace addons\shop\model;

use think\Cookie;
use think\Model;

/**
 * 模型
 */
class Carts extends Model
{

    // 表名
    protected $name = 'shop_carts';
    // 开启自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';
    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = '';
    // 追加属性
    protected $append = [];

    /**
     * @ DateTime 2021-05-31
     * @ 获取购物车商品列表
     * @param string  $ids
     * @param integer $user_id
     * @param integer $sceneval
     * @return array
     */
    public static function getGoodsList($ids, $user_id, $sceneval = '')
    {
        return (new self())->field("c.*,string_agg(sp.name || ':' || sv.value, ',' ORDER BY sp.id ASC) sku_attr")
            ->with([
                'Goods' => function ($query) {
                    $query->where('status', 'normal');
                },
                'Sku'
            ])
            ->alias('c')
            ->join('shop_goods_sku sku', 'c.goods_sku_id=sku.id', 'LEFT')
            ->join('shop_goods_sku_spec p', "find_in_set(p.id::text, sku.sku_id) > 0", 'LEFT')
            ->join('shop_spec sp', 'sp.id=p.spec_id', 'LEFT')
            ->join('shop_spec_value sv', 'sv.id=p.spec_value_id', 'LEFT')
            ->where(function ($query) use ($ids, $sceneval) {
                if ($ids) {
                    $query->where('c.id', 'in', $ids);
                }
                if ($sceneval) {
                    $query->where('c.sceneval', $sceneval);
                }
            })
            ->where('c.user_id', $user_id)
            ->order('c.createtime desc')
            ->group('c.id')
            ->select();
    }

    /**
     * 添加商品到购物车
     *
     * @param string $goods_id     商品ID
     * @param string $goods_sku_id 商品SKUID
     * @param int    $nums         数量
     * @param int    $user_id      会员ID
     * @param int    $sceneval     1是加入购物车 2是立即购买
     * @return mixed
     */
    public static function push($goods_id, $goods_sku_id, $nums = 1, $user_id = 0, $sceneval = 1)
    {

        $row = (new self)->where('goods_id', $goods_id)
            ->where('goods_sku_id', $goods_sku_id)
            ->where('user_id', $user_id)
            ->where('sceneval', $sceneval)
            ->find();
        //已存在，数量加
        if ($row) {
            if ($sceneval == 2) {
                $row->nums = $nums;
                $row->save();
            } else {
                $row->setInc('nums', $nums);
            }
        } else {
            $row = (new self);
            $row->save([
                'goods_id'     => $goods_id,
                'goods_sku_id' => $goods_sku_id,
                'user_id'      => $user_id,
                'sceneval'     => $sceneval,
                'nums'         => $nums
            ]);
        }
        return $row->id;
    }

    /**
     * 清空购物车
     */
    public static function clear($cart_ids)
    {
        self::where('id', 'IN', $cart_ids)->delete();
    }


    public function Goods()
    {
        return $this->belongsTo('Goods', 'goods_id', 'id', [], 'LEFT');
    }

    public function Sku()
    {
        return $this->belongsTo('Sku', 'goods_sku_id', 'id', [], 'LEFT');
    }
}
