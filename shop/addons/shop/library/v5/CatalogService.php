<?php

namespace addons\shop\library\v5;

use think\Db;

class CatalogService
{
    public function listProducts(array $filters = [])
    {
        $limit = isset($filters['limit']) ? (int)$filters['limit'] : 100;
        $limit = max(1, min(200, $limit));
        $cursorId = $this->decodeCursor(isset($filters['cursor']) ? $filters['cursor'] : '');

        $query = Db::name('shop_goods_sku')->alias('s')
            ->join('shop_goods g', 'g.id=s.goods_id')
            ->where('g.agent_visible', 1)
            ->where('g.catalog_status', 'published')
            ->where('g.status', 'normal')
            ->where('s.id', '>', $cursorId);

        if (!empty($filters['updated_after'])) {
            $updated = is_numeric($filters['updated_after']) ? (int)$filters['updated_after'] : strtotime($filters['updated_after']);
            if ($updated) {
                $query->where('g.updatetime|s.updatetime', '>', $updated);
            }
        }
        if (!empty($filters['category_codes'])) {
            $query->where('g.business_category_code', 'in', (array)$filters['category_codes']);
        }
        if (!empty($filters['ingredient_codes'])) {
            $ingredientIds = Db::name('shop_ingredient')->where('ingredient_code', 'in', (array)$filters['ingredient_codes'])->column('id');
            if (!$ingredientIds) {
                return ['items' => [], 'next_cursor' => '', 'has_more' => false, 'catalog_version' => $this->currentVersion()];
            }
            $skuIds = Db::name('shop_ingredient_sku_map')->where('ingredient_id', 'in', $ingredientIds)->where('status', 'normal')->column('sku_id');
            $query->where('s.id', 'in', $skuIds ?: [0]);
        }

        $rows = $query->field([
            's.id' => 'sku_pk', 's.goods_id', 's.sku_id', 's.sku_code', 's.image' => 'sku_image',
            's.price' => 'sku_price', 's.stocks', 's.reserved_stock', 's.safety_stock',
            's.net_content_value', 's.net_content_unit', 's.updatetime' => 'sku_updated_at',
            'g.title', 'g.image', 'g.business_category_code', 'g.data_completeness',
            'g.catalog_version', 'g.updatetime' => 'goods_updated_at',
        ])->order('s.id', 'asc')->limit($limit + 1)->select();

        $hasMore = count($rows) > $limit;
        if ($hasMore) {
            array_pop($rows);
        }
        $items = [];
        foreach ($rows as $row) {
            $item = $this->formatCatalogItem($row);
            if (!isset($filters['available_only']) || $filters['available_only'] !== false) {
                if ($item['sale_status'] !== 'available') {
                    continue;
                }
            }
            $items[] = $item;
        }
        $last = end($rows);
        return [
            'items'           => $items,
            'next_cursor'     => $hasMore && $last ? $this->encodeCursor($last['sku_pk']) : '',
            'has_more'        => $hasMore,
            'catalog_version' => $this->currentVersion(),
        ];
    }

    public function getSku($skuId, $includeUnavailable = true)
    {
        $row = Db::name('shop_goods_sku')->alias('s')
            ->join('shop_goods g', 'g.id=s.goods_id')
            ->where('s.id', (int)$skuId)
            ->field([
                's.id' => 'sku_pk', 's.goods_id', 's.sku_id', 's.sku_code', 's.image' => 'sku_image',
                's.price' => 'sku_price', 's.stocks', 's.reserved_stock', 's.safety_stock',
                's.net_content_value', 's.net_content_unit', 's.updatetime' => 'sku_updated_at',
                'g.title', 'g.image', 'g.business_category_code', 'g.data_completeness',
                'g.catalog_version', 'g.agent_visible', 'g.catalog_status', 'g.status' => 'goods_status',
                'g.updatetime' => 'goods_updated_at',
            ])->find();
        if (!$row) {
            throw new DomainException('SKU不存在', 40401, 404);
        }
        $item = $this->formatCatalogItem($row);
        if (!$includeUnavailable && $item['sale_status'] !== 'available') {
            throw new DomainException('SKU当前不可售', 40904, 409, ['sku_id' => (string)$skuId]);
        }
        return $item;
    }

