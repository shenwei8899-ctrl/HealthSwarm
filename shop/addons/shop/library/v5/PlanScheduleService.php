<?php

namespace addons\shop\library\v5;

use think\Db;

/** 预约、报价和恢复共用的排程。送达次日开始食用。 */
class PlanScheduleService
{
    public function availableDates(array $policy, array $delivery, $count = 21, $resume = false, $excludeOrder = 0, $frequency = 'daily')
    {
        $config = $policy['config']['delivery'];
        $start = new \DateTimeImmutable('today', new \DateTimeZone('Asia/Shanghai'));
        $items = [];
        for ($offset = $config[$resume ? 'resume_lead_days' : 'first_lead_days']; $offset <= $config['booking_horizon_days']; $offset++) {
            $date = $start->modify('+'.$offset.' days')->format('Y-m-d');
            try {
                $this->preview($policy, $delivery, $date, $count, $resume, $excludeOrder, $frequency);
                $items[] = ['delivery_date'=>$date, 'first_meal_date'=>$start->modify('+'.($offset+1).' days')->format('Y-m-d')];
            } catch (DomainException $error) {
                if ($error->getCode() !== 40961) throw $error;
            }
        }
        return ['items'=>$items, 'policy_version'=>$policy['version']];
    }

    public function preview(array $policy, array $delivery, $firstDate, $count = 21, $resume = false, $excludeOrder = 0, $frequency = 'daily')
    {
        if (empty($delivery['slot']) || ($delivery['slot']['service_scope'] ?? 'normal')!=='plan') throw new DomainException('请选择专属计划配送时段',40915,409);
        $region = null;
        foreach ($policy['config']['delivery']['regions'] as $candidate) {
            if ((string)$candidate['area_id'] === (string)$delivery['area']['id']) $region = $candidate;
        }
        if (!$region) throw new DomainException('当前区域尚未开放专属计划配送',40961,409);
        $paused = [];
        if ($resume && $excludeOrder) {
            $existing=Db::name('shop_plan_delivery_batch')->where('plan_order_id',$excludeOrder)->order('batch_no')->select();
            $paused=array_values(array_filter($existing,function($batch){return $batch['status']==='paused';}));
            if (count($paused)!==$count) throw new DomainException('暂停批次已变化，请重新预约',40961,409);
        }
        $ranges = self::menuRanges($frequency, $count, $paused);
        $items = self::dates($policy['config']['delivery'], $region, $firstDate, count($ranges), $resume, null, $ranges);
        if ($paused) {
            foreach ($items as $index=>$candidate) foreach ($existing as $fixed) {
                if (in_array($fixed['status'],['paused','cancelled','refund_pending','refunded'],true)) continue;
                $before=(int)$fixed['batch_no']<(int)$paused[$index]['batch_no'];
                $fixedEnd = $fixed['meal_end_date'] ?? $fixed['meal_date'];
                if (($before && $fixedEnd >= $candidate['meal_date']) || (!$before && $fixed['meal_date'] <= $candidate['meal_end_date'])) throw new DomainException('新的配送安排不能与已确定批次重叠或改变餐单顺序',40961,409);
            }
        }
        foreach ($items as &$item) {
            $week=(int)(new \DateTimeImmutable($item['delivery_date']))->format('N');
            $closed=Json::decode($delivery['slot']['blackout_dates_json'] ?? '[]',[]);
            if (!in_array((string)$week,explode(',',(string)$delivery['slot']['weekday_mask']),true) || in_array($item['delivery_date'],$closed,true)) throw new DomainException('配送时段在所选日期停运',40961,409);
            $used = Db::name('shop_plan_delivery_batch')->alias('b')
                ->join('shop_service_plan_order p', 'p.id=b.plan_order_id')
                ->join('shop_order o', 'o.id=p.order_id')
                ->where('b.delivery_area_id', $delivery['area']['id'])->where('b.delivery_date',$item['delivery_date'])
                ->where('b.status','not in',['paused','cancelled','refund_pending','refunded'])
                ->where('p.id','<>',$resume?0:$excludeOrder)
                ->where('o.orderstate','not in',[1,2])
                ->where(function ($q) { $q->where('o.paystate',1)->whereOr('o.orderstate',0); })
                ->count();
            if ($used >= $region['daily_capacity']) throw new DomainException('所选日期配送名额已满',40961,409,['delivery_date'=>$item['delivery_date']]);
            if (!empty($delivery['slot']['id']) && (int)$delivery['slot']['capacity']>0) {
                $slotUsed=(int)Db::name('shop_plan_delivery_batch')->alias('b')
                    ->join('shop_service_plan_order p','p.id=b.plan_order_id')->join('shop_order o','o.id=p.order_id')
                    ->where('b.delivery_slot_id',$delivery['slot']['id'])->where('b.delivery_date',$item['delivery_date'])
                    ->where('b.status','not in',['paused','cancelled','refund_pending','refunded'])->where('p.id','<>',$resume?0:$excludeOrder)
                    ->where('o.orderstate','not in',[1,2])
                    ->where(function ($q) { $q->where('o.paystate',1)->whereOr('o.orderstate',0); })->count();
                if ($slotUsed+(int)$delivery['slot']['used_capacity'] >= (int)$delivery['slot']['capacity']) throw new DomainException('所选配送时段名额已满',40961,409,['delivery_date'=>$item['delivery_date']]);
            }
            $item['shipping_fee_cent'] = $region['fee_cent'] + (int)($delivery['slot']['extra_fee_cent'] ?? 0);
            $item['delivery_area_id'] = (int)$delivery['area']['id'];
        }
        return ['items'=>$items, 'total_batches'=>count($items), 'policy_version'=>$policy['version']];
    }

