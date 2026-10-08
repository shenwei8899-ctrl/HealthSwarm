<?php

namespace addons\shop\library\service;

use RuntimeException;
use think\Db;

/**
 * Warehouse inventory is the source of truth for all new shop flows.
 */
class InventoryService
{
    public static function getAvailability($warehouseSkuId)
    {
        $row = Db::name('shop_warehouse_sku')->where('id', (int)$warehouseSkuId)->find();
        if (!$row) {
            throw new RuntimeException('库存记录不存在', 404);
        }

        return self::appendAvailableQuantity($row);
    }

    public static function listAvailableSources($goodsId, $goodsSkuId = 0, $quantity = 1)
    {
        $quantity = self::positiveQuantity($quantity);
        $rows = Db::name('shop_warehouse_sku')
            ->alias('ws')
            ->join('__SHOP_WAREHOUSE__ w', 'w.id = ws.warehouse_id')
            ->join('__SHOP_SUPPLIER__ s', 's.id = ws.supplier_id', 'LEFT')
            ->join('__SHOP_SUPPLIER_SKU__ ss', 'ss.id = ws.supplier_sku_id', 'LEFT')
            ->where('ws.goods_id', (int)$goodsId)
            ->where('ws.goods_sku_id', (int)$goodsSkuId)
            ->where('w.status', 'normal')
            ->where('ws.on_hand_qty - ws.locked_qty - ws.unavailable_qty >= ' . $quantity)
            ->where(function ($query) {
                $query->where('ws.supplier_id', 0)->whereOr(function ($supplierQuery) {
                    $supplierQuery->where('s.status', 'normal')->where('ss.status', 'normal');
                });
            })
            ->field('ws.*,w.code AS warehouse_code,w.name AS warehouse_name,w.owner_type,w.warehouse_type,s.code AS supplier_code,s.name AS supplier_name,ss.supply_price,ss.delivery_days,ss.fulfillment_mode,ss.priority')
            ->order('ss.priority DESC,ss.supply_price ASC,ws.id ASC')
            ->select();

        foreach ($rows as &$row) {
            $row = self::appendAvailableQuantity($row);
        }
        unset($row);

        return $rows;
    }

