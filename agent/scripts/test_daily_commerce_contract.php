<?php
/** 独立验证推荐包汇总校验，不连接商城数据库。 */
namespace addons\shop\library\v5 {
    class ProductMatchService
    {
        public static $catalog = [];

        public function validateSubmittedItem(array $item)
        {
            $sku = self::$catalog[$item['sku_id']];
            return ['issue' => null, 'selected' => [
                'sku_id' => $item['sku_id'], 'quantity' => $item['quantity'],
                'total_price_cent' => 800 * $item['quantity'], 'product_snapshot' => $sku,
            ]];
        }
    }
}

namespace {
    use addons\shop\library\v5\ProductMatchService;

    require $argv[1] . '/addons/shop/library/v5/RecommendationPackageService.php';

    class PackageContract extends \addons\shop\library\v5\RecommendationPackageService
    {
        public function check(array $payload) { return $this->buildItems($payload); }
    }

    function requireCase($valid, $name)
    {
        if (!$valid) throw new \RuntimeException($name);
    }

    ProductMatchService::$catalog = ['7' => ['available_quantity' => 3, 'ingredients' => [[
        'ingredient_code' => 'vegetable-A', 'net_value' => 100, 'net_unit' => 'g',
        'convert_ratio' => 1, 'loss_rate' => 0, 'review_status' => 'approved',
    ]]]];
    $input = ['items' => [['sku_id' => '7', 'quantity' => 2]], 'ingredient_requirements' => [[
        'ingredient_code' => 'vegetable-A', 'required_value' => '150', 'required_unit' => 'g',
    ]]];
    $service = new PackageContract();
    $result = $service->check($input);
    requireCase(!$result['issues'] && $result['total_amount_cent'] === 1600, 'approved_coverage_and_price');

    $input['items'][] = ['sku_id' => '7', 'quantity' => 2];
    $result = $service->check($input);
    requireCase(in_array('out_of_stock', array_column($result['issues'], 'issue_code'), true), 'aggregate_stock');
    array_pop($input['items']);

    ProductMatchService::$catalog['7']['ingredients'][0]['review_status'] = 'pending';
    $result = $service->check($input);
    requireCase(in_array('ingredient_uncovered', array_column($result['issues'], 'issue_code'), true), 'pending_mapping');
    ProductMatchService::$catalog['7']['ingredients'][0]['review_status'] = 'approved';
    $input['ingredient_requirements'][0]['required_value'] = '201';
    requireCase((bool)$service->check($input)['issues'], 'insufficient_coverage');

    $input['ingredient_requirements'][0]['required_value'] = '150';
    $input['ingredient_requirements'][0]['required_unit'] = 'ml';
    requireCase((bool)$service->check($input)['issues'], 'unit_mismatch');
    ProductMatchService::$catalog['7']['ingredients'][0]['net_unit'] = 'ml';
    requireCase(!$service->check($input)['issues'], 'preserve_existing_same_unit_contract');

    $input['ingredient_requirements'][] = [
        'ingredient_code' => 'optional-A', 'required_value' => 10, 'required_unit' => 'g', 'is_optional' => true,
    ];
    requireCase(!$service->check($input)['issues'], 'preserve_optional_ingredient');
    echo json_encode(['passed' => 7, 'database_access' => false]) . "\n";
}
