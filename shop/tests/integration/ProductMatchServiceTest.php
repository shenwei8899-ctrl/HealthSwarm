<?php

require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'bootstrap.php';

use addons\shop\library\service\ProductMatchService;
use addons\shop\library\service\UnitConverter;
use think\Db;

function matchAssertSame($expected, $actual, $message)
{
    if ($expected !== $actual) {
        throw new RuntimeException($message . ': expected ' . var_export($expected, true) . ', got ' . var_export($actual, true));
    }
}

matchAssertSame('500.000', UnitConverter::convert('0.5', 'kg', 'g'), 'Weight conversion must be exact');
matchAssertSame('1000.000', UnitConverter::convert('1', 'l', 'ml'), 'Volume conversion must be exact');

$goods = Db::name('shop_goods')->where('status', 'normal')->order('id ASC')->find();
if (!$goods) {
    throw new RuntimeException('No active goods are available for integration testing.');
}

$suffix = date('His') . bin2hex(random_bytes(2));
Db::startTrans();
try {
    $ingredientId = Db::name('shop_ingredient')->insertGetId([
        'code' => 'TEST-' . $suffix,
        'name' => '测试食材',
        'category' => '测试',
        'default_unit' => 'g',
        'aliases_json' => json_encode([], JSON_UNESCAPED_UNICODE),
        'status' => 'normal',
        'createtime' => time(),
        'updatetime' => time(),
    ]);
    Db::name('shop_goods_ext')->insert([
        'goods_id' => $goods['id'],
        'product_type' => 'INGREDIENT',
        'allergen_tags_json' => json_encode(['peanut'], JSON_UNESCAPED_UNICODE),
        'origin' => '测试产地',
        'shelf_life_days' => 7,
        'createtime' => time(),
        'updatetime' => time(),
    ]);
    Db::name('shop_ingredient_product_map')->insert([
        'ingredient_id' => $ingredientId,
        'goods_id' => $goods['id'],
        'goods_sku_id' => 0,
        'content_quantity' => '300.000',
        'content_unit' => 'g',
        'conversion_rate' => '1.000000',
        'priority' => 1000,
        'is_substitute' => 0,
        'status' => 'normal',
        'createtime' => time(),
        'updatetime' => time(),
    ]);
    $supplierId = Db::name('shop_supplier')->insertGetId([
        'code' => 'TEST-S-' . $suffix,
        'name' => '测试供应商',
        'fulfillment_mode' => 'SUPPLIER_DIRECT',
        'api_type' => 'MANUAL',
        'priority' => 1000,
        'status' => 'normal',
        'createtime' => time(),
        'updatetime' => time(),
    ]);
    $supplierSkuId = Db::name('shop_supplier_sku')->insertGetId([
        'supplier_id' => $supplierId,
        'goods_id' => $goods['id'],
        'goods_sku_id' => 0,
        'supplier_goods_code' => 'TEST-G-' . $suffix,
        'supplier_sku_code' => 'TEST-SKU-' . $suffix,
        'supply_price' => '5.00',
        'delivery_days' => 1,
        'fulfillment_mode' => 'SUPPLIER_DIRECT',
        'priority' => 1000,
        'sync_status' => 'SUCCESS',
        'status' => 'normal',
        'createtime' => time(),
        'updatetime' => time(),
    ]);
    $warehouseId = Db::name('shop_warehouse')->insertGetId([
        'code' => 'TEST-W-' . $suffix,
        'name' => '测试直发仓',
        'owner_type' => 'SUPPLIER',
        'owner_id' => $supplierId,
        'warehouse_type' => 'VIRTUAL_DIRECT',
        'status' => 'normal',
        'createtime' => time(),
        'updatetime' => time(),
    ]);
    Db::name('shop_warehouse_sku')->insert([
        'warehouse_id' => $warehouseId,
        'supplier_id' => $supplierId,
        'supplier_sku_id' => $supplierSkuId,
        'goods_id' => $goods['id'],
        'goods_sku_id' => 0,
        'on_hand_qty' => 5,
        'locked_qty' => 0,
        'unavailable_qty' => 0,
        'in_transit_qty' => 0,
        'version' => 0,
        'createtime' => time(),
        'updatetime' => time(),
    ]);
    Db::name('shop_warehouse_sku')
        ->where('goods_id', $goods['id'])
        ->where('goods_sku_id', 0)
        ->where('supplier_id', 0)
        ->update(['on_hand_qty' => 0, 'updatetime' => time()]);

    $result = ProductMatchService::match($ingredientId, '0.5', 'kg');
    matchAssertSame(true, $result['matched'], 'Ingredient must match an available supplier product');
    matchAssertSame(2, $result['selected']['purchase_quantity'], 'Package quantity must cover the requirement');
    matchAssertSame('600.000', $result['selected']['covered_quantity'], 'Coverage quantity must be calculated');
    matchAssertSame('100.000', $result['selected']['excess_quantity'], 'Excess quantity must be calculated');
    matchAssertSame((int)$supplierId, $result['selected']['supplier_id'], 'The actual supplier must be returned');

    $blocked = ProductMatchService::match($ingredientId, '500', 'g', [
        'excluded_allergen_tags' => ['peanut'],
    ]);
    matchAssertSame(false, $blocked['matched'], 'Excluded allergens must remove the product');

    Db::rollback();
} catch (Throwable $e) {
    Db::rollback();
    throw $e;
}

echo "ProductMatchService integration test passed.\n";
