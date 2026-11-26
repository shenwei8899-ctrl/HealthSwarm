<?php

namespace addons\shop\library\v5;

use think\Db;

class CheckoutService
{
    public function preview($userId, array $payload, array $context = [])
    {
        foreach (['source_type', 'source_ref', 'source_version', 'address_id'] as $field) {
            if (!isset($payload[$field]) || $payload[$field] === '') {
                throw new DomainException('缺少必填字段: ' . $field, 40001, 400, ['field' => $field]);
            }
        }
        if (!in_array($payload['source_type'], ['cart', 'purchase_list', 'recommendation_package', 'service_plan'], true)) {
            throw new DomainException('结算来源无效', 40001, 400);
        }
        $delivery = (new DeliveryService())->validateAddress($userId, $payload['address_id'], isset($payload['delivery_slot_id']) ? $payload['delivery_slot_id'] : 0);
        if ($payload['source_type'] === 'service_plan') {
            $pricing = $this->pricePlan($userId, $payload, $delivery);
        } else {
            $pricing = $this->priceCommerce($userId, $payload, $delivery);
        }
        if (!empty($pricing['warnings'])) {
            foreach ($pricing['warnings'] as $warning) {
                if (!empty($warning['blocking'])) {
                    throw new DomainException('结算校验未通过', 40917, 409, ['trade_issues' => $pricing['warnings']]);
                }
            }
        }
        $token = 'checkout_' . bin2hex(random_bytes(24));
        $tokenHash = hash('sha256', $token);
        $now = time();
        $expiresAt = $now + ($payload['source_type'] === 'service_plan' ? $pricing['policy_snapshot']['config']['quote_ttl_seconds'] : 900);
        $mealSnapshot = (new MealCommerceService())->quoteSnapshot($userId, $payload, $pricing);
        unset($pricing['_validated_package']);
        if ($mealSnapshot) $pricing['meal_snapshot'] = $mealSnapshot;
        $pricing['address_snapshot'] = $delivery['snapshot'];
        $pricing['delivery_area_id'] = (string)$delivery['area']['id'];
        $pricing['delivery_slot_id'] = $delivery['slot'] ? (string)$delivery['slot']['id'] : '0';
        $pricing['delivery_slot_fee_cent'] = $delivery['slot'] ? (int)$delivery['slot']['extra_fee_cent'] : 0;

        Db::startTrans();
        try {
            Db::name('shop_checkout_session')->insert([
                'checkout_token_hash' => $tokenHash, 'user_id' => $userId,
                'source_type' => $payload['source_type'], 'source_ref' => $payload['source_ref'],
                'source_version' => (int)$payload['source_version'], 'address_id' => (int)$payload['address_id'],
                'pricing_snapshot_json' => Json::encode($pricing),
                'trade_issues_json' => Json::encode(isset($pricing['warnings']) ? $pricing['warnings'] : []),
                'total_amount_cent' => $pricing['payable_amount_cent'],
                'status' => 'active', 'expires_at' => $expiresAt,
                'createtime' => $now, 'updatetime' => $now,
            ]);
            Db::commit();
        } catch (\Exception $e) {
            Db::rollback();
            throw $e;
        }
        $pricing['checkout_token'] = $token;
        $pricing['expires_at'] = date(DATE_ATOM, $expiresAt);
        return $pricing;
    }

    public function createOrder($userId, array $payload, $requestId)
    {
        if (empty($payload['checkout_token'])) {
            throw new DomainException('checkout_token不能为空', 40001, 400);
        }
        $tokenHash = hash('sha256', $payload['checkout_token']);
        $session = Db::name('shop_checkout_session')->where('checkout_token_hash', $tokenHash)->find();
        if (!$session || (int)$session['user_id'] !== (int)$userId) {
            throw new DomainException('结算令牌无效', 40408, 404);
        }
        if ($session['status'] !== 'active' || (int)$session['expires_at'] <= time()) {
            throw new DomainException('结算令牌已失效', 40918, 409);
        }
        $pricing = Json::decode($session['pricing_snapshot_json'], []);
        Db::startTrans();
        try {
            $locked = Db::name('shop_checkout_session')->where('id', $session['id'])->lock(true)->find();
            if ($locked['status'] !== 'active') throw new DomainException('结算令牌已使用', 40918, 409);
            if (!empty($pricing['meal_snapshot'])) {
                $meal = $pricing['meal_snapshot'];
                Db::name('shop_recommendation_package')->where('package_sn',$meal['package_sn'])->where('user_id',$userId)->lock(true)->find();
                if ($session['source_type'] !== 'recommendation_package') {
                    $currentMenu=(new MealCommerceService())->package($userId, $meal['package_sn'], $meal['package_version']);
                    if (!$currentMenu['available']) throw new DomainException('菜单已不可购买，请重新确认',40917,409);
                }
            }
            $this->revalidatePricing($locked, $pricing);
            $result = $session['source_type'] === 'service_plan'
                ? $this->createPlanOrder($session, $pricing, $payload, $requestId)
                : $this->createNormalOrder($session, $pricing, $payload, $requestId);
            Db::commit();
            return $result;
        } catch (\Exception $e) { Db::rollback(); throw $e; }
    }

