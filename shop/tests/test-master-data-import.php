<?php

require __DIR__ . DIRECTORY_SEPARATOR . 'bootstrap.php';

use addons\shop\library\v5\MasterDataImportService;
use PhpOffice\PhpSpreadsheet\IOFactory;
use PhpOffice\PhpSpreadsheet\Writer\Xlsx;
use think\Db;

$service = new MasterDataImportService();
$suffix = strtoupper(substr(hash('sha256', uniqid('', true)), 0, 8));
$categoryCode = 'TEST-CAT-' . $suffix;
$goodsCode = 'TEST-GOODS-' . $suffix;
$skuCode = 'TEST-SKU-' . $suffix;
$ingredientCode = 'TEST-ING-' . $suffix;
$files = [];
$batchIds = [];
$batchSns = [];

try {
    $valid = $service->createTemplate();
    $files[] = $valid;
    $book = IOFactory::load($valid);
    $book->getSheetByName('分类')->fromArray([$categoryCode, '测试分类', '', 1, 1, 'normal'], null, 'A2');
    $book->getSheetByName('商品')->fromArray([$goodsCode, '测试商品', $categoryCode, 'normal', '导入测试', 12.50, 15.00, 0.5, '', 1, 'published', 'normal'], null, 'A2');
    $book->getSheetByName('SKU')->fromArray([$skuCode, $goodsCode, '500g', 12.50, 15.00, 20, 2, 500, 'g', ''], null, 'A2');
    $book->getSheetByName('食材')->fromArray([$ingredientCode, '测试食材', $categoryCode, 'g', '导入测试', 'normal'], null, 'A2');
    $book->getSheetByName('营养资料')->fromArray([$skuCode, 'per_100g', 100, 'g', 100, 10, 2, 12, 3, 20, '测试来源', 'v1', 'approved', 'normal'], null, 'A2');
    $book->getSheetByName('食材SKU映射')->fromArray([$ingredientCode, $skuCode, 'primary', 500, 'g', 1, 0.05, 100, 'approved', 'normal'], null, 'A2');
    (new Xlsx($book))->save($valid);
    $book->disconnectWorksheets();

    $preview = $service->preview($valid, 'valid-import.xlsx', 1);
    $batchIds[] = $preview['batch_id'];
    $batchSns[] = $preview['batch_sn'];
    assertTrue($preview['status'] === 'validated', 'valid workbook should pass preview');
    assertTrue($preview['invalid_rows'] === 0, 'valid workbook should have no invalid rows');

    $confirmed = $service->confirm($preview['batch_id'], 1);
    assertTrue($confirmed['status'] === 'imported', 'valid workbook should import');
    assertTrue($confirmed['inserted_count'] === 6, 'six master-data records should be inserted');
    assertTrue((bool)Db::name('shop_goods_sku')->where('sku_code', $skuCode)->find(), 'SKU should exist after import');

    $duplicate = $service->preview($valid, 'valid-import.xlsx', 1);
    assertTrue($duplicate['duplicate'] === true && $duplicate['batch_id'] === $preview['batch_id'], 'same file hash should reuse original batch');

    $invalid = $service->createTemplate();
    $files[] = $invalid;
    $book = IOFactory::load($invalid);
    $book->getSheetByName('商品')->fromArray(['BAD-' . $suffix, '错误商品', 'MISSING-' . $suffix, 'invalid-type', '', 'not-a-number', 1, 0, '', 1, 'draft', 'normal'], null, 'A2');
    $book->getSheetByName('商品')->fromArray(['BAD-' . $suffix, '重复商品', 'MISSING-' . $suffix, 'normal', '', 1, 1, 0, '', 1, 'draft', 'normal'], null, 'A3');
    (new Xlsx($book))->save($invalid);
    $book->disconnectWorksheets();
    $invalidPreview = $service->preview($invalid, 'invalid-import.xlsx', 1);
    $batchIds[] = $invalidPreview['batch_id'];
    assertTrue($invalidPreview['status'] === 'invalid', 'missing category should fail preview');
    assertTrue($invalidPreview['invalid_rows'] > 0, 'invalid workbook should report row errors');
    $messages = implode('|', array_column($invalidPreview['errors'], 'error_message'));
    assertTrue(strpos($messages, '分类编码不存在') !== false, 'missing references should be reported');
    assertTrue(strpos($messages, '必须是有效数字') !== false, 'invalid decimals should be reported');
    assertTrue(strpos($messages, '取值无效') !== false, 'invalid enums should be reported');
    assertTrue(strpos($messages, '工作表内重复') !== false, 'duplicate codes should be reported');

    $empty = $service->createTemplate();
    $files[] = $empty;
    $emptyPreview = $service->preview($empty, 'empty-import.xlsx', 1);
    $batchIds[] = $emptyPreview['batch_id'];
    assertTrue($emptyPreview['status'] === 'invalid' && $emptyPreview['invalid_rows'] === 1, 'empty workbook should be rejected');

    echo "Master data import integration test passed.\n";
} finally {
    $skuId = Db::name('shop_goods_sku')->where('sku_code', $skuCode)->value('id');
    $ingredientId = Db::name('shop_ingredient')->where('ingredient_code', $ingredientCode)->value('id');
    if ($skuId) {
        Db::name('shop_sku_nutrition_fact')->where('sku_id', $skuId)->delete();
        Db::name('shop_ingredient_sku_map')->where('sku_id', $skuId)->delete();
        Db::name('shop_goods_sku')->where('id', $skuId)->delete();
    }
    if ($ingredientId) Db::name('shop_ingredient')->where('id', $ingredientId)->delete();
    Db::name('shop_goods')->where('goods_sn', $goodsCode)->delete();
    Db::name('shop_goods')->where('goods_sn', 'BAD-' . $suffix)->delete();
    Db::name('shop_category')->where('business_category_code', $categoryCode)->delete();
    if ($batchIds) {
        Db::name('shop_master_data_import_row')->where('batch_id', 'in', $batchIds)->delete();
        Db::name('shop_master_data_import')->where('id', 'in', $batchIds)->delete();
    }
    if ($batchSns) Db::name('shop_catalog_version')->where('resource_ref', 'in', $batchSns)->delete();
    foreach ($files as $file) if (is_file($file)) @unlink($file);
}

function assertTrue($condition, $message)
{
    if (!$condition) throw new RuntimeException($message);
}
