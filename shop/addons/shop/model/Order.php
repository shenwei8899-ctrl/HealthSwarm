<?php

namespace addons\shop\model;

use think\Db;
use think\Exception;
use think\Model;
use addons\shop\model\Freight;
use addons\shop\model\Carts;
use addons\shop\model\Address;
use Yansongda\Pay\Exceptions\GatewayException;
use addons\epay\library\Service;
use addons\shop\model\OrderAction;
use addons\shop\model\TemplateMsg;
use traits\model\SoftDelete;

/**
 * 模型
 */
class Order extends Model
{
    use SoftDelete;

    // 表名
    protected $name = 'shop_order';
    // 开启自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';
    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    protected $deleteTime = 'deletetime';
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
        return url('shop.order/detail', ['orderid' => $data['order_sn']]);
    }

    public function getPayurlAttr($value, $data)
    {
        return addon_url('shop/payment/index') . '?orderid=' . $data['order_sn'];
    }

    public function getCommenturlAttr($value, $data)
    {
        return url('shop.comment/post') . '?orderid=' . $data['order_sn'];
    }

    /**
     * 获取快递查询URL
     */
    public function getLogisticsurlAttr($value, $data)
    {
        $url = self::$config['logisticstype'] == 'kdnapi' ? url('shop.order/logistics') . '?orderid=' . $data['order_sn'] : "https://www.kuaidi100.com/chaxun?com={$data['expressname']}&nu={$data['expressno']}";
        return $url;
    }

    public function getOrderstateList()
    {
        return ['0' => __('Orderstate 0'), '1' => __('Orderstate 1'), '2' => __('Orderstate 2'), '3' => __('Orderstate 3'), '4' => __('Orderstate 4'), '5' => __('Orderstate 5')];
    }

    public function getShippingstateList()
    {
        return ['0' => __('Shippingstate 0'), '1' => __('Shippingstate 1'), '2' => __('Shippingstate 2'), '3' => __('Shippingstate 3')];
    }

    public function getPaystateList()
    {
        return ['0' => __('Paystate 0'), '1' => __('Paystate 1')];
    }

    public function getOrderstateTextAttr($value, $data)
    {
        $value = $value ? $value : $data['orderstate'];
        $list = $this->getOrderstateList();
        return $list[$value] ?? '';
    }

    public function getShippingstateTextAttr($value, $data)
    {
        $value = $value ? $value : $data['shippingstate'];
        $list = $this->getShippingstateList();
        return $list[$value] ?? '';
    }

    public function getPaystateTextAttr($value, $data)
    {
        $value = $value ? $value : $data['paystate'];
        $list = $this->getPaystateList();
        return $list[$value] ?? '';
    }

    public function getStatusTextAttr($value, $data)
    {
        if ($data['orderstate'] == 0) {
            if ($data['paystate'] == 0) {
                return '待付款';
            }
            if ($data['shippingstate'] == 0) {
                return '待发货';
            } elseif ($data['shippingstate'] == 1) {
                return '待收货';
            } elseif ($data['shippingstate'] == 2) {
                return '待评价';
            }
        } elseif ($data['orderstate'] == 1) {
            return '已取消';
        } elseif ($data['orderstate'] == 2) {
            return '已失效';
        } elseif ($data['orderstate'] == 3) {
            return '已完成';
        } elseif ($data['orderstate'] == 4) {
            return '退货/退款中';
        }
        return '未知';
    }

    //获取订单剩余有效时长
    public function getRemainsecondsAttr($value, $data)
    {
        return max(0, $data['expiretime'] - time());
    }

    public function getMobileAttr($value, $data)
    {
        return substr_replace($value, '****', 3, 4);
    }

    //计算购物车商品
    public static function computeCarts(&$orderInfo, $cart_ids, $user_id, $area_id, $user_coupon_id = '')
    {
        $config = get_addon_config('shop');
        $goodsList = Carts::getGoodsList($cart_ids, $user_id);
        if (empty($goodsList)) {
            throw new \Exception("未找到商品");
        }
        $orderInfo['amount'] = 0;
        $orderInfo['goodsprice'] = 0;
        $orderInfo['shippingfee'] = 0;
        $orderInfo['discount'] = 0;
        $orderItem = [];
        $shippingTemp = [];
        $userCoupon = null;
        //校验领取和是否可使用
        if ($user_coupon_id) {
            $userCouponModel = new UserCoupon();
            $userCoupon = $userCouponModel->checkUserOrUse($user_coupon_id, $user_id);
            $orderInfo['user_coupon_id'] = $user_coupon_id;
        }
        //判断商品库存和状态
        foreach ($goodsList as $item) {
            $goodsItem = [];
            if (empty($item->goods) && empty($item->sku)) {
                throw new \Exception("商品已下架");
            }
            //规格
            if ($item->goods_sku_id && empty($item->sku)) {
                throw new \Exception("商品规格不存在");
            }
            if (!empty($item->sku)) { //规格计算
                if ($item->sku->stocks < $item->nums) {
                    throw new \Exception("有商品库存不足,请返回购物车重新修改");
                }
                $goodsItem['image'] = !empty($item->sku->image) ? $item->sku->image : $item->goods->image;
                $goodsItem['price'] = $item->sku->price;
                $goodsItem['marketprice'] = $item->sku->marketprice;
                $goodsItem['goods_sn'] = $item->sku->goods_sn;
                $amount = bcmul($item->sku->price, $item->nums, 2);
            } else { //商品默认计算
                if ($item->goods->stocks < $item->nums) {
                    throw new \Exception("有商品库存不足,请返回购物车重新修改");
                }
                $goodsItem['image'] = !empty($item->sku->image) ? $item->sku->image : $item->goods->image;
                $goodsItem['price'] = $item->goods->price;
                $goodsItem['marketprice'] = $item->goods->marketprice;
                $goodsItem['goods_sn'] = $item->goods->goods_sn;
                $amount = bcmul($item->goods->price, $item->nums, 2);
            }
            $goodsItem['amount'] = $amount;
            //订单总价
            $orderInfo['amount'] = bcadd($orderInfo['amount'], $amount, 2);
            //商品总价
            $orderInfo['goodsprice'] = bcadd($orderInfo['goodsprice'], $amount, 2);

            $freight_id = $item->goods->freight_id;
            //计算邮费【合并运费模板】
            if (!isset($shippingTemp[$freight_id])) {
                $shippingTemp[$freight_id] = [
                    'nums'   => $item->nums,
                    'weight' => $item->goods->weight,
                    'amount' => $amount
                ];
            } else {
                $shippingTemp[$freight_id] = [
                    'nums'   => bcadd($shippingTemp[$freight_id]['nums'], $item->nums, 2),
                    'weight' => bcadd($shippingTemp[$freight_id]['weight'], $item->goods->weight, 2),
                    'amount' => bcadd($shippingTemp[$freight_id]['amount'], $amount, 2)
                ];
            }
            //创建订单商品数据
            $orderItem[] = array_merge($goodsItem, [
                'order_sn'     => $orderInfo['order_sn'],
                'goods_id'     => $item->goods_id,
                'title'        => $item->goods->title,
                'url'          => $item->goods->url,
                'nums'         => $item->nums,
                'goods_sku_id' => $item->goods_sku_id,
                'attrdata'     => $item->sku_attr,
                'weight'       => $item->goods->weight,
                'category_id'  => $item->goods->category_id,
                'brand_id'     => $item->goods->brand_id,
            ]);
        }
        //按运费模板计算
        foreach ($shippingTemp as $key => $item) {
            $shippingfee = Freight::calculate($key, $area_id, $item['nums'], $item['weight'], $item['amount']);
            $orderInfo['shippingfee'] = bcadd($orderInfo['shippingfee'], $shippingfee, 2);
        }

        //订单总价(含邮费)
        $orderInfo['amount'] = bcadd($orderInfo['goodsprice'], $orderInfo['shippingfee'], 2);

        if (!empty($userCoupon)) {
            //校验优惠券
            $goods_ids = array_column($orderItem, 'goods_id');
            $category_ids = array_column($orderItem, 'category_id');
            $brand_ids = array_column($orderItem, 'brand_id');
            $couponModel = new Coupon();
            $coupon = $couponModel->getCoupon($userCoupon['coupon_id'])
                ->checkCoupon()
                ->checkOpen()
                ->checkUseTime($userCoupon['createtime'])
                ->checkConditionGoods($goods_ids, $user_id, $category_ids, $brand_ids);

            //计算折扣金额，判断是使用不含运费，还是含运费的金额
            $amount = !isset($config['shippingfeecoupon']) || $config['shippingfeecoupon'] == 0 ? $orderInfo['goodsprice'] : $orderInfo['amount'];
            list($new_money, $coupon_money) = $coupon->doBuy($amount);

            //判断优惠金额是否超出总价，超出则直接设定优惠金额为总价
            $orderInfo['discount'] = $coupon_money > $amount ? $amount : $coupon_money;
        }

        //计算订单的应付金额【减去折扣】
        $orderInfo['saleamount'] = max(0, bcsub($orderInfo['amount'], $orderInfo['discount'], 2));
        $orderInfo['discount'] = bcadd($orderInfo['discount'], 0, 2);

        return [
            $orderItem,
            $goodsList,
            $userCoupon
        ];
    }

    /**
     * @ DateTime 2021-05-28
     * @ 创建订单
     * @param int    $address_id
     * @param int    $user_id
     * @param mixed  $cart_ids
     * @param string $memo
     * @return Order|null
     */
    public static function createOrder($address_id, $user_id, $cart_ids, $user_coupon_id, $memo)
    {
        $address = Address::get($address_id);
        if (!$address || $address['user_id'] != $user_id) {
            throw new \Exception("地址未找到");
        }
        $config = get_addon_config('shop');
        $order_sn = date("Ymdhis") . sprintf("%08d", $user_id) . mt_rand(1000, 9999);
        //订单主表
        $orderInfo = [
            'user_id'     => $user_id,
            'order_sn'    => $order_sn,
            'address_id'  => $address->id,
            'province_id' => $address->province_id,
            'city_id'     => $address->city_id,
            'area_id'     => $address->area_id,
            'receiver'    => $address->receiver,
            'mobile'      => $address->getData('mobile'),
            'address'     => $address->address,
            'zipcode'     => $address->zipcode,
            'goodsprice'  => 0, //商品金额 (不含运费)
            'amount'      => 0, //总金额 (含运费)
            'shippingfee' => 0, //运费
            'discount'    => 0, //优惠金额
            'saleamount'  => 0,
            'memo'        => $memo,
            'expiretime'  => time() + $config['order_timeout'], //订单失效
            'status'      => 'normal'
        ];

        //订单详细表
        list($orderItem, $goodsList, $userCoupon) = self::computeCarts($orderInfo, $cart_ids, $user_id, $address->area_id, $user_coupon_id);
        $order = null;
        Db::startTrans();
        try {
            //创建订单
            $order = Order::create($orderInfo, true);
            //减库存
            foreach ($goodsList as $index => $item) {
                if ($item->sku) {
                    $item->sku->setDec('stocks', $item->nums);
                }
                $item->goods->setDec("stocks", $item->nums);
            }
            //计算单个商品折扣后的价格
            $saleamount = bcsub($order['saleamount'], $order['shippingfee'], 2);
            $saleratio = $order['goodsprice'] > 0 ? bcdiv($saleamount, $order['goodsprice'], 10) : 1;
            $saleremains = $saleamount;
            foreach ($orderItem as $index => &$item) {
                if (!isset($orderItem[$index + 1])) {
                    $saleprice = $saleremains;
                } else {
                    $saleprice = $order['discount'] == 0 ? bcmul($item['price'], $item['nums'], 2) : bcmul(bcmul($item['price'], $item['nums'], 2), $saleratio, 2);
                }
                $saleremains = bcsub($saleremains, $saleprice, 2);
                $item['realprice'] = $saleprice;
            }
            unset($item);
            //创建订单商品数据
            foreach ($orderItem as $index => $item) {
                OrderGoods::create($item, true);
            }
            //修改地址使用次数
            $address->setInc('usednums');
            //优惠券已使用
            if (!empty($userCoupon)) {
                $userCoupon->save(['is_used' => 2]);
            }
            //提交事务
            Db::commit();
        } catch (Exception $e) {
            Db::rollback();
            throw new Exception($e->getMessage());
        }
        //清空购物车
        Carts::clear($cart_ids);
        //记录操作
        OrderAction::push($order_sn, '系统', '订单创建成功');
        //订单应付金额为0时直接结算
        if ($order['saleamount'] == 0) {
            self::settle($order->order_sn, 0);
            $order = Order::get($order->id);
        }
        return $order;
    }

    /**
     * @ DateTime 2021-05-31
     * @ 订单信息
     * @param $order_sn
     * @param $user_id
     * @return array|false|\PDOStatement|string|Model
     */
    public static function getDetail($order_sn, $user_id)
    {
        return self::with(['orderGoods'])->where('order_sn', $order_sn)->where('user_id', $user_id)->find();
    }

    /**
     * 判断订单是否失效
     * @param $order_sn
     * @return bool
     */
    public static function isExpired($order_sn)
    {
        $orderInfo = Order::getByOrderSn($order_sn);
        //订单过期
        if (!$orderInfo['orderstate'] && !$orderInfo['paystate'] && time() > $orderInfo['expiretime']) {
            // 启动事务
            Db::startTrans();
            try {
                $orderInfo->save(['orderstate' => 2]);
                //库存恢复
                OrderGoods::setGoodsStocksInc($orderInfo->order_sn);
                //恢复优惠券
                UserCoupon::resetUserCoupon($orderInfo->user_coupon_id, $orderInfo->order_sn);
                // 提交事务
                Db::commit();
            } catch (\Exception $e) {
                // 回滚事务
                Db::rollback();
            }
            return true;
        }
        return false;
    }


    /**
     * @ 支付
     * @param string $orderid
     * @param int    $user_id
     * @param string $paytype
     * @param string $method
     * @param string $openid
     * @param string $notifyurl
     * @param string $returnurl
     * @return \addons\epay\library\Collection|\addons\epay\library\RedirectResponse|\addons\epay\library\Response|null
     * @throws \Exception
     */
    public static function pay($orderid, $user_id, $paytype, $method = 'web', $openid = '', $notifyurl = null, $returnurl = null)
    {
        $request = \think\Request::instance();
        $order = self::getDetail($orderid, $user_id);
        if (!$order) {
            throw new \Exception('订单不存在！');
        }
        if ($order->paystate) {
            throw new \Exception('订单已支付！');
        }
        if ($order->orderstate) {
            throw new \Exception('订单已失效！');
        }
        //支付金额为0，无需支付
        if ($order->saleamount == 0) {
            throw new \Exception('无需支付！');
        }
        $order_sn = $order->order_sn;
        // 启动事务
        Db::startTrans();
        try {
            //支付方式变更
            if (($order['paytype'] == $paytype && $order['method'] != $method)) {
                $order_sn = date("Ymdhis") . sprintf("%08d", $user_id) . mt_rand(1000, 9999);
                //更新电子面单
                $electronics = $order->order_electronics;
                foreach ($electronics as $aftersales) {
                    $aftersales->order_sn = $order_sn;
                    $aftersales->save();
                }
                //更新操作日志
                $orderAction = $order->order_action;
                foreach ($orderAction as $action) {
                    $action->order_sn = $order_sn;
                    $action->save();
                }
                $order->save(['order_sn' => $order_sn]);
                //更新订单明细
                foreach ($order->order_goods as $item) {
                    $item->order_sn = $order_sn;
                    $item->save();
                }
            }
            //更新支付类型和方法
            $order->allowField(true)->save(['paytype' => $paytype, 'method' => $method, 'openid' => $openid]);
            //提交事务
            Db::commit();
        } catch (\Exception $e) {
            // 回滚事务
            Db::rollback();
            throw new \Exception($e->getMessage());
        }
        $response = null;
        $epay = get_addon_info('epay');

        if ($epay && $epay['state']) {
            $notifyurl = $notifyurl ? $notifyurl : $request->root(true) . '/addons/shop/order/epay/type/notify/paytype/' . $paytype;
            $returnurl = $returnurl ? $returnurl : $request->root(true) . '/addons/shop/order/epay/type/return/paytype/' . $paytype . '/order_sn/' . $order_sn;

            //保证取出的金额一致，不一致将导致订单重复错误
            $amount = sprintf("%.2f", $order->saleamount);

            $params = [
                'amount'    => $amount,
                'orderid'   => $order_sn,
                'type'      => $paytype,
                'title'     => "支付{$amount}元",
                'notifyurl' => $notifyurl,
                'returnurl' => $returnurl,
                'method'    => $method,
                'openid'    => $openid
            ];
            try {
                $response = Service::submitOrder($params);
            } catch (GatewayException $e) {
                throw new \Exception(config('app_debug') ? $e->getMessage() : "支付失败，请稍后重试");
            }
        } else {
            throw new \Exception("请在后台安装配置微信支付宝整合插件");
        }
        return $response;
    }


    /**
     * 订单列表
     *
     * @param $param
     * @return \think\Paginator
     */
    public static function tableList($param)
    {
        $pageNum = 15;
        if (!empty($param['num'])) {
            $pageNum = $param['num'];
        }
        return self::with(['orderGoods'])
            ->where(function ($query) use ($param) {
                $query->where('status', 'normal');

                if (!empty($param['user_id'])) {
                    $query->where('user_id', $param['user_id']);
                }

                if (isset($param['orderstate']) && $param['orderstate'] != '') {
                    $query->where('orderstate', $param['orderstate']);
                }
                if (isset($param['shippingstate']) && $param['shippingstate'] != '') {
                    $query->where('shippingstate', $param['shippingstate']);
                }
                if (isset($param['paystate']) && $param['paystate'] != '') {
                    $query->where('paystate', $param['paystate']);
                }
                if (isset($param['q']) && $param['q'] != '') {
                    $query->where('order_sn', 'in', function ($query) use ($param) {
                        return $query->name('shop_order_goods')->where('order_sn|title', 'like', '%' . $param['q'] . '%')->field('order_sn');
                    });
                }
            })
            ->order('createtime desc')->paginate($pageNum, false, ['query' => request()->get()]);
    }


    /**
     * @ DateTime 2021-06-01
     * @ 订单结算
     * @param string $order_sn      订单号
     * @param float  $payamount     支付金额
     * @param string $transactionid 流水号
     * @return bool
     */
    public static function settle($order_sn, $payamount, $transactionid = '')
    {
        $order = self::with(['orderGoods'])->where('order_sn', $order_sn)->find();
        if (!$order || $order->paystate == 1) {
            return false;
        }

        if ($payamount != $order->saleamount) {
            \think\Log::write("[shop][pay][{$order_sn}][订单支付金额不一致]");
            return false;
        }

        // 启动事务
        Db::startTrans();
        try {
            $order->paystate = 1;
            $order->transactionid = $transactionid;
            $order->payamount = $payamount;
            $order->paytime = time();
            $order->paytype = !$order->paytype ? 'system' : $order->paytype;
            $order->method = !$order->method ? 'system' : $order->method;
            $order->save();
            if ($order->payamount == $order->saleamount) {
                //支付完成后,商品销量+1
                foreach ($order->order_goods as $item) {
                    $goods = $item->goods;
                    $sku = $item->sku;
                    if ($goods) {
                        $goods->setInc('sales', $item->nums);
                    }
                    if ($sku) {
                        $sku->setInc('sales', $item->nums);
                    }
                }
            }
            // 提交事务
            Db::commit();
        } catch (\Exception $e) {
            // 回滚事务
            Db::rollback();
            return false;
        }
        //记录操作
        OrderAction::push($order_sn, '系统', '订单支付成功');
        // V5订单在旧商城完成支付后，同步扩展状态、库存占用和计划状态。
        try {
            (new \addons\shop\library\v5\PaymentService())->onPaid(
                $order_sn,
                (int)round($payamount * 100),
                $transactionid
            );
        } catch (\Exception $e) {
            \think\Log::write('[shop][v5][pay-sync][' . $order_sn . ']' . $e->getMessage(), 'error');
        }
        //发送通知
        TemplateMsg::sendTempMsg(0, $order->order_sn);
        return true;
    }

    public function user()
    {
        return $this->belongsTo('User', 'user_id', 'id', [], 'LEFT')->setEagerlyType(0);
    }

    public function address()
    {
        return $this->belongsTo('Address', 'address_id', 'id', [], 'LEFT')->setEagerlyType(0);
    }

    public function orderGoods()
    {
        return $this->hasMany('OrderGoods', 'order_sn', 'order_sn');
    }

    public function orderElectronics()
    {
        return $this->hasMany('OrderElectronics', 'order_sn', 'order_sn');
    }

    public function orderAction()
    {
        return $this->hasMany('OrderAction', 'order_sn', 'order_sn');
    }
}
