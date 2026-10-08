<?php

namespace addons\shop\library\service;

use RuntimeException;
use think\Db;

class SupplierProductCatalogService
{
    public static function ingest($supplierId, array $row)
    {
        $supplierId = (int)$supplierId;
        $supplierSkuCode = trim((string)($row['supplier_sku_code'] ?? ''));
        $supplierGoodsCode = trim((string)($row['supplier_goods_code'] ?? ''));
        if (!$supplierId || $supplierSkuCode === '') {
            throw new RuntimeException('供应商商品缺少供应商 SKU 编码', 422);
        }

        $now = time();
        $existing = Db::name('shop_supplier_product_pool')
            ->where('supplier_id', $supplierId)
            ->where('supplier_sku_code', $supplierSkuCode)
            ->find();
        $data = [
            'supplier_goods_code' => $supplierGoodsCode,
            'title' => trim((string)($row['title'] ?? $row['name'] ?? '')),
            'spec_text' => trim((string)($row['spec_text'] ?? $row['specification'] ?? '')),
            'barcode' => trim((string)($row['barcode'] ?? '')),
            'image' => trim((string)($row['image'] ?? '')),
            'supply_price' => max(0, (float)($row['supply_price'] ?? 0)),
            'min_order_qty' => max(1, (int)($row['min_order_qty'] ?? 1)),
            'delivery_days' => max(0, (int)($row['delivery_days'] ?? 0)),
            'fulfillment_mode' => in_array(($row['fulfillment_mode'] ?? ''), ['PLATFORM_WAREHOUSE', 'SUPPLIER_DIRECT'], true)
                ? $row['fulfillment_mode'] : 'SUPPLIER_DIRECT',
            'source_payload_json' => self::json($row),
            'sync_status' => 'SUCCESS',
            'last_sync_time' => $now,
            'status' => ($row['status'] ?? 'normal') === 'offline' ? 'offline' : 'normal',
            'updatetime' => $now,
        ];

        if ($existing) {
            Db::name('shop_supplier_product_pool')->where('id', (int)$existing['id'])->update($data);
            $sourceId = (int)$existing['id'];
        } else {
            $data = array_merge($data, [
                'supplier_id' => $supplierId,
                'supplier_sku_code' => $supplierSkuCode,
                'match_status' => 'PENDING',
                'match_method' => 'NONE',
                'match_note' => '',
                'goods_id' => 0,
                'goods_sku_id' => 0,
                'createtime' => $now,
            ]);
            $sourceId = (int)Db::name('shop_supplier_product_pool')->insertGetId($data);
        }

        $source = Db::name('shop_supplier_product_pool')->where('id', $sourceId)->find();
        $explicitSkuId = (int)($row['goods_sku_id'] ?? 0);
        if ($explicitSkuId) {
            self::bindToPlatformSku($sourceId, $explicitSkuId, 'UPSTREAM_MAPPING');
        } elseif (($source['match_status'] ?? '') === 'PENDING') {
            $autoSkuId = self::findSkuByBarcode((string)$source['barcode']);
            if ($autoSkuId) {
                self::bindToPlatformSku($sourceId, $autoSkuId, 'BARCODE');
            }
        }
        return Db::name('shop_supplier_product_pool')->where('id', $sourceId)->find();
    }

    public static function bindToPlatformSku($sourceId, $goodsSkuId, $method = 'MANUAL')
    {
        $source = Db::name('shop_supplier_product_pool')->where('id', (int)$sourceId)->lock(true)->find();
        $sku = Db::name('shop_goods_sku')->where('id', (int)$goodsSkuId)->find();
        if (!$source || !$sku) {
            throw new RuntimeException('供应商商品或平台 SKU 不存在', 404);
        }
        $goods = Db::name('shop_goods')->where('id', (int)$sku['goods_id'])->find();
        if (!$goods) {
            throw new RuntimeException('平台商品不存在', 404);
        }

        $duplicate = Db::name('shop_supplier_sku')
            ->where('supplier_id', (int)$source['supplier_id'])
            ->where('goods_id', (int)$goods['id'])
            ->where('goods_sku_id', (int)$sku['id'])
            ->find();
        if ($duplicate && (string)$duplicate['supplier_sku_code'] !== (string)$source['supplier_sku_code']) {
            throw new RuntimeException('该供应商已存在关联到此平台 SKU 的其他供货 SKU', 409);
        }

        $now = time();
        $supply = [
            'supplier_goods_code' => (string)$source['supplier_goods_code'],
            'supplier_sku_code' => (string)$source['supplier_sku_code'],
            'supply_price' => (string)$source['supply_price'],
            'min_order_qty' => (int)$source['min_order_qty'],
            'delivery_days' => (int)$source['delivery_days'],
            'fulfillment_mode' => (string)$source['fulfillment_mode'],
            'last_sync_time' => $now,
            'sync_status' => 'SUCCESS',
            'status' => $source['status'] === 'offline' ? 'offline' : 'normal',
            'updatetime' => $now,
        ];
        if ($duplicate) {
            Db::name('shop_supplier_sku')->where('id', (int)$duplicate['id'])->update($supply);
        } else {
            Db::name('shop_supplier_sku')->insert(array_merge($supply, [
                'supplier_id' => (int)$source['supplier_id'],
                'goods_id' => (int)$goods['id'],
                'goods_sku_id' => (int)$sku['id'],
                'priority' => 0,
                'createtime' => $now,
            ]));
        }
        Db::name('shop_supplier_product_pool')->where('id', (int)$source['id'])->update([
            'goods_id' => (int)$goods['id'],
            'goods_sku_id' => (int)$sku['id'],
            'match_status' => $method === 'BARCODE' ? 'AUTO_MATCHED' : 'MATCHED',
            'match_method' => $method,
            'match_note' => '',
            'updatetime' => $now,
        ]);
        return ['goods_id' => (int)$goods['id'], 'goods_sku_id' => (int)$sku['id']];
    }

