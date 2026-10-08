<?php

namespace addons\shop\controller;

use addons\shop\model\Order;
use addons\shop\model\UserCoupon;
use think\Controller;
use think\Db;
use addons\shop\model\OrderGoods;
use addons\shop\model\OrderAction;

/**
 * 定时任务接口
 *
 * 以Crontab方式每分钟定时执行,且只可以Cli方式运行
 * @internal
 */
class Autotask extends Controller
{

    /**
     * 初始化方法,最前且始终执行
     */
    public function _initialize()
    {
        // 只可以以cli方式执行
        if (!$this->request->isCli()) {
            $this->error('Autotask script only work at client!');
        }

        parent::_initialize();

        // 清除错误
        error_reporting(0);

        // 设置永不超时
        set_time_limit(0);
    }

    /**
     * 执行定时任务
     */
    public function index()
    {
        $time = time();
        try {
            $config = get_addon_config('shop');
            //确认收货时间
            $receive = $time - $config['auto_delivery_time'] * 24 * 60 * 60;
            //失效订单
            $order = Order::where(function ($query) use ($time) {
                $query->where('paystate', 0)->where('expiretime', '<=', $time)->where('orderstate', 0);
            })->whereOr(function ($query) use ($receive) {
                $query->where('shippingstate', 1)->where('paystate', 1)->where('shippingtime', '<=', $receive)->where('orderstate', 0);
            })->where('request_id', '')->select();

            //超过设置订单状态为过期
            if ($order) {
                foreach ($order as $item) {
                    // 启动事务
                    Db::startTrans();
                    try {
                        //失效的
                        if (!$item->paystate) {
                            $item->save(['orderstate' => 2]);
                            //库存恢复
                            OrderGoods::setGoodsStocksInc($item->order_sn);
                            //恢复优惠券
                            UserCoupon::resetUserCoupon($item->user_coupon_id, $item->order_sn);
                        } else { //待收货的
                            $item->save(['shippingstate' => 2, 'receivetime' => time()]);
                            OrderAction::push($item->order_sn, '系统', '订单确认收货成功');
                        }
                        // 提交事务
                        Db::commit();
                    } catch (\Exception $e) {
                        // 回滚事务
                        Db::rollback();
                        continue;
                    }
                }
            }
        } catch (\Exception $e) {
            echo $e->getMessage();
        }
        try {
            (new \addons\shop\library\v5\JobRunner())->runAll();
        } catch (\Exception $e) {
            echo $e->getMessage();
        }
        echo "done";
    }

}
