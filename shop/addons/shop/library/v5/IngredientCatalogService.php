<?php

namespace addons\shop\library\v5;

use think\Db;

/** Read-only ingredient identification; pending mappings never become purchase candidates. */
class IngredientCatalogService
{
    public function listIngredients(array $filters = [])
    {
        $q = $this->text($filters, 'q', 100);
        $cursor = $this->text($filters, 'cursor', 512);
        $limit = isset($filters['limit']) ? $filters['limit'] : 50;
        if ((!is_string($limit) && !is_int($limit)) || !preg_match('/^[1-9][0-9]{0,2}$/D', (string)$limit) || (int)$limit > 200) {
            throw new DomainException('limit必须是1到200的整数', 40004, 400);
        }
        $limit = (int)$limit;
        $q = mb_strtolower($q, 'UTF-8');
        $fingerprint = hash('sha256', $q);
        $after = 0;
        if ($cursor !== '') {
            $decoded = base64_decode(strtr($cursor, '-_', '+/'), true);
            $value = $decoded === false ? null : json_decode($decoded, true);
            if (!is_array($value) || ($value['v'] ?? null) !== 1 || ($value['q'] ?? null) !== $fingerprint
                || !isset($value['id']) || !is_int($value['id']) || $value['id'] <= 0) {
                throw new DomainException('cursor无效或与查询条件不一致', 40004, 400);
            }
            $after = $value['id'];
        }
        $query = Db::name('shop_ingredient')->where('status', 'normal')->whereNull('deletetime')->where('id', '>', $after);
        if ($q !== '') {
            // Escape LIKE wildcards as literal text; bind all user input.
            $pattern = '%' . strtr($q, ['!' => '!!', '%' => '!%', '_' => '!_']) . '%';
            $aliasIds = Db::name('shop_ingredient_alias')->where('status', 'normal')
                ->whereRaw("LOWER(alias) LIKE :alias_q ESCAPE '!'", ['alias_q' => $pattern])->column('ingredient_id');
            $match = "LOWER(name) LIKE :name_q ESCAPE '!' OR LOWER(ingredient_code) LIKE :code_q ESCAPE '!'";
            // This framework version does not carry raw bindings out of a nested where closure.
            if ($aliasIds) $match .= ' OR id IN (' . implode(',', array_map('intval', $aliasIds)) . ')';
            $query->whereRaw('(' . $match . ')', ['name_q' => $pattern, 'code_q' => $pattern]);
        }
        $rows = $query->field('id,ingredient_code,name,category_code,default_unit,description,status,version,updatetime')
            ->order('id', 'asc')->limit($limit + 1)->select();
        $hasMore = count($rows) > $limit;
        if ($hasMore) array_pop($rows);
        $ids = array_column($rows, 'id');
        $aliases = $maps = [];
        if ($ids) {
            foreach (Db::name('shop_ingredient_alias')->where('ingredient_id', 'in', $ids)->where('status', 'normal')->order('id', 'asc')->select() as $alias) {
                $aliases[$alias['ingredient_id']][] = $alias['alias'];
            }
            foreach (Db::name('shop_ingredient_sku_map')->where('ingredient_id', 'in', $ids)->order('priority', 'desc')->order('id', 'asc')->select() as $map) {
                $maps[$map['ingredient_id']][] = $map;
            }
        }
        $skuIds = [];
        foreach ($maps as $group) foreach ($group as $map) $skuIds[] = (int)$map['sku_id'];
        $skus = [];
        if ($skuIds) {
            $skuRows = Db::name('shop_goods_sku')->alias('s')->join('shop_goods g', 'g.id=s.goods_id')
                ->where('s.id', 'in', array_unique($skuIds))->where('g.status', 'normal')->whereNull('g.deletetime')
                ->where('g.agent_visible', 1)->where('g.catalog_status', 'published')
                ->field('s.id,s.goods_id,s.stocks,s.reserved_stock,s.safety_stock,s.price')->select();
            foreach ($skuRows as $sku) $skus[$sku['id']] = $sku;
        }
        $items = [];
        $now = time();
        foreach ($rows as $row) {
            $valid = $pending = 0;
            $candidates = [];
            foreach ($maps[$row['id']] ?? [] as $map) {
                if ($map['status'] !== 'normal') continue;
                if ($map['review_status'] === 'pending') ++$pending;
                if ($map['review_status'] !== 'approved' || ((int)$map['valid_from'] > $now)
                    || ((int)$map['valid_to'] > 0 && (int)$map['valid_to'] <= $now)) continue;
                ++$valid;
                $sku = $skus[$map['sku_id']] ?? null;
                if (!$sku || (int)$map['goods_id'] !== (int)$sku['goods_id']
                    || (int)$sku['stocks'] - (int)$sku['reserved_stock'] - (int)$sku['safety_stock'] <= 0
                    || (float)$sku['price'] <= 0 || !is_finite((float)$sku['price'])) continue;
                if (!is_finite((float)$map['net_value']) || (float)$map['net_value'] <= 0
                    || !is_finite((float)$map['convert_ratio']) || (float)$map['convert_ratio'] <= 0
                    || !is_finite((float)$map['loss_rate']) || (float)$map['loss_rate'] < 0 || (float)$map['loss_rate'] >= 1
                    || !in_array($map['net_unit'], ['g', 'kg', 'ml', 'l', 'piece', 'pack'], true)) continue;
                $candidates[] = (string)$map['sku_id'];
            }
            $items[] = [
                'ingredient_id' => (string)$row['id'], 'ingredient_code' => $row['ingredient_code'],
                'name' => $row['name'], 'aliases' => array_values(array_unique($aliases[$row['id']] ?? [])),
                'category_code' => $row['category_code'], 'default_unit' => $row['default_unit'],
                'description' => $row['description'], 'status' => $row['status'], 'version' => (int)$row['version'],
                'updated_at' => (int)$row['updatetime'] > 0 ? date(DATE_ATOM, $row['updatetime']) : null,
                'candidate_sku_ids' => array_values(array_unique($candidates)),
                'mapping_status' => $valid ? 'approved' : ($pending ? 'pending_review' : 'no_valid_mapping'),
                'pending_mapping_count' => $pending,
                'availability_status' => $candidates ? 'available' : ($valid ? 'unavailable' : 'blocked'),
            ];
        }
        $last = end($rows);
        return [
            'items' => $items, 'has_more' => $hasMore,
            'next_cursor' => $hasMore ? rtrim(strtr(base64_encode(json_encode(['v' => 1, 'id' => (int)$last['id'], 'q' => $fingerprint])), '+/', '-_'), '=') : '',
            'catalog_version' => (new CatalogService())->currentVersion(),
            'evaluated_at' => date(DATE_ATOM, $now),
        ];
    }

    private function text(array $filters, $key, $max)
    {
        if (!array_key_exists($key, $filters)) return '';
        if (!is_string($filters[$key]) || !mb_check_encoding($filters[$key], 'UTF-8') || mb_strlen($filters[$key], 'UTF-8') > $max) {
            throw new DomainException($key . '必须是有效字符串，且不超过' . $max . '个字符', 40004, 400);
        }
        return trim($filters[$key]);
    }
}
