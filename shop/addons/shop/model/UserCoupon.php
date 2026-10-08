<?php

namespace addons\shop\model;

use think\Model;
use addons\shop\library\IntCode;
use addons\shop\model\OrderAction;

class UserCoupon extends Model
{

    // 表名
    protected $name = 'shop_user_coupon';

    // 自动写入时间戳字段
    protected $autoWriteTimestamp = 'int';

    // 定义时间戳字段名
    protected $createTime = 'createtime';
    protected $updateTime = 'updatetime';
    protected $deleteTime = false;

    // 追加属性
    protected $append = [
        'is_used_text'
    ];


    public function getIsUsedList()
    {
        return ['1' => __('Is_used 1'), '2' => __('Is_used 2')];
    }


    public function getIsUsedTextAttr($value, $data)
    {
        $value = $value ?: ($data['is_used'] ?? '');
        $list = $this->getIsUsedList();
        return $list[$value] ?? '';
    }

    /**
     * 检查优惠券的归属用户和是否已使用
     *
     * @param [type] $user_coupon_id
     * @param [type] $user_id
     * @return Object
     */
    public function checkUserOrUse($user_coupon_id, $user_id)
    {
        $row = $this->where('id', $user_coupon_id)->where('user_id', $user_id)->find();
        if (!$row) {
            throw new \Exception('未领取该优惠券或不可用！');
        }
        if ($row['is_used'] == 2) {
            throw new \Exception('该优惠券已使用！');
        }
        return $row;
    }

    //我的优惠券列表
    public static function tableList($param)
    {
        $pageNum = 10;
        if (!empty($param['num'])) {
            $pageNum = $param['num'];
        }
        return self::field('id,coupon_id,user_id,is_used,expire_time,begin_time,createtime')->with(['Coupon' => function ($query) {
            $query->field('id,name,result,result_data,allow_num,begintime,endtime,mode,use_times');
        }])->where(function ($query) use ($param) {

            $time = time();
            if (!empty($param['is_used'])) {
                $query->where('is_used', $param['is_used'])->where('begin_time', '<', $time);
            }

            if (isset($param['user_id']) && $param['user_id'] != '') {
                $query->where('user_id', $param['user_id']);
            }
            if (!empty($param['begin_time'])) {
                $query->where('begin_time', '>', $time);
            }
            if (!empty($param['expire_time'])) {
                $query->where('expire_time', '<', $time);
            }
        })->order('createtime desc')->paginate($pageNum);
    }


    //我的可以使用的优惠券【过滤掉条件不符合的】
    public static function myGoodsCoupon($user_id, $goods_ids, $category_ids, $brand_ids)
    {
        $order = (new Order())->where('user_id', $user_id)->where('paytime', '>', 0)->count();
        if ($order) {
            $type = 3; //老用户
        } else {
            $type = 2; //新用户
        }
        $conditions = CouponCondition::getGoodsCondition($goods_ids, $category_ids, $brand_ids, $type);
        $sql = "condition_ids IS NULL OR condition_ids=''";
        foreach ($conditions as $key => $item) {
            $sql .= " OR FIND_IN_SET('{$item['id']}',condition_ids)";
        }
        $time = time();
        //我的所有未使用的优惠券
        $list = self::field('*')->with(['Coupon' => function ($query) use ($sql) {
            $query->where($sql);
        }])->where('user_id', $user_id)
            ->where('is_used', 1)
            ->where('begin_time', '<', $time)
            ->where('expire_time', '>', $time)
            ->select();
        $data = [];
        foreach ($list as $item) {
            if (!empty($item['coupon'])) {
                $coupon = $item['coupon'];
                $coupon['id'] = is_numeric($coupon['id']) ? IntCode::encode($coupon['id']) : $coupon['id'];
                $coupon['user_coupon_id'] = $item['id'];
                $coupon['expire_time'] = $item['expire_time'];
                $data[] = $coupon->toArray();
            }
        }
        return $data;
    }

    //恢复优惠券
    public static function resetUserCoupon($user_coupon_id, $order_sn)
    {
        if ($user_coupon_id) {
            self::where('id', $user_coupon_id)->update(['is_used' => 1]);
            //记录操作
            OrderAction::push($order_sn, '系统', '订单取消恢复优惠券');
        }
        return true;
    }

    public function Coupon()
    {
        return $this->hasOne('Coupon', 'id', 'coupon_id');
    }
}
