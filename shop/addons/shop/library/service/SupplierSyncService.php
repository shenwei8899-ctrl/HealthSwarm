<?php

namespace addons\shop\library\service;

use RuntimeException;
use think\Db;

class SupplierSyncService
{
    private static $types = ['PRODUCT', 'PRICE', 'STOCK', 'DELIVERY', 'ORDER', 'ACCEPT', 'SHIPPING', 'AFTERSALE'];

    public static function enqueue($supplierId, $type, $bizKey, array $payload, $direction = 'INBOUND', $maxAttempts = 5)
    {
        $supplierId = (int)$supplierId;
        $type = strtoupper(trim((string)$type));
        $direction = strtoupper(trim((string)$direction));
        $bizKey = trim((string)$bizKey);
        if (!in_array($type, self::$types, true) || !in_array($direction, ['INBOUND', 'OUTBOUND'], true)) {
            throw new RuntimeException('不支持的供应商同步类型', 422);
        }
        if ($bizKey === '' || !$payload || !Db::name('shop_supplier')->where('id', $supplierId)->where('status', 'normal')->find()) {
            throw new RuntimeException('供应商同步参数不完整', 422);
        }
        $existing = Db::name('shop_supplier_sync_job')
            ->where('supplier_id', $supplierId)
            ->where('sync_type', $type)
            ->where('biz_key', $bizKey)
            ->find();
        $payloadJson = self::json($payload);
        if ($existing) {
            $storedPayload = json_decode($existing['payload_json'], true);
            if (!is_array($storedPayload) || $storedPayload != $payload || $existing['direction'] !== $direction) {
                throw new RuntimeException('相同业务键的供应商同步内容不一致', 409);
            }
            return $existing;
        }
        $now = time();
        $job = [
            'job_sn' => self::jobNumber($supplierId, $type, $bizKey),
            'supplier_id' => $supplierId,
            'sync_type' => $type,
            'direction' => $direction,
            'biz_key' => $bizKey,
            'payload_json' => $payloadJson,
            'status' => 'PENDING',
            'attempts' => 0,
            'max_attempts' => max(1, (int)$maxAttempts),
            'createtime' => $now,
            'updatetime' => $now,
        ];
        $job['id'] = Db::name('shop_supplier_sync_job')->insertGetId($job);
        return $job;
    }

    public static function process($jobId)
    {
        Db::startTrans();
        try {
            $job = Db::name('shop_supplier_sync_job')->where('id', (int)$jobId)->lock(true)->find();
            if (!$job) {
                throw new RuntimeException('供应商同步任务不存在', 404);
            }
            if ($job['status'] === 'SUCCESS') {
                Db::commit();
                return $job;
            }
            if ($job['status'] === 'MANUAL_REQUIRED') {
                throw new RuntimeException('供应商同步任务等待人工补偿', 409);
            }
            $attempt = (int)$job['attempts'] + 1;
            Db::name('shop_supplier_sync_job')->where('id', (int)$job['id'])->update([
                'status' => 'RUNNING',
                'attempts' => $attempt,
                'last_error' => '',
                'updatetime' => time(),
            ]);
            Db::commit();
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }

        $payload = json_decode($job['payload_json'], true);
        try {
            $result = self::dispatch($job, is_array($payload) ? $payload : []);
            $now = time();
            Db::name('shop_supplier_sync_job')->where('id', (int)$job['id'])->update([
                'response_json' => self::json($result),
                'status' => 'SUCCESS',
                'next_retry_at' => null,
                'last_error' => '',
                'completed_at' => $now,
                'updatetime' => $now,
            ]);
            self::logAttempt($job, $payload, $result, 'SUCCESS', '', $attempt);
        } catch (\Throwable $e) {
            $manual = $attempt >= (int)$job['max_attempts'];
            $nextRetry = $manual ? null : time() + min(3600, 60 * (2 ** max(0, $attempt - 1)));
            Db::name('shop_supplier_sync_job')->where('id', (int)$job['id'])->update([
                'status' => $manual ? 'MANUAL_REQUIRED' : 'FAILED',
                'next_retry_at' => $nextRetry,
                'last_error' => mb_substr($e->getMessage(), 0, 1000),
                'updatetime' => time(),
            ]);
            self::logAttempt($job, $payload, [], 'FAILED', $e->getMessage(), $attempt);
        }
        return Db::name('shop_supplier_sync_job')->where('id', (int)$job['id'])->find();
    }

