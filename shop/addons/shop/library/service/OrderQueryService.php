<?php

namespace addons\shop\library\service;

use RuntimeException;
use think\Db;

class OrderQueryService
{
    public static function listOrders($userId, array $filters = [])
    {
        $page = max(1, (int)($filters['page'] ?? 1));
        $pageSize = max(1, min(100, (int)($filters['page_size'] ?? 20)));
        $query = Db::name('shop_order')
            ->alias('orders')
            ->join('__SHOP_ORDER_EXT__ ext', 'ext.order_id = orders.id', 'LEFT')
            ->where('orders.user_id', (int)$userId)
            ->where('orders.status', '<>', 'hidden');
        if (!empty($filters['biz_status'])) {
            $statuses = is_array($filters['biz_status'])
                ? $filters['biz_status']
                : preg_split('/\s*,\s*/', trim((string)$filters['biz_status']), -1, PREG_SPLIT_NO_EMPTY);
            $statuses = array_values(array_unique(array_filter(array_map('trim', $statuses))));
            if (count($statuses) === 1) {
                $query->where('ext.biz_status', $statuses[0]);
            } elseif ($statuses) {
                $query->where('ext.biz_status', 'in', $statuses);
            }
        }
        if (array_key_exists('orderstate', $filters) && $filters['orderstate'] !== null && $filters['orderstate'] !== '') {
            $query->where('orders.orderstate', (int)$filters['orderstate']);
        }
        if (array_key_exists('shippingstate', $filters) && $filters['shippingstate'] !== null && $filters['shippingstate'] !== '') {
            $query->where('orders.shippingstate', (int)$filters['shippingstate']);
        }
        $total = (clone $query)->count();
        $rows = $query
            ->field('orders.id,orders.order_sn,orders.amount,orders.saleamount,orders.shippingfee,orders.paystate,orders.orderstate,orders.shippingstate,orders.createtime,ext.biz_status,ext.fulfillment_status,ext.refund_status')
            ->order('orders.id DESC')
            ->page($page, $pageSize)
            ->select();
        foreach ($rows as &$row) {
            $row = self::normalizeOrderSummary($row);
            $row['items'] = self::items((int)$row['id']);
        }
        unset($row);
        return [
            'items' => $rows,
            'pagination' => ['page' => $page, 'page_size' => $pageSize, 'total' => (int)$total],
        ];
    }

    public static function detail($orderSn, $userId)
    {
        $order = self::ownedOrder($orderSn, $userId);
        $extension = Db::name('shop_order_ext')->where('order_id', (int)$order['id'])->find();
        $supplierOrders = Db::name('shop_order_supplier')
            ->where('order_id', (int)$order['id'])
            ->order('id ASC')
            ->select();
        foreach ($supplierOrders as &$supplierOrder) {
            $supplierOrder['id'] = (int)$supplierOrder['id'];
            $supplierOrder['supplier_id'] = (int)$supplierOrder['supplier_id'];
            $supplierOrder['warehouse_id'] = (int)$supplierOrder['warehouse_id'];
            $supplierOrder['items'] = self::items((int)$order['id'], (int)$supplierOrder['id']);
            $supplierOrder['shipments'] = self::shipmentRows((int)$order['id'], (int)$supplierOrder['id']);
        }
        unset($supplierOrder);

        $result = self::normalizeOrderSummary(array_merge($order, $extension ?: []));
        $result['receiver'] = $order['receiver'];
        $result['mobile'] = self::maskMobile($order['mobile']);
        $result['address'] = $order['address'];
        $result['memo'] = $order['memo'];
        $result['shopping_list_id'] = (int)($extension['shopping_list_id'] ?? 0);
        $result['shopping_list_version'] = (int)($extension['shopping_list_version'] ?? 0);
        $result['trace_id'] = (string)($extension['trace_id'] ?? '');
        $result['items'] = self::items((int)$order['id']);
        $result['supplier_orders'] = $supplierOrders;
        $result['shipments'] = self::shipmentRows((int)$order['id']);
        $result['aftersales'] = self::aftersalesRows((int)$order['id']);
        $latestAfterSalesByGoods = [];
        foreach ($result['aftersales'] as $afterSales) {
            $orderGoodsId = (int)$afterSales['order_goods_id'];
            if (!isset($latestAfterSalesByGoods[$orderGoodsId])) {
                $latestAfterSalesByGoods[$orderGoodsId] = (int)$afterSales['id'];
            }
        }
        foreach ($result['items'] as &$item) {
            $item['aftersales_id'] = $latestAfterSalesByGoods[(int)$item['id']] ?? 0;
        }
        unset($item);
        $result['substitutions'] = self::substitutionRows((int)$order['id']);
        return $result;
    }

