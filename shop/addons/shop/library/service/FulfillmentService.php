<?php

namespace addons\shop\library\service;

use addons\shop\model\OrderAction;
use RuntimeException;
use think\Db;

class FulfillmentService
{
    public static function markPreparing($supplierOrderId)
    {
        Db::startTrans();
        try {
            $supplierOrder = self::lockSupplierOrder($supplierOrderId);
            self::assertPaidOrder($supplierOrder['order_id']);
            if ($supplierOrder['status'] === 'PREPARING') {
                Db::commit();
                return $supplierOrder;
            }
            if (!in_array($supplierOrder['status'], ['PENDING_ACCEPT', 'ACCEPTED'], true)) {
                throw new RuntimeException('供应商子单当前状态不能开始备货', 409);
            }
            $now = time();
            Db::name('shop_order_supplier')->where('id', (int)$supplierOrderId)->update([
                'status' => 'PREPARING',
                'accepted_at' => $supplierOrder['accepted_at'] ?: $now,
                'preparing_at' => $now,
                'updatetime' => $now,
            ]);
            self::refreshMainOrderStatus((int)$supplierOrder['order_id']);
            self::statusLog($supplierOrder, $supplierOrder['status'], 'PREPARING', '开始备货');
            Db::commit();
            return Db::name('shop_order_supplier')->where('id', (int)$supplierOrderId)->find();
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    public static function shipSupplierOrder($supplierOrderId, $shipperName, $logisticCode, $shipperCode = '')
    {
        $existing = Db::name('shop_order_shipment')
            ->where('supplier_order_id', (int)$supplierOrderId)
            ->where('logistic_code', trim((string)$logisticCode))
            ->where('status', '<>', 'CANCELLED')
            ->find();
        if ($existing) {
            return $existing;
        }
        $items = Db::name('shop_order_goods_ext')
            ->alias('ext')
            ->join('__SHOP_ORDER_GOODS__ goods', 'goods.id = ext.order_goods_id')
            ->where('ext.supplier_order_id', (int)$supplierOrderId)
            ->field('ext.order_goods_id,ext.shipped_quantity,ext.refunded_quantity,goods.nums')
            ->select();
        $shippingItems = [];
        foreach ($items as $item) {
            $remaining = (int)$item['nums'] - (int)$item['refunded_quantity'] - (int)$item['shipped_quantity'];
            if ($remaining > 0) {
                $shippingItems[] = ['order_goods_id' => (int)$item['order_goods_id'], 'quantity' => $remaining];
            }
        }
        return self::shipPackage($supplierOrderId, $shipperName, $logisticCode, $shippingItems, $shipperCode);
    }

    public static function shipPackage($supplierOrderId, $shipperName, $logisticCode, array $items, $shipperCode = '')
    {
        $shipperName = trim((string)$shipperName);
        $logisticCode = trim((string)$logisticCode);
        if ($shipperName === '' || $logisticCode === '' || !$items) {
            throw new RuntimeException('物流公司、物流单号和包裹商品不能为空');
        }

        Db::startTrans();
        try {
            $supplierOrder = self::lockSupplierOrder($supplierOrderId);
            $order = self::assertPaidOrder($supplierOrder['order_id']);
            $existingShipment = Db::name('shop_order_shipment')
                ->where('supplier_order_id', (int)$supplierOrderId)
                ->where('logistic_code', $logisticCode)
                ->where('status', '<>', 'CANCELLED')
                ->lock(true)
                ->find();
            if ($existingShipment) {
                self::assertShipmentItems($existingShipment['id'], $items);
                Db::commit();
                return $existingShipment;
            }
            if (in_array($supplierOrder['status'], ['CANCELLED', 'REJECTED', 'COMPLETED'], true)) {
                throw new RuntimeException('供应商子单当前状态不能发货', 409);
            }

            $now = time();
            $shipmentSn = self::shipmentNumber($supplierOrder['supplier_order_sn'], $logisticCode);
            $shipmentId = Db::name('shop_order_shipment')->insertGetId([
                'shipment_sn' => $shipmentSn,
                'supplier_order_id' => (int)$supplierOrderId,
                'order_id' => (int)$supplierOrder['order_id'],
                'order_sn' => $supplierOrder['order_sn'],
                'shipper_code' => trim((string)$shipperCode),
                'shipper_name' => $shipperName,
                'logistic_code' => $logisticCode,
                'status' => 'SHIPPED',
                'shipping_at' => $now,
                'createtime' => $now,
                'updatetime' => $now,
            ]);

            $goodsRows = Db::name('shop_order_goods_ext')
                ->alias('ext')
                ->join('__SHOP_ORDER_GOODS__ goods', 'goods.id = ext.order_goods_id')
                ->where('ext.supplier_order_id', (int)$supplierOrderId)
                ->where('ext.order_goods_id', 'in', array_column($items, 'order_goods_id'))
                ->field('ext.id AS ext_id,ext.order_goods_id,ext.shipped_quantity,ext.refunded_quantity,goods.nums')
                ->lock(true)
                ->select();
            $goodsMap = [];
            foreach ($goodsRows as $goodsRow) {
                $goodsMap[(int)$goodsRow['order_goods_id']] = $goodsRow;
            }
            $shipmentItemCount = 0;
            foreach ($items as $item) {
                $orderGoodsId = isset($item['order_goods_id']) ? (int)$item['order_goods_id'] : 0;
                $shippingQuantity = isset($item['quantity']) ? (int)$item['quantity'] : 0;
                if (!$orderGoodsId || $shippingQuantity <= 0 || !isset($goodsMap[$orderGoodsId])) {
                    throw new RuntimeException('包裹包含无效的订单商品', 422);
                }
                $goodsRow = $goodsMap[$orderGoodsId];
                $remaining = (int)$goodsRow['nums'] - (int)$goodsRow['refunded_quantity'] - (int)$goodsRow['shipped_quantity'];
                if ($shippingQuantity > $remaining) {
                    throw new RuntimeException('发货数量超过订单商品剩余可发数量', 409);
                }
                InventoryService::deductOrderGoodsQuantity(
                    $orderGoodsId,
                    $shippingQuantity,
                    $shipmentSn,
                    '包裹出库：' . $logisticCode
                );
                Db::name('shop_order_shipment_item')->insert([
                    'shipment_id' => $shipmentId,
                    'order_goods_id' => (int)$goodsRow['order_goods_id'],
                    'quantity' => $shippingQuantity,
                    'createtime' => $now,
                ]);
                Db::name('shop_order_goods_ext')->where('id', (int)$goodsRow['ext_id'])->update([
                    'shipped_quantity' => (int)$goodsRow['shipped_quantity'] + $shippingQuantity,
                    'updatetime' => $now,
                ]);
                $shipmentItemCount++;
            }
            if ($shipmentItemCount === 0) {
                throw new RuntimeException('供应商子单没有可发货商品', 409);
            }

            $remainingCount = self::remainingQuantity($supplierOrderId);
            $targetStatus = $remainingCount > 0 ? 'PART_SHIPPED' : 'SHIPPED';
            Db::name('shop_order_supplier')->where('id', (int)$supplierOrderId)->update([
                'status' => $targetStatus,
                'shipping_at' => $supplierOrder['shipping_at'] ?: $now,
                'updatetime' => $now,
            ]);
            self::refreshMainOrderStatus((int)$supplierOrder['order_id']);

            $supplierOrderCount = Db::name('shop_order_supplier')->where('order_id', (int)$supplierOrder['order_id'])->count();
            if ($supplierOrderCount === 1) {
                Db::name('shop_order')->where('id', (int)$supplierOrder['order_id'])->update([
                    'expressname' => $shipperName,
                    'expressno' => $logisticCode,
                ]);
            }
            self::statusLog(
                $supplierOrder,
                $supplierOrder['status'],
                $targetStatus,
                $targetStatus === 'SHIPPED' ? '供应商子单已全部发货' : '供应商子单部分发货'
            );
            Db::commit();
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }

        OrderAction::push($order['order_sn'], '系统', '供应商子单包裹已发货：' . $logisticCode);
        return Db::name('shop_order_shipment')->where('id', $shipmentId)->find();
    }

    private static function refreshMainOrderStatus($orderId)
    {
        $orders = Db::name('shop_order_supplier')->where('order_id', $orderId)->column('status');
        $total = count($orders);
        $shipped = count(array_filter($orders, function ($status) {
            return in_array($status, ['SHIPPED', 'COMPLETED'], true);
        }));
        $preparing = count(array_filter($orders, function ($status) {
            return in_array($status, ['ACCEPTED', 'PREPARING'], true);
        }));
        $partial = count(array_filter($orders, function ($status) {
            return $status === 'PART_SHIPPED';
        }));

        if ($total > 0 && $shipped === $total) {
            $bizStatus = 'SHIPPING';
            $fulfillmentStatus = 'SHIPPED';
            Db::name('shop_order')->where('id', $orderId)->update([
                'shippingstate' => 1,
                'shippingtime' => time(),
                'updatetime' => time(),
            ]);
        } elseif ($shipped > 0 || $partial > 0) {
            $bizStatus = 'PART_SHIPPED';
            $fulfillmentStatus = 'PART_SHIPPED';
        } elseif ($preparing > 0) {
            $bizStatus = 'PREPARING';
            $fulfillmentStatus = 'PREPARING';
        } else {
            $bizStatus = 'PAID';
            $fulfillmentStatus = 'PENDING';
        }
        Db::name('shop_order_ext')->where('order_id', $orderId)->update([
            'biz_status' => $bizStatus,
            'fulfillment_status' => $fulfillmentStatus,
            'version' => Db::raw('version + 1'),
            'updatetime' => time(),
        ]);
    }

    private static function lockSupplierOrder($supplierOrderId)
    {
        $row = Db::name('shop_order_supplier')->where('id', (int)$supplierOrderId)->lock(true)->find();
        if (!$row) {
            throw new RuntimeException('供应商子单不存在', 404);
        }
        return $row;
    }

    private static function assertPaidOrder($orderId)
    {
        $order = Db::name('shop_order')->where('id', (int)$orderId)->lock(true)->find();
        if (!$order) {
            throw new RuntimeException('主订单不存在', 404);
        }
        if ((int)$order['paystate'] !== 1 || (int)$order['orderstate'] !== 0) {
            throw new RuntimeException('主订单未支付或已关闭', 409);
        }
        return $order;
    }

    private static function shipmentNumber($supplierOrderSn, $logisticCode = '')
    {
        return 'SHIP' . strtoupper(substr(hash('sha256', $supplierOrderSn . '|' . $logisticCode), 0, 28));
    }

    private static function remainingQuantity($supplierOrderId)
    {
        $rows = Db::name('shop_order_goods_ext')
            ->alias('ext')
            ->join('__SHOP_ORDER_GOODS__ goods', 'goods.id = ext.order_goods_id')
            ->where('ext.supplier_order_id', (int)$supplierOrderId)
            ->field('goods.nums,ext.shipped_quantity,ext.refunded_quantity')
            ->select();
        $remaining = 0;
        foreach ($rows as $row) {
            $remaining += max(0, (int)$row['nums'] - (int)$row['shipped_quantity'] - (int)$row['refunded_quantity']);
        }
        return $remaining;
    }

    private static function assertShipmentItems($shipmentId, array $items)
    {
        $stored = Db::name('shop_order_shipment_item')
            ->where('shipment_id', (int)$shipmentId)
            ->order('order_goods_id ASC')
            ->column('quantity', 'order_goods_id');
        $expected = [];
        foreach ($items as $item) {
            $expected[(int)$item['order_goods_id']] = (int)$item['quantity'];
        }
        ksort($expected);
        $stored = array_map('intval', $stored);
        ksort($stored);
        if ($stored !== $expected) {
            throw new RuntimeException('相同物流单号的包裹商品不一致', 409);
        }
    }

    private static function statusLog(array $supplierOrder, $fromStatus, $toStatus, $remark)
    {
        Db::name('shop_order_status_log')->insert([
            'order_id' => (int)$supplierOrder['order_id'],
            'order_sn' => $supplierOrder['order_sn'],
            'supplier_order_id' => (int)$supplierOrder['id'],
            'status_type' => 'SUPPLIER_ORDER',
            'from_status' => $fromStatus,
            'to_status' => $toStatus,
            'biz_no' => $supplierOrder['supplier_order_sn'],
            'operator_type' => 'SYSTEM',
            'operator_id' => 0,
            'remark' => $remark,
            'createtime' => time(),
        ]);
    }
}