    protected function pricePlan($userId, array $payload, array $delivery)
    {
        $policy = (new PlanPolicyService())->current();
        if (empty($payload['first_delivery_date']) || !preg_match('/^\d{4}-\d{2}-\d{2}$/', $payload['first_delivery_date'])) {
            throw new DomainException('首批配送日期格式错误', 40011, 400);
        }
        $plan = Db::name('shop_service_plan')->where('plan_sn', $payload['source_ref'])->find();
        if (!$plan) {
            throw new DomainException('专属计划不存在', 40404, 404);
        }
        (new IdentityService())->assertOwner($userId, $plan['user_id']);
        if ((int)$plan['current_version'] !== (int)$payload['source_version'] || $plan['status'] !== 'available') {
            throw new DomainException('专属计划不可结算或版本已变化', 40906, 409);
        }
        (new AgentMealSourceService())->assertSource($userId,'service_plan',$plan['plan_sn'],$payload['source_version']);
        $frequency = PlanScheduleService::purchaseFrequency($plan, $payload['delivery_frequency'] ?? null);
        $schedule=(new PlanScheduleService())->preview($policy,$delivery,$payload['first_delivery_date'],21,false,0,$frequency);
        $version = Db::name('shop_service_plan_version')->where('plan_id', $plan['id'])->where('version_no', $plan['current_version'])->find();
        $draft = Json::decode($version['pricing_draft_json'], []);
        if (count($draft['days'] ?? []) !== 21) {
            throw new DomainException('计划交易草案必须包含完整21天', 40921, 409);
        }
        $pricedBatches = [];
        $warnings = isset($draft['issues']) ? $draft['issues'] : [];
        $source = Json::decode($version['source_payload_json'], []);
        $sourceDays = array_column($source['days'] ?? [], null, 'day_no');
        $draftDays = array_column($draft['days'], null, 'day_no');
        $tierSkus = $policy['config']['tiers'][$plan['tier_code']]['allowed_sku_ids'];
        $goodsTotal = 0;$quantities=[];
        foreach ($schedule['items'] as $batch) {
            $dayTotal = 0;
            $items = [];
            if ($frequency === 'daily') {
                $matched = $draftDays[$batch['menu_day_start']] ?? null;
                if ($matched === null) throw new DomainException('计划食材来源不完整',40921,409);
            } else {
                $meals = [];
                $eligibleSkus = [];
                $lastUse = [];
                foreach (range($batch['menu_day_start'], $batch['menu_day_end']) as $dayNo) {
                    if (!isset($sourceDays[$dayNo])) throw new DomainException('计划食材来源不完整',40921,409);
                    $meals = array_merge($meals, $sourceDays[$dayNo]['meals']);
                    $eligibleSkus = array_merge($eligibleSkus, $sourceDays[$dayNo]['eligible_sku_ids']);
                    foreach (PlanRequirements::aggregate($sourceDays[$dayNo]['meals']) as $requirement) {
                        $lastUse[$requirement['ingredient_code']] = $dayNo - $batch['menu_day_start'] + 1;
                    }
                }
                $matched = PlanRequirements::matchBatch(
                    $meals, array_values(array_intersect($tierSkus, array_unique($eligibleSkus))), $lastUse
                );
                $warnings = array_merge($warnings, $matched['issues']);
            }
            foreach ($matched['items'] as $draftItem) {
                try {
                    $sku = (new CatalogService())->getSku($draftItem['sku_id'], false);
                    $quantity = max(1, (int)$draftItem['quantity']);
                    AgentMealSourceService::assertComposition($draftItem['product_snapshot'],$sku);
                    $quantities[$sku['sku_id']]=($quantities[$sku['sku_id']] ?? 0)+$quantity;
                    if ($quantities[$sku['sku_id']]>(int)$sku['available_quantity']) throw new DomainException('计划商品库存不足',40904,409);
                    $line = $sku['price_cent'] * $quantity;
                    $items[] = [
                        'sku_id' => $sku['sku_id'], 'goods_id' => $sku['product_id'],
                        'quantity' => $quantity, 'unit_price_cent' => $sku['price_cent'],
                        'line_amount_cent' => $line, 'ingredient_code' => $draftItem['ingredient_code'],
                        'snapshot' => $sku, 'ingredient_codes'=>$draftItem['ingredient_codes'] ?? [$draftItem['ingredient_code']],
                    ];
                    $dayTotal += $line;
                } catch (DomainException $e) {
                    $warnings[] = ['issue_code' => 'sku_unavailable', 'sku_id' => $draftItem['sku_id'], 'message' => $e->getMessage(), 'blocking' => true];
                }
            }
            $goodsTotal += $dayTotal;
            $pricedBatches[] = ['goods_amount_cent' => $dayTotal, 'items' => $items];
        }
        $serviceFee = $policy['config']['service_fee_cent'];
        $shippingFee = array_sum(array_column($schedule['items'],'shipping_fee_cent'));
        $discount = 0;
        $payable = $goodsTotal + $shippingFee + $serviceFee - $discount;
        $goodsAllocation = array_column($pricedBatches, 'goods_amount_cent');
        $shippingAllocation = array_column($schedule['items'],'shipping_fee_cent');
        $dayCounts = array_map(static function ($batch) { return $batch['menu_day_end'] - $batch['menu_day_start'] + 1; }, $schedule['items']);
        $serviceAllocation = $this->allocate($serviceFee, $dayCounts);
        $discountAllocation = $this->allocate($discount, $goodsAllocation);
        $members=(int)Db::name('shop_service_plan_member')->where('plan_id',$plan['id'])->count();
        PlanPolicyService::assertBudget($policy['config']['tiers'][$plan['tier_code']],$members,$goodsTotal,$serviceFee,$shippingFee);
        $batches = [];
        foreach ($pricedBatches as $index => $batch) {
            $amount = $goodsAllocation[$index] + $shippingAllocation[$index] + $serviceAllocation[$index] - $discountAllocation[$index];
            $batches[] = array_merge($schedule['items'][$index], [
                'goods_amount_cent' => $goodsAllocation[$index],
                'shipping_fee_cent' => $shippingAllocation[$index],
                'service_fee_cent' => $serviceAllocation[$index],
                'discount_amount_cent' => $discountAllocation[$index],
                'allocated_pay_amount_cent' => $amount, 'items' => $batch['items'],
            ]);
        }
        foreach ($warnings as $warning) {
            if (!empty($warning['blocking'])) {
                throw new DomainException('计划商品或库存已变化，请由Agent重新评估', 42204, 422, ['issues' => $warnings]);
            }
        }
        return [
            'source_type' => 'service_plan', 'source_ref' => $plan['plan_sn'],
            'source_version' => (int)$plan['current_version'], 'items' => [],
            'goods_amount_cent' => $goodsTotal, 'discount_amount_cent' => $discount,
            'shipping_fee_cent' => $shippingFee, 'service_fee_cent' => $serviceFee,
            'payable_amount_cent' => $payable, 'delivery_batches' => $batches, 'delivery_frequency' => $frequency,
            'policy_snapshot' => $policy, 'warnings' => $warnings,
        ];
    }