    public static function shipments($orderSn, $userId)
    {
        $order = self::ownedOrder($orderSn, $userId);
        return self::shipmentRows((int)$order['id']);
    }

    public static function paymentStatus($orderSn, $userId)
    {
        $order = self::ownedOrder($orderSn, $userId);
        $transaction = Db::name('shop_payment_transaction')
            ->where('order_id', (int)$order['id'])
            ->order('id DESC')
            ->find();
        return [
            'order_sn' => $order['order_sn'],
            'paid' => (int)$order['paystate'] === 1,
            'pay_state' => (int)$order['paystate'],
            'channel' => $transaction['channel'] ?? '',
            'transaction_status' => $transaction['status'] ?? ((int)$order['paystate'] === 1 ? 'SUCCESS' : 'CREATED'),
            'paid_at' => (int)($transaction['paid_at'] ?? $order['paytime'] ?? 0),
        ];
    }

    public static function aftersalesDetail($aftersalesId, $userId)
    {
        $row = Db::name('shop_order_aftersales')
            ->where('id', (int)$aftersalesId)
            ->where('user_id', (int)$userId)
            ->find();
        if (!$row) {
            throw new RuntimeException('售后单不存在', 404);
        }
        $extension = Db::name('shop_aftersales_ext')->where('aftersales_id', (int)$row['id'])->find();
        $inspection = Db::name('shop_aftersales_inspection')->where('aftersales_id', (int)$row['id'])->find();
        $refundTransaction = Db::name('shop_refund_transaction')->where('aftersales_id', (int)$row['id'])->find();
        return self::normalizeAfterSales($row, $extension, $inspection, $refundTransaction);
    }

