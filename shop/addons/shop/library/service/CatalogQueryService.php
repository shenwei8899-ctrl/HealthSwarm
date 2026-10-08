<?php

namespace addons\shop\library\service;

use RuntimeException;
use think\Db;

class CatalogQueryService
{
    public static function listGoods(array $filters = [])
    {
        $page = max(1, (int)($filters['page'] ?? 1));
        $pageSize = max(1, min(100, (int)($filters['page_size'] ?? 20)));
        $query = Db::name('shop_goods')
            ->alias('g')
            ->join('__SHOP_GOODS_EXT__ ge', 'ge.goods_id = g.id', 'LEFT')
            ->where('g.status', 'normal');
        if (!empty($filters['keyword'])) {
            $query->where('g.title|g.keywords', 'like', '%' . trim((string)$filters['keyword']) . '%');
        }
        if (!empty($filters['category_id'])) {
            $query->where('g.category_id', (int)$filters['category_id']);
        }
        $total = (clone $query)->count();
        $rows = $query
            ->field('g.id,g.goods_sn,g.title,g.subtitle,g.description,g.category_id,g.brand_id,g.price,g.marketprice,g.image,g.sales,g.status,ge.product_type,ge.origin,ge.shelf_life_days')
            ->order('g.weigh DESC,g.id DESC')
            ->page($page, $pageSize)
            ->select();
        foreach ($rows as &$row) {
            $row['id'] = (int)$row['id'];
            $row['category_id'] = (int)$row['category_id'];
            $row['brand_id'] = (int)$row['brand_id'];
            $row['shelf_life_days'] = (int)$row['shelf_life_days'];
            $row['product_type'] = $row['product_type'] ?: 'NORMAL';
            $row['origin'] = $row['origin'] ?: '';
            $row['availability'] = self::summarizeGoodsAvailability($row['id']);
        }
        unset($row);
        return [
            'items' => $rows,
            'pagination' => [
                'page' => $page,
                'page_size' => $pageSize,
                'total' => (int)$total,
            ],
        ];
    }

    public static function detail($goodsId, array $region = [])
    {
        $goodsId = (int)$goodsId;
        $goods = Db::name('shop_goods')
            ->alias('g')
            ->join('__SHOP_GOODS_EXT__ ge', 'ge.goods_id = g.id', 'LEFT')
            ->where('g.id', $goodsId)
            ->where('g.status', '<>', 'hidden')
            ->field('g.id,g.goods_sn,g.title,g.subtitle,g.description,g.category_id,g.brand_id,g.price,g.marketprice,g.image,g.images,g.content,g.sales,g.status,g.spectype,ge.product_type,ge.composition_json,ge.allergen_tags_json,ge.applicable_tags_json,ge.origin,ge.storage_condition,ge.shelf_life_days,ge.delivery_scope_type')
            ->find();
        if (!$goods) {
            throw new RuntimeException('商品不存在或已下架', 404);
        }

        $skuRows = Db::name('shop_goods_sku')
            ->where('goods_id', $goodsId)
            ->order('weigh DESC,id ASC')
            ->select();
        if (!$skuRows) {
            $skuRows = [[
                'id' => 0,
                'goods_id' => $goodsId,
                'goods_sn' => $goods['goods_sn'],
                'sku_id' => '',
                'image' => $goods['image'],
                'price' => $goods['price'],
                'marketprice' => $goods['marketprice'],
            ]];
        }

        $skus = [];
        foreach ($skuRows as $sku) {
            $skuId = (int)$sku['id'];
            $extension = Db::name('shop_sku_ext')
                ->where('goods_id', $goodsId)
                ->where('goods_sku_id', $skuId)
                ->find();
            $availability = self::availability($goodsId, $skuId, 1, $region);
            $skus[] = [
                'id' => $skuId,
                'goods_id' => $goodsId,
                'goods_sn' => (string)$sku['goods_sn'],
                'specification_key' => (string)$sku['sku_id'],
                'image' => (string)$sku['image'],
                'price' => (string)$sku['price'],
                'marketprice' => (string)$sku['marketprice'],
                'barcode' => (string)($extension['barcode'] ?? ''),
                'unit' => (string)($extension['unit'] ?? '份'),
                'net_quantity' => (string)($extension['net_quantity'] ?? '0.000'),
                'net_unit' => (string)($extension['net_unit'] ?? 'g'),
                'safety_stock' => (int)($extension['safety_stock'] ?? 0),
                'batch_enabled' => (bool)($extension['batch_enabled'] ?? false),
                'expiry_enabled' => (bool)($extension['expiry_enabled'] ?? false),
                'availability' => $availability,
            ];
        }

        return [
            'id' => (int)$goods['id'],
            'goods_sn' => $goods['goods_sn'],
            'title' => $goods['title'],
            'subtitle' => $goods['subtitle'],
            'description' => $goods['description'],
            'category_id' => (int)$goods['category_id'],
            'brand_id' => (int)$goods['brand_id'],
            'price' => (string)$goods['price'],
            'marketprice' => (string)$goods['marketprice'],
            'image' => $goods['image'],
            'images' => self::splitImages($goods['images']),
            'content' => $goods['content'],
            'sales' => (int)$goods['sales'],
            'status' => $goods['status'],
            'product_type' => $goods['product_type'] ?: 'NORMAL',
            'composition' => self::decodeJson($goods['composition_json']),
            'allergen_tags' => self::decodeJson($goods['allergen_tags_json']),
            'applicable_tags' => self::decodeJson($goods['applicable_tags_json']),
            'origin' => $goods['origin'] ?: '',
            'storage_condition' => $goods['storage_condition'] ?: '',
            'shelf_life_days' => (int)$goods['shelf_life_days'],
            'delivery_scope_type' => $goods['delivery_scope_type'] ?: 'SUPPLIER',
            'skus' => $skus,
            'substitutes' => self::substitutes($goodsId, 0, $region),
        ];
    }