    protected function priceCommerce($userId, array $payload, array $delivery)
    {
        $sourceItems = isset($payload['items']) ? $payload['items'] : [];
        if ($payload['source_type'] === 'cart') {
            if ((string)$payload['source_ref'] !== (string)$userId) throw new DomainException('购物车来源不匹配', 40301, 403);
            $sourceItems = (new CartService())->checkoutItems($userId, isset($payload['cart_items']) ? $payload['cart_items'] : []);
            (new AgentMealSourceService())->assertCart($userId, $sourceItems);
        } elseif ($payload['source_type'] === 'purchase_list') {
            (new AgentMealSourceService())->assertSource($userId, 'purchase_list', $payload['source_ref'], $payload['source_version']);
            $list = Db::name('shop_purchase_list')->where('purchase_list_sn', $payload['source_ref'])->find();
            if (!$list) {
                throw new DomainException('采购清单不存在', 40403, 404);
            }
            (new IdentityService())->assertOwner($userId, $list['user_id']);
            if ((int)$list['current_version'] !== (int)$payload['source_version'] || !in_array($list['status'], ['ready', 'confirmed'], true)) {
                throw new DomainException('采购清单不可结算或版本已变化', 40906, 409);
            }
            $sourceItems = Db::name('shop_purchase_item')->alias('i')->join('shop_purchase_match m', 'm.id=i.selected_match_id')
                ->where('i.purchase_list_id', $list['id'])->where('i.list_version_no', $list['current_version'])
                ->field('m.sku_id,m.required_pack_count as quantity')->select();
        } elseif ($payload['source_type'] === 'recommendation_package') {
            (new AgentMealSourceService())->assertSource($userId, 'recommendation_package', $payload['source_ref'], $payload['source_version']);
            $package = (new RecommendationPackageService())->getBySn($payload['source_ref'], $userId);
            if ((int)$package['package_version'] !== (int)$payload['source_version'] || !in_array($package['status'], ['available', 'confirmed'], true)) {
                throw new DomainException('推荐包不可结算或版本已变化', 40906, 409);
            }
            $sourceItems = self::recommendationItems($package['items'], $payload['items'] ?? null);
            $exclusiveSource = ExclusivePurchaseDeliveryService::source($payload['source_ref']);
        }
        if (empty($exclusiveSource) && ($delivery['slot']['service_scope'] ?? 'normal') !== 'normal') throw new DomainException('请选择普通订单配送时段',40915,409);
        if (!$sourceItems) {
            throw new DomainException('结算商品不能为空', 40012, 400);
        }
        $items = [];
        $goodsTotal = 0;
        $warnings = [];
        foreach ($sourceItems as $sourceItem) {
            try {
                $sku = (new CatalogService())->getSku($sourceItem['sku_id'], false);
                $quantity = (int)$sourceItem['quantity'];
                if ($quantity <= 0 || $quantity > (int)$sku['available_quantity']) throw new DomainException('购买数量无效或库存不足', 40904, 409);
                $line = $sku['price_cent'] * $quantity;
                $items[] = ['sku_id' => $sku['sku_id'], 'goods_id' => $sku['product_id'], 'quantity' => $quantity, 'unit_price_cent' => $sku['price_cent'], 'line_amount_cent' => $line, 'snapshot' => $sku];
                $goodsTotal += $line;
            } catch (DomainException $e) {
                $warnings[] = ['issue_code' => 'sku_unavailable', 'sku_id' => isset($sourceItem['sku_id']) ? (string)$sourceItem['sku_id'] : null, 'message' => $e->getMessage(), 'blocking' => true];
            }
        }
        $shipping = $delivery['slot'] ? (int)$delivery['slot']['extra_fee_cent'] : 0;
        $pricing = [
            'source_type' => $payload['source_type'], 'source_ref' => $payload['source_ref'],
            'source_version' => (int)$payload['source_version'], 'items' => $items,
            'goods_amount_cent' => $goodsTotal, 'discount_amount_cent' => 0,
            'shipping_fee_cent' => $shipping, 'service_fee_cent' => 0,
            'payable_amount_cent' => $goodsTotal + $shipping, 'delivery_batches' => [],
            'non_refund_policy' => null, 'warnings' => $warnings,
            'cart_items' => $payload['source_type'] === 'cart' ? $sourceItems : [],
            '_validated_package' => $payload['source_type'] === 'recommendation_package' ? $package : null,
        ];
        if (!empty($exclusiveSource) && !$warnings) {
            $schedule = (new ExclusivePurchaseDeliveryService())->quote($exclusiveSource, $items, $delivery, $payload['first_meal_date'] ?? null);
            $pricing = array_merge($pricing, $schedule);
            $pricing['payable_amount_cent'] = $goodsTotal + $schedule['shipping_fee_cent'];
        }
        return $pricing;
    }

