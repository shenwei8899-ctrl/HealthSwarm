<?php

namespace addons\shop\library\service;

use RuntimeException;
use think\Db;

class OrderSubstitutionService
{
    public static function confirm($orderSn, $substitutionId, $userId)
    {
        $orderSn = trim((string)$orderSn);
        $substitutionId = (int)$substitutionId;
        $userId = (int)$userId;
        Db::startTrans();
        try {
            $order = Db::name('shop_order')->where('order_sn', $orderSn)->where('user_id', $userId)->lock(true)->find();
            if (!$order) {
                throw new RuntimeException('订单不存在', 404);
            }
            $substitution = Db::name('shop_order_substitution')
                ->where('id', $substitutionId)->where('order_id', (int)$order['id'])->lock(true)->find();
            if (!$substitution) {
                throw new RuntimeException('替代确认记录不存在', 404);
            }
            if ($substitution['status'] === 'CONFIRMED') {
                Db::commit();
                return self::normalize($substitution);
            }
            if ($substitution['status'] !== 'PENDING_CONFIRM') {
                throw new RuntimeException('当前替代记录不能确认', 409);
            }
            if ((int)$order['orderstate'] !== 0 || (int)$order['shippingstate'] !== 0) {
                throw new RuntimeException('订单已取消、完成或发货，不能替换商品', 409);
            }

            $orderGoods = Db::name('shop_order_goods')->where('id', (int)$substitution['order_goods_id'])->where('order_sn', $orderSn)->lock(true)->find();
            $extension = $orderGoods ? Db::name('shop_order_goods_ext')->where('order_goods_id', (int)$orderGoods['id'])->lock(true)->find() : null;
            if (!$orderGoods || !$extension || (int)$extension['shipped_quantity'] > 0 || (int)$extension['refunded_quantity'] > 0) {
                throw new RuntimeException('订单商品已出库或进入售后，不能替换', 409);
            }
            if ((int)$orderGoods['goods_id'] !== (int)$substitution['from_goods_id']
                || (int)$orderGoods['goods_sku_id'] !== (int)$substitution['from_goods_sku_id']) {
                throw new RuntimeException('原订单商品与替代记录不一致', 409);
            }
            $relationship = Db::name('shop_goods_substitute')
                ->where('goods_id', (int)$substitution['from_goods_id'])
                ->where('goods_sku_id', (int)$substitution['from_goods_sku_id'])
                ->where('substitute_goods_id', (int)$substitution['to_goods_id'])
                ->where('substitute_goods_sku_id', (int)$substitution['to_goods_sku_id'])
                ->where('status', 'normal')->find();
            if (!$relationship) {
                throw new RuntimeException('替代商品关系已失效', 409);
            }
            self::validateConstraints($substitution);

            $sources = InventoryService::listAvailableSources(
                (int)$substitution['to_goods_id'],
                (int)$substitution['to_goods_sku_id'],
                (int)$orderGoods['nums']
            );
            $region = ['province_id' => (int)$order['province_id'], 'city_id' => (int)$order['city_id'], 'area_id' => (int)$order['area_id']];
            $selected = null;
            foreach ($sources as $source) {
                if ((int)$substitution['to_supplier_id'] > 0 && (int)$source['supplier_id'] !== (int)$substitution['to_supplier_id']) {
                    continue;
                }
                if (ProductMatchService::isRegionDeliverable((int)$source['supplier_id'], $region)) {
                    $selected = $source;
                    break;
                }
            }
            if (!$selected) {
                throw new RuntimeException('替代商品无可配送库存', 409);
            }

            $newSupplierOrder = self::findOrCreateSupplierOrder($order, $selected);
            $bizNo = 'SUBSTITUTION:' . $substitutionId;
            InventoryService::reallocateOrderGoods(
                (int)$orderGoods['id'],
                (int)$selected['id'],
                (int)$orderGoods['nums'],
                $newSupplierOrder['supplier_order_sn'],
                $bizNo
            );

            $goods = Db::name('shop_goods')->where('id', (int)$substitution['to_goods_id'])->find();
            $sku = (int)$substitution['to_goods_sku_id'] > 0
                ? Db::name('shop_goods_sku')->where('id', (int)$substitution['to_goods_sku_id'])->find()
                : null;
            if (!$goods || $goods['status'] !== 'normal') {
                throw new RuntimeException('替代商品已下架', 409);
            }
            $now = time();
            Db::name('shop_order_goods')->where('id', (int)$orderGoods['id'])->update([
                'goods_id' => (int)$goods['id'],
                'goods_sku_id' => $sku ? (int)$sku['id'] : 0,
                'goods_sn' => $sku ? $sku['goods_sn'] : $goods['goods_sn'],
                'title' => $goods['title'],
                'image' => $sku && $sku['image'] ? $sku['image'] : $goods['image'],
                'marketprice' => $sku ? $sku['marketprice'] : $goods['marketprice'],
            ]);
            $snapshot = json_decode((string)$extension['goods_snapshot_json'], true) ?: [];
            $snapshot['substitution'] = [
                'id' => $substitutionId,
                'from_goods_id' => (int)$substitution['from_goods_id'],
                'from_goods_sku_id' => (int)$substitution['from_goods_sku_id'],
                'to_goods_id' => (int)$goods['id'],
                'to_goods_sku_id' => $sku ? (int)$sku['id'] : 0,
                'confirmed_at' => $now,
            ];
            Db::name('shop_order_goods_ext')->where('id', (int)$extension['id'])->update([
                'supplier_order_id' => (int)$newSupplierOrder['id'],
                'supplier_id' => (int)$selected['supplier_id'],
                'supplier_sku_id' => (int)$selected['supplier_sku_id'],
                'warehouse_id' => (int)$selected['warehouse_id'],
                'supply_price' => (string)($selected['supply_price'] ?: '0.00'),
                'goods_snapshot_json' => json_encode($snapshot, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'delivery_snapshot_json' => json_encode([
                    'supplier_id' => (int)$selected['supplier_id'],
                    'supplier_name' => $selected['supplier_name'] ?: '平台自营',
                    'warehouse_id' => (int)$selected['warehouse_id'],
                    'fulfillment_mode' => $selected['fulfillment_mode'] ?: 'PLATFORM_WAREHOUSE',
                    'delivery_days' => (int)$selected['delivery_days'],
                ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'updatetime' => $now,
            ]);
            if ((int)$extension['shopping_list_item_id'] > 0) {
                Db::name('shop_shopping_list_item')->where('id', (int)$extension['shopping_list_item_id'])->update([
                    'selected_goods_id' => (int)$goods['id'],
                    'selected_goods_sku_id' => $sku ? (int)$sku['id'] : 0,
                    'selected_supplier_id' => (int)$selected['supplier_id'],
                    'substitution_confirmed' => 1,
                    'updatetime' => $now,
                ]);
            }
            Db::name('shop_order_substitution')->where('id', $substitutionId)->update([
                'to_supplier_id' => (int)$selected['supplier_id'],
                'status' => 'CONFIRMED',
                'confirmed_at' => $now,
                'updatetime' => $now,
            ]);
            self::refreshSupplierOrder((int)$extension['supplier_order_id']);
            self::refreshSupplierOrder((int)$newSupplierOrder['id']);
            Db::name('shop_order_snapshot')->insert([
                'order_id' => (int)$order['id'], 'order_sn' => $orderSn, 'snapshot_type' => 'FULFILLMENT',
                'snapshot_json' => json_encode(['event' => 'SUBSTITUTION_CONFIRMED', 'substitution_id' => $substitutionId, 'source' => $selected], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'createtime' => $now,
            ]);
            Db::name('shop_order_status_log')->insert([
                'order_id' => (int)$order['id'], 'order_sn' => $orderSn, 'supplier_order_id' => (int)$newSupplierOrder['id'],
                'status_type' => 'FULFILLMENT', 'from_status' => 'SUBSTITUTION_PENDING', 'to_status' => 'SUBSTITUTION_CONFIRMED',
                'biz_no' => $bizNo, 'operator_type' => 'USER', 'operator_id' => $userId, 'remark' => '用户确认替代商品', 'createtime' => $now,
            ]);
            $confirmed = Db::name('shop_order_substitution')->where('id', $substitutionId)->find();
            Db::commit();
            return self::normalize($confirmed);
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    public static function reject($orderSn, $substitutionId, $userId)
    {
        $orderSn = trim((string)$orderSn);
        $substitutionId = (int)$substitutionId;
        $userId = (int)$userId;
        Db::startTrans();
        try {
            $order = Db::name('shop_order')->where('order_sn', $orderSn)->where('user_id', $userId)->lock(true)->find();
            if (!$order) {
                throw new RuntimeException('订单不存在', 404);
            }
            $substitution = Db::name('shop_order_substitution')
                ->where('id', $substitutionId)
                ->where('order_id', (int)$order['id'])
                ->lock(true)
                ->find();
            if (!$substitution) {
                throw new RuntimeException('替代确认记录不存在', 404);
            }
            if ($substitution['status'] === 'REJECTED') {
                $aftersalesId = 0;
                if ((int)$order['paystate'] === 1) {
                    $aftersalesId = (int)Db::name('shop_order_aftersales')
                        ->where('order_id', (int)$order['id'])
                        ->where('order_goods_id', (int)$substitution['order_goods_id'])
                        ->where('reason', '拒绝缺货替代商品')
                        ->order('id DESC')
                        ->value('id');
                }
                Db::commit();
                return [
                    'substitution' => self::normalize($substitution),
                    'order_cancelled' => (int)$order['orderstate'] === 1,
                    'aftersales_id' => $aftersalesId,
                ];
            }
            if ($substitution['status'] !== 'PENDING_CONFIRM') {
                throw new RuntimeException('当前替代记录不能拒绝', 409);
            }
            if ((int)$order['orderstate'] !== 0 || (int)$order['shippingstate'] !== 0) {
                throw new RuntimeException('订单已取消、完成或发货，不能拒绝替换', 409);
            }
            $orderGoods = Db::name('shop_order_goods')
                ->where('id', (int)$substitution['order_goods_id'])
                ->where('order_sn', $orderSn)
                ->lock(true)
                ->find();
            $extension = $orderGoods
                ? Db::name('shop_order_goods_ext')->where('order_goods_id', (int)$orderGoods['id'])->lock(true)->find()
                : null;
            if (!$orderGoods || !$extension || (int)$extension['shipped_quantity'] > 0 || (int)$extension['refunded_quantity'] > 0) {
                throw new RuntimeException('订单商品已出库或进入售后，不能拒绝替换', 409);
            }

            $aftersalesId = 0;
            $orderCancelled = false;
            if ((int)$order['paystate'] === 1) {
                $application = AfterSalesApplicationService::create(
                    (int)$orderGoods['id'],
                    $userId,
                    1,
                    (int)$orderGoods['nums'],
                    '拒绝缺货替代商品'
                );
                $aftersalesId = (int)$application['aftersales_id'];
            } else {
                OrderService::cancelUnpaid($orderSn, $userId);
                $orderCancelled = true;
            }

            $now = time();
            Db::name('shop_order_substitution')->where('id', $substitutionId)->update([
                'status' => 'REJECTED',
                'confirmed_at' => $now,
                'updatetime' => $now,
            ]);
            Db::commit();
            $substitution['status'] = 'REJECTED';
            $substitution['confirmed_at'] = $now;
            $substitution['updatetime'] = $now;
            return [
                'substitution' => self::normalize($substitution),
                'order_cancelled' => $orderCancelled,
                'aftersales_id' => $aftersalesId,
            ];
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    private static function validateConstraints(array $substitution)
    {
        $constraints = json_decode((string)$substitution['constraint_result_json'], true) ?: [];
        if (array_key_exists('allowed', $constraints) && !$constraints['allowed']) {
            throw new RuntimeException('替代商品不满足用户约束', 409);
        }
        $excluded = array_map('strval', (array)($constraints['excluded_allergen_tags'] ?? []));
        if ($excluded) {
            $tags = Db::name('shop_goods_ext')->where('goods_id', (int)$substitution['to_goods_id'])->value('allergen_tags_json');
            $tags = json_decode((string)$tags, true) ?: [];
            if (array_intersect($excluded, array_map('strval', $tags))) {
                throw new RuntimeException('替代商品包含用户排除的过敏原', 409);
            }
        }
    }

    private static function findOrCreateSupplierOrder(array $order, array $source)
    {
        $existing = Db::name('shop_order_supplier')->where('order_id', (int)$order['id'])
            ->where('supplier_id', (int)$source['supplier_id'])->where('warehouse_id', (int)$source['warehouse_id'])->lock(true)->find();
        if ($existing) {
            return $existing;
        }
        $sn = 'SO' . strtoupper(substr(hash('sha256', $order['order_sn'] . '|' . $source['supplier_id'] . '|' . $source['warehouse_id']), 0, 30));
        $id = Db::name('shop_order_supplier')->insertGetId([
            'supplier_order_sn' => $sn, 'order_id' => (int)$order['id'], 'order_sn' => $order['order_sn'],
            'supplier_id' => (int)$source['supplier_id'], 'warehouse_id' => (int)$source['warehouse_id'],
            'fulfillment_mode' => $source['fulfillment_mode'] ?: 'PLATFORM_WAREHOUSE', 'goods_amount' => '0.00',
            'shipping_fee' => '0.00', 'supply_amount' => '0.00', 'status' => (int)$order['paystate'] === 1 ? 'PENDING_ACCEPT' : 'PENDING_ASSIGN',
            'createtime' => time(), 'updatetime' => time(),
        ]);
        return Db::name('shop_order_supplier')->where('id', $id)->find();
    }

    private static function refreshSupplierOrder($supplierOrderId)
    {
        $supplierOrderId = (int)$supplierOrderId;
        $count = Db::name('shop_order_goods_ext')->where('supplier_order_id', $supplierOrderId)->count();
        if ($count === 0) {
            Db::name('shop_order_supplier')->where('id', $supplierOrderId)->update(['status' => 'CANCELLED', 'cancelled_at' => time(), 'goods_amount' => '0.00', 'supply_amount' => '0.00', 'updatetime' => time()]);
            return;
        }
        $amounts = Db::name('shop_order_goods_ext')->alias('ext')->join('__SHOP_ORDER_GOODS__ goods', 'goods.id=ext.order_goods_id')
            ->where('ext.supplier_order_id', $supplierOrderId)
            ->field('SUM(goods.price*goods.nums) AS goods_amount,SUM(ext.supply_price*goods.nums) AS supply_amount')->find();
        Db::name('shop_order_supplier')->where('id', $supplierOrderId)->update([
            'goods_amount' => $amounts['goods_amount'] ?: '0.00', 'supply_amount' => $amounts['supply_amount'] ?: '0.00', 'updatetime' => time(),
        ]);
    }

    private static function normalize(array $row)
    {
        foreach (['id','order_id','order_goods_id','from_supplier_id','from_goods_id','from_goods_sku_id','to_supplier_id','to_goods_id','to_goods_sku_id','confirmed_at'] as $field) {
            $row[$field] = (int)($row[$field] ?? 0);
        }
        $row['constraint_result'] = json_decode((string)($row['constraint_result_json'] ?? ''), true) ?: [];
        unset($row['constraint_result_json']);
        return $row;
    }
}