    public static function availability($goodsId, $goodsSkuId = 0, $quantity = 1, array $region = [])
    {
        $goodsId = (int)$goodsId;
        $goodsSkuId = (int)$goodsSkuId;
        $quantity = max(1, (int)$quantity);
        $sources = InventoryService::listAvailableSources($goodsId, $goodsSkuId, $quantity);
        $publicSources = [];
        foreach ($sources as $source) {
            if (!ProductMatchService::isRegionDeliverable((int)$source['supplier_id'], $region)) {
                continue;
            }
            $publicSources[] = [
                'supplier_id' => (int)$source['supplier_id'],
                'supplier_name' => $source['supplier_name'] ?: '平台自营',
                'warehouse_id' => (int)$source['warehouse_id'],
                'available_quantity' => (int)$source['available_qty'],
                'delivery_days' => (int)($source['delivery_days'] ?? 0),
                'fulfillment_mode' => $source['fulfillment_mode'] ?: 'PLATFORM_WAREHOUSE',
            ];
        }
        $quantities = array_column($publicSources, 'available_quantity');
        return [
            'goods_id' => $goodsId,
            'goods_sku_id' => $goodsSkuId,
            'requested_quantity' => $quantity,
            'available' => !empty($publicSources),
            'max_single_source_quantity' => $quantities ? max($quantities) : 0,
            'total_source_quantity' => $quantities ? array_sum($quantities) : 0,
            'sources' => $publicSources,
        ];
    }

    public static function substitutes($goodsId, $goodsSkuId = 0, array $region = [])
    {
        $rows = Db::name('shop_goods_substitute')
            ->alias('sub')
            ->join('__SHOP_GOODS__ goods', 'goods.id = sub.substitute_goods_id')
            ->join('__SHOP_GOODS_SKU__ sku', 'sku.id = sub.substitute_goods_sku_id', 'LEFT')
            ->where('sub.goods_id', (int)$goodsId)
            ->where('sub.goods_sku_id', (int)$goodsSkuId)
            ->where('sub.status', 'normal')
            ->where('goods.status', 'normal')
            ->field('sub.substitute_goods_id AS goods_id,sub.substitute_goods_sku_id AS goods_sku_id,sub.priority,goods.title,goods.image,goods.price AS goods_price,sku.price AS sku_price')
            ->order('sub.priority DESC,sub.id ASC')
            ->select();
        $result = [];
        foreach ($rows as $row) {
            $availability = self::availability((int)$row['goods_id'], (int)$row['goods_sku_id'], 1, $region);
            if (!$availability['available']) {
                continue;
            }
            $result[] = [
                'goods_id' => (int)$row['goods_id'],
                'goods_sku_id' => (int)$row['goods_sku_id'],
                'title' => $row['title'],
                'image' => $row['image'],
                'price' => $row['sku_price'] !== null ? (string)$row['sku_price'] : (string)$row['goods_price'],
                'priority' => (int)$row['priority'],
                'availability' => $availability,
            ];
        }
        return $result;
    }

    private static function summarizeGoodsAvailability($goodsId)
    {
        $row = Db::name('shop_warehouse_sku')
            ->where('goods_id', (int)$goodsId)
            ->field('MAX(GREATEST(on_hand_qty - locked_qty - unavailable_qty, 0)) AS max_quantity,SUM(GREATEST(on_hand_qty - locked_qty - unavailable_qty, 0)) AS total_quantity')
            ->find();
        return [
            'available' => (int)($row['max_quantity'] ?? 0) > 0,
            'max_single_source_quantity' => (int)($row['max_quantity'] ?? 0),
            'total_source_quantity' => (int)($row['total_quantity'] ?? 0),
        ];
    }

    private static function decodeJson($value)
    {
        if (!$value) {
            return [];
        }
        $decoded = is_array($value) ? $value : json_decode($value, true);
        return is_array($decoded) ? $decoded : [];
    }

    private static function splitImages($images)
    {
        return array_values(array_filter(array_map('trim', explode(',', (string)$images))));
    }
}
