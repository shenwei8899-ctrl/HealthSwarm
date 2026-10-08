<?php

namespace addons\shop\library\service;

use RuntimeException;
use think\Db;

class ProductMatchService
{
    public static function match($ingredientId, $requiredQuantity, $unit, array $constraints = [], array $region = [])
    {
        $ingredient = Db::name('shop_ingredient')
            ->where('id', (int)$ingredientId)
            ->where('status', 'normal')
            ->find();
        if (!$ingredient) {
            throw new RuntimeException('标准食材不存在或已停用', 404);
        }
        if (!is_numeric($requiredQuantity) || (float)$requiredQuantity <= 0) {
            throw new RuntimeException('食材需求数量必须大于0');
        }

        $requiredInDefaultUnit = UnitConverter::convert(
            (string)$requiredQuantity,
            $unit,
            $ingredient['default_unit'],
            3
        );
        $maps = Db::name('shop_ingredient_product_map')
            ->alias('m')
            ->join('__SHOP_GOODS__ g', 'g.id = m.goods_id')
            ->join('__SHOP_GOODS_SKU__ sku', 'sku.id = m.goods_sku_id', 'LEFT')
            ->join('__SHOP_GOODS_EXT__ ge', 'ge.goods_id = m.goods_id', 'LEFT')
            ->where('m.ingredient_id', (int)$ingredientId)
            ->where('m.status', 'normal')
            ->where('g.status', 'normal')
            ->field('m.*,g.title,g.image,g.price AS goods_price,g.marketprice AS goods_marketprice,g.stocks AS goods_stocks,sku.price AS sku_price,sku.marketprice AS sku_marketprice,sku.stocks AS sku_stocks,ge.origin,ge.shelf_life_days,ge.storage_condition,ge.composition_json,ge.allergen_tags_json,ge.applicable_tags_json')
            ->order('m.is_substitute ASC,m.priority DESC,m.id ASC')
            ->select();

        $candidates = [];
        foreach ($maps as $map) {
            if (!self::passesConstraints($map, $constraints)) {
                continue;
            }

            $coverage = bcmul((string)$map['content_quantity'], (string)$map['conversion_rate'], 3);
            if (bccomp($coverage, '0', 3) <= 0) {
                continue;
            }
            $purchaseQuantity = (int)ceil((float)bcdiv($requiredInDefaultUnit, $coverage, 6));
            $sources = InventoryService::listAvailableSources(
                (int)$map['goods_id'],
                (int)$map['goods_sku_id'],
                $purchaseQuantity
            );

            foreach ($sources as $source) {
                if (!self::isRegionDeliverable((int)$source['supplier_id'], $region)) {
                    continue;
                }
                $covered = bcmul($coverage, (string)$purchaseQuantity, 3);
                $shortage = max(0, (float)$requiredInDefaultUnit - (float)$covered);
                $excess = max(0, (float)$covered - (float)$requiredInDefaultUnit);
                $salePrice = (int)$map['goods_sku_id'] > 0 && $map['sku_price'] !== null
                    ? (string)$map['sku_price']
                    : (string)$map['goods_price'];

                $candidates[] = [
                    'ingredient_id'       => (int)$ingredient['id'],
                    'goods_id'            => (int)$map['goods_id'],
                    'goods_sku_id'        => (int)$map['goods_sku_id'],
                    'title'               => $map['title'],
                    'image'               => $map['image'],
                    'purchase_quantity'   => $purchaseQuantity,
                    'unit_coverage'       => $coverage,
                    'coverage_unit'       => $ingredient['default_unit'],
                    'covered_quantity'    => number_format((float)$covered, 3, '.', ''),
                    'shortage_quantity'   => number_format($shortage, 3, '.', ''),
                    'excess_quantity'     => number_format($excess, 3, '.', ''),
                    'sale_price'           => $salePrice,
                    'total_sale_price'     => bcmul($salePrice, (string)$purchaseQuantity, 2),
                    'supplier_id'          => (int)$source['supplier_id'],
                    'supplier_sku_id'      => (int)$source['supplier_sku_id'],
                    'supplier_name'        => $source['supplier_name'] ?: '平台自营',
                    'supply_price'         => $source['supply_price'] === null ? '0.00' : (string)$source['supply_price'],
                    'warehouse_id'         => (int)$source['warehouse_id'],
                    'warehouse_sku_id'     => (int)$source['id'],
                    'available_quantity'   => (int)$source['available_qty'],
                    'delivery_days'        => $source['delivery_days'] === null ? 0 : (int)$source['delivery_days'],
                    'fulfillment_mode'     => $source['fulfillment_mode'] ?: 'PLATFORM_WAREHOUSE',
                    'origin'               => $map['origin'] ?: '',
                    'shelf_life_days'       => (int)$map['shelf_life_days'],
                    'storage_condition'    => $map['storage_condition'] ?: '',
                    'composition'          => self::decodeJson($map['composition_json']),
                    'allergen_tags'        => self::decodeJson($map['allergen_tags_json']),
                    'is_substitute'        => (bool)$map['is_substitute'],
                    'map_priority'         => (int)$map['priority'],
                    'supplier_priority'    => isset($source['priority']) ? (int)$source['priority'] : 0,
                ];
            }
        }

        usort($candidates, function ($left, $right) {
            $leftRank = [
                $left['is_substitute'] ? 1 : 0,
                $left['shortage_quantity'] > 0 ? 1 : 0,
                $left['delivery_days'],
                (float)$left['total_sale_price'],
                -$left['map_priority'],
                -$left['supplier_priority'],
            ];
            $rightRank = [
                $right['is_substitute'] ? 1 : 0,
                $right['shortage_quantity'] > 0 ? 1 : 0,
                $right['delivery_days'],
                (float)$right['total_sale_price'],
                -$right['map_priority'],
                -$right['supplier_priority'],
            ];
            return $leftRank <=> $rightRank;
        });

        return [
            'ingredient' => [
                'id' => (int)$ingredient['id'],
                'code' => $ingredient['code'],
                'name' => $ingredient['name'],
                'required_quantity' => number_format((float)$requiredInDefaultUnit, 3, '.', ''),
                'unit' => $ingredient['default_unit'],
            ],
            'selected' => $candidates ? $candidates[0] : null,
            'alternatives' => $candidates ? array_slice($candidates, 1) : [],
            'matched' => !empty($candidates),
        ];
    }

