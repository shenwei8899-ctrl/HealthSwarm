<?php

namespace addons\shop\model;

use think\Model;
use think\Db;

/**
 * 模型
 */
class OrderGoods extends Model
{

    // 表名
    protected $name = 'shop_order_goods';
    // 开启自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';
    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = '';
    // 追加属性
    protected $append = [
        'url'
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
        $suffix = static::$config['moduleurlsuffix']['goods'] ?? static::$config['urlsuffix'];
        return $this->goods ? $this->goods->url : addon_url('shop/goods/index', ['id' => $data['goods_id']], $suffix);
    }

    public function getFullurlAttr($value, $data)
    {
        $suffix = static::$config['moduleurlsuffix']['goods'] ?? static::$config['urlsuffix'];
        return $this->goods ? $this->goods->fullurl : addon_url('shop/goods/index', ['id' => $data['goods_id']], $suffix, true);
    }

    public function getImageAttr($value, $data)
    {
        $value = $value ?: ($data['image'] ?? '/assets/addons/shop/img/noimage.jpg');
        return cdnurl($value, true);
    }

    //销量增
    public static function setGoodsSalesInc($order_sn)
    {
        $list = (new self)->where('order_sn', $order_sn)->select();
        // 启动事务
        Db::startTrans();
        try {
            foreach ($list as $item) {
                $goods = $item->goods;
                $sku = $item->sku;
                if ($goods) {
                    $goods->setInc('sales', $item->nums);
                }
                if ($sku) {
                    $sku->setInc('sales', $item->nums);
                }
            }
            // 提交事务
            Db::commit();
        } catch (\Exception $e) {
            // 回滚事务
            Db::rollback();
        }
        return true;
    }

    //销量减
    public static function setGoodsSalesDec($order_sn)
    {
        $list = (new self)->where('order_sn', $order_sn)->select();
        // 启动事务
        Db::startTrans();
        try {
            foreach ($list as $item) {
                $goods = $item->goods;
                $sku = $item->sku;
                if ($goods) {
                    $goods->setDec('sales', $item->nums);
                }
                if ($sku) {
                    $sku->setDec('sales', $item->nums);
                }
            }
            // 提交事务
            Db::commit();
        } catch (\Exception $e) {
            // 回滚事务
            Db::rollback();
        }
        return true;
    }

    //库存增
    public static function setGoodsStocksInc($order_sn)
    {
        $list = (new self)->where('order_sn', $order_sn)->select();
        // 启动事务
        Db::startTrans();
        try {
            foreach ($list as $item) {
                $goods = $item->goods;
                $sku = $item->sku;
                if ($sku) {
                    $sku->setInc('stocks', $item->nums);
                }
                if ($goods) {
                    $goods->setInc('stocks', $item->nums);
                }
            }
            // 提交事务
            Db::commit();
        } catch (\Exception $e) {
            // 回滚事务
            Db::rollback();
        }
        return true;
    }

    //库存减
    public static function setGoodsStocksDec($order_sn)
    {
        $list = (new self)->where('order_sn', $order_sn)->select();
        // 启动事务
        Db::startTrans();
        try {
            foreach ($list as $item) {
                $goods = $item->goods;
                $sku = $item->sku;
                if ($sku) {
                    $sku->setDec('stocks', $item->nums);
                }
                if ($goods) {
                    $goods->setDec('stocks', $item->nums);
                }
            }
            // 提交事务
            Db::commit();
        } catch (\Exception $e) {
            // 回滚事务
            Db::rollback();
        }
        return true;
    }

    public function goods()
    {
        return $this->belongsTo('Goods', 'goods_id', 'id', [], 'LEFT')->setEagerlyType(1);
    }

    public function Sku()
    {
        return $this->belongsTo('Sku', 'goods_sku_id', 'id', [], 'LEFT');
    }

    public function Order()
    {
        return $this->hasOne('Order', 'order_sn', 'order_sn', [], 'LEFT');
    }

    /**
     * 获取申请售后订单商品可退运费
     * @return mixed
     * @throws \think\Exception
     */
    public function getAvailableRefundShippingfee()
    {
        $orderGoods = $this;
        $order = $orderGoods->order;
        $shippingfee = 0;

        $config = get_addon_config('shop');
        switch ($config['shippingfeerefund'] ?? '') {
            case 'averageprice':
                //按价格平摊
                $shippingfee = bcmul($order['shippingfee'], bcdiv($orderGoods['realprice'], (bcsub($order['payamount'], $order['shippingfee'], 2)), 6), 2);
                break;
            case 'averagegoods':
                $goodsCount = OrderGoods::where('order_sn', $order->order_sn)->count();
                //按商品数量平摊
                $shippingfee = bcdiv($order->shippingfee, $goodsCount, 2);
                break;
            case 'lastrefund':
                //运费叠加至最后一个退款商品，商品退到最后一件 需要退邮费
                $unrefundGoodsNums = OrderGoods::where('order_sn', $order->order_sn)->where('salestate', 'IN', [0, 6])->count();
                $shippingfee = $unrefundGoodsNums > 1 ? 0 : $order->shippingfee;
                break;
            default:
                break;
        }

        $shippingfee = min($shippingfee, $order['shippingfee']);
        if ($shippingfee > 0) {
            //可退运费不能超过剩余可退运费的金额
            $refundedShippingFee = OrderAftersales::where('order_id', $order->order_sn)->where('status', 'IN', [1, 2])->sum('shippingfee');
            $shippingfee = min(bcsub($order['shippingfee'], $refundedShippingFee, 2), $shippingfee);
        }
        $shippingfee = max(0, $shippingfee);
        return $shippingfee;
    }
}