    public static function retryDue($limit = 50)
    {
        $ids = Db::name('shop_supplier_sync_job')
            ->where('status', 'FAILED')
            ->where('next_retry_at', '<=', time())
            ->order('next_retry_at ASC,id ASC')
            ->limit(max(1, min(500, (int)$limit)))
            ->column('id');
        $result = [];
        foreach ($ids as $id) {
            $result[] = self::process((int)$id);
        }
        return $result;
    }

    public static function retryNow($jobId)
    {
        $job = Db::name('shop_supplier_sync_job')->where('id', (int)$jobId)->find();
        if (!$job || !in_array($job['status'], ['FAILED', 'MANUAL_REQUIRED'], true)) {
            throw new RuntimeException('当前同步任务不能重试', 409);
        }
        Db::name('shop_supplier_sync_job')->where('id', (int)$jobId)->update([
            'status' => 'PENDING',
            'attempts' => $job['status'] === 'MANUAL_REQUIRED' ? 0 : (int)$job['attempts'],
            'next_retry_at' => null,
            'updatetime' => time(),
        ]);
        return self::process($jobId);
    }

    public static function completeManually($jobId, array $response, $operatorId, $remark)
    {
        $job = Db::name('shop_supplier_sync_job')->where('id', (int)$jobId)->find();
        if (!$job || !in_array($job['status'], ['FAILED', 'MANUAL_REQUIRED'], true)) {
            throw new RuntimeException('当前同步任务不能人工完成', 409);
        }
        $response['manual_operator_id'] = (int)$operatorId;
        $response['manual_remark'] = trim((string)$remark);
        Db::name('shop_supplier_sync_job')->where('id', (int)$jobId)->update([
            'response_json' => self::json($response),
            'status' => 'SUCCESS',
            'next_retry_at' => null,
            'last_error' => '',
            'completed_at' => time(),
            'updatetime' => time(),
        ]);
        return Db::name('shop_supplier_sync_job')->where('id', (int)$jobId)->find();
    }

    private static function dispatch(array $job, array $payload)
    {
        switch ($job['sync_type']) {
            case 'PRODUCT':
                return self::syncProducts($job, $payload);
            case 'PRICE':
                return self::syncPrices($job, $payload);
            case 'STOCK':
                return self::syncStocks($job, $payload);
            case 'DELIVERY':
                return self::syncDelivery($job, $payload);
            case 'ACCEPT':
                return self::syncAcceptance($job, $payload);
            case 'SHIPPING':
                return self::syncShipping($job, $payload);
            default:
                throw new RuntimeException('该同步任务需要供应商接口适配器或人工处理', 409);
        }
    }

    private static function syncProducts(array $job, array $payload)
    {
        $rows = isset($payload['items']) && is_array($payload['items']) ? $payload['items'] : [];
        if (!$rows) {
            throw new RuntimeException('供应商商品数据不能为空', 422);
        }
        $count = 0;
        foreach ($rows as $row) {
            // A supplier feed enters the raw product pool first. Legacy integrations may
            // still provide an explicit platform SKU and will be linked immediately.
            if (!empty($row['goods_id']) && empty($row['goods_sku_id'])) {
                $row['goods_sku_id'] = (int)Db::name('shop_goods_sku')
                    ->where('goods_id', (int)$row['goods_id'])->order('id ASC')->value('id');
            }
            if (!empty($row['goods_sku_id'])) {
                $sku = Db::name('shop_goods_sku')->where('id', (int)$row['goods_sku_id'])->find();
                if (!$sku || (!empty($row['goods_id']) && (int)$sku['goods_id'] !== (int)$row['goods_id'])) {
                    throw new RuntimeException('供应商商品指定的平台 SKU 无效', 409);
                }
                $goods = Db::name('shop_goods')->where('id', (int)$sku['goods_id'])->find();
                $row['goods_id'] = (int)$sku['goods_id'];
                $row['title'] = $row['title'] ?? $goods['title'];
            }
            SupplierProductCatalogService::ingest((int)$job['supplier_id'], $row);
            $count++;
        }
        return ['processed' => $count];
    }