    /** 客户端只能从本人已校验商品包中减选并调整包装数；省略 items 沿用整包。 */
    public static function recommendationItems(array $packageItems, $selected = null)
    {
        $defaults = array_map(static function ($item) {
            return ['sku_id'=>(string)$item['sku_id'], 'quantity'=>(int)$item['quantity']];
        }, $packageItems);
        if ($selected === null) return $defaults;
        if (!is_array($selected) || !$selected || count($selected) > count($defaults)) {
            throw new DomainException('请选择本餐食材', 40012, 400);
        }
        $allowed = array_column($defaults, 'sku_id');
        $seen = []; $result = [];
        foreach ($selected as $item) {
            $sid = is_array($item) && isset($item['sku_id']) ? (string)$item['sku_id'] : '';
            $quantity = is_array($item) ? ($item['quantity'] ?? null) : null;
            if (!in_array($sid, $allowed, true) || isset($seen[$sid]) || !is_int($quantity) || $quantity < 1 || $quantity > 100000) {
                throw new DomainException('所选食材或数量无效，请重新核对', 40012, 400);
            }
            $seen[$sid] = true;
            $result[] = ['sku_id'=>$sid, 'quantity'=>$quantity];
        }
        return $result;
    }

    protected function revalidatePricing(array $session, array $pricing)
    {
        $deliveryService = new DeliveryService();
        $deliveryService->lockRules();
        $delivery = $deliveryService->validateAddress($session['user_id'], $session['address_id'], $pricing['delivery_slot_id'] ?? 0, true);
        if ((string)$delivery['area']['id'] !== (string)$pricing['delivery_area_id']
            || Json::canonical($delivery['snapshot']) !== Json::canonical($pricing['address_snapshot'])
            || (int)($delivery['slot']['extra_fee_cent'] ?? 0) !== (int)($pricing['delivery_slot_fee_cent'] ?? 0)) {
            throw new DomainException('地址或配送规则已变化，请重新结算', 40906, 409);
        }
        if ($session['source_type'] === 'cart') {
            (new CartService())->checkoutItems($session['user_id'], $pricing['cart_items'], true);
            (new AgentMealSourceService())->assertCart($session['user_id'], $pricing['cart_items']);
        } else {
            (new AgentMealSourceService())->assertSource($session['user_id'], $session['source_type'], $session['source_ref'], $session['source_version']);
        }
        if ((int)$session['expires_at'] <= time()) {
            throw new DomainException('结算令牌已过期', 40918, 409);
        }
        if ($session['source_type'] === 'service_plan') {
            (new PlanScheduleService())->lockCapacity();
            $plan = Db::name('shop_service_plan')->where('plan_sn', $session['source_ref'])->lock(true)->find();
            if (!$plan || (int)$plan['current_version'] !== (int)$session['source_version'] || $plan['status'] !== 'available') {
                throw new DomainException('计划版本或状态已变化，请重新结算', 40906, 409);
            }
            $fresh=$this->pricePlan($session['user_id'],[
                'source_ref'=>$session['source_ref'],'source_version'=>$session['source_version'],
                'first_delivery_date'=>$pricing['delivery_batches'][0]['delivery_date'],
                'delivery_frequency'=>$pricing['delivery_frequency'] ?? 'daily',
            ],$delivery);
            if (!isset($pricing['delivery_frequency'])) {
                foreach ($fresh['delivery_batches'] as &$batch) {
                    unset($batch['meal_end_date'], $batch['menu_day_start'], $batch['menu_day_end']);
                }
                unset($batch);
            }
            foreach (['fresh','pricing'] as $name) { foreach (${$name}['delivery_batches'] as &$batch) { foreach ($batch['items'] as &$item) unset($item['snapshot']); unset($item); } unset($batch); }
            foreach (['policy_snapshot','delivery_batches','payable_amount_cent'] as $key) {
                if (Json::canonical($fresh[$key])!==Json::canonical($pricing[$key])) throw new DomainException('价格、供货或配送规则已变化，请重新确认报价',40922,409);
            }
            return;
        }
        if (!empty($pricing['exclusive_delivery'])) {
            (new PlanScheduleService())->lockCapacity();
            $fresh = $this->priceCommerce($session['user_id'], [
                'source_type'=>$session['source_type'], 'source_ref'=>$session['source_ref'], 'source_version'=>$session['source_version'],
                'items'=>array_map(static function ($item) { return ['sku_id'=>(string)$item['sku_id'],'quantity'=>(int)$item['quantity']]; }, $pricing['items']),
                'first_meal_date'=>$pricing['exclusive_delivery']['first_meal_date'],
            ], $delivery);
            if (!empty($fresh['warnings'])) throw new DomainException('商品库存或供货已变化，请重新核对',40922,409);
            $currentItems = array_column($fresh['items'], null, 'sku_id');
            foreach ($pricing['items'] as $item) {
                AgentMealSourceService::assertComposition($item['snapshot'], $currentItems[$item['sku_id']]['snapshot']);
            }
            // 商品快照含每次读取都会变化的 valid_until；价格、包装及排期单独参与比较。
            foreach (['fresh','pricing'] as $name) {
                foreach (${$name}['delivery_batches'] as &$batch) {
                    foreach ($batch['items'] as &$item) unset($item['snapshot']);
                    unset($item);
                }
                unset($batch);
            }
            foreach (['exclusive_delivery','delivery_batches','shipping_fee_cent','payable_amount_cent'] as $key) {
                if (Json::canonical($fresh[$key] ?? null) !== Json::canonical($pricing[$key])) throw new DomainException('商品、配送安排或费用已变化，请重新确认',40922,409);
            }
            return;
        }
        foreach ($pricing['items'] as $item) {
            $sku = (new CatalogService())->getSku($item['sku_id'], false);
            if ((int)$sku['price_cent'] !== (int)$item['unit_price_cent']) {
                throw new DomainException('商品价格已变化，请重新结算', 40922, 409, ['sku_id' => $item['sku_id']]);
            }
        }
    }

