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
        $expiresAt = $now + 900;
        $pricing['address_snapshot'] = $delivery['snapshot'];
        $pricing['delivery_area_id'] = (string)$delivery['area']['id'];
        $pricing['delivery_slot_id'] = $delivery['slot'] ? (string)$delivery['slot']['id'] : '0';

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
            if ($payload['source_type'] === 'service_plan') {
                $policy = $pricing['non_refund_policy'];
                Db::name('shop_order_consent')->insert([
                    'consent_sn' => Identifiers::make('consent'), 'user_id' => $userId,
                    'order_id' => 0, 'checkout_token_hash' => $tokenHash,
                    'consent_type' => 'plan_non_refund', 'policy_version' => $policy['policy_version'],
                    'policy_title' => $policy['title'], 'policy_content_hash' => $policy['content_hash'],
                    'displayed_at' => isset($context['displayed_at']) ? (int)$context['displayed_at'] : $now,
                    'confirmed_at' => $now, 'confirm_action' => 'explicit_click',
                    'ip_hash' => !empty($context['ip']) ? hash('sha256', $context['ip']) : '',
                    'device_hash' => !empty($context['device_id']) ? hash('sha256', $context['device_id']) : '',
                    'request_id' => isset($context['request_id']) ? $context['request_id'] : '', 'createtime' => $now,
                ]);
            }
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
        $this->revalidatePricing($session, $pricing);
        if ($session['source_type'] === 'service_plan') {
            return $this->createPlanOrder($session, $pricing, $payload, $requestId);
        }
        return $this->createNormalOrder($session, $pricing, $payload, $requestId);
    }

    protected function pricePlan($userId, array $payload, array $delivery)
    {
        if (empty($payload['non_refund_ack'])) {
            throw new DomainException('购买专属计划前必须主动确认不退款提示', 40919, 409);
        }
        $policy = (new ServicePlanService())->policy();
        if (empty($payload['non_refund_policy_version']) || $payload['non_refund_policy_version'] !== $policy['policy_version']) {
            throw new DomainException('退款政策版本已更新，请重新阅读并确认', 40920, 409, ['current_policy' => $policy]);
        }
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
        $version = Db::name('shop_service_plan_version')->where('plan_id', $plan['id'])->where('version_no', $plan['current_version'])->find();
        $draft = Json::decode($version['pricing_draft_json'], []);
        $days = [];
        $warnings = isset($draft['issues']) ? $draft['issues'] : [];
        $goodsTotal = 0;
        foreach ((array)$draft['days'] as $day) {
            $dayTotal = 0;
            $items = [];
            foreach ((array)$day['items'] as $draftItem) {
                try {
                    $sku = (new CatalogService())->getSku($draftItem['sku_id'], false);
                    $quantity = max(1, (int)$draftItem['quantity']);
                    $line = $sku['price_cent'] * $quantity;
                    $items[] = [
                        'sku_id' => $sku['sku_id'], 'goods_id' => $sku['product_id'],
                        'quantity' => $quantity, 'unit_price_cent' => $sku['price_cent'],
                        'line_amount_cent' => $line, 'ingredient_code' => $draftItem['ingredient_code'],
                        'snapshot' => $sku,
                    ];
                    $dayTotal += $line;
                } catch (DomainException $e) {
                    $warnings[] = ['issue_code' => 'sku_unavailable', 'sku_id' => $draftItem['sku_id'], 'message' => $e->getMessage(), 'blocking' => true];
                }
            }
            $goodsTotal += $dayTotal;
            $days[] = ['day_no' => (int)$day['day_no'], 'goods_amount_cent' => $dayTotal, 'items' => $items];
        }
        if (count($days) !== 21) {
            throw new DomainException('计划交易草案不是完整21天', 40921, 409);
        }
        $config = get_addon_config('shop');
        $serviceFee = isset($config['v5_plan_service_fee_cent']) ? max(0, (int)$config['v5_plan_service_fee_cent']) : 0;
        $slotFee = $delivery['slot'] ? (int)$delivery['slot']['extra_fee_cent'] : 0;
        $shippingFee = $slotFee * 21;
        $discount = 0;
        $payable = $goodsTotal + $shippingFee + $serviceFee - $discount;
        $goodsAllocation = $this->allocate($goodsTotal, array_column($days, 'goods_amount_cent'));
        $shippingAllocation = $this->allocate($shippingFee, array_fill(0, 21, 1));
        $serviceAllocation = $this->allocate($serviceFee, array_fill(0, 21, 1));
        $discountAllocation = $this->allocate($discount, array_column($days, 'goods_amount_cent'));
        $first = strtotime($payload['first_delivery_date'] . ' 00:00:00');
        if (!$first) {
            throw new DomainException('首批配送日期无效', 40011, 400);
        }
        $batches = [];
        foreach ($days as $index => $day) {
            $deliveryDate = strtotime('+' . $index . ' day', $first);
            $amount = $goodsAllocation[$index] + $shippingAllocation[$index] + $serviceAllocation[$index] - $discountAllocation[$index];
            $batches[] = [
                'batch_no' => $index + 1, 'delivery_date' => date('Y-m-d', $deliveryDate),
                'meal_date' => date('Y-m-d', strtotime('+1 day', $deliveryDate)),
                'inventory_lock_at' => strtotime('-3 day', $deliveryDate),
                'goods_amount_cent' => $goodsAllocation[$index],
                'shipping_fee_cent' => $shippingAllocation[$index],
                'service_fee_cent' => $serviceAllocation[$index],
                'discount_amount_cent' => $discountAllocation[$index],
                'allocated_pay_amount_cent' => $amount, 'items' => $day['items'],
            ];
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
            'payable_amount_cent' => $payable, 'delivery_batches' => $batches,
            'non_refund_policy' => $policy, 'warnings' => $warnings,
        ];
    }

    protected function priceCommerce($userId, array $payload, array $delivery)
    {
        $sourceItems = isset($payload['items']) ? $payload['items'] : [];
        if ($payload['source_type'] === 'purchase_list') {
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
            $package = (new RecommendationPackageService())->getBySn($payload['source_ref'], $userId);
            if ((int)$package['package_version'] !== (int)$payload['source_version'] || $package['status'] !== 'available') {
                throw new DomainException('推荐包不可结算或版本已变化', 40906, 409);
            }
            $sourceItems = [];
            foreach ($package['items'] as $item) {
                $sourceItems[] = ['sku_id' => $item['sku_id'], 'quantity' => $item['quantity']];
            }
        }
        if (!$sourceItems) {
            throw new DomainException('结算商品不能为空', 40012, 400);
        }
        $items = [];
        $goodsTotal = 0;
        $warnings = [];
        foreach ($sourceItems as $sourceItem) {
            try {
                $sku = (new CatalogService())->getSku($sourceItem['sku_id'], false);
                $quantity = max(1, (int)$sourceItem['quantity']);
                $line = $sku['price_cent'] * $quantity;
                $items[] = ['sku_id' => $sku['sku_id'], 'goods_id' => $sku['product_id'], 'quantity' => $quantity, 'unit_price_cent' => $sku['price_cent'], 'line_amount_cent' => $line, 'snapshot' => $sku];
                $goodsTotal += $line;
            } catch (DomainException $e) {
                $warnings[] = ['issue_code' => 'sku_unavailable', 'sku_id' => isset($sourceItem['sku_id']) ? (string)$sourceItem['sku_id'] : null, 'message' => $e->getMessage(), 'blocking' => true];
            }
        }
        $shipping = $delivery['slot'] ? (int)$delivery['slot']['extra_fee_cent'] : 0;
        return [
            'source_type' => $payload['source_type'], 'source_ref' => $payload['source_ref'],
            'source_version' => (int)$payload['source_version'], 'items' => $items,
            'goods_amount_cent' => $goodsTotal, 'discount_amount_cent' => 0,
            'shipping_fee_cent' => $shipping, 'service_fee_cent' => 0,
            'payable_amount_cent' => $goodsTotal + $shipping, 'delivery_batches' => [],
            'non_refund_policy' => null, 'warnings' => $warnings,
        ];
    }

    protected function revalidatePricing(array $session, array $pricing)
    {
        if ((int)$session['expires_at'] <= time()) {
            throw new DomainException('结算令牌已过期', 40918, 409);
        }
        if ($session['source_type'] === 'service_plan') {
            $plan = Db::name('shop_service_plan')->where('plan_sn', $session['source_ref'])->find();
            if (!$plan || (int)$plan['current_version'] !== (int)$session['source_version'] || $plan['status'] !== 'available') {
                throw new DomainException('计划版本或状态已变化，请重新结算', 40906, 409);
            }
            $policy = (new ServicePlanService())->policy();
            if ($policy['policy_version'] !== $pricing['non_refund_policy']['policy_version']) {
                throw new DomainException('退款政策已更新，请重新确认', 40920, 409);
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
        $consent = Db::name('shop_order_consent')->where('checkout_token_hash', $session['checkout_token_hash'])
            ->where('consent_type', 'plan_non_refund')->find();
        if (!$consent) {
            throw new DomainException('缺少专属计划不退款确认凭证', 40919, 409);
        }
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
                'receiver' => $address['receiver'], 'address' => $address['detail'], 'zipcode' => $address['zipcode'],
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
        $consentId = Db::name('shop_order_consent')->where('checkout_token_hash', $session['checkout_token_hash'])->value('id');
        $planOrderSn = Identifiers::make('po');
        $planOrderId = Db::name('shop_service_plan_order')->insertGetId([
            'plan_order_sn' => $planOrderSn, 'order_id' => $orderId, 'order_sn' => $orderSn,
            'plan_id' => $plan['id'], 'plan_version_id' => $version['id'], 'user_id' => $session['user_id'],
            'schedule_version' => 1, 'first_delivery_date' => $pricing['delivery_batches'][0]['delivery_date'],
            'delivery_frequency' => 'daily', 'total_batches' => 21, 'completed_batches' => 0,
            'total_amount_cent' => $pricing['payable_amount_cent'], 'goods_amount_cent' => $pricing['goods_amount_cent'],
            'shipping_fee_cent' => $pricing['shipping_fee_cent'], 'service_fee_cent' => $pricing['service_fee_cent'],
            'discount_amount_cent' => $pricing['discount_amount_cent'], 'fulfilled_amount_cent' => 0,
            'exception_refunded_amount_cent' => 0, 'user_cancellable' => 0,
            'non_refund_consent_id' => $consentId, 'status' => 'pending_payment', 'row_version' => 1,
            'createtime' => $now, 'updatetime' => $now,
        ]);
        foreach ($pricing['delivery_batches'] as $batch) {
            $batchId = Db::name('shop_plan_delivery_batch')->insertGetId([
                'batch_sn' => Identifiers::make('batch'), 'plan_order_id' => $planOrderId,
                'batch_no' => $batch['batch_no'], 'schedule_version' => 1,
                'meal_date' => $batch['meal_date'], 'delivery_date' => $batch['delivery_date'],
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
                    'ingredient_codes_json' => Json::encode([$item['ingredient_code']]),
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
