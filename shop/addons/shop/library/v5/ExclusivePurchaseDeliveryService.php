<?php

namespace addons\shop\library\v5;

use think\Db;

/** 参考计划使用独立商品来源，配送规则与预约容量复用商城计划服务。 */
class ExclusivePurchaseDeliveryService
{
    public static function source($packageSn)
    {
        $proof = Db::name('shop_recommendation_package')->where('package_sn', $packageSn)->value('agent_source_proof_json');
        $source = AgentMealSourceService::referenceSource(Json::decode($proof ?: '{}', []));
        return ($source['kind'] ?? '') === 'exclusive_purchase' ? $source : null;
    }

    /** 日期列表只读；同一地址、时段、实际选购量参与所有候选排期校验。 */
    public function availableDates($userId, array $payload)
    {
        if (($payload['source_type'] ?? '') !== 'recommendation_package') throw new DomainException('采购来源无效',40001,400);
        (new AgentMealSourceService())->assertSource($userId, $payload['source_type'], $payload['source_ref'] ?? '', $payload['source_version'] ?? 0);
        $source = self::source($payload['source_ref']);
        if (!$source) throw new DomainException('当前采购不支持整周配送',40001,400);
        $package = (new RecommendationPackageService())->getBySn($payload['source_ref'], $userId);
        $selected = CheckoutService::recommendationItems($package['items'], $payload['items'] ?? null);
        $delivery = (new DeliveryService())->validateAddress($userId, $payload['address_id'] ?? 0, $payload['delivery_slot_id'] ?? 0);
        $policy = (new PlanPolicyService())->current();
        $allocation = $this->currentAllocation($source, $selected, $policy);
        $today = new \DateTimeImmutable('today', new \DateTimeZone('Asia/Shanghai'));
        $dates = [];
        $lastError = '';
        for ($offset = $policy['config']['delivery']['first_lead_days']; $offset <= $policy['config']['delivery']['booking_horizon_days']; $offset++) {
            $mealDate = $today->modify('+'.($offset + 1).' days')->format('Y-m-d');
            try {
                $this->schedule($allocation, $delivery, $policy, $mealDate);
                $dates[] = $mealDate;
            } catch (DomainException $error) {
                if (!in_array($error->getCode(), [40961,40916], true)) throw $error;
                $lastError = $error->getMessage();
            }
        }
        return ['items'=>$dates, 'policy_version'=>$policy['version'], 'message'=>$dates ? '' : ($lastError ?: '暂无可预约日期')];
    }

    /** 金额及批次由服务端生成；客户端只能选择起始日期和统一时段。 */
    public function quote(array $source, array $items, array $delivery, $mealDate)
    {
        $policy = (new PlanPolicyService())->current();
        $allocation = $this->currentAllocation($source, $items, $policy);
        $batches = $this->schedule($allocation, $delivery, $policy, $mealDate);
        return [
            'exclusive_delivery'=>[
                'version'=>1, 'first_meal_date'=>$mealDate,
                'last_meal_date'=>(new \DateTimeImmutable($mealDate))->modify('+6 days')->format('Y-m-d'),
                'policy_version'=>$policy['version'], 'policy_hash'=>$policy['hash'],
                'requirements_hash'=>hash('sha256', Json::canonical($source['delivery_requirements'])),
            ],
            'delivery_batches'=>$batches,
            'shipping_fee_cent'=>array_sum(array_column($batches, 'shipping_fee_cent')),
        ];
    }

    /** 整数包装不拆包；至少每个保鲜窗口一包，其余按原谱相对使用量分配。 */
    public static function allocate(array $requirements, array $items)
    {
        if (($requirements['version'] ?? null) !== 1 || ($requirements['period_days'] ?? null) !== 7) {
            throw new DomainException('配送依据已更新，请返回计划重新打开采购',40906,409);
        }
        $allowed = array_column($requirements['items'] ?? [], null, 'sku_id');
        $batches = [];
        foreach ($items as $item) {
            $sid = (string)$item['sku_id'];
            $entry = $allowed[$sid] ?? null;
            $rule = $entry['storage_rule'] ?? null;
            if (!$entry || !$rule || ($rule['review_status'] ?? '') !== 'approved' || !is_int($rule['max_days'] ?? null) || $rule['max_days'] < 1 ||
                !in_array($rule['condition'] ?? '', ['ambient','refrigerated','frozen'], true) || empty($rule['source']) || empty($rule['version'])) {
                throw new DomainException(($entry['food'] ?? '商品').'的储存规则待核对，暂不能确认配送',40963,409,['reason'=>'storage_rule_pending','sku_id'=>$sid]);
            }
            $uses = [];
            foreach ($entry['uses'] ?? [] as $use) {
                if (!is_int($use['day_no'] ?? null) || $use['day_no'] < 1 || $use['day_no'] > 7 || !is_numeric($use['weight'] ?? null) || !is_finite((float)$use['weight']) || $use['weight'] <= 0) {
                    throw new DomainException('食材使用日依据无效，请重新采购',40906,409);
                }
                $uses[$use['day_no']] = ($uses[$use['day_no']] ?? 0) + $use['weight'];
            }
            if (!$uses) throw new DomainException('食材缺少使用日，请重新采购',40906,409);
            ksort($uses);
            $windows = [];
            foreach ($uses as $day => $weight) {
                $start = $rule['max_days'] >= 7 ? 1 : $day;
                $last = count($windows) - 1;
                if ($last >= 0 && $day <= $windows[$last]['day_no'] + $rule['max_days'] - 1) {
                    $windows[$last]['use_days'][] = $day;
                    $windows[$last]['weight'] += $weight;
                } else $windows[] = ['day_no'=>$start, 'use_days'=>[$day], 'weight'=>$weight];
            }
            $quantity = $item['quantity'];
            if (!is_int($quantity) || $quantity < count($windows) || $quantity > 100000) {
                throw new DomainException($entry['food'].'需要分'.count($windows).'趟配送，请返回食材列表核对包装数量',40963,409,[
                    'reason'=>'insufficient_delivery_packs','sku_id'=>$sid,'minimum_packages'=>count($windows),
                ]);
            }
            $remaining = $quantity - count($windows);
            $totalWeight = array_sum(array_column($windows, 'weight'));
            $fractions = [];
            foreach ($windows as $index => &$window) {
                $share = $remaining * $window['weight'] / $totalWeight;
                $window['quantity'] = 1 + (int)floor($share);
                $fractions[$index] = $share - floor($share);
            }
            unset($window);
            arsort($fractions, SORT_NUMERIC);
            $extra = $quantity - array_sum(array_column($windows, 'quantity'));
            foreach (array_slice(array_keys($fractions), 0, $extra) as $index) $windows[$index]['quantity']++;
            foreach ($windows as $window) {
                $day = $window['day_no'];
                $batches[$day][] = array_merge($item, [
                    'quantity'=>$window['quantity'], 'food'=>$entry['food'], 'use_days'=>$window['use_days'],
                    'storage_condition'=>$rule['condition'], 'storage_max_days'=>$rule['max_days'],
                    'storage_rule_version'=>$rule['version'],
                    'line_amount_cent'=>isset($item['unit_price_cent']) ? $window['quantity'] * $item['unit_price_cent'] : null,
                ]);
            }
        }
        if (!$batches) throw new DomainException('请至少选择一件食材',40012,400);
        ksort($batches);
        return $batches;
    }