    private static function syncPrices(array $job, array $payload)
    {
        $rows = isset($payload['items']) && is_array($payload['items']) ? $payload['items'] : [];
        $count = 0;
        foreach ($rows as $row) {
            $query = Db::name('shop_supplier_sku')->where('supplier_id', (int)$job['supplier_id']);
            if (!empty($row['supplier_sku_id'])) {
                $query->where('id', (int)$row['supplier_sku_id']);
            } else {
                $query->where('supplier_sku_code', trim((string)$row['supplier_sku_code']));
            }
            $supplierSku = $query->find();
            if (!$supplierSku || !isset($row['supply_price']) || (float)$row['supply_price'] < 0) {
                throw new RuntimeException('供应商价格数据无效', 409);
            }
            Db::name('shop_supplier_sku')->where('id', (int)$supplierSku['id'])->update([
                'supply_price' => (string)$row['supply_price'],
                'last_sync_time' => time(),
                'sync_status' => 'SUCCESS',
                'updatetime' => time(),
            ]);
            $count++;
        }
        return ['processed' => $count];
    }

    private static function syncStocks(array $job, array $payload)
    {
        $rows = isset($payload['items']) && is_array($payload['items']) ? $payload['items'] : [];
        $count = 0;
        foreach ($rows as $index => $row) {
            $supplierSku = self::supplierSku($job['supplier_id'], $row);
            $warehouse = self::supplierWarehouse($job['supplier_id'], $row);
            $stock = Db::name('shop_warehouse_sku')
                ->where('warehouse_id', (int)$warehouse['id'])
                ->where('supplier_sku_id', (int)$supplierSku['id'])
                ->find();
            if (!$stock) {
                $stockId = Db::name('shop_warehouse_sku')->insertGetId([
                    'warehouse_id' => (int)$warehouse['id'],
                    'supplier_id' => (int)$job['supplier_id'],
                    'supplier_sku_id' => (int)$supplierSku['id'],
                    'goods_id' => (int)$supplierSku['goods_id'],
                    'goods_sku_id' => (int)$supplierSku['goods_sku_id'],
                    'on_hand_qty' => 0,
                    'locked_qty' => 0,
                    'unavailable_qty' => 0,
                    'in_transit_qty' => 0,
                    'version' => 0,
                    'last_sync_time' => time(),
                    'createtime' => time(),
                    'updatetime' => time(),
                ]);
            } else {
                $stockId = (int)$stock['id'];
            }
            InventoryService::synchronizeOnHand(
                $stockId,
                isset($row['on_hand_quantity']) ? $row['on_hand_quantity'] : null,
                $job['job_sn'] . ':' . $index,
                '供应商库存同步：' . $supplierSku['supplier_sku_code']
            );
            Db::name('shop_warehouse_sku')->where('id', $stockId)->update(['last_sync_time' => time()]);
            $count++;
        }
        return ['processed' => $count];
    }

    private static function syncDelivery(array $job, array $payload)
    {
        $rows = isset($payload['items']) && is_array($payload['items']) ? $payload['items'] : [];
        $count = 0;
        foreach ($rows as $row) {
            $keys = [
                'supplier_id' => (int)$job['supplier_id'],
                'province_id' => isset($row['province_id']) ? (int)$row['province_id'] : 0,
                'city_id' => isset($row['city_id']) ? (int)$row['city_id'] : 0,
                'area_id' => isset($row['area_id']) ? (int)$row['area_id'] : 0,
            ];
            $data = [
                'shipping_fee' => isset($row['shipping_fee']) ? (string)$row['shipping_fee'] : '0.00',
                'free_shipping_amount' => isset($row['free_shipping_amount']) ? (string)$row['free_shipping_amount'] : '0.00',
                'delivery_days' => isset($row['delivery_days']) ? max(0, (int)$row['delivery_days']) : 0,
                'status' => isset($row['status']) ? $row['status'] : 'normal',
                'updatetime' => time(),
            ];
            $existing = Db::name('shop_supplier_delivery_region')->where($keys)->find();
            if ($existing) {
                Db::name('shop_supplier_delivery_region')->where('id', (int)$existing['id'])->update($data);
            } else {
                Db::name('shop_supplier_delivery_region')->insert(array_merge($keys, $data, ['createtime' => time()]));
            }
            $count++;
        }
        return ['processed' => $count];
    }