    protected function createNormalOrder(array $session, array $pricing, array $payload, $requestId)
    {
        $reservations = [];
        try {
            foreach ($pricing['items'] as $index => $item) {
                $reservations[] = (new InventoryService())->reserve($item['sku_id'], $item['quantity'], 'checkout', $session['checkout_token_hash'], $index, $requestId, time() + 1800);
            }
            $result = $this->persistOrder($session, $pricing, $payload, $requestId, 'normal', $reservations);
            return $result;
        } catch (\Exception $e) {
            foreach ($reservations as $reservation) {
                try {
                    (new InventoryService())->release($reservation['reservation_sn'], 'order_create_failed', $requestId);
                } catch (\Exception $ignored) {
                }
            }
            throw $e;
        }
    }

    protected function createPlanOrder(array $session, array $pricing, array $payload, $requestId)
    {
        return $this->persistOrder($session, $pricing, $payload, $requestId, 'plan', []);
    }

    protected function persistOrder(array $session, array $pricing, array $payload, $requestId, $orderType, array $reservations)
    {
        $orderSn = Identifiers::make($orderType === 'plan' ? 'planorder' : 'order');
        $address = $pricing['address_snapshot'];
        $now = time();
        Db::startTrans();
        try {
            $amount = number_format($pricing['payable_amount_cent'] / 100, 2, '.', '');
            $orderId = Db::name('shop_order')->insertGetId([
                'order_sn' => $orderSn, 'user_id' => $session['user_id'], 'address_id' => $session['address_id'],
                'province_id' => $address['province_id'], 'city_id' => $address['city_id'], 'area_id' => $address['area_id'],
                'receiver' => $address['receiver'], 'address' => trim(($address['region'] ?? '') . ' ' . $address['detail']), 'zipcode' => $address['zipcode'],
                'mobile' => $address['mobile'], 'amount' => $amount,
                'discount' => number_format($pricing['discount_amount_cent'] / 100, 2, '.', ''),
                'shippingfee' => number_format($pricing['shipping_fee_cent'] / 100, 2, '.', ''),
                'goodsprice' => number_format($pricing['goods_amount_cent'] / 100, 2, '.', ''),
                'saleamount' => $amount, 'payamount' => '0.00', 'createtime' => $now, 'updatetime' => $now,
                'expiretime' => $now + 1800, 'orderstate' => 0, 'shippingstate' => 0, 'paystate' => 0,
                'memo' => isset($payload['remark']) ? $payload['remark'] : '', 'status' => 'normal',
                'order_type' => $orderType, 'row_version' => 1, 'request_id' => $requestId,
            ]);
            Db::name('shop_order_ext')->insert([
                'order_id' => $orderId, 'order_sn' => $orderSn, 'source_type' => $session['source_type'],
                'source_ref' => $session['source_ref'], 'source_version' => $session['source_version'],
                'checkout_token_hash' => $session['checkout_token_hash'], 'business_status' => 'created',
                'payment_status' => 'created', 'fulfillment_status' => 'pending', 'exception_status' => 'normal',
                'address_snapshot_json' => Json::encode($address), 'pricing_snapshot_json' => Json::encode($pricing),
                'request_id' => $requestId, 'row_version' => 1, 'createtime' => $now, 'updatetime' => $now,
            ]);

            if ($orderType === 'plan') {
                $this->persistPlanOrder($orderId, $orderSn, $session, $pricing, $now);
            } else {
                foreach ($pricing['items'] as $index => $item) {
                    $this->persistOrderItem($orderId, $orderSn, $item, 0, isset($reservations[$index]) ? $reservations[$index]['id'] : 0, $now);
                }
            }
            Db::name('shop_checkout_session')->where('id', $session['id'])->where('status', 'active')->update(['status' => 'consumed', 'updatetime' => $now]);
            if ($orderType !== 'plan' && empty($pricing['exclusive_delivery'])) (new DeliveryService())->reserveSlot($orderSn, (int)($pricing['delivery_slot_id'] ?? 0), $pricing['delivery_area_id']);
            if ($session['source_type'] === 'cart') {
                foreach ($pricing['cart_items'] as $cartItem) {
                    Db::name('shop_carts')->where('id', $cartItem['cart_item_id'])->where('user_id', $session['user_id'])->where('row_version', $cartItem['version'])->delete();
                }
            }
            Db::name('shop_order_consent')->where('checkout_token_hash', $session['checkout_token_hash'])->update(['order_id' => $orderId]);
            (new OutboxService())->append('order.created', 'order', $orderSn, 1, 'agent', ['order_sn' => $orderSn, 'order_type' => $orderType, 'request_id' => $requestId]);
            Db::commit();
        } catch (\Exception $e) {
            Db::rollback();
            throw $e;
        }
        return [
            'order_sn' => $orderSn, 'order_type' => $orderType, 'status' => 'created',
            'pay_status' => 'unpaid', 'payable_amount_cent' => (int)$pricing['payable_amount_cent'],
            'expire_at' => date(DATE_ATOM, $now + 1800), 'created_at' => date(DATE_ATOM, $now),
        ];
    }