    /** 既有订单快照拥有预约事实，取消或过期订单不占用容量。 */
    public static function reservedCapacity($areaId, $date, $slotId)
    {
        $rows = Db::name('shop_order_ext')->alias('e')->join('shop_order o', 'o.id=e.order_id')
            ->where('e.source_type', 'recommendation_package')->where('o.orderstate', 'not in', [1,2])
            ->where(function ($q) { $q->where('o.paystate',1)->whereOr('o.expiretime','>',time()); })
            ->field('e.pricing_snapshot_json')->select();
        $area = 0; $slot = 0;
        foreach ($rows as $row) {
            $pricing = Json::decode($row['pricing_snapshot_json'], []);
            if (empty($pricing['exclusive_delivery']) || (string)($pricing['delivery_area_id'] ?? '') !== (string)$areaId) continue;
            foreach ($pricing['delivery_batches'] ?? [] as $batch) {
                if ($batch['delivery_date'] !== $date) continue;
                $area++;
                if ((string)($pricing['delivery_slot_id'] ?? '') === (string)$slotId) $slot++;
            }
        }
        return ['area'=>$area, 'slot'=>$slot];
    }

    private function currentAllocation(array $source, array $items, array $policy)
    {
        $requirements = $source['delivery_requirements'] ?? [];
        $saved = array_column($requirements['items'] ?? [], null, 'sku_id');
        foreach ($items as $item) {
            $sid = (string)$item['sku_id'];
            if (Json::canonical($saved[$sid]['storage_rule'] ?? null) !== Json::canonical($policy['config']['delivery']['storage_rules'][$sid] ?? null)) {
                throw new DomainException('商品储存规则已变化，请返回计划重新读取采购',40906,409);
            }
        }
        return self::allocate($requirements, $items);
    }

    private function schedule(array $allocation, array $delivery, array $policy, $mealDate)
    {
        $tz = new \DateTimeZone('Asia/Shanghai');
        $meal = is_string($mealDate) ? \DateTimeImmutable::createFromFormat('!Y-m-d', $mealDate, $tz) : false;
        if (!$meal || $meal->format('Y-m-d') !== $mealDate) throw new DomainException('请选择开始食用日期',40001,400);
        $days = array_keys($allocation);
        $ranges = [];
        foreach ($days as $index => $day) $ranges[] = [$day, ($days[$index+1] ?? 8) - 1];
        $first = $meal->modify(sprintf('%+d days', $days[0] - 2))->format('Y-m-d');
        // 全周起始日也必须满足提前期，不能借取消早期商品绕过预约窗口。
        PlanScheduleService::dates($policy['config']['delivery'], ['weekdays'=>range(1,7),'closed_dates'=>[]], $meal->modify('-1 day')->format('Y-m-d'), 1);
        $schedule = (new PlanScheduleService())->preview($policy, $delivery, $first, count($ranges), false, 0, 'daily', $ranges);
        $batches = [];
        foreach ($schedule['items'] as $index => $batch) {
            $batch['items'] = $allocation[$days[$index]];
            $batch['goods_amount_cent'] = array_sum(array_column($batch['items'], 'line_amount_cent'));
            $batch['slot_name'] = $delivery['slot']['name'] ?: $delivery['slot']['start_time'].'–'.$delivery['slot']['end_time'];
            $batch['contains_weekly_staples'] = (bool)array_filter($batch['items'], static function ($item) { return $item['storage_max_days'] >= 7; });
            $batches[] = $batch;
        }
        return $batches;
    }
}
