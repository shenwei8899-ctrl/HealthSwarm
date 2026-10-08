<?php

namespace addons\shop\library\service;

use RuntimeException;
use think\Db;

class AfterSalesService
{
    /**
     * Applies inventory and aggregate state changes after an after-sales request is approved.
     * Returns false for legacy orders that do not have supply-chain extensions.
     */
    public static function approve($aftersalesId)
    {
        $aftersalesId = (int)$aftersalesId;
        Db::startTrans();
        try {
            $context = self::lockContext($aftersalesId);
            if (!$context) {
                Db::commit();
                return false;
            }
            list($aftersales, $order, $orderGoods, $goodsExt, $supplierOrder) = $context;
            if ((int)$aftersales['status'] !== 2) {
                throw new RuntimeException('售后单尚未审核通过', 409);
            }

            $existing = Db::name('shop_aftersales_ext')->where('aftersales_id', $aftersalesId)->lock(true)->find();
            if ($existing) {
                Db::commit();
                return true;
            }

            $quantity = self::validateRefundQuantity($aftersales, $orderGoods, $goodsExt);
            $now = time();
            $returnStatus = (int)$aftersales['type'] === 2 ? 'PENDING' : 'NONE';
            Db::name('shop_aftersales_ext')->insert([
                'aftersales_id' => $aftersalesId,
                'supplier_order_id' => (int)$goodsExt['supplier_order_id'],
                'supplier_id' => (int)$goodsExt['supplier_id'],
                'warehouse_id' => (int)$goodsExt['warehouse_id'],
                'return_status' => $returnStatus,
                'restock_quantity' => 0,
                'idempotency_key' => 'AFTERSALE-APPROVE-' . $aftersalesId,
                'createtime' => $now,
                'updatetime' => $now,
            ]);

            if ((int)$aftersales['type'] === 1) {
                if ((int)$goodsExt['shipped_quantity'] === 0) {
                    InventoryService::releaseOrderGoodsQuantity(
                        (int)$orderGoods['id'],
                        $quantity,
                        'AFTERSALE-RELEASE-' . $aftersalesId,
                        $aftersalesId,
                        '未发货售后退款释放库存'
                    );
                }
                self::increaseRefundedQuantity($goodsExt, $orderGoods, $quantity, 4);
                self::cancelSupplierOrderIfEmpty($supplierOrder);
            } else {
                Db::name('shop_order_goods')->where('id', (int)$orderGoods['id'])->update(['salestate' => 3]);
            }

            self::refreshOrderRefundStatus((int)$order['id']);
            self::statusLog($order, $supplierOrder, 'APPROVED', $aftersalesId, '售后审核通过');
            Db::commit();
            return true;
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    public static function reject($aftersalesId)
    {
        $aftersalesId = (int)$aftersalesId;
        Db::startTrans();
        try {
            $context = self::lockContext($aftersalesId);
            if (!$context) {
                Db::commit();
                return false;
            }
            list($aftersales, $order, $orderGoods, $goodsExt, $supplierOrder) = $context;
            if ((int)$aftersales['status'] !== 3) {
                throw new RuntimeException('售后单尚未拒绝', 409);
            }
            Db::name('shop_order_goods')->where('id', (int)$orderGoods['id'])->update(['salestate' => 6]);
            self::refreshOrderRefundStatus((int)$order['id']);
            self::statusLog($order, $supplierOrder, 'REJECTED', $aftersalesId, '售后审核拒绝');
            Db::commit();
            return true;
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    public static function inspectReturn(
        $aftersalesId,
        $acceptedQuantity,
        $rejectedQuantity,
        $bizNo,
        $operatorId = 0,
        $remark = ''
    ) {
        $aftersalesId = (int)$aftersalesId;
        $acceptedQuantity = self::nonNegativeInteger($acceptedQuantity, '合格数量必须是非负整数');
        $rejectedQuantity = self::nonNegativeInteger($rejectedQuantity, '不合格数量必须是非负整数');
        $bizNo = trim((string)$bizNo);
        if ($bizNo === '') {
            throw new RuntimeException('退货质检业务号不能为空');
        }

        Db::startTrans();
        try {
            $context = self::lockContext($aftersalesId);
            if (!$context) {
                throw new RuntimeException('历史订单不支持供应链退货质检', 409);
            }
            list($aftersales, $order, $orderGoods, $goodsExt, $supplierOrder) = $context;
            if ((int)$aftersales['type'] !== 2 || (int)$aftersales['status'] !== 2) {
                throw new RuntimeException('售后单不是已通过的退货退款', 409);
            }
            if ($acceptedQuantity + $rejectedQuantity !== (int)$aftersales['nums']) {
                throw new RuntimeException('合格与不合格数量之和必须等于本次退货数量', 409);
            }

            $existing = Db::name('shop_aftersales_inspection')->where('aftersales_id', $aftersalesId)->lock(true)->find();
            if ($existing) {
                if ((int)$existing['accepted_quantity'] !== $acceptedQuantity || (int)$existing['rejected_quantity'] !== $rejectedQuantity) {
                    throw new RuntimeException('售后单已经按其他数量完成质检', 409);
                }
                Db::commit();
                return false;
            }

            $aftersalesExt = Db::name('shop_aftersales_ext')->where('aftersales_id', $aftersalesId)->lock(true)->find();
            if (!$aftersalesExt || !in_array($aftersalesExt['return_status'], ['PENDING', 'SHIPPED', 'RECEIVED'], true)) {
                throw new RuntimeException('退货当前状态不能质检入库', 409);
            }
            $warehouseSku = Db::name('shop_warehouse_sku')
                ->where('warehouse_id', (int)$goodsExt['warehouse_id'])
                ->where('goods_id', (int)$orderGoods['goods_id'])
                ->where('goods_sku_id', (int)$orderGoods['goods_sku_id'])
                ->lock(true)
                ->find();
            if (!$warehouseSku) {
                throw new RuntimeException('退货入库库存记录不存在', 404);
            }

            if ($acceptedQuantity > 0) {
                InventoryService::restock(
                    (int)$warehouseSku['id'],
                    $acceptedQuantity,
                    $bizNo . '-SALEABLE',
                    '售后退货质检合格入库'
                );
            }
            if ($rejectedQuantity > 0) {
                InventoryService::restockUnavailable(
                    (int)$warehouseSku['id'],
                    $rejectedQuantity,
                    $bizNo . '-UNSALEABLE',
                    '售后退货质检不合格入库'
                );
            }

            $inspectionStatus = $acceptedQuantity === 0
                ? 'REJECTED'
                : ($rejectedQuantity === 0 ? 'ACCEPTED' : 'PARTIAL');
            $now = time();
            Db::name('shop_aftersales_inspection')->insert([
                'inspection_sn' => self::identifier('AI', [$aftersalesId, $bizNo]),
                'aftersales_id' => $aftersalesId,
                'supplier_order_id' => (int)$goodsExt['supplier_order_id'],
                'warehouse_sku_id' => (int)$warehouseSku['id'],
                'accepted_quantity' => $acceptedQuantity,
                'rejected_quantity' => $rejectedQuantity,
                'status' => $inspectionStatus,
                'biz_no' => $bizNo,
                'operator_type' => 'ADMIN',
                'operator_id' => (int)$operatorId,
                'remark' => trim((string)$remark),
                'createtime' => $now,
            ]);
            Db::name('shop_aftersales_ext')->where('id', (int)$aftersalesExt['id'])->update([
                'return_status' => $inspectionStatus === 'REJECTED' ? 'REJECTED' : 'ACCEPTED',
                'restock_quantity' => $acceptedQuantity,
                'updatetime' => $now,
            ]);

            self::increaseRefundedQuantity(
                $goodsExt,
                $orderGoods,
                $acceptedQuantity + $rejectedQuantity,
                5
            );
            self::refreshOrderRefundStatus((int)$order['id']);
            self::statusLog(
                $order,
                $supplierOrder,
                'RETURN_INSPECTED',
                $aftersalesId,
                sprintf('退货质检完成：合格%d，不合格%d', $acceptedQuantity, $rejectedQuantity)
            );
            Db::commit();
            return true;
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    private static function lockContext($aftersalesId)
    {
        $aftersales = Db::name('shop_order_aftersales')->where('id', $aftersalesId)->lock(true)->find();
        if (!$aftersales) {
            throw new RuntimeException('售后单不存在', 404);
        }
        $order = Db::name('shop_order')->where('id', (int)$aftersales['order_id'])->lock(true)->find();
        $orderGoods = Db::name('shop_order_goods')->where('id', (int)$aftersales['order_goods_id'])->lock(true)->find();
        $goodsExt = Db::name('shop_order_goods_ext')->where('order_goods_id', (int)$aftersales['order_goods_id'])->lock(true)->find();
        if (!$order || !$orderGoods) {
            throw new RuntimeException('售后关联订单不存在', 404);
        }
        if (!$goodsExt || !Db::name('shop_order_ext')->where('order_id', (int)$order['id'])->find()) {
            return null;
        }
        $supplierOrder = Db::name('shop_order_supplier')->where('id', (int)$goodsExt['supplier_order_id'])->lock(true)->find();
        if (!$supplierOrder) {
            throw new RuntimeException('售后关联供应商子单不存在', 404);
        }
        return [$aftersales, $order, $orderGoods, $goodsExt, $supplierOrder];
    }

    private static function validateRefundQuantity(array $aftersales, array $orderGoods, array $goodsExt)
    {
        $quantity = (int)$aftersales['nums'];
        $remaining = (int)$orderGoods['nums'] - (int)$goodsExt['refunded_quantity'];
        if ($quantity <= 0 || $quantity > $remaining) {
            throw new RuntimeException('售后数量超过订单商品剩余可退数量', 409);
        }
        return $quantity;
    }

    private static function increaseRefundedQuantity(array $goodsExt, array $orderGoods, $quantity, $completedSaleState)
    {
        $refundedQuantity = (int)$goodsExt['refunded_quantity'] + (int)$quantity;
        if ($refundedQuantity > (int)$orderGoods['nums']) {
            throw new RuntimeException('累计退款数量超过订单商品数量', 409);
        }
        $now = time();
        Db::name('shop_order_goods_ext')->where('id', (int)$goodsExt['id'])->update([
            'refunded_quantity' => $refundedQuantity,
            'updatetime' => $now,
        ]);
        Db::name('shop_order_goods')->where('id', (int)$orderGoods['id'])->update([
            'salestate' => $refundedQuantity === (int)$orderGoods['nums'] ? (int)$completedSaleState : 0,
        ]);
    }

    private static function cancelSupplierOrderIfEmpty(array $supplierOrder)
    {
        if (in_array($supplierOrder['status'], ['SHIPPED', 'COMPLETED', 'CANCELLED'], true)) {
            return;
        }
        $items = Db::name('shop_order_goods_ext')
            ->alias('ext')
            ->join('__SHOP_ORDER_GOODS__ goods', 'goods.id = ext.order_goods_id')
            ->where('ext.supplier_order_id', (int)$supplierOrder['id'])
            ->field('goods.nums,ext.refunded_quantity')
            ->select();
        foreach ($items as $item) {
            if ((int)$item['refunded_quantity'] < (int)$item['nums']) {
                return;
            }
        }
        Db::name('shop_order_supplier')->where('id', (int)$supplierOrder['id'])->update([
            'status' => 'CANCELLED',
            'cancelled_at' => time(),
            'updatetime' => time(),
        ]);
    }

    private static function refreshOrderRefundStatus($orderId)
    {
        $items = Db::name('shop_order_goods_ext')
            ->alias('ext')
            ->join('__SHOP_ORDER_GOODS__ goods', 'goods.id = ext.order_goods_id')
            ->where('goods.order_sn', Db::name('shop_order')->where('id', $orderId)->value('order_sn'))
            ->field('goods.nums,ext.refunded_quantity')
            ->select();
        $total = 0;
        $refunded = 0;
        foreach ($items as $item) {
            $total += (int)$item['nums'];
            $refunded += (int)$item['refunded_quantity'];
        }
        $pendingReturn = Db::name('shop_aftersales_ext')
            ->alias('ae')
            ->join('__SHOP_ORDER_AFTERSALES__ a', 'a.id = ae.aftersales_id')
            ->where('a.order_id', $orderId)
            ->where('ae.return_status', 'in', ['PENDING', 'SHIPPED', 'RECEIVED'])
            ->count();

        if ($pendingReturn > 0) {
            $refundStatus = 'RETURN_PENDING';
            $bizStatus = 'AFTERSALE';
            $orderState = 4;
        } elseif ($total > 0 && $refunded >= $total) {
            $refundStatus = 'REFUNDED';
            $bizStatus = 'REFUNDED';
            $orderState = 3;
        } elseif ($refunded > 0) {
            $refundStatus = 'PARTIAL_REFUNDED';
            $bizStatus = null;
            $orderState = 0;
        } else {
            $refundStatus = 'NONE';
            $bizStatus = null;
            $orderState = 0;
        }

        $now = time();
        $orderUpdate = ['orderstate' => $orderState, 'updatetime' => $now];
        if ($refundStatus === 'REFUNDED') {
            $orderUpdate['refundtime'] = $now;
        }
        Db::name('shop_order')->where('id', $orderId)->update($orderUpdate);

        $extensionUpdate = [
            'refund_status' => $refundStatus,
            'version' => Db::raw('version + 1'),
            'updatetime' => $now,
        ];
        if ($bizStatus !== null) {
            $extensionUpdate['biz_status'] = $bizStatus;
        }
        Db::name('shop_order_ext')->where('order_id', $orderId)->update($extensionUpdate);
    }

    private static function statusLog(array $order, array $supplierOrder, $toStatus, $aftersalesId, $remark)
    {
        Db::name('shop_order_status_log')->insert([
            'order_id' => (int)$order['id'],
            'order_sn' => $order['order_sn'],
            'supplier_order_id' => (int)$supplierOrder['id'],
            'status_type' => 'REFUND',
            'from_status' => '',
            'to_status' => $toStatus,
            'biz_no' => 'AFTERSALE-' . (int)$aftersalesId,
            'operator_type' => 'SYSTEM',
            'operator_id' => 0,
            'remark' => $remark,
            'createtime' => time(),
        ]);
    }

    private static function nonNegativeInteger($value, $message)
    {
        $value = filter_var($value, FILTER_VALIDATE_INT);
        if ($value === false || $value < 0) {
            throw new RuntimeException($message);
        }
        return (int)$value;
    }

    private static function identifier($prefix, array $parts)
    {
        return $prefix . strtoupper(substr(hash('sha256', implode('|', $parts)), 0, 30));
    }
}