    protected function persistPlanOrder($orderId, $orderSn, array $session, array $pricing, $now)
    {
        $plan = Db::name('shop_service_plan')->where('plan_sn', $session['source_ref'])->find();
        $version = Db::name('shop_service_plan_version')->where('plan_id', $plan['id'])->where('version_no', $session['source_version'])->find();
        $planOrderSn = Identifiers::make('po');
        $planOrderId = Db::name('shop_service_plan_order')->insertGetId([
            'plan_order_sn' => $planOrderSn, 'order_id' => $orderId, 'order_sn' => $orderSn,
            'plan_id' => $plan['id'], 'plan_version_id' => $version['id'], 'user_id' => $session['user_id'],
            'schedule_version' => 1, 'first_delivery_date' => $pricing['delivery_batches'][0]['delivery_date'],
            'delivery_frequency' => $pricing['delivery_frequency'] ?? 'daily', 'total_batches' => count($pricing['delivery_batches']), 'completed_batches' => 0,
            'total_amount_cent' => $pricing['payable_amount_cent'], 'goods_amount_cent' => $pricing['goods_amount_cent'],
            'shipping_fee_cent' => $pricing['shipping_fee_cent'], 'service_fee_cent' => $pricing['service_fee_cent'],
            'discount_amount_cent' => $pricing['discount_amount_cent'], 'fulfilled_amount_cent' => 0,
            'exception_refunded_amount_cent' => 0, 'user_cancellable' => 1,
            'non_refund_consent_id' => 0, 'policy_snapshot_json'=>Json::encode($pricing['policy_snapshot']), 'status' => 'pending_payment', 'row_version' => 1,
            'createtime' => $now, 'updatetime' => $now,
        ]);
        foreach ($pricing['delivery_batches'] as $batch) {
            $batchId = Db::name('shop_plan_delivery_batch')->insertGetId([
                'batch_sn' => Identifiers::make('batch'), 'plan_order_id' => $planOrderId,
                'batch_no' => $batch['batch_no'], 'schedule_version' => 1,
                'delivery_area_id'=>$batch['delivery_area_id'],
                'meal_date' => $batch['meal_date'], 'delivery_date' => $batch['delivery_date'],
                'meal_end_date' => $batch['meal_end_date'] ?? $batch['meal_date'],
                'menu_day_start' => $batch['menu_day_start'] ?? $batch['batch_no'],
                'menu_day_end' => $batch['menu_day_end'] ?? $batch['batch_no'],
                'inventory_lock_at' => $batch['inventory_lock_at'], 'delivery_slot_id' => $pricing['delivery_slot_id'],
                'cutoff_at' => $batch['inventory_lock_at'], 'address_snapshot_json' => Json::encode($pricing['address_snapshot']),
                'goods_amount_cent' => $batch['goods_amount_cent'], 'shipping_fee_cent' => $batch['shipping_fee_cent'],
                'service_fee_cent' => $batch['service_fee_cent'], 'discount_amount_cent' => $batch['discount_amount_cent'],
                'allocated_pay_amount_cent' => $batch['allocated_pay_amount_cent'], 'exception_refunded_amount_cent' => 0,
                'inventory_status' => 'pending', 'supplier_status' => 'pending', 'fulfillment_status' => 'pending',
                'aftersale_status' => 'none', 'status' => 'scheduled', 'row_version' => 1,
                'createtime' => $now, 'updatetime' => $now,
            ]);
            foreach ($batch['items'] as $item) {
                $batchItemId = Db::name('shop_plan_delivery_batch_item')->insertGetId([
                    'batch_id' => $batchId, 'goods_id' => $item['goods_id'], 'sku_id' => $item['sku_id'],
                    'quantity' => $item['quantity'], 'unit_price_cent' => $item['unit_price_cent'],
                    'line_amount_cent' => $item['line_amount_cent'], 'discount_allocated_cent' => 0,
                    'ingredient_codes_json' => Json::encode($item['ingredient_codes']),
                    'sku_snapshot_json' => Json::encode($item['snapshot']), 'status' => 'scheduled',
                    'createtime' => $now, 'updatetime' => $now,
                ]);
                $this->persistOrderItem($orderId, $orderSn, $item, $batchId, 0, $now, $batchItemId);
            }
        }
    }