    /**
     * Items: [['warehouse_sku_id' => 1, 'quantity' => 2], ...].
     */
    public static function reserve($bizKey, $orderSn, array $items, $expireTime = null, $supplierOrderSn = '')
    {
        self::requiredString($bizKey, '库存锁定业务键不能为空');
        self::requiredString($orderSn, '订单号不能为空');
        if (!$items) {
            throw new RuntimeException('库存锁定明细不能为空');
        }

        Db::startTrans();
        try {
            $reservations = [];
            foreach ($items as $item) {
                $warehouseSkuId = isset($item['warehouse_sku_id']) ? (int)$item['warehouse_sku_id'] : 0;
                $quantity = self::positiveQuantity(isset($item['quantity']) ? $item['quantity'] : 0);
                if (!$warehouseSkuId) {
                    throw new RuntimeException('库存记录ID不能为空');
                }

                $existing = Db::name('shop_stock_reservation')
                    ->where('biz_key', $bizKey)
                    ->where('warehouse_sku_id', $warehouseSkuId)
                    ->lock(true)
                    ->find();
                if ($existing) {
                    if ((int)$existing['quantity'] !== $quantity || $existing['order_sn'] !== $orderSn) {
                        throw new RuntimeException('相同幂等键的库存锁定参数不一致', 409);
                    }
                    $reservations[] = $existing;
                    continue;
                }

                $stock = self::lockStock($warehouseSkuId);
                if (self::availableQuantity($stock) < $quantity) {
                    throw new RuntimeException('商品库存不足', 409);
                }

                $now = time();
                self::updateStock($stock, 0, $quantity, $now);
                $reservationSn = self::identifier('RS', [$bizKey, $warehouseSkuId]);
                $reservation = [
                    'reservation_sn'  => $reservationSn,
                    'biz_key'         => $bizKey,
                    'order_sn'        => $orderSn,
                    'supplier_order_sn' => (string)$supplierOrderSn,
                    'warehouse_sku_id' => $warehouseSkuId,
                    'goods_id'        => (int)$stock['goods_id'],
                    'goods_sku_id'    => (int)$stock['goods_sku_id'],
                    'quantity'        => $quantity,
                    'status'          => 'LOCKED',
                    'expiretime'      => $expireTime ? (int)$expireTime : null,
                    'createtime'      => $now,
                    'updatetime'      => $now,
                ];
                $reservation['id'] = Db::name('shop_stock_reservation')->insertGetId($reservation);

                self::recordFlow($stock, 'ORDER_LOCK', $bizKey, 0, $quantity, '订单锁定库存', $now);
                $reservations[] = $reservation;
            }
            Db::commit();
            return $reservations;
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    public static function releaseByBizKey($bizKey, $remark = '订单释放库存')
    {
        return self::transitionReservations($bizKey, 'RELEASED', $remark);
    }

    public static function deductByBizKey($bizKey, $remark = '订单出库')
    {
        return self::transitionReservations($bizKey, 'DEDUCTED', $remark);
    }

    public static function releaseOrderGoodsQuantity($orderGoodsId, $quantity, $bizNo, $aftersalesId = 0, $remark = '售后部分释放库存')
    {
        $orderGoodsId = (int)$orderGoodsId;
        $quantity = self::positiveQuantity($quantity);
        self::requiredString($bizNo, '库存释放业务号不能为空');

        Db::startTrans();
        try {
            $orderGoods = Db::name('shop_order_goods')->where('id', $orderGoodsId)->lock(true)->find();
            $extension = Db::name('shop_order_goods_ext')->where('order_goods_id', $orderGoodsId)->lock(true)->find();
            if (!$orderGoods || !$extension) {
                throw new RuntimeException('订单商品库存来源不存在', 404);
            }
            $supplierOrder = Db::name('shop_order_supplier')->where('id', (int)$extension['supplier_order_id'])->find();
            if (!$supplierOrder) {
                throw new RuntimeException('供应商履约子单不存在', 404);
            }

            $reservation = Db::name('shop_stock_reservation')
                ->where('supplier_order_sn', $supplierOrder['supplier_order_sn'])
                ->where('goods_id', (int)$orderGoods['goods_id'])
                ->where('goods_sku_id', (int)$orderGoods['goods_sku_id'])
                ->lock(true)
                ->find();
            if (!$reservation) {
                throw new RuntimeException('订单商品库存锁定记录不存在', 404);
            }

            $changed = self::adjustReservation(
                $reservation,
                'RELEASE',
                $quantity,
                $bizNo,
                $orderGoodsId,
                (int)$aftersalesId,
                $remark
            );
            Db::commit();
            return $changed;
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    public static function deductOrderGoodsQuantity($orderGoodsId, $quantity, $bizNo, $remark = '订单商品出库')
    {
        $orderGoodsId = (int)$orderGoodsId;
        $quantity = self::positiveQuantity($quantity);
        self::requiredString($bizNo, '库存出库业务号不能为空');

        Db::startTrans();
        try {
            $orderGoods = Db::name('shop_order_goods')->where('id', $orderGoodsId)->lock(true)->find();
            $extension = Db::name('shop_order_goods_ext')->where('order_goods_id', $orderGoodsId)->lock(true)->find();
            if (!$orderGoods || !$extension) {
                throw new RuntimeException('订单商品库存来源不存在', 404);
            }
            $supplierOrder = Db::name('shop_order_supplier')->where('id', (int)$extension['supplier_order_id'])->find();
            if (!$supplierOrder) {
                throw new RuntimeException('供应商履约子单不存在', 404);
            }
            $reservation = Db::name('shop_stock_reservation')
                ->where('supplier_order_sn', $supplierOrder['supplier_order_sn'])
                ->where('goods_id', (int)$orderGoods['goods_id'])
                ->where('goods_sku_id', (int)$orderGoods['goods_sku_id'])
                ->lock(true)
                ->find();
            if (!$reservation) {
                throw new RuntimeException('订单商品库存锁定记录不存在', 404);
            }
            $changed = self::adjustReservation(
                $reservation,
                'DEDUCT',
                $quantity,
                $bizNo,
                $orderGoodsId,
                0,
                $remark
            );
            Db::commit();
            return $changed;
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    /**
     * Atomically move a full order-line reservation to a replacement SKU source.
     */
    public static function reallocateOrderGoods($orderGoodsId, $newWarehouseSkuId, $quantity, $newSupplierOrderSn, $bizNo)
    {
        $orderGoodsId = (int)$orderGoodsId;
        $newWarehouseSkuId = (int)$newWarehouseSkuId;
        $quantity = self::positiveQuantity($quantity);
        self::requiredString($newSupplierOrderSn, '替代商品供应商子单号不能为空');
        self::requiredString($bizNo, '替代库存业务号不能为空');

        Db::startTrans();
        try {
            $orderGoods = Db::name('shop_order_goods')->where('id', $orderGoodsId)->lock(true)->find();
            $extension = Db::name('shop_order_goods_ext')->where('order_goods_id', $orderGoodsId)->lock(true)->find();
            $oldSupplierOrder = $extension
                ? Db::name('shop_order_supplier')->where('id', (int)$extension['supplier_order_id'])->lock(true)->find()
                : null;
            if (!$orderGoods || !$extension || !$oldSupplierOrder) {
                throw new RuntimeException('订单商品库存来源不存在', 404);
            }
            $oldReservation = Db::name('shop_stock_reservation')
                ->where('supplier_order_sn', $oldSupplierOrder['supplier_order_sn'])
                ->where('goods_id', (int)$orderGoods['goods_id'])
                ->where('goods_sku_id', (int)$orderGoods['goods_sku_id'])
                ->lock(true)
                ->find();
            if (!$oldReservation || $oldReservation['status'] !== 'LOCKED') {
                throw new RuntimeException('原商品库存锁定已失效，不能替换', 409);
            }
            if (self::remainingReservationQuantity($oldReservation) !== $quantity) {
                throw new RuntimeException('仅支持整条未出库商品替换', 409);
            }

            $newStock = self::lockStock($newWarehouseSkuId);
            if ((int)$newStock['goods_id'] === (int)$orderGoods['goods_id']
                && (int)$newStock['goods_sku_id'] === (int)$orderGoods['goods_sku_id']) {
                throw new RuntimeException('替代商品不能与原商品相同', 409);
            }
            if (self::availableQuantity($newStock) < $quantity) {
                throw new RuntimeException('替代商品库存不足', 409);
            }

            self::adjustReservation($oldReservation, 'RELEASE', $quantity, $bizNo, $orderGoodsId, 0, '订单替代释放原商品库存');

            $newBizKey = 'SUPPLIER_ORDER:' . $newSupplierOrderSn;
            $existing = Db::name('shop_stock_reservation')
                ->where('biz_key', $newBizKey)
                ->where('warehouse_sku_id', $newWarehouseSkuId)
                ->lock(true)
                ->find();
            if ($existing) {
                throw new RuntimeException('替代库存已被其他订单行占用', 409);
            }
            $now = time();
            self::updateStock($newStock, 0, $quantity, $now);
            Db::name('shop_stock_reservation')->insert([
                'reservation_sn' => self::identifier('RS', [$newBizKey, $newWarehouseSkuId]),
                'biz_key' => $newBizKey,
                'order_sn' => $orderGoods['order_sn'],
                'supplier_order_sn' => $newSupplierOrderSn,
                'warehouse_sku_id' => $newWarehouseSkuId,
                'goods_id' => (int)$newStock['goods_id'],
                'goods_sku_id' => (int)$newStock['goods_sku_id'],
                'quantity' => $quantity,
                'status' => 'LOCKED',
                'expiretime' => $oldReservation['expiretime'],
                'createtime' => $now,
                'updatetime' => $now,
            ]);
            self::recordFlow($newStock, 'ORDER_LOCK', $newBizKey, 0, $quantity, '订单替代锁定新商品库存', $now);
            Db::commit();
            return ['old_reservation_id' => (int)$oldReservation['id'], 'new_warehouse_sku_id' => $newWarehouseSkuId];
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    public static function restock($warehouseSkuId, $quantity, $bizNo, $remark = '售后退货入库')
    {
        $warehouseSkuId = (int)$warehouseSkuId;
        $quantity = self::positiveQuantity($quantity);
        self::requiredString($bizNo, '入库业务号不能为空');

        Db::startTrans();
        try {
            $flowSn = self::flowIdentifier('AFTERSALE_IN', $bizNo, $warehouseSkuId);
            if (Db::name('shop_stock_flow')->where('flow_sn', $flowSn)->lock(true)->find()) {
                Db::commit();
                return false;
            }

            $stock = self::lockStock($warehouseSkuId);
            $now = time();
            self::updateStock($stock, $quantity, 0, $now);
            self::recordFlow($stock, 'AFTERSALE_IN', $bizNo, $quantity, 0, $remark, $now);
            Db::commit();
            return true;
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    public static function restockUnavailable($warehouseSkuId, $quantity, $bizNo, $remark = '售后退货质检不合格入库')
    {
        $warehouseSkuId = (int)$warehouseSkuId;
        $quantity = self::positiveQuantity($quantity);
        self::requiredString($bizNo, '不可售入库业务号不能为空');

        Db::startTrans();
        try {
            $flowSn = self::flowIdentifier('AFTERSALE_UNAVAILABLE_IN', $bizNo, $warehouseSkuId);
            if (Db::name('shop_stock_flow')->where('flow_sn', $flowSn)->lock(true)->find()) {
                Db::commit();
                return false;
            }

            $stock = self::lockStock($warehouseSkuId);
            $now = time();
            $afterOnHand = (int)$stock['on_hand_qty'] + $quantity;
            $afterUnavailable = (int)$stock['unavailable_qty'] + $quantity;
            $affected = Db::name('shop_warehouse_sku')
                ->where('id', $warehouseSkuId)
                ->where('version', (int)$stock['version'])
                ->update([
                    'on_hand_qty' => $afterOnHand,
                    'unavailable_qty' => $afterUnavailable,
                    'version' => (int)$stock['version'] + 1,
                    'updatetime' => $now,
                ]);
            if ($affected !== 1) {
                throw new RuntimeException('库存已发生变化，请重试', 409);
            }
            self::recordFlow(
                $stock,
                'AFTERSALE_UNAVAILABLE_IN',
                $bizNo,
                $quantity,
                0,
                $remark . '；不可售库存增加 ' . $quantity,
                $now
            );
            Db::commit();
            return true;
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    public static function synchronizeOnHand($warehouseSkuId, $onHandQuantity, $bizNo, $remark = '供应商库存同步')
    {
        $warehouseSkuId = (int)$warehouseSkuId;
        $onHandQuantity = filter_var($onHandQuantity, FILTER_VALIDATE_INT);
        if ($onHandQuantity === false || $onHandQuantity < 0) {
            throw new RuntimeException('同步库存必须是非负整数', 422);
        }
        self::requiredString($bizNo, '库存同步业务号不能为空');

        Db::startTrans();
        try {
            $flowSn = self::flowIdentifier('SYNC_ADJUST', $bizNo, $warehouseSkuId);
            $existing = Db::name('shop_stock_flow')->where('flow_sn', $flowSn)->lock(true)->find();
            if ($existing) {
                if ((int)$existing['after_on_hand'] !== (int)$onHandQuantity) {
                    throw new RuntimeException('相同同步业务号的库存数量不一致', 409);
                }
                Db::commit();
                return false;
            }
            $stock = self::lockStock($warehouseSkuId);
            if ((int)$onHandQuantity < (int)$stock['locked_qty'] + (int)$stock['unavailable_qty']) {
                throw new RuntimeException('外部库存小于本地锁定及不可售库存，需人工处理', 409);
            }
            $delta = (int)$onHandQuantity - (int)$stock['on_hand_qty'];
            $now = time();
            self::updateStock($stock, $delta, 0, $now);
            self::recordFlow($stock, 'SYNC_ADJUST', $bizNo, $delta, 0, $remark, $now);
            Db::commit();
            return true;
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    public static function manualAdjust(
        $warehouseSkuId,
        $onHandDelta,
        $unavailableDelta,
        $inTransitDelta,
        $bizNo,
        $operatorId,
        $remark
    ) {
        $warehouseSkuId = (int)$warehouseSkuId;
        $onHandDelta = (int)$onHandDelta;
        $unavailableDelta = (int)$unavailableDelta;
        $inTransitDelta = (int)$inTransitDelta;
        self::requiredString($bizNo, '库存调整业务号不能为空');
        self::requiredString($remark, '库存调整原因不能为空');
        if ($onHandDelta === 0 && $unavailableDelta === 0 && $inTransitDelta === 0) {
            throw new RuntimeException('库存调整数量不能全部为 0', 422);
        }

        Db::startTrans();
        try {
            $flowSn = self::flowIdentifier('MANUAL_ADJUST', $bizNo, $warehouseSkuId);
            if (Db::name('shop_stock_flow')->where('flow_sn', $flowSn)->lock(true)->find()) {
                Db::commit();
                return false;
            }
            $stock = self::lockStock($warehouseSkuId);
            $afterOnHand = (int)$stock['on_hand_qty'] + $onHandDelta;
            $afterUnavailable = (int)$stock['unavailable_qty'] + $unavailableDelta;
            $afterInTransit = (int)$stock['in_transit_qty'] + $inTransitDelta;
            if ($afterOnHand < 0 || $afterUnavailable < 0 || $afterInTransit < 0
                || (int)$stock['locked_qty'] + $afterUnavailable > $afterOnHand) {
                throw new RuntimeException('调整后库存不能为负数，锁定与不可售库存不能超过实物库存', 409);
            }
            $now = time();
            $affected = Db::name('shop_warehouse_sku')
                ->where('id', $warehouseSkuId)
                ->where('version', (int)$stock['version'])
                ->update([
                    'on_hand_qty' => $afterOnHand,
                    'unavailable_qty' => $afterUnavailable,
                    'in_transit_qty' => $afterInTransit,
                    'version' => (int)$stock['version'] + 1,
                    'updatetime' => $now,
                ]);
            if ($affected !== 1) {
                throw new RuntimeException('库存已发生变化，请重试', 409);
            }
            self::recordFlow(
                $stock,
                'MANUAL_ADJUST',
                $bizNo,
                $onHandDelta,
                0,
                $remark . '；不可售变化=' . $unavailableDelta . '；在途变化=' . $inTransitDelta,
                $now,
                'ADMIN',
                (int)$operatorId
            );
            Db::commit();
            return true;
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    private static function transitionReservations($bizKey, $targetStatus, $remark)
    {
        self::requiredString($bizKey, '库存业务键不能为空');
        if (!in_array($targetStatus, ['RELEASED', 'DEDUCTED'], true)) {
            throw new RuntimeException('不支持的库存锁定状态');
        }

        Db::startTrans();
        try {
            $ids = Db::name('shop_stock_reservation')
                ->where('biz_key', $bizKey)
                ->order('id ASC')
                ->column('id');
            if (!$ids) {
                throw new RuntimeException('未找到库存锁定记录', 404);
            }

            $changed = 0;
            foreach ($ids as $id) {
                $reservation = Db::name('shop_stock_reservation')->where('id', (int)$id)->lock(true)->find();
                if ($reservation['status'] === $targetStatus) {
                    continue;
                }
                if (in_array($reservation['status'], ['RELEASED', 'DEDUCTED'], true)) {
                    continue;
                }
                if ($reservation['status'] !== 'LOCKED') {
                    throw new RuntimeException('库存锁定记录状态不允许转换', 409);
                }

                $stock = self::lockStock((int)$reservation['warehouse_sku_id']);
                $quantity = self::remainingReservationQuantity($reservation);
                if ($quantity === 0) {
                    continue;
                }
                if ((int)$stock['locked_qty'] < $quantity) {
                    throw new RuntimeException('锁定库存数据不一致', 409);
                }
                if ($targetStatus === 'DEDUCTED' && (int)$stock['on_hand_qty'] < $quantity) {
                    throw new RuntimeException('实际库存数据不一致', 409);
                }

                $now = time();
                $onHandDelta = $targetStatus === 'DEDUCTED' ? -$quantity : 0;
                self::updateStock($stock, $onHandDelta, -$quantity, $now);
                self::recordReservationAdjustment(
                    $reservation,
                    $targetStatus === 'DEDUCTED' ? 'DEDUCT' : 'RELEASE',
                    $quantity,
                    $bizKey,
                    0,
                    0,
                    $remark,
                    $now
                );
                Db::name('shop_stock_reservation')->where('id', (int)$reservation['id'])->update([
                    'status'      => $targetStatus,
                    'released_at' => $targetStatus === 'RELEASED' ? $now : null,
                    'deducted_at' => $targetStatus === 'DEDUCTED' ? $now : null,
                    'updatetime'  => $now,
                ]);

                $bizType = $targetStatus === 'DEDUCTED' ? 'ORDER_OUT' : 'ORDER_RELEASE';
                self::recordFlow($stock, $bizType, $bizKey, $onHandDelta, -$quantity, $remark, $now);
                $changed++;
            }
            Db::commit();
            return $changed;
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    private static function adjustReservation(array $reservation, $type, $quantity, $bizNo, $orderGoodsId, $aftersalesId, $remark)
    {
        if (!in_array($type, ['RELEASE', 'DEDUCT'], true)) {
            throw new RuntimeException('不支持的库存锁定调整类型');
        }
        $adjustmentSn = self::reservationAdjustmentIdentifier($type, $bizNo, (int)$reservation['id'], $orderGoodsId);
        $existing = Db::name('shop_stock_reservation_adjustment')
            ->where('reservation_id', (int)$reservation['id'])
            ->where('adjustment_type', $type)
            ->where('biz_no', $bizNo)
            ->where('order_goods_id', (int)$orderGoodsId)
            ->lock(true)
            ->find();
        if ($existing) {
            if ((int)$existing['quantity'] !== (int)$quantity || (int)$existing['order_goods_id'] !== (int)$orderGoodsId) {
                throw new RuntimeException('相同幂等键的库存调整参数不一致', 409);
            }
            return false;
        }
        if ($reservation['status'] !== 'LOCKED') {
            throw new RuntimeException('库存锁定记录已结束，不能继续调整', 409);
        }

        $remaining = self::remainingReservationQuantity($reservation);
        if ($quantity > $remaining) {
            throw new RuntimeException('调整数量超过剩余锁定库存', 409);
        }
        $stock = self::lockStock((int)$reservation['warehouse_sku_id']);
        if ((int)$stock['locked_qty'] < $quantity) {
            throw new RuntimeException('锁定库存数据不一致', 409);
        }

        $now = time();
        if ($type === 'DEDUCT' && (int)$stock['on_hand_qty'] < $quantity) {
            throw new RuntimeException('实际库存数据不一致', 409);
        }
        $onHandDelta = $type === 'DEDUCT' ? -$quantity : 0;
        self::updateStock($stock, $onHandDelta, -$quantity, $now);
        self::recordReservationAdjustment(
            $reservation,
            $type,
            $quantity,
            $bizNo,
            $orderGoodsId,
            $aftersalesId,
            $remark,
            $now
        );
        if ($quantity === $remaining) {
            Db::name('shop_stock_reservation')->where('id', (int)$reservation['id'])->update([
                'status' => $type === 'DEDUCT' ? 'DEDUCTED' : 'RELEASED',
                'released_at' => $type === 'RELEASE' ? $now : null,
                'deducted_at' => $type === 'DEDUCT' ? $now : null,
                'updatetime' => $now,
            ]);
        }
        self::recordFlow(
            $stock,
            $type === 'DEDUCT' ? 'ORDER_OUT' : 'ORDER_RELEASE',
            $bizNo,
            $onHandDelta,
            -$quantity,
            $remark,
            $now
        );
        return true;
    }

    private static function remainingReservationQuantity(array $reservation)
    {
        $adjusted = (int)Db::name('shop_stock_reservation_adjustment')
            ->where('reservation_id', (int)$reservation['id'])
            ->sum('quantity');
        $remaining = (int)$reservation['quantity'] - $adjusted;
        if ($remaining < 0) {
            throw new RuntimeException('库存锁定调整数量异常', 409);
        }
        return $remaining;
    }

    private static function recordReservationAdjustment(
        array $reservation,
        $type,
        $quantity,
        $bizNo,
        $orderGoodsId,
        $aftersalesId,
        $remark,
        $now
    ) {
        Db::name('shop_stock_reservation_adjustment')->insert([
            'adjustment_sn' => self::reservationAdjustmentIdentifier($type, $bizNo, (int)$reservation['id'], $orderGoodsId),
            'reservation_id' => (int)$reservation['id'],
            'order_goods_id' => (int)$orderGoodsId,
            'aftersales_id' => (int)$aftersalesId,
            'adjustment_type' => $type,
            'quantity' => (int)$quantity,
            'biz_no' => $bizNo,
            'remark' => $remark,
            'createtime' => $now,
        ]);
    }

    private static function lockStock($warehouseSkuId)
    {
        $stock = Db::name('shop_warehouse_sku')->where('id', (int)$warehouseSkuId)->lock(true)->find();
        if (!$stock) {
            throw new RuntimeException('库存记录不存在', 404);
        }
        return $stock;
    }

    private static function updateStock(array $stock, $onHandDelta, $lockedDelta, $now)
    {
        $afterOnHand = (int)$stock['on_hand_qty'] + (int)$onHandDelta;
        $afterLocked = (int)$stock['locked_qty'] + (int)$lockedDelta;
        if ($afterOnHand < 0 || $afterLocked < 0 || $afterLocked + (int)$stock['unavailable_qty'] > $afterOnHand) {
            throw new RuntimeException('库存数量不能为负数或超过实际库存', 409);
        }

        $affected = Db::name('shop_warehouse_sku')
            ->where('id', (int)$stock['id'])
            ->where('version', (int)$stock['version'])
            ->update([
                'on_hand_qty' => $afterOnHand,
                'locked_qty'  => $afterLocked,
                'version'     => (int)$stock['version'] + 1,
                'updatetime'  => $now,
            ]);
        if ($affected !== 1) {
            throw new RuntimeException('库存已发生变化，请重试', 409);
        }
    }

    private static function recordFlow(
        array $stock,
        $bizType,
        $bizNo,
        $onHandDelta,
        $lockedDelta,
        $remark,
        $now,
        $operatorType = 'SYSTEM',
        $operatorId = 0
    )
    {
        $flowSn = self::flowIdentifier($bizType, $bizNo, (int)$stock['id']);
        Db::name('shop_stock_flow')->insert([
            'flow_sn'          => $flowSn,
            'warehouse_sku_id' => (int)$stock['id'],
            'supplier_id'      => (int)$stock['supplier_id'],
            'warehouse_id'     => (int)$stock['warehouse_id'],
            'goods_id'         => (int)$stock['goods_id'],
            'goods_sku_id'     => (int)$stock['goods_sku_id'],
            'biz_type'         => $bizType,
            'biz_no'           => $bizNo,
            'change_on_hand'   => (int)$onHandDelta,
            'change_locked'    => (int)$lockedDelta,
            'before_on_hand'   => (int)$stock['on_hand_qty'],
            'after_on_hand'    => (int)$stock['on_hand_qty'] + (int)$onHandDelta,
            'before_locked'    => (int)$stock['locked_qty'],
            'after_locked'     => (int)$stock['locked_qty'] + (int)$lockedDelta,
            'operator_type'    => $operatorType,
            'operator_id'      => (int)$operatorId,
            'remark'           => $remark,
            'createtime'       => $now,
        ]);
    }

    private static function appendAvailableQuantity(array $row)
    {
        $row['available_qty'] = self::availableQuantity($row);
        return $row;
    }

    private static function availableQuantity(array $row)
    {
        return max(0, (int)$row['on_hand_qty'] - (int)$row['locked_qty'] - (int)$row['unavailable_qty']);
    }

    private static function positiveQuantity($quantity)
    {
        $quantity = filter_var($quantity, FILTER_VALIDATE_INT);
        if ($quantity === false || $quantity <= 0) {
            throw new RuntimeException('商品数量必须是正整数');
        }
        return (int)$quantity;
    }

    private static function requiredString($value, $message)
    {
        if (!is_string($value) || trim($value) === '') {
            throw new RuntimeException($message);
        }
    }

    private static function identifier($prefix, array $parts)
    {
        return $prefix . strtoupper(substr(hash('sha256', implode('|', $parts)), 0, 30));
    }

    private static function flowIdentifier($bizType, $bizNo, $warehouseSkuId)
    {
        return self::identifier('SF', [$bizType, $bizNo, $warehouseSkuId]);
    }

    private static function reservationAdjustmentIdentifier($type, $bizNo, $reservationId, $orderGoodsId = 0)
    {
        return self::identifier('SA', [$type, $bizNo, $reservationId, (int)$orderGoodsId]);
    }
}