    /** 在购买或恢复事务内持锁，容量复核与保存批次使用同一串行边界。 */
    public function lockCapacity()
    {
        if (strtolower((string)config('database.type'))==='pgsql') Db::query('SELECT pg_advisory_xact_lock(761025, 21)');
        Db::name('shop_plan_policy')->order('id','asc')->lock(true)->select();
    }

    public static function purchaseFrequency(array $plan, $value)
    {
        if ($plan['delivery_frequency'] === 'daily' && ($value === null || $value === 'daily')) return 'daily';
        if (in_array($value, ['weekly_2', 'weekly_3'], true)) return $value;
        throw new DomainException('请选择每周配送两次或三次',40011,400);
    }

    public static function menuRanges($frequency, $count, array $paused = [])
    {
        if ($paused) {
            return array_map(static function ($batch) {
                $start = (int)($batch['menu_day_start'] ?? $batch['batch_no']);
                return [$start, (int)($batch['menu_day_end'] ?? $start)];
            }, $paused);
        }
        $widths = ['daily' => [1], 'weekly_2' => [3, 4], 'weekly_3' => [2, 2, 3]][$frequency] ?? [];
        if (!$widths || $count < 1 || $count > 21) throw new DomainException('配送排期参数无效',40011,400);
        $ranges = [];
        for ($day = 1; $day <= $count; $day = $end + 1) {
            $end = min($count, $day + $widths[count($ranges) % count($widths)] - 1);
            $ranges[] = [$day, $end];
        }
        return $ranges;
    }

    public static function dates(array $config, array $region, $firstDate, $count = 21, $resume = false, $now = null, array $ranges = [])
    {
        $tz = new \DateTimeZone('Asia/Shanghai');
        $now = $now === null ? time() : $now;
        $today = (new \DateTimeImmutable('@'.$now))->setTimezone($tz)->setTime(0,0);
        $first = \DateTimeImmutable::createFromFormat('!Y-m-d', (string)$firstDate, $tz);
        if (!$first || $first->format('Y-m-d') !== $firstDate || $count < 1 || $count > 21 ||
            $first < $today->modify('+'.$config[$resume ? 'resume_lead_days' : 'first_lead_days'].' days') ||
            $first > $today->modify('+'.$config['booking_horizon_days'].' days')) {
            throw new DomainException('请选择可预约的首批送达日',40961,409);
        }
        $items = [];
        $date = $first;
        foreach ($ranges ?: self::menuRanges('daily', $count) as $index => [$start, $end]) {
            $cutoff = new \DateTimeImmutable($date->modify('-'.$config['cutoff_lead_days'].' days')->format('Y-m-d').' '.$config['cutoff_time'], $tz);
            if (!in_array((int)$date->format('N'),$region['weekdays'],true) || in_array($date->format('Y-m-d'),$region['closed_dates'],true) || $cutoff->getTimestamp() <= $now) {
                throw new DomainException('连续配送期间存在不可预约日期',40961,409,['delivery_date'=>$date->format('Y-m-d')]);
            }
            $items[] = ['batch_no'=>$index+1,'delivery_date'=>$date->format('Y-m-d'),
                'meal_date'=>$date->modify('+1 day')->format('Y-m-d'),
                'meal_end_date'=>$date->modify('+'.($end - $start + 1).' days')->format('Y-m-d'),
                'menu_day_start'=>$start,'menu_day_end'=>$end,
                'cutoff_at'=>$cutoff->getTimestamp(),'inventory_lock_at'=>$cutoff->getTimestamp()];
            $date = $date->modify('+'.($end - $start + 1).' days');
        }
        return $items;
    }

    public static function changeable(array $batch, $now = null)
    {
        return in_array($batch['status'],['scheduled','paused'],true)
            && ($batch['status']==='paused' || (int)$batch['cutoff_at'] > ($now === null ? time() : $now))
            && in_array($batch['inventory_status'],['pending','released'],true)
            && $batch['supplier_status'] === 'pending' && $batch['fulfillment_status'] === 'pending'
            && ($batch['aftersale_status'] ?? 'none') === 'none';
    }
}