    protected function persistOrderItem($orderId, $orderSn, array $item, $batchId, $reservationId, $now, $batchItemId = 0)
    {
        $snapshot = $item['snapshot'];
        $orderGoodsId = Db::name('shop_order_goods')->insertGetId([
            'order_sn' => $orderSn, 'goods_sn' => $snapshot['sku_code'], 'goods_id' => $item['goods_id'],
            'goods_sku_id' => $item['sku_id'], 'title' => $snapshot['product_name'], 'nums' => $item['quantity'],
            'marketprice' => number_format($item['unit_price_cent'] / 100, 2, '.', ''),
            'price' => number_format($item['unit_price_cent'] / 100, 2, '.', ''),
            'realprice' => number_format($item['line_amount_cent'] / 100, 2, '.', ''),
            'image' => $snapshot['image_url'], 'row_version' => 1,
        ]);
        Db::name('shop_order_goods_ext')->insert([
            'order_goods_id' => $orderGoodsId, 'order_id' => $orderId, 'order_sn' => $orderSn,
            'plan_batch_id' => $batchId, 'sku_snapshot_json' => Json::encode($snapshot),
            'ingredient_snapshot_json' => Json::encode($snapshot['ingredients']),
            'unit_price_cent' => $item['unit_price_cent'], 'line_amount_cent' => $item['line_amount_cent'],
            'discount_allocated_cent' => 0, 'refunded_quantity' => 0, 'refunded_amount_cent' => 0,
            'createtime' => $now, 'updatetime' => $now,
        ]);
        if ($batchItemId) {
            Db::name('shop_plan_delivery_batch_item')->where('id', $batchItemId)->update(['supplier_order_item_id' => 0]);
        }
    }

    protected function allocate($total, array $weights)
    {
        $count = count($weights);
        if ($count === 0) {
            return [];
        }
        $sum = array_sum($weights);
        if ($sum <= 0) {
            $weights = array_fill(0, $count, 1);
            $sum = $count;
        }
        $result = [];
        $allocated = 0;
        foreach ($weights as $index => $weight) {
            $value = $index === $count - 1 ? $total - $allocated : (int)floor($total * $weight / $sum);
            $result[] = $value;
            $allocated += $value;
        }
        return $result;
    }
}
