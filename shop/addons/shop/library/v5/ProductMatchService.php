<?php

namespace addons\shop\library\v5;

use think\Db;

class ProductMatchService
{
    public function matchRequirement(array $requirement)
    {
        foreach (['ingredient_code', 'required_value', 'required_unit'] as $field) {
            if (!isset($requirement[$field]) || $requirement[$field] === '') {
                throw new DomainException('食材需求字段不完整', 40004, 400, ['field' => $field]);
            }
        }
        if (!is_numeric($requirement['required_value']) || !is_finite((float)$requirement['required_value']) || (float)$requirement['required_value'] <= 0) throw new DomainException('采购数量必须为正数', 40004, 400);
        $ingredient = Db::name('shop_ingredient')->where('ingredient_code', $requirement['ingredient_code'])->where('status', 'normal')->find();
        if (!$ingredient) {
            return ['selected' => null, 'candidates' => [], 'issue' => $this->issue('ingredient_unmapped', null, '标准食材未维护')];
        }
        $maps = Db::name('shop_ingredient_sku_map')->where('ingredient_id', $ingredient['id'])
            ->where('status', 'normal')->where('review_status', 'approved')
            ->order('priority', 'desc')->select();
        $maps = array_values(array_filter($maps, [CatalogEligibility::class, 'current']));
        if (!$maps) return ['selected'=>null,'candidates'=>[],'issue'=>$this->issue('ingredient_mapping_unapproved',null,'缺少已审核且在有效期内的商品食材关联')];
        $candidates = [];
        $unitCompatible = false;
        $catalog = new CatalogService();
        foreach ($maps as $map) {
            $netValue = CatalogEligibility::convert($map['net_value'], $map['net_unit'], $requirement['required_unit']);
            if ($netValue === null) continue;
            $unitCompatible = true;
            try {
                $sku = $catalog->getSku($map['sku_id'], false);
            } catch (DomainException $e) {
                continue;
            }
            $effectiveNet = $netValue * (float)$map['convert_ratio'] * (1 - (float)$map['loss_rate']);
            if ($effectiveNet <= 0) {
                continue;
            }
            $packs = (int)ceil((float)$requirement['required_value'] / $effectiveNet);
            if ($packs < 1 || $packs > (int)$sku['available_quantity']) continue;
            $covered = $packs * $effectiveNet;
            $candidates[] = [
                'sku_id'             => $sku['sku_id'],
                'ingredient_id'      => (string)$ingredient['id'],
                'ingredient_code'    => $ingredient['ingredient_code'],
                'quantity'           => $packs,
                'covered_value'      => number_format($covered, 3, '.', ''),
                'covered_unit'       => $requirement['required_unit'],
                'surplus_value'      => number_format(max(0, $covered - (float)$requirement['required_value']), 3, '.', ''),
                'unit_price_cent'    => $sku['price_cent'],
                'total_price_cent'   => $sku['price_cent'] * $packs,
                'match_score'        => max(0, 10000 - (int)round(max(0, $covered - (float)$requirement['required_value']) * 10) + (int)$map['priority']),
                'product_snapshot'   => $sku,
                'requires_agent_revalidation' => false,
            ];
        }
        usort($candidates, function ($a, $b) {
            if ($a['match_score'] === $b['match_score']) {
                return $a['total_price_cent'] - $b['total_price_cent'];
            }
            return $b['match_score'] - $a['match_score'];
        });
        if (!$candidates) {
            return ['selected' => null, 'candidates' => [], 'issue' => $this->issue($unitCompatible ? 'out_of_stock' : 'unit_conversion_missing', null, $unitCompatible ? '没有足量库存的可售同食材SKU' : '需求单位与商品单位不兼容，需提供审核换算')];
        }
        return ['selected' => $candidates[0], 'candidates' => $candidates, 'issue' => null];
    }

    public function validateSubmittedItem(array $item)
    {
        if (empty($item['sku_id']) || !isset($item['quantity']) || !ctype_digit((string)$item['quantity']) || (int)$item['quantity'] < 1) {
            return ['selected' => null, 'issue' => $this->issue('invalid_item', isset($item['sku_id']) ? $item['sku_id'] : null, 'SKU或数量缺失')];
        }
        try {
            $sku = (new CatalogService())->getSku($item['sku_id'], false);
        } catch (DomainException $e) {
            return ['selected' => null, 'issue' => $this->issue('out_of_stock', $item['sku_id'], $e->getMessage())];
        }
        if ((int)$item['quantity'] > (int)$sku['available_quantity']) return ['selected'=>null,'issue'=>$this->issue('out_of_stock',$item['sku_id'],'所需数量超过可用库存')];
        $selected = [
            'sku_id'          => (string)$item['sku_id'],
            'ingredient_id'   => isset($item['ingredient_id']) ? (string)$item['ingredient_id'] : '0',
            'ingredient_code' => isset($item['ingredient_code']) ? $item['ingredient_code'] : '',
            'quantity'        => max(1, (int)$item['quantity']),
            'covered_value'   => isset($item['covers_value']) ? (string)$item['covers_value'] : '0.000',
            'covered_unit'    => isset($item['covers_unit']) ? $item['covers_unit'] : '',
            'unit_price_cent' => $sku['price_cent'],
            'total_price_cent'=> $sku['price_cent'] * max(1, (int)$item['quantity']),
            'product_snapshot'=> $sku,
            'requires_agent_revalidation' => false,
        ];
        return ['selected' => $selected, 'issue' => null];
    }

    protected function issue($code, $skuId, $message)
    {
        return [
            'issue_code' => $code,
            'sku_id' => $skuId === null ? null : (string)$skuId,
            'message' => $message,
            'retryable' => in_array($code, ['out_of_stock', 'price_changed'], true),
            'requires_agent_revalidation' => $code === 'ingredient_unmapped',
            'alternative_sku_ids' => [],
        ];
    }
}