    public function alternatives($skuId, array $filters = [])
    {
        $source = $this->getSku($skuId, true);
        $map = Db::name('shop_ingredient_sku_map')->where('sku_id', (int)$skuId)->where('status', 'normal')->order('priority', 'desc')->find();
        if (!$map) {
            return ['source' => $source, 'items' => []];
        }
        $rows = Db::name('shop_ingredient_sku_map')->where('ingredient_id', $map['ingredient_id'])
            ->where('status', 'normal')->where('sku_id', '<>', (int)$skuId)
            ->order('priority', 'desc')->limit(min(50, max(1, (int)(isset($filters['limit']) ? $filters['limit'] : 10))))->select();
        $required = isset($filters['required_quantity_value']) ? (float)$filters['required_quantity_value'] : (float)$map['net_value'];
        $items = [];
        foreach ($rows as $candidate) {
            try {
                $item = $this->getSku($candidate['sku_id'], false);
            } catch (DomainException $e) {
                continue;
            }
            $net = max(0.001, (float)$candidate['net_value']);
            $packs = (int)ceil($required / $net);
            $item['required_pack_count'] = $packs;
            $item['covered_value'] = number_format($packs * $net, 3, '.', '');
            $item['covered_unit'] = $candidate['net_unit'];
            $item['surplus_value'] = number_format(max(0, $packs * $net - $required), 3, '.', '');
            $item['alternative_reason'] = 'same_ingredient';
            $items[] = $item;
        }
        return ['source' => $source, 'items' => $items];
    }

    public function currentVersion()
    {
        $row = Db::name('shop_catalog_version')->order('id', 'desc')->find();
        return $row ? $row['catalog_version'] : 'catalog_0';
    }

    public function touchVersion($changeType, $resourceRef, $summary = '')
    {
        $version = Identifiers::make('catalog');
        Db::name('shop_catalog_version')->insert([
            'catalog_version' => $version,
            'change_type'     => $changeType,
            'resource_ref'    => (string)$resourceRef,
            'summary'         => $summary,
            'createtime'      => time(),
        ]);
        return $version;
    }

    protected function formatCatalogItem(array $row)
    {
        $skuId = (int)$row['sku_pk'];
        $available = max(0, (int)$row['stocks'] - (int)$row['reserved_stock'] - (int)$row['safety_stock']);
        $catalogAllowed = (!isset($row['agent_visible']) || (int)$row['agent_visible'] === 1)
            && (!isset($row['catalog_status']) || $row['catalog_status'] === 'published')
            && (!isset($row['goods_status']) || $row['goods_status'] === 'normal');

        $maps = Db::name('shop_ingredient_sku_map')->alias('m')
            ->join('shop_ingredient i', 'i.id=m.ingredient_id')
            ->where('m.sku_id', $skuId)->where('m.status', 'normal')
            ->field('i.ingredient_code,i.name,m.role,m.net_value,m.net_unit,m.convert_ratio,m.loss_rate')
            ->order('m.priority', 'desc')->select();
        $nutrition = Db::name('shop_sku_nutrition_fact')->where('sku_id', $skuId)
            ->where('status', 'normal')->order('valid_from', 'desc')->find();
        $allergenCodes = Db::name('shop_sku_ingredient_component')->alias('c')
            ->join('shop_ingredient i', 'i.id=c.ingredient_id')
            ->where('c.sku_id', $skuId)->where('c.allergen_flag', 1)->column('i.ingredient_code');

        return [
            'catalog_version'      => isset($row['catalog_version']) ? (string)$row['catalog_version'] : $this->currentVersion(),
            'product_id'           => (string)$row['goods_id'],
            'sku_id'               => (string)$skuId,
            'product_name'         => $row['title'],
            'sku_name'             => $row['sku_id'] !== '' ? $row['sku_id'] : $row['title'],
            'sku_code'             => $row['sku_code'],
            'category_code'        => $row['business_category_code'],
            'image_url'            => $row['sku_image'] ?: $row['image'],
            'sale_status'          => $catalogAllowed && $available > 0 ? 'available' : 'unavailable',
            'unavailable_reason'   => !$catalogAllowed ? 'not_published' : ($available <= 0 ? 'out_of_stock' : null),
            'price_cent'           => (int)round(((float)$row['sku_price']) * 100),
            'available_stock_level'=> $available <= 0 ? 'out' : ($available <= max(5, (int)$row['safety_stock']) ? 'low' : 'sufficient'),
            'net_content'          => ['value' => number_format((float)$row['net_content_value'], 3, '.', ''), 'unit' => $row['net_content_unit']],
            'ingredients'          => $maps,
            'allergen_codes'       => array_values($allergenCodes),
            'nutrition_facts'      => $nutrition ?: null,
            'data_completeness'    => $row['data_completeness'],
            'updated_at'           => date(DATE_ATOM, max((int)$row['sku_updated_at'], (int)$row['goods_updated_at'])),
            'valid_until'          => date(DATE_ATOM, time() + 300),
        ];
    }

    protected function encodeCursor($id)
    {
        return rtrim(strtr(base64_encode('sku:' . (int)$id), '+/', '-_'), '=');
    }

    protected function decodeCursor($cursor)
    {
        if (!$cursor) {
            return 0;
        }
        $decoded = base64_decode(strtr($cursor, '-_', '+/'));
        return strpos($decoded, 'sku:') === 0 ? (int)substr($decoded, 4) : 0;
    }
}
