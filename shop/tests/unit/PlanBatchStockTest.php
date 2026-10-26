<?php

namespace addons\shop\library\v5;

// 仅替换目录读取；实际复合包装匹配与库存分配由 PlanRequirements 执行。
class ProductMatchService
{
    public static $skus = [];

    public function matchRequirement(array $requirement, array $allowed, array $codes)
    {
        $candidates = [];
        foreach (self::$skus as $id => $sku) {
            if (!in_array($id, $allowed, true)) continue;
            $perPack = 0;
            foreach ($sku['ingredients'] as $map) {
                if ($map['ingredient_code'] === $requirement['ingredient_code']) {
                    $perPack += CatalogEligibility::convert($map['net_value'], 'g', $requirement['required_unit']) ?? 0;
                }
            }
            if ($perPack <= 0) continue;
            $quantity = (int)ceil($requirement['required_value'] / $perPack);
            if ($quantity > $sku['available_quantity']) continue;
            $candidates[] = ['sku_id'=>$id, 'quantity'=>$quantity, 'covered_value'=>$quantity*$perPack,
                'total_price_cent'=>$quantity*$sku['price_cent'], 'product_snapshot'=>$sku];
        }
        return ['selected'=>$candidates[0] ?? null, 'candidates'=>$candidates,
            'issue'=>$candidates ? null : ['issue_code'=>'out_of_stock']];
    }
}

require dirname(__DIR__, 2) . '/addons/shop/library/v5/CatalogEligibility.php';
require dirname(__DIR__, 2) . '/addons/shop/library/v5/PlanRequirements.php';

function batchAssert($condition, $message)
{
    if (!$condition) throw new \RuntimeException($message);
}

function syntheticPack($a, $b, $stock, $price)
{
    return ['available_quantity'=>$stock, 'price_cent'=>$price, 'ingredients'=>[
        ['ingredient_code'=>'A', 'net_value'=>$a, 'net_unit'=>'g', 'convert_ratio'=>1, 'loss_rate'=>0],
        ['ingredient_code'=>'B', 'net_value'=>$b, 'net_unit'=>'g', 'convert_ratio'=>1, 'loss_rate'=>0],
    ]];
}

$meals = [['meal_type'=>'dinner', 'recipe_ref'=>'synthetic', 'recipe_version_ref'=>'v1', 'ingredient_requirements'=>[
    ['ingredient_code'=>'A', 'required_value'=>10, 'required_unit'=>'g'],
    ['ingredient_code'=>'B', 'required_value'=>10, 'required_unit'=>'g'],
]]];
ProductMatchService::$skus = ['X'=>syntheticPack(10, 5, 1, 100), 'Y'=>syntheticPack(10, 10, 1, 200)];
$matched = PlanRequirements::matchBatch($meals, ['X', 'Y']);
batchAssert($matched['issues'] === [], 'A feasible composite alternative must not report no stock');
$coverage = ['A'=>0, 'B'=>0];
foreach ($matched['items'] as $item) {
    batchAssert($item['quantity'] <= ProductMatchService::$skus[$item['sku_id']]['available_quantity'], 'Same batch over-allocated stock');
    foreach ($item['product_snapshot']['ingredients'] as $map) $coverage[$map['ingredient_code']] += $map['net_value'] * $item['quantity'];
}
batchAssert($coverage['A'] >= 10 && $coverage['B'] >= 10, 'The selected batch must actually cover both ingredients');

ProductMatchService::$skus = ['X'=>syntheticPack(10, 5, 1, 100)];
$blocked = PlanRequirements::matchBatch($meals, ['X']);
batchAssert($blocked['items'] === [] && $blocked['issues'][0]['issue_code'] === 'out_of_stock', 'Insufficient stock must remain blocked');
ProductMatchService::$skus['X']['available_quantity'] = 2;
$reused = PlanRequirements::matchBatch($meals, ['X']);
batchAssert($reused['issues'] === [] && count($reused['items']) === 1 && $reused['items'][0]['quantity'] === 2, 'One SKU may cover the remaining component only within stock');
batchAssert($reused['items'][0]['total_price_cent'] === 200, 'Repeated SKU must count each purchased pack once');
$excluded = PlanRequirements::matchBatch($meals, []);
batchAssert($excluded['items'] === [] && $excluded['issues'] !== [], 'Matching must not escape the approved SKU range');
echo "Composite batch stock passed: feasible alternative, shortage, shared stock, approved range.\n";
