<?php

namespace addons\shop\library\service;

use think\Db;

class SupplyReportService
{
    private static $types = ['product_sales', 'orders', 'supplier_fulfillment', 'inventory', 'refunds', 'expiry'];

    public static function normalizeType($type)
    {
        return in_array($type, self::$types, true) ? $type : 'product_sales';
    }

    public static function rows($type)
    {
        $type = self::normalizeType($type);
        if ($type === 'product_sales') {
            return Db::name('shop_order_goods')->alias('goods')->join('__SHOP_ORDER__ orders', 'orders.order_sn=goods.order_sn')
                ->where('orders.paystate', 1)->where('orders.orderstate', 'in', [0, 3, 4])
                ->group('goods.goods_id,goods.title')->field("goods.goods_id AS id,goods.title AS dimension,SUM(goods.nums) AS metric1,SUM(goods.realprice) AS metric2,COUNT(DISTINCT orders.id) AS metric3,'件 / 元 / 单' AS unit_label")
                ->order('metric2 DESC')->limit(200)->select();
        }
        if ($type === 'orders') {
            return Db::name('shop_order_ext')->alias('ext')->join('__SHOP_ORDER__ orders', 'orders.id=ext.order_id')
                ->group('ext.biz_status')->field("ext.biz_status AS id,ext.biz_status AS dimension,COUNT(*) AS metric1,SUM(orders.saleamount) AS metric2,SUM(orders.paystate=1) AS metric3,'单 / 元 / 已支付' AS unit_label")
                ->order('metric1 DESC')->select();
        }
        if ($type === 'supplier_fulfillment') {
            return Db::name('shop_order_supplier')->alias('sub')->join('__SHOP_SUPPLIER__ supplier', 'supplier.id=sub.supplier_id', 'LEFT')
                ->group('sub.supplier_id,supplier.name')->field("sub.supplier_id AS id,COALESCE(supplier.name,'平台自营') AS dimension,COUNT(*) AS metric1,SUM(sub.status IN ('SHIPPED','COMPLETED')) AS metric2,SUM(sub.supply_amount) AS metric3,'子单 / 已履约 / 供货额' AS unit_label")
                ->order('metric1 DESC')->select();
        }
        if ($type === 'inventory') {
            return Db::name('shop_warehouse_sku')->alias('stock')->join('__SHOP_WAREHOUSE__ warehouse', 'warehouse.id=stock.warehouse_id')
                ->group('stock.warehouse_id,warehouse.name')->field("stock.warehouse_id AS id,warehouse.name AS dimension,SUM(stock.on_hand_qty-stock.locked_qty-stock.unavailable_qty) AS metric1,SUM(stock.locked_qty) AS metric2,SUM(stock.unavailable_qty) AS metric3,'可售 / 锁定 / 不可售' AS unit_label")
                ->order('metric1 DESC')->select();
        }
        if ($type === 'refunds') {
            return Db::name('shop_refund_transaction')->group('status')
                ->field("status AS id,status AS dimension,COUNT(*) AS metric1,SUM(amount) AS metric2,SUM(attempt_count) AS metric3,'笔 / 元 / 尝试' AS unit_label")
                ->order('metric1 DESC')->select();
        }
        return Db::name('shop_stock_batch')->alias('batch')->join('__SHOP_WAREHOUSE_SKU__ stock', 'stock.id=batch.warehouse_sku_id')
            ->join('__SHOP_GOODS__ goods', 'goods.id=stock.goods_id')->whereNotNull('batch.expiry_date')
            ->where('batch.expiry_date', '<=', date('Y-m-d', strtotime('+90 days')))->where('batch.status', '<>', 'disabled')
            ->group('stock.goods_id,goods.title')->field("stock.goods_id AS id,goods.title AS dimension,SUM(batch.on_hand_qty-batch.locked_qty-batch.unavailable_qty) AS metric1,MIN(DATEDIFF(batch.expiry_date,CURDATE())) AS metric2,COUNT(*) AS metric3,'临期库存 / 最短天数 / 批次' AS unit_label")
            ->order('metric2 ASC')->select();
    }
}