    public static function createPlatformDraft($sourceId)
    {
        Db::startTrans();
        try {
            $source = Db::name('shop_supplier_product_pool')->where('id', (int)$sourceId)->lock(true)->find();
            if (!$source) {
                throw new RuntimeException('供应商商品不存在', 404);
            }
            if (in_array($source['match_status'], ['MATCHED', 'AUTO_MATCHED'], true)) {
                throw new RuntimeException('该供应商商品已关联平台 SKU', 409);
            }
            $now = time();
            $baseTitle = trim((string)$source['title']) ?: ('供应商商品 ' . $source['supplier_sku_code']);
            $salePrice = round(max(0.01, (float)$source['supply_price'] * 1.3), 2);
            $marketPrice = round($salePrice * 1.15, 2);
            $goodsId = (int)Db::name('shop_goods')->insertGetId([
                'category_id' => 0,
                'goods_sn' => 'AUTO-' . strtoupper(substr(hash('sha256', $source['supplier_id'] . '|' . $source['supplier_sku_code']), 0, 16)),
                'title' => $baseTitle,
                'subtitle' => '由供应商商品创建，待补充平台资料',
                'keywords' => '',
                'description' => '待运营完善商品资料后上架',
                'marketprice' => $marketPrice,
                'price' => $salePrice,
                'stocks' => 0,
                'sales' => 0,
                'spectype' => 1,
                'weight' => 0,
                'isvirtual' => 0,
                'weigh' => 0,
                'status' => 'hidden',
                'createtime' => $now,
                'updatetime' => $now,
            ]);
            $skuId = (int)Db::name('shop_goods_sku')->insertGetId([
                'goods_id' => $goodsId,
                'goods_sn' => 'AUTO-SKU-' . strtoupper(substr(hash('sha256', $source['supplier_id'] . '|' . $source['supplier_sku_code']), 0, 16)),
                'sku_id' => 'DEFAULT',
                'image' => (string)$source['image'],
                'price' => $salePrice,
                'marketprice' => $marketPrice,
                'stocks' => 0,
                'sales' => 0,
                'weigh' => 0,
                'createtime' => $now,
                'updatetime' => $now,
            ]);
            Db::name('shop_goods_ext')->insert([
                'goods_id' => $goodsId,
                'product_type' => 'INGREDIENT',
                'composition_json' => '[]',
                'allergen_tags_json' => '[]',
                'applicable_tags_json' => '[]',
                'origin' => '供应商待确认',
                'storage_condition' => '',
                'shelf_life_days' => 0,
                'delivery_scope_type' => 'ALL',
                'createtime' => $now,
                'updatetime' => $now,
            ]);
            Db::name('shop_sku_ext')->insert([
                'goods_id' => $goodsId,
                'goods_sku_id' => $skuId,
                'barcode' => (string)$source['barcode'],
                'unit' => '件',
                'net_quantity' => 1,
                'net_unit' => '件',
                'reference_cost_price' => (string)$source['supply_price'],
                'safety_stock' => 0,
                'batch_enabled' => 0,
                'expiry_enabled' => 0,
                'createtime' => $now,
                'updatetime' => $now,
            ]);
            self::bindToPlatformSku((int)$source['id'], $skuId, 'CREATE_DRAFT');
            Db::commit();
            return ['goods_id' => $goodsId, 'goods_sku_id' => $skuId];
        } catch (\Throwable $e) {
            Db::rollback();
            throw $e;
        }
    }

    private static function findSkuByBarcode($barcode)
    {
        if (trim($barcode) === '') {
            return 0;
        }
        return (int)Db::name('shop_sku_ext')->where('barcode', trim($barcode))->value('goods_sku_id');
    }

    private static function json(array $data)
    {
        return json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRESERVE_ZERO_FRACTION);
    }
}
