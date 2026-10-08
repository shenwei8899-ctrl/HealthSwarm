<?php

namespace addons\shop\library\service;

use addons\shop\model\Address;
use addons\shop\model\Carts;
use addons\shop\model\Coupon;
use addons\shop\model\Freight;
use addons\shop\model\Order as OrderModel;
use addons\shop\model\OrderAction;
use addons\shop\model\OrderGoods;
use addons\shop\model\UserCoupon;
use RuntimeException;
use think\Db;

class OrderService
{
    public static function createFromCart(
        $addressId,
        $userId,
        $cartIds,
        $userCouponId,
        $memo,
        $idempotencyKey,
        $shoppingListId = 0,
        $shoppingListVersion = 0,
        $traceId = '',
        $checkoutToken = ''
    ) {
        $userId = (int)$userId;
        $idempotencyKey = trim((string)$idempotencyKey);
        if ($userId <= 0 || $idempotencyKey === '') {
            throw new RuntimeException('订单幂等键不能为空');
        }

        $existingExt = Db::name('shop_order_ext')
            ->where('user_id', $userId)
            ->where('idempotency_key', $idempotencyKey)
            ->find();
        if ($existingExt) {
            return OrderModel::get((int)$existingExt['order_id']);
        }

        $address = Address::get((int)$addressId);
        if (!$address || (int)$address['user_id'] !== $userId) {
            throw new RuntimeException('地址未找到', 404);
        }
        $cartProvenance = CartService::provenanceMap($userId, $cartIds);
        list($shoppingListId, $shoppingListVersion) = self::resolveShoppingListContext(
            $cartProvenance,
            $shoppingListId,
            $shoppingListVersion
        );
        self::validateShoppingList($shoppingListId, $shoppingListVersion, $userId);

        $config = get_addon_config('shop');
        $orderSn = self::orderNumber($userId);
        $now = time();
        $orderInfo = [
            'user_id' => $userId,
            'order_sn' => $orderSn,
            'address_id' => $address->id,
            'province_id' => $address->province_id,
            'city_id' => $address->city_id,
            'area_id' => $address->area_id,
            'receiver' => $address->receiver,
            'mobile' => $address->getData('mobile'),
            'address' => $address->address,
            'zipcode' => $address->zipcode,
            'goodsprice' => 0,
            'amount' => 0,
            'shippingfee' => 0,
            'discount' => 0,
            'saleamount' => 0,
            'memo' => $memo,
            'expiretime' => $now + (int)$config['order_timeout'],
            'status' => 'normal',
        ];

        list($orderItems, $goodsList, $userCoupon) = OrderModel::computeCarts(
            $orderInfo,
            $cartIds,
            $userId,
            $address->area_id,
            $userCouponId
        );
        $region = [
            'province_id' => (int)$address->province_id,
            'city_id' => (int)$address->city_id,
            'area_id' => (int)$address->area_id,
        ];
        $allocations = self::allocateSources($goodsList, $region, $cartProvenance);
        $groups = self::buildSupplierGroups($orderItems, $allocations, $region);
        self::applyPricing($orderInfo, $groups, $userCoupon, $userId, $orderItems);
        if ($checkoutToken !== '') {
            self::validateCheckoutToken($checkoutToken, $userId, $addressId, $cartIds, $orderInfo, $allocations);
        }

        Db::startTrans();
        try {
            $duplicate = Db::name('shop_order_ext')
                ->where('user_id', $userId)
                ->where('idempotency_key', $idempotencyKey)
                ->lock(true)
                ->find();
            if ($duplicate) {
                $existing = OrderModel::get((int)$duplicate['order_id']);
                Db::commit();
                return $existing;
            }

            $order = OrderModel::create($orderInfo, true);
            Db::name('shop_order_ext')->insert([
                'order_id' => (int)$order->id,
                'order_sn' => $orderSn,
                'user_id' => $userId,
                'idempotency_key' => $idempotencyKey,
                'shopping_list_id' => (int)$shoppingListId,
                'shopping_list_version' => (int)$shoppingListVersion,
                'biz_status' => 'PENDING_PAYMENT',
                'fulfillment_status' => 'PENDING',
                'refund_status' => 'NONE',
                'trace_id' => $traceId ?: bin2hex(random_bytes(16)),
                'version' => 0,
                'createtime' => $now,
                'updatetime' => $now,
            ]);

            $supplierOrderIds = [];
            foreach ($groups as $groupKey => $group) {
                $supplierOrderSn = self::supplierOrderNumber($orderSn, $group['supplier_id'], $group['warehouse_id']);
                $supplierOrderIds[$groupKey] = [
                    'id' => Db::name('shop_order_supplier')->insertGetId([
                        'supplier_order_sn' => $supplierOrderSn,
                        'order_id' => (int)$order->id,
                        'order_sn' => $orderSn,
                        'supplier_id' => $group['supplier_id'],
                        'warehouse_id' => $group['warehouse_id'],
                        'fulfillment_mode' => $group['fulfillment_mode'],
                        'goods_amount' => $group['goods_amount'],
                        'shipping_fee' => $group['shipping_fee'],
                        'supply_amount' => $group['supply_amount'],
                        'status' => 'PENDING_ASSIGN',
                        'createtime' => $now,
                        'updatetime' => $now,
                    ]),
                    'supplier_order_sn' => $supplierOrderSn,
                ];
            }

            foreach ($groups as $groupKey => $group) {
                $supplierOrderSn = $supplierOrderIds[$groupKey]['supplier_order_sn'];
                InventoryService::reserve(
                    self::supplierInventoryBizKey($supplierOrderSn),
                    $orderSn,
                    self::aggregateReservations($allocations, $groupKey),
                    (int)$orderInfo['expiretime'],
                    $supplierOrderSn
                );
            }

            $saleAmount = bcsub((string)$order['saleamount'], (string)$order['shippingfee'], 2);
            $saleRatio = (float)$order['goodsprice'] > 0 ? bcdiv($saleAmount, (string)$order['goodsprice'], 10) : '1';
            $saleRemains = $saleAmount;
            foreach ($orderItems as $index => $item) {
                if (!isset($orderItems[$index + 1])) {
                    $salePrice = $saleRemains;
                } else {
                    $lineAmount = bcmul((string)$item['price'], (string)$item['nums'], 2);
                    $salePrice = (float)$order['discount'] == 0 ? $lineAmount : bcmul($lineAmount, $saleRatio, 2);
                }
                $saleRemains = bcsub($saleRemains, $salePrice, 2);
                $item['realprice'] = $salePrice;
                $orderGoods = OrderGoods::create($item, true);

                $allocation = $allocations[$index];
                $groupKey = self::groupKey($allocation);
                $supplierOrder = $supplierOrderIds[$groupKey];
                Db::name('shop_order_goods_ext')->insert([
                    'order_goods_id' => (int)$orderGoods->id,
                    'supplier_order_id' => (int)$supplierOrder['id'],
                    'supplier_id' => (int)$allocation['supplier_id'],
                    'supplier_sku_id' => (int)$allocation['supplier_sku_id'],
                    'warehouse_id' => (int)$allocation['warehouse_id'],
                    'shopping_list_item_id' => (int)$allocation['shopping_list_item_id'],
                    'ingredient_id' => (int)$allocation['ingredient_id'],
                    'supply_price' => (string)$allocation['supply_price'],
                    'goods_snapshot_json' => json_encode(self::goodsSnapshot($item, $allocation), JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                    'delivery_snapshot_json' => json_encode(self::deliverySnapshot($allocation, $address), JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                    'shipped_quantity' => 0,
                    'refunded_quantity' => 0,
                    'createtime' => $now,
                    'updatetime' => $now,
                ]);
            }

            Db::name('shop_order_snapshot')->insert([
                'order_id' => (int)$order->id,
                'order_sn' => $orderSn,
                'snapshot_type' => 'ORDER',
                'snapshot_json' => json_encode([
                    'order' => $orderInfo,
                    'items' => $orderItems,
                    'allocations' => $allocations,
                    'shopping_list_id' => (int)$shoppingListId,
                    'shopping_list_version' => (int)$shoppingListVersion,
                    'checkout_token' => $checkoutToken,
                ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'createtime' => $now,
            ]);
            self::statusLog((int)$order->id, $orderSn, 'ORDER', '', 'PENDING_PAYMENT', $idempotencyKey, '订单创建');

            $address->setInc('usednums');
            if (!empty($userCoupon)) {
                $userCoupon->save(['is_used' => 2]);
            }
            if ($shoppingListId) {
                Db::name('shop_shopping_list')->where('id', (int)$shoppingListId)->update([
                    'status' => 'ORDERED',
                    'updatetime' => $now,
                ]);
            }
            CartService::clearExtensions($cartIds);
            Carts::clear($cartIds);
            Db::commit();
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }

        OrderAction::push($orderSn, '系统', '订单创建成功，库存已锁定');
        if ((float)$order['saleamount'] === 0.0) {
            OrderModel::settle($order->order_sn, 0);
            $order = OrderModel::get($order->id);
        }
        return $order;
    }

    public static function previewCart(
        $addressId,
        $userId,
        $cartIds,
        $userCouponId = 0,
        $shoppingListId = 0,
        $shoppingListVersion = 0
    ) {
        $userId = (int)$userId;
        $address = Address::get((int)$addressId);
        if (!$address || (int)$address['user_id'] !== $userId) {
            throw new RuntimeException('地址未找到', 404);
        }
        $cartProvenance = CartService::provenanceMap($userId, $cartIds);
        list($shoppingListId, $shoppingListVersion) = self::resolveShoppingListContext(
            $cartProvenance,
            $shoppingListId,
            $shoppingListVersion
        );
        self::validateShoppingList($shoppingListId, $shoppingListVersion, $userId);

        $orderInfo = [
            'order_sn' => 'CHECKOUT-' . $userId,
            'goodsprice' => 0,
            'amount' => 0,
            'shippingfee' => 0,
            'discount' => 0,
            'saleamount' => 0,
        ];
        list($orderItems, $goodsList, $userCoupon) = OrderModel::computeCarts(
            $orderInfo,
            $cartIds,
            $userId,
            $address->area_id,
            $userCouponId
        );
        $region = [
            'province_id' => (int)$address->province_id,
            'city_id' => (int)$address->city_id,
            'area_id' => (int)$address->area_id,
        ];
        $allocations = self::allocateSources($goodsList, $region, $cartProvenance);
        $groups = self::buildSupplierGroups($orderItems, $allocations, $region);
        self::applyPricing($orderInfo, $groups, $userCoupon, $userId, $orderItems);
        $token = self::makeCheckoutToken($userId, $addressId, $cartIds, $orderInfo, $allocations);

        $items = [];
        foreach ($orderItems as $index => $item) {
            $allocation = $allocations[$index];
            $items[] = [
                'cart_id' => (int)$allocation['cart_id'],
                'goods_id' => (int)$item['goods_id'],
                'goods_sku_id' => (int)$item['goods_sku_id'],
                'title' => $item['title'],
                'image' => $item['image'],
                'attrdata' => $item['attrdata'],
                'quantity' => (int)$item['nums'],
                'unit_price' => (string)$item['price'],
                'line_amount' => (string)$item['amount'],
                'supplier_id' => (int)$allocation['supplier_id'],
                'supplier_name' => $allocation['supplier_name'],
                'warehouse_id' => (int)$allocation['warehouse_id'],
                'fulfillment_mode' => $allocation['fulfillment_mode'],
                'delivery_days' => (int)$allocation['delivery_days'],
                'available_quantity' => (int)$allocation['available_quantity'],
                'shopping_list_item_id' => (int)$allocation['shopping_list_item_id'],
                'ingredient_id' => (int)$allocation['ingredient_id'],
            ];
        }
        $supplierGroups = [];
        foreach ($groups as $group) {
            $supplierGroups[] = [
                'supplier_id' => (int)$group['supplier_id'],
                'warehouse_id' => (int)$group['warehouse_id'],
                'fulfillment_mode' => $group['fulfillment_mode'],
                'goods_amount' => $group['goods_amount'],
                'shipping_fee' => $group['shipping_fee'],
            ];
        }
        return [
            'cart_ids' => self::normalizeIds($cartIds),
            'shopping_list_id' => (int)$shoppingListId,
            'shopping_list_version' => (int)$shoppingListVersion,
            'address' => [
                'id' => (int)$address->id,
                'receiver' => $address->receiver,
                'mobile' => self::maskMobile($address->getData('mobile')),
                'province_id' => (int)$address->province_id,
                'city_id' => (int)$address->city_id,
                'area_id' => (int)$address->area_id,
                'address' => $address->address,
            ],
            'pricing' => [
                'goods_amount' => (string)$orderInfo['goodsprice'],
                'shipping_fee' => (string)$orderInfo['shippingfee'],
                'discount' => (string)$orderInfo['discount'],
                'payable_amount' => (string)$orderInfo['saleamount'],
            ],
            'items' => $items,
            'supplier_orders' => $supplierGroups,
            'checkout_token' => $token,
            'expires_at' => (int)explode('.', $token, 2)[0] + 600,
        ];
    }

    public static function cancelUnpaid($orderSn, $userId, $reason = '用户取消订单')
    {
        Db::startTrans();
        try {
            $order = Db::name('shop_order')
                ->where('order_sn', (string)$orderSn)
                ->where('user_id', (int)$userId)
                ->lock(true)
                ->find();
            if (!$order) {
                throw new RuntimeException('订单不存在', 404);
            }
            if ((int)$order['orderstate'] === 1 || (int)$order['orderstate'] === 2) {
                Db::commit();
                return OrderModel::get((int)$order['id']);
            }
            if ((int)$order['paystate'] !== 0 || (int)$order['orderstate'] !== 0) {
                throw new RuntimeException('订单当前状态不允许取消', 409);
            }

            $now = time();
            $hasOrderExtension = (bool)Db::name('shop_order_ext')->where('order_id', (int)$order['id'])->find();
            Db::name('shop_order')->where('id', (int)$order['id'])->update([
                'orderstate' => 1,
                'canceltime' => $now,
                'updatetime' => $now,
            ]);
            Db::name('shop_order_ext')->where('order_id', (int)$order['id'])->update([
                'biz_status' => 'CANCELLED',
                'fulfillment_status' => 'CANCELLED',
                'version' => Db::raw('version + 1'),
                'updatetime' => $now,
            ]);
            Db::name('shop_order_supplier')->where('order_id', (int)$order['id'])->update([
                'status' => 'CANCELLED',
                'cancelled_at' => $now,
                'updatetime' => $now,
            ]);
            $supplierOrderNumbers = Db::name('shop_order_supplier')
                ->where('order_id', (int)$order['id'])
                ->column('supplier_order_sn');
            foreach ($supplierOrderNumbers as $supplierOrderSn) {
                InventoryService::releaseByBizKey(self::supplierInventoryBizKey($supplierOrderSn), $reason);
            }
            if (!$hasOrderExtension) {
                OrderGoods::setGoodsStocksInc($orderSn);
            }
            UserCoupon::resetUserCoupon($order['user_coupon_id'], $orderSn);
            self::statusLog((int)$order['id'], $orderSn, 'ORDER', 'PENDING_PAYMENT', 'CANCELLED', $orderSn, $reason);
            Db::commit();
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }

        OrderAction::push($orderSn, '系统', $reason);
        return OrderModel::get((int)$order['id']);
    }

    public static function expireUnpaid($orderSn)
    {
        $order = Db::name('shop_order')->where('order_sn', (string)$orderSn)->find();
        if (!$order || (int)$order['paystate'] !== 0 || (int)$order['orderstate'] !== 0 || (int)$order['expiretime'] > time()) {
            return false;
        }
        self::cancelUnpaid($orderSn, (int)$order['user_id'], '订单支付超时关闭');
        Db::name('shop_order')->where('id', (int)$order['id'])->update(['orderstate' => 2]);
        Db::name('shop_order_ext')->where('order_id', (int)$order['id'])->update(['biz_status' => 'CLOSED', 'updatetime' => time()]);
        return true;
    }

    private static function allocateSources($goodsList, array $region, array $cartProvenance = [])
    {
        $allocations = [];
        foreach ($goodsList as $item) {
            $sources = InventoryService::listAvailableSources(
                (int)$item->goods_id,
                (int)$item->goods_sku_id,
                (int)$item->nums
            );
            $provenance = isset($cartProvenance[(int)$item->id]) ? $cartProvenance[(int)$item->id] : [];
            $preferredSupplierId = isset($provenance['preferred_supplier_id'])
                ? (int)$provenance['preferred_supplier_id']
                : 0;
            $selected = null;
            if ($preferredSupplierId) {
                foreach ($sources as $source) {
                    if ((int)$source['supplier_id'] === $preferredSupplierId
                        && ProductMatchService::isRegionDeliverable((int)$source['supplier_id'], $region)) {
                        $selected = $source;
                        break;
                    }
                }
            }
            foreach ($sources as $source) {
                if ($selected) {
                    break;
                }
                if (ProductMatchService::isRegionDeliverable((int)$source['supplier_id'], $region)) {
                    $selected = $source;
                    break;
                }
            }
            if (!$selected) {
                throw new RuntimeException('商品库存不足或当前地址不可配送', 409);
            }
            $allocations[] = [
                'warehouse_sku_id' => (int)$selected['id'],
                'warehouse_id' => (int)$selected['warehouse_id'],
                'supplier_id' => (int)$selected['supplier_id'],
                'supplier_sku_id' => (int)$selected['supplier_sku_id'],
                'supplier_name' => $selected['supplier_name'] ?: '平台自营',
                'supply_price' => $selected['supply_price'] === null ? '0.00' : (string)$selected['supply_price'],
                'delivery_days' => $selected['delivery_days'] === null ? 0 : (int)$selected['delivery_days'],
                'fulfillment_mode' => $selected['fulfillment_mode'] ?: 'PLATFORM_WAREHOUSE',
                'quantity' => (int)$item->nums,
                'available_quantity' => (int)$selected['available_qty'],
                'inventory_version' => (int)$selected['version'],
                'cart_id' => (int)$item->id,
                'shopping_list_id' => isset($provenance['shopping_list_id']) ? (int)$provenance['shopping_list_id'] : 0,
                'shopping_list_item_id' => isset($provenance['shopping_list_item_id']) ? (int)$provenance['shopping_list_item_id'] : 0,
                'ingredient_id' => isset($provenance['ingredient_id']) ? (int)$provenance['ingredient_id'] : 0,
                'preferred_supplier_id' => $preferredSupplierId,
                'selected_supplier_id' => (int)$selected['supplier_id'],
                'shopping_list_version' => isset($provenance['shopping_list_version']) ? (int)$provenance['shopping_list_version'] : 0,
                'source_hash' => isset($provenance['source_hash']) ? $provenance['source_hash'] : '',
            ];
        }
        return $allocations;
    }

    private static function buildSupplierGroups(array $orderItems, array $allocations, array $region)
    {
        $groups = [];
        foreach ($orderItems as $index => $item) {
            $allocation = $allocations[$index];
            $key = self::groupKey($allocation);
            if (!isset($groups[$key])) {
                $groups[$key] = [
                    'supplier_id' => $allocation['supplier_id'],
                    'warehouse_id' => $allocation['warehouse_id'],
                    'fulfillment_mode' => $allocation['fulfillment_mode'],
                    'goods_amount' => '0.00',
                    'shipping_fee' => '0.00',
                    'supply_amount' => '0.00',
                    'freight_buckets' => [],
                ];
            }
            $lineAmount = bcmul((string)$item['price'], (string)$item['nums'], 2);
            $lineSupply = bcmul((string)$allocation['supply_price'], (string)$item['nums'], 2);
            $groups[$key]['goods_amount'] = bcadd($groups[$key]['goods_amount'], $lineAmount, 2);
            $groups[$key]['supply_amount'] = bcadd($groups[$key]['supply_amount'], $lineSupply, 2);
            if ($allocation['fulfillment_mode'] === 'PLATFORM_WAREHOUSE') {
                $freightId = (int)$item['freight_id'];
                if (!isset($groups[$key]['freight_buckets'][$freightId])) {
                    $groups[$key]['freight_buckets'][$freightId] = [
                        'nums' => 0,
                        'weight' => '0.00',
                        'amount' => '0.00',
                    ];
                }
                $groups[$key]['freight_buckets'][$freightId]['nums'] += (int)$item['nums'];
                $groups[$key]['freight_buckets'][$freightId]['weight'] = bcadd(
                    $groups[$key]['freight_buckets'][$freightId]['weight'],
                    bcmul((string)$item['weight'], (string)$item['nums'], 2),
                    2
                );
                $groups[$key]['freight_buckets'][$freightId]['amount'] = bcadd(
                    $groups[$key]['freight_buckets'][$freightId]['amount'],
                    $lineAmount,
                    2
                );
            }
        }

        foreach ($groups as &$group) {
            if ($group['fulfillment_mode'] === 'PLATFORM_WAREHOUSE') {
                foreach ($group['freight_buckets'] as $freightId => $bucket) {
                    $fee = Freight::calculate(
                        $freightId,
                        isset($region['area_id']) ? (int)$region['area_id'] : 0,
                        $bucket['nums'],
                        $bucket['weight'],
                        $bucket['amount']
                    );
                    $group['shipping_fee'] = bcadd($group['shipping_fee'], (string)$fee, 2);
                }
            } else {
                $group['shipping_fee'] = self::supplierDirectShippingFee(
                    (int)$group['supplier_id'],
                    $region,
                    $group['goods_amount']
                );
            }
            unset($group['freight_buckets']);
        }
        unset($group);
        return $groups;
    }

    private static function supplierDirectShippingFee($supplierId, array $region, $goodsAmount)
    {
        $rows = Db::name('shop_supplier_delivery_region')
            ->where('supplier_id', (int)$supplierId)
            ->where('status', 'normal')
            ->where(function ($query) use ($region) {
                $query->where('province_id', 0)->whereOr('province_id', (int)$region['province_id']);
            })
            ->where(function ($query) use ($region) {
                $query->where('city_id', 0)->whereOr('city_id', (int)$region['city_id']);
            })
            ->where(function ($query) use ($region) {
                $query->where('area_id', 0)->whereOr('area_id', (int)$region['area_id']);
            })
            ->select();
        if (!$rows) {
            throw new RuntimeException('供应商不支持当前配送地址', 409);
        }
        usort($rows, function ($left, $right) {
            $leftScore = ((int)$left['province_id'] > 0 ? 1 : 0) + ((int)$left['city_id'] > 0 ? 1 : 0) + ((int)$left['area_id'] > 0 ? 1 : 0);
            $rightScore = ((int)$right['province_id'] > 0 ? 1 : 0) + ((int)$right['city_id'] > 0 ? 1 : 0) + ((int)$right['area_id'] > 0 ? 1 : 0);
            return $rightScore <=> $leftScore;
        });
        $rule = $rows[0];
        if (bccomp((string)$rule['free_shipping_amount'], '0.00', 2) > 0
            && bccomp((string)$goodsAmount, (string)$rule['free_shipping_amount'], 2) >= 0) {
            return '0.00';
        }
        return (string)$rule['shipping_fee'];
    }

    private static function applyPricing(array &$orderInfo, array $groups, $userCoupon, $userId, array $orderItems)
    {
        $shippingFee = '0.00';
        foreach ($groups as $group) {
            $shippingFee = bcadd($shippingFee, (string)$group['shipping_fee'], 2);
        }
        $orderInfo['shippingfee'] = $shippingFee;
        $orderInfo['amount'] = bcadd((string)$orderInfo['goodsprice'], $shippingFee, 2);
        $orderInfo['discount'] = '0.00';
        if ($userCoupon) {
            $couponModel = new Coupon();
            $coupon = $couponModel->getCoupon($userCoupon['coupon_id'])
                ->checkCoupon()
                ->checkOpen()
                ->checkUseTime($userCoupon['createtime'])
                ->checkConditionGoods(
                    array_column($orderItems, 'goods_id'),
                    $userId,
                    array_column($orderItems, 'category_id'),
                    array_column($orderItems, 'brand_id')
                );
            $config = get_addon_config('shop');
            $couponBase = !isset($config['shippingfeecoupon']) || (int)$config['shippingfeecoupon'] === 0
                ? $orderInfo['goodsprice']
                : $orderInfo['amount'];
            list($unused, $discount) = $coupon->doBuy($couponBase);
            $orderInfo['discount'] = bcadd((string)min((float)$discount, (float)$orderInfo['amount']), '0', 2);
        }
        $orderInfo['saleamount'] = bcsub((string)$orderInfo['amount'], (string)$orderInfo['discount'], 2);
    }

    private static function makeCheckoutToken($userId, $addressId, $cartIds, array $orderInfo, array $allocations, $issuedAt = null)
    {
        $issuedAt = $issuedAt ?: time();
        return $issuedAt . '.' . hash('sha256', self::checkoutFingerprint(
            $userId,
            $addressId,
            $cartIds,
            $orderInfo,
            $allocations,
            $issuedAt
        ));
    }

    private static function validateCheckoutToken($token, $userId, $addressId, $cartIds, array $orderInfo, array $allocations)
    {
        $parts = explode('.', (string)$token, 2);
        $issuedAt = isset($parts[0]) ? (int)$parts[0] : 0;
        if (!$issuedAt || !isset($parts[1]) || time() - $issuedAt > 600 || $issuedAt > time() + 30) {
            throw new RuntimeException('结算预览已过期，请重新确认', 409);
        }
        $expected = self::makeCheckoutToken($userId, $addressId, $cartIds, $orderInfo, $allocations, $issuedAt);
        if (!hash_equals($expected, (string)$token)) {
            throw new RuntimeException('价格、库存或供应商已变化，请重新结算', 409);
        }
    }

    private static function checkoutFingerprint($userId, $addressId, $cartIds, array $orderInfo, array $allocations, $issuedAt)
    {
        $items = [];
        foreach ($allocations as $allocation) {
            $items[] = [
                'cart_id' => (int)$allocation['cart_id'],
                'warehouse_sku_id' => (int)$allocation['warehouse_sku_id'],
                'supplier_id' => (int)$allocation['supplier_id'],
                'quantity' => (int)$allocation['quantity'],
                'available_quantity' => (int)$allocation['available_quantity'],
                'inventory_version' => (int)$allocation['inventory_version'],
                'source_hash' => $allocation['source_hash'],
            ];
        }
        return json_encode([
            'issued_at' => (int)$issuedAt,
            'user_id' => (int)$userId,
            'address_id' => (int)$addressId,
            'cart_ids' => self::normalizeIds($cartIds),
            'goods_amount' => (string)$orderInfo['goodsprice'],
            'shipping_fee' => (string)$orderInfo['shippingfee'],
            'discount' => (string)$orderInfo['discount'],
            'payable_amount' => (string)$orderInfo['saleamount'],
            'items' => $items,
        ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    }

    private static function normalizeIds($ids)
    {
        if (is_string($ids)) {
            $ids = preg_split('/\s*,\s*/', trim($ids), -1, PREG_SPLIT_NO_EMPTY);
        }
        if (!is_array($ids)) {
            $ids = $ids ? [$ids] : [];
        }
        $ids = array_values(array_unique(array_filter(array_map('intval', $ids))));
        sort($ids);
        return $ids;
    }

    private static function maskMobile($mobile)
    {
        return preg_replace('/^(\d{3})\d+(\d{4})$/', '$1****$2', (string)$mobile);
    }

    private static function aggregateReservations(array $allocations, $groupKey = null)
    {
        $aggregated = [];
        foreach ($allocations as $allocation) {
            if ($groupKey !== null && self::groupKey($allocation) !== $groupKey) {
                continue;
            }
            $id = (int)$allocation['warehouse_sku_id'];
            if (!isset($aggregated[$id])) {
                $aggregated[$id] = ['warehouse_sku_id' => $id, 'quantity' => 0];
            }
            $aggregated[$id]['quantity'] += (int)$allocation['quantity'];
        }
        return array_values($aggregated);
    }

    private static function validateShoppingList($shoppingListId, $shoppingListVersion, $userId)
    {
        if (!$shoppingListId) {
            return;
        }
        $list = Db::name('shop_shopping_list')
            ->where('id', (int)$shoppingListId)
            ->where('user_id', (int)$userId)
            ->find();
        if (!$list || $list['status'] !== 'CONFIRMED') {
            throw new RuntimeException('购物清单不存在或尚未确认', 409);
        }
        if ((int)$list['list_version'] !== (int)$shoppingListVersion) {
            throw new RuntimeException('购物清单版本已变化，请重新结算', 409);
        }
    }

    private static function resolveShoppingListContext(array $provenance, $shoppingListId, $shoppingListVersion)
    {
        $shoppingListId = (int)$shoppingListId;
        $shoppingListVersion = (int)$shoppingListVersion;
        $contexts = [];
        foreach ($provenance as $source) {
            $key = (int)$source['shopping_list_id'] . ':' . (int)$source['shopping_list_version'];
            $contexts[$key] = [
                'id' => (int)$source['shopping_list_id'],
                'version' => (int)$source['shopping_list_version'],
            ];
            if ($shoppingListId && (int)$source['shopping_list_id'] !== $shoppingListId) {
                throw new RuntimeException('购物车包含其他购物清单来源，请重新结算', 409);
            }
            if ($shoppingListVersion && (int)$source['shopping_list_version'] !== $shoppingListVersion) {
                throw new RuntimeException('购物清单版本已变化，请重新结算', 409);
            }
        }
        if (!$shoppingListId && count($contexts) === 1) {
            $context = reset($contexts);
            return [$context['id'], $context['version']];
        }
        if ($shoppingListId && !$shoppingListVersion) {
            throw new RuntimeException('购物清单版本不能为空', 422);
        }
        return [$shoppingListId, $shoppingListVersion];
    }

    private static function goodsSnapshot(array $item, array $allocation)
    {
        return [
            'goods_id' => (int)$item['goods_id'],
            'goods_sku_id' => (int)$item['goods_sku_id'],
            'goods_sn' => $item['goods_sn'],
            'title' => $item['title'],
            'attrdata' => $item['attrdata'],
            'image' => $item['image'],
            'price' => (string)$item['price'],
            'marketprice' => (string)$item['marketprice'],
            'quantity' => (int)$item['nums'],
            'supplier_id' => (int)$allocation['supplier_id'],
            'supplier_sku_id' => (int)$allocation['supplier_sku_id'],
            'supply_price' => (string)$allocation['supply_price'],
            'shopping_list_id' => (int)$allocation['shopping_list_id'],
            'shopping_list_item_id' => (int)$allocation['shopping_list_item_id'],
            'ingredient_id' => (int)$allocation['ingredient_id'],
            'preferred_supplier_id' => (int)$allocation['preferred_supplier_id'],
            'selected_supplier_id' => (int)$allocation['selected_supplier_id'],
            'shopping_list_version' => (int)$allocation['shopping_list_version'],
            'source_hash' => $allocation['source_hash'],
        ];
    }

    private static function deliverySnapshot(array $allocation, $address)
    {
        return [
            'supplier_id' => (int)$allocation['supplier_id'],
            'supplier_name' => $allocation['supplier_name'],
            'warehouse_id' => (int)$allocation['warehouse_id'],
            'fulfillment_mode' => $allocation['fulfillment_mode'],
            'delivery_days' => (int)$allocation['delivery_days'],
            'province_id' => (int)$address->province_id,
            'city_id' => (int)$address->city_id,
            'area_id' => (int)$address->area_id,
        ];
    }

    private static function statusLog($orderId, $orderSn, $statusType, $fromStatus, $toStatus, $bizNo, $remark)
    {
        Db::name('shop_order_status_log')->insert([
            'order_id' => (int)$orderId,
            'order_sn' => $orderSn,
            'supplier_order_id' => 0,
            'status_type' => $statusType,
            'from_status' => $fromStatus,
            'to_status' => $toStatus,
            'biz_no' => $bizNo,
            'operator_type' => 'SYSTEM',
            'operator_id' => 0,
            'remark' => $remark,
            'createtime' => time(),
        ]);
    }

    private static function groupKey(array $allocation)
    {
        return $allocation['supplier_id'] . ':' . $allocation['warehouse_id'] . ':' . $allocation['fulfillment_mode'];
    }

    private static function orderNumber($userId)
    {
        return date('YmdHis') . sprintf('%08d', $userId) . strtoupper(bin2hex(random_bytes(3)));
    }

    private static function supplierOrderNumber($orderSn, $supplierId, $warehouseId)
    {
        return 'SO' . strtoupper(substr(hash('sha256', $orderSn . '|' . $supplierId . '|' . $warehouseId), 0, 30));
    }

    public static function supplierInventoryBizKey($supplierOrderSn)
    {
        return 'SUPPLIER_ORDER:' . $supplierOrderSn;
    }
}