    public static function saveReturnShipment($aftersalesId, $userId, $expressName, $expressNo)
    {
        $expressName = trim((string)$expressName);
        $expressNo = trim((string)$expressNo);
        if ($expressName === '' || $expressNo === '') {
            throw new RuntimeException('快递公司和快递单号不能为空');
        }
        Db::startTrans();
        try {
            $row = Db::name('shop_order_aftersales')
                ->where('id', (int)$aftersalesId)
                ->where('user_id', (int)$userId)
                ->lock(true)
                ->find();
            if (!$row || (int)$row['type'] !== 2 || (int)$row['status'] !== 2) {
                throw new RuntimeException('售后单当前状态不能提交退货物流', 409);
            }
            if ($row['expressno'] !== '') {
                if ($row['expressname'] !== $expressName || $row['expressno'] !== $expressNo) {
                    throw new RuntimeException('退货物流已经提交', 409);
                }
                Db::commit();
                return self::aftersalesDetail($aftersalesId, $userId);
            }
            Db::name('shop_order_aftersales')->where('id', (int)$row['id'])->update([
                'expressname' => $expressName,
                'expressno' => $expressNo,
                'updatetime' => time(),
            ]);
            Db::name('shop_aftersales_ext')->where('aftersales_id', (int)$row['id'])->update([
                'return_status' => 'SHIPPED',
                'updatetime' => time(),
            ]);
            Db::commit();
            return self::aftersalesDetail($aftersalesId, $userId);
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    private static function ownedOrder($orderSn, $userId)
    {
        $order = Db::name('shop_order')
            ->where('order_sn', trim((string)$orderSn))
            ->where('user_id', (int)$userId)
            ->where('status', '<>', 'hidden')
            ->find();
        if (!$order) {
            throw new RuntimeException('订单不存在', 404);
        }
        return $order;
    }

    private static function items($orderId, $supplierOrderId = 0)
    {
        $orderSn = Db::name('shop_order')->where('id', (int)$orderId)->value('order_sn');
        $query = Db::name('shop_order_goods')
            ->alias('goods')
            ->join('__SHOP_ORDER_GOODS_EXT__ ext', 'ext.order_goods_id = goods.id', 'LEFT')
            ->where('goods.order_sn', $orderSn);
        if ($supplierOrderId) {
            $query->where('ext.supplier_order_id', (int)$supplierOrderId);
        }
        $rows = $query
            ->field('goods.id,goods.goods_id,goods.goods_sku_id,goods.title,goods.image,goods.attrdata,goods.price,goods.realprice,goods.nums,goods.salestate,ext.supplier_order_id,ext.supplier_id,ext.warehouse_id,ext.shopping_list_item_id,ext.ingredient_id,ext.shipped_quantity,ext.refunded_quantity,ext.goods_snapshot_json,ext.delivery_snapshot_json')
            ->order('goods.id ASC')
            ->select();
        foreach ($rows as &$row) {
            foreach (['id', 'goods_id', 'goods_sku_id', 'nums', 'salestate', 'supplier_order_id', 'supplier_id', 'warehouse_id', 'shopping_list_item_id', 'ingredient_id', 'shipped_quantity', 'refunded_quantity'] as $field) {
                $row[$field] = (int)($row[$field] ?? 0);
            }
            $row['remaining_refundable_quantity'] = max(0, $row['nums'] - $row['refunded_quantity']);
            $row['goods_snapshot'] = self::decodeJson($row['goods_snapshot_json'] ?? null);
            $row['delivery_snapshot'] = self::decodeJson($row['delivery_snapshot_json'] ?? null);
            unset($row['goods_snapshot_json'], $row['delivery_snapshot_json']);
        }
        unset($row);
        return $rows;
    }

    private static function shipmentRows($orderId, $supplierOrderId = 0)
    {
        $query = Db::name('shop_order_shipment')->where('order_id', (int)$orderId);
        if ($supplierOrderId) {
            $query->where('supplier_order_id', (int)$supplierOrderId);
        }
        $rows = $query->order('id ASC')->select();
        foreach ($rows as &$row) {
            $row['id'] = (int)$row['id'];
            $row['supplier_order_id'] = (int)$row['supplier_order_id'];
            $row['items'] = Db::name('shop_order_shipment_item')
                ->alias('shipment_item')
                ->join('__SHOP_ORDER_GOODS__ order_goods', 'order_goods.id = shipment_item.order_goods_id', 'LEFT')
                ->where('shipment_item.shipment_id', (int)$row['id'])
                ->field('shipment_item.order_goods_id,shipment_item.quantity,order_goods.goods_id,order_goods.goods_sku_id,order_goods.title,order_goods.image,order_goods.attrdata')
                ->select();
            foreach ($row['items'] as &$item) {
                $item['order_goods_id'] = (int)$item['order_goods_id'];
                $item['quantity'] = (int)$item['quantity'];
                $item['goods_id'] = (int)($item['goods_id'] ?? 0);
                $item['goods_sku_id'] = (int)($item['goods_sku_id'] ?? 0);
            }
            unset($item);
        }
        unset($row);
        return $rows;
    }

    private static function aftersalesRows($orderId)
    {
        $rows = Db::name('shop_order_aftersales')->where('order_id', (int)$orderId)->order('id DESC')->select();
        foreach ($rows as &$row) {
            $extension = Db::name('shop_aftersales_ext')->where('aftersales_id', (int)$row['id'])->find();
            $inspection = Db::name('shop_aftersales_inspection')->where('aftersales_id', (int)$row['id'])->find();
            $refundTransaction = Db::name('shop_refund_transaction')->where('aftersales_id', (int)$row['id'])->find();
            $row = self::normalizeAfterSales($row, $extension, $inspection, $refundTransaction);
        }
        unset($row);
        return $rows;
    }

    private static function substitutionRows($orderId)
    {
        $rows = Db::name('shop_order_substitution')
            ->alias('substitution')
            ->join('__SHOP_GOODS__ from_goods', 'from_goods.id = substitution.from_goods_id', 'LEFT')
            ->join('__SHOP_GOODS_SKU__ from_sku', 'from_sku.id = substitution.from_goods_sku_id', 'LEFT')
            ->join('__SHOP_GOODS__ to_goods', 'to_goods.id = substitution.to_goods_id', 'LEFT')
            ->join('__SHOP_GOODS_SKU__ to_sku', 'to_sku.id = substitution.to_goods_sku_id', 'LEFT')
            ->join('__SHOP_SUPPLIER__ supplier', 'supplier.id = substitution.to_supplier_id', 'LEFT')
            ->where('substitution.order_id', (int)$orderId)
            ->field('substitution.*,from_goods.title AS from_goods_title,from_goods.image AS from_goods_image,COALESCE(from_sku.price,from_goods.price) AS from_price,to_goods.title AS to_goods_title,COALESCE(NULLIF(to_sku.image,\'\'),to_goods.image) AS to_goods_image,COALESCE(to_sku.price,to_goods.price) AS to_price,supplier.name AS to_supplier_name')
            ->order('substitution.id DESC')
            ->select();
        foreach ($rows as &$row) {
            foreach (['id','order_id','order_goods_id','from_supplier_id','from_goods_id','from_goods_sku_id','to_supplier_id','to_goods_id','to_goods_sku_id','confirmed_at'] as $field) {
                $row[$field] = (int)($row[$field] ?? 0);
            }
            $row['constraint_result'] = self::decodeJson($row['constraint_result_json'] ?? null);
            unset($row['constraint_result_json']);
        }
        unset($row);
        return $rows;
    }

    private static function normalizeAfterSales(array $row, $extension, $inspection, $refundTransaction)
    {
        $orderGoods = Db::name('shop_order_goods')
            ->where('id', (int)$row['order_goods_id'])
            ->field('id,goods_id,goods_sku_id,title,image,attrdata,price,realprice,nums,salestate')
            ->find();
        if ($orderGoods) {
            foreach (['id', 'goods_id', 'goods_sku_id', 'nums', 'salestate'] as $field) {
                $orderGoods[$field] = (int)$orderGoods[$field];
            }
        }

        return [
            'id' => (int)$row['id'],
            'order_id' => (int)$row['order_id'],
            'order_goods_id' => (int)$row['order_goods_id'],
            'type' => (int)$row['type'],
            'quantity' => (int)$row['nums'],
            'refund_amount' => (string)$row['refund'],
            'realprice' => (string)$row['realprice'],
            'shippingfee' => (string)$row['shippingfee'],
            'reason' => $row['reason'],
            'images' => self::splitCommaValues($row['images'] ?? ''),
            'seller_reply' => (string)($row['mark'] ?? ''),
            'status' => (int)$row['status'],
            'express_name' => $row['expressname'],
            'express_no' => $row['expressno'],
            'return_status' => $extension['return_status'] ?? 'NONE',
            'inspection' => $inspection ? [
                'accepted_quantity' => (int)$inspection['accepted_quantity'],
                'rejected_quantity' => (int)$inspection['rejected_quantity'],
                'status' => $inspection['status'],
            ] : null,
            'refund_transaction_status' => $refundTransaction['status'] ?? '',
            'order_goods' => $orderGoods ?: [],
            'createtime' => (int)$row['createtime'],
            'updatetime' => (int)$row['updatetime'],
        ];
    }

    private static function normalizeOrderSummary(array $row)
    {
        foreach (['id', 'paystate', 'orderstate', 'shippingstate', 'createtime'] as $field) {
            $row[$field] = (int)($row[$field] ?? 0);
        }
        $row['biz_status'] = $row['biz_status'] ?? self::legacyBizStatus($row);
        $row['fulfillment_status'] = $row['fulfillment_status'] ?? '';
        $row['refund_status'] = $row['refund_status'] ?? 'NONE';
        return $row;
    }

    private static function legacyBizStatus(array $order)
    {
        if ((int)$order['orderstate'] === 1) {
            return 'CANCELLED';
        }
        if ((int)$order['orderstate'] === 3) {
            return 'COMPLETED';
        }
        if ((int)$order['orderstate'] === 4) {
            return 'AFTERSALE';
        }
        if (!(int)$order['paystate']) {
            return 'PENDING_PAYMENT';
        }
        if ((int)$order['shippingstate'] === 2) {
            return 'COMPLETED';
        }
        if ((int)$order['shippingstate'] === 1) {
            return 'SHIPPING';
        }
        return 'PAID';
    }

    private static function decodeJson($value)
    {
        if (!$value) {
            return [];
        }
        $decoded = is_array($value) ? $value : json_decode($value, true);
        return is_array($decoded) ? $decoded : [];
    }

    private static function splitCommaValues($value)
    {
        return array_values(array_filter(array_map('trim', explode(',', (string)$value))));
    }

    private static function maskMobile($mobile)
    {
        $mobile = (string)$mobile;
        return strlen($mobile) >= 7 ? substr($mobile, 0, 3) . '****' . substr($mobile, -4) : $mobile;
    }
}