    public static function matchRequirements(array $requirements, array $region = [])
    {
        $results = [];
        foreach ($requirements as $requirement) {
            $results[] = self::match(
                isset($requirement['ingredient_id']) ? $requirement['ingredient_id'] : 0,
                isset($requirement['required_quantity']) ? $requirement['required_quantity'] : 0,
                isset($requirement['unit']) ? $requirement['unit'] : '',
                isset($requirement['constraints']) && is_array($requirement['constraints']) ? $requirement['constraints'] : [],
                $region
            );
        }
        return $results;
    }

    private static function passesConstraints(array $map, array $constraints)
    {
        $blockedGoodsIds = isset($constraints['blocked_goods_ids']) ? array_map('intval', (array)$constraints['blocked_goods_ids']) : [];
        if (in_array((int)$map['goods_id'], $blockedGoodsIds, true)) {
            return false;
        }

        $excludedAllergens = isset($constraints['excluded_allergen_tags'])
            ? array_map('strval', (array)$constraints['excluded_allergen_tags'])
            : [];
        $goodsAllergens = array_map('strval', (array)self::decodeJson($map['allergen_tags_json']));
        if (array_intersect($excludedAllergens, $goodsAllergens)) {
            return false;
        }

        if (isset($constraints['allowed']) && !$constraints['allowed']) {
            return false;
        }
        return true;
    }

    public static function isRegionDeliverable($supplierId, array $region)
    {
        if ($supplierId === 0 || !$region) {
            return true;
        }
        $query = Db::name('shop_supplier_delivery_region')
            ->where('supplier_id', $supplierId)
            ->where('status', 'normal');
        if (!$query->count()) {
            return false;
        }

        $provinceId = isset($region['province_id']) ? (int)$region['province_id'] : 0;
        $cityId = isset($region['city_id']) ? (int)$region['city_id'] : 0;
        $areaId = isset($region['area_id']) ? (int)$region['area_id'] : 0;
        return (bool)Db::name('shop_supplier_delivery_region')
            ->where('supplier_id', $supplierId)
            ->where('status', 'normal')
            ->where(function ($query) use ($provinceId) {
                $query->where('province_id', 0)->whereOr('province_id', $provinceId);
            })
            ->where(function ($query) use ($cityId) {
                $query->where('city_id', 0)->whereOr('city_id', $cityId);
            })
            ->where(function ($query) use ($areaId) {
                $query->where('area_id', 0)->whereOr('area_id', $areaId);
            })
            ->find();
    }

    private static function decodeJson($value)
    {
        if (!$value) {
            return [];
        }
        if (is_array($value)) {
            return $value;
        }
        $decoded = json_decode($value, true);
        return is_array($decoded) ? $decoded : [];
    }
}
