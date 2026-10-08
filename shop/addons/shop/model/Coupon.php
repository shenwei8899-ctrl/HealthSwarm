<?php

namespace addons\shop\model;

use think\Model;
use addons\shop\model\UserCoupon;
use addons\shop\library\coupon\ToCalculate;
use addons\shop\library\coupon\Discount;
use addons\shop\library\coupon\FullReduction;
use addons\shop\model\Order;
use addons\shop\library\IntCode;

class Coupon extends Model
{

    // 表名
    protected $name = 'shop_coupon';

    // 自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';

    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    protected $deleteTime = false;

    // 追加属性
    protected $append = [
        'condition_text',
        'result_text',
        'is_open_text',
        'url',
        'use_times_text',
        'receive_times',
    ];

    protected static $config = [];

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
        $vars = [
            ':coupon' => $data['id']
        ];
        $suffix = static::$config['moduleurlsuffix']['coupon'] ?? static::$config['urlsuffix'];
        return addon_url('shop/coupon/show', $vars, $suffix, $domain);
    }

    public function getReceiveTimesAttr($value, $data)
    {
        return date("Y-m-d H:i:s", $data['begintime']) . ' - ' . date("Y-m-d H:i:s", $data['endtime']);
    }

    public function getConditionList()
    {
        return ['0' => __('Condition 0'), '1' => __('Condition 1'), '2' => __('Condition 2'), '3' => __('Condition 3'), '4' => __('Condition 4')];
    }

    public function getResultList()
    {
        return ['0' => __('Result 0'), '1' => __('Result 1')];
    }

    public function getIsOpenList()
    {
        return ['0' => __('Is_open 0'), '1' => __('Is_open 1')];
    }


    public function getConditionTextAttr($value, $data)
    {
        $value = $value ?: ($data['condition'] ?? '');
        $list = $this->getConditionList();
        return $list[$value] ?? '';
    }


    public function getResultTextAttr($value, $data)
    {
        $value = $value ?: ($data['result'] ?? '');
        $list = $this->getResultList();
        return $list[$value] ?? '';
    }


    public function getIsOpenTextAttr($value, $data)
    {
        $value = $value ?: ($data['is_open'] ?? '');
        $list = $this->getIsOpenList();
        return $list[$value] ?? '';
    }

    public function getUseTimesTextAttr($value, $data)
    {
        $value = $value ?: ($data['use_times'] ?? '');
        return preg_replace('/\s\d{2}\:\d{2}\:\d{2}/i', '', $value);
    }

    public function getResultDataAttr($value)
    {
        return (array)json_decode($value, true);
    }

    //购买计算:0=订单满xx打x折,1=订单满xx减x元
    public function doBuy($money)
    {
        $obj = null;
        //判断是那种计算方式
        switch ((int)$this->getData('result')) {
            case 0: //订单满xx打x折
                $obj = new ToCalculate(new Discount());
                break;
            case 1: //订单满xx减x元
                $obj = new ToCalculate(new FullReduction());
                break;
        }
        if (!$obj) {
            throw new \Exception('未找到优惠方式');
        }
        return $obj->doing($this->getData('result_data'), $money);
    }

    /**
     * @ 获取优惠券
     * @param $id
     * @return array|bool|Model|\PDOStatement|string|null
     */
    public static function getCouponInfo($id)
    {
        if (!is_numeric($id)) {
            $id = IntCode::decode($id);
        }
        $row = self::where('id', $id)->where('is_open', 1)->find();
        if (!empty($row)) {
            $row->id = IntCode::encode($row->id);
            $rd = $row->result_data;
            $row->result_tips = '订单满' . $rd['money'] . ($row->result ? '减' : '打') . $rd['number'] . ($row->result ? '元' : '折');
            if ($row->mode == 'fixation') {
                $row->expire_time = "领取后 {$row['use_times']} 天内有效";
            } else {
                $row->expire_time = "领取后有效时间为:" . $row['use_times_text'];
            }
        }
        return $row;
    }

    /**
     * 获取优惠券
     * @param $coupon_id
     * @return array|false|\PDOStatement|string|Model|$this
     */
    public function getCoupon($coupon_id)
    {
        return $this->where('id', $coupon_id)->where('is_open', 1)->find();
    }

    /**
     * 检查优惠券
     * @return $this
     * @throws \Exception
     */
    public function checkCoupon()
    {
        if (empty($this->origin)) {
            throw new \Exception('该优惠券不存在！');
        }
        return $this;
    }

    /**
     * 是否开启
     * @return $this
     * @throws \Exception
     */
    public function checkOpen()
    {
        if ($this->getData('is_open') == 0) {
            throw new \Exception('该优惠券已关闭！');
        }
        return $this;
    }

    /**
     * 判断优惠券的剩余数量
     * @return $this
     * @throws \Exception
     */
    public function checkNumber()
    {
        if ($this->getData('give_num') <= $this->getData('received_num')) {
            throw new \Exception('该优惠券已被领完！');
        }
        return $this;
    }

    /**
     * 判断自己的剩余数量
     * @param $user_id
     * @return $this
     * @throws \think\Exception
     */
    public function checkMyNumber($user_id)
    {
        $self_num = UserCoupon::where('user_id', $user_id)->where('coupon_id', $this->getData('id'))->count();
        if ($this->getData('allow_num') <= $self_num) {
            throw new \Exception('您没有可领取该优惠券的数量！');
        }
        return $this;
    }

    /**
     * 校验优惠券领取的时间
     * @return $this
     * @throws \Exception
     */
    public function checkReceiveTime()
    {
        $time = time();
        $receive_times = $this->getAttr('receive_times');
        $range_time = explode(' - ', $receive_times);
        if (count($range_time) != 2) {
            throw new \Exception('该优惠券领取时间格式错误！', 1000);
        }

        if ($time < strtotime($range_time[0])) {
            throw new \Exception('未到领取优惠券时间，请过后再来！', 1002);
        }
        if ($time > strtotime($range_time[1])) {
            throw new \Exception('该优惠券已经失效！', 1000);
        }
        return $this;
    }

    /**
     * 校验优惠券使用的时间
     * @param $use_coupon_time
     * @return $this
     * @throws \Exception
     */
    public function checkUseTime($use_coupon_time)
    {
        $time = time();
        $use_times = $this->getData('use_times');
        if ($this->getData('mode') == 'fixation') { //固定日期

            if (!empty($use_times) && is_numeric($use_times) && ($time - $use_coupon_time >= $use_times * 24 * 60 * 60)) {
                throw new \Exception('该优惠券已经失效！', 1000);
            }
        } else { //时间范围

            $range_time = explode(' - ', $use_times);
            if (count($range_time) != 2) {
                throw new \Exception('该优惠券使用时间格式错误！', 1000);
            }

            if ($time < strtotime($range_time[0])) {
                throw new \Exception('未到使用优惠券时间，请换个优惠券试试！', 1001);
            }

            if ($time > strtotime($range_time[1])) {
                throw new \Exception('该优惠券已经失效！', 1000);
            }
        }
        return $this;
    }

    /**
     * @ 获取生效和失效时间
     * @return array
     */
    public function getUseTime()
    {
        $timeArr = [];
        $time = time();
        $use_times = $this->getData('use_times');
        if ($this->getData('mode') == 'fixation') { //固定日期
            $timeArr[0] = $time;
            $timeArr[1] = \fast\Date::unixtime('day', $use_times, 'end');
        } else { //时间范围
            $range_time = explode(' - ', $use_times);
            if (count($range_time) != 2) {
                throw new \Exception('该优惠券使用时间格式错误！');
            }
            $timeArr[0] = strtotime($range_time[0]);
            $timeArr[1] = strtotime($range_time[1]);
        }
        return $timeArr;
    }

    /**
     * 优惠券是否已经领取
     * @param $user_id
     * @return $this
     */
    public function checkReceive($user_id)
    {
        if (empty($this->origin)) {
            throw new \Exception('该优惠券不存在！');
        }
        $row = UserCoupon::where('coupon_id', $this->getData('id'))->where('user_id', $user_id)->find();
        if ($row) {
            throw new \Exception('您已领取该优惠券！');
        }
        return $this;
    }

    /**
     * 判断条件：1指定商品
     * @param       $goods_ids
     * @param       $user_id
     * @param array $category_ids
     * @param array $brand_ids
     * @return $this
     * @throws \think\Exception
     */
    public function checkConditionGoods($goods_ids, $user_id, $category_ids = [], $brand_ids = [])
    {
        if (!empty($this->getData('condition_ids'))) {

            $conditions = CouponCondition::where('id', 'IN', $this->getData('condition_ids'))->select();

            foreach ($conditions as $item) {
                switch ($item['type']) {
                    case 1: //指定商品
                        $ids = explode(',', $item['content']);
                        $result = array_intersect($goods_ids, $ids);
                        //要全等
                        if (count($goods_ids) != count($result)) {
                            throw new \Exception('该优惠券必须在指定的商品使用！');
                        }
                        break;
                    case 2: //新用户专享
                        $order = (new Order())->where('user_id', $user_id)->where('paytime', '>', 0)->count();
                        if ($order) {
                            throw new \Exception('该优惠券限定新用户专享！');
                        }
                        break;
                    case 3: //老用户专享
                        $order = (new Order())->where('user_id', $user_id)->where('paytime', '>', 0)->count();
                        if (!$order) {
                            throw new \Exception('该优惠券限定老用户专享！');
                        }
                        break;
                    case 4: //指定分类
                        $ids = explode(',', $item['content']);
                        $result = array_intersect($category_ids, $ids);
                        //要全等
                        if (count($category_ids) != count($result)) {
                            throw new \Exception('该优惠券必须在指定分类的商品使用！');
                        }
                        break;
                    case 5: //指定品牌
                        $ids = explode(',', $item['content']);
                        $result = array_intersect($brand_ids, $ids);
                        //要全等
                        if (count($brand_ids) != count($result)) {
                            throw new \Exception('该优惠券必须在指定品牌的商品使用！');
                        }
                        break;
                }
            }
        }
        return $this;
    }

    /**
     * 渲染优惠券
     * @param       $row
     * @param array $coupon_ids
     * @return mixed
     */
    public static function render(&$row, $coupon_ids = [])
    {
        //失效的优惠券状态
        if (!empty($coupon_ids) && in_array($row['id'], $coupon_ids)) {
            $num = 0;
            foreach ($coupon_ids as $res) {
                if ($res == $row['id']) {
                    $num++;
                }
            }
            $row['is_received'] = ($row['allow_num'] - $num) == 0;
        } else {
            $row['is_received'] = false;
        }
        $row->expired = false;
        $row->online = true;
        try {
            $row->checkReceiveTime();
        } catch (\Exception $e) {
            if ($e->getCode() == 1000) {
                $row->expired = true;
            } elseif ($e->getCode() == 1002) {
                $row->online = false;
            };
            $row->message = $e->getMessage();
        }
        $row->has_more = $row->received_num >= $row->give_num;
        $row->id = IntCode::encode($row->id);
        return $row;
    }

    /**
     * 获取列表
     * @param $param
     * @return \think\Paginator
     */
    public static function tableList($param)
    {

        $pageNum = 15;
        if (!empty($param['num'])) {
            $pageNum = $param['num'];
        }

        return self::where(function ($query) use ($param) {

            if (!empty($param['is_private'])) {
                $query->where('is_private', $param['is_private']);
            }

            if (!empty($param['is_open'])) {
                $query->where('is_open', $param['is_open']);
            }

            if (isset($param['result']) && $param['result'] != '') {
                $query->where('result', $param['result']);
            }
        })->where('endtime', '>', time())->order('createtime desc')->paginate($pageNum);
    }
}
