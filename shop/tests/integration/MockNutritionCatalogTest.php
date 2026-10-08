<?php

require dirname(__DIR__) . DIRECTORY_SEPARATOR . 'bootstrap.php';

use addons\shop\library\service\ProductMatchService;
use think\Db;

function mockCatalogAssert($condition, $message)
{
    if (!$condition) {
        throw new RuntimeException($message);
    }
}

$goods = Db::name('shop_goods')->where('goods_sn', 'like', 'MOCK_NUTRITION_%')->where('status', 'normal')->select();
mockCatalogAssert(count($goods) === 5, 'Five MOCK nutrition goods must be available.');
mockCatalogAssert(Db::name('shop_goods')->count() === 5, 'Legacy products must be removed from the reset catalog.');
mockCatalogAssert(Db::name('shop_goods_sku')->count() === 5, 'The reset catalog must contain one SKU per MOCK product.');
mockCatalogAssert(Db::name('shop_order')->where('order_sn', 'like', 'MOCK-ORD-%')->count() === 10, 'The operations seed must provide ten lifecycle orders.');
mockCatalogAssert(Db::name('shop_order_goods')->alias('og')->join('__SHOP_ORDER__ o', 'o.order_sn=og.order_sn')->where('o.order_sn', 'like', 'MOCK-ORD-%')->count() === 10, 'Every MOCK order must have one order item.');
mockCatalogAssert(Db::name('shop_warehouse_sku')->count() === 10, 'The reset catalog must contain two inventory sources per MOCK SKU.');
mockCatalogAssert(Db::name('shop_category')->count() === 19, 'The nutrition category tree must contain 19 MOCK categories.');
mockCatalogAssert(Db::name('shop_category')->where('name', 'in', ['电子产品', '数码手机', '食物饮品', '母婴玩具'])->count() === 0, 'Legacy demo-store categories must be removed.');
mockCatalogAssert(Db::name('shop_goods')->where('goods_sn', 'like', 'MOCK_NUTRITION_%')->where('category_id', 0)->count() === 0, 'Every MOCK nutrition good must be assigned to a nutrition category.');
mockCatalogAssert(Db::name('shop_goods')->where('goods_sn', 'not like', 'MOCK_NUTRITION_%')->where('category_id', '<>', 0)->count() === 0, 'Legacy goods must remain unclassified after the category reset.');
mockCatalogAssert(Db::name('shop_goods_ext')->alias('ge')->join('__SHOP_GOODS__ g', 'g.id=ge.goods_id')->where('g.goods_sn', 'like', 'MOCK_NUTRITION_%')->count() === 5, 'Every MOCK nutrition good must have extension data.');
mockCatalogAssert(Db::name('shop_ingredient')->where('code', 'like', 'MOCK_INGREDIENT_%')->where('status', 'normal')->count() === 5, 'Five MOCK ingredients must be available.');
mockCatalogAssert(Db::name('shop_ingredient_product_map')->alias('m')->join('__SHOP_INGREDIENT__ i', 'i.id=m.ingredient_id')->where('i.code', 'like', 'MOCK_INGREDIENT_%')->where('m.status', 'normal')->count() === 5, 'Every MOCK ingredient must have a product map.');

$suppliers = Db::name('shop_supplier')->where('code', 'in', ['MOCK_SUPPLIER_FRESH', 'MOCK_SUPPLIER_PANTRY'])->where('status', 'normal')->column('id');
mockCatalogAssert(count($suppliers) === 2, 'Two MOCK suppliers must be available.');
$shared = Db::name('shop_supplier_sku')->where('supplier_id', 'in', $suppliers)->where('status', 'normal')->group('goods_id,goods_sku_id')->having('COUNT(DISTINCT supplier_id) = 2')->count();
mockCatalogAssert($shared === 5, 'Every MOCK SKU must have two supplier sources.');
mockCatalogAssert(Db::name('shop_stock_batch')->where('batch_no', 'like', 'MOCK-BATCH-%')->count() === 10, 'MOCK stock batches must be available for both suppliers.');
mockCatalogAssert(Db::name('shop_shopping_list')->where('list_sn', 'MOCK_LIST_WEEKLY_NUTRITION')->where('status', 'CONFIRMED')->count() === 1, 'A confirmed MOCK shopping list must be available.');

$ingredient = Db::name('shop_ingredient')->where('code', 'MOCK_INGREDIENT_OAT')->find();
$match = ProductMatchService::match((int)$ingredient['id'], 500, 'g', [], ['province_id' => 0, 'city_id' => 0, 'area_id' => 0]);
mockCatalogAssert($match['matched'] === true, 'MOCK oat must match a saleable supplier SKU.');
mockCatalogAssert($match['selected']['supplier_id'] === (int)$suppliers[0] || $match['selected']['supplier_id'] === (int)$suppliers[1], 'MOCK match must return a MOCK supplier.');

echo "MOCK nutrition catalog integration test passed.\n";