    private static function syncAcceptance(array $job, array $payload)
    {
        $supplierOrder = Db::name('shop_order_supplier')
            ->where('supplier_id', (int)$job['supplier_id'])
            ->where('supplier_order_sn', trim((string)$payload['supplier_order_sn']))
            ->find();
        $status = strtoupper(trim((string)$payload['status']));
        if (!$supplierOrder || !in_array($status, ['ACCEPTED', 'REJECTED'], true)) {
            throw new RuntimeException('供应商接单数据无效', 409);
        }
        if (in_array($supplierOrder['status'], [$status, 'SHIPPED', 'COMPLETED'], true)) {
            return ['supplier_order_id' => (int)$supplierOrder['id'], 'status' => $supplierOrder['status']];
        }
        Db::name('shop_order_supplier')->where('id', (int)$supplierOrder['id'])->update([
            'status' => $status,
            'accepted_at' => $status === 'ACCEPTED' ? time() : null,
            'cancelled_at' => $status === 'REJECTED' ? time() : null,
            'updatetime' => time(),
        ]);
        return ['supplier_order_id' => (int)$supplierOrder['id'], 'status' => $status];
    }

    private static function syncShipping(array $job, array $payload)
    {
        $supplierOrder = Db::name('shop_order_supplier')
            ->where('supplier_id', (int)$job['supplier_id'])
            ->where('supplier_order_sn', trim((string)$payload['supplier_order_sn']))
            ->find();
        if (!$supplierOrder) {
            throw new RuntimeException('供应商履约子单不存在', 404);
        }
        $shipment = FulfillmentService::shipPackage(
            (int)$supplierOrder['id'],
            isset($payload['shipper_name']) ? $payload['shipper_name'] : '',
            isset($payload['logistic_code']) ? $payload['logistic_code'] : '',
            isset($payload['items']) && is_array($payload['items']) ? $payload['items'] : [],
            isset($payload['shipper_code']) ? $payload['shipper_code'] : ''
        );
        return ['shipment_id' => (int)$shipment['id'], 'shipment_sn' => $shipment['shipment_sn']];
    }

    private static function supplierSku($supplierId, array $row)
    {
        $query = Db::name('shop_supplier_sku')->where('supplier_id', (int)$supplierId);
        if (!empty($row['supplier_sku_id'])) {
            $query->where('id', (int)$row['supplier_sku_id']);
        } else {
            $query->where('supplier_sku_code', trim((string)$row['supplier_sku_code']));
        }
        $supplierSku = $query->find();
        if (!$supplierSku) {
            throw new RuntimeException('供应商 SKU 不存在', 404);
        }
        return $supplierSku;
    }

    private static function supplierWarehouse($supplierId, array $row)
    {
        $query = Db::name('shop_warehouse')->where('owner_type', 'SUPPLIER')->where('owner_id', (int)$supplierId)->where('status', 'normal');
        if (!empty($row['warehouse_code'])) {
            $query->where('code', trim((string)$row['warehouse_code']));
        }
        $warehouse = $query->order('id ASC')->find();
        if (!$warehouse) {
            throw new RuntimeException('供应商仓库不存在', 404);
        }
        return $warehouse;
    }

    private static function logAttempt(array $job, array $request, array $response, $status, $error, $attempt)
    {
        Db::name('shop_supplier_sync_log')->insert([
            'supplier_id' => (int)$job['supplier_id'],
            'sync_type' => in_array($job['sync_type'], ['ACCEPT', 'SHIPPING'], true) ? 'ORDER' : $job['sync_type'],
            'biz_key' => $job['biz_key'],
            'request_id' => $job['job_sn'] . '-' . $attempt,
            'request_json' => self::json($request),
            'response_json' => self::json($response),
            'status' => $status,
            'error_message' => mb_substr((string)$error, 0, 1000),
            'retry_count' => max(0, (int)$attempt - 1),
            'createtime' => time(),
        ]);
    }

    private static function jobNumber($supplierId, $type, $bizKey)
    {
        return 'SJ' . strtoupper(substr(hash('sha256', $supplierId . '|' . $type . '|' . $bizKey), 0, 30));
    }

    private static function json(array $data)
    {
        return json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRESERVE_ZERO_FRACTION);
    }
}
